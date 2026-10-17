"""For the ``factory learn`` tests: a repo with a trace DB of runs, and a fake harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from advice_fixture import git, make_repo
from aifactory.engine import agents
from aifactory.engine.data_types import AgentResult
from aifactory.engine.tracer import Tracer
from aifactory.harness.check import HarnessStatus
from aifactory.run.store import TaskRunStore


def _run(db: Any, run_id: str, task_id: str) -> None:
    db.execute(
        "INSERT INTO task_runs (run_id, task_id, branch, worktree, base, base_sha, state, "
        "started_at) VALUES (?,?,?,?,?,?,?,?)",
        (run_id, task_id, f"b-{run_id}", "/wt", "main", "0" * 40, "succeeded", "2026-10-01"),
    )
    db.execute("INSERT INTO sessions (adw_id, status) VALUES (?, 'success')", (run_id,))


def _envelope(
    db: Any,
    run_id: str,
    phase: str,
    agent: str,
    output_type: str,
    payload: dict[str, Any],
    created_at: str,
    *,
    valid: bool = True,
) -> None:
    phase_id = f"{run_id}-{phase}"
    db.execute(
        "INSERT OR IGNORE INTO phases (phase_id, adw_id, name) VALUES (?,?,?)",
        (phase_id, run_id, phase),
    )
    db.execute(
        "INSERT INTO envelopes (envelope_id, adw_id, phase_id, agent, output_type, "
        "payload_json, valid, attempt, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            f"env-{run_id}-{phase}-{created_at}",
            run_id,
            phase_id,
            agent,
            output_type,
            json.dumps({"status": "success", "summary": "", **payload}),
            int(valid),
            1,
            created_at,
        ),
    )


def _review(*blocking: str, approved: bool = False) -> dict[str, Any]:
    return {"approved": approved, "blocking": list(blocking), "findings": []}


def make_learn_repo(tmp_path: Path) -> Path:
    root = make_repo(tmp_path / "repo")
    # `factory learn accept` commits the backlog with the repo's own identity; CI has none.
    git(root, "config", "user.name", "test")
    git(root, "config", "user.email", "test@test")
    db_path = root / ".factory/trace.db"
    TaskRunStore(db_path).close()
    tracer = Tracer(db_path, tmp_path / "events.jsonl")
    db = tracer.conn
    _run(db, "run-a", "P01-S01-T01")
    _run(db, "run-b", "P01-S01-T02")
    _run(db, "run-c", "P01-S01-T03")
    # c1: run-a, review
    _envelope(
        db,
        "run-a",
        "review",
        "reviewer",
        "ReviewOutput",
        _review("The new CLI command has no test."),
        "2026-10-02T10:00:00.000+00:00",
    )
    # an invalid attempt counts for nothing
    _envelope(
        db,
        "run-a",
        "review",
        "reviewer",
        "ReviewOutput",
        _review("garbage"),
        "2026-10-02T10:00:01.000+00:00",
        valid=False,
    )
    # c2: run-b, review (an unmet finding); c3: run-b, test triage
    _envelope(
        db,
        "run-b",
        "review",
        "reviewer",
        "ReviewOutput",
        {
            "approved": False,
            "blocking": [],
            "findings": [
                {"requirement": "tests", "met": False, "evidence": "no test for 'factory x'"},
                {"requirement": "docs", "met": True, "evidence": "README"},
            ],
        },
        "2026-10-05T10:00:00.000+00:00",
    )
    _envelope(
        db,
        "run-b",
        "test_plan_triage",
        "tester",
        "TestPlanOutput",
        {"coverage": "none", "reason": "ruff failed on unused import", "failure_cause": "code"},
        "2026-10-05T11:00:00.000+00:00",
    )
    # run-c approves: no objection
    _envelope(
        db,
        "run-c",
        "review",
        "reviewer",
        "ReviewOutput",
        _review(approved=True),
        "2026-10-06T10:00:00.000+00:00",
    )
    tracer.conn.close()
    return root


def fake_learner(monkeypatch: pytest.MonkeyPatch) -> tuple[list[Any], list[dict[str, Any]]]:
    """The requests the fake harness saw, and the answers it gives in order."""
    seen: list[Any] = []
    answers: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "aifactory.learn.scan.check_harness", lambda name: HarnessStatus(name, "fake", "fake", "1")
    )

    def run(request: Any, **kwargs: Any) -> AgentResult:
        seen.append(request)
        answer = answers[min(len(seen), len(answers)) - 1]
        return AgentResult(text=json.dumps(answer), returncode=0)

    monkeypatch.setattr(agents.INTERFACES["claude"], "run", run)
    return seen, answers
