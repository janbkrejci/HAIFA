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


def test_failed_first_turn_keeps_its_session_for_a_joined_run(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)
    run.add_usage(10, 0.2)
    env.script.add("builder", *(["garbage"] * (agents.JSON_FIX_ATTEMPTS + 1)))
    with pytest.raises(RuntimeError):
        agent_phase(run, "builder")
    session_id = env.script.calls[0].session_id
    env.script.add_ok("builder")
    resumed = start(env)
    assert rows(env.db_path, "SELECT status, ended_at FROM sessions") == [("running", None)]
    resumed.add_usage(20, 0.3)
    agent_phase(resumed, "builder", prompt="## Continuation\nContinue the failed phase.")
    assert env.script.calls[-1].session_id == session_id
    assert rows(env.db_path, "SELECT total_tokens, total_cost FROM sessions") == [(30, 0.5)]


@pytest.mark.parametrize(
    "error", ["No conversation found with session ID", "no rollout found for thread"]
)
def test_missing_session_uses_the_continuation_in_a_fresh_session(
    engine_env: EngineEnv, error: str
) -> None:
    env = engine_env
    env.script.add_ok("builder")
    agent_phase(start(env), "builder")
    previous = env.script.calls[-1].session_id
    env.script.add_ok("builder")
    env.script.add_ok("builder")

    def missing_once(wt: object) -> None:
        raise RuntimeError(error)

    env.script.on("builder", missing_once)
    prompt = (
        "## Continuation\nRead context_handoff/ and the earlier phase outputs.\n"
        "## Retry note\nGo on."
    )
    agent_phase(start(env), "builder", prompt=prompt)
    assert env.script.calls[-2].session_id == previous
    assert env.script.calls[-1].session_id != previous
    assert prompt in env.script.calls[-1].prompt


def test_continuation_does_not_hide_provider_errors(engine_env: EngineEnv) -> None:
    env = engine_env
    env.script.add_ok("builder")

    def offline(wt: object) -> None:
        raise RuntimeError("provider unavailable")

    env.script.on("builder", offline)
    with pytest.raises(RuntimeError, match="provider unavailable"):
        agent_phase(start(env), "builder", prompt="## Continuation\nGo on.")
    assert len(env.script.calls) == 1
