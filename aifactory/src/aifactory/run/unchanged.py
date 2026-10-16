"""A succeeded run that left nothing to publish: the task is done without a pull request.

When the agents found the work already in ``base`` (another task did it), the branch
has no commit beyond the run's ``base_sha`` and the hosting refuses a PR for it. The
task then gets ``status: done`` and a line in ``## Běhy`` committed to ``base``, so it
does not stay ``todo`` with a PR error and the tasks that wait for it can start.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from aifactory.backlog import TaskEditError, commit_backlog, complete_task
from aifactory.run import gitops
from aifactory.run.store import TaskRunRow, TaskRunStore


def unchanged(row: TaskRunRow) -> bool:
    """Whether the run's branch has no commit beyond the commit the run started from."""
    worktree = Path(row.worktree)
    if not worktree.is_dir() or not row.base_sha:
        return False
    count = gitops.git(worktree, "rev-list", "--count", f"{row.base_sha}..HEAD").strip()
    return count == "0"


def unchanged_entry(row: TaskRunRow, cost: float) -> str:
    date = datetime.date.today().isoformat()
    workflow = row.workflow or "?"
    return f"- {date} · workflow {workflow} · bez změn, běh {row.run_id} · náklady ${cost:.2f}"


def finish_unchanged(
    main: Path, store: TaskRunStore, row: TaskRunRow
) -> tuple[str | None, list[str]]:
    """Mark the task of `row` done in ``base``: (the error when it was not, warnings)."""
    # Local import: aifactory.review imports aifactory.run.
    from aifactory.review.prbody import branch_cost

    cost, _ = branch_cost(store.db_path, [row.run_id])
    try:
        with store.serialized():
            complete_task(main, row.task_id, unchanged_entry(row, cost))
            done = commit_backlog(main, f"{row.task_id}: hotovo bez změn (běh {row.run_id})")
    except TaskEditError as exc:
        return f"task not marked done: {exc.code}: {exc.message}", []
    return None, list(done.warnings)
