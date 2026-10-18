"""Provider ``azure``: pull requests on Azure DevOps through the ``az`` CLI.

Configuration lives in ``.factory/config.yaml``::

    git_provider: azure
    azure:
      organization: contoso          # or https://dev.azure.com/contoso
      project: Fabrikam
      repository: fabrikam-app

Every ``az`` call goes through ``AzCli.run``. The executable is ``az`` found on
``PATH`` (or ``$AIFACTORY_AZ``); tests put a fake one first on ``PATH``. Every call
passes ``--output json --only-show-errors``; ``az repos`` calls also pass
``--detect false`` and an explicit ``--org`` so nothing is guessed from git remotes.

Before the first operation the provider checks itself (``check``): ``az`` is
installed, the ``azure-devops`` extension is present and ``az`` is logged in
(``az account show``), unless ``$AZURE_DEVOPS_EXT_PAT`` holds a token. The result
is remembered. The constructor never runs ``az``.

Commands used (shapes from the ``az repos pr`` / ``az devops invoke`` docs):

- ``az repos pr create`` -- ``--description`` takes one value per line. Real
  ``az`` prints ``repository.webUrl: null`` here and in ``pr show``/``pr list``,
  so the PR URL is built from the settings
  (``<organization_url>/<project>/_git/<repository>/pullrequest/<id>``);
- ``az repos pr show --id`` -- status; Azure computes ``mergeStatus``
  asynchronously (``queued``/``notSet``), so ``status`` asks again a bounded
  number of times, like the GitHub provider;
- ``az repos pr update --id --description`` -- a new PR description;
- ``az repos pr set-vote --id --vote approve`` -- approval after the final push;
  head checks before and after voting detect changes, but cannot be atomic;
- ``az repos pr update --id --status completed --squash true|false`` -- merge.
  The CLI has no ``--match-head-commit``: the head is compared with
  ``lastMergeSourceCommit`` right before completing, which leaves a small race
  window. Completion can be asynchronous, so the PR is polled afterwards;
- ``az devops invoke --area git --resource pullRequestThreads`` -- comment
  (``az repos pr`` has no comment command); the body goes in a temporary
  ``--in-file``;
- ``az repos pr policy list --id`` -- CI checks (``checks``): the evaluations of
  the PR's build validation (``Build``) and status (``Status``) policies. Other
  policies (reviewers, work items, comments) are not CI and are left out.
  ``approved`` is green, ``rejected``/``broken`` red, ``queued``/``running``
  pending, ``notApplicable`` is skipped. A PR without such a policy falls back to
  ``az pipelines runs list --branch`` (the latest run of each pipeline at the
  PR's head commit), so CI triggered by the branch push counts too;
- ``az devops invoke --area build --resource timeline`` and ``--resource logs``
  -- ``check_logs``: the issues and the log tail of each failed task of a red
  build (``az pipelines runs`` has no log command). A red status policy has no
  build, its entry is a note.

A missing PR is ``ERROR: TF401180 ...`` with exit 1 (``az_failed``). Unit tests
use a fake ``az`` (``tests/providers/az_fake.py``) that prints what real ``az``
prints; ``just validate --remote azure`` runs the PR lifecycle against a real
sandbox repo.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from aifactory.config.settings import AzureSettings, ProjectSettings
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
    utc_iso,
)

UNKNOWN_ATTEMPTS = 5
UNKNOWN_DELAY = 2.0
API_VERSION = "7.1"
PAT_ENV = "AZURE_DEVOPS_EXT_PAT"
AZ_TIMEOUT = 120
WINDOWS = sys.platform == "win32"
# Azure DevOps refuses a PR description over 4000 characters; keep room for the note.
MAX_DESCRIPTION = 4000
TRUNCATED = "\n\n… (zkráceno na limit popisu PR v Azure DevOps, celé znění je v tasku a v běhu)"

CHECK_LOG_LINES = 150
"""How many trailing lines of a red check's log ``check_logs`` keeps."""
# Policy type ids of Azure DevOps (fixed across organizations).
BUILD_POLICY = "0609b952-1397-4640-95ec-e00a01b2c241"
STATUS_POLICY = "cbdc66da-9728-4af8-aada-9a5a32e4a226"
_CI_POLICIES = {BUILD_POLICY: "Build", STATUS_POLICY: "Status"}
_POLICY_STATES = {
    "approved": CHECKS_PASSING,
    "rejected": CHECKS_FAILING,
    "broken": CHECKS_FAILING,
    "queued": CHECKS_PENDING,
    "running": CHECKS_PENDING,
}
_RUNS_TOP = 50

_MISSING = "az (Azure CLI) is not installed or not on PATH; install it: https://aka.ms/azure-cli"
_NO_EXTENSION = (
    "the azure-devops extension of az is missing; run: az extension add --name azure-devops"
)
_NOT_LOGGED_IN = f"az is not logged in; run 'az login' or set {PAT_ENV}"
_NO_SECTION = (
    "git_provider 'azure' needs an 'azure' section with organization, project and repository"
)


class AzError(ProviderError):
    def __init__(self, args: tuple[str, ...], returncode: int, stderr: str) -> None:
        self.args_ = args
        self.returncode = returncode
        self.stderr = stderr
        lowered = stderr.lower()
        code = "az_not_logged_in" if "az login" in lowered or "tf400813" in lowered else "az_failed"
        detail = stderr.strip() or f"exit {returncode}"
        super().__init__(code, f"az {' '.join(args[:3])}: {detail}")


class AzCli:
    """The one place that runs ``az``."""

    def __init__(self, cwd: Path, executable: str | None = None) -> None:
        self.cwd = cwd
        self.executable = executable or os.environ.get("AIFACTORY_AZ") or "az"

    def _argv(self, args: tuple[str, ...]) -> list[str]:
        if not WINDOWS:
            return [self.executable, *args]
        resolved = shutil.which(self.executable)
        if resolved is None:
            raise ProviderError("az_missing", _MISSING)
        shim = Path(resolved)
        if shim.suffix.lower() not in (".cmd", ".bat"):
            return [resolved, *args]
        # MSI layout only: never feed arbitrary arguments through cmd.exe.
        install = shim.parent.parent
        python = install / "python.exe"
        module = install / "Lib" / "site-packages" / "azure" / "cli" / "__main__.py"
        if (
            shim.stem.lower() == "az"
            and shim.parent.name.lower() == "wbin"
            and python.is_file()
            # MSI may ship only legacy bytecode, which Python can run with -m.
            and (module.is_file() or module.with_suffix(".pyc").is_file())
        ):
            return [str(python), "-I", "-X", "utf8", "-B", "-m", "azure.cli", *args]
        raise ProviderError(
            "az_missing",
            "Unsupported Azure CLI Windows shim; install the Azure CLI MSI or set "
            "AIFACTORY_AZ to a native executable (not a .cmd/.bat wrapper).",
        )

    def run(self, *args: str) -> str:
        try:
            result = subprocess.run(
                self._argv(args),
                cwd=self.cwd,
                input="",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=AZ_TIMEOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if WINDOWS else 0,
            )
        except FileNotFoundError as exc:
            raise ProviderError("az_missing", _MISSING) from exc
        except subprocess.TimeoutExpired as exc:
            raise ProviderError("az_timeout", f"Azure CLI exceeded {AZ_TIMEOUT}s; retry") from exc
        except OSError as exc:
            raise ProviderError("az_missing", f"{_MISSING}; could not launch: {exc}") from exc
        if result.returncode != 0:
            raise AzError(args, result.returncode, result.stderr)
        return result.stdout

    def json(self, *args: str) -> Any:
        out = self.run(*args)
        try:
            return json.loads(out)
        except json.JSONDecodeError as exc:
            raise ProviderError("az_failed", f"az {' '.join(args[:3])}: not JSON: {exc}") from exc


def _commit(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if isinstance(value, dict) and isinstance(value.get("commitId"), str):
        return str(value["commitId"])
    return None


@dataclass(frozen=True)
class _Check:
    name: str
    state: str  # CHECKS_PASSING | CHECKS_PENDING | CHECKS_FAILING
    build_id: int | None = None
    note: str = ""  # where to look when there is no build log


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _policy_check(item: dict[str, Any]) -> _Check | None:
    """A CI check from one ``az repos pr policy list`` record; None for other policies."""
    config = _dict(item.get("configuration"))
    kind = _dict(config.get("type"))
    type_id = str(kind.get("id", "")).lower()
    kind_name = str(kind.get("displayName", ""))
    if type_id not in _CI_POLICIES and kind_name not in _CI_POLICIES.values():
        return None
    state = _POLICY_STATES.get(str(item.get("status", "")).lower())
    if state is None:  # notApplicable, or a status this code does not know
        return None
    settings = _dict(config.get("settings"))
    context = _dict(item.get("context"))
    build = context.get("buildId")
    build_id = build if isinstance(build, int) and not isinstance(build, bool) else None
    if kind_name == "Status" or type_id == STATUS_POLICY:
        genre = str(settings.get("statusGenre") or "")
        status_name = str(settings.get("statusName") or "")
        default = "/".join(part for part in (genre, status_name) if part) or "Status"
        name = str(settings.get("defaultDisplayName") or settings.get("displayName") or default)
        return _Check(name, state, None, f"status check {default}; see the PR in Azure DevOps")
    definition = settings.get("buildDefinitionId")
    default = f"Build {definition}" if definition is not None else "Build"
    name = str(settings.get("displayName") or context.get("buildDefinitionName") or default)
    return _Check(name, state, build_id)


def _run_check(item: dict[str, Any]) -> _Check:
    """A CI check from one ``az pipelines runs list`` record."""
    definition = _dict(item.get("definition"))
    name = str(definition.get("name") or f"pipeline {definition.get('id', '?')}")
    run = item.get("id")
    run_id = run if isinstance(run, int) and not isinstance(run, bool) else None
    if str(item.get("status", "")).lower() != "completed":
        return _Check(name, CHECKS_PENDING, run_id)
    result = str(item.get("result", "")).lower()
    passed = result in ("succeeded", "partiallysucceeded")
    return _Check(name, CHECKS_PASSING if passed else CHECKS_FAILING, run_id)


def _unique(checks: list[_Check]) -> list[_Check]:
    """``checks`` with repeated names numbered (``name (2)``), so names are keys."""
    seen: dict[str, int] = {}
    out: list[_Check] = []
    for check in checks:
        count = seen.get(check.name, 0) + 1
        seen[check.name] = count
        if count > 1:
            check = _Check(f"{check.name} ({count})", check.state, check.build_id, check.note)
        out.append(check)
    return out


def _fit(body: str) -> str:
    """``body`` cut at a line end so that it and the note fit Azure's limit (with margin)."""
    margin = 100  # the leading spaces _description_lines may add
    if len(body) <= MAX_DESCRIPTION - margin:
        return body
    limit = MAX_DESCRIPTION - margin - len(TRUNCATED)
    cut = body.rfind("\n", 0, limit)
    return body[: cut if cut > 0 else limit].rstrip() + TRUNCATED


def _description_lines(body: str) -> list[str]:
    """``body`` as ``--description`` values (one per line), within Azure's length limit.

    A line that looks like an option (``---``: starts with ``-``, no space) gets a
    leading space so argparse does not take it for one.
    """
    body = _fit(body)
    return [
        f" {line}" if line.startswith("-") and " " not in line else line
        for line in body.splitlines()
    ]


class AzureProvider(GitProvider):
    name = "azure"
    reports_checks = True

    def __init__(
        self,
        root: Path,
        settings: ProjectSettings,
        az: AzCli | None = None,
        *,
        attempts: int = UNKNOWN_ATTEMPTS,
        delay: float = UNKNOWN_DELAY,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if attempts < 1:
            raise ValueError(f"attempts must be at least 1, got {attempts}")
        super().__init__(root, settings)
        if settings.azure is None:
            raise ProviderError("invalid_config", _NO_SECTION)
        self.azure: AzureSettings = settings.azure
        self.az = az or AzCli(root)
        self.attempts = attempts
        self.delay = delay
        self.sleep = sleep
        self._checked = False

    # -- self-check ---------------------------------------------------------

    def check(self) -> None:
        """Fail with a clear ``ProviderError`` if ``az`` cannot work for this provider."""
        try:
            self.az.run("--version")
        except AzError as exc:
            raise ProviderError("az_missing", f"{_MISSING} ({exc.message})") from exc
        try:
            self.az.run("extension", "show", "--name", "azure-devops", "--output", "json")
        except AzError as exc:
            raise ProviderError("az_devops_missing", _NO_EXTENSION) from exc
        if os.environ.get(PAT_ENV):
            return
        try:
            self.az.run("account", "show", "--output", "json")
        except AzError as exc:
            raise ProviderError("az_not_logged_in", _NOT_LOGGED_IN) from exc

    def _ready(self) -> None:
        if not self._checked:
            self.check()
            self._checked = True

    # -- helpers ------------------------------------------------------------

    def _org(self) -> list[str]:
        return ["--org", self.azure.organization_url]

    @staticmethod
    def _tail() -> list[str]:
        return ["--detect", "false", "--output", "json", "--only-show-errors"]

    def _pr_url(self, data: dict[str, Any], pr_id: int) -> str:
        repository = data.get("repository")
        if isinstance(repository, dict) and isinstance(repository.get("webUrl"), str):
            return f"{str(repository['webUrl']).rstrip('/')}/pullrequest/{pr_id}"
        project = quote(self.azure.project, safe="")
        repo = quote(self.azure.repository, safe="")
        return f"{self.azure.organization_url}/{project}/_git/{repo}/pullrequest/{pr_id}"

    # -- operations ---------------------------------------------------------

    def create_pr(self, branch: str, title: str, body: str) -> PullRequest:
        self._ready()
        args = [
            "repos",
            "pr",
            "create",
            *self._org(),
            "--project",
            self.azure.project,
            "--repository",
            self.azure.repository,
            "--source-branch",
            branch,
            "--target-branch",
            self.settings.base,
            "--title",
            title,
        ]
        lines = _description_lines(body)
        if lines:
            args += ["--description", *lines]
        data = self.az.json(*args, *self._tail())
        if not isinstance(data, dict) or not isinstance(data.get("pullRequestId"), int):
            raise ProviderError("az_failed", "az repos pr create: no pullRequestId in output")
        pr_id = int(data["pullRequestId"])
        return PullRequest(
            id=str(pr_id),
            url=self._pr_url(data, pr_id),
            branch=branch,
            base=self.settings.base,
            title=title,
        )

    def find_open_pr(self, branch: str) -> PullRequest | None:
        """Find the active PR for this source branch and configured target."""
        self._ready()
        data = self.az.json(
            "repos",
            "pr",
            "list",
            *self._org(),
            "--project",
            self.azure.project,
            "--repository",
            self.azure.repository,
            "--source-branch",
            branch,
            "--target-branch",
            self.settings.base,
            "--status",
            "active",
            *self._tail(),
        )
        if not isinstance(data, list):
            raise ProviderError("az_failed", "az repos pr list: expected a JSON array")
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("pullRequestId"), int):
                raise ProviderError("az_failed", "az repos pr list: no pullRequestId in output")
            pr_id = int(item["pullRequestId"])
            return PullRequest(
                id=str(pr_id),
                url=self._pr_url(item, pr_id),
                branch=branch,
                base=self.settings.base,
                title=str(item.get("title", "")),
            )
        return None

    def _show(self, pr: PullRequest) -> dict[str, Any]:
        data = self.az.json("repos", "pr", "show", "--id", pr.id, *self._org(), *self._tail())
        if not isinstance(data, dict):
            raise ProviderError("az_failed", "az repos pr show: expected a JSON object")
        return data

    @staticmethod
    def _parse(data: dict[str, Any]) -> PrStatus:
        head = _commit(data, "lastMergeSourceCommit")
        state = str(data.get("status", "")).lower()
        if state == "completed":
            return PrStatus(
                MERGED,
                head_sha=head,
                merge_sha=_commit(data, "lastMergeCommit"),
                merged_at=utc_iso(data.get("closedDate")),
            )
        if state == "abandoned":
            return PrStatus(CLOSED, head_sha=head)
        merge_status = str(data.get("mergeStatus", "")).lower()
        if merge_status == "succeeded":
            return PrStatus(OPEN, MERGEABLE, head_sha=head)
        if merge_status == "conflicts":
            return PrStatus(OPEN, CONFLICT, head_sha=head)
        return PrStatus(OPEN, UNKNOWN, head_sha=head)

    def _status_once(self, pr: PullRequest) -> PrStatus:
        return self._parse(self._show(pr))

    def status(self, pr: PullRequest) -> PrStatus:
        """The PR status; an open PR with ``unknown`` mergeability is asked again."""
        self._ready()
        for attempt in range(1, self.attempts + 1):
            status = self._status_once(pr)
            if status.state != OPEN or status.mergeability != UNKNOWN:
                return status
            if attempt < self.attempts:
                self.sleep(self.delay)
        return status

    def approve(self, pr: PullRequest, head_sha: str) -> bool:
        """Vote after the final push, guarded by head checks (CLI is not atomic)."""
        self._ready()
        current = self._fresh_head(pr, head_sha)
        if current.state == MERGED:
            return False  # allow existing merge recovery without claiming a new review
        self._approval_head(pr, current, head_sha)
        try:
            self.az.run(
                "repos",
                "pr",
                "set-vote",
                "--id",
                pr.id,
                "--vote",
                "approve",
                *self._org(),
                *self._tail(),
            )
        except ProviderError as exc:
            raise ProviderError(
                "approve_failed", f"Azure approval vote for PR {pr.id} failed: {exc.message}"
            ) from exc
        self._approval_head(pr, self._status_once(pr), head_sha)
        return True

    def _fresh_head(self, pr: PullRequest, head_sha: str) -> PrStatus:
        """The PR status once Azure reports ``head_sha`` as its source commit.

        Azure updates ``lastMergeSourceCommit`` a moment after a push (the done
        commit pushed just before approval), so ask again a bounded number of times.
        """
        current = self._status_once(pr)
        for _ in range(self.attempts - 1):
            if current.state != OPEN or current.head_sha == head_sha:
                break
            self.sleep(self.delay)
            current = self._status_once(pr)
        return current

    @staticmethod
    def _approval_head(pr: PullRequest, current: PrStatus, head_sha: str) -> None:
        if current.state != OPEN or current.head_sha != head_sha:
            raise ProviderError(
                "approve_failed",
                f"PR {pr.id} approval head changed or PR not open: "
                f"{current.state}, {current.head_sha} != {head_sha}; merge stopped",
            )

    # -- CI checks ----------------------------------------------------------

    def _ci_checks(self, pr: PullRequest) -> list[_Check]:
        """The PR's CI checks: build and status policies, else the branch's pipeline runs."""
        self._ready()
        data = self.az.json(
            "repos", "pr", "policy", "list", "--id", pr.id, *self._org(), *self._tail()
        )
        if not isinstance(data, list):
            raise ProviderError("az_failed", "az repos pr policy list: expected a JSON array")
        policies = [check for item in data if (check := _policy_check(_dict(item))) is not None]
        if policies:
            return _unique(policies)
        return _unique(self._run_checks(pr))

    def _run_checks(self, pr: PullRequest) -> list[_Check]:
        """The latest pipeline run of each pipeline at the PR's head commit."""
        head = _commit(self._show(pr), "lastMergeSourceCommit")
        if head is None:
            return []
        data = self.az.json(
            "pipelines",
            "runs",
            "list",
            "--branch",
            f"refs/heads/{pr.branch}",
            "--project",
            self.azure.project,
            "--top",
            str(_RUNS_TOP),
            "--query-order",
            "QueueTimeDesc",
            *self._org(),
            *self._tail(),
        )
        if not isinstance(data, list):
            raise ProviderError("az_failed", "az pipelines runs list: expected a JSON array")
        latest: dict[object, _Check] = {}
        for item in data:
            run = _dict(item)
            if run.get("sourceVersion") != head:
                continue
            key = _dict(run.get("definition")).get("id", run.get("id"))
            if key not in latest:  # newest first
                latest[key] = _run_check(run)
        return list(latest.values())

    def checks(self, pr: PullRequest) -> ChecksStatus:
        """``failing`` when any check is red, else ``pending`` / ``passing`` / ``none``."""
        found = self._ci_checks(pr)
        if not found:
            return ChecksStatus(CHECKS_NONE)
        failing = tuple(check.name for check in found if check.state == CHECKS_FAILING)
        if failing:
            return ChecksStatus(CHECKS_FAILING, failing)
        if any(check.state == CHECKS_PENDING for check in found):
            return ChecksStatus(CHECKS_PENDING)
        return ChecksStatus(CHECKS_PASSING)

    def check_logs(self, pr: PullRequest, failing: tuple[str, ...]) -> dict[str, str]:
        """The issues and log tail of the failed tasks of each red check's build.

        Only the last ``CHECK_LOG_LINES`` lines are kept. A check without a build, or
        whose log cannot be read, gets ``log unavailable: ...`` instead; only a failure
        to read the checks themselves raises.
        """
        if not failing:
            return {}
        by_name = {check.name: check for check in self._ci_checks(pr)}
        logs: dict[str, str] = {}
        for name in failing:
            check = by_name.get(name)
            if check is None or check.build_id is None:
                note = check.note if check is not None and check.note else "no build"
                logs[name] = f"log unavailable: {note}"
                continue
            try:
                text = self._build_log(check.build_id)
            except ProviderError as exc:
                detail = (getattr(exc, "stderr", "") or exc.message).strip().splitlines()
                first = detail[0] if detail else exc.code
                logs[name] = f"log unavailable: {first} (build {check.build_id})"
                continue
            lines = text.splitlines()[-CHECK_LOG_LINES:]
            logs[name] = "\n".join(lines) if lines else f"log empty (build {check.build_id})"
        return logs

    def _invoke_build(self, resource: str, *route: str) -> Any:
        return self.az.json(
            "devops",
            "invoke",
            "--area",
            "build",
            "--resource",
            resource,
            "--route-parameters",
            f"project={self.azure.project}",
            *route,
            "--api-version",
            API_VERSION,
            *self._org(),
            "--output",
            "json",
            "--only-show-errors",
        )

    def _build_log(self, build_id: int) -> str:
        """The issues and log lines of the failed tasks of build `build_id`."""
        timeline = self._invoke_build("timeline", f"buildId={build_id}")
        records = _dict(timeline).get("records")
        if not isinstance(records, list):
            raise ProviderError("az_failed", "build timeline: no records")
        failed = [
            record
            for item in records
            if (record := _dict(item)).get("type") == "Task"
            and str(record.get("result", "")).lower() == "failed"
        ]
        failed.sort(key=lambda record: int(record.get("order") or 0))
        out: list[str] = []
        for record in failed:
            out.append(f"## {record.get('name', '?')}")
            for issue in record.get("issues") or []:
                issue = _dict(issue)
                if issue.get("message"):
                    out.append(f"{issue.get('type', 'error')}: {issue['message']}")
            log_id = _dict(record.get("log")).get("id")
            if log_id is None:
                continue
            lines = self._invoke_build("logs", f"buildId={build_id}", f"logId={log_id}")
            value = _dict(lines).get("value") if isinstance(lines, dict) else lines
            if isinstance(value, list):
                out += [str(line) for line in value[-CHECK_LOG_LINES:]]
        return "\n".join(out)

    def merge(
        self, pr: PullRequest, head_sha: str, subject: str, strategy: str | None = None
    ) -> str | None:
        """Complete `pr` if its head is still `head_sha`.

        ``az repos pr update`` has no equivalent of ``--match-head-commit``; the
        head is compared with ``lastMergeSourceCommit`` just before completing, so
        a push between that check and the update is not caught.
        """
        chosen = self._strategy(strategy)
        current = self.status(pr)
        if current.state == MERGED:
            return current.merge_sha
        if current.state == CLOSED:
            raise MergeFailed("merge_failed", f"PR {pr.id} is abandoned")
        if current.mergeability == CONFLICT:
            raise MergeFailed("conflict", f"PR {pr.id} has conflicts with {pr.base}")
        if current.head_sha != head_sha:
            raise MergeFailed("merge_failed", f"PR {pr.id} moved: {current.head_sha} != {head_sha}")
        try:
            resp = self.az.json(
                "repos",
                "pr",
                "update",
                "--id",
                pr.id,
                *self._org(),
                "--status",
                "completed",
                "--squash",
                "true" if chosen == "squash" else "false",
                "--merge-commit-message",
                subject,
                "--delete-source-branch",
                "false",
                *self._tail(),
            )
        except AzError as exc:
            if exc.code == "az_not_logged_in":
                raise
            detail = exc.stderr.strip() or exc.message
            try:
                after: PrStatus | None = self._status_once(pr)
            except ProviderError:
                after = None
            if after is not None and after.state == OPEN and after.mergeability == CONFLICT:
                raise MergeFailed("conflict", f"PR {pr.id} has conflicts: {detail}") from exc
            raise MergeFailed("merge_failed", detail) from exc
        if isinstance(resp, dict) and str(resp.get("status", "")).lower() == "completed":
            return _commit(resp, "lastMergeCommit")
        return self._await_completion(pr)

    def _await_completion(self, pr: PullRequest) -> str | None:
        for attempt in range(1, self.attempts + 1):
            status = self._status_once(pr)
            if status.state == MERGED:
                return status.merge_sha
            if status.state == CLOSED:
                raise MergeFailed("merge_failed", f"PR {pr.id} was abandoned while completing")
            if status.mergeability == CONFLICT:
                raise MergeFailed("conflict", f"PR {pr.id} has conflicts with {pr.base}")
            if attempt < self.attempts:
                self.sleep(self.delay)
        raise MergeFailed("merge_failed", f"PR {pr.id} not completed after {self.attempts} checks")

    def update_pr(self, pr: PullRequest, body: str) -> None:
        self._ready()
        args = ["repos", "pr", "update", "--id", pr.id, *self._org()]
        lines = _description_lines(body)
        if lines:
            args += ["--description", *lines]
        self.az.json(*args, *self._tail())

    def comment(self, pr: PullRequest, body: str) -> None:
        self._ready()
        payload = {
            "comments": [{"parentCommentId": 0, "content": body, "commentType": 1}],
            "status": 1,
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as handle:
            json.dump(payload, handle)
            path = handle.name
        try:
            self.az.run(
                "devops",
                "invoke",
                "--area",
                "git",
                "--resource",
                "pullRequestThreads",
                "--route-parameters",
                f"project={self.azure.project}",
                f"repositoryId={self.azure.repository}",
                f"pullRequestId={pr.id}",
                "--http-method",
                "POST",
                "--in-file",
                path,
                "--api-version",
                API_VERSION,
                *self._org(),
                "--output",
                "json",
                "--only-show-errors",
            )
        finally:
            Path(path).unlink(missing_ok=True)
