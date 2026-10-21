"""The kanban's queue preferences in the trace DB (``task_queue``, ``TaskRunStore``)."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

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


def test_queue_front_preserves_other_order_and_exclusions(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.set_queue_order(["A", "B", "C", "D"])
        for task_id in ("B", "X", "Y"):
            store.set_excluded(task_id, True)
        store.queue_front(["X", "B", "N"])
        assert store.queue_prefs().order == ("X", "B", "N", "A", "C", "D")
        assert store.queue_prefs().excluded == frozenset({"B", "X", "Y"})
        store.queue_front([])
        with pytest.raises(ValueError):
            store.queue_front(["N", "N"])
        assert store.queue_prefs().order == ("X", "B", "N", "A", "C", "D")
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


def test_concurrent_queue_front_keeps_both_batches(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_queue_order(["A", "B"])
    barrier = Barrier(2)

    def prepend(ids: list[str]) -> None:
        other = _store(tmp_path)
        try:
            barrier.wait(timeout=10)
            other.queue_front(ids)
        finally:
            other.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(prepend, ["X", "Y"])
            second = pool.submit(prepend, ["N", "M"])
            first.result(timeout=20)
            second.result(timeout=20)
        assert store.queue_prefs().order in (
            ("X", "Y", "N", "M", "A", "B"),
            ("N", "M", "X", "Y", "A", "B"),
        )
    finally:
        store.close()


def test_queue_front_rolls_back_the_whole_batch(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.set_queue_order(["A", "B"])
        store.conn.execute(
            "CREATE TRIGGER reject_front BEFORE INSERT ON task_queue "
            "WHEN NEW.task_id = 'Y' BEGIN SELECT RAISE(ABORT, 'rejected'); END"
        )
        with pytest.raises(sqlite3.IntegrityError, match="rejected"):
            store.queue_front(["X", "Y"])
        assert store.queue_prefs().order == ("A", "B")
    finally:
        store.close()
