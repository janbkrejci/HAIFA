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
- ``writes_needed``: an agent reported ``status: fail`` with ``fail_kind: needs_writes``:
  the task needs paths its ``writes`` do not cover (the agent's ``needs_writes``).
  ``failure_detail`` holds ``agent``, ``summary``, ``paths`` (the normalized paths) and
  ``needs_writes`` (each path with the agent's reason). ``factory task retry
  --allow-writes`` adds them to ``writes`` like those of a ``writes_violation``.
- ``invalid_output``: an agent never returned a valid envelope (JSON that does not parse
  or validate, or claim gates still red after the corrections).
- ``process_gone``: the run's process died (the run was reaped as ``aborted``).
- ``stopped``: the operator stopped the run (or interrupted its process).
- ``blocked``: an agent reported a blocking follow-up or a blocking existing task
  (``blocks_task``, ``blocked_by``); ``failure_detail`` holds ``blockers``. Not a failure
  for the Overview: it resolves once the blockers are done. A run recorded before the kind
  existed whose error starts with ``blocked: `` reads as ``blocked`` (``shown_kind``).
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
WRITES_NEEDED = "writes_needed"
INVALID_OUTPUT = "invalid_output"
PROCESS_GONE = "process_gone"
STOPPED = "stopped"
BLOCKED = "blocked"
OTHER = "other"
FAILURE_KINDS = (
    ACCEPT_NOT_MET,
    NOTHING_TO_DO,
    QUOTA,
    WRITES_VIOLATION,
    WRITES_NEEDED,
    INVALID_OUTPUT,
    PROCESS_GONE,
    STOPPED,
    BLOCKED,
    OTHER,
)

# the envelope's ``fail_kind`` of an agent that needs paths outside the task's writes
NEEDS_WRITES = "needs_writes"

# the error of a run that ended blocked starts with it (``run.task.blocked_reason``)
BLOCKED_PREFIX = "blocked: "
_BLOCKED_WAITS = " waits for "


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
    """An agent's envelope said ``status: fail``; ``fail_kind`` refines the kind.

    ``fail_kind: nothing_to_do`` is ``nothing_to_do``; ``fail_kind: needs_writes`` with
    paths in `needs_writes` (``[{path, reason}]``) is ``writes_needed``; else ``other``.
    """

    def __init__(
        self,
        agent: str,
        summary: str,
        fail_kind: str | None,
        needs_writes: list[dict[str, str]] | None = None,
    ) -> None:
        needed = needed_paths(needs_writes or [])
        detail: dict[str, Any] = {"agent": agent, "summary": summary[:1000], "fail_kind": fail_kind}
        if fail_kind == NOTHING_TO_DO:
            kind = NOTHING_TO_DO
        elif fail_kind == NEEDS_WRITES and needed:
            kind = WRITES_NEEDED
            detail["paths"] = [item["path"] for item in needed]
            detail["needs_writes"] = needed
        else:
            kind = OTHER
        message = f"{agent} reported status='fail': {summary}"
        if kind == WRITES_NEEDED:
            message += f" (needs writes: {', '.join(detail['paths'])})"
        super().__init__(message, kind=kind, detail=detail)


def normalize_path(path: str) -> str:
    """A repository path as ``writes`` holds it: forward slashes, no leading ``./``."""
    value = path.strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def needed_paths(items: list[Any]) -> list[dict[str, str]]:
    """The ``needs_writes`` items with a path: ``[{path, reason}]``, normalized, unique."""
    out: dict[str, str] = {}
    for item in items:
        path = item.get("path") if isinstance(item, dict) else getattr(item, "path", None)
        reason = item.get("reason") if isinstance(item, dict) else getattr(item, "reason", "")
        if not isinstance(path, str) or not normalize_path(path):
            continue
        key = normalize_path(path)
        text = reason.strip() if isinstance(reason, str) else ""
        if key not in out or (text and not out[key]):
            out[key] = text
    return [{"path": p, "reason": r} for p, r in out.items()]


def shown_kind(kind: str | None, error: str | None) -> str:
    """The kind of an ended unsuccessful run as shown: the stored one, else from `error`.

    A run recorded without a kind is ``blocked`` when its error starts with
    ``BLOCKED_PREFIX``, otherwise ``other``.
    """
    if kind:
        return kind
    return BLOCKED if (error or "").startswith(BLOCKED_PREFIX) else OTHER


def blocked_error(task_id: str, blockers: list[str]) -> str:
    """The error of a run that ended blocked on `blockers` (``error_blockers`` reads it)."""
    return f"{BLOCKED_PREFIX}task {task_id}{_BLOCKED_WAITS}{', '.join(blockers)}"


def error_blockers(error: str | None) -> list[str] | None:
    """The blockers named by a blocked run's `error`; None when it is not one."""
    text = error or ""
    if not text.startswith(BLOCKED_PREFIX):
        return None
    head = text.split(";", 1)[0]
    _, sep, waits = head.partition(_BLOCKED_WAITS)
    if not sep:
        return []
    return [part.strip() for part in waits.split(", ") if part.strip()]


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
