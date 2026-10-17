"""The table ``learn_lessons`` in the trace DB: the lessons ``factory learn scan`` proposed
and the ones a person rejected.

A lesson's id is a hash of its normalized rule, so the same rule found again keeps its
id. ``state`` is ``proposed`` or ``rejected``; a scan updates a proposed lesson and never
touches a rejected one. ``complaints`` are the keys of the objections the lesson was made
of (``collect.Objection.key``).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from aifactory import database
from aifactory.backlog import TaskEditError
from aifactory.engine.tracer import BUSY_TIMEOUT
from aifactory.engine.utils import now_iso

PROPOSED, REJECTED = "proposed", "rejected"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS learn_lessons (
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


def normalize(rule: str) -> str:
    return re.sub(r"[\s.!;:]+$", "", " ".join(rule.lower().split()))


def lesson_id(rule: str) -> str:
    return "L" + hashlib.sha1(normalize(rule).encode("utf-8")).hexdigest()[:8]


@dataclass
class StoredLesson:
    lesson_id: str
    rule: str
    target: str
    target_detail: str = ""
    complaints: list[str] = field(default_factory=list)
    runs: list[str] = field(default_factory=list)
    state: str = PROPOSED
    reason: str | None = None


class LessonStore:
    def __init__(self, trace_db: Path) -> None:
        if not database.is_remote(trace_db):
            trace_db.parent.mkdir(parents=True, exist_ok=True)
        self.conn = database.connect(str(trace_db), isolation_level=None, timeout=BUSY_TIMEOUT)
        self.conn.execute(f"PRAGMA busy_timeout={int(BUSY_TIMEOUT * 1000)};")
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def all(self) -> list[StoredLesson]:
        rows = self.conn.execute(
            "SELECT lesson_id, rule, target, target_detail, complaints, runs, state, reason "
            "FROM learn_lessons ORDER BY created_at, lesson_id"
        ).fetchall()
        return [
            StoredLesson(r[0], r[1], r[2], r[3], json.loads(r[4]), json.loads(r[5]), r[6], r[7])
            for r in rows
        ]

    def rejected(self) -> list[StoredLesson]:
        return [lesson for lesson in self.all() if lesson.state == REJECTED]

    def save_proposed(self, lesson: StoredLesson) -> None:
        """Insert or update a proposed lesson; a rejected one stays as it is."""
        now = now_iso()
        self.conn.execute(
            "INSERT INTO learn_lessons (lesson_id, rule, target, target_detail, complaints, "
            "runs, state, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(lesson_id) DO UPDATE SET rule=excluded.rule, target=excluded.target, "
            "target_detail=excluded.target_detail, complaints=excluded.complaints, "
            "runs=excluded.runs, updated_at=excluded.updated_at "
            f"WHERE learn_lessons.state = '{PROPOSED}'",
            (
                lesson.lesson_id,
                lesson.rule,
                lesson.target,
                lesson.target_detail,
                json.dumps(lesson.complaints),
                json.dumps(lesson.runs),
                PROPOSED,
                now,
                now,
            ),
        )

    def reject(self, lesson_id: str, reason: str | None = None) -> StoredLesson:
        """Mark ``lesson_id`` rejected: no later scan offers it again."""
        cur = self.conn.execute(
            "UPDATE learn_lessons SET state=?, reason=?, updated_at=? WHERE lesson_id=?",
            (REJECTED, reason, now_iso(), lesson_id),
        )
        if not cur.rowcount:
            raise TaskEditError(
                "unknown_lesson", f"no lesson {lesson_id}; run 'factory learn scan'"
            )
        return next(lesson for lesson in self.all() if lesson.lesson_id == lesson_id)
