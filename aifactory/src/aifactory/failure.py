"""The kind of a failed task run: a typed field next to the free text of ``task_runs.error``.

A run that did not succeed records one of ``FAILURE_KINDS`` in ``task_runs.failure_kind``
and a JSON object with the facts in ``task_runs.failure_detail``:

- ``accept_not_met``: the workflow ran to its end, its ``accept`` was false.
- ``nothing_to_do``: an agent reported ``status: fail`` with ``fail_kind: nothing_to_do``
  (the work is done already or the task asks for no change).
- ``quota``: the harness reported an exhausted quota or credit (recognized by the
  harness adapter, ``QuotaExhausted``).
- ``writes_violation``: an agent wrote outside its worktree or its ``writes``
  (``engine.permissions.PermissionBreach``, raised by the write guard).
- ``invalid_output``: an agent never returned a valid envelope (JSON that does not parse
  or validate, or claim gates still red after the corrections).
- ``process_gone``: the run's process died (the run was reaped as ``aborted``).
- ``stopped``: the operator stopped the run (or interrupted its process).
- ``other``: anything else. Runs recorded before the field existed read as ``other``.

Each kind is decided where the failure arises: the exception raised there carries it
(``failure_kind`` and ``failure_detail`` attributes), ``classify`` only reads them.
"""

from __future__ import annotations

from typing import Any

ACCEPT_NOT_MET = "accept_not_met"
NOTHING_TO_DO = "nothing_to_do"
QUOTA = "quota"
WRITES_VIOLATION = "writes_violation"
INVALID_OUTPUT = "invalid_output"
PROCESS_GONE = "process_gone"
STOPPED = "stopped"
OTHER = "other"
FAILURE_KINDS = (
    ACCEPT_NOT_MET,
    NOTHING_TO_DO,
    QUOTA,
    WRITES_VIOLATION,
    INVALID_OUTPUT,
    PROCESS_GONE,
    STOPPED,
    OTHER,
)


class RunFailure(RuntimeError):
    """A failure that knows its kind; ``detail`` holds JSON-ready facts about it."""

    failure_kind: str = OTHER

    def __init__(
        self, message: str, *, kind: str | None = None, detail: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        if kind is not None:
            self.failure_kind = kind
        self.failure_detail: dict[str, Any] = dict(detail or {})


class QuotaExhausted(RunFailure):
    """The harness reports an exhausted quota, usage limit or credit balance."""

    failure_kind = QUOTA

    def __init__(self, harness: str, message: str) -> None:
        text = message.strip()
        super().__init__(
            f"{harness}: quota exhausted: {text[-800:]}",
            detail={"harness": harness, "message": text[-500:]},
        )


class InvalidOutput(RunFailure):
    """An agent never returned a valid envelope."""

    failure_kind = INVALID_OUTPUT


class AgentReportedFail(RunFailure):
    """An agent's envelope said ``status: fail``; ``fail_kind`` refines the kind."""

    def __init__(self, agent: str, summary: str, fail_kind: str | None) -> None:
        kind = NOTHING_TO_DO if fail_kind == NOTHING_TO_DO else OTHER
        super().__init__(
            f"{agent} reported status='fail': {summary}",
            kind=kind,
            detail={"agent": agent, "summary": summary[:1000], "fail_kind": fail_kind},
        )


def classify(exc: BaseException) -> tuple[str, dict[str, Any]]:
    """The kind and detail of `exc` (or of the error it was raised from), else ``other``."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        kind = getattr(current, "failure_kind", None)
        if isinstance(kind, str) and kind in FAILURE_KINDS:
            detail = getattr(current, "failure_detail", None)
            return kind, dict(detail) if isinstance(detail, dict) else {}
        current = current.__cause__
    return OTHER, {"error_type": type(exc).__name__}
