"""Intent progress carries locale-neutral metadata alongside preserved legacy text."""

import json
from pathlib import Path
from typing import Any, NoReturn

import pytest

from aifactory.web.intent import _progress_item


@pytest.mark.parametrize(
    ("event", "code", "params"),
    [
        (
            {"type": "agent_start", "name": "proposer", "payload": {"model": "model-x"}},
            "agent_start",
            {"name": "proposer", "model": "model-x"},
        ),
        (
            {"type": "agent_start", "name": "proposer"},
            "agent_start",
            {"name": "proposer", "model": ""},
        ),
        ({"type": "gate_fail"}, "gate_fail", None),
        ({"type": "agent_end"}, "agent_end", None),
        ({"type": "log", "name": "provider_backoff"}, "provider_backoff", None),
        ({"type": "log", "name": "session_fallback"}, "session_fallback", None),
        (
            {"type": "error", "payload": {"error": "Uložená chyba"}},
            "error",
            {"error": "Uložená chyba"},
        ),
    ],
)
def test_progress_metadata(event: dict[str, Any], code: str, params: dict[str, str] | None) -> None:
    line = json.dumps({**event, "ts": "2026-01-01"}, ensure_ascii=False)
    first = _progress_item(line)
    assert first is not None
    assert first["code"] == code
    assert first.get("params") == params
    assert first["ts"] == "2026-01-01"
    assert first["text"]
    # Another client reads the same event without a shared server locale.
    assert _progress_item(line) == first


def test_tool_names_and_unknown_events_are_not_translated() -> None:
    item = _progress_item(json.dumps({"type": "tool_call", "name": "Read soubor"}))
    assert item == {"kind": "tool_call", "text": "Read soubor", "ts": ""}
    assert _progress_item('{"type":"unhandled"}') is None
    assert _progress_item("invalid JSON") is None


@pytest.mark.parametrize("task_parameters", [False, True])
def test_advice_failure_exposes_code_without_changing_stored_error(
    tmp_path: Path, task_parameters: bool
) -> None:
    from aifactory.web.workflow_advice import AdviceManager, Job

    def fail(*args: Any) -> NoReturn:
        raise RuntimeError("private runtime detail")

    manager = AdviceManager(fail, task_parameters=task_parameters)
    job = Job(id="job-1", repo=tmp_path, context={}, fingerprint="draft")
    try:
        manager._run(job)
        expected = "task_advice_failed" if task_parameters else "workflow_advice_failed"
        assert job.json()["state"] == "failed"
        assert job.json()["error_code"] == expected
        assert "Agent nedokončil" in job.json()["error"]
    finally:
        manager.close()


def test_intent_failure_exposes_code_without_changing_stored_error(tmp_path: Path) -> None:
    from contextlib import ExitStack

    from aifactory.web.intent import IntentJob, IntentManager
    from aifactory.workflow.propose import Target

    def fail(*args: Any, **kwargs: Any) -> NoReturn:
        raise RuntimeError("private runtime detail")

    manager = IntentManager(fail)
    job = IntentJob(
        id="intent-1",
        repo=tmp_path,
        intent="Uživatelský záměr",
        target=Target(),
        workdir=tmp_path,
        stack=ExitStack(),
    )
    try:
        manager._run(job, None)
        assert job.json()["state"] == "failed"
        assert job.json()["error_code"] == "proposal_failed"
        assert job.json()["error"] == "Agent nedokončil návrh. Zkus to znovu."
        assert job.json()["intent"] == "Uživatelský záměr"
    finally:
        manager.close()


@pytest.mark.parametrize("task_parameters", [False, True])
def test_advice_validation_failure_exposes_code_and_preserves_diagnostic(
    tmp_path: Path, task_parameters: bool
) -> None:
    from aifactory.errors import UsageError
    from aifactory.web.workflow_advice import AdviceManager, Job

    diagnostic = "proposed workflow is unavailable"

    def fail(*args: Any) -> NoReturn:
        raise UsageError(diagnostic)

    manager = AdviceManager(fail, task_parameters=task_parameters)
    job = Job(id="invalid-advice", repo=tmp_path, context={}, fingerprint="user draft")
    try:
        manager._run(job)
        result = job.json()
        assert result["state"] == "failed"
        assert result["error_code"] == "advice_invalid"
        assert result["error"] == diagnostic
        assert result["fingerprint"] == "user draft"
    finally:
        manager.close()
