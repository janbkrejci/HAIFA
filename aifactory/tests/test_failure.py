"""``aifactory.failure``: the kind travels on the exception raised where the failure arose."""

from __future__ import annotations

import pytest

from aifactory import failure
from aifactory.run import task as task_mod


def test_classify_reads_the_kind_of_the_exception() -> None:
    exc = failure.InvalidOutput("bad", detail={"agent": "builder"})
    assert failure.classify(exc) == (failure.INVALID_OUTPUT, {"agent": "builder"})


def test_classify_follows_the_cause() -> None:
    quota = failure.QuotaExhausted("codex", "usage limit")
    try:
        try:
            raise quota
        except failure.QuotaExhausted as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        kind, detail = failure.classify(outer)
    assert kind == failure.QUOTA and detail["harness"] == "codex"


def test_unknown_exception_is_other() -> None:
    assert failure.classify(ValueError("x")) == (failure.OTHER, {"error_type": "ValueError"})


def test_agent_reported_fail_kinds() -> None:
    assert failure.AgentReportedFail("b", "s", "nothing_to_do").failure_kind == "nothing_to_do"
    assert failure.AgentReportedFail("b", "s", "anything").failure_kind == failure.OTHER


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (KeyboardInterrupt(), failure.STOPPED),
        (SystemExit(143), failure.STOPPED),
        (SystemExit(1), failure.OTHER),
    ],
)
def test_interrupted_run(exc: BaseException, kind: str) -> None:
    assert task_mod._interrupt_failure(exc)[0] == kind
