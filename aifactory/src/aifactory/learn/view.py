"""The lessons of a repo for the dashboard: their occurrences and, once adopted, their effect.

Every stored lesson comes with its objections (``sources.resolve_objections``, by the keys
the lesson keeps, so objections of other registered repos count too), the runs they come
from and the repos of the objections (``origin``). An accepted lesson also carries its
task's pull request, looked up in the trace DB of the lesson's repo; once that is merged,
``effect`` counts the runs (and objections) of the lesson before and after the merge. The
grouping is the scan's: a later ``factory learn scan`` adds the objections that repeat an
accepted lesson to it (``scan.repeats_of``). The runs of the lesson's own task (in the
lesson's repo) are left out of the count.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aifactory import database
from aifactory.engine.tracer import BUSY_TIMEOUT
from aifactory.learn.collect import Objection
from aifactory.learn.scan import _snippet, trace_db
from aifactory.learn.store import ACCEPTED, PROPOSED, LessonStore, StoredLesson

_ORDER = {PROPOSED: 0, ACCEPTED: 1}


def _moment(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _prs(db: Path, task_ids: list[str]) -> dict[str, dict[str, Any]]:
    """The pull request of each task: the first merged one, else the newest."""
    if not task_ids or not database.available(db):
        return {}
    conn = database.connect(f"file:{db}?mode=ro", uri=True, timeout=BUSY_TIMEOUT)
    try:
        marks = ", ".join("?" for _ in task_ids)
        rows = conn.execute(
            "SELECT task_id, url, state, COALESCE(merged_at, updated_at) FROM task_prs "
            f"WHERE task_id IN ({marks}) ORDER BY created_at, rowid",
            task_ids,
        ).fetchall()
    except sqlite3.OperationalError:  # no PR recorded yet (table missing)
        return {}
    finally:
        conn.close()
    found: dict[str, dict[str, Any]] = {}
    for task_id, url, state, when in rows:
        current = found.get(str(task_id))
        if current is not None and current["state"] == "merged":
            continue
        found[str(task_id)] = {
            "url": str(url),
            "state": str(state),
            "merged_at": str(when) if state == "merged" else None,
        }
    return found


def _count(objections: list[Objection]) -> dict[str, int]:
    return {"runs": len({(o.repo, o.run_id) for o in objections}), "objections": len(objections)}


def effect(
    lesson: StoredLesson, objections: list[Objection], merged_at: str | None, own: str = ""
) -> dict[str, Any] | None:
    """How often the lesson's mistake came up before and after its PR was merged.

    ``own`` is the registry id of the lesson's repo: only its runs of the lesson's task
    are left out (another repo may have a task of the same id).
    """
    merged = _moment(merged_at)
    if lesson.state != ACCEPTED or merged is None:
        return None
    before: list[Objection] = []
    after: list[Objection] = []
    for o in objections:
        moment = _moment(o.created_at)
        if moment is None or (lesson.task_id and o.task_id == lesson.task_id and o.repo == own):
            continue
        (after if moment >= merged else before).append(o)
    return {"merged_at": merged_at, "before": _count(before), "after": _count(after)}


def _origin(lesson: StoredLesson, objections: list[Objection]) -> list[str]:
    found = list(dict.fromkeys(o.repo for o in objections if o.repo))
    return found or list(lesson.origin)


def lesson_json(
    lesson: StoredLesson,
    objections: list[Objection],
    pr: dict[str, Any] | None,
    own: str = "",
) -> dict[str, Any]:
    runs: dict[tuple[str, str], str] = {}
    for o in objections:
        runs.setdefault((o.repo, o.run_id), o.task_id)
    known = {run for _repo, run in runs}
    for run in lesson.runs:
        if run not in known:
            runs.setdefault((own, run), "")
    return {
        "id": lesson.lesson_id,
        "rule": lesson.rule,
        "target": lesson.target,
        "target_detail": lesson.target_detail,
        "state": lesson.state,
        "reason": lesson.reason,
        "task_id": lesson.task_id,
        "occurrences": len(runs),
        "origin": _origin(lesson, objections),
        "runs": [{"run_id": r, "task_id": t, "repo": repo} for (repo, r), t in runs.items()],
        "complaints": [{**_snippet(o), "repo": o.repo} for o in objections],
        "pr": pr,
        "effect": effect(lesson, objections, pr["merged_at"] if pr else None, own),
    }


def lessons(repo: Path) -> list[dict[str, Any]]:
    """Every lesson of the repo: proposed first (most runs first), then accepted, rejected."""
    db = trace_db(repo)
    if not database.available(db):
        return []
    store = LessonStore(db)
    try:
        stored = store.all()
    finally:
        store.close()
    if not stored:
        return []
    from aifactory.learn.accept import _repo_id
    from aifactory.learn.sources import resolve_objections  # imports aifactory.web

    own = _repo_id(repo)
    prs = _prs(db, [s.task_id for s in stored if s.task_id])
    result = [
        lesson_json(
            s,
            resolve_objections(s.complaints, repo),
            prs.get(s.task_id) if s.task_id else None,
            own,
        )
        for s in stored
    ]
    result.sort(key=lambda item: (_ORDER.get(item["state"], 2), -item["occurrences"]))
    return result
