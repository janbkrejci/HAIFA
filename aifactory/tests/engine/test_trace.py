"""Phases and events land in the trace DB; ``run.finish`` settles the session."""

from __future__ import annotations

import json

import pytest
from engine_fakes import (  # noqa: F401
    EngineEnv,
    agent_phase,
    engine_env_fixture,
    events_of,
    rows,
    start,
    types_of,
)

from aifactory.engine import session
from aifactory.engine.data_types import PhaseParams
from aifactory.engine.runner import Run

CODE = PhaseParams(
    name="lint", kind="code", owner="git", description="Run a deterministic step for the test"
)


def _code_phase(run: Run) -> None:
    with run.phase(CODE) as ph:
        ph.log(note="x")


def _failing_phase(run: Run) -> None:
    with pytest.raises(ValueError, match="boom"), run.phase(CODE):
        raise ValueError("boom")


def _session(env: EngineEnv, adw_id: str) -> tuple[str, str | None]:
    found = rows(env.db_path, "SELECT status, ended_at FROM sessions WHERE adw_id=?", adw_id)
    assert len(found) == 1
    return str(found[0][0]), found[0][1]


def test_code_phase_is_traced(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)
    _code_phase(run)

    phase_id = f"{run.adw_id}_01_lint"
    phases = rows(
        env.db_path, "SELECT phase_id, seq, status, ended_at FROM phases WHERE adw_id=?", run.adw_id
    )
    assert len(phases) == 1
    assert phases[0][:3] == (phase_id, 1, "success")
    assert phases[0][3]
    events = events_of(env.db_path, phase_id)
    assert types_of(events) == ["phase_start", "log", "phase_end"]
    assert events[-1][2] == {"status": "success"}
    jsonl = env.data_dir / "sessions" / run.adw_id / "events.jsonl"
    assert len(jsonl.read_text().splitlines()) >= 3


def test_agent_phase_is_traced(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)
    env.script.add_ok("builder")
    agent_phase(run, "builder")

    phase_id = f"{run.adw_id}_01_builder"
    kinds = types_of(events_of(env.db_path, phase_id))
    order = ["agent_start", "handoff", "agent_end", "phase_end"]
    assert [k for k in kinds if k in order] == order
    assert rows(env.db_path, "SELECT valid FROM envelopes WHERE phase_id=?", phase_id) == [(1,)]
    assert rows(env.db_path, "SELECT agent FROM agent_sessions WHERE adw_id=?", run.adw_id) == [
        ("builder",)
    ]
    agent_dir = env.data_dir / "sessions" / run.adw_id / "builder"
    assert (agent_dir / "envelope.json").is_file()
    assert (agent_dir / "prompts" / "user.md").read_text() == "do it\n"
    agent_map = json.loads((agent_dir.parent / "agent_map.json").read_text())
    assert agent_map["builder"]["session_id"] == env.script.calls[0].session_id


def test_exception_fails_phase_and_session(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)
    _failing_phase(run)

    phase_id = f"{run.adw_id}_01_lint"
    status, error = rows(
        env.db_path, "SELECT status, error FROM phases WHERE phase_id=?", phase_id
    )[0]
    assert status == "fail" and "boom" in error
    events = events_of(env.db_path, phase_id)
    assert types_of(events)[-2:] == ["error", "phase_end"]
    assert events[-1][2] == {"status": "fail"}
    assert _session(env, run.adw_id)[0] == "fail"


def test_finish_accepted(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)
    _code_phase(run)

    assert run.finish(accepted=True) == 0
    status, ended = _session(env, run.adw_id)
    assert status == "success" and ended


@pytest.mark.parametrize(
    ("reason", "expected"),
    [("suite red", "suite red"), ("", "the run's acceptance criterion was not met")],
)
def test_finish_not_accepted(engine_env: EngineEnv, reason: str, expected: str) -> None:
    env = engine_env
    run = start(env)
    _code_phase(run)

    assert run.finish(accepted=False, reason=reason) == 1
    assert _session(env, run.adw_id)[0] == "fail"
    found = rows(
        env.db_path,
        "SELECT payload_json FROM events WHERE adw_id=? AND type='error' AND name='not_accepted'",
        run.adw_id,
    )
    assert [json.loads(p) for (p,) in found] == [{"reason": expected}]


def _not_accepted_count(env: EngineEnv, adw_id: str) -> int:
    found = rows(
        env.db_path, "SELECT COUNT(*) FROM events WHERE adw_id=? AND name='not_accepted'", adw_id
    )
    return int(found[0][0])


def test_finish_without_phases_fails(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)

    assert run.finish() == 1
    assert _session(env, run.adw_id)[0] == "fail"
    assert _not_accepted_count(env, run.adw_id) == 0


def test_finish_with_failed_phase_fails(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)
    _failing_phase(run)

    assert run.finish(accepted=True) == 1
    assert _session(env, run.adw_id)[0] == "fail"
    assert _not_accepted_count(env, run.adw_id) == 0


def test_joined_run_continues_sequence(engine_env: EngineEnv) -> None:
    env = engine_env
    first = session.ensure(env.cfg, "same-id")
    _code_phase(first)
    second = session.ensure(env.cfg, "same-id")
    _code_phase(second)

    phases = rows(
        env.db_path, "SELECT seq, phase_id FROM phases WHERE adw_id=? ORDER BY seq", "same-id"
    )
    assert phases == [(1, "same-id_01_lint"), (2, "same-id_02_lint")]
