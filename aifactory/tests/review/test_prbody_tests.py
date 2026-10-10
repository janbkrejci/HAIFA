"""The test lines of the PR body name the planned checks that did not run."""

from __future__ import annotations

from aifactory.review.prbody import _tests
from aifactory.workflow import WorkflowRun


def test_not_run_checks_are_listed_with_the_reason() -> None:
    wf = WorkflowRun(exit_code=1, accepted=False, adw_id="r1")
    wf.results["test"] = {
        "passed": False,
        "summary": "tests: 1 of 1 check(s) failed",
        "test_plan": {
            "coverage": "scoped",
            "commands": ["make build", "pytest"],
            "not_run": [{"name": "unit", "reason": "build failed and has stop_on_fail"}],
        },
    }
    [line] = _tests(wf)
    assert "cílené ověření: neprošly" in line
    assert "nespuštěno: `unit` (build failed and has stop_on_fail)" in line


def test_a_result_without_not_run_has_no_such_note() -> None:
    wf = WorkflowRun(exit_code=0, accepted=True, adw_id="r1")
    wf.results["test"] = {"passed": True, "test_plan": {"coverage": "full", "commands": ["pytest"]}}
    [line] = _tests(wf)
    assert "nespuštěno" not in line
