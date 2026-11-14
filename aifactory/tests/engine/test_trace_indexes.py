"""History indexes upgrade existing databases without changing rows or page ordering."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aifactory.engine.tracer import Tracer
from aifactory.run.store import TaskRunStore


@pytest.mark.parametrize("table", ["events", "phases", "envelopes", "gate_results"])
def test_history_index_upgrades_existing_rows(tmp_path: Path, table: str) -> None:
    db = tmp_path / "trace.db"
    tracer = Tracer(db, tmp_path / "events.jsonl")
    tracer.conn.execute(f"DROP INDEX {table}_run")
    tracer.conn.executemany(
        f"INSERT INTO {table}(adw_id) VALUES (?)", [(f"run-{i % 5}",) for i in range(100)]
    )
    query = (
        f"SELECT rowid, adw_id FROM {table} WHERE adw_id = ? AND rowid > ? ORDER BY rowid LIMIT ?"
    )
    args = ("run-2", 20, 7)
    before = tracer.conn.execute(query, args).fetchall()
    tracer.conn.close()

    for _ in range(2):  # migration and reopening are both idempotent
        tracer = Tracer(db, tmp_path / "events.jsonl")
        try:
            assert tracer.conn.execute(query, args).fetchall() == before
            plan = " ".join(
                row[3] for row in tracer.conn.execute("EXPLAIN QUERY PLAN " + query, args)
            )
            assert f"USING INDEX {table}_run" in plan or f"USING COVERING INDEX {table}_run" in plan
            assert "TEMP B-TREE" not in plan
            assert tracer.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 100
        finally:
            tracer.conn.close()


def test_run_page_index_follows_legacy_column_migration(tmp_path: Path) -> None:
    db = tmp_path / "trace.db"
    store = TaskRunStore(db)
    store.conn.execute("DROP INDEX task_runs_page")
    store.conn.execute("ALTER TABLE task_runs DROP COLUMN archived")
    store.conn.executemany(
        "INSERT INTO task_runs(run_id, task_id, branch, worktree, base, base_sha, "
        "state, started_at) "
        "VALUES (?, 'task', 'branch', 'worktree', 'main', 'sha', 'succeeded', ?)",
        [(f"run-{i}", f"2026-01-{i // 5 + 1:02d}") for i in range(30)],
    )
    store.close()
    query = (
        "SELECT run_id FROM task_runs WHERE archived = 0 "
        "ORDER BY started_at DESC, rowid DESC LIMIT 7 OFFSET 3"
    )
    for _ in range(2):
        store = TaskRunStore(db)
        try:
            assert [r[0] for r in store.conn.execute(query)] == [
                f"run-{i}" for i in range(26, 19, -1)
            ]
            plan = " ".join(row[3] for row in store.conn.execute("EXPLAIN QUERY PLAN " + query))
            assert "USING INDEX task_runs_page" in plan
            assert "TEMP B-TREE" not in plan
            assert store.conn.execute("SELECT COUNT(*) FROM task_runs").fetchone()[0] == 30
        finally:
            store.close()
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
