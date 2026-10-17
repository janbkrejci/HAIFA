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

Precedence: when the task's project sets a quota chain (``quota_switch`` in its
``index.md``, ``quota_chain.py``), the chain applies and the ``fallback`` of ``local.yaml``
and ``agents.yaml`` is ignored for the run. The run then walks the chain: each retry that
was a chain switch may be followed by the next one, until a harness finishes or the chain
is used up. Without a project chain the single fallback above applies, tried once.
Every quota failure is recorded in the trace DB (``harness_quota``), with or without a
switch, so the chain skips a harness that is still out.

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
from aifactory.run.store import FAILED, TaskRunRow, TaskRunStore
from aifactory.workflow import CodeRunner

if TYPE_CHECKING:
    from aifactory.backlog import Task
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
    "mark_quota",
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
    reason = str(record.get("reason") or "operator")
    why = ["návrat (limit obnoven)" if reason == "quota_return" else reason]
    why.append("automaticky" if record.get("auto") else "operátor")
    if record.get("source"):
        why.append(f"záloha z {record['source']}")
    if record.get("agent"):
        why.append(f"agent {record['agent']}")
    before = record.get("from") or {}
    after = record.get("to") or {}
    return f"{_label(before)} → {_label(after)} ({', '.join(why)})"


def harness_switches(runs: Iterable[TaskRunRow]) -> list[str]:
    """One line per harness switch of `runs`, oldest first (the PR body lists them).

    The switch a run started with (the project's quota chain, ``harness_start``) comes
    before the switches of its retries.
    """
    lines: list[str] = []
    for row in runs:
        start = row.harness_start_dict()
        if start is not None:
            lines.append(f"běh {row.run_id}, start: {switch_text(start)}")
        for number, retry in enumerate(row.retry_list(), start=2):
            record = retry.get(SWITCH_KEY)
            if isinstance(record, dict):
                lines.append(f"běh {row.run_id}, pokus {number}: {switch_text(record)}")
    return lines


def _tried(run: TaskRunRow, exhausted: str) -> set[str]:
    """The harnesses `run` has run on so far, `exhausted` included."""
    tried = {exhausted}
    start = run.harness_start_dict()
    if start is not None and (start.get("to") or {}).get("harness"):
        tried.add(str(start["to"]["harness"]))
    for retry in run.retry_list():
        record = retry.get(SWITCH_KEY)
        if not isinstance(record, dict):
            continue
        for side in ("from", "to"):
            harness = (record.get(side) or {}).get("harness")
            if harness:
                tried.add(str(harness))
    return tried


def mark_quota(store: TaskRunStore, detail: dict[str, Any]) -> None:
    """Record the harness of a quota failure as out of quota until its reset time."""
    from aifactory.harness.quota import retry_at

    harness = detail.get("harness")
    if not isinstance(harness, str) or not harness:
        return
    message = str(detail.get("message") or "")
    when = retry_at(message).isoformat(timespec="milliseconds")
    store.mark_quota(harness, message, when)


def continue_on_fallback(
    main: Path,
    result: TaskRunResult,
    *,
    code: CodeRunner | None = None,
    provider: GitProvider | None = None,
    enabled: bool = True,
    task: Task | None = None,
) -> TaskRunResult:
    """`result`, or the result of its retry on another harness after a quota failure.

    Nothing happens unless the run failed with ``quota``. With a project chain (`task`'s
    ``quota_switch``) the run continues on the chain's next harness that it has not used
    and that has quota; without one, on the configured fallback when it is another harness
    than the one that ran out. A retry that cannot start leaves the run failed with
    ``quota`` and adds a warning. ``enabled=False`` (the task's ``auto_heal: false``,
    ``heal.py``) never switches.
    """
    from aifactory.run import task as run_mod
    from aifactory.run.retry import retry_run

    run = result.run
    if run.state != FAILED or run.failure_kind != failures.QUOTA:
        return result
    detail = run.failure_detail_dict() or {}
    try:
        rc = run_mod._load(main)
    except TaskRunError:
        return result
    store = TaskRunStore(rc.local.trace_db_path(main))
    try:
        mark_quota(store, detail)
        if not enabled:
            result.warnings = (*result.warnings, "quota fallback skipped: auto_heal is off")
            return result
        chained = _chain_target(store, rc, run, detail, task)
    finally:
        store.close()
    if chained is not None:
        target, source, warning = chained
        if target is None:
            result.warnings = (*result.warnings, warning)
            return result
        override: dict[str, str] = {"harness": target}
        switch: dict[str, Any] = {"auto": True, "source": source, "chain": True}
    else:
        agent = detail.get("agent")
        found = configured_fallback(rc, agent if isinstance(agent, str) else None)
        if found is None:
            return result
        fallback, source = found
        if fallback.harness == detail.get("harness"):
            result.warnings = (
                *result.warnings,
                f"quota fallback skipped: {source} names {fallback.harness}, "
                "the harness that ran out",
            )
            return result
        target, override = fallback.harness, fallback.override()
        switch = {"auto": True, "source": source}
    try:
        retried = retry_run(
            main,
            run.task_id,
            run_id=run.run_id,
            code=code,
            provider=provider,
            agents_override=override,
            switch=switch,
        )
    except TaskRunError as exc:
        result.warnings = (
            *result.warnings,
            f"quota fallback to {target} did not start: {exc.code}: {exc.message}",
        )
        return result
    retries = retried.run.retry_list()
    record = retries[-1].get(SWITCH_KEY) if retries else None
    switched = (f"quota: switched {switch_text(record)}",) if isinstance(record, dict) else ()
    retried.warnings = (*result.warnings, *switched, *retried.warnings)
    return retried


def _chain_target(
    store: TaskRunStore,
    rc: RunConfig,
    run: TaskRunRow,
    detail: dict[str, Any],
    task: Task | None,
) -> tuple[str | None, str, str] | None:
    """With a project chain: (the next harness or None, the source, the warning when none).

    None without a project chain (the configured fallback applies). The project's place in
    the chain moves to the next harness here, before its retry starts.
    """
    from aifactory.run.quota_chain import next_harness, primary_harness, project_chain

    if task is None:
        return None
    pc = project_chain(task, primary_harness(task, rc))
    if pc is None:
        return None
    exhausted = str(detail.get("harness") or "")
    target = next_harness(store, pc, exhausted, _tried(run, exhausted))
    if target is None:
        return None, pc.source, f"quota: chain of project {pc.project_id} exhausted"
    store.set_project_position(pc.project_id, None if target == pc.primary else target)
    return target, pc.source, ""
