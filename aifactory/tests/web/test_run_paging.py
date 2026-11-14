"""Filtered pagination reads only the requested run details; live keeps historical edits."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from trace_fixture import T1, make_trace_db

from aifactory.run.store import TaskRunRow, TaskRunStore
from aifactory.web import create_app, runs
from aifactory.web.live import LiveWatcher


def test_paging_filters_before_hydrating_and_rejects_invalid_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_trace_db(tmp_path / "repo", os.getpid())
    original = runs._summaries
    seen: list[int] = []

    def summaries(
        store: TaskRunStore, rows: list[TaskRunRow], titles: dict[str, str]
    ) -> list[dict[str, Any]]:
        seen.append(len(rows))
        return original(store, rows, titles)

    monkeypatch.setattr(runs, "_summaries", summaries)
    with TestClient(create_app(root), base_url="http://127.0.0.1:4700") as client:
        first = client.get(f"/api/runs?task={T1}&limit=1").json()["data"]
        assert first["total"] == 2
        assert [r["run_id"] for r in first["runs"]] == ["r-fail"]
        second = client.get(f"/api/runs?task={T1}&limit=1&offset=1").json()["data"]
        assert [r["run_id"] for r in second["runs"]] == ["r-ok"]
        assert first["tasks"] == second["tasks"]
        assert seen == [1, 1]
        for query in ("limit=0", "limit=501", "offset=-1"):
            assert client.get(f"/api/runs?{query}").status_code == 400


def test_journal_tracks_old_run_updates_deletes_and_overflow(tmp_path: Path) -> None:
    root = make_trace_db(tmp_path / "repo", os.getpid())
    store = TaskRunStore(root / ".factory/trace.db")
    watcher = LiveWatcher(root)
    try:
        assert watcher.poll() == []
        queries: list[str] = []
        assert watcher._conn is not None
        watcher._conn.set_trace_callback(queries.append)
        store.conn.execute("UPDATE task_runs SET state = 'running' WHERE run_id = 'r-ok'")
        [event] = watcher.poll()
        assert event.kind == "trace"
        assert "r-ok" in event.data["run_ids"]
        assert event.data["runs_changed"] is True
        assert not any(query.endswith("FROM task_runs") for query in queries)
        store.conn.execute("DELETE FROM task_runs WHERE run_id = 'r-ok'")
        [event] = watcher.poll()
        assert event.data["task_ids"] == [T1]
        assert "r-ok" in event.data["run_ids"]
        with store.conn:
            for _ in range(1001):
                store.conn.execute("UPDATE task_runs SET note = 'edited' WHERE run_id = 'r-fail'")
        assert store.conn.execute("SELECT COUNT(*) FROM trace_changes").fetchone()[0] == 1000
        assert watcher.poll()[0].kind == "resync"
        assert watcher.poll() == []
    finally:
        watcher.close()
        store.close()
