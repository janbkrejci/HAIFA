"""Process reservations before claim, with no external services."""

import os
from pathlib import Path

import pytest

from aifactory.run import store as store_module
from aifactory.run.queue import Slots
from aifactory.run.store import TaskRunRow, TaskRunStore


def test_operations_preserve_capacity_and_are_reaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TaskRunStore(tmp_path / "trace.db")
    try:
        first = store.start_operation("T01", "run", os.getpid())
        second = store.start_operation("T01", "retry", os.getpid())
        assert Slots.of(store).running == ()
        store.claim(
            TaskRunRow(
                run_id="r1",
                task_id="T01",
                branch="b",
                worktree="",
                base="main",
                base_sha="a",
                head_sha=None,
                state="running",
                started_at="2026-01-01",
                pid=os.getpid(),
            )
        )
        assert [r.run_id for r in store.live_runs()] == ["r1"]
        assert Slots.of(store).running == ("T01",)
        store.finish_operation(first)
        assert [r.run_id for r in store.live_operations()] == [second]
        monkeypatch.setattr(store_module, "_alive", lambda pid: False)
        assert store.live_operations() == []
        assert store.conn.execute("SELECT COUNT(*) FROM task_operations").fetchone()[0] == 0
    finally:
        store.close()


def test_member_failure_before_claim_removes_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from run_repo import make_run_repo

    from aifactory.run import members
    from aifactory.run.errors import TaskRunError

    repo = make_run_repo(tmp_path / "repo")

    class Process:
        pid = os.getpid()
        returncode = 3

        def poll(self) -> int:
            return self.returncode

    monkeypatch.setattr(
        members, "subprocess", SimpleNamespace(Popen=lambda *args, **kwargs: Process(), DEVNULL=-3)
    )

    def before_claim(*args: object) -> None:
        store = TaskRunStore(repo / ".factory" / "trace.db")
        try:
            assert [(r.task_id, r.workflow) for r in store.live_operations()] == [("T01", "run")]
        finally:
            store.close()

    monkeypatch.setattr(members, "new_row", before_claim)
    with pytest.raises(TaskRunError, match="without a readable envelope"):
        members.ProcessRunner(repo).start("T01")
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        assert store.live_operations() == []
    finally:
        store.close()


def test_publish_keeps_previous_error_while_operation_is_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from aifactory.review import flow
    from aifactory.review.errors import ReviewError

    store = TaskRunStore(tmp_path / "trace.db")
    store.claim(
        TaskRunRow(
            run_id="r1",
            task_id="T01",
            branch="b",
            worktree="",
            base="main",
            base_sha="a",
            head_sha=None,
            state="running",
            started_at="2026-01-01",
            pid=os.getpid(),
        )
    )
    store.finish("r1", "succeeded", None, None)
    store.set_pr_error("r1", "previous push failed")
    monkeypatch.setattr(flow, "_context", lambda *args: SimpleNamespace(store=store))

    def publishing(*args: object) -> None:
        assert [(r.task_id, r.workflow) for r in store.live_operations()] == [("T01", "publish")]
        row = store.get("r1")
        assert row is not None and row.pr_error == "previous push failed"
        raise RuntimeError("publication interrupted")

    monkeypatch.setattr(flow, "_publish", publishing)
    with pytest.raises(ReviewError, match="publication interrupted"):
        flow.publish_task(tmp_path, "T01")
    reopened = TaskRunStore(tmp_path / "trace.db")
    try:
        assert reopened.live_operations() == []
        row = reopened.get("r1")
        assert row is not None and row.pr_error == "previous push failed"
    finally:
        reopened.close()
