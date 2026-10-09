"""Provider ``github``: pull requests through the ``gh`` CLI.

Every ``gh`` call goes through ``GhCli.run``. The executable is ``gh`` found on
``PATH`` (or ``$AIFACTORY_GH``); tests put a fake one first on ``PATH``. Bodies go
in on stdin (``--body-file -``). Pushing is plain git, not ``gh``.

GitHub computes mergeability lazily and answers ``UNKNOWN`` until it is done, so
``status`` asks again a bounded number of times while an open PR is ``unknown``.
The default budget is 30 queries spaced 2 s apart (58 s of pauses), so the
auto-merge preflight also tolerates a slow upstream mergeability calculation.
If it remains unknown, auto-merge starts another batch after a pause until the
hosting reports a definitive result; ordinary status reads stay bounded.
A merge GitHub rejects with a transient error ("Base branch was modified",
"Head branch was modified" ... "try the merge again") is retried after the same
pause, at most ``retry_attempts`` times (five by default); a real conflict is never retried.

Right after a push GitHub recomputes mergeability and rejects a merge with
"Pull Request is not mergeable" until it is done. ``merge`` therefore waits for
a computed mergeability up to ``merge_attempts`` times (``MERGE_WAIT_ATTEMPTS`` x
``UNKNOWN_DELAY``, about 30 s) before merging, and retries a "not mergeable"
rejection of an open PR that is not ``CONFLICTING`` within the same bound; only
then it gives up with ``merge_failed``.

``checks`` reads ``gh pr checks ID --json name,bucket``; a PR without checks
(``no checks reported``) has ``none``. ``find_open_pr`` reads ``gh pr list --head BRANCH
--state open`` so a publish adopts a PR the hosting has but ``task_prs`` does not.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aifactory.config.settings import ProjectSettings
from aifactory.providers.base import (
    CHECKS_FAILING,
    CHECKS_NONE,
    CHECKS_PASSING,
    CHECKS_PENDING,
    CLOSED,
    CONFLICT,
    MERGEABLE,
    MERGED,
    OPEN,
    UNKNOWN,
    ChecksStatus,
    GitProvider,
    MergeFailed,
    ProviderError,
    PrStatus,
    PullRequest,
)

UNKNOWN_ATTEMPTS = 30
UNKNOWN_DELAY = 2.0
MERGE_WAIT_ATTEMPTS = 15
MERGE_RETRY_ATTEMPTS = 5

NOT_MERGEABLE = "not mergeable"

TRANSIENT_MERGE_ERRORS = (
    "base branch was modified",
    "head branch was modified",
    "try the merge again",
)


def _transient(detail: str) -> bool:
    lowered = detail.lower()
    return any(marker in lowered for marker in TRANSIENT_MERGE_ERRORS)


class GhError(ProviderError):
    def __init__(self, args: tuple[str, ...], returncode: int, stderr: str) -> None:
        self.args_ = args
        self.returncode = returncode
        self.stderr = stderr
        detail = stderr.strip() or f"exit {returncode}"
        super().__init__("gh_failed", f"gh {' '.join(args[:2])}: {detail}")


class GhCli:
    """The one place that runs ``gh``."""

    def __init__(self, cwd: Path, executable: str | None = None) -> None:
        self.cwd = cwd
        self.executable = executable or os.environ.get("AIFACTORY_GH") or "gh"

    def run(self, *args: str, stdin: str | None = None) -> str:
        try:
            result = subprocess.run(
                [self.executable, *args],
                cwd=self.cwd,
                input=stdin if stdin is not None else "",
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except FileNotFoundError as exc:
            raise ProviderError("gh_missing", "gh is not installed or not on PATH") from exc
        if result.returncode != 0:
            raise GhError(args, result.returncode, result.stderr)
        return result.stdout

    def json(self, *args: str) -> Any:
        out = self.run(*args)
        try:
            return json.loads(out)
        except json.JSONDecodeError as exc:
            raise ProviderError("gh_failed", f"gh {' '.join(args[:2])}: not JSON: {exc}") from exc


_STATUS_FIELDS = "state,mergeable,headRefOid,mergeCommit"


def _merge_oid(data: dict[str, Any]) -> str | None:
    commit = data.get("mergeCommit")
    if isinstance(commit, dict) and isinstance(commit.get("oid"), str):
        return str(commit["oid"])
    return None


class GitHubProvider(GitProvider):
    name = "github"

    def __init__(
        self,
        root: Path,
        settings: ProjectSettings,
        gh: GhCli | None = None,
        *,
        attempts: int | None = None,
        delay: float = UNKNOWN_DELAY,
        sleep: Callable[[float], None] = time.sleep,
        merge_attempts: int = MERGE_WAIT_ATTEMPTS,
    ) -> None:
        if attempts is not None and attempts < 1:
            raise ValueError(f"attempts must be at least 1, got {attempts}")
        if merge_attempts < 1:
            raise ValueError(f"merge_attempts must be at least 1, got {merge_attempts}")
        super().__init__(root, settings)
        self.gh = gh or GhCli(root)
        self.attempts = UNKNOWN_ATTEMPTS if attempts is None else attempts
        # Keep transient merge retries independent of the longer status polling budget.
        self.retry_attempts = MERGE_RETRY_ATTEMPTS if attempts is None else attempts
        self.merge_attempts = merge_attempts
        self.delay = delay
        self.sleep = sleep

    def create_pr(self, branch: str, title: str, body: str) -> PullRequest:
        out = self.gh.run(
            "pr",
            "create",
            "--base",
            self.settings.base,
            "--head",
            branch,
            "--title",
            title,
            "--body-file",
            "-",
            stdin=body,
        )
        url = next((line.strip() for line in reversed(out.splitlines()) if line.strip()), "")
        number = url.rstrip("/").rsplit("/", 1)[-1]
        if not number.isdigit():
            raise ProviderError("gh_failed", f"gh pr create: no PR URL in output {out.strip()!r}")
        return PullRequest(id=number, url=url, branch=branch, base=self.settings.base, title=title)

    def find_open_pr(self, branch: str) -> PullRequest | None:
        """``gh pr list --head BRANCH --state open``: the newest open PR of `branch`."""
        data = self.gh.json(
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "open",
            "--json",
            "number,url,title,baseRefName,headRefName",
        )
        if not isinstance(data, list):
            raise ProviderError("gh_failed", "gh pr list: expected a JSON list")
        for item in data:
            if not isinstance(item, dict) or item.get("headRefName", branch) != branch:
                continue
            number = item.get("number")
            if number is None:
                continue
            return PullRequest(
                id=str(number),
                url=str(item.get("url") or ""),
                branch=branch,
                base=str(item.get("baseRefName") or self.settings.base),
                title=str(item.get("title") or ""),
            )
        return None

    def _status_once(self, pr: PullRequest) -> PrStatus:
        data = self.gh.json("pr", "view", pr.id, "--json", _STATUS_FIELDS)
        if not isinstance(data, dict):
            raise ProviderError("gh_failed", "gh pr view: expected a JSON object")
        state = str(data.get("state", "")).upper()
        raw_head = data.get("headRefOid")
        head = raw_head if isinstance(raw_head, str) else None
        if state == "MERGED":
            return PrStatus(MERGED, head_sha=head, merge_sha=_merge_oid(data))
        if state == "CLOSED":
            return PrStatus(CLOSED, head_sha=head)
        mergeable = str(data.get("mergeable", "")).upper()
        if mergeable == "MERGEABLE":
            return PrStatus(OPEN, MERGEABLE, head_sha=head)
        if mergeable == "CONFLICTING":
            return PrStatus(OPEN, CONFLICT, head_sha=head)
        return PrStatus(OPEN, UNKNOWN, head_sha=head)

    def status(self, pr: PullRequest) -> PrStatus:
        """The PR status; an open PR with ``unknown`` mergeability is asked again."""
        return self._poll_status(pr, self.attempts)

    def _poll_status(self, pr: PullRequest, attempts: int) -> PrStatus:
        """Ask up to ``attempts`` times while an open PR's mergeability is ``unknown``."""
        for attempt in range(1, attempts + 1):
            status = self._status_once(pr)
            if status.state != OPEN or status.mergeability != UNKNOWN:
                return status
            if attempt < attempts:
                self.sleep(self.delay)
        return status

    def checks(self, pr: PullRequest) -> ChecksStatus:
        """``failing`` when any check failed or was cancelled, else ``pending`` / ``passing``."""
        try:
            data = self.gh.json("pr", "checks", pr.id, "--json", "name,bucket")
        except GhError as exc:
            if "no checks reported" in exc.stderr.lower():
                return ChecksStatus(CHECKS_NONE)
            raise
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise ProviderError("gh_failed", "gh pr checks: expected a JSON list of objects")
        if not data:
            return ChecksStatus(CHECKS_NONE)
        buckets = [str(item.get("bucket", "")).lower() for item in data]
        failing = tuple(
            str(item.get("name", "?"))
            for item, bucket in zip(data, buckets, strict=True)
            if bucket in ("fail", "cancel")
        )
        if failing:
            return ChecksStatus(CHECKS_FAILING, failing)
        if "pending" in buckets:
            return ChecksStatus(CHECKS_PENDING)
        return ChecksStatus(CHECKS_PASSING)

    def merge(
        self, pr: PullRequest, head_sha: str, subject: str, strategy: str | None = None
    ) -> str | None:
        chosen = self._strategy(strategy)
        # A push just before the merge (the ``status: done`` commit) makes GitHub
        # recompute mergeability; wait for it as long as for a "not mergeable" retry.
        current = self._poll_status(pr, self.merge_attempts)
        if current.state == MERGED:
            return current.merge_sha
        if current.state == CLOSED:
            raise MergeFailed("merge_failed", f"PR {pr.id} is closed")
        if current.mergeability == CONFLICT:
            raise MergeFailed("conflict", f"PR {pr.id} has conflicts with {pr.base}")
        attempt = 1
        waits = 1
        while True:
            try:
                self.gh.run(
                    "pr",
                    "merge",
                    pr.id,
                    f"--{chosen}",
                    "--match-head-commit",
                    head_sha,
                    "--subject",
                    subject,
                )
            except GhError as exc:
                detail = exc.stderr.strip() or exc.message
                try:
                    after: PrStatus | None = self._status_once(pr)
                except ProviderError:
                    after = None
                if after is not None and after.state == MERGED:
                    return after.merge_sha
                if after is not None and after.state == OPEN and after.mergeability == CONFLICT:
                    raise MergeFailed("conflict", f"PR {pr.id} has conflicts: {detail}") from exc
                if after is not None and after.state == CLOSED:
                    raise MergeFailed("merge_failed", detail) from exc
                if NOT_MERGEABLE in detail.lower() and after is not None and after.state == OPEN:
                    # Mergeability was still being computed; CONFLICTING was handled above.
                    if waits < self.merge_attempts:
                        waits += 1
                        self.sleep(self.delay)
                        continue
                    raise MergeFailed(
                        "merge_failed",
                        f"{detail} (mergeability {after.mergeability} after "
                        f"{self.merge_attempts} attempts)",
                    ) from exc
                if _transient(detail):
                    if attempt < self.retry_attempts:
                        attempt += 1
                        self.sleep(self.delay)
                        continue
                    detail = f"{detail} (gave up after {self.retry_attempts} attempts)"
                raise MergeFailed("merge_failed", detail) from exc
            return self._status_once(pr).merge_sha

    def update_pr(self, pr: PullRequest, body: str) -> None:
        self.gh.run("pr", "edit", pr.id, "--body-file", "-", stdin=body)

    def comment(self, pr: PullRequest, body: str) -> None:
        self.gh.run("pr", "comment", pr.id, "--body-file", "-", stdin=body)
