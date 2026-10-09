"""A busy trace DB: writers wait instead of failing, and git work holds no DB lock.

Another process holds the trace DB's write lock longer than SQLite's old 5 s busy
timeout; a run's writes (store and Tracer) wait for it and succeed once it lets go.
``serialized()`` (the lock around git work) is a lock file, not a DB transaction,
so DB writes go on while it is held.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from aifactory.engine.data_types import EventRecord
from aifactory.engine.tracer import Tracer
from aifactory.run import TaskRunError, TaskRunStore
from aifactory.run.store import RUNNING, SUCCEEDED, TaskRunRow, is_db_busy

HOLD_SECONDS = 6.5  # longer than the old 5 s busy_timeout

_HOLDER = """
import sqlite3, sys, time
conn = sqlite3.connect(sys.argv[1], isolation_level=None)
conn.execute("BEGIN IMMEDIATE")
conn.execute("UPDATE task_runs SET note = 'held' WHERE 0")
print("locked", flush=True)
time.sleep(float(sys.argv[2]))
conn.execute("COMMIT")
"""


def hold_write_lock(db: Path, seconds: float) -> subprocess.Popen[str]:
    """Start a process that holds the write lock of `db` for `seconds`; return once it holds it."""
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(db), str(seconds)],
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "locked"
    return proc


def _row(run_id: str, task_id: str) -> TaskRunRow:
    return TaskRunRow(
        run_id=run_id,
        task_id=task_id,
        branch=f"factory/{task_id}-1",
        worktree=f"/tmp/wt/{run_id}",
        base="main",
        base_sha="0" * 40,
        head_sha=None,
        state=RUNNING,
        started_at="2026-01-01T10:00:00+00:00",
        pid=os.getpid(),
    )


@pytest.fixture(name="db")
def db_fixture(tmp_path: Path) -> Iterator[Path]:
    db = tmp_path / "trace.db"
    store = TaskRunStore(db)
    Tracer(db, tmp_path / "events.jsonl").conn.close()
    store.close()
    yield db


def test_run_writes_wait_for_a_lock_held_longer_than_5s(db: Path, tmp_path: Path) -> None:
    holder = hold_write_lock(db, HOLD_SECONDS)
    store = TaskRunStore(db)
    tracer = Tracer(db, tmp_path / "events.jsonl")
    try:
        start = time.monotonic()
        store.claim(_row("r-1", "T1"))
        tracer.session_start("r-1", "tester")
        tracer.event(EventRecord(adw_id="r-1", type="phase", name="build"))
        store.finish("r-1", SUCCEEDED, "a" * 40, None)
        waited = time.monotonic() - start
    finally:
        tracer.conn.close()
        store.close()
        holder.wait(timeout=30)
    assert holder.returncode == 0
    assert waited > 5.0  # it really waited past the old timeout
    check = TaskRunStore(db)
    try:
        row = check.get("r-1")
        assert row is not None and row.state == SUCCEEDED
        events = check.conn.execute("SELECT name FROM events WHERE adw_id = 'r-1'").fetchall()
        assert events == [("build",)]
    finally:
        check.close()


def test_serialized_holds_no_db_write_lock(db: Path) -> None:
    """Git work runs under ``serialized()``; other processes write the DB meanwhile."""
    store = TaskRunStore(db)
    other = sqlite3.connect(str(db), isolation_level=None, timeout=0)
    try:
        with store.serialized():
            other.execute("BEGIN IMMEDIATE")  # would raise "database is locked" at once
            other.execute("COMMIT")
    finally:
        other.close()
        store.close()


def test_serialized_is_exclusive_across_threads_and_reentrant(db: Path) -> None:
    store = TaskRunStore(db)
    order: list[str] = []
    try:
        with store.serialized():
            with store.serialized():  # claim inside a serialized block must not deadlock
                store.claim(_row("r-1", "T1"))

            def other() -> None:
                second = TaskRunStore(db)
                try:
                    with second.serialized():
                        order.append("other")
                finally:
                    second.close()

            thread = threading.Thread(target=other)
            thread.start()
            time.sleep(0.3)
            order.append("first")
        thread.join(timeout=10)
    finally:
        store.close()
    assert order == ["first", "other"]


def test_a_lock_that_outlasts_the_wait_is_db_busy(
    db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("aifactory.run.store.BUSY_TIMEOUT", 0.2)
    holder = hold_write_lock(db, 2.0)
    try:
        store = TaskRunStore(db)
        try:
            with pytest.raises(sqlite3.OperationalError) as caught:
                store.claim(_row("r-1", "T1"))
        finally:
            store.close()
    finally:
        holder.wait(timeout=30)
    assert is_db_busy(caught.value)
    assert is_db_busy(TaskRunError("trace_db_locked", "x"))
    assert not is_db_busy(TaskRunError("already_running", "x"))
