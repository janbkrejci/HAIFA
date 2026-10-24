"""The final code review requests missing tests directly from the builder."""

from __future__ import annotations

import json
import sys

from workflow_fakes import (
    EngineEnv,
    FakeCodeRunner,
    ok,
    plan_envelope,
    workflow_env_fixture,  # noqa: F401
)

from aifactory.workflow import DEFAULT_WORKFLOWS_DIR, load_workflow, run_workflow

MISSING = "tests/test_launcher.py: the launcher retries a failed browser start"


def test_missing_tests_go_directly_from_final_review_to_builder(workflow_env: EngineEnv) -> None:
    env = workflow_env
    tester = next(a for a in env.cfg.agents if a.name == "tester")
    env.cfg.agents.append(tester.model_copy(update={"name": "test-reviewer"}))
    env.script.add("builder", ok(summary="built"), ok(summary="wrote regression test"))
    first = plan_envelope()
    with_test = {
        **first,
        "checks": [
            *first["checks"],
            {"name": "launcher", "argv": [sys.executable, "-c", "print('launcher')"]},
        ],
    }
    env.script.add("tester", first, with_test)
    env.script.add(
        "reviewer",
        ok(approved=False, blocking=[MISSING]),
        ok(approved=True),
    )
    code = FakeCodeRunner([True, True])
    result = run_workflow(
        load_workflow(DEFAULT_WORKFLOWS_DIR / "build-test-review.yaml"),
        "do it",
        env.cfg,
        code=code,
    )
    assert result.accepted
    assert [c.agent for c in env.script.calls] == [
        "builder",
        "tester",
        "reviewer",
        "builder",
        "tester",
        "reviewer",
    ]
    assert MISSING in json.loads(env.script.calls[3].previous())["blocking"]
    assert [c.name for c in code.plans[-1].checks] == ["check", "launcher"]
    assert not any(
        name.startswith(("triage", "test_review", "test_fix")) for name, _, _ in result.phases
    )
