"""A workflow from before 3.0 (no test_plan at all) gets one before its first test."""

from __future__ import annotations

import pytest
from workflow_fakes import workflow

from aifactory.workflow import Repeat, RoleStep, WorkflowError


def test_plan_is_added_before_the_first_test_in_a_loop() -> None:
    wf = workflow(
        """
name: old
description: An older build, test and commit
steps:
  - build
  - repeat: {max: 3, until: test.passed}
    steps: [test, fix]
  - commit: {when: test.passed}
accept: test.passed
"""
    )
    loop = wf.steps[1]
    assert isinstance(loop, Repeat)
    assert [getattr(s, "name", None) for s in loop.steps] == ["test_plan", "test", "fix"]
    assert isinstance(loop.steps[0], RoleStep) and loop.steps[0].role.agent == "tester"
    assert loop.until_tail == 1  # the last round still stops at the test
    assert wf.warnings and "no test_plan step" in wf.warnings[0]


def test_plan_is_added_at_top_level() -> None:
    wf = workflow("name: old\ndescription: An older build and test\nsteps: [build, test]\n")
    assert [s.name for s in wf.steps] == ["build", "test_plan", "test"]  # type: ignore[union-attr]


def test_workflow_with_a_plan_is_not_changed() -> None:
    wf = workflow(
        "name: new\ndescription: A planned build and test\nsteps: [build, test_plan, test]\n"
    )
    assert wf.warnings == ()


def test_test_before_an_existing_plan_is_still_an_error() -> None:
    with pytest.raises(WorkflowError) as err:
        workflow(
            "name: bad\ndescription: A test before its plan\nsteps: [build, test, test_plan]\n"
        )
    assert err.value.issues[0].code == "test_without_plan"
