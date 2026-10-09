"""A role step may run on another roster agent and keep the role's output type and gates."""

from __future__ import annotations

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

HEADER = "name: step-agent\ndescription: A build step that runs on another roster agent\n"

PLAN = ok(summary="planned", commit_message="Add the plan")
BUILD = ok(summary="built", changed_files=[], commit_message="Build it")


def test_step_runs_on_its_agent(workflow_env: EngineEnv) -> None:
    workflow_env.script.add("planner", PLAN)
    workflow_env.script.add("scout", BUILD)
    wf = workflow(HEADER + "steps:\n  - plan\n  - build: {agent: scout}\n")
    result = run_workflow(wf, "do it", workflow_env.cfg, code=FakeCodeRunner([]))
    assert result.exit_code == 0
    assert [c.agent for c in workflow_env.script.calls] == ["planner", "scout"]
    assert [(r.phase, r.owner) for r in result.records] == [
        ("plan", "planner"),
        ("build", "scout"),
    ]
    assert isinstance(result.envelopes["build"], dt.BuildOutput)


def test_step_agent_with_override(workflow_env: EngineEnv) -> None:
    workflow_env.script.add("planner", PLAN)
    workflow_env.script.add("scout", BUILD)
    wf = workflow(
        HEADER + "steps:\n  - plan\n  - build: {agent: scout, harness: codex, model: gpt-5.5}\n"
    )
    result = run_workflow(wf, "do it", workflow_env.cfg, code=FakeCodeRunner([]))
    assert result.exit_code == 0
    calls = [(c.harness, c.agent, c.model) for c in workflow_env.script.calls]
    assert calls[1] == ("codex", "scout", "gpt-5.5")


def test_unknown_step_agent_fails_preflight(workflow_env: EngineEnv) -> None:
    wf = workflow(HEADER + "steps:\n  - plan\n  - build: {agent: ghost}\n")
    with pytest.raises(WorkflowError) as exc:
        run_workflow(wf, "do it", workflow_env.cfg, code=FakeCodeRunner([]))
    assert [(i.code, i.path) for i in exc.value.issues] == [
        ("unknown_agent", "steps[1].build.agent")
    ]
    assert "'ghost'" in exc.value.issues[0].message
    assert workflow_env.script.calls == []
