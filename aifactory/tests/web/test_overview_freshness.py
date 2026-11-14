"""Slow polls, remote process ownership and fresh cached dashboard reads."""

from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path
from typing import Any

import pytest
from overview_fixture import T_RUN, make_installed_repo, make_overview_repo

from aifactory import database
from aifactory.backlog.edit import load_for_edit
from aifactory.repo_settings import RepositorySettings
from aifactory.run.store import TaskRunStore
from aifactory.web import overview
from aifactory.web.overview import Overview
from aifactory.web.registry import Registry, RepoEntry


def entry(root: Path) -> RepoEntry:
    return RepoEntry(id="test", name="test", path=str(root), added_at="2026-01-01")


@pytest.mark.parametrize("broken", [False, True])
def test_completed_timeout_is_delivered_once_then_recomputed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, broken: bool
) -> None:
    ov = Overview(Registry(tmp_path / "home"), timeout=0.01)
    release = threading.Event()
    calls = 0

    def slow(_: RepoEntry) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        release.wait(5)
        if broken:
            raise ValueError("broken repo")
        return {"state": "ok"}

    monkeypatch.setattr(ov, "repo", slow)

    async def check() -> None:
        assert (await ov._bounded(entry(tmp_path)))["state"] == "timeout"
        # Another poll while the computation is running shares the same worker.
        assert (await ov._bounded(entry(tmp_path)))["state"] == "timeout"
        assert calls == 1
        release.set()
        future = next(iter(ov._inflight.values()))
        try:
            await asyncio.wrap_future(future)
        except ValueError:
            pass
        result = await ov._bounded(entry(tmp_path))
        assert result["state"] == ("error" if broken else "ok")
        if not broken:
            assert result["stale"] is True
        assert calls == 1
        await ov._bounded(entry(tmp_path))
        assert calls == 2

    try:
        asyncio.run(check())
    finally:
        release.set()
        ov._pool.shutdown(wait=True)


def test_foreign_pid_is_never_probed_and_still_holds_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TaskRunStore(tmp_path / "trace.db")
    try:
        store.conn.execute("CREATE TABLE haifa_owners(id TEXT PRIMARY KEY, machine TEXT)")
        store.conn.execute(
            "INSERT INTO task_runs(run_id,task_id,state,started_at,pid,branch,worktree,"
            "base,base_sha) "
            "VALUES ('foreign','T1','running','2026-01-01',99999999,'b','/tmp/worktree','main','a')"
        )
        store.conn.execute("INSERT INTO haifa_owners VALUES ('foreign','other-machine')")
        monkeypatch.setattr(overview, "_process", lambda _: pytest.fail("foreign PID probed"))
        trace = overview._read_trace(store.conn)
        assert len(overview._active_runs(trace)) == 1
        assert overview._row_process(trace.runs[0]) == "unknown"
        assert not trace.runs[0]["owned_here"]
        store.conn.execute("UPDATE haifa_owners SET machine = ?", (database.MACHINE,))
        monkeypatch.setattr(overview, "_process", lambda _: "ended")
        assert overview._active_runs(overview._read_trace(store.conn)) == []
    finally:
        store.close()


def test_task_cache_observes_edit_add_delete_and_container_inheritance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_installed_repo(tmp_path / "repo")
    ov = Overview(Registry(tmp_path / "home"))
    original = load_for_edit
    calls = 0

    def counted(path: Path) -> Any:
        nonlocal calls
        calls += 1
        return original(path)

    monkeypatch.setattr(overview, "load_for_edit", counted)
    first = ov.repo(entry(root))
    assert ov.repo(entry(root))["tasks"] == first["tasks"]
    assert calls == 1
    task = next(root.glob(f"backlog/**/{T_RUN}-*.md"))
    task.write_text(task.read_text().replace("status: todo", "status: cancelled"))
    assert ov.repo(entry(root))["tasks"]["cancelled"] == first["tasks"]["cancelled"] + 1
    added = task.with_name("M01-S01-T99-new.md")
    added.write_text("---\nid: M01-S01-T99\ntitle: New\nstatus: todo\n---\n")
    assert sum(ov.repo(entry(root))["tasks"].values()) == sum(first["tasks"].values()) + 1
    added.unlink()
    assert sum(ov.repo(entry(root))["tasks"].values()) == sum(first["tasks"].values())
    container = root / "backlog/M01-core/index.md"
    container.write_text(container.read_text().replace("workflow: plan-commit", "workflow: ''"))
    ov.repo(entry(root))
    assert calls == 5


def test_history_reduction_keeps_old_running_and_latest_failed(tmp_path: Path) -> None:
    store = TaskRunStore(tmp_path / "trace.db")
    try:
        store.conn.executemany(
            "INSERT INTO task_runs(run_id,task_id,state,started_at,ended_at,branch,worktree,"
            "base,base_sha) "
            "VALUES (?,?,?,?,?,'b','/tmp/worktree','main','a')",
            [(f"r{i}", "T1", "failed", f"2026-{i:05}", "2026-12-01") for i in range(100)],
        )
        store.conn.execute("UPDATE task_runs SET state='running' WHERE run_id='r0'")
        trace = overview._read_trace(store.conn)
        assert [row["run_id"] for row in trace.runs] == ["r99", "r0"]
        assert "2026-12-01" in trace.activity
    finally:
        store.close()


def test_overview_uses_one_fresh_merge_policy_snapshot_per_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_overview_repo(tmp_path / "repo", live_pid=os.getpid(), dead_pid=99999999)
    ov = Overview(Registry(tmp_path / "home"))
    original = RepositorySettings.show
    calls = 0
    enabled = False

    def show(settings: RepositorySettings) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        result = original(settings)
        result["auto_merge_policy"]["value"] = enabled
        return result

    monkeypatch.setattr(RepositorySettings, "show", show)
    monkeypatch.setattr(overview, "waits_for_automerge", lambda *a: pytest.fail("per-PR read"))
    monkeypatch.setattr(
        "aifactory.web.backlog.waits_for_automerge", lambda *a: pytest.fail("per-task read")
    )
    first = ov.repo(entry(root))
    assert first["tasks"]["in review"] == len(first["review"]) == 1
    enabled = True
    second = ov.repo(entry(root))
    assert second["tasks"]["awaiting merge"] == len(second["automerge"]) == 1
    assert calls == 2
