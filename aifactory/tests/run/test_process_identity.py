"""Persist OS process identities, migrate legacy traces, and fail safely on unknowns."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import psutil
import pytest

from aifactory import oscompat
from aifactory.engine.tracer import Tracer
from aifactory.run.store import FAILED, TaskRunRow, TaskRunStore


def row() -> TaskRunRow:
    return TaskRunRow(
        "run",
        "task",
        "branch",
        "/worktree",
        "main",
        "abc",
        None,
        "running",
        "2026-11-14T12:00:00Z",
        pid=os.getpid(),
    )


def test_claim_retry_and_trace_record_creation_time(tmp_path: Path) -> None:
    path = tmp_path / "trace.db"
    store = TaskRunStore(path)
    tracer = Tracer(path, tmp_path / "events.jsonl")
    try:
        created_at = psutil.Process().create_time()
        store.claim(row())
        claimed = store.get("run")
        assert claimed is not None and claimed.pid_created_at == created_at
        tracer.process_start("run", "agent", "builder", os.getpid(), "python")
        assert store.process_identities("run") == {os.getpid(): created_at}
        store.finish("run", FAILED, None, "failed")
        store.conn.execute("UPDATE task_runs SET pid_created_at = 1")
        retried = store.reclaim("run", os.getpid(), {"from": "test"})
        assert retried.pid_created_at == created_at
    finally:
        tracer.conn.close()
        store.close()


def test_legacy_process_rows_migrate_without_inventing_identity(tmp_path: Path) -> None:
    path = tmp_path / "trace.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE processes(id INTEGER PRIMARY KEY, adw_id TEXT, kind TEXT, "
            "name TEXT, pid INTEGER, command TEXT, started_at TEXT, ended_at TEXT)"
        )
        conn.execute(
            "INSERT INTO processes VALUES(1, 'run', 'agent', 'builder', ?, 'python', '', NULL)",
            (os.getpid(),),
        )
    tracer = Tracer(path, tmp_path / "events.jsonl")
    store = TaskRunStore(path)
    try:
        assert store.process_identities("run") == {os.getpid(): None}
    finally:
        tracer.conn.close()
        store.close()


def test_unknown_identity_does_not_reap_running_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TaskRunStore(tmp_path / "trace.db")
    try:
        store.claim(row())
        monkeypatch.setattr(oscompat, "process_matches", lambda pid, created_at: None)
        assert store.running("task") is not None
    finally:
        store.close()


def test_access_denied_identity_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(pid: int) -> psutil.Process:
        raise psutil.AccessDenied(pid)

    monkeypatch.setattr(psutil, "Process", denied)
    assert oscompat.process_created_at(123) is None
    assert oscompat.process_matches(123, 1.0) is None
    assert oscompat.process_matches(123, None) is None
