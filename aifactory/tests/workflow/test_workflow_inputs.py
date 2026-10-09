"""A step with several inputs: review gets the builder's envelope and the last test result.

Also: a run reports, before any agent runs, the agents whose harness cannot
enforce their ``disallowed_commands``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from workflow_fakes import (
    PREV_END,
    PREV_START,
    Call,
    EngineEnv,
    FakeCodeRunner,
    ok,
    workflow,
    workflow_env_fixture,  # noqa: F401  (pytest fixture)
)

from aifactory.engine import data_types as dt
from aifactory.engine.role_registry import load_roles
from aifactory.workflow import RoleStep, WorkflowError, parse_workflow, run_workflow

HEADER = "name: t\ndescription: A workflow written only to exercise step inputs\n"
TEST_START = "TEST<<"
TEST_END = ">>TEST"

BUILD = ok(summary="built", changed_files=[], commit_message="Build it")
FIX = ok(summary="fixed", changed_files=[], commit_message="Fix it")
APPROVE = ok(summary="looks right", approved=True)

LOOP = (
    HEADER
    + """\
steps:
  - build
  - repeat: {max: 2, until: test.passed}
    steps: [test, fix]
  - review:
      input: [build, fix]
accept: review.approved
"""
)

MAPPED = (
    HEADER
    + """\
steps:
  - build
  - test
  - review:
      input:
        previous_envelope: [build]
        suite: test
accept: review.approved
"""
)


class LoggedTests(FakeCodeRunner):
    """Test steps that ran a real-looking command and wrote a log."""

    def test(self, run: Any) -> Any:
        passed = self.test_results.pop(0)
        check = dt.QualityCheckResult(
            name="test",
            area="backend",
            operation="build",
            command="just check-scoped",
            returncode=0 if passed else 1,
            passed=passed,
            duration_seconds=1.0,
            output_artifact="/data/quality/test.log",
        )
        failures = [] if passed else ["test: failed"]
        return dt.QualityResult(
            passed=passed, checks=[check], failures=failures, artifacts=[check.output_artifact]
        )


def _between(text: str, start: str, end: str) -> str:
    begin = text.index(start) + len(start)
    return text[begin : text.index(end)]


def _with_variables(env: EngineEnv, tmp_path: Path, *names: str) -> None:
    """The reviewer's user prompt also shows ``{{test_result}}`` (and ``names``)."""
    user = tmp_path / "reviewer_user.md"
    parts = [f"{{{{prompt}}}}\n{PREV_START}{{{{previous_envelope}}}}{PREV_END}\n"]
    parts.append(f"{TEST_START}{{{{test_result}}}}{TEST_END}\n")
    parts += [f"{name.upper()}<<{{{{{name}}}}}>>{name.upper()}\n" for name in names]
    user.write_text("".join(parts), encoding="utf-8", newline="\n")
    for agent in env.cfg.agents:
        if agent.name == "reviewer":
            agent.prompt_engineering.user = str(user)


def _call(env: EngineEnv, agent: str) -> Call:
    return next(call for call in env.script.calls if call.agent == agent)


def test_review_gets_builder_envelope_and_test_result(
    workflow_env: EngineEnv, tmp_path: Path
) -> None:
    _with_variables(workflow_env, tmp_path)
    workflow_env.script.add("builder", BUILD, FIX)
    workflow_env.script.add("reviewer", APPROVE)
    code = LoggedTests([False, True])
    result = run_workflow(workflow(LOOP), "do it", workflow_env.cfg, code=code)
    assert result.accepted
    review = _call(workflow_env, "reviewer")
    # previous_envelope: the latest of build/fix, never the test report
    assert json.loads(review.previous())["summary"] == "fixed"
    report = json.loads(_between(review.prompt, TEST_START, TEST_END))
    assert report == {
        "step": "test",
        "phase": "test_2",
        "passed": True,
        "command": "just check-scoped",
        "log": "/data/quality/test.log",
        "failures": 0,
        "code_changed_since": False,
    }


def test_test_result_says_when_code_changed_after_it(
    workflow_env: EngineEnv, tmp_path: Path
) -> None:
    text = HEADER + "steps:\n  - test\n  - build\n  - review\naccept: review.approved\n"
    _with_variables(workflow_env, tmp_path)
    workflow_env.script.add("builder", BUILD)
    workflow_env.script.add("reviewer", APPROVE)
    run_workflow(workflow(text), "do it", workflow_env.cfg, code=LoggedTests([False]))
    review = _call(workflow_env, "reviewer")
    report = json.loads(_between(review.prompt, TEST_START, TEST_END))
    assert report["passed"] is False
    assert report["code_changed_since"] is True


def test_test_result_before_any_test_is_none(workflow_env: EngineEnv, tmp_path: Path) -> None:
    text = HEADER + "steps:\n  - build\n  - review\naccept: review.approved\n"
    _with_variables(workflow_env, tmp_path)
    workflow_env.script.add("builder", BUILD)
    workflow_env.script.add("reviewer", APPROVE)
    run_workflow(workflow(text), "do it", workflow_env.cfg, code=FakeCodeRunner([]))
    review = _call(workflow_env, "reviewer")
    assert _between(review.prompt, TEST_START, TEST_END) == "(none)"


def test_input_mapping_adds_a_template_variable(workflow_env: EngineEnv, tmp_path: Path) -> None:
    _with_variables(workflow_env, tmp_path, "suite")
    workflow_env.script.add("builder", BUILD)
    workflow_env.script.add("reviewer", APPROVE)
    run_workflow(workflow(MAPPED), "do it", workflow_env.cfg, code=LoggedTests([True]))
    review = _call(workflow_env, "reviewer")
    assert json.loads(review.previous())["summary"] == "built"
    suite = json.loads(_between(review.prompt, "SUITE<<", ">>SUITE"))
    assert (suite["passed"], suite["command"]) == (True, "just check-scoped")


def test_parse_input_mapping() -> None:
    wf = workflow(MAPPED)
    review = wf.steps[2]
    assert isinstance(review, RoleStep)
    assert review.inputs == ("build",)
    assert review.variables == (("suite", ("test",)),)


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("{prompt: [build]}", "invalid_input"),
        ("{context_handoff_dir: build}", "invalid_input"),
        ("{Bad-Name: build}", "invalid_input"),
        ("{suite: 3}", "invalid_input"),
        ("{suite: nosuchstep}", "unknown_ref"),
    ],
)
def test_parse_input_mapping_errors(value: str, code: str) -> None:
    import yaml

    text = HEADER + f"steps:\n  - build\n  - review:\n      input: {value}\n"
    with pytest.raises(WorkflowError) as exc:
        parse_workflow(yaml.safe_load(text), load_roles())
    assert code in [issue.code for issue in exc.value.issues]


def test_run_reports_unenforced_disallowed_commands(workflow_env: EngineEnv) -> None:
    for index, agent in enumerate(workflow_env.cfg.agents):
        if agent.name == "builder":
            workflow_env.cfg.agents[index] = agent.model_copy(
                update={"disallowed_commands": ["just test"]}
            )
    text = (
        HEADER + "steps:\n  - build:\n      harness: codex\n  - review\naccept: review.approved\n"
    )
    workflow_env.script.add("builder", BUILD)
    workflow_env.script.add("reviewer", APPROVE)
    result = run_workflow(workflow(text), "do it", workflow_env.cfg, code=FakeCodeRunner([]))
    assert len(result.warnings) == 1
    assert "'builder'" in result.warnings[0] and "codex" in result.warnings[0]
    assert [call.harness for call in workflow_env.script.calls] == ["codex", "claude"]


def test_claude_run_has_nothing_to_report(workflow_env: EngineEnv) -> None:
    for index, agent in enumerate(workflow_env.cfg.agents):
        workflow_env.cfg.agents[index] = agent.model_copy(
            update={"disallowed_commands": ["just test"]}
        )
    text = HEADER + "steps:\n  - build\naccept: build.ran\n"
    workflow_env.script.add("builder", BUILD)
    result = run_workflow(workflow(text), "do it", workflow_env.cfg, code=FakeCodeRunner([]))
    assert result.warnings == []


@pytest.mark.parametrize("coverage", ["scoped", "none", "deferred"])
def test_review_receives_adaptive_policy_evidence(
    workflow_env: EngineEnv, tmp_path: Path, coverage: str
) -> None:
    from aifactory.testing.model import Evidence

    evidence = Evidence.model_validate(
        {
            "coverage": coverage,
            "reason": "Explicit workflow policy",
            "executed": 1 if coverage == "scoped" else 0,
            "defer_to": "M01-S01-T99" if coverage == "deferred" else None,
        }
    )

    class AdaptiveTests(LoggedTests):
        def test(self, run: Any) -> dt.QualityResult:
            result: dt.QualityResult = super().test(run)
            result.test_plan = evidence
            if evidence.executed == 0:
                result.checks = []
                result.artifacts = []
            return result

    _with_variables(workflow_env, tmp_path)
    workflow_env.script.add("builder", BUILD)
    workflow_env.script.add("reviewer", APPROVE)
    result = run_workflow(workflow(LOOP), "do it", workflow_env.cfg, code=AdaptiveTests([True]))
    assert result.accepted
    review = _call(workflow_env, "reviewer")
    assert json.loads(review.previous())["summary"] == "built"
    report = json.loads(_between(review.prompt, TEST_START, TEST_END))
    assert report["test_plan"] == evidence.model_dump()
    if evidence.executed == 0:
        assert report["command"] is None
        assert report["log"] is None
