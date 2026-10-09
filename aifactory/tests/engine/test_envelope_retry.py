"""An invalid envelope re-prompts the SAME agent session with a correction."""

from __future__ import annotations

import json

import pytest
from engine_fakes import EngineEnv, agent_phase, engine_env_fixture, ok, rows, start  # noqa: F401

from aifactory.engine import agents

FIX_PREFIX = "Your response was not valid JSON for the required structure"


def _envelopes(env: EngineEnv, phase_id: str) -> list[tuple[int, int]]:
    found = rows(
        env.db_path,
        "SELECT valid, attempt FROM envelopes WHERE phase_id=? ORDER BY rowid",
        phase_id,
    )
    return [(int(v), int(a)) for v, a in found]


@pytest.mark.parametrize("bad", ["not json at all", json.dumps({"status": "maybe"})])
def test_invalid_envelope_is_reprompted_in_same_session(engine_env: EngineEnv, bad: str) -> None:
    env = engine_env
    run = start(env)
    env.script.add("builder", bad, json.dumps(ok()))

    envelope = agent_phase(run, "builder")

    assert envelope.status == "success"
    calls = env.script.calls
    assert len(calls) == 2
    assert calls[0].session_id == calls[1].session_id
    assert calls[1].prompt.startswith(FIX_PREFIX)
    assert "status, summary, artifacts, notes_for_next_agent" in calls[1].prompt
    phase_id = f"{run.adw_id}_01_builder"
    assert _envelopes(env, phase_id) == [(0, 1), (1, 2)]


def test_fenced_json_parses_first_time(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)
    env.script.add("builder", "Here you go:\n```json\n" + json.dumps(ok()) + "\n```\n")

    agent_phase(run, "builder")

    assert len(env.script.calls) == 1


def test_retries_are_bounded(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)
    attempts = agents.JSON_FIX_ATTEMPTS + 1
    env.script.add("builder", *(["garbage"] * attempts))

    with pytest.raises(RuntimeError, match="never produced valid GenericOutput JSON"):
        agent_phase(run, "builder")

    assert len(env.script.calls) == attempts
    assert len({c.session_id for c in env.script.calls}) == 1
    phase_id = f"{run.adw_id}_01_builder"
    assert rows(env.db_path, "SELECT status FROM phases WHERE phase_id=?", phase_id) == [("fail",)]
