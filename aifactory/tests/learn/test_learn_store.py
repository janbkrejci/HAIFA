"""``LessonStore`` on a trace DB of an older HAIFA: ``learn_lessons`` without ``task_id``."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from aifactory.learn.store import ACCEPTED, PROPOSED, LessonStore

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
