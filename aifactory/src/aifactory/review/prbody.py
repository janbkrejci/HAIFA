"""Title and body of a task's pull request, from the task, the run and the trace DB."""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from aifactory import database
from aifactory.backlog import Task
from aifactory.engine.tracer import BUSY_TIMEOUT
from aifactory.workflow import StepRecord, WorkflowRun


class RunLike(Protocol):
    run_id: str
    branch: str
    note: str | None


def pr_title(task: Task) -> str:
    return f"{task.id}: {task.title}"


@contextlib.contextmanager
def _trace(trace_db: Path) -> Iterator[sqlite3.Connection | None]:
    if not database.available(trace_db):
        yield None
        return
    conn = database.connect(f"file:{trace_db}?mode=ro", uri=True, timeout=BUSY_TIMEOUT)
    try:
        yield conn
    finally:
        conn.close()


def _query(trace_db: Path, sql: str, args: tuple[Any, ...]) -> list[tuple[Any, ...]]:
    with _trace(trace_db) as conn:
        if conn is None:
            return []
        try:
            return list(conn.execute(sql, args).fetchall())
        except sqlite3.OperationalError:
            return []


def run_cost(trace_db: Path, run_id: str) -> tuple[float, int]:
    rows = _query(
        trace_db, "SELECT total_cost, total_tokens FROM sessions WHERE adw_id = ?", (run_id,)
    )
    if not rows:
        return 0.0, 0
    cost, tokens = rows[0]
    return float(cost or 0.0), int(tokens or 0)


def branch_cost(trace_db: Path, run_ids: Sequence[str]) -> tuple[float, int]:
    total, tokens = 0.0, 0
    for run_id in run_ids:
        cost, used = run_cost(trace_db, run_id)
        total += cost
        tokens += used
    return total, tokens


@dataclass(frozen=True)
class StepInfo:
    """An agent step of a run, as the trace recorded it."""

    step: str
    agent: str
    harness: str | None
    model: str | None


@dataclass(frozen=True)
class CheckInfo:
    """A gate verdict or a test/quality/command step result of a run."""

    kind: str  # "gate" | "test"
    name: str
    phase: str
    passed: bool
    detail: str


def _payload(raw: object) -> dict[str, Any]:
    try:
        data = json.loads(str(raw)) if raw else {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def run_steps(trace_db: Path, run_id: str) -> list[StepInfo]:
    """Agent phases of `run_id` in order, with the harness and model each one used."""
    rows = _query(
        trace_db,
        "SELECT p.phase_id, p.name, p.owner, e.payload_json FROM phases p "
        "LEFT JOIN events e ON e.phase_id = p.phase_id AND e.type = 'log' "
        "WHERE p.adw_id = ? AND p.kind = 'agent' ORDER BY p.seq, e.started_at",
        (run_id,),
    )
    steps: dict[str, StepInfo] = {}
    for phase_id, name, owner, payload_json in rows:
        known = steps.get(str(phase_id))
        if known is not None and known.harness is not None:
            continue
        payload = _payload(payload_json)
        if known is None or "harness" in payload:
            harness = payload.get("harness") if "harness" in payload else None
            model = payload.get("model") if "harness" in payload else None
            steps[str(phase_id)] = StepInfo(
                step=str(name or ""),
                agent=str(owner or ""),
                harness=str(harness) if harness is not None else None,
                model=str(model) if model is not None else None,
            )
    return list(steps.values())


def run_checks(trace_db: Path, run_id: str) -> list[CheckInfo]:
    """Gates (latest verdict per phase and gate) then test steps of `run_id`."""
    rows = _query(
        trace_db,
        "SELECT COALESCE(p.name, g.phase_id), g.gate, g.passed, g.violations_json "
        "FROM gate_results g LEFT JOIN phases p ON p.phase_id = g.phase_id "
        "WHERE g.adw_id = ? ORDER BY g.id",
        (run_id,),
    )
    latest: dict[tuple[str, str], tuple[bool, list[str]]] = {}
    for phase, gate, passed, violations_json in rows:
        try:
            violations = json.loads(violations_json or "[]")
        except json.JSONDecodeError:
            violations = []
        latest[(str(phase), str(gate))] = (
            bool(passed),
            [str(v) for v in violations] if isinstance(violations, list) else [],
        )
    checks = [
        CheckInfo("gate", gate, phase, passed, "; ".join(violations))
        for (phase, gate), (passed, violations) in latest.items()
    ]
    tests = _query(
        trace_db,
        "SELECT p.name, e.payload_json FROM phases p "
        "JOIN events e ON e.phase_id = p.phase_id AND e.type = 'log' "
        "WHERE p.adw_id = ? AND p.kind = 'code' ORDER BY p.seq, e.started_at",
        (run_id,),
    )
    for name, payload_json in tests:
        payload = _payload(payload_json)
        if isinstance(payload.get("passed"), bool):
            checks.append(
                CheckInfo(
                    "test",
                    str(name or ""),
                    str(name or ""),
                    bool(payload["passed"]),
                    str(payload.get("test_plan") or payload.get("checks") or ""),
                )
            )
    return checks


def _gates(trace_db: Path, run_id: str) -> list[str]:
    lines = []
    for check in run_checks(trace_db, run_id):
        if check.kind != "gate":
            continue
        verdict = "prošla" if check.passed else f"neprošla ({check.detail or 'bez detailu'})"
        lines.append(f"- gate `{check.name}` v `{check.phase}`: {verdict}")
    return lines


def _agents(wf: WorkflowRun) -> list[str]:
    last: dict[str, StepRecord] = {}
    for record in wf.records:
        if record.kind == "agent":
            last[record.step] = record
    lines = []
    for step, record in last.items():
        envelope = wf.envelopes.get(step)
        summary = str(getattr(envelope, "summary", "") or "").strip() or "(bez shrnutí)"
        how = "/".join(x for x in (record.harness, record.model) if x) or "?"
        lines.append(f"- `{step}` ({record.owner}, {how}): {summary}")
    return lines


def _tests(wf: WorkflowRun) -> list[str]:
    lines = []
    for key, result in wf.results.items():
        if "passed" in result and "approved" not in result:
            verdict = "prošly" if result.get("passed") else "neprošly"
            plan = result.get("test_plan") or {}
            coverage = plan.get("coverage")
            if coverage == "none":
                verdict = "neprovedeno"
            elif coverage == "scoped":
                verdict = f"cílené ověření: {verdict}"
            elif coverage == "full":
                verdict = f"plné ověření: {verdict}"
            commands = [str(c) for c in plan.get("commands") or []]
            if commands:
                verdict += "; " + ", ".join(f"`{c}`" for c in commands)
            summary = str(result.get("summary") or "").strip()
            lines.append(f"- test `{key}`: {verdict}" + (f" ({summary})" if summary else ""))
    return lines


def _reviews(wf: WorkflowRun) -> list[str]:
    lines = []
    for key, result in wf.results.items():
        if "approved" not in result:
            continue
        line = f"- `{key}`: {'schváleno' if result.get('approved') else 'neschváleno'}"
        blocking = [str(b) for b in result.get("blocking") or []]
        if blocking:
            line += f"; blokující: {'; '.join(blocking)}"
        summary = str(result.get("summary") or "").strip()
        if summary:
            line += f" — {summary}"
        lines.append(line)
    return lines


def pr_body(
    task: Task, runs: Sequence[RunLike], wf: WorkflowRun | None, trace_db: Path, branch: str
) -> str:
    """Markdown body: task, agents, gates and tests, review, costs (all runs on the branch)."""
    out = [f"<!-- factory: task={task.id} branch={branch} -->", "", "## Zadání", ""]
    body = task.body.strip()
    if body.splitlines()[:1] == ["## Zadání"]:
        body = body.split("\n", 1)[1].strip() if "\n" in body else ""
    out.append(body or f"{task.id}: {task.title}")
    notes = [(r.run_id, r.note.strip()) for r in reversed(list(runs)) if r.note and r.note.strip()]
    for run_id, note in notes:
        out += ["", f"Poznámka k běhu {run_id}: {note}"]
    out += ["", "## Agenti", ""]
    out += (_agents(wf) if wf else []) or ["- žádný agent neběžel"]
    checks = (_gates(trace_db, wf.adw_id) if wf else []) + (_tests(wf) if wf else [])
    out += ["", "## Gates a testy", ""] + (checks or ["- nic neběželo"])
    out += ["", "## Review", ""] + ((_reviews(wf) if wf else []) or ["- review neběželo"])
    out += ["", "## Náklady", ""]
    total = 0.0
    for r in reversed(list(runs)):
        cost, tokens = run_cost(trace_db, r.run_id)
        total += cost
        out.append(f"- běh {r.run_id}: ${cost:.2f}, {tokens} tokenů")
    out.append(f"- celkem: ${total:.2f}")
    return "\n".join(out) + "\n"
