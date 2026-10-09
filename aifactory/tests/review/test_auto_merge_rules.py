"""The conditions of auto-merge as pure functions (no git, no provider)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from aifactory.engine.data_types import ReviewFinding, ReviewOutput
from aifactory.providers import (
    CHECKS_FAILING,
    CHECKS_NONE,
    CHECKS_PASSING,
    CHECKS_PENDING,
    CLOSED,
    CONFLICT,
    MERGEABLE,
    MERGED,
    OPEN,
    UNKNOWN,
    ChecksStatus,
    PrStatus,
)
from aifactory.review import hosting_blocker, last_review, review_blocker, workflow_has_review
from aifactory.workflow import DEFAULT_WORKFLOWS_DIR, WorkflowRun

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workflow"))

from workflow_fakes import workflow  # noqa: E402


def _review(approved: bool, *, blocking: list[str] | None = None, met: bool = True) -> ReviewOutput:
    return ReviewOutput(
        status="success",
        summary="r",
        approved=approved,
        blocking=blocking or [],
        findings=[ReviewFinding(requirement="the ask", met=met)],
    )


def test_review_blocker_each_condition() -> None:
    assert review_blocker(None) == ("no_review", "no review ran in this run")
    assert review_blocker(_review(False, blocking=["x"]))[0] == "review_rejected"  # type: ignore[index]
    blocking = review_blocker(_review(True, blocking=["fix it"]))
    assert blocking is not None and blocking[0] == "review_blocking" and "fix it" in blocking[1]
    unmet = review_blocker(_review(True, met=False))
    assert unmet is not None and unmet[0] == "review_unmet" and "the ask" in unmet[1]
    assert review_blocker(_review(True)) is None


@pytest.mark.parametrize(
    ("status", "checks", "code"),
    [
        (PrStatus(CLOSED), ChecksStatus(CHECKS_NONE), "pr_not_open"),
        (PrStatus(MERGED), ChecksStatus(CHECKS_NONE), "pr_not_open"),
        (PrStatus(OPEN, CONFLICT), ChecksStatus(CHECKS_PASSING), "conflict"),
        (PrStatus(OPEN, UNKNOWN), ChecksStatus(CHECKS_PASSING), "mergeability_unknown"),
        (PrStatus(OPEN, MERGEABLE), ChecksStatus(CHECKS_FAILING, ("ci",)), "checks_failing"),
        (PrStatus(OPEN, MERGEABLE), ChecksStatus(CHECKS_PENDING), None),
        (PrStatus(OPEN, MERGEABLE), ChecksStatus(CHECKS_NONE), None),
        (PrStatus(OPEN, MERGEABLE), ChecksStatus(CHECKS_PASSING), None),
    ],
)
def test_hosting_blocker(status: PrStatus, checks: ChecksStatus, code: str | None) -> None:
    found = hosting_blocker(status, checks)
    assert (found[0] if found else None) == code


def test_workflow_has_review() -> None:
    sdlc = (DEFAULT_WORKFLOWS_DIR / "simple-sdlc.yaml").read_text(encoding="utf-8")
    assert workflow_has_review(workflow(sdlc))
    reviewed = (
        "name: r\ndescription: Plan, check the plan, commit\nsteps: [plan, reviewer, commit]\n"
    )
    assert workflow_has_review(workflow(reviewed))
    plain = "name: p\ndescription: Plan and commit the plan\nsteps: [plan, commit]\n"
    assert not workflow_has_review(workflow(plain))


def test_last_review_is_the_newest() -> None:
    first, last = _review(True), _review(False, blocking=["no"])
    run = WorkflowRun(
        exit_code=0,
        accepted=True,
        adw_id="a",
        envelopes={"review": last},
        history=[("review", first), ("plan", object()), ("review", last)],
    )
    assert last_review(run) is last
    assert last_review(WorkflowRun(exit_code=0, accepted=True, adw_id="a")) is None
    assert last_review(None) is None
