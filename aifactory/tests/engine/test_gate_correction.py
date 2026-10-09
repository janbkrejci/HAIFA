"""Gate violations flow back into the SAME agent session as a correction."""

from __future__ import annotations

import json

import pytest
from engine_fakes import (  # noqa: F401
    EngineEnv,
    agent_phase,
    engine_env_fixture,
    event_names,
    ok,
    rows,
    start,
)

from aifactory.engine import agents
from aifactory.engine.data_types import EnvelopeBase, GateCheck, GateReport
from aifactory.engine.runner import Run


def summary_fixed(envelope: EnvelopeBase, run: Run) -> GateReport:
    return GateReport(checks=[GateCheck(item="summary", ok=envelope.summary == "fixed")])


def legacy_fixed(envelope: EnvelopeBase, run: Run) -> list[str]:
    return [] if envelope.summary == "fixed" else ["bad"]


@pytest.mark.parametrize("gate", [summary_fixed, legacy_fixed])
def test_gate_failure_is_corrected_in_same_session(engine_env: EngineEnv, gate: object) -> None:
    assert callable(gate)
    env = engine_env
    run = start(env)
    env.script.add_ok("builder", summary="wrong")
    env.script.add_ok("builder", summary="fixed")

    envelope = agent_phase(run, "builder", retries=1, gates=[gate])

    assert envelope.summary == "fixed"
    calls = env.script.calls
    assert len(calls) == 2
    assert calls[0].session_id == calls[1].session_id
    assert calls[1].prompt.startswith("Your previous response failed validation:")
    assert calls[1].prompt.endswith("re-emit ONLY your Report JSON.")

    phase_id = f"{run.adw_id}_01_builder"
    gate_name = gate.__name__  # type: ignore[attr-defined]
    results = rows(
        env.db_path,
        "SELECT attempt, passed FROM gate_results WHERE phase_id=? AND gate=? ORDER BY id",
        phase_id,
        gate_name,
    )
    assert results == [(1, 0), (2, 1)]
    assert event_names(env.db_path, run.adw_id, "gate_fail") == [gate_name]
    assert event_names(env.db_path, run.adw_id, "gate_pass") == [gate_name]
    assert rows(env.db_path, "SELECT attempt FROM phases WHERE phase_id=?", phase_id) == [(1,)]


def test_no_retries_fails_on_first_violation(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)
    env.script.add_ok("builder", summary="wrong")

    with pytest.raises(agents.GateFailure):
        agent_phase(run, "builder", retries=0, gates=[summary_fixed])

    assert len(env.script.calls) == 1


def test_invalid_json_inside_correction_stays_in_session(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)
    env.script.add(
        "builder",
        json.dumps(ok(summary="wrong")),
        "garbage",
        json.dumps(ok(summary="fixed")),
    )

    envelope = agent_phase(run, "builder", retries=1, gates=[summary_fixed])

    assert envelope.summary == "fixed"
    assert len(env.script.calls) == 3
    assert len({c.session_id for c in env.script.calls}) == 1


def test_reported_fail_status_fails_the_phase(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)
    env.script.add("builder", json.dumps({"status": "fail", "summary": "gave up"}))

    with pytest.raises(RuntimeError, match="reported status='fail'"):
        agent_phase(run, "builder")
