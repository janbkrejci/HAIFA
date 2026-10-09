"""The kanban's queue preferences in the trace DB (``task_queue``, ``TaskRunStore``)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aifactory.run.store import QueuePrefs, TaskRunStore


def _store(tmp_path: Path) -> TaskRunStore:
    return TaskRunStore(tmp_path / "trace.db")


def test_empty_store_has_no_prefs(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        assert store.queue_prefs() == QueuePrefs()
    finally:
        store.close()


def test_order_is_saved_and_replaced(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.set_queue_order(["B", "A", "C"])
        assert store.queue_prefs().order == ("B", "A", "C")
        store.set_queue_order(["C", "B"])
        assert store.queue_prefs().order == ("C", "B")
        # rows without rank and exclusion are removed
        count = store.conn.execute("SELECT COUNT(*) FROM task_queue").fetchone()[0]
        assert count == 2
    finally:
        store.close()


def test_exclusion_survives_reordering(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.set_queue_order(["A", "B"])
        store.set_excluded("B", True)
        store.set_excluded("X", True)
        store.set_queue_order(["B"])
        prefs = store.queue_prefs()
        assert prefs.order == ("B",)
        assert prefs.excluded == frozenset({"B", "X"})
        store.set_excluded("X", False)
        assert store.queue_prefs().excluded == frozenset({"B"})
        rows = store.conn.execute("SELECT task_id FROM task_queue ORDER BY task_id").fetchall()
        assert [r[0] for r in rows] == ["B"]
    finally:
        store.close()


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.set_queue_order(["A"])
        with pytest.raises(ValueError):
            store.set_queue_order(["B", "B"])
        assert store.queue_prefs().order == ("A",)
    finally:
        store.close()


def test_older_db_gets_the_table(tmp_path: Path) -> None:
    db = tmp_path / "trace.db"
    TaskRunStore(db).close()
    conn = sqlite3.connect(db)
    conn.execute("DROP TABLE task_queue")
    conn.commit()
    conn.close()
    store = TaskRunStore(db)
    try:
        assert store.queue_prefs() == QueuePrefs()
        store.set_excluded("A", True)
        assert store.queue_prefs().excluded == frozenset({"A"})
    finally:
        store.close()
