"""Each step runs on its own harness and model; the envelope crosses harnesses unchanged."""

from __future__ import annotations

import json

import pytest
from workflow_fakes import (
    EngineEnv,
    FakeCodeRunner,
    ok,
    workflow,
    workflow_env_fixture,  # noqa: F401  (pytest fixture)
)

from aifactory.engine import data_types as dt
from aifactory.workflow import WorkflowError, run_workflow

MIXED = """\
name: mixed-harness
description: One run spread over three harnesses to prove each step picks its own
steps:
  - plan: {harness: claude, model: opus, thinking: high}
  - build: {harness: codex, model: gpt-5.5}
  - review: {harness: pi, model: google/gemini-3.6-flash, thinking: low}
accept: review.approved
"""

PLAN = ok(summary="planned", commit_message="Add the plan", notes_for_next_agent="ünïcode — ok")
BUILD = ok(summary="built", changed_files=[], commit_message="Build it")
REVIEW = ok(summary="approved", approved=True)


def _script(env: EngineEnv) -> None:
    env.script.add("planner", PLAN)
    env.script.add("builder", BUILD)
    env.script.add("reviewer", REVIEW)


def _defaults(env: EngineEnv) -> list[tuple[str, str, str | None]]:
    return [(str(a.coding_agent), a.model, a.thinking) for a in env.cfg.agents]


def test_each_step_gets_its_harness_and_model(workflow_env: EngineEnv) -> None:
    _script(workflow_env)
    result = run_workflow(workflow(MIXED), "do it", workflow_env.cfg, code=FakeCodeRunner([]))
    assert (result.exit_code, result.accepted) == (0, True)
    calls = [(c.harness, c.agent, c.model, c.thinking) for c in workflow_env.script.calls]
    assert calls == [
        ("claude", "planner", "opus", "high"),
        ("codex", "builder", "gpt-5.5", "medium"),  # thinking not overridden: agent default
        ("pi", "reviewer", "google/gemini-3.6-flash", "low"),
    ]
    records = [(r.phase, r.harness, r.model, r.thinking) for r in result.records]
    assert records == [
        ("plan", "claude", "opus", "high"),
        ("build", "codex", "gpt-5.5", "medium"),
        ("review", "pi", "google/gemini-3.6-flash", "low"),
    ]


def test_envelope_crosses_harnesses_unchanged(workflow_env: EngineEnv) -> None:
    _script(workflow_env)
    result = run_workflow(workflow(MIXED), "do it", workflow_env.cfg, code=FakeCodeRunner([]))
    _, codex_call, pi_call = workflow_env.script.calls
    assert codex_call.previous() == result.envelopes["plan"].model_dump_json(indent=2)
    assert pi_call.previous() == result.envelopes["build"].model_dump_json(indent=2)
    received = dt.PlanOutput.model_validate_json(codex_call.previous())
    assert received == dt.PlanOutput.model_validate(PLAN)
    assert json.loads(pi_call.previous())["commit_message"] == "Build it"


def test_agents_are_restored_after_the_run(workflow_env: EngineEnv) -> None:
    before = _defaults(workflow_env)
    _script(workflow_env)
    run_workflow(workflow(MIXED), "do it", workflow_env.cfg, code=FakeCodeRunner([]))
    assert _defaults(workflow_env) == before
    assert set(before) == {("claude", "sonnet", "medium")}


def test_preflight_rejects_a_model_before_anything_runs(workflow_env: EngineEnv) -> None:
    _script(workflow_env)
    workflow_env.fakes["codex"].reject_models = True
    with pytest.raises(WorkflowError) as exc:
        run_workflow(workflow(MIXED), "do it", workflow_env.cfg, code=FakeCodeRunner([]))
    assert [(i.code, i.path) for i in exc.value.issues] == [("invalid_agent", "steps[1].build")]
    assert "gpt-5.5" in exc.value.issues[0].message
    assert workflow_env.script.calls == []


def test_preflight_rejects_an_agent_missing_from_the_roster(workflow_env: EngineEnv) -> None:
    workflow_env.cfg.agents = [a for a in workflow_env.cfg.agents if a.name != "reviewer"]
    _script(workflow_env)
    with pytest.raises(WorkflowError) as exc:
        run_workflow(workflow(MIXED), "do it", workflow_env.cfg, code=FakeCodeRunner([]))
    assert [(i.code, i.path) for i in exc.value.issues] == [("unknown_agent", "steps[2].review")]
    assert workflow_env.script.calls == []
