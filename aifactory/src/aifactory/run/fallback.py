"""Quota fallback: a run whose harness ran out of quota continues on another harness.

When a run (``run_task``) or its retry (``retry_run``) ends ``failed`` with
``failure_kind: quota`` and a fallback is configured (``harness/fallback.py``: ``local.yaml``
first, then the agent's own ``fallback`` in ``agents.yaml``, then ``defaults.fallback``),
the factory retries the run once with every agent on the fallback harness
(``retry_run(agents_override=...)``). The agents of the continuing phases get the usual
``## Continuation`` section; with another harness or model they start a new session.

The fallback is tried at most once: a retry that was itself a harness switch (automatic,
or the operator's from the dashboard) never switches again, and a fallback on the harness
that ran out is not tried. When the fallback fails too, the run ends failed with the kind
of that failure (``quota`` when the fallback ran out as well).

A task with ``auto_heal: false`` (``heal.py``) is never switched automatically.

The switch is recorded as ``harness_switch`` in the retry's entry of ``task_runs.retries``
and logged in the ``request`` phase of the attempt (the run's events); the PR body lists it.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aifactory import failure as failures
from aifactory.config import RunConfig
from aifactory.harness.fallback import Fallback
from aifactory.providers import GitProvider
from aifactory.run.errors import TaskRunError
from aifactory.run.store import FAILED, TaskRunRow
from aifactory.workflow import CodeRunner

if TYPE_CHECKING:
    from aifactory.run.task import TaskRunResult

SWITCH_KEY = "harness_switch"
SOURCE_LOCAL = "local.yaml"
SOURCE_AGENT = "agents.yaml (agent)"
SOURCE_DEFAULTS = "agents.yaml (defaults)"

__all__ = [
    "SWITCH_KEY",
    "configured_fallback",
    "continue_on_fallback",
    "harness_switch",
    "harness_switches",
    "switch_text",
]


def configured_fallback(rc: RunConfig, agent: str | None) -> tuple[Fallback, str] | None:
    """The fallback for a quota failure of `agent` and where it is set; None without one.

    ``local.yaml`` wins over the agent's ``fallback`` in ``agents.yaml``, which wins over
    ``defaults.fallback``.
    """
    local: Fallback | None = getattr(rc.local, "fallback", None)
    if local is not None:
        return local, SOURCE_LOCAL
    roster = rc.config.agents
    for entry in roster.agents:
        own: Fallback | None = getattr(entry, "fallback", None)
        if entry.name == agent and own is not None:
            return own, SOURCE_AGENT
    shared: Fallback | None = getattr(roster.defaults, "fallback", None)
    if shared is not None:
        return shared, SOURCE_DEFAULTS
    return None


def _side(values: dict[str, Any]) -> dict[str, str]:
    return {k: str(values[k]) for k in ("harness", "model", "thinking") if values.get(k)}


def harness_switch(
    row: TaskRunRow,
    binding: dict[str, str],
    *,
    auto: bool,
    source: str | None = None,
    previous: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The record of a switch to `binding`: from where, to where and why."""
    detail = row.failure_detail_dict() or {}
    before = _side(detail) if detail.get("harness") else dict(previous or {})
    record: dict[str, Any] = {
        "from": before,
        "to": _side(binding),
        "reason": row.failure_kind or "operator",
        "auto": auto,
    }
    if detail.get("agent"):
        record["agent"] = str(detail["agent"])
    if source:
        record["source"] = source
    return record


def _label(side: dict[str, Any]) -> str:
    harness = str(side.get("harness") or "?")
    model = side.get("model")
    return f"{harness}/{model}" if model else harness


def switch_text(record: dict[str, Any]) -> str:
    """One line about a switch: ``codex/gpt-6.1-sol → claude/claude-opus-5-5 (quota, ...)``."""
    why = [str(record.get("reason") or "operator")]
    why.append("automaticky" if record.get("auto") else "operátor")
    if record.get("source"):
        why.append(f"záloha z {record['source']}")
    if record.get("agent"):
        why.append(f"agent {record['agent']}")
    before = record.get("from") or {}
    after = record.get("to") or {}
    return f"{_label(before)} → {_label(after)} ({', '.join(why)})"


def harness_switches(runs: Iterable[TaskRunRow]) -> list[str]:
    """One line per harness switch of `runs`, oldest first (the PR body lists them)."""
    lines: list[str] = []
    for row in runs:
        for number, retry in enumerate(row.retry_list(), start=2):
            record = retry.get(SWITCH_KEY)
            if isinstance(record, dict):
                lines.append(f"běh {row.run_id}, pokus {number}: {switch_text(record)}")
    return lines


def continue_on_fallback(
    main: Path,
    result: TaskRunResult,
    *,
    code: CodeRunner | None = None,
    provider: GitProvider | None = None,
    enabled: bool = True,
) -> TaskRunResult:
    """`result`, or the result of its retry on the fallback harness after a quota failure.

    Nothing happens unless the run failed with ``quota``, a fallback is configured and it
    is another harness than the one that ran out. A retry that cannot start leaves the run
    failed with ``quota`` and adds a warning. ``enabled=False`` (the task's ``auto_heal:
    false``, ``heal.py``) never switches.
    """
    from aifactory.run import task as run_mod
    from aifactory.run.retry import retry_run

    run = result.run
    if run.state != FAILED or run.failure_kind != failures.QUOTA:
        return result
    if not enabled:
        result.warnings = (*result.warnings, "quota fallback skipped: auto_heal is off")
        return result
    detail = run.failure_detail_dict() or {}
    try:
        rc = run_mod._load(main)
    except TaskRunError:
        return result
    agent = detail.get("agent")
    found = configured_fallback(rc, agent if isinstance(agent, str) else None)
    if found is None:
        return result
    fallback, source = found
    if fallback.harness == detail.get("harness"):
        result.warnings = (
            *result.warnings,
            f"quota fallback skipped: {source} names {fallback.harness}, the harness that ran out",
        )
        return result
    try:
        retried = retry_run(
            main,
            run.task_id,
            run_id=run.run_id,
            code=code,
            provider=provider,
            agents_override=fallback.override(),
            switch={"auto": True, "source": source},
        )
    except TaskRunError as exc:
        result.warnings = (
            *result.warnings,
            f"quota fallback to {fallback.harness} did not start: {exc.code}: {exc.message}",
        )
        return result
    retries = retried.run.retry_list()
    record = retries[-1].get(SWITCH_KEY) if retries else None
    switched = (f"quota: switched {switch_text(record)}",) if isinstance(record, dict) else ()
    retried.warnings = (*result.warnings, *switched, *retried.warnings)
    return retried
