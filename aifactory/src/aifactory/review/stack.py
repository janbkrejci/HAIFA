"""Stacked PRs after their dependency is merged (``stacked_prs``, see ``run/stack.py``).

``approve_task`` calls ``restack_dependents`` once a PR is merged. Every open PR whose
run forked from the merged branch is rebased onto base without the dependency's commits
(``resolve_task``: the ``resolve`` workflow, an agent only on a conflict). A task with
``auto_merge`` whose auto-merge waited for the stack (``auto_merge_error`` empty) is then
merged like after its run, which restacks its own dependents in turn. Nothing here
raises: problems come back as warnings and stay in ``task_prs.auto_merge_error``.
"""

from __future__ import annotations

from pathlib import Path

from aifactory.backlog import Task, load_backlog
from aifactory.config import ConfigError, load_run_config
from aifactory.providers import GitProvider
from aifactory.review.errors import ReviewError
from aifactory.run import gitops
from aifactory.run.errors import TaskRunError
from aifactory.run.queue import auto_merge_enabled
from aifactory.run.resolve import RESOLVE_WORKFLOW
from aifactory.run.stack import open_stack, stacked_on
from aifactory.run.store import STARTED_AUTO_RESOLVE, SUCCEEDED, TaskPrRow, TaskRunStore
from aifactory.workflow import CodeRunner


def _dependents(store: TaskRunStore, merged_branch: str) -> list[TaskPrRow]:
    """Open PRs stacked on `merged_branch` and on no other open PR."""
    return [
        pr
        for pr in store.open_prs()
        if stacked_on(store, pr.branch) == merged_branch and open_stack(store, pr.branch) is None
    ]


def restack_dependents(
    repo: Path,
    trace_db: Path,
    merged_branch: str,
    *,
    provider: GitProvider | None = None,
    code: CodeRunner | None = None,
) -> list[str]:
    """Rebase the PRs stacked on `merged_branch` onto base and auto-merge them; warnings."""
    # Local imports: review.flow and review.automerge import this module's callers.
    from aifactory.review.automerge import _hosting_and_merge, _record_error
    from aifactory.review.flow import resolve_task

    store = TaskRunStore(trace_db)
    try:
        dependents = _dependents(store, merged_branch)
    finally:
        store.close()
    warnings: list[str] = []
    for pr in dependents:
        try:
            resolved = resolve_task(
                repo,
                pr.task_id,
                provider=provider,
                code=code,
                workflow=RESOLVE_WORKFLOW,
                started_by=STARTED_AUTO_RESOLVE,
            )
        except (ReviewError, TaskRunError) as exc:
            reason = f"restack_failed: {exc.code}: {exc.message}"
            _record_error(trace_db, pr.branch, reason)
            warnings.append(f"{pr.task_id}: {reason}")
            continue
        if resolved.run.state != SUCCEEDED:
            reason = f"restack_failed: run {resolved.run.run_id} ended {resolved.run.state}"
            _record_error(trace_db, pr.branch, reason)
            warnings.append(f"{pr.task_id}: {reason}")
            continue
        if pr.auto_merge_error is not None:
            continue  # its auto-merge failed for another reason: the operator approves it
        try:
            main = gitops.main_root(repo)
            rc = load_run_config(main)
        except (TaskRunError, ConfigError) as exc:
            warnings.append(f"{pr.task_id}: not auto-merged: {exc}")
            continue
        task = load_backlog(main, rc.config.settings).by_id.get(pr.task_id)
        if not isinstance(task, Task) or not auto_merge_enabled(task):
            continue
        outcome = _hosting_and_merge(repo, resolved.pr or pr, task, provider, rc, main, code)
        if not outcome.merged:
            reason = f"{outcome.code}: {outcome.reason} (after restack)"
            _record_error(trace_db, pr.branch, reason)
            warnings.append(f"{pr.task_id}: not auto-merged: {reason}")
    return warnings
