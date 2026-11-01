"""``LessonStore`` on a trace DB of an older HAIFA: ``learn_lessons`` without ``task_id``
or ``origin``."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aifactory.learn.store import ACCEPTED, PROPOSED, LessonStore, StoredLesson

_OLD_SCHEMA = """
CREATE TABLE learn_lessons (
  lesson_id TEXT PRIMARY KEY,
  rule TEXT NOT NULL,
  target TEXT NOT NULL,
  target_detail TEXT NOT NULL DEFAULT '',
  complaints TEXT NOT NULL DEFAULT '[]',
  runs TEXT NOT NULL DEFAULT '[]',
  state TEXT NOT NULL,
  reason TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


def test_old_table_gets_task_id_column(tmp_path: Path) -> None:
    db = tmp_path / "trace.db"
    conn = sqlite3.connect(db)
    conn.executescript(_OLD_SCHEMA)
    conn.execute(
        "INSERT INTO learn_lessons (lesson_id, rule, target, complaints, runs, state, "
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        ("L00000001", "Test it.", "AGENTS.md", '["e#0"]', '["run-a", "run-b"]', PROPOSED, "t", "t"),
    )
    conn.commit()
    conn.close()

    store = LessonStore(db)
    try:
        [lesson] = store.all()
        assert (lesson.lesson_id, lesson.state, lesson.task_id) == ("L00000001", PROPOSED, None)
        assert lesson.origin == []
        assert lesson.runs == ["run-a", "run-b"]
        accepted = store.accept("L00000001", "T")
        assert (accepted.state, accepted.task_id) == (ACCEPTED, "T")
    finally:
        store.close()

    store = LessonStore(db)  # opening a migrated table again changes nothing
    try:
        assert [(s.state, s.task_id) for s in store.all()] == [(ACCEPTED, "T")]
    finally:
        store.close()


_TASK_ID_SCHEMA = _OLD_SCHEMA.replace("  reason TEXT,\n", "  reason TEXT,\n  task_id TEXT,\n")


@pytest.mark.parametrize("schema", [_OLD_SCHEMA, _TASK_ID_SCHEMA])
def test_old_table_gets_origin_column(tmp_path: Path, schema: str) -> None:
    db = tmp_path / "trace.db"
    conn = sqlite3.connect(db)
    conn.executescript(schema)
    conn.execute(
        "INSERT INTO learn_lessons (lesson_id, rule, target, state, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?)",
        ("L00000001", "Test it.", "AGENTS.md", PROPOSED, "t", "t"),
    )
    conn.commit()
    conn.close()

    store = LessonStore(db)
    try:
        [old] = store.all()
        assert old.origin == []
        store.save_proposed(
            StoredLesson("L00000002", "Lint it.", "seed", "builder", origin=["alpha", "beta"])
        )
        # a proposed lesson found again takes the repos of its new objections
        store.save_proposed(StoredLesson("L00000001", "Test it.", "AGENTS.md", origin=["gamma"]))
    finally:
        store.close()

    store = LessonStore(db)  # opening a migrated table again changes nothing
    try:
        assert sorted((s.lesson_id, s.origin) for s in store.all()) == [
            ("L00000001", ["gamma"]),
            ("L00000002", ["alpha", "beta"]),
        ]
    finally:
        store.close()
