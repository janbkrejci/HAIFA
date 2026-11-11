"""Scoped repair rounds, a single final suite, and the pre-rebase testing baseline."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from workflow_fakes import (
    EngineEnv,
    FakeCodeRunner,
    ok,
    workflow,
    workflow_env_fixture,  # noqa: F401
)

from aifactory.engine import data_types as dt
from aifactory.engine import gates
from aifactory.failure import RunFailure
from aifactory.review.prbody import _tests
from aifactory.testing.model import Evidence
from aifactory.testing.profile import ProfileCache
from aifactory.workflow import DEFAULT_WORKFLOWS_DIR, load_workflow, run_workflow
from aifactory.workflow.interpreter import testing_scope as scope_for_paths
from aifactory.workflow.journal import Journal
from aifactory.workflow.rebase import RebaseOutput


class ChecksRunner(FakeCodeRunner):
    def test(self, run: Any, plan: Any) -> dt.QualityResult:
        result: dt.QualityResult = super().test(run, plan)
        result.checks = [
            dt.QualityCheckResult(
                name=c.name,
                area="backend",
                operation="build",
                command=shlex.join(c.argv),
                returncode=0 if result.passed or i else 1,
                passed=result.passed or bool(i),
                duration_seconds=0.01,
                output_artifact="",
                output_tail="failure in module A",
            )
            for i, c in enumerate(plan.checks)
        ]
        result.test_plan = Evidence(
            coverage=plan.coverage,
            reason=plan.reason,
            executed=len(plan.checks),
            commands=[c.command for c in result.checks],
        )
        return result


def selected(*names: str, coverage: str = "scoped") -> dict[str, Any]:
    return ok(
        coverage=coverage,
        reason="shared runtime changed" if coverage == "full" else "affected modules",
        checks=[
            {"name": n, "argv": [sys.executable, "-c", f"print({(n + coverage)!r})"]} for n in names
        ],
    )


def test_scoped_round_defers_green_checks_but_cannot_discard_failure() -> None:
    previous = dt.TestPlanOutput.model_validate(selected("failed", "green"))
    run = SimpleNamespace(
        previous_test_plan=previous, required_coverage="scoped", failed_test_checks=["failed"]
    )
    assert gates.plan_keeps_checks(dt.TestPlanOutput.model_validate(selected("failed")), run).passed
    discarded = selected("green")
    discarded["dropped"] = [{"name": "failed", "reason": "the whole suite confirms later"}]
    assert not gates.plan_keeps_checks(dt.TestPlanOutput.model_validate(discarded), run).passed
    discarded["coverage"] = "full"
    assert not gates.plan_keeps_checks(dt.TestPlanOutput.model_validate(discarded), run).passed
    run.previous_test_plan = dt.TestPlanOutput.model_validate(selected("suite", coverage="full"))
    run.failed_test_checks = []
    assert gates.plan_keeps_checks(
        dt.TestPlanOutput.model_validate(selected("affected")), run
    ).passed


def test_fix_and_revision_run_scoped_then_confirm_once(workflow_env: EngineEnv) -> None:
    env = workflow_env
    env.script.add("builder", ok(), ok(), ok())
    env.script.add("reviewer", ok(approved=False, blocking=["revise A"]), ok(approved=True))
    env.script.add(
        "tester",
        selected("suite", coverage="full"),
        selected("failed", "green"),
        selected("failed", "affected"),
        selected("revised"),
        selected("suite", coverage="full"),
    )
    code = ChecksRunner([False, True, True, True])
    result = run_workflow(
        load_workflow(DEFAULT_WORKFLOWS_DIR / "build-test-review.yaml"),
        "change shared runtime",
        env.cfg,
        code=code,
    )
    assert result.accepted
    assert [[c.name for c in p.checks] for p in code.plans] == [
        ["failed", "green"],
        ["failed", "affected"],
        ["revised"],
        ["suite"],
    ]
    # Only the first check fails; a green, unaffected check is not accumulated.
    assert [p.coverage for p in code.plans] == ["scoped", "scoped", "scoped", "full"]
    phases = [r.phase for r in result.records]
    assert phases.index("review_2") < phases.index("final_test") < phases.index("commit_build")
    assert result.results["full_suite"] == {"count": 1, "reasons": ["shared runtime changed"]}
    assert "full suite runs: 1" in result.results["test"]["summary"]
    assert any("full suite runs: 1 (shared runtime changed)" in line for line in _tests(result))


@pytest.mark.parametrize("repair_passes", [True, False])
def test_failed_confirmation_repairs_scoped_and_never_runs_full_again(
    workflow_env: EngineEnv,
    repair_passes: bool,
) -> None:
    env = workflow_env
    rounds = 1 if repair_passes else 3
    env.script.add("builder", ok(), *[ok() for _ in range(rounds)])
    env.script.add(
        "tester",
        selected("suite", coverage="full"),
        selected("affected"),
        selected("suite", coverage="full"),
        *[selected("suite") for _ in range(rounds)],
    )
    code = ChecksRunner([True, False, *[repair_passes] * rounds])
    result = run_workflow(
        load_workflow(DEFAULT_WORKFLOWS_DIR / "build-test.yaml"),
        "change shared runtime",
        env.cfg,
        code=code,
    )
    assert result.accepted is repair_passes
    assert len(code.commits) == int(repair_passes)
    assert sum(p.coverage == "full" for p in code.plans) == 1
    assert result.results["full_suite"]["count"] == 1


def test_replay_does_not_execute_the_confirmation_again(workflow_env: EngineEnv) -> None:
    env = workflow_env
    env.script.add("builder", ok())
    env.script.add(
        "tester",
        selected("suite", coverage="full"),
        selected("affected"),
        selected("suite", coverage="full"),
    )
    journal = Journal(path=None)
    wf = load_workflow(DEFAULT_WORKFLOWS_DIR / "build-test.yaml")
    first = run_workflow(
        wf, "shared runtime", env.cfg, code=ChecksRunner([True, True]), journal=journal
    )
    assert first.accepted
    journal.start_replay(len(journal.entries))
    code = ChecksRunner([])
    second = run_workflow(wf, "shared runtime", env.cfg, code=code, journal=journal)
    assert second.accepted
    assert code.plans == []
    assert second.results["full_suite"]["count"] == 1


@pytest.mark.parametrize(
    ("paths", "shared", "coverage"),
    [
        (["README.md", "factory/backlog/task.md"], [], "none"),
        (["src/Project/Feature.cs"], [], "scoped"),
        (["src/RobTextMode/Mode.cs"], ["src/RobTextMode"], "full"),
        (["src/RobTextMode.cs"], ["src/RobText*.cs"], "full"),
        (["Directory.Build.props"], [], "full"),
        (["tests/conftest.py"], [], "full"),
        (["requirements.txt"], [], "full"),
        ([".github/workflows/ci.yml"], [], "full"),
    ],
)
def test_scope_uses_diff_categories_and_profile_paths(
    paths: list[str],
    shared: list[str],
    coverage: str,
) -> None:
    assert scope_for_paths(paths, shared)["coverage"] == coverage


class ChangedRebase(ChecksRunner):
    def __init__(self, root: Path, auto_code: bool) -> None:
        super().__init__([True])
        self.root = root
        self.auto_code = auto_code

    def baseline(self) -> str:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True
        ).stdout.strip()

    def rebase(self, run: Any) -> RebaseOutput:
        before = self.baseline()
        (self.root / "README.md").write_text("resolved docs")
        if self.auto_code:
            (self.root / "Feature.cs").write_text("// automatically merged code")
        return RebaseOutput(
            status="success",
            summary="rebased",
            onto="1" * 40,
            before=before,
            clean=False,
            conflict=True,
            files=["README.md"],
        )


@pytest.mark.parametrize("auto_code", [False, True])
@pytest.mark.parametrize("name", ["resolve", "resolve-reviewed"])
def test_resolve_scope_includes_automatic_merges_against_pre_rebase_head(
    workflow_env: EngineEnv,
    auto_code: bool,
    name: str,
) -> None:
    env = workflow_env
    tester = next(a for a in env.cfg.agents if a.name == "tester")
    prompt = Path(tester.prompt_engineering.user)
    prompt.write_text("{{baseline}}\n{{testing_scope}}", encoding="utf-8")
    env.script.add("builder", ok())
    if name == "resolve-reviewed":
        env.script.add("reviewer", ok(approved=True))
    env.script.add(
        "tester",
        selected("project-build", "project-tests") if auto_code else selected("docs-reader"),
    )
    code = ChangedRebase(env.repo, auto_code)
    before = code.baseline()
    result = run_workflow(
        load_workflow(DEFAULT_WORKFLOWS_DIR / f"{name}.yaml"),
        "resolve",
        env.cfg,
        code=code,
        baseline="0" * 40,
    )
    assert result.accepted
    call = next(c for c in env.script.calls if c.agent == "tester")
    assert call.prompt.splitlines()[0] == before
    scope = json.loads(call.prompt.splitlines()[1])
    assert scope["coverage"] == ("scoped" if auto_code else "none")
    assert "README.md" in scope["files"]
    assert ("Feature.cs" in scope["files"]) is auto_code
    assert [c.name for c in code.plans[0].checks] == (
        ["project-build", "project-tests"] if auto_code else ["docs-reader"]
    )


def test_second_full_execution_is_blocked_before_the_runner(workflow_env: EngineEnv) -> None:
    env = workflow_env
    env.script.add("tester", selected("suite", coverage="full"))
    code = ChecksRunner([True])
    wf = workflow("name: t\ndescription: repeated suite\nsteps: [test_plan, test, test]\n")
    with pytest.raises(RunFailure, match="whole suite already ran"):
        run_workflow(wf, "read-only verification", env.cfg, code=code)
    assert len(code.plans) == 1


def test_doc_only_change_can_have_no_checks(workflow_env: EngineEnv) -> None:
    env = workflow_env
    env.script.add("builder", ok())
    env.script.add(
        "tester", ok(coverage="none", reason="Documentation has no reader checks", checks=[])
    )
    result = run_workflow(
        load_workflow(DEFAULT_WORKFLOWS_DIR / "build-test.yaml"),
        "edit documentation only",
        env.cfg,
        code=ChecksRunner([True]),
    )
    assert result.accepted
    assert result.results["full_suite"]["count"] == 0


def test_profile_shared_paths_reach_the_first_plan(workflow_env: EngineEnv, tmp_path: Path) -> None:
    env = workflow_env
    (env.repo / "RobTextMode.cs").write_text("// shared implementation")
    cache = ProfileCache(tmp_path / "profiles", "project")
    cache.save(env.repo, "shared_paths: RobTextMode.cs")
    tester = next(a for a in env.cfg.agents if a.name == "tester")
    Path(tester.prompt_engineering.user).write_text("{{testing_scope}}", encoding="utf-8")
    env.script.add("tester", selected("suite", coverage="full"))
    code = ChangedRebase(env.repo, False)
    result = run_workflow(
        workflow("name: t\ndescription: profile scope\nsteps: [test_plan, test]\n"),
        "check shared implementation",
        env.cfg,
        code=code,
        baseline=code.baseline(),
        test_profile=cache,
    )
    assert result.accepted
    scope = json.loads(env.script.calls[0].prompt)
    assert scope["coverage"] == "full"
    assert scope["shared"] == ["RobTextMode.cs"]


def test_failed_confirmation_rechecks_review_after_scoped_repair(workflow_env: EngineEnv) -> None:
    env = workflow_env
    env.script.add("builder", ok(), ok())
    env.script.add("reviewer", ok(approved=True), ok(approved=True))
    env.script.add(
        "tester",
        selected("suite", coverage="full"),
        selected("affected"),
        selected("suite", coverage="full"),
        selected("suite"),
    )
    code = ChecksRunner([True, False, True])
    result = run_workflow(
        load_workflow(DEFAULT_WORKFLOWS_DIR / "build-test-review.yaml"),
        "repair final confirmation",
        env.cfg,
        code=code,
    )
    assert result.accepted
    phases = [r.phase for r in result.records]
    assert (
        phases.index("final_retest_1")
        < phases.index("final_review_1")
        < phases.index("commit_build")
    )
    assert sum(p.coverage == "full" for p in code.plans) == 1


def test_custom_workflow_without_commit_confirms_before_acceptance(workflow_env: EngineEnv) -> None:
    env = workflow_env
    env.script.add("builder", ok())
    env.script.add(
        "tester",
        selected("suite", coverage="full"),
        selected("affected"),
        selected("suite", coverage="full"),
    )
    code = ChecksRunner([True, True])
    wf = workflow(
        "name: custom\ndescription: custom implementation\n"
        "steps: [build, test_plan, test]\naccept: test.passed\n"
    )
    result = run_workflow(wf, "implement", env.cfg, code=code)
    assert result.accepted
    assert [p.coverage for p in code.plans] == ["scoped", "full"]
    assert result.records[-1].phase == "final_test"


@pytest.mark.parametrize("commit_when_full", [False, True])
@pytest.mark.parametrize("accept_full", [False, True])
@pytest.mark.parametrize("confirmation_passes", [False, True])
def test_custom_full_conditions_confirm_before_commit_and_acceptance(
    workflow_env: EngineEnv,
    commit_when_full: bool,
    accept_full: bool,
    confirmation_passes: bool,
) -> None:
    env = workflow_env
    env.script.add("builder", ok())
    env.script.add(
        "tester",
        selected("suite", coverage="full"),
        selected("affected"),
        selected("suite", coverage="full"),
    )
    full_condition = 'test.passed and test.coverage == "full"'
    commit_condition = full_condition if commit_when_full else "test.passed"
    accept_condition = full_condition if accept_full else "test.passed"
    wf = workflow(
        "name: custom\ndescription: deferred full conditions\nsteps:\n"
        "  - build\n  - test_plan\n  - test\n"
        f"  - commit:\n      when: {commit_condition}\naccept: {accept_condition}\n"
    )
    code = ChecksRunner([True, confirmation_passes])
    result = run_workflow(wf, "implement shared change", env.cfg, code=code)
    assert result.accepted is confirmation_passes
    assert len(code.commits) == int(confirmation_passes)
    assert [p.coverage for p in code.plans] == ["scoped", "full"]
    assert result.results["full_suite"]["count"] == 1
    if confirmation_passes:
        phases = [r.phase for r in result.records]
        assert phases.index("final_test") < phases.index("commit")


def test_custom_full_acceptance_without_commit_runs_confirmation(workflow_env: EngineEnv) -> None:
    env = workflow_env
    env.script.add("builder", ok())
    env.script.add(
        "tester",
        selected("suite", coverage="full"),
        selected("affected"),
        selected("suite", coverage="full"),
    )
    wf = workflow(
        "name: custom\ndescription: full acceptance\nsteps: [build, test_plan, test]\n"
        'accept: test.passed and test.coverage == "full"\n'
    )
    code = ChecksRunner([True, True])
    result = run_workflow(wf, "implement shared change", env.cfg, code=code)
    assert result.accepted
    assert result.records[-1].phase == "final_test"
    assert [p.coverage for p in code.plans] == ["scoped", "full"]


def test_full_condition_does_not_bypass_rejected_review(workflow_env: EngineEnv) -> None:
    env = workflow_env
    env.script.add("builder", ok())
    env.script.add("tester", selected("suite", coverage="full"), selected("affected"))
    env.script.add("reviewer", ok(approved=False, blocking=["missing behavior"]))
    condition = 'review.approved and test.passed and test.coverage == "full"'
    wf = workflow(
        "name: custom\ndescription: rejected review\nsteps:\n"
        "  - build\n  - test_plan\n  - test\n  - review\n"
        f"  - commit:\n      when: {condition}\naccept: {condition}\n"
    )
    code = ChecksRunner([True])
    result = run_workflow(wf, "implement shared change", env.cfg, code=code)
    assert not result.accepted
    assert code.commits == []
    assert [p.coverage for p in code.plans] == ["scoped"]
    assert result.results["test"]["coverage"] == "scoped"
