"""The packaged workflows load, pass `factory workflow check` and keep their loop shape."""

from __future__ import annotations

from pathlib import Path

import pytest
from workflow_fakes import EngineEnv, workflow_env_fixture  # noqa: F401

from aifactory.cli import main
from aifactory.workflow import DEFAULT_WORKFLOWS_DIR, CodeStep, Repeat, RoleStep, load_workflow
from cli_json import read_envelope

DEFAULTS = sorted(DEFAULT_WORKFLOWS_DIR.glob("*.yaml"))
NAMES = {
    "plan",
    "plan-build",
    "plan-build-test",
    "simple-sdlc",
    "document",
    "scout",
    "resolve",
    "resolve-reviewed",
}


def test_every_packaged_workflow_is_known() -> None:
    assert {path.stem for path in DEFAULTS} == NAMES


@pytest.mark.parametrize("path", DEFAULTS, ids=lambda p: p.stem)
def test_default_workflows_load(path: Path) -> None:
    workflow = load_workflow(path)
    assert workflow.name == path.stem
    assert workflow.steps


@pytest.mark.parametrize("path", DEFAULTS, ids=lambda p: p.stem)
def test_default_workflow_passes_check(
    path: Path,
    workflow_env: EngineEnv,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    roster = workflow_env.repo.parent / "agents.yaml"
    argv = ["workflow", "check", str(path), "--json", "--agents", str(roster)]
    assert main(argv) == 0
    env = read_envelope(capsys)
    assert env["ok"] is True
    assert env["warnings"] == []
    assert env["data"]["issues"] == []
    assert env["data"]["agents"] == str(roster)


def test_simple_sdlc_structure() -> None:
    workflow = load_workflow(DEFAULT_WORKFLOWS_DIR / "simple-sdlc.yaml")
    loops = [s for s in workflow.steps if isinstance(s, Repeat)]
    assert [loop.max for loop in loops] == [3, 2]
    assert [loop.until.source for loop in loops if loop.until] == [
        "test.passed",
        "review.approved",
    ]
    # The last round ends at the check: no fix_3, no revise_2.
    assert [loop.until_tail for loop in loops] == [0, 0]
    review = loops[1].steps[0]
    assert isinstance(review, RoleStep)
    assert review.inputs == ("build", "fix", "revise")
    retest = workflow.steps[5]
    assert isinstance(retest, CodeStep)
    assert (retest.key, retest.phase_id) == ("test", "retest")
    assert workflow.accept is not None


def test_plan_build_test_structure() -> None:
    workflow = load_workflow(DEFAULT_WORKFLOWS_DIR / "plan-build-test.yaml")
    loops = [s for s in workflow.steps if isinstance(s, Repeat)]
    assert len(loops) == 1
    assert loops[0].max == 3
    assert loops[0].until_tail == 0
    assert workflow.accept is not None
    assert workflow.accept.source == "test.passed"


def test_resolve_structure() -> None:
    workflow = load_workflow(DEFAULT_WORKFLOWS_DIR / "resolve.yaml")
    rebase, resolve, loop = workflow.steps
    assert isinstance(rebase, CodeStep)
    assert rebase.action == "rebase"
    assert rebase.when is None
    assert isinstance(resolve, RoleStep)
    assert resolve.name == "resolve"
    assert resolve.role.agent == "builder"
    assert resolve.when is not None
    assert resolve.when.source == "rebase.conflict"
    assert isinstance(loop, Repeat)
    assert loop.max == 3
    assert loop.until is not None
    assert loop.until.source == "test.passed"
    rebuild, test, fix = loop.steps
    assert isinstance(rebuild, CodeStep)
    assert rebuild.action == "rebuild"
    assert rebuild.when is not None
    assert rebuild.when.source == "rebase.conflict"
    assert isinstance(test, CodeStep)
    assert test.action == "test"
    assert isinstance(fix, RoleStep)
    assert fix.name == "fix"
    assert fix.role.agent == "builder"
    assert fix.when is not None
    assert fix.when.source == "rebase.conflict"
    assert workflow.accept is not None
    assert workflow.accept.source == "test.passed"
