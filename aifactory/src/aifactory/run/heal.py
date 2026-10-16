"""Self-healing of an auto-continue chain: the safe action after a failure, by its kind.

When a run of a chain that goes on (``--auto`` or ``auto_continue``) fails, the chain
acts by the run's ``failure_kind`` (``aifactory.failure``):

- ``quota``: the run already continued on the configured fallback harness
  (``fallback.continue_on_fallback``, inside ``run_task``/``retry_run``); the chain only
  records that switch (``switch_event``) and goes on when the fallback succeeded.
- ``process_gone``: the run's process died; the chain retries the run once
  (``retry_run``) and goes on with the retry.
- ``nothing_to_do`` with the agent's reason (its ``summary``, the evidence): the chain
  marks the task done in ``base`` without changes (``unchanged.finish_nothing_to_do``)
  and goes on as after a run that changed nothing.
- every other kind (and ``nothing_to_do`` without a reason) is left to the operator:
  the chain stops ``failed`` as before.

Each run is healed at most once. ``auto_heal`` (inherited like ``auto_continue``, default
``true``; ``auto_heal: false`` in a task, step or project switches it off) disables every
automatic action of the task, the quota fallback of a single run included.

Every action is a chain event (``HealEvent``), stored in ``task_chains.events`` and shown
on the Overview, e.g. „Factory pokračovala na Claude Code po vyčerpání kvóty Codexu“.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aifactory import failure as failures
from aifactory.backlog import Task, TaskEditError, effective
from aifactory.engine.utils import now_iso
from aifactory.providers import GitProvider
from aifactory.run.errors import TaskRunError
from aifactory.run.fallback import SWITCH_KEY
from aifactory.run.store import FAILED, SUCCEEDED
from aifactory.workflow import CodeRunner

if TYPE_CHECKING:
    from aifactory.run.task import TaskRunResult

ACTION_FALLBACK, ACTION_RETRY, ACTION_CLOSE = "fallback", "retry", "close"
HEAL_ACTIONS: tuple[str, ...] = (ACTION_FALLBACK, ACTION_RETRY, ACTION_CLOSE)

# how the Overview names a harness: (nominative, genitive)
_HARNESS_NAMES: dict[str, tuple[str, str]] = {
    "claude": ("Claude Code", "Claude Code"),
    "codex": ("Codex", "Codexu"),
    "pi": ("pi", "pi"),
}

__all__ = [
    "ACTION_CLOSE",
    "ACTION_FALLBACK",
    "ACTION_RETRY",
    "HEAL_ACTIONS",
    "HealEvent",
    "Healing",
    "auto_heal_enabled",
    "heal",
    "switch_event",
]


def auto_heal_enabled(task: Task) -> bool:
    """Whether the chain may act on a failure of `task` (``auto_heal``, default true)."""
    return effective(task).get("auto_heal") is not False


@dataclass(frozen=True)
class HealEvent:
    """One automatic action of a chain: what, on which run, and whether it helped."""

    action: str  # HEAL_ACTIONS
    failure_kind: str
    task_id: str
    run_id: str
    ok: bool
    text: str
    at: str = ""
    detail: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "at": self.at or str(now_iso()),
            "action": self.action,
            "failure_kind": self.failure_kind,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "ok": self.ok,
            "text": self.text,
        }
        if self.detail:
            data["detail"] = dict(self.detail)
        return data


@dataclass
class Healing:
    """The outcome of ``heal``: the event, the newest result of the run, whether to go on."""

    event: HealEvent
    result: TaskRunResult | None  # the retry or the closed run; None: nothing new ran
    goes_on: bool  # False: the action did not help, the chain stops


def _name(harness: object, case: int) -> str:
    key = str(harness or "?")
    names = _HARNESS_NAMES.get(key)
    return names[case] if names is not None else key


def switch_text(record: dict[str, Any]) -> str:
    """„Factory pokračovala na Claude Code po vyčerpání kvóty Codexu“ for a quota switch."""
    before = record.get("from") or {}
    after = record.get("to") or {}
    return (
        f"Factory pokračovala na {_name(after.get('harness'), 0)} "
        f"po vyčerpání kvóty {_name(before.get('harness'), 1)}"
    )


def switch_event(result: TaskRunResult, since: str) -> HealEvent | None:
    """The automatic quota fallback of `result` that started at or after `since`, if any."""
    retries = result.run.retry_list()
    if not retries:
        return None
    last = retries[-1]
    record = last.get(SWITCH_KEY)
    if not isinstance(record, dict) or not record.get("auto"):
        return None
    if str(last.get("started_at") or "") < since:
        return None
    ok = result.ok
    text = switch_text(record)
    if not ok:
        text += "; běh selhal i tam"
    return HealEvent(
        ACTION_FALLBACK,
        str(record.get("reason") or failures.QUOTA),
        result.run.task_id,
        result.run.run_id,
        ok,
        text,
        at=str(last.get("started_at") or ""),
        detail={"from": record.get("from"), "to": record.get("to")},
    )


def _event(result: TaskRunResult, action: str, ok: bool, text: str) -> HealEvent:
    run = result.run
    return HealEvent(action, run.failure_kind or failures.OTHER, run.task_id, run.run_id, ok, text)


def _retry(
    repo: Path,
    result: TaskRunResult,
    code: CodeRunner | None,
    provider: GitProvider | None,
    retry: Callable[..., TaskRunResult] | None,
) -> Healing:
    # Module attribute: a patched `retry_run` applies here too.
    from aifactory.run import retry as retry_mod

    run = result.run
    runner = retry if retry is not None else retry_mod.retry_run
    try:
        retried = runner(repo, run.task_id, run_id=run.run_id, code=code, provider=provider)
    except TaskRunError as exc:
        text = f"Factory nezopakovala běh {run.run_id} po pádu procesu: {exc.code}: {exc.message}"
        return Healing(_event(result, ACTION_RETRY, False, text), None, False)
    if retried.ok:
        text = f"Factory zopakovala běh {run.run_id} po pádu procesu"
    else:
        text = f"Factory zopakovala běh {run.run_id} po pádu procesu; opakování selhalo"
    event = _event(result, ACTION_RETRY, retried.ok, text)
    return Healing(event, retried, retried.ok)


def _close(repo: Path, result: TaskRunResult) -> Healing | None:
    from aifactory.run.unchanged import finish_nothing_to_do

    run = result.run
    detail = run.failure_detail_dict() or {}
    reason = str(detail.get("summary") or "").strip()
    if not reason:
        return None  # no evidence: left to the operator
    try:
        finish_nothing_to_do(repo, run.run_id)
    except (TaskRunError, TaskEditError) as exc:
        text = f"Factory neuzavřela task {run.task_id} bez změn: {exc.code}: {exc.message}"
        return Healing(_event(result, ACTION_CLOSE, False, text), None, False)
    short = " ".join(reason.split())
    if len(short) > 200:
        short = short[:199] + "…"
    text = f"Factory uzavřela task {run.task_id} jako hotový bez změn: {short}"
    event = _event(result, ACTION_CLOSE, True, text)
    return Healing(event, _closed_result(result), True)


def _closed_result(result: TaskRunResult) -> TaskRunResult:
    from dataclasses import replace

    return replace(result, done_without_pr=True, closed_by_heal=True)


def heal(
    repo: Path,
    result: TaskRunResult,
    task: Task,
    *,
    code: CodeRunner | None = None,
    provider: GitProvider | None = None,
    retry: Callable[..., TaskRunResult] | None = None,
) -> Healing | None:
    """The automatic action for the failed run `result` of `task`; None: left to a person.

    Only a ``failed`` or ``aborted`` run with ``auto_heal`` on is acted on. `retry`
    replaces ``retry_run`` (the parallel chain passes its own).
    """
    run = result.run
    if run.state == SUCCEEDED or not auto_heal_enabled(task):
        return None
    kind = run.shown_failure_kind
    if kind == failures.PROCESS_GONE:
        return _retry(repo, result, code, provider, retry)
    if kind == failures.NOTHING_TO_DO and run.state == FAILED:
        return _close(repo, result)
    return None
