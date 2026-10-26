"""A run that leaves nothing to publish: the task is done without a pull request.

When the agents found the work already in ``base`` (another task did it), the branch
has no commit beyond the run's ``base_sha`` and the hosting refuses a PR for it. The
task then gets ``status: done`` and a line in ``## Běhy`` committed to ``base``, so it
does not stay ``todo`` with a PR error and the tasks that wait for it can start. A
builder that reports ``already_done`` ends the workflow at once; its evidence (the
commits or files where the change is) goes into that line.

A run that failed with ``nothing_to_do`` (the task asks only for a change of the
backlog) is marked done by the operator: ``finish_nothing_to_do`` (dashboard „Hotovo“,
``POST /api/runs/{id}/done``) writes the same line with the agent's reason. Error codes
(``TaskRunError.code``): ``unknown_run``, ``invalid_config``, ``already_running``,
``not_nothing_to_do``; errors of the edit and the commit are ``TaskEditError``.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from pathlib import Path

from aifactory import failure
from aifactory.backlog import TaskEditError, commit_backlog, complete_task
from aifactory.backlog.commit import BacklogCommit
from aifactory.config import ConfigError, load_run_config
from aifactory.run import gitops
from aifactory.run.errors import TaskRunError
from aifactory.run.store import TaskRunRow, TaskRunStore, already_running

COMPLETION_ERROR_PREFIX = "task not marked done: "


def unchanged(row: TaskRunRow) -> bool:
    """Whether the run's branch has no commit beyond the commit the run started from."""
    worktree = Path(row.worktree)
    if not worktree.is_dir() or not row.base_sha:
        return False
    count = gitops.git(worktree, "rev-list", "--count", f"{row.base_sha}..HEAD").strip()
    return count == "0"


def only_spec_changes(row: TaskRunRow, spec: str) -> bool:
    """No implementation diff, including uncommitted and untracked files."""
    worktree = Path(row.worktree)
    if not worktree.is_dir() or not row.base_sha:
        return False
    tracked = gitops.git(worktree, "diff", "--name-only", "-z", row.base_sha)
    untracked = gitops.git(worktree, "ls-files", "--others", "--exclude-standard", "-z")
    files = {name for name in (tracked + "\0" + untracked).split("\0") if name}
    return not (files - {spec})


def _one_line(text: str, limit: int = 300) -> str:
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


def unchanged_entry(
    row: TaskRunRow, cost: float, evidence: Sequence[str] = (), reason: str = ""
) -> str:
    """The ``## Běhy`` line: ``bez změn``, then the evidence or the agent's reason."""
    date = datetime.date.today().isoformat()
    workflow = row.workflow or "?"
    parts = [f"- {date} · workflow {workflow} · bez změn, běh {row.run_id}"]
    if evidence:
        parts.append(f"už hotovo: {_one_line(', '.join(evidence))}")
    if reason.strip():
        parts.append(f"důvod: {_one_line(reason)}")
    parts.append(f"náklady ${cost:.2f}")
    return " · ".join(parts)


def _complete(
    main: Path, store: TaskRunStore, row: TaskRunRow, evidence: Sequence[str], reason: str
) -> BacklogCommit:
    # Local import: aifactory.review imports aifactory.run.
    from aifactory.review.prbody import branch_cost

    cost, _ = branch_cost(store.db_path, [row.run_id])
    with store.serialized():
        complete_task(main, row.task_id, unchanged_entry(row, cost, evidence, reason))
        return commit_backlog(main, f"{row.task_id}: hotovo bez změn (běh {row.run_id})")


def finish_unchanged(
    main: Path,
    store: TaskRunStore,
    row: TaskRunRow,
    evidence: Sequence[str] = (),
    reason: str = "",
) -> tuple[str | None, list[str]]:
    """Mark the task of `row` done in ``base``: (the error when it was not, warnings)."""
    try:
        done = _complete(main, store, row, evidence, reason)
    except TaskEditError as exc:
        return f"{COMPLETION_ERROR_PREFIX}{exc.code}: {exc.message}", []
    if done.pr is not None and not done.merged:
        return (
            f"{COMPLETION_ERROR_PREFIX}backlog PR awaits merge: {done.pr['url']}",
            list(done.warnings),
        )
    return None, list(done.warnings)


def finish_nothing_to_do(repo: Path, run_id: str) -> tuple[TaskRunRow, BacklogCommit]:
    """Mark the task of the ``nothing_to_do`` run `run_id` done in ``base`` without changes."""
    main = gitops.main_root(repo)
    try:
        rc = load_run_config(main)
    except ConfigError as exc:
        raise TaskRunError("invalid_config", str(exc)) from exc
    store = TaskRunStore(rc.local.trace_db_path(main))
    try:
        row = store.get(run_id)
        if row is None:
            raise TaskRunError("unknown_run", f"no run {run_id}")
        busy = store.running(row.task_id)
        if busy is not None:
            raise already_running(busy)
        if row.shown_failure_kind != failure.NOTHING_TO_DO:
            raise TaskRunError(
                "not_nothing_to_do",
                f"run {run_id} of task {row.task_id} is {row.state} "
                f"({row.shown_failure_kind or 'no failure'}), not {failure.NOTHING_TO_DO}; "
                "only a run whose agent had nothing to do marks its task done",
            )
        detail = row.failure_detail_dict() or {}
        agent = str(detail.get("agent") or "agent")
        summary = str(detail.get("summary") or "")
        reason = f"{agent}: {summary}" if summary else agent
        commit = _complete(main, store, row, (), reason)
    finally:
        store.close()
    return row, commit
