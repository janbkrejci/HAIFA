"""Read task runs and their trace for the dashboard's Runs screen.

A run is a row of ``task_runs``; its ``run_id`` is the ``adw_id`` of the engine's
trace tables (``sessions``, ``phases``, ``events``, ``envelopes``,
``gate_results``, ``agent_sessions``). Only the archive functions at the end write
(``task_runs.archived`` and deleting archived runs); a repository without a trace DB
gets empty results (the DB is not created). A trace table
that does not exist yet reads as empty.

``phase_prompts`` also reads the run's session directory (``<data_dir>/sessions/<run_id>``
from the run config, not next to the trace DB): the prompts a phase sent, never a path
outside that directory, each file capped at ``MAX_PROMPT_BYTES``.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from aifactory.engine.quality import TEST_SLOT_EVENT
from aifactory.run.errors import TaskRunError
from aifactory.run.store import TaskRunRow, TaskRunStore
from aifactory.run.task import existing_store, session_dir_of

# ``paused`` filters the running runs that wait at a phase boundary (``pause`` = paused)
RUN_STATES = ("running", "paused", "succeeded", "failed", "aborted", "stopped")
DEFAULT_EVENTS_LIMIT = 500
MAX_EVENTS_LIMIT = 1000

JsonDict = dict[str, Any]


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _rows(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...]) -> list[JsonDict]:
    cursor = conn.execute(sql, args)
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]


def _parse_json(text: object) -> Any:
    if not isinstance(text, str) or not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.astimezone()


def _duration(started: str | None, ended: str | None) -> float | None:
    start = _time(started)
    if start is None:
        return None
    end = _time(ended) if ended else datetime.now(start.tzinfo)
    if end is None:
        return None
    return max(0.0, round((end - start).total_seconds(), 3))


def _placeholders(values: list[str]) -> str:
    return ", ".join("?" for _ in values)


def _sessions(conn: sqlite3.Connection, ids: list[str]) -> dict[str, JsonDict]:
    if not ids or not _has_table(conn, "sessions"):
        return {}
    rows = _rows(
        conn,
        "SELECT adw_id, adw_name, request, status, engineer, started_at, ended_at, "
        f"total_tokens, total_cost FROM sessions WHERE adw_id IN ({_placeholders(ids)})",
        tuple(ids),
    )
    return {str(r["adw_id"]): r for r in rows}


def _logged_request(conn: sqlite3.Connection, run_id: str) -> str | None:
    """The whole request the run's latest request (engineer) phase logged as ``input``."""
    if not _has_table(conn, "events") or not _has_table(conn, "phases"):
        return None
    rows = conn.execute(
        "SELECT e.payload_json FROM events e JOIN phases p ON p.phase_id = e.phase_id "
        "WHERE e.adw_id = ? AND e.type = 'log' AND p.kind = 'engineer' "
        "ORDER BY e.rowid DESC",
        (run_id,),
    ).fetchall()
    for (payload_json,) in rows:
        payload = _parse_json(payload_json)
        if isinstance(payload, dict) and payload.get("input") is not None:
            return str(payload["input"])
    return None


def _with_full_request(
    conn: sqlite3.Connection, run_id: str, session: JsonDict | None
) -> JsonDict | None:
    """The session with its whole request.

    An older trace kept only the first 500 characters in ``sessions.request``; the
    whole request is the ``input`` the request phase logged, so that wins when it is
    longer than the stored one.
    """
    if session is None:
        return None
    logged = _logged_request(conn, run_id)
    stored = session.get("request")
    if logged is not None and len(logged) > len(stored or ""):
        return {**session, "request": logged}
    return session


def _slot_waits(conn: sqlite3.Connection, ids: list[str]) -> dict[str, JsonDict]:
    """Phase id -> its test slot wait (``ahead``, ``slots``) while the latest
    ``test_slot`` event of the phase says it is waiting (see ``engine.slots``)."""
    if not ids or not _has_table(conn, "events"):
        return {}
    rows = _rows(
        conn,
        "SELECT phase_id, payload_json FROM events "
        f"WHERE adw_id IN ({_placeholders(ids)}) AND type = 'log' AND name = ? ORDER BY rowid",
        (*ids, TEST_SLOT_EVENT),
    )
    latest: dict[str, Any] = {}
    for r in rows:
        latest[str(r["phase_id"])] = _parse_json(r["payload_json"])
    out: dict[str, JsonDict] = {}
    for phase_id, payload in latest.items():
        if isinstance(payload, dict) and payload.get("state") == "waiting":
            out[phase_id] = {"ahead": payload.get("ahead"), "slots": payload.get("slots")}
    return out


def _slot_wait(phase: JsonDict, waits: dict[str, JsonDict]) -> JsonDict | None:
    """The phase's slot wait, only while the phase is still running."""
    if phase.get("status") != "running":
        return None
    return waits.get(str(phase.get("phase_id")))


def _phase_dots(conn: sqlite3.Connection, ids: list[str]) -> dict[str, list[JsonDict]]:
    if not ids or not _has_table(conn, "phases"):
        return {}
    rows = _rows(
        conn,
        "SELECT adw_id, phase_id, seq, name, status FROM phases "
        f"WHERE adw_id IN ({_placeholders(ids)}) ORDER BY seq, rowid",
        tuple(ids),
    )
    waits = _slot_waits(conn, ids) if any(r["status"] == "running" for r in rows) else {}
    out: dict[str, list[JsonDict]] = {}
    for r in rows:
        out.setdefault(str(r["adw_id"]), []).append(
            {
                "seq": r["seq"],
                "name": r["name"],
                "status": r["status"],
                "slot_wait": _slot_wait(r, waits),
            }
        )
    return out


def _task_titles(repo: Path) -> tuple[dict[str, str], list[str]]:
    from aifactory.backlog import TaskEditError, iter_tasks, load_for_edit
    from aifactory.config import ConfigError

    try:
        backlog = load_for_edit(repo)
    except (ConfigError, TaskEditError, OSError, ValueError) as exc:
        return {}, [f"task titles are not available: {exc}"]
    return {t.id: t.title for t in iter_tasks(backlog)}, []


def _summary(
    store: TaskRunStore,
    row: TaskRunRow,
    session: JsonDict | None,
    phases: list[JsonDict],
    titles: dict[str, str],
) -> JsonDict:
    pr = store.pr_for_branch(row.branch)
    return {
        "run_id": row.run_id,
        "task_id": row.task_id,
        "task_title": titles.get(row.task_id),
        "workflow": row.workflow,
        "state": row.state,
        "branch": row.branch,
        "started_at": row.started_at,
        "ended_at": row.ended_at,
        "duration_s": _duration(row.started_at, row.ended_at),
        "tokens": int((session or {}).get("total_tokens") or 0),
        "cost": float((session or {}).get("total_cost") or 0.0),
        "error": row.error,
        "note": row.note,
        "archived": bool(row.archived),
        "started_by": row.started_by,
        "pause": row.pause if row.state == "running" else None,
        # why a succeeded run has no PR; the dashboard offers `task publish` for it
        "pr_error": row.pr_error if pr is None else None,
        "pr": None
        if pr is None
        else {
            "url": pr.url,
            "pr_id": pr.pr_id,
            "state": pr.state,
            "merged_by": pr.merged_by,
            "auto_merge_error": pr.auto_merge_error,
        },
        "phases": phases,
    }


def _summaries(
    store: TaskRunStore, rows: list[TaskRunRow], titles: dict[str, str]
) -> list[JsonDict]:
    ids = [r.run_id for r in rows]
    sessions = _sessions(store.conn, ids)
    dots = _phase_dots(store.conn, ids)
    return [
        _summary(store, r, sessions.get(r.run_id), dots.get(r.run_id, []), titles) for r in rows
    ]


def _totals(summaries: list[JsonDict]) -> JsonDict:
    per_task: dict[str, JsonDict] = {}
    for s in summaries:
        entry = per_task.setdefault(
            s["task_id"],
            {
                "task_id": s["task_id"],
                "task_title": s["task_title"],
                "cost": 0.0,
                "tokens": 0,
                "runs": 0,
            },
        )
        entry["cost"] += s["cost"]
        entry["tokens"] += s["tokens"]
        entry["runs"] += 1
    tasks = [per_task[k] for k in sorted(per_task)]
    for t in tasks:
        t["cost"] = round(t["cost"], 6)
    return {
        "backlog": {
            "cost": round(sum(s["cost"] for s in summaries), 6),
            "tokens": sum(s["tokens"] for s in summaries),
            "runs": len(summaries),
        },
        "tasks": tasks,
    }


def _empty_list() -> JsonDict:
    return {"runs": [], "tasks": []}


def _empty_totals() -> JsonDict:
    return {"backlog": {"cost": 0.0, "tokens": 0, "runs": 0}, "tasks": []}


def list_runs(
    repo: Path, *, state: str | None = None, task: str | None = None, archived: bool = False
) -> tuple[JsonDict, list[str]]:
    """Runs newest first, filtered by ``state`` and ``task`` (cost totals: ``run_totals``).

    ``archived`` picks the archived runs instead of the active (not archived) ones.
    """
    if state and state not in RUN_STATES:
        raise TaskRunError(
            "invalid_status", f"invalid run state '{state}', allowed: {', '.join(RUN_STATES)}"
        )
    store = existing_store(repo)
    if store is None:
        return _empty_list(), []
    try:
        rows = store.all_runs()
        titles, warnings = _task_titles(repo) if rows else ({}, [])
        summaries = _summaries(store, rows, titles)
    finally:
        store.close()
    shown = [
        s
        for s in summaries
        if s["archived"] == archived
        and (not state or s["state"] == state or (state == "paused" and s["pause"] == state))
        and (not task or s["task_id"] == task)
    ]
    data = {"runs": shown, "tasks": sorted({s["task_id"] for s in summaries})}
    return data, warnings


def run_totals(repo: Path) -> tuple[JsonDict, list[str]]:
    """Cost totals over every run (archived too): per task and for the whole backlog.

    Asked for separately: the Runs page loads them only when its costs section is opened.
    """
    store = existing_store(repo)
    if store is None:
        return _empty_totals(), []
    try:
        rows = store.all_runs()
        titles, warnings = _task_titles(repo) if rows else ({}, [])
        summaries = _summaries(store, rows, titles)
    finally:
        store.close()
    return _totals(summaries), warnings


def _open_run(repo: Path, run_id: str) -> tuple[TaskRunStore, TaskRunRow]:
    store = existing_store(repo)
    if store is None:
        raise TaskRunError("unknown_run", f"no run {run_id}: there is no trace database")
    row = store.get(run_id)
    if row is not None and row.state == "running":
        store.for_task(row.task_id)  # a dead running row becomes aborted
        row = store.get(run_id)
    if row is None:
        store.close()
        raise TaskRunError("unknown_run", f"no run {run_id}")
    return store, row


def run_summary(repo: Path, run_id: str) -> JsonDict:
    """One run as in the list (``unknown_run`` when there is none)."""
    store, row = _open_run(repo, run_id)
    try:
        titles, _ = _task_titles(repo)
        return _summaries(store, [row], titles)[0]
    finally:
        store.close()


def publish_run(repo: Path, run_id: str) -> tuple[JsonDict, list[str]]:
    """``factory task publish`` for the task of `run_id` (its last succeeded run).

    ``{run, pr, pr_error}``: ``run`` as in the list; a push or PR that failed again is
    ``pr_error`` (HTTP 200, the request itself did its job).
    """
    from aifactory.review import publish_task

    store, row = _open_run(repo, run_id)
    store.close()
    result = publish_task(repo, row.task_id, run_id=run_id)
    return (
        {
            "run": run_summary(repo, run_id),
            "pr": result.pr.to_json() if result.pr is not None else None,
            "pr_error": result.pr_error,
        },
        list(result.warnings),
    )


def _agent_sessions(conn: sqlite3.Connection, run_id: str) -> list[JsonDict]:
    if not _has_table(conn, "agent_sessions"):
        return []
    optional = [
        c
        for c in ("color", "context_tokens", "context_window")
        if _has_column(conn, "agent_sessions", c)
    ]
    cols = ", ".join(["agent", "coding_agent", "model", *optional, "session_id"])
    return _rows(
        conn,
        f"SELECT {cols}, created_at, last_used_at FROM agent_sessions "
        "WHERE adw_id = ? ORDER BY created_at, rowid",
        (run_id,),
    )


def _agent_events(
    conn: sqlite3.Connection, run_id: str, phase_ids: list[str] | None = None
) -> list[JsonDict]:
    """The run's agent start/end events; only of ``phase_ids`` when given."""
    if not _has_table(conn, "events") or phase_ids == []:
        return []
    where = ""
    args: tuple[Any, ...] = (run_id,)
    if phase_ids is not None:
        where = f" AND phase_id IN ({_placeholders(phase_ids)})"
        args = (run_id, *phase_ids)
    return _rows(
        conn,
        "SELECT phase_id, type, name, payload_json, tokens FROM events "
        f"WHERE adw_id = ? AND type IN ('agent_start', 'agent_end'){where} ORDER BY rowid",
        args,
    )


def _add_usage(total: JsonDict | None, usage: Any) -> JsonDict | None:
    if not isinstance(usage, dict):
        return total
    merged: JsonDict = dict(total or {})
    for key, value in usage.items():
        if isinstance(value, int | float) and not isinstance(value, bool):
            merged[key] = merged.get(key, 0) + value
        else:
            merged.setdefault(key, value)
    return merged


def _phases(
    conn: sqlite3.Connection,
    run_id: str,
    agents: list[JsonDict],
    agent_events: list[JsonDict],
    where: str = "",
    args: tuple[Any, ...] = (),
) -> list[JsonDict]:
    """The run's phases (narrowed by the extra SQL ``where`` and its ``args``)."""
    if not _has_table(conn, "phases"):
        return []
    rows = _rows(
        conn,
        "SELECT rowid, phase_id, adw_id, seq, name, kind, owner, description, status, attempt, "
        f"retries, error, started_at, ended_at FROM phases WHERE adw_id = ?{where} "
        "ORDER BY seq, rowid",
        (run_id, *args),
    )
    by_agent = {str(a["agent"]): a for a in agents}
    waits = _slot_waits(conn, [run_id]) if any(r["status"] == "running" for r in rows) else {}
    for phase in rows:
        harness: str | None = None
        model: str | None = None
        tokens = 0
        cost = 0.0
        usage: JsonDict | None = None
        for event in agent_events:
            if event["phase_id"] != phase["phase_id"]:
                continue
            payload = _parse_json(event["payload_json"])
            payload = payload if isinstance(payload, dict) else {}
            if event["type"] == "agent_start":
                harness = harness or payload.get("coding_agent")
                model = model or payload.get("model")
            else:
                tokens += int(event["tokens"] or 0)
                raw_cost = payload.get("cost")
                if isinstance(raw_cost, int | float):
                    cost += float(raw_cost)
                usage = _add_usage(usage, payload.get("usage"))
        if phase["kind"] != "code" and (harness is None or model is None):
            fallback = by_agent.get(str(phase["owner"]))
            if fallback is not None:
                harness = harness or fallback.get("coding_agent")
                model = model or fallback.get("model")
        if phase["kind"] == "code":
            harness, model = None, None
        phase.update(
            harness=harness,
            model=model,
            tokens=tokens,
            cost=round(cost, 6),
            usage=usage,
            slot_wait=_slot_wait(phase, waits),
            duration_s=_duration(phase["started_at"], phase["ended_at"])
            if phase["started_at"] and phase["ended_at"]
            else None,
        )
    return rows


def _usage(agent_events: list[JsonDict]) -> JsonDict:
    read = 0
    written = 0
    for event in agent_events:
        if event["type"] != "agent_end":
            continue
        payload = _parse_json(event["payload_json"])
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if not isinstance(usage, dict):
            continue
        read += int(usage.get("input_tokens") or 0) + int(usage.get("cache_write_tokens") or 0)
        written += int(usage.get("output_tokens") or 0)
    return {"read": read, "written": written}


def _gates(conn: sqlite3.Connection, run_id: str, after: int = 0) -> list[JsonDict]:
    if not _has_table(conn, "gate_results"):
        return []
    checks = (
        "checks_json" if _has_column(conn, "gate_results", "checks_json") else "NULL AS checks_json"
    )
    rows = _rows(
        conn,
        "SELECT id, adw_id, phase_id, attempt, gate, passed, violations_json, "
        f"{checks}, created_at FROM gate_results WHERE adw_id = ? AND id > ? ORDER BY id",
        (run_id, after),
    )
    out: list[JsonDict] = []
    for r in rows:
        violations = _parse_json(r.pop("violations_json"))
        parsed_checks = _parse_json(r.pop("checks_json"))
        r["passed"] = bool(r["passed"])
        r["violations"] = [str(v) for v in violations] if isinstance(violations, list) else []
        r["checks"] = (
            [c for c in parsed_checks if isinstance(c, dict)]
            if isinstance(parsed_checks, list)
            else None
        )
        out.append(r)
    return out


def _envelopes(conn: sqlite3.Connection, run_id: str, after: int = 0) -> list[JsonDict]:
    if not _has_table(conn, "envelopes"):
        return []
    rows = _rows(
        conn,
        "SELECT rowid, envelope_id, adw_id, phase_id, agent, output_type, payload_json, valid, "
        "attempt, created_at FROM envelopes WHERE adw_id = ? AND rowid > ? "
        "ORDER BY created_at, rowid",
        (run_id, after),
    )
    for r in rows:
        raw = r.pop("payload_json")
        r["valid"] = bool(r["valid"])
        payload = _parse_json(raw)
        r["payload"] = payload
        r["payload_raw"] = raw if payload is None and raw else None
    return rows


def run_detail(repo: Path, run_id: str) -> tuple[JsonDict, list[str]]:
    """A run with its session, phases, gates and envelopes (``unknown_run`` when none)."""
    store, row = _open_run(repo, run_id)
    try:
        titles, warnings = _task_titles(repo)
        summary = _summaries(store, [row], titles)[0]
        conn = store.conn
        session = _with_full_request(conn, run_id, _sessions(conn, [run_id]).get(run_id))
        agents = _agent_sessions(conn, run_id)
        agent_events = _agent_events(conn, run_id)
        phases = _phases(conn, run_id, agents, agent_events)
        gates = _gates(conn, run_id)
        envelopes = _envelopes(conn, run_id)
        data = {
            "run": summary,
            "session": session,
            "usage": _usage(agent_events),
            "agents": agents,
            "phases": phases,
            "gates": gates,
            "envelopes": envelopes,
            "cursors": {
                "events": _max_rowid(conn, "events", run_id),
                "phases": _cursor(phases, "rowid", 0),
                "gates": _cursor(gates, "id", 0),
                "envelopes": _cursor(envelopes, "rowid", 0),
            },
        }
    finally:
        store.close()
    return data, warnings


def _cursor(rows: list[JsonDict], key: str, after: int) -> int:
    return max([after, *(int(r[key]) for r in rows if r.get(key) is not None)])


def _max_rowid(conn: sqlite3.Connection, table: str, run_id: str) -> int:
    if not _has_table(conn, table):
        return 0
    row = conn.execute(f"SELECT MAX(rowid) FROM {table} WHERE adw_id = ?", (run_id,)).fetchone()
    return int(row[0] or 0) if row else 0


MAX_OPEN_PHASES = 50


def run_tail(
    repo: Path,
    run_id: str,
    *,
    events_after: int = 0,
    phases_after: int = 0,
    gates_after: int = 0,
    envelopes_after: int = 0,
    open_phases: list[str] | None = None,
    limit: int = DEFAULT_EVENTS_LIMIT,
) -> JsonDict:
    """What is new in a run since the given rowid cursors (``unknown_run`` when none).

    Phases are upserted, so their rowid does not move when their status does: besides
    phases past ``phases_after`` this returns the phases of the new events, the
    ``open_phases`` the client still shows as running and every running phase.
    """
    store, row = _open_run(repo, run_id)
    try:
        conn = store.conn
        capped = max(1, min(limit, MAX_EVENTS_LIMIT))
        events_after = max(0, events_after)
        events: list[JsonDict] = []
        if _has_table(conn, "events"):
            events = _rows(
                conn,
                "SELECT rowid, event_id, adw_id, phase_id, parent_id, type, name, payload_json, "
                "tokens, started_at, ended_at FROM events WHERE adw_id = ? AND rowid > ? "
                "ORDER BY rowid LIMIT ?",
                (run_id, events_after, capped + 1),
            )
        has_more = len(events) > capped
        events = events[:capped]
        for e in events:
            e["payload"] = _parse_json(e.pop("payload_json"))
        touched = sorted(
            {str(e["phase_id"]) for e in events if e["phase_id"]}
            | set((open_phases or [])[:MAX_OPEN_PHASES])
        )
        where = " AND (rowid > ? OR status = 'running'"
        args: tuple[Any, ...] = (max(0, phases_after),)
        if touched:
            where += f" OR phase_id IN ({_placeholders(touched)})"
            args = (*args, *touched)
        where += ")"
        agents = _agent_sessions(conn, run_id)
        candidates = (
            _rows(
                conn,
                f"SELECT phase_id FROM phases WHERE adw_id = ?{where}",
                (run_id, *args),
            )
            if _has_table(conn, "phases")
            else []
        )
        phase_ids = [str(c["phase_id"]) for c in candidates]
        phases = (
            _phases(conn, run_id, agents, _agent_events(conn, run_id, phase_ids), where, args)
            if phase_ids
            else []
        )
        gates = _gates(conn, run_id, max(0, gates_after))
        envelopes = _envelopes(conn, run_id, max(0, envelopes_after))
        titles, _ = _task_titles(repo)
        summary = _summaries(store, [row], titles)[0]
        session = _sessions(conn, [run_id]).get(run_id)
        new_agent_events = [e for e in events if e["type"] == "agent_end"]
        usage_delta = _usage(
            [
                {"type": e["type"], "payload_json": json.dumps(e["payload"])}
                for e in new_agent_events
            ]
        )
    finally:
        store.close()
    return {
        "run": summary,
        "session": session,
        "events": events,
        "phases": phases,
        "gates": gates,
        "envelopes": envelopes,
        "agents": agents,
        "usage_delta": usage_delta,
        "cursors": {
            "events": _cursor(events, "rowid", events_after),
            "phases": _cursor(phases, "rowid", max(0, phases_after)),
            "gates": _cursor(gates, "id", max(0, gates_after)),
            "envelopes": _cursor(envelopes, "rowid", max(0, envelopes_after)),
        },
        "has_more": has_more,
    }


def run_events(
    repo: Path, run_id: str, *, after: int = 0, limit: int = DEFAULT_EVENTS_LIMIT
) -> JsonDict:
    """A page of the run's trace events in insertion order (rowid cursor ``after``)."""
    store, _row = _open_run(repo, run_id)
    try:
        conn = store.conn
        capped = max(1, min(limit, MAX_EVENTS_LIMIT))
        after = max(0, after)
        if not _has_table(conn, "events"):
            return {"events": [], "cursor": after, "has_more": False}
        rows = _rows(
            conn,
            "SELECT rowid, event_id, adw_id, phase_id, parent_id, type, name, payload_json, "
            "tokens, started_at, ended_at FROM events WHERE adw_id = ? AND rowid > ? "
            "ORDER BY rowid LIMIT ?",
            (run_id, after, capped + 1),
        )
    finally:
        store.close()
    has_more = len(rows) > capped
    rows = rows[:capped]
    for r in rows:
        r["payload"] = _parse_json(r.pop("payload_json"))
    cursor = int(rows[-1]["rowid"]) if rows else after
    return {"events": rows, "cursor": cursor, "has_more": has_more}


MAX_PROMPT_BYTES = 256 * 1024
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")
_PROMPT_FILES = ("system", "user")


def _safe_segment(value: object) -> bool:
    """One path segment that cannot leave its directory (no ``/``, ``\\``, NUL or ``..``)."""
    return isinstance(value, str) and bool(_SAFE_ID.fullmatch(value)) and ".." not in value


def _read_prompt(root: Path, path: Path) -> tuple[str | None, bool]:
    """``path`` as text (at most ``MAX_PROMPT_BYTES``) and whether it was cut.

    None when the file is missing, unreadable or (symlinks resolved) outside ``root``.
    """
    try:
        target = path.resolve()
        if not target.is_relative_to(root.resolve()) or not target.is_file():
            return None, False
        with target.open("rb") as handle:
            raw = handle.read(MAX_PROMPT_BYTES + 1)
    except OSError:
        return None, False
    truncated = len(raw) > MAX_PROMPT_BYTES
    return raw[:MAX_PROMPT_BYTES].decode("utf-8", errors="replace"), truncated


def _read_prompts(root: Path, directory: Path) -> tuple[JsonDict, JsonDict]:
    texts: JsonDict = {}
    cut: JsonDict = {}
    for kind in _PROMPT_FILES:
        texts[kind], cut[kind] = _read_prompt(root, directory / f"{kind}.md")
    return texts, cut


def phase_prompts(repo: Path, run_id: str, phase_id: str) -> tuple[JsonDict, list[str]]:
    """The system and user prompt one phase of a run sent.

    From ``<session>/<agent>/prompts/phases/<phase>/``; a run from before per-phase
    prompts falls back to the agent's last prompts (``source == "agent"``, ``legacy``).
    A missing file is None. ``invalid_value`` for an unsafe id, ``unknown_run`` and
    ``unknown_phase`` when the trace has neither.
    """
    if not _safe_segment(run_id) or not _safe_segment(phase_id):
        raise TaskRunError("invalid_value", "invalid run_id or phase_id")
    store, _row = _open_run(repo, run_id)
    try:
        conn = store.conn
        found = (
            _rows(
                conn,
                "SELECT phase_id, name, kind, owner FROM phases "
                "WHERE adw_id = ? AND phase_id = ? LIMIT 1",
                (run_id, phase_id),
            )
            if _has_table(conn, "phases")
            else []
        )
    finally:
        store.close()
    if not found:
        raise TaskRunError("unknown_phase", f"no phase {phase_id} in run {run_id}")
    phase = found[0]
    name, owner, kind = phase["name"], phase["owner"], phase["kind"]
    warnings: list[str] = []
    texts: JsonDict = dict.fromkeys(_PROMPT_FILES)
    cut: JsonDict = dict.fromkeys(_PROMPT_FILES, False)
    source = "none"
    if kind == "code":
        pass
    elif not _safe_segment(owner) or not _safe_segment(name):
        warnings.append("phase owner/name is not a safe path segment")
    else:
        session = session_dir_of(repo, run_id)
        prompts_dir = session / str(owner) / "prompts"
        texts, cut = _read_prompts(session, prompts_dir / "phases" / str(name))
        if any(texts[k] is not None for k in _PROMPT_FILES):
            source = "phase"
        else:
            texts, cut = _read_prompts(session, prompts_dir)
            if any(texts[k] is not None for k in _PROMPT_FILES):
                source = "agent"
                warnings.append("run has no per-phase prompts; showing the agent's last prompts")
    data = {
        "run_id": run_id,
        "phase_id": phase_id,
        "phase": name,
        "agent": owner,
        "kind": kind,
        "source": source,
        "legacy": source == "agent",
        "system": texts["system"],
        "user": texts["user"],
        "truncated": cut,
        "max_bytes": MAX_PROMPT_BYTES,
    }
    return data, warnings


def _store(repo: Path) -> TaskRunStore:
    store = existing_store(repo)
    if store is None:
        raise TaskRunError("unknown_run", "there is no trace database")
    return store


def archive_run(repo: Path, run_id: str) -> JsonDict:
    """Archive a finished run (``run_running`` while it runs); the run as in the list."""
    store = _store(repo)
    try:
        if not store.archive(run_id):
            raise TaskRunError("unknown_run", f"no run {run_id}")
    finally:
        store.close()
    return run_summary(repo, run_id)


def unarchive_run(repo: Path, run_id: str) -> JsonDict:
    """Return an archived run to the active ones; the run as in the list."""
    store = _store(repo)
    try:
        if not store.unarchive(run_id):
            raise TaskRunError("unknown_run", f"no run {run_id}")
    finally:
        store.close()
    return run_summary(repo, run_id)


def delete_run(repo: Path, run_id: str) -> JsonDict:
    """Erase an archived run and its trace (``run_not_archived`` otherwise)."""
    store = _store(repo)
    try:
        if not store.delete_run(run_id):
            raise TaskRunError("unknown_run", f"no run {run_id}")
    finally:
        store.close()
    return {"deleted": [run_id]}


def archive_finished(repo: Path) -> JsonDict:
    """Archive every finished run (succeeded, failed, aborted, stopped)."""
    store = existing_store(repo)
    if store is None:
        return {"archived": []}
    try:
        return {"archived": store.archive_finished()}
    finally:
        store.close()


def delete_archived(repo: Path) -> JsonDict:
    """Erase every archived run and its trace."""
    store = existing_store(repo)
    if store is None:
        return {"deleted": []}
    try:
        return {"deleted": store.delete_archived()}
    finally:
        store.close()
