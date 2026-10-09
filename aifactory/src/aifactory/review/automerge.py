"""Auto-merge: approve and merge a task's PR right after its run, without the operator.

With ``auto_merge: true`` inherited by the task (task, step or project
``index.md``), ``run_chain`` calls ``try_auto_merge`` after the run. It merges
the PR the same way ``factory task approve`` does (``approve_task``: the
``status: done`` commit, push, merge, ``task_prs`` merged, base caught up,
worktrees removed), with ``merged_by == "auto-merge"``, but only when all holds:

1. the run ended ``succeeded`` and opened its PR;
2. the run's workflow has a review phase (a role step returning ``ReviewOutput``);
   a workflow without review is never merged automatically;
3. the last review of the run approved, with no blocking and no unmet item;
4. the PR is open and merges cleanly (``mergeable``) into base;
5. its checks on the hosting are not red (pending or no checks do not block).

An open PR whose mergeability is still unknown is polled again until the hosting
reports a definitive result. Each bounded provider polling batch is followed by
a pause; an unknown result alone never ends the auto-merge attempt.

A PR in conflict is resolved once: ``resolve_and_merge`` runs ``factory task resolve`` with the
workflow ``resolve-reviewed`` (the whole suite, and a review when the agent resolved source
conflicts) and merges the PR when that run succeeded and conditions 4 and 5 hold.

The first condition that does not hold (or a failed merge) is the reason: the
PR stays open for ``factory task approve`` and ``task_prs.auto_merge_error``
holds ``"<code>: <reason>"``. ``try_auto_merge`` never raises for that.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from time import sleep

from aifactory.backlog import Task
from aifactory.config import ConfigError, RunConfig, load_run_config
from aifactory.engine.data_types import ReviewOutput
from aifactory.providers import (
    CHECKS_FAILING,
    CONFLICT,
    MERGEABLE,
    OPEN,
    UNKNOWN,
    ChecksStatus,
    GitProvider,
    ProviderError,
    PrStatus,
    get_provider,
)
from aifactory.review import flow as review_flow
from aifactory.review.errors import ReviewError
from aifactory.review.flow import ApproveResult, approve_task
from aifactory.run import gitops
from aifactory.run.errors import TaskRunError
from aifactory.run.queue import auto_merge_enabled
from aifactory.run.resolve import RESOLVE_REVIEWED_WORKFLOW
from aifactory.run.store import (
    MERGED_BY_AUTO,
    STARTED_AUTO_RESOLVE,
    SUCCEEDED,
    TaskPrRow,
    TaskRunStore,
)
from aifactory.run.task import TaskRunResult, named_workflow
from aifactory.workflow import CodeRunner, RoleStep, Workflow, WorkflowRun, walk

AUTO_MERGE = MERGED_BY_AUTO
AUTO_MERGE_POLL_DELAY = 2.0
__all__ = [
    "AUTO_MERGE",
    "AutoMergeResult",
    "auto_merge_enabled",
    "hosting_blocker",
    "last_review",
    "resolve_and_merge",
    "review_blocker",
    "try_auto_merge",
    "workflow_has_review",
]


@dataclass
class AutoMergeResult:
    """What auto-merge did with a run's PR; ``code``/``reason`` say why it did not merge."""

    merged: bool
    code: str | None
    reason: str | None
    pr_url: str | None
    merge_sha: str | None = None
    approve: ApproveResult | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "merged": self.merged,
            "code": self.code,
            "reason": self.reason,
            "pr_url": self.pr_url,
            "merge_sha": self.merge_sha,
            "merged_by": AUTO_MERGE if self.merged else None,
        }

    @classmethod
    def from_json(cls, data: object) -> AutoMergeResult | None:
        """The result as ``to_json`` wrote it (a run's envelope); None when unreadable."""
        if not isinstance(data, dict) or not isinstance(data.get("merged"), bool):
            return None

        def text(key: str) -> str | None:
            value = data.get(key)
            return value if isinstance(value, str) else None

        return cls(
            merged=data["merged"],
            code=text("code"),
            reason=text("reason"),
            pr_url=text("pr_url"),
            merge_sha=text("merge_sha"),
        )


def workflow_has_review(workflow: Workflow) -> bool:
    """The workflow has a role step whose output is a ``ReviewOutput``."""
    return any(
        isinstance(step, RoleStep)
        and isinstance(step.role.output_type, type)
        and issubclass(step.role.output_type, ReviewOutput)
        for step in walk(workflow.steps)
    )


def last_review(wf: WorkflowRun | None) -> ReviewOutput | None:
    """The newest review envelope of the run."""
    if wf is None:
        return None
    envelopes = [e for _, e in wf.history] if wf.history else list(wf.envelopes.values())
    for envelope in reversed(envelopes):
        if isinstance(envelope, ReviewOutput):
            return envelope
    return None


def review_blocker(review: ReviewOutput | None) -> tuple[str, str] | None:
    """``(code, reason)`` when the review does not allow a merge; ``None`` when it does."""
    if review is None:
        return "no_review", "no review ran in this run"
    if not review.approved:
        detail = f": {'; '.join(review.blocking)}" if review.blocking else ""
        return "review_rejected", f"the last review did not approve{detail}"
    if review.blocking:
        return (
            "review_blocking",
            f"{len(review.blocking)} blocking item(s): {'; '.join(review.blocking)}",
        )
    unmet = [f.requirement for f in review.findings if not f.met]
    if unmet:
        return "review_unmet", f"{len(unmet)} unmet requirement(s): {'; '.join(unmet)}"
    return None


def hosting_blocker(status: PrStatus, checks: ChecksStatus) -> tuple[str, str] | None:
    """``(code, reason)`` when the hosting state does not allow a merge; ``None`` when it does."""
    if status.state != OPEN:
        return "pr_not_open", f"the PR is {status.state}"
    if status.mergeability == CONFLICT:
        return "conflict", "the PR does not merge into base; run `factory task resolve`"
    if status.mergeability != MERGEABLE:
        return "mergeability_unknown", f"the hosting reports mergeability {status.mergeability}"
    if checks.state == CHECKS_FAILING:
        names = ", ".join(checks.failing) or "?"
        return "checks_failing", f"red checks: {names}"
    return None


def try_auto_merge(
    repo: Path, result: TaskRunResult, task: Task, *, provider: GitProvider | None = None
) -> AutoMergeResult:
    """Approve and merge the PR of `result` when every condition holds; never raises for that."""
    pr = result.pr
    if result.run.state != SUCCEEDED:
        return AutoMergeResult(
            False,
            "run_not_succeeded",
            f"the run ended {result.run.state}",
            pr.url if pr else None,
        )
    if pr is None:
        return AutoMergeResult(False, "no_pr", result.pr_error or "the run opened no PR", None)
    outcome = _check_and_merge(repo, result, task, provider)
    if not outcome.merged:
        _record_error(result.trace_db, pr.branch, f"{outcome.code}: {outcome.reason}")
    return outcome


def resolve_and_merge(
    repo: Path,
    result: TaskRunResult,
    task: Task,
    *,
    provider: GitProvider | None = None,
    code: CodeRunner | None = None,
    merge_lock: Callable[[], AbstractContextManager[object]] | None = None,
) -> tuple[TaskRunResult | None, AutoMergeResult]:
    """Resolve the conflicting PR of `result` once (``resolve-reviewed``), then merge it.

    The resolve run tests the whole suite and has a resolution the agent wrote reviewed; its
    ``accept`` requires both, so only a succeeded run is merged, under conditions 4 and 5.
    ``merge_lock`` (a chain member: the store's merge lock) is held for the merge only,
    never during the resolve run.
    Returns the resolve run (None when it could not start) and what auto-merge did.
    """
    pr = result.pr
    assert pr is not None

    def failed(
        code_: str, reason: str, run: TaskRunResult | None
    ) -> tuple[TaskRunResult | None, AutoMergeResult]:
        _record_error(result.trace_db, pr.branch, f"{code_}: {reason}")
        return run, AutoMergeResult(False, code_, reason, pr.url)

    try:
        resolved = review_flow.resolve_task(
            repo,
            task.id,
            provider=provider,
            code=code,
            workflow=RESOLVE_REVIEWED_WORKFLOW,
            started_by=STARTED_AUTO_RESOLVE,
        )
    except (ReviewError, TaskRunError) as exc:
        return failed("resolve_failed", f"{exc.code}: {exc.message}", None)
    if resolved.run.state != SUCCEEDED:
        detail = f": {resolved.run.error}" if resolved.run.error else ""
        reason = f"auto-resolve run {resolved.run.run_id} ended {resolved.run.state}{detail}"
        return failed("resolve_failed", reason, resolved)
    try:
        main = gitops.main_root(repo)
        rc = load_run_config(main)
    except (TaskRunError, ConfigError) as exc:
        return failed("workflow_unavailable", str(exc), resolved)
    with merge_lock() if merge_lock is not None else contextlib.nullcontext():
        outcome = _hosting_and_merge(repo, resolved.pr or pr, task, provider, rc, main)
    if outcome.merged:
        _record_error(result.trace_db, pr.branch, None)
    else:
        _record_error(
            result.trace_db, pr.branch, f"{outcome.code}: {outcome.reason} (after auto-resolve)"
        )
    return resolved, outcome


def _check_and_merge(
    repo: Path, result: TaskRunResult, task: Task, provider: GitProvider | None
) -> AutoMergeResult:
    pr = result.pr
    assert pr is not None
    url = pr.url

    def blocked(code: str, reason: str) -> AutoMergeResult:
        return AutoMergeResult(False, code, reason, url)

    try:
        main = gitops.main_root(repo)
        rc = load_run_config(main)
        name = result.run.workflow or ""
        workflow = named_workflow(name, rc.config, task.id)
    except (TaskRunError, ConfigError) as exc:
        return blocked("workflow_unavailable", str(exc))
    if not workflow_has_review(workflow):
        return blocked(
            "no_review_phase",
            f"workflow {workflow.name} has no review phase; auto-merge never merges it",
        )
    review = review_blocker(last_review(result.workflow_run))
    if review is not None:
        return blocked(*review)
    return _hosting_and_merge(repo, pr, task, provider, rc, main)


def _hosting_and_merge(
    repo: Path,
    pr: TaskPrRow,
    task: Task,
    provider: GitProvider | None,
    rc: RunConfig,
    main: Path,
) -> AutoMergeResult:
    """Conditions 4 and 5 on the hosting, then the merge (``approve_task``)."""
    url = pr.url

    def blocked(code: str, reason: str) -> AutoMergeResult:
        return AutoMergeResult(False, code, reason, url)

    try:
        if provider is None:
            provider = get_provider(rc.config.settings, main)
        status = provider.status(pr.request())
        while status.state == OPEN and status.mergeability == UNKNOWN:
            sleep(AUTO_MERGE_POLL_DELAY)
            status = provider.status(pr.request())
    except ProviderError as exc:
        return blocked("status_unavailable", f"{exc.code}: {exc.message}")
    try:
        checks = provider.checks(pr.request())
    except ProviderError as exc:
        return blocked("checks_unavailable", f"{exc.code}: {exc.message}")
    hosting = hosting_blocker(status, checks)
    if hosting is not None:
        return blocked(*hosting)
    try:
        approved = approve_task(repo, task.id, provider=provider, merged_by=AUTO_MERGE)
    except ReviewError as exc:
        return blocked(exc.code, exc.message)
    except (OSError, RuntimeError) as exc:
        return blocked("merge_failed", str(exc))
    return AutoMergeResult(True, None, None, url, approved.merge_sha, approved)


def _record_error(trace_db: Path, branch: str, error: str | None) -> None:
    try:
        store = TaskRunStore(trace_db)
    except (TaskRunError, OSError):  # pragma: no cover - the run just wrote this DB
        return
    try:
        store.update_pr(branch, auto_merge_error=error)
    finally:
        store.close()
