"""Title and body of a task's pull request, from the task, the run and the trace DB."""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from aifactory import database
from aifactory.backlog import Task
from aifactory.engine.data_types import PrSummary
from aifactory.engine.tracer import BUSY_TIMEOUT
from aifactory.workflow import StepRecord, WorkflowRun

if TYPE_CHECKING:  # aifactory.run imports aifactory.review lazily; keep it one-way here
    from aifactory.run.followups import CreatedFollowUp


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


def _short(text: str, limit: int = 160) -> str:
    """`text` on one line, cut to `limit` characters with an ellipsis."""
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


def _agents(wf: WorkflowRun) -> list[str]:
    last: dict[str, StepRecord] = {}
    for record in wf.records:
        if record.kind == "agent":
            last[record.step] = record
    lines = []
    for step, record in last.items():
        envelope = wf.envelopes.get(step)
        summary = _short(str(getattr(envelope, "summary", "") or "")) or "(bez shrnutí)"
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
            not_run = [n for n in plan.get("not_run") or [] if isinstance(n, dict)]
            if not_run:
                verdict += "; nespuštěno: " + ", ".join(
                    f"`{n.get('name')}` ({n.get('reason')})" for n in not_run
                )
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
        summary = _short(str(result.get("summary") or ""))
        if summary:
            line += f" — {summary}"
        lines.append(line)
    return lines


SUMMARY_END = "<!-- factory: summary-end -->"
_NO_SUMMARY = "_Agenti běhu shrnutí nedodali._"


def latest_summary(wf: WorkflowRun | None) -> PrSummary | None:
    """The newest non-empty ``pr_summary`` an agent of the run reported, else None."""
    if wf is None:
        return None
    for _, envelope in reversed(wf.history):
        summary = getattr(envelope, "pr_summary", None)
        if isinstance(summary, PrSummary) and not summary.empty:
            return summary
    return None


def previous_summary(body: str | None) -> str | None:
    """The summary block of an earlier PR body (between the marker line and SUMMARY_END)."""
    if not body or SUMMARY_END not in body:
        return None
    head = body.split(SUMMARY_END, 1)[0]
    lines = head.splitlines()
    if lines and lines[0].startswith("<!-- factory: task="):
        lines = lines[1:]
    text = "\n".join(lines).strip()
    return text or None


def _items(values: Sequence[str]) -> list[str]:
    return [f"- {v.strip()}" for v in values if v.strip()]


def _last_build_summary(wf: WorkflowRun | None) -> str:
    """The summary of the last envelope that reported changed files (a build or a fix)."""
    if wf is None:
        return ""
    for _, envelope in reversed(wf.history):
        if "changed_files" in type(envelope).model_fields:
            return str(getattr(envelope, "summary", "") or "").strip()
    return ""


def summary_block(
    summary: PrSummary | None,
    task: Task,
    wf: WorkflowRun | None,
    follow_ups: Sequence[CreatedFollowUp] = (),
) -> str:
    """Goal, what was done, what was not (with new backlog tasks), notes for approval.

    The text comes from the agents' ``pr_summary``; without one, the task title and the
    build's summary stand in. The task text itself is never copied.
    """
    if summary is None or summary.empty:
        goal = f"{task.title}\n\n{_NO_SUMMARY}"
        build = _last_build_summary(wf)
        done = [f"- {build}"] if build else ["- (bez shrnutí)"]
        not_done: list[str] = []
        notes: list[str] = []
    else:
        goal = summary.goal.strip() or task.title
        done = _items(summary.done) or ["- (bez shrnutí)"]
        not_done = _items(summary.not_done)
        notes = _items(summary.notes)
    for item in follow_ups:
        tag = "blokuje tento task" if item.blocks else "nový task"
        reason = f" ({item.reason})" if item.reason else ""
        not_done.append(f"- {tag} `{item.id}`: {item.title}{reason}")
    out = ["## Cíl", "", goal, "", "## Co bylo uděláno", "", *done]
    out += ["", "## Co uděláno nebylo", "", *(not_done or ["- nic"])]
    if notes:
        out += ["", "## Důležité pro schválení", "", *notes]
    return "\n".join(out)


def pr_body(
    task: Task,
    runs: Sequence[RunLike],
    wf: WorkflowRun | None,
    trace_db: Path,
    branch: str,
    *,
    follow_ups: Sequence[CreatedFollowUp] = (),
    previous_body: str | None = None,
    reuse_summary: bool = False,
    switches: Sequence[str] = (),
) -> str:
    """Markdown body: the agents' summary first, then the technical details.

    `switches` are the harness switches of the runs (``run.fallback.harness_switches``),
    one line each: from which harness or model to which and why.

    The summary (goal, done, not done, notes for approval) comes from the run's agents.
    `reuse_summary` (a resolve run) or a run without one keeps the summary of
    `previous_body`, the branch's earlier PR body, when it has one. The technical part
    covers every run on the branch: agents, gates and tests, review, costs.
    """
    out = [f"<!-- factory: task={task.id} branch={branch} -->", ""]
    summary = latest_summary(wf)
    kept = previous_summary(previous_body)
    if kept is not None and (reuse_summary or summary is None):
        out.append(kept)
    else:
        out.append(summary_block(summary, task, wf, follow_ups))
    out += ["", SUMMARY_END, "", "## Technické podrobnosti"]
    notes = [(r.run_id, r.note.strip()) for r in reversed(list(runs)) if r.note and r.note.strip()]
    if notes:
        out += ["", "### Poznámky k běhům", ""]
        out += [f"- běh {run_id}: {_short(note, 300)}" for run_id, note in notes]
    if switches:
        out += ["", "### Přepnutí harnessu", ""]
        out += [f"- {line}" for line in switches]
    out += ["", "### Agenti", ""]
    out += (_agents(wf) if wf else []) or ["- žádný agent neběžel"]
    checks = (_gates(trace_db, wf.adw_id) if wf else []) + (_tests(wf) if wf else [])
    out += ["", "### Gates a testy", ""] + (checks or ["- nic neběželo"])
    out += ["", "### Review", ""] + ((_reviews(wf) if wf else []) or ["- review neběželo"])
    out += ["", "### Náklady", ""]
    total = 0.0
    for r in reversed(list(runs)):
        cost, tokens = run_cost(trace_db, r.run_id)
        total += cost
        out.append(f"- běh {r.run_id}: ${cost:.2f}, {tokens} tokenů")
    out.append(f"- celkem: ${total:.2f}")
    return "\n".join(out) + "\n"
