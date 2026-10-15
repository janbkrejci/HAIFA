"""``start_factory``: the Overview's "Spustit továrnu" with a fake `start`.

The fake claims a `running` row with a live pid in the real trace DB (or claims nothing,
like a launch whose claim was not seen in time), so the selection sees it like a run.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from run_repo import commit_all, make_run_repo, write
from test_parallel_chain import CORE, STEP, T01, T02, T03, T04, _db, no_files, setup_tasks

from aifactory.engine.utils import now_iso
from aifactory.run import TaskRunError, TaskRunRow, TaskRunStore, start_factory


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def _row(task_id: str) -> TaskRunRow:
    return TaskRunRow(
        run_id=f"r-{task_id}",
        task_id=task_id,
        branch=f"factory/{task_id}-1",
        worktree="wt",
        base="main",
        base_sha="0",
        head_sha=None,
        state="running",
        started_at=str(now_iso()),
        pid=os.getpid(),
    )


def claim(repo: Path, task_id: str) -> TaskRunRow:
    row = _row(task_id)
    store = TaskRunStore(_db(repo))
    try:
        store.claim(row)
    finally:
        store.close()
    return row


class FakeStart:
    """Records the started tasks; claims a row unless the task is in `pending`."""

    def __init__(
        self,
        repo: Path,
        *,
        pending: tuple[str, ...] = (),
        refuse: tuple[str, ...] = (),
        claim_rows: bool = True,
    ) -> None:
        self.repo = repo
        self.pending = pending
        self.refuse = refuse
        self.claim_rows = claim_rows
        self.calls: list[str] = []

    def __call__(self, task_id: str) -> TaskRunRow | None:
        self.calls.append(task_id)
        if task_id in self.refuse:
            raise TaskRunError("already_running", f"{task_id} runs elsewhere")
        if task_id in self.pending or not self.claim_rows:
            return None
        return claim(self.repo, task_id)


def test_starts_as_many_as_free_slots_in_queue_order(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/"), (T03, "src/c/")])
    store = TaskRunStore(_db(repo))
    try:
        store.set_queue_order([T03])
    finally:
        store.close()
    start = FakeStart(repo)
    result = start_factory(repo, start, max_parallel=2, pr_files=no_files)
    assert start.calls == [T03, T01]
    assert (result.max_parallel, result.running, result.free_slots) == (2, 0, 2)
    data = result.to_json()
    assert data["started"] == [
        {"task_id": T03, "run_id": f"r-{T03}"},
        {"task_id": T01, "run_id": f"r-{T01}"},
    ]
    assert data["max_parallel_runs"] == 2


def test_excluded_blocked_and_workflowless_tasks_are_skipped(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/")])
    write(
        repo,
        f"{CORE}/{STEP}/{T03}.md",
        f"---\nid: {T03}\ntitle: No workflow\nstatus: todo\nworkflow: null\nwrites: [src/c/]\n"
        "---\n\nDo it.\n",
    )
    write(
        repo,
        f"{CORE}/{STEP}/{T04}.md",
        f"---\nid: {T04}\ntitle: Blocked\nstatus: todo\nwrites: [src/d/]\ndepends_on: [{T02}]\n"
        "---\n\nDo it.\n",
    )
    commit_all(repo, "more tasks")
    store = TaskRunStore(_db(repo))
    try:
        store.set_excluded(T02, True)
    finally:
        store.close()
    start = FakeStart(repo)
    result = start_factory(repo, start, max_parallel=3, pr_files=no_files)
    assert start.calls == [T01]
    reasons = {s.task_id: s.reason for s in result.skipped}
    assert reasons == {T02: "excluded", T03: "no_workflow", T04: "blocked"}


def test_a_live_run_takes_a_slot(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/"), (T03, "src/c/")])
    claim(repo, T01)
    start = FakeStart(repo)
    result = start_factory(repo, start, max_parallel=2, pr_files=no_files)
    assert (result.running, result.free_slots) == (1, 1)
    assert start.calls == [T02]


def test_no_free_slot_starts_nothing(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/")])
    claim(repo, T01)
    start = FakeStart(repo)
    result = start_factory(repo, start, max_parallel=1, pr_files=no_files)
    assert start.calls == []
    assert (result.free_slots, result.started, result.skipped) == (0, [], [])


@pytest.mark.parametrize("pending", [False, True])
def test_overlapping_writes_start_only_the_first(repo: Path, pending: bool) -> None:
    setup_tasks(repo, [(T01, "src/app/"), (T02, "src/app/sub/")])
    start = FakeStart(repo, pending=(T01,) if pending else ())
    result = start_factory(repo, start, max_parallel=3, pr_files=no_files)
    assert start.calls == [T01]
    assert result.to_json()["started"] == [
        {"task_id": T01, "run_id": None if pending else f"r-{T01}"}
    ]
    (skip,) = result.skipped
    assert (skip.task_id, skip.reason, skip.waits_on) == (T02, "writes_overlap", [T01])


def test_a_refused_start_is_cannot_start_and_the_next_one_starts(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/")])
    start = FakeStart(repo, refuse=(T01,))
    result = start_factory(repo, start, max_parallel=1, pr_files=no_files)
    assert start.calls == [T01, T02]
    assert [s.task_id for s in result.started if not isinstance(s, str)] == [T02]
    assert [(s.task_id, s.reason) for s in result.skipped] == [(T01, "cannot_start")]


def test_without_a_trace_db_none_is_created(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/")])
    assert not _db(repo).exists()
    start = FakeStart(repo, claim_rows=False)
    result = start_factory(repo, start, max_parallel=2, pr_files=no_files)
    assert start.calls == [T01, T02]
    assert result.started == [T01, T02]
    assert not _db(repo).exists()
