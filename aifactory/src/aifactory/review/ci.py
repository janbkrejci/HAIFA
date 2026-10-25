"""The CI gate of approve and auto-merge: wait for the merge head's checks, repair red ones.

``approve_task`` (the operator's ``factory task approve``, the dashboard and auto-merge)
pushes the ``status: done`` commit, then ``head_checks`` waits for the CI checks of
exactly that head. No checks (``none``, also after ``AUTO_MERGE_CHECKS_APPEAR`` on a
hosting that reports checks) or green checks: the PR is merged. Red checks: the
names and logs of the red checks (``check_logs``) go as the note into a ``ci-fix`` run
on the PR's own branch (``run_ci_fix``, ``started_by`` ``auto-ci-fix``), which pushes
its repair to the same PR; then the checks are waited for again. At most
``CI_FIX_ROUNDS`` repair runs per approve; checks still red after them, or still
running after ``AUTO_MERGE_CHECKS_TIMEOUT``, leave the PR open. A repair run whose agent
needs paths outside the task's ``writes`` (``writes_needed``) leaves it open with the
code ``writes_needed`` and the paths in ``auto_merge_error``; ``factory task approve
--allow-writes`` adds them to the task's writes in base and approves again.
"""

from __future__ import annotations

from pathlib import Path
from time import monotonic, sleep

from aifactory.config import load_run_config
from aifactory.providers import (
    CHECKS_FAILING,
    CHECKS_NONE,
    CHECKS_PENDING,
    ChecksStatus,
    GitProvider,
    PullRequest,
    get_provider,
)
from aifactory.run import gitops
from aifactory.run.resolve import CI_FIX_WORKFLOW
from aifactory.run.store import STARTED_AUTO_CI_FIX
from aifactory.run.task import TaskRunResult, run_task
from aifactory.workflow import CodeRunner

AUTO_MERGE_CHECKS_DELAY = 15.0
"""Seconds between two reads of the PR's checks while they run."""
AUTO_MERGE_CHECKS_TIMEOUT = 30 * 60.0
"""How long approve waits for running checks before it gives up (`checks_pending`)."""
AUTO_MERGE_CHECKS_APPEAR = 90.0
"""How long a pushed head on a hosting with checks may show none before "no checks" counts."""
CI_FIX_ROUNDS = 2
"""The most ``ci-fix`` repair runs one approve (or auto-merge) starts."""
CI_REPORT_LIMIT = 16_000
"""The longest note (in characters) a repair run gets; logs are cut from their start."""
_clock = monotonic
"""The clock of the checks wait (a module attribute, so tests can move it)."""

_INSTRUCTION = (
    "Fix the cause in the code this task owns so these checks pass; do not disable or "
    "skip checks; do not edit CI configuration unless the failure is in it and it is in "
    "your allowed paths. When the fix needs a path outside your allowed paths, report "
    "status fail with fail_kind needs_writes and the paths in needs_writes."
)


def settled_checks(provider: GitProvider, request: PullRequest) -> ChecksStatus:
    """The PR's checks once none runs, or as they are when the wait is over."""
    start = _clock()
    checks = provider.checks(request)
    while True:
        waited = _clock() - start
        running = checks.state == CHECKS_PENDING and waited < AUTO_MERGE_CHECKS_TIMEOUT
        appearing = (
            checks.state == CHECKS_NONE
            and provider.reports_checks
            and waited < AUTO_MERGE_CHECKS_APPEAR
        )
        if not (running or appearing):
            return checks
        sleep(AUTO_MERGE_CHECKS_DELAY)
        checks = provider.checks(request)


def head_checks(provider: GitProvider, request: PullRequest, head: str) -> ChecksStatus:
    """The settled checks of the PR once the hosting shows `head` as its head.

    A hosting that reports checks may still show the previous head (and its checks)
    right after a push; it gets ``AUTO_MERGE_CHECKS_APPEAR`` to show `head`. A hosting
    without head info, or one that still shows another head after that, gets its
    checks read as they are: the merge itself is bound to `head`
    (``--match-head-commit``), so it never merges a head these checks did not see.
    """
    if provider.reports_checks:
        start = _clock()
        while True:
            seen = provider.status(request).head_sha
            if seen is None or seen == head or _clock() - start >= AUTO_MERGE_CHECKS_APPEAR:
                break
            sleep(AUTO_MERGE_CHECKS_DELAY)
    return settled_checks(provider, request)


def checks_reason(checks: ChecksStatus, rounds: int = 0) -> tuple[str, str] | None:
    """``(code, reason)`` when the checks do not allow a merge; ``None`` when they do."""
    after = f" after {rounds} ci-fix run(s)" if rounds else ""
    if checks.state == CHECKS_FAILING:
        names = ", ".join(checks.failing) or "?"
        return "checks_failing", f"red checks: {names}{after}"
    if checks.state == CHECKS_PENDING:
        minutes = round(AUTO_MERGE_CHECKS_TIMEOUT / 60)
        return "checks_pending", f"checks still running after {minutes} min{after}"
    return None


def ci_report(failing: tuple[str, ...], logs: dict[str, str]) -> str:
    """The note of a repair run: the red checks, their logs and what to do."""
    head = ["## CI checks failed on this PR", ""]
    head += [f"- {name}" for name in failing] or ["- ?"]
    tail = ["", _INSTRUCTION]
    fixed = len("\n".join([*head, *tail])) + 2
    sections: list[tuple[str, str]] = [(n, logs[n]) for n in failing if logs.get(n)]
    budget = max(0, CI_REPORT_LIMIT - fixed)
    parts: list[str] = []
    if sections:
        frame = sum(len(f"\n### {name}\n```\n\n```") for name, _ in sections)
        share = max(0, (budget - frame) // len(sections))
        for name, log in sections:
            text = log if len(log) <= share else "…" + log[len(log) - share + 1 :]
            parts += ["", f"### {name}", "```", text, "```"]
    return "\n".join([*head, *parts, *tail])[:CI_REPORT_LIMIT]


def billing_block(logs: dict[str, str]) -> str | None:
    """A hosting refusal that a code repair cannot resolve."""
    marker = (
        "check annotation: The job was not started because recent account payments "
        "have failed or your spending limit needs to be increased"
    )
    for name, log in logs.items():
        for line in log.splitlines():
            if line.startswith(marker):
                return f"{name}: {line.removeprefix('check annotation: ')}"
    return None


def run_ci_fix(
    repo: Path,
    task_id: str,
    branch: str,
    report: str,
    provider: GitProvider,
    code: CodeRunner | None,
) -> TaskRunResult:
    """A ``ci-fix`` run of `task_id` on `branch` with `report` as the note.

    The caller frees the branch first (no worktree may hold it). Returns the
    ``TaskRunResult``; raises ``TaskRunError`` when the run cannot start.
    """
    return run_task(
        repo,
        task_id,
        note=report,
        force=True,
        code=code,
        provider=provider,
        branch=branch,
        workflow_name=CI_FIX_WORKFLOW,
        started_by=STARTED_AUTO_CI_FIX,
    )


def provider_reports_checks(repo: Path) -> bool:
    """Whether the repo's hosting reports CI checks (approve may then wait long)."""
    try:
        main = gitops.main_root(repo)
        return get_provider(load_run_config(main).config.settings, main).reports_checks
    except Exception:  # noqa: BLE001 - the approve itself reports a broken setup
        return False
