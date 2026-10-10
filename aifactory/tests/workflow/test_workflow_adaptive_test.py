"""The tester's plan and the `test` step that runs it: real check processes, no live agents."""

from __future__ import annotations

import json
import shlex
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from pydantic import ValidationError
from workflow_fakes import (
    EngineEnv,
    FakeCodeRunner,
    ok,
    plan_envelope,
    triage_envelope,
    workflow,
    workflow_env_fixture,  # noqa: F401  (pytest fixture)
)

from aifactory.engine import gates
from aifactory.engine.data_types import TestPlanOutput
from aifactory.testing.executor import execute
from aifactory.workflow import run_workflow

HEADER = "name: t\ndescription: A workflow written only to exercise the test plan\n"


def fake_run(tmp_path: Path, timeout: int = 4) -> Any:
    """The attributes of a task run that the executor and the quality runner read."""
    return SimpleNamespace(
        repo_root=tmp_path,
        context_handoff_dir=tmp_path.parent / (tmp_path.name + "-logs"),
        phases=[SimpleNamespace(seq=1, phase_id="test")],
        adw_id="test",
        console=SimpleNamespace(note=lambda msg: None),
        tracer=SimpleNamespace(event=lambda event: None),
        test_timeout=timeout,
    )


def python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def plan(*codes: str, coverage: str = "scoped") -> TestPlanOutput:
    """A plan with one Python check per code snippet, named check0, check1, ..."""
    return TestPlanOutput.model_validate(
        ok(
            coverage=coverage,
            reason="covers the change",
            checks=[{"name": f"check{i}", "argv": python(code)} for i, code in enumerate(codes)],
        )
    )


def touch(name: str) -> str:
    return f"from pathlib import Path; Path({name!r}).touch()"


class Slots:
    def __init__(self) -> None:
        self.count = 0

    @contextmanager
    def hold(self, waiting: Any) -> Iterator[SimpleNamespace]:
        self.count += 1
        yield SimpleNamespace(slot=0, waited_seconds=0.0)


# ── executor ────────────────────────────────────────────────────────────────


def test_checks_run_in_order_in_the_worktree_under_one_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    run = fake_run(tmp_path)
    run.test_slots = Slots()
    order = "from pathlib import Path; p = Path('order'); p.write_text(p.read_text() + '{}')"
    (tmp_path / "order").write_text("")
    result = execute(run, plan(order.format("a"), order.format("b"), order.format("c")))
    assert result.passed
    assert (tmp_path / "order").read_text() == "abc"
    assert [c.name for c in result.checks] == ["check0", "check1", "check2"]
    assert run.test_slots.count == 1
    assert result.test_plan is not None
    assert (result.test_plan.coverage, result.test_plan.executed) == ("scoped", 3)


def test_first_failure_stops_the_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    run = fake_run(tmp_path)
    tested = plan(touch("first"), "raise SystemExit(3)", touch("third"))
    result = execute(run, tested)
    assert not result.passed
    assert [c.returncode for c in result.checks] == [0, 3]
    assert (tmp_path / "first").exists() and not (tmp_path / "third").exists()
    assert len(result.failures) == 1 and result.failures[0].startswith("check1:")
    assert result.test_plan is not None
    assert result.test_plan.executed == 2
    # The evidence names every planned command, also the one that never ran.
    assert len(result.test_plan.commands) == 3
    assert result.test_plan.commands[2] == shlex.join(python(touch("third")))


def test_coverage_none_passes_with_nothing_executed(tmp_path: Path) -> None:
    run = fake_run(tmp_path)
    run.test_slots = Slots()
    result = execute(run, plan(coverage="none"))
    assert result.passed and result.checks == [] and result.failures == []
    assert run.test_slots.count == 0  # nothing to run, no slot taken
    assert result.test_plan is not None
    assert result.test_plan.model_dump() == {
        "coverage": "none",
        "reason": "covers the change",
        "executed": 0,
        "commands": [],
        "dropped": [],
    }


def test_checks_share_one_time_limit(tmp_path: Path) -> None:
    run = fake_run(tmp_path, timeout=1)
    sleep = "import time; time.sleep(0.6)"
    result = execute(run, plan(sleep, sleep))
    assert not result.passed
    assert result.checks[-1].returncode == 124


def test_exhausted_budget_does_not_start_the_next_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.engine import quality
    from aifactory.testing import executor

    monkeypatch.chdir(tmp_path)
    run = fake_run(tmp_path, timeout=1)
    clock = iter([0.0, 0.25, 1.1])
    monkeypatch.setattr(executor, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    limits: list[float] = []
    original = quality._run

    def observed(spec: Any, running: Any) -> Any:
        limits.append(spec.timeout_seconds)
        return original(spec, running)

    monkeypatch.setattr(quality, "_run", observed)
    result = execute(run, plan("print('first')", touch("must-not-start")))
    assert limits == [0.75]
    assert not (tmp_path / "must-not-start").exists()
    assert not result.passed and "shared time limit" in result.failures[0]
    assert result.test_plan is not None and result.test_plan.executed == 1
    assert len(result.checks) == 1 and result.checks[0].passed


def test_a_check_timeout_only_shortens_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.engine import quality

    limits: list[float] = []
    original = quality._run

    def observed(spec: Any, running: Any) -> Any:
        limits.append(spec.timeout_seconds)
        return original(spec, running)

    monkeypatch.setattr(quality, "_run", observed)
    tested = TestPlanOutput.model_validate(
        ok(
            coverage="full",
            reason="whole suite",
            checks=[
                {"name": "short", "argv": python("pass"), "timeout": 2},
                {"name": "long", "argv": python("pass"), "timeout": 999},
            ],
        )
    )
    assert execute(fake_run(tmp_path, timeout=4), tested).passed
    assert limits[0] == 2
    assert 3 < limits[1] <= 4


# ── TestPlanOutput ──────────────────────────────────────────────────────────


def test_valid_plans() -> None:
    assert TestPlanOutput.model_validate(plan_envelope(coverage="none")).checks == []
    full = TestPlanOutput.model_validate(plan_envelope("pytest", coverage="full"))
    assert full.checks[0].argv == ["pytest"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"coverage": "none", "checks": [{"name": "x", "argv": ["true"]}]}, "coverage"),
        ({"coverage": "full", "checks": []}, "coverage"),
        ({"coverage": "scoped", "checks": []}, "coverage"),
        ({"checks": [{"name": "x", "argv": ["true"]}] * 2}, "unique"),
        ({"checks": [{"name": "a/b", "argv": ["true"]}]}, "safe file names"),
        ({"checks": [{"name": "..", "argv": ["true"]}]}, "safe file names"),
        ({"checks": [{"name": "x", "argv": []}]}, "argv"),
        ({"checks": [{"name": "x", "argv": ["true"], "timeout": 0}]}, "timeout"),
        ({"checks": [{"name": "x", "argv": ["true"], "shell": True}]}, "shell"),
        ({"coverage": "deferred"}, "coverage"),
        ({"reason": ""}, "reason"),
    ],
)
def test_invalid_plans(change: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        TestPlanOutput.model_validate({**plan_envelope(), **change})


# ── gate checks_runnable ────────────────────────────────────────────────────


def test_checks_runnable_finds_programs_on_path_and_in_the_worktree(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/check.sh").write_text("exit 0\n")
    tested = TestPlanOutput.model_validate(
        ok(
            coverage="scoped",
            reason="covers the change",
            checks=[
                {"name": "on_path", "argv": ["true"]},
                {"name": "local", "argv": ["./scripts/check.sh"]},
                {"name": "unknown", "argv": ["no-such-program-haifa"]},
                {"name": "missing", "argv": ["scripts/missing.sh"]},
            ],
        )
    )
    report = gates.checks_runnable(tested, SimpleNamespace(repo_root=tmp_path))
    assert not report.passed
    assert [v.split(":")[0] for v in report.violations] == ["unknown", "missing"]


def test_checks_runnable_passes_a_plan_without_checks(tmp_path: Path) -> None:
    tested = TestPlanOutput.model_validate(plan_envelope(coverage="none"))
    assert gates.checks_runnable(tested, SimpleNamespace(repo_root=tmp_path)).passed


# ── gate plan_keeps_checks ──────────────────────────────────────────────────


def checks_plan(*checks: tuple[str, list[str]], dropped: tuple[str, ...] = ()) -> TestPlanOutput:
    return TestPlanOutput.model_validate(
        ok(
            coverage="scoped",
            reason="covers the change",
            checks=[{"name": name, "argv": argv} for name, argv in checks],
            dropped=[{"name": name, "reason": "no longer relevant"} for name in dropped],
        )
    )


PREVIOUS = checks_plan(("unit", ["pytest", "tests/unit"]), ("lint", ["ruff", "check"]))


def test_plan_keeps_checks_passes_the_first_plan() -> None:
    first = checks_plan(("unit", ["pytest"]))
    assert gates.plan_keeps_checks(first, SimpleNamespace(previous_test_plan=None)).passed
    assert gates.plan_keeps_checks(first, SimpleNamespace()).passed


def test_plan_keeps_checks_matches_by_argv_not_name() -> None:
    renamed = checks_plan(("tests", ["pytest", "tests/unit"]), ("ruff", ["ruff", "check"]))
    report = gates.plan_keeps_checks(renamed, SimpleNamespace(previous_test_plan=PREVIOUS))
    assert report.passed
    assert [c.item for c in report.checks] == ["unit", "lint"]


def test_plan_keeps_checks_accepts_a_dropped_entry() -> None:
    new = checks_plan(("unit", ["pytest", "tests/unit"]), dropped=("lint",))
    assert gates.plan_keeps_checks(new, SimpleNamespace(previous_test_plan=PREVIOUS)).passed


def test_plan_keeps_checks_fails_a_check_left_out_silently() -> None:
    # Same name, other argv, and no `dropped` entry: the old check is gone.
    new = checks_plan(("unit", ["pytest", "tests/unit/test_one.py"]), ("lint", ["ruff", "check"]))
    report = gates.plan_keeps_checks(new, SimpleNamespace(previous_test_plan=PREVIOUS))
    assert not report.passed
    assert len(report.violations) == 1
    assert report.violations[0].startswith("unit:")
    assert "dropped" in report.violations[0]


# ── interpreter ─────────────────────────────────────────────────────────────


def test_every_test_runs_the_latest_plan(workflow_env: EngineEnv) -> None:
    text = (
        HEADER
        + """\
steps:
  - test_plan
  - test
  - build
  - test_plan: {id: replan}
  - test: {id: retest}
accept: test.passed
"""
    )
    replan = ok(
        coverage="scoped",
        reason="the build replaced the first check",
        checks=[{"name": "second", "argv": ["echo", "2"]}],
        dropped=[{"name": "check", "reason": "the build removed what it checked"}],
    )
    workflow_env.script.add("tester", plan_envelope("echo", "first"), replan)
    workflow_env.script.add("builder", ok(summary="built", changed_files=[]))
    code = FakeCodeRunner([True, True])
    result = run_workflow(workflow(text), "do it", workflow_env.cfg, code=code)
    assert result.accepted
    assert [p.checks[0].argv for p in code.plans] == [["echo", "first"], ["echo", "2"]]
    assert [d.name for d in code.plans[1].dropped] == ["check"]


def test_a_failing_plan_reaches_the_fixer_and_the_retest_passes(
    workflow_env: EngineEnv,
) -> None:
    """Real executor: the check fails until the builder writes ``fixed.py``."""
    check = "from pathlib import Path; raise SystemExit(0 if Path('fixed.py').exists() else 3)"
    text = yaml.safe_dump(
        {
            "name": "planned",
            "description": "Retest after each repair",
            "steps": [
                "test_plan",
                {"repeat": {"max": 2, "until": "test.passed"}, "steps": ["test", "fix"]},
            ],
            "accept": "test.passed",
        }
    )
    workflow_env.script.add(
        "tester", plan_envelope(*python(check)), triage_envelope("code", *python(check))
    )
    workflow_env.script.add("builder", ok(summary="fixed", changed_files=["fixed.py"]))
    workflow_env.script.on("builder", lambda root: (root / "fixed.py").write_text("pass"))
    result = run_workflow(workflow(text), "fix it", workflow_env.cfg, repo_root=workflow_env.repo)
    assert result.accepted
    assert [call.agent for call in workflow_env.script.calls] == ["tester", "tester", "builder"]
    evidence = result.results["test"]["test_plan"]
    assert (evidence["coverage"], evidence["executed"]) == ("scoped", 1)
    assert evidence["commands"] and "fixed.py" in evidence["commands"][0]


def test_previous_test_plan_is_a_prompt_variable(workflow_env: EngineEnv, tmp_path: Path) -> None:
    user = tmp_path / "tester_user.md"
    user.write_text("{{prompt}}\nPLAN<<{{previous_test_plan}}>>PLAN\n", encoding="utf-8")
    for agent in workflow_env.cfg.agents:
        if agent.name == "tester":
            agent.prompt_engineering.user = str(user)
    text = HEADER + "steps:\n  - test_plan\n  - test\n  - test_plan: {id: replan}\n"
    first = plan_envelope("echo", "first")
    workflow_env.script.add("tester", first, first)
    run_workflow(workflow(text), "do it", workflow_env.cfg, code=FakeCodeRunner([True]))
    rendered = [
        call.prompt.split("PLAN<<")[1].split(">>PLAN")[0] for call in workflow_env.script.calls
    ]
    assert rendered[0] == "(none)"
    assert json.loads(rendered[1]) == {
        "coverage": "scoped",
        "reason": "covers the change",
        "checks": [{"name": "check", "argv": ["echo", "first"], "timeout": None}],
    }


def test_a_replan_that_drops_a_check_silently_is_sent_back(workflow_env: EngineEnv) -> None:
    text = HEADER + "steps:\n  - test_plan\n  - test_plan: {id: replan}\n  - test\n"
    silent = plan_envelope("echo", "other")  # same name, other argv, no `dropped`
    kept = plan_envelope("echo", "first")
    workflow_env.script.add("tester", kept, silent, kept)
    code = FakeCodeRunner([True])
    result = run_workflow(workflow(text), "do it", workflow_env.cfg, code=code)
    assert result.accepted
    assert len(workflow_env.script.calls) == 3
    assert "dropped" in workflow_env.script.calls[2].prompt  # the gate's correction
    assert code.plans[0].checks[0].argv == ["echo", "first"]


# ── triage of a red test ────────────────────────────────────────────────────

LOOP = HEADER + (
    "steps:\n  - test_plan\n  - repeat: {max: MAX, until: test.passed}\n    steps: [test, fix]\n"
    "accept: test.passed\n"
)


def corrected(*argv: str) -> dict[str, Any]:
    """A triage verdict `plan` whose corrected check replaces the first plan's."""
    return {
        **triage_envelope("plan", *argv),
        "dropped": [{"name": "check", "reason": "it pointed at a file that does not exist"}],
    }


def _phase_names(result: Any) -> list[str]:
    return [name for name, _, _ in result.phases if name != "request"]


def test_triage_code_sends_the_red_test_to_the_fixer(workflow_env: EngineEnv) -> None:
    workflow_env.script.add("tester", plan_envelope(), triage_envelope("code"))
    workflow_env.script.add("builder", ok(summary="fixed", changed_files=[]))
    code = FakeCodeRunner([False, True])
    result = run_workflow(workflow(LOOP.replace("MAX", "2")), "do it", workflow_env.cfg, code=code)
    assert result.accepted
    assert _phase_names(result) == ["test_plan", "test_1", "triage_1", "fix_1", "test_2"]
    triage, fix = workflow_env.script.calls[1], workflow_env.script.calls[2]
    assert json.loads(triage.previous())["passed"] is False  # the tester judges the red test
    assert json.loads(fix.previous())["passed"] is False  # the verdict is not stored
    assert result.results["test_plan"]["failure_cause"] == ""  # still the first plan
    assert len(code.plans) == 2 and code.plans[0] is code.plans[1]


def test_triage_plan_reruns_the_test_with_the_corrected_plan(workflow_env: EngineEnv) -> None:
    # max 1: a plan repair does not use up the round, and no builder is called.
    workflow_env.script.add("tester", plan_envelope("echo", "bad"), corrected("echo", "good"))
    code = FakeCodeRunner([False, True])
    result = run_workflow(workflow(LOOP.replace("MAX", "1")), "do it", workflow_env.cfg, code=code)
    assert result.accepted
    assert _phase_names(result) == ["test_plan", "test_1", "triage_1", "test_1_2"]
    assert [c.agent for c in workflow_env.script.calls] == ["tester", "tester"]
    assert [p.checks[0].argv for p in code.plans] == [["echo", "bad"], ["echo", "good"]]
    assert result.results["test_plan"]["failure_cause"] == "plan"


def test_plan_repairs_are_capped(workflow_env: EngineEnv) -> None:
    workflow_env.script.add(
        "tester",
        plan_envelope("echo", "bad"),
        corrected("echo", "a"),
        triage_envelope("plan", "echo", "a"),
        {**triage_envelope("plan", "echo", "a"), "reason": "still the wrong path"},
    )
    code = FakeCodeRunner([False, False, False])
    with pytest.raises(RuntimeError, match="still cannot run after 2 corrections"):
        run_workflow(workflow(LOOP.replace("MAX", "3")), "do it", workflow_env.cfg, code=code)
    assert not any(call.agent == "builder" for call in workflow_env.script.calls)
    assert len(code.plans) == 3


def test_failed_test_is_rendered_only_in_triage(workflow_env: EngineEnv, tmp_path: Path) -> None:
    user = tmp_path / "user.md"
    user.write_text(
        "{{prompt}}\nPREV<<{{previous_envelope}}>>PREV\nFAILED<<{{failed_test}}>>FAILED\n",
        encoding="utf-8",
    )
    for agent in workflow_env.cfg.agents:
        if agent.name in ("tester", "builder"):
            agent.prompt_engineering.user = str(user)
    workflow_env.script.add("tester", plan_envelope(), triage_envelope("code"))
    workflow_env.script.add("builder", ok(summary="fixed", changed_files=[]))
    run_workflow(
        workflow(LOOP.replace("MAX", "2")),
        "do it",
        workflow_env.cfg,
        code=FakeCodeRunner([False, True]),
    )
    failed = {
        call.agent + str(i): call.prompt.split("FAILED<<")[1].split(">>FAILED")[0]
        for i, call in enumerate(workflow_env.script.calls)
    }
    assert failed["tester0"] == "(none)"  # the first plan
    assert failed["builder2"] == "(none)"  # the fixer
    report = json.loads(failed["tester1"])  # the triage
    assert (report["step"], report["phase"], report["passed"]) == ("test", "test_1", False)


# ── required coverage ───────────────────────────────────────────────────────


def test_plan_keeps_checks_passes_any_full_plan() -> None:
    full = TestPlanOutput.model_validate(plan_envelope("just", "check", coverage="full"))
    assert gates.plan_keeps_checks(full, SimpleNamespace(previous_test_plan=PREVIOUS)).passed


@pytest.mark.parametrize(
    ("required", "coverage", "passed"),
    [(None, "scoped", True), ("full", "full", True), ("full", "scoped", False)],
)
def test_coverage_required_gate(required: str | None, coverage: str, passed: bool) -> None:
    tested = TestPlanOutput.model_validate(plan_envelope(coverage=coverage))
    report = gates.coverage_required(tested, SimpleNamespace(required_coverage=required))
    assert report.passed is passed


def test_a_scoped_plan_on_a_full_step_is_sent_back(workflow_env: EngineEnv) -> None:
    text = HEADER + "steps:\n  - test_plan: {coverage: full}\n  - test\n"
    workflow_env.script.add("tester", plan_envelope(), plan_envelope(coverage="full"))
    code = FakeCodeRunner([True])
    result = run_workflow(workflow(text), "do it", workflow_env.cfg, code=code)
    assert result.accepted
    assert len(workflow_env.script.calls) == 2
    assert "requires `full`" in workflow_env.script.calls[1].prompt  # the gate's correction
    assert code.plans[0].coverage == "full"
