"""A test review that requires tests the repo lacks goes to the builder, not to a failed run."""

from __future__ import annotations

import json
import sys
from typing import Any

import pytest
from workflow_fakes import (
    EngineEnv,
    FakeCodeRunner,
    ok,
    plan_envelope,
    workflow,
    workflow_env_fixture,  # noqa: F401  (pytest fixture)
)

from aifactory.workflow import run_workflow

TEXT = """\
name: t
description: Build, plan the tests, run them, review
steps:
  - build
  - test_plan
  - test
  - review
accept: review.approved
"""
MISSING = "tests/test_launcher.py: the launcher retries a failed browser start"
REJECT = ok(summary="no launcher test", approved=False, blocking=[f"missing test {MISSING}"])
APPROVE = ok(summary="plan fits", approved=True)
FIRST = plan_envelope()
# The revision keeps the existing check and names the test the builder must write.
WANTS_TEST = {**plan_envelope(), "missing_tests": [MISSING]}
# The plan after the builder wrote the test: the old check plus the new test.
WITH_TEST = ok(
    coverage="scoped",
    reason="adds the new launcher test",
    checks=[
        *FIRST["checks"],
        {"name": "launcher", "argv": [sys.executable, "-c", "print('launcher')"]},
    ],
)


@pytest.fixture(name="env")
def env_fixture(workflow_env: EngineEnv) -> EngineEnv:
    """The engine env with the test reviewer in the roster, so every plan is reviewed."""
    tester = next(a for a in workflow_env.cfg.agents if a.name == "tester")
    workflow_env.cfg.agents.append(tester.model_copy(update={"name": "test-reviewer"}))
    return workflow_env


def _names(result: Any) -> list[str]:
    return [name for name, _, _ in result.phases if name != "request"]


def test_missing_tests_go_to_the_builder_and_the_run_reaches_review(env: EngineEnv) -> None:
    env.script.add("builder", ok(summary="built", changed_files=[]))
    env.script.add("builder", ok(summary="wrote the test", changed_files=["test_launcher.py"]))
    env.script.on("builder", lambda root: None, lambda root: (root / "test_launcher.py").touch())
    env.script.add("tester", FIRST, WANTS_TEST, WITH_TEST)
    env.script.add("test-reviewer", REJECT, APPROVE)
    env.script.add("reviewer", ok(summary="looks right", approved=True))
    code = FakeCodeRunner([True])
    result = run_workflow(workflow(TEXT), "do it", env.cfg, code=code)

    assert result.accepted
    assert _names(result) == [
        "build",
        "test_plan",
        "test_review",
        "plan_revision",
        "test_fix",
        "plan_revision_2",
        "test_review_2",
        "test",
        "review",
    ]
    calls = env.script.calls
    fix = calls[4]
    assert fix.agent == "builder"
    assert MISSING in json.loads(fix.previous())["blocking"][0]  # the review's findings
    replan = calls[5]
    assert replan.agent == "tester"
    assert json.loads(replan.previous())["summary"] == "wrote the test"
    # The test step ran the plan that includes the new test.
    assert [c.name for c in code.plans[0].checks] == ["check", "launcher"]
    assert result.results["test_plan"]["missing_tests"] == []


def test_missing_test_rounds_are_capped(env: EngineEnv) -> None:
    env.script.add("builder", *[ok(summary="built", changed_files=[])] * 3)
    env.script.add("tester", FIRST, WANTS_TEST, FIRST, WANTS_TEST, FIRST, WANTS_TEST)
    env.script.add("test-reviewer", REJECT, REJECT, REJECT)
    with pytest.raises(RuntimeError, match="after 2 builder rounds"):
        run_workflow(workflow(TEXT), "do it", env.cfg, code=FakeCodeRunner([]))
    assert [c.agent for c in env.script.calls].count("builder") == 3  # build + 2 rounds


def test_a_plan_that_cannot_be_made_still_fails(env: EngineEnv) -> None:
    env.script.add("builder", ok(summary="built", changed_files=[]))
    env.script.add("tester", FIRST, {**FIRST, "status": "fail", "summary": "no runner"})
    env.script.add("test-reviewer", REJECT)
    with pytest.raises(RuntimeError, match="no runner"):
        run_workflow(workflow(TEXT), "do it", env.cfg, code=FakeCodeRunner([]))
    assert [c.agent for c in env.script.calls] == ["builder", "tester", "test-reviewer", "tester"]
