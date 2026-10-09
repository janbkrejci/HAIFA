"""A repo with a backlog and a trace DB of three task runs, for the Runs API tests.

``T1`` has two runs: ``r-ok`` (succeeded, with a PR and a full trace) and
``r-fail`` (failed); ``T2`` has ``r-run`` (running under ``running_pid``).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from web_repo import git_repo

from aifactory.engine.tracer import SCHEMA
from aifactory.run.store import TaskPrRow, TaskRunRow, TaskRunStore

T1 = "M01-S01-T01"
T2 = "M01-S01-T02"

_FILES = {
    ".factory/config.yaml": "base: main\n",
    "backlog/M01-core/index.md": "---\nid: M01\ntitle: Core\nworkflow: plan-commit\n---\n",
    "backlog/M01-core/S01-model/index.md": (
        "---\nid: M01-S01\ntitle: Model\nwrites: [src/app/]\n---\n"
    ),
    "backlog/M01-core/S01-model/M01-S01-T01-schema.md": (
        f"---\nid: {T1}\ntitle: Schema\nstatus: todo\n---\n\n## Zadání\nSchéma.\n"
    ),
    "backlog/M01-core/S01-model/M01-S01-T02-loader.md": (
        f"---\nid: {T2}\ntitle: Loader\nstatus: todo\n---\n\n## Zadání\nLoader.\n"
    ),
}

USAGE = {
    "input_tokens": 100,
    "output_tokens": 30,
    "cache_read_tokens": 1000,
    "cache_write_tokens": 50,
    "total_tokens": 1180,
    "input_cost": 0.1,
    "output_cost": 0.1,
    "cache_read_cost": 0.03,
    "cache_write_cost": 0.02,
    "total_cost": 0.25,
}


def _run(run_id: str, task_id: str, n: int, state: str, day: int, **extra: object) -> TaskRunRow:
    return TaskRunRow(
        run_id=run_id,
        task_id=task_id,
        branch=f"factory/{task_id}-{n}",
        worktree=f"/tmp/wt/{run_id}",
        base="main",
        base_sha="0" * 40,
        head_sha=None,
        state=state,
        started_at=f"2026-01-0{day}T10:00:00+00:00",
        workflow="plan-commit",
        **extra,  # type: ignore[arg-type]
    )


def make_repo(path: Path) -> Path:
    """A git repo with ``.factory/config.yaml`` and a two-task backlog (no trace DB)."""
    root = git_repo(path)
    for rel, text in _FILES.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    return root


def make_trace_db(path: Path, running_pid: int) -> Path:
    """The repo at ``path`` with ``.factory/trace.db``; returns the repo root."""
    root = make_repo(path)
    db = root / ".factory" / "trace.db"
    store = TaskRunStore(db)
    store.claim(
        _run("r-ok", T1, 1, "running", 1, pid=running_pid)
    )  # claim, then finish, like a real run
    store.finish("r-ok", "succeeded", "a" * 40, None)
    store.conn.execute(
        "UPDATE task_runs SET ended_at = ? WHERE run_id = 'r-ok'", ("2026-01-01T10:05:00+00:00",)
    )
    store.claim(_run("r-fail", T1, 2, "running", 2, pid=running_pid))
    store.finish("r-fail", "failed", None, "accept not met")
    store.conn.execute(
        "UPDATE task_runs SET ended_at = ? WHERE run_id = 'r-fail'",
        ("2026-01-02T10:01:00+00:00",),
    )
    store.claim(_run("r-run", T2, 1, "running", 3, pid=running_pid, started_by="auto-continue"))
    store.save_pr(
        TaskPrRow(
            branch=f"factory/{T1}-1",
            task_id=T1,
            provider="local",
            pr_id="7",
            url="https://example.test/pr/7",
            base="main",
            base_sha="0" * 40,
            title="Schema",
            body="",
            state="open",
            created_at="2026-01-01T10:05:00+00:00",
            updated_at="2026-01-01T10:05:00+00:00",
        )
    )
    store.close()

    conn = sqlite3.connect(str(db), isolation_level=None)
    conn.executescript(SCHEMA)
    for adw_id, status, total, cost in (
        ("r-ok", "success", 1180, 0.25),
        ("r-fail", "fail", 500, 0.05),
        ("r-run", "running", 100, 0.01),
    ):
        conn.execute(
            "INSERT INTO sessions (adw_id, adw_name, status, engineer, started_at, "
            "total_tokens, total_cost) VALUES (?, 'factory', ?, 'tester', ?, ?, ?)",
            (adw_id, status, "2026-01-01T10:00:00+00:00", total, cost),
        )
    # Inserted out of order: the API sorts by seq.
    conn.execute(
        "INSERT INTO phases (phase_id, adw_id, seq, name, kind, owner, status, attempt, "
        "retries, started_at, ended_at) VALUES ('p2', 'r-ok', 2, 'test', 'code', 'tests', "
        "'fail', 1, 0, '2026-01-01T10:03:00+00:00', '2026-01-01T10:05:00+00:00')"
    )
    conn.execute(
        "INSERT INTO phases (phase_id, adw_id, seq, name, kind, owner, status, attempt, "
        "retries, started_at, ended_at) VALUES ('p1', 'r-ok', 1, 'plan', 'agent', 'planner', "
        "'success', 1, 2, '2026-01-01T10:00:00+00:00', '2026-01-01T10:03:00+00:00')"
    )
    conn.execute(
        "INSERT INTO phases (phase_id, adw_id, seq, name, kind, owner, status, attempt, "
        "retries, started_at) VALUES ('p3', 'r-run', 1, 'plan', 'agent', 'planner', "
        "'running', 1, 2, '2026-01-03T10:00:00+00:00')"
    )
    events: list[tuple[str, str, str, str, dict[str, object], int | None]] = [
        ("e1", "p1", "phase_start", "plan", {}, None),
        (
            "e2",
            "p1",
            "agent_start",
            "planner",
            {"coding_agent": "claude", "model": "claude-opus", "session_id": "s1"},
            None,
        ),
        (
            "e3",
            "p1",
            "tool_call",
            "Read",
            {
                "tool": "Read",
                "args": {"file_path": "src/app/x.py"},
                "result_snippet": "print('x')",
                "ok": True,
                "agent": "planner",
            },
            None,
        ),
        ("e4", "p1", "agent_end", "planner", {"cost": 0.25, "usage": USAGE}, 1180),
        ("e5", "p1", "phase_end", "plan", {"status": "success"}, None),
        ("e6", "p2", "phase_start", "test", {}, None),
        ("e7", "p2", "gate_fail", "tests", {"violations": ["tests failed"]}, None),
        ("e8", "p2", "phase_end", "test", {"status": "fail"}, None),
    ]
    for event_id, phase_id, type_, name, payload, tokens in events:
        conn.execute(
            "INSERT INTO events (event_id, adw_id, phase_id, type, name, payload_json, tokens, "
            "started_at) VALUES (?, 'r-ok', ?, ?, ?, ?, ?, '2026-01-01T10:01:00+00:00')",
            (event_id, phase_id, type_, name, json.dumps(payload), tokens),
        )
    conn.execute(
        "INSERT INTO gate_results (adw_id, phase_id, attempt, gate, passed, violations_json, "
        "checks_json, created_at) VALUES ('r-ok', 'p1', 1, 'artifacts_exist', 1, '[]', ?, "
        "'2026-01-01T10:02:00+00:00')",
        (json.dumps([{"item": "specs/x.md", "ok": True, "note": "exists"}]),),
    )
    conn.execute(
        "INSERT INTO gate_results (adw_id, phase_id, attempt, gate, passed, violations_json, "
        "checks_json, created_at) VALUES ('r-ok', 'p2', 1, 'tests_pass', 0, ?, NULL, "
        "'2026-01-01T10:04:00+00:00')",
        (json.dumps(["tests failed"]),),
    )
    conn.execute(
        "INSERT INTO envelopes (envelope_id, adw_id, phase_id, agent, output_type, "
        "payload_json, valid, attempt, created_at) VALUES ('env1', 'r-ok', 'p1', 'planner', "
        "'PlanOutput', ?, 1, 1, '2026-01-01T10:02:00+00:00')",
        (json.dumps({"status": "success", "summary": "a plan"}),),
    )
    conn.execute(
        "INSERT INTO agent_sessions (adw_id, agent, coding_agent, model, session_id, "
        "created_at, last_used_at) VALUES ('r-run', 'planner', 'codex', 'gpt-5', 's9', "
        "'2026-01-03T10:00:00+00:00', '2026-01-03T10:00:00+00:00')"
    )
    conn.close()
    return root
