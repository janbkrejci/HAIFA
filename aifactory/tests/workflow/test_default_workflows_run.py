"""Each packaged workflow runs the phases of the Python ADW of the same name.

Phase orders come from the ``Phases:`` docstrings and loops in ``adws/adw_*.py``.
Loops follow 2.7: the last round ends at the step ``until`` reads, so a last
rejection is not followed by ``revise_2`` and a last red suite not by ``fix_3``.
"""

from __future__ import annotations

import json
from typing import Any

from workflow_fakes import (  # noqa: F401
    EngineEnv,
    FakeCodeRunner,
    ok,
    plan_envelope,
    workflow_env_fixture,
)

from aifactory.workflow import DEFAULT_WORKFLOWS_DIR, WorkflowRun, load_workflow, run_workflow

REQUEST = ("request", "engineer")
PLAN_PHASE = ("plan", "agent", "planner")
BUILD_PHASE = ("build", "agent", "builder")
TEST_PLAN_PHASE = ("test_plan", "agent", "tester")
COMMIT = ("commit", "code", "git")
HEAD = [REQUEST, PLAN_PHASE, ("commit_plan", "code", "git"), BUILD_PHASE, TEST_PLAN_PHASE]
TAIL = [
    ("commit_build", "code", "git"),
    ("changes", "code", "git"),
    ("document", "agent", "documenter"),
    ("commit_docs", "code", "git"),
]

PLAN = ok(summary="planned", commit_message="Add the plan")
BUILD = ok(summary="built", commit_message="Build the feature")
FIX = ok(summary="fixed", commit_message="Fix the failing test")
REVISE = ok(summary="revised", commit_message="Close review findings")
APPROVE = ok(summary="looks right", approved=True)
REJECT = ok(summary="missing X", approved=False, blocking=["missing X"])
DOCUMENT = ok(summary="documented", commit_message="Document the feature")
SCOUT = ok(summary="found it")
TEST_PLAN = plan_envelope()
# Keeps the first plan's check (gate plan_keeps_checks) and adds one.
REPLAN = ok(
    coverage="scoped",
    reason="the revision touched more",
    checks=[{"name": "check", "argv": ["true"]}, {"name": "more", "argv": ["echo", "more"]}],
)


def _test(i: int) -> tuple[str, str, str]:
    return (f"test_{i}", "code", "quality")


def _fix(i: int) -> tuple[str, str, str]:
    return (f"fix_{i}", "agent", "builder")


def _review(i: int) -> tuple[str, str, str]:
    return (f"review_{i}", "agent", "reviewer")


def _revise(i: int) -> tuple[str, str, str]:
    return (f"revise_{i}", "agent", "builder")


def _replan(i: int, name: str = "test_plan") -> tuple[str, str, str]:
    return (f"{name}_{i}", "agent", "tester")


def _retest(i: int) -> tuple[str, str, str]:
    return (f"retest_{i}", "code", "quality")


def _run(
    env: EngineEnv, name: str, tests: list[bool], prompt: str = "add a /health endpoint"
) -> tuple[WorkflowRun, FakeCodeRunner]:
    code = FakeCodeRunner(tests)
    workflow = load_workflow(DEFAULT_WORKFLOWS_DIR / f"{name}.yaml")
    result = run_workflow(workflow, prompt, env.cfg, code=code)
    return result, code


def _phases(result: WorkflowRun) -> list[tuple[str, ...]]:
    """(name, kind, owner), except the engineer's name, which depends on the machine."""
    return [p[:2] if p[1] == "engineer" else p for p in result.phases]


def _script(env: EngineEnv, **agents: list[dict[str, Any]]) -> None:
    for agent, envelopes in agents.items():
        env.script.add(agent, *envelopes)


def _assert_done(env: EngineEnv, code: FakeCodeRunner) -> None:
    """Every scripted envelope and test result was consumed."""
    assert code.test_results == []
    assert all(not queue for queue in env.script.queue.values())


# ── single-pass workflows ─────────────────────────────────────────────────


def test_plan(workflow_env: EngineEnv) -> None:
    _script(workflow_env, planner=[PLAN])
    result, code = _run(workflow_env, "plan", [])
    assert _phases(result) == [REQUEST, PLAN_PHASE]
    assert (result.exit_code, result.accepted) == (0, True)
    assert code.commits == []
    _assert_done(workflow_env, code)


def test_scout(workflow_env: EngineEnv) -> None:
    _script(workflow_env, scout=[SCOUT])
    result, code = _run(workflow_env, "scout", [])
    assert _phases(result) == [REQUEST, ("scout", "agent", "scout")]
    assert (result.exit_code, result.accepted) == (0, True)
    assert code.commits == []
    _assert_done(workflow_env, code)


def test_plan_build(workflow_env: EngineEnv) -> None:
    _script(workflow_env, planner=[PLAN], builder=[BUILD])
    result, code = _run(workflow_env, "plan-build", [])
    assert _phases(result) == [REQUEST, PLAN_PHASE, BUILD_PHASE, COMMIT]
    assert (result.exit_code, result.accepted) == (0, True)
    assert code.commits == ["Build the feature"]
    _assert_done(workflow_env, code)


def test_document(workflow_env: EngineEnv) -> None:
    _script(workflow_env, documenter=[DOCUMENT])
    result, code = _run(workflow_env, "document", [])
    assert _phases(result) == [
        REQUEST,
        ("changes", "code", "git"),
        ("document", "agent", "documenter"),
    ]
    assert (result.exit_code, result.accepted) == (0, True)
    assert code.commits == []
    _assert_done(workflow_env, code)


# ── plan-build-test ───────────────────────────────────────────────────────


def test_plan_build_test_green_first_time(workflow_env: EngineEnv) -> None:
    _script(workflow_env, planner=[PLAN], builder=[BUILD], tester=[TEST_PLAN])
    result, code = _run(workflow_env, "plan-build-test", [True])
    assert _phases(result) == [
        REQUEST,
        PLAN_PHASE,
        BUILD_PHASE,
        TEST_PLAN_PHASE,
        _test(1),
        COMMIT,
    ]
    assert (result.exit_code, result.accepted) == (0, True)
    assert code.commits == ["Build the feature"]
    _assert_done(workflow_env, code)


def test_plan_build_test_fixed_once(workflow_env: EngineEnv) -> None:
    _script(workflow_env, planner=[PLAN], builder=[BUILD, FIX], tester=[TEST_PLAN, TEST_PLAN])
    result, code = _run(workflow_env, "plan-build-test", [False, True])
    assert _phases(result) == [
        REQUEST,
        PLAN_PHASE,
        BUILD_PHASE,
        TEST_PLAN_PHASE,
        _test(1),
        _fix(1),
        _replan(1),
        _test(2),
        COMMIT,
    ]
    assert (result.exit_code, result.accepted) == (0, True)
    assert code.commits == ["Fix the failing test"]
    _assert_done(workflow_env, code)


def test_plan_build_test_never_green(workflow_env: EngineEnv) -> None:
    # Deliberate difference from adw_plan_build_test.py (2.7): the last red suite
    # is not followed by fix_3. Either way nothing is committed.
    _script(
        workflow_env,
        planner=[PLAN],
        builder=[BUILD, FIX, FIX],
        tester=[TEST_PLAN, TEST_PLAN, TEST_PLAN],
    )
    result, code = _run(workflow_env, "plan-build-test", [False, False, False])
    assert _phases(result) == [
        REQUEST,
        PLAN_PHASE,
        BUILD_PHASE,
        TEST_PLAN_PHASE,
        _test(1),
        _fix(1),
        _replan(1),
        _test(2),
        _fix(2),
        _replan(2),
        _test(3),
    ]
    assert (result.exit_code, result.accepted) == (1, False)
    assert code.commits == []
    _assert_done(workflow_env, code)


# ── simple-sdlc ───────────────────────────────────────────────────────────


def _assert_agent_defaults(env: EngineEnv) -> None:
    assert env.script.calls
    for call in env.script.calls:
        assert (call.harness, call.model, call.thinking) == ("claude", "sonnet", "medium")


def test_simple_sdlc_everything_passes(workflow_env: EngineEnv) -> None:
    _script(
        workflow_env,
        planner=[PLAN],
        builder=[BUILD],
        tester=[TEST_PLAN],
        reviewer=[APPROVE],
        documenter=[DOCUMENT],
    )
    result, code = _run(workflow_env, "simple-sdlc", [True])
    assert _phases(result) == [*HEAD, _test(1), _review(1), *TAIL]
    assert (result.exit_code, result.accepted) == (0, True)
    assert code.commits == ["Add the plan", "Build the feature", "Document the feature"]
    _assert_agent_defaults(workflow_env)
    _assert_done(workflow_env, code)


def test_simple_sdlc_tests_fail_once(workflow_env: EngineEnv) -> None:
    _script(
        workflow_env,
        planner=[PLAN],
        builder=[BUILD, FIX],
        tester=[TEST_PLAN, TEST_PLAN],
        reviewer=[APPROVE],
        documenter=[DOCUMENT],
    )
    result, code = _run(workflow_env, "simple-sdlc", [False, True])
    assert _phases(result) == [
        *HEAD,
        _test(1),
        _fix(1),
        _replan(1),
        _test(2),
        _review(1),
        *TAIL,
    ]
    assert (result.exit_code, result.accepted) == (0, True)
    fix_call = workflow_env.script.calls[3]
    assert fix_call.agent == "builder"
    assert '"passed": false' in fix_call.previous()  # the fixer reads the failing suite
    review_call = workflow_env.script.calls[5]
    assert review_call.agent == "reviewer"
    assert "fixed" in review_call.previous()  # the reviewer reads the latest code
    assert code.commits[1] == "Fix the failing test"
    _assert_agent_defaults(workflow_env)
    _assert_done(workflow_env, code)


def test_simple_sdlc_review_rejects_once(workflow_env: EngineEnv) -> None:
    _script(
        workflow_env,
        planner=[PLAN],
        builder=[BUILD, REVISE],
        tester=[TEST_PLAN, REPLAN],
        reviewer=[REJECT, APPROVE],
        documenter=[DOCUMENT],
    )
    result, code = _run(workflow_env, "simple-sdlc", [True, True])
    # The revision is replanned and retested before the second review sees it.
    assert _phases(result) == [
        *HEAD,
        _test(1),
        _review(1),
        _revise(1),
        _replan(1, "replan"),
        _retest(1),
        _review(2),
        *TAIL,
    ]
    assert (result.exit_code, result.accepted) == (0, True)
    calls = workflow_env.script.calls
    assert [c.agent for c in calls[3:7]] == ["reviewer", "builder", "tester", "reviewer"]
    assert "missing X" in calls[4].previous()
    # The replan reads the review (input: [review]), not the revision.
    assert json.loads(calls[5].previous())["blocking"] == ["missing X"]
    assert "revised" in calls[6].previous()
    # The retest runs the replanned checks, not the first plan.
    assert [[c.name for c in plan.checks] for plan in code.plans] == [
        ["check"],
        ["check", "more"],
    ]
    assert code.commits == ["Add the plan", "Close review findings", "Document the feature"]
    _assert_agent_defaults(workflow_env)
    _assert_done(workflow_env, code)


def test_simple_sdlc_review_rejects_twice(workflow_env: EngineEnv) -> None:
    # As in adw_simple_sdlc.py: after the last rejection there is no revise_2;
    # only the plan is committed.
    _script(
        workflow_env,
        planner=[PLAN],
        builder=[BUILD, REVISE],
        tester=[TEST_PLAN, TEST_PLAN],
        reviewer=[REJECT, REJECT],
    )
    result, code = _run(workflow_env, "simple-sdlc", [True, True])
    assert _phases(result) == [
        *HEAD,
        _test(1),
        _review(1),
        _revise(1),
        _replan(1, "replan"),
        _retest(1),
        _review(2),
    ]
    assert _revise(2) not in _phases(result)
    assert (result.exit_code, result.accepted) == (1, False)
    assert code.commits == ["Add the plan"]
    assert [c.agent for c in workflow_env.script.calls].count("builder") == 2
    _assert_done(workflow_env, code)


def test_simple_sdlc_tests_never_pass(workflow_env: EngineEnv) -> None:
    # Deliberate difference from adw_simple_sdlc.py (2.7): the last red suite is
    # not followed by fix_3. The review still runs, as in the Python ADW.
    _script(
        workflow_env,
        planner=[PLAN],
        builder=[BUILD, FIX, FIX],
        tester=[TEST_PLAN, TEST_PLAN, TEST_PLAN],
        reviewer=[APPROVE],
    )
    result, code = _run(workflow_env, "simple-sdlc", [False, False, False])
    assert _phases(result) == [
        *HEAD,
        _test(1),
        _fix(1),
        _replan(1),
        _test(2),
        _fix(2),
        _replan(2),
        _test(3),
        _review(1),
    ]
    assert (result.exit_code, result.accepted) == (1, False)
    assert code.commits == ["Add the plan"]
    _assert_done(workflow_env, code)
