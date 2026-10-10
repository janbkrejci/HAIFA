"""`repeat` with `max`/`until` and `when` guards, run against fake harnesses.

`until` is evaluated after every body step; the loop ends the moment it holds.
In the last iteration the loop ends at the step `until` reads, so a last failing
test is not followed by `fix_3` and a last rejection not by `revise_2`.
"""

from __future__ import annotations

import json

from workflow_fakes import (
    EngineEnv,
    FakeCodeRunner,
    ok,
    plan_envelope,
    workflow,
    workflow_env_fixture,  # noqa: F401  (pytest fixture)
)

from aifactory.workflow import WorkflowRun, run_workflow

HEADER = "name: t\ndescription: A workflow written only to exercise the loops\n"

TEST_LOOP = (
    HEADER
    + """\
steps:
  - build
  - test_plan
  - repeat: {max: 3, until: test.passed}
    steps: [test, fix]
accept: test.passed
"""
)

REVIEW_LOOP = (
    HEADER
    + """\
steps:
  - build
  - test_plan
  - repeat: {max: 2, until: review.approved}
    steps: [review, revise]
  - test: {when: revise.ran}
  - commit:
      when: review.approved and test.passed
      description: Land the reviewed and tested change
accept: review.approved
"""
)

BUILD = ok(summary="built", changed_files=[], commit_message="Build it")
FIX = ok(summary="fixed", changed_files=[], commit_message="Fix it")
REVISE = ok(summary="revised", changed_files=[], commit_message="Revise it")
PLAN = plan_envelope()
APPROVE = ok(summary="looks right", approved=True)
REJECT = ok(summary="missing X", approved=False, blocking=["missing X"])


def _run(env: EngineEnv, text: str, tests: list[bool]) -> tuple[WorkflowRun, FakeCodeRunner]:
    code = FakeCodeRunner(tests)
    result = run_workflow(workflow(text), "do it", env.cfg, code=code)
    return result, code


def _phases(result: WorkflowRun) -> list[str]:
    return [name for name, _, _ in result.phases if name != "request"]


def _agents(env: EngineEnv) -> list[str]:
    return [call.agent for call in env.script.calls]


# ── test / fix ───────────────────────────────────────────────────────────────


def test_fix_repairs_the_suite(workflow_env: EngineEnv) -> None:
    workflow_env.script.add("builder", BUILD, FIX)
    workflow_env.script.add("tester", PLAN)
    result, code = _run(workflow_env, TEST_LOOP, [False, True])
    assert _phases(result) == ["build", "test_plan", "test_1", "fix_1", "test_2"]
    assert (result.exit_code, result.accepted) == (0, True)
    assert code.test_results == []
    assert [check.argv for plan in code.plans for check in plan.checks] == [["true"]] * 2
    fix_call = workflow_env.script.calls[2]
    previous = json.loads(fix_call.previous())
    assert previous["passed"] is False  # the fixer reads the failing suite
    assert previous["failures"] == ["test: failed"]


def test_green_suite_skips_fix(workflow_env: EngineEnv) -> None:
    workflow_env.script.add("builder", BUILD)
    workflow_env.script.add("tester", PLAN)
    result, _ = _run(workflow_env, TEST_LOOP, [True])
    assert _phases(result) == ["build", "test_plan", "test_1"]
    assert (result.exit_code, result.accepted) == (0, True)
    assert _agents(workflow_env) == ["builder", "tester"]  # never fix
    assert "fix" not in result.results


def test_max_runs_out_without_a_last_fix(workflow_env: EngineEnv) -> None:
    workflow_env.script.add("builder", BUILD, FIX, FIX)
    workflow_env.script.add("tester", PLAN)
    result, code = _run(workflow_env, TEST_LOOP, [False, False, False])
    assert _phases(result) == ["build", "test_plan", "test_1", "fix_1", "test_2", "fix_2", "test_3"]
    assert "fix_3" not in _phases(result)
    assert result.accepted is False
    assert result.exit_code != 0
    assert code.test_results == []
    assert workflow_env.script.queue["builder"] == []


# ── review / revise ──────────────────────────────────────────────────────────


def test_revision_is_approved(workflow_env: EngineEnv) -> None:
    workflow_env.script.add("builder", BUILD, REVISE)
    workflow_env.script.add("reviewer", REJECT, APPROVE)
    workflow_env.script.add("tester", PLAN)
    result, code = _run(workflow_env, REVIEW_LOOP, [True])
    assert _phases(result) == [
        "build",
        "test_plan",
        "review_1",
        "revise_1",
        "review_2",
        "test",
        "commit",
    ]
    assert (result.exit_code, result.accepted) == (0, True)
    revise_call, review_2_call = workflow_env.script.calls[3], workflow_env.script.calls[4]
    assert revise_call.agent == "builder"
    assert json.loads(revise_call.previous())["blocking"] == ["missing X"]
    assert json.loads(review_2_call.previous())["summary"] == "revised"
    assert code.commits == ["Revise it"]


def test_max_runs_out_without_a_last_revise(workflow_env: EngineEnv) -> None:
    workflow_env.script.add("builder", BUILD, REVISE)
    workflow_env.script.add("reviewer", REJECT, REJECT)
    workflow_env.script.add("tester", PLAN)
    result, code = _run(workflow_env, REVIEW_LOOP, [True])
    # revise_1 ran, so the guarded test runs; the commit needs an approval.
    assert _phases(result) == ["build", "test_plan", "review_1", "revise_1", "review_2", "test"]
    assert "revise_2" not in _phases(result)
    assert result.accepted is False
    assert result.exit_code != 0
    assert code.commits == []
    assert _agents(workflow_env) == ["builder", "tester", "reviewer", "builder", "reviewer"]


def test_first_approval_skips_revise_and_the_guarded_test(workflow_env: EngineEnv) -> None:
    workflow_env.script.add("builder", BUILD)
    workflow_env.script.add("reviewer", APPROVE)
    workflow_env.script.add("tester", PLAN)
    result, code = _run(workflow_env, REVIEW_LOOP, [])
    # `test: {when: revise.ran}` does not run, so `test.passed` is unset and
    # the commit guarded by it does not run either.
    assert _phases(result) == ["build", "test_plan", "review_1"]
    assert (result.exit_code, result.accepted) == (0, True)
    assert code.commits == []
    assert result.results.get("revise") is None


# ── when ─────────────────────────────────────────────────────────────────────


def test_when_on_a_whole_repeat(workflow_env: EngineEnv) -> None:
    text = (
        HEADER
        + """\
steps:
  - test_plan
  - test
  - repeat: {max: 2, until: test.passed, when: not test.passed}
    steps: [fix, test]
accept: test.passed
"""
    )
    workflow_env.script.add("tester", PLAN, PLAN)
    result, _ = _run(workflow_env, text, [True])
    assert _phases(result) == ["test_plan", "test"]
    assert _agents(workflow_env) == ["tester"]

    workflow_env.script.add("builder", FIX)
    again, _ = _run(workflow_env, text, [False, True])
    assert _phases(again) == ["test_plan", "test", "fix_1", "test_1"]
    assert again.accepted is True


def test_when_false_inside_the_body_counts_as_not_run(workflow_env: EngineEnv) -> None:
    text = (
        HEADER
        + """\
steps:
  - build
  - test_plan
  - repeat: {max: 2, until: test.passed}
    steps:
      - test
      - fix: {when: build.status == 'fail'}
accept: test.passed
"""
    )
    workflow_env.script.add("builder", BUILD)
    workflow_env.script.add("tester", PLAN)
    result, _ = _run(workflow_env, text, [False, True])
    assert _phases(result) == ["build", "test_plan", "test_1", "test_2"]
    assert result.accepted is True


def test_until_without_a_body_reference_runs_the_whole_last_round(
    workflow_env: EngineEnv,
) -> None:
    text = (
        HEADER
        + """\
steps:
  - build
  - test_plan
  - repeat: {max: 2, until: build.status == 'fail'}
    steps: [test, fix]
"""
    )
    workflow_env.script.add("builder", BUILD, FIX, FIX)
    workflow_env.script.add("tester", PLAN)
    result, _ = _run(workflow_env, text, [False, False])
    assert _phases(result) == ["build", "test_plan", "test_1", "fix_1", "test_2", "fix_2"]
    assert result.accepted is True  # no accept: the run is accepted


def test_loop_without_until_runs_max_times(workflow_env: EngineEnv) -> None:
    text = (
        HEADER
        + """\
steps:
  - test_plan
  - repeat: {max: 3}
    steps: [test]
"""
    )
    workflow_env.script.add("tester", PLAN)
    result, _ = _run(workflow_env, text, [True, True, True])
    assert _phases(result) == ["test_plan", "test_1", "test_2", "test_3"]
