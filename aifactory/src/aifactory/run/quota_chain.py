"""The project's quota chain: the harnesses a run switches to when its harness runs out.

A project sets ``quota_switch: [codex, pi]`` (backup harnesses, in order) and
``quota_switch_back: true|false`` in its ``index.md``; its tasks inherit them. The chain of a
run is ``[primary, *quota_switch]``: ``primary`` is the harness the task's settings give
without the chain (``primary_harness``).

On a ``quota`` failure (``fallback.continue_on_fallback``) the run continues on the next
harness of the chain after the one that ran out that this run has not used yet and that has
quota (``next_harness``). When none is left the run ends ``failed`` with ``quota``. The
project then stays on that harness: ``project_harness`` in the trace DB holds the
project's place in the chain, and new runs start there.

With ``quota_switch_back`` a new run starts one step higher in the chain once that harness
has its limit back (``start_harness``), and so on, step by step, back to the primary.
The return happens only when a new run starts, never between the phases of a run: an agent
on another harness loses its coding-agent session, so a switch in the middle of a run is
only worth it when the current harness cannot go on at all. A manual retry keeps the run's
harness.

Whether a harness has quota is machine state in the trace DB (``harness_quota``): every
quota failure records the harness with the reset time its message gives
(``harness.quota.retry_at``, else one hour), a succeeded run clears the harness it ran on.

A non-empty project chain wins over the ``fallback`` of ``local.yaml`` and ``agents.yaml``
(``fallback.py``); without one the single fallback applies as before.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from aifactory.backlog import Task
from aifactory.backlog.derived import ancestors, effective
from aifactory.harness import canonical

if TYPE_CHECKING:
    from aifactory.config import RunConfig
    from aifactory.run.store import TaskRunStore

SOURCE = "projekt {id} (quota_switch)"
RETURN = "quota_return"
QUOTA = "quota"

__all__ = [
    "QUOTA",
    "RETURN",
    "SOURCE",
    "ProjectChain",
    "Start",
    "next_harness",
    "primary_harness",
    "project_chain",
    "start_harness",
    "start_record",
]


@dataclass(frozen=True)
class ProjectChain:
    """The quota chain of a task's project: ``chain[0]`` is the primary harness."""

    project_id: str
    chain: tuple[str, ...]
    back: bool

    @property
    def primary(self) -> str:
        return self.chain[0]

    @property
    def source(self) -> str:
        return SOURCE.format(id=self.project_id)


@dataclass(frozen=True)
class Start:
    """Where a new run starts in the chain: `harness`, coming from `previous` for `reason`.

    ``reason`` is None (the primary, nothing switched), ``quota`` (the project is lower in
    the chain) or ``quota_return`` (one step back up). ``position`` is the project's new
    place in the chain (None: the primary).
    """

    harness: str
    previous: str | None = None
    reason: str | None = None
    position: str | None = None


def primary_harness(task: Task, rc: RunConfig) -> str | None:
    """The harness `task` runs on without the chain: its settings, else the roster's."""
    from aifactory.harness.settings import effective_override
    from aifactory.run.task import task_harness_values

    try:
        harness = effective_override(task_harness_values(task), None).get("harness")
    except ValueError:
        harness = None
    if harness:
        return harness
    roster = rc.config.agents
    if roster.defaults.harness:
        return canonical(roster.defaults.harness)
    return canonical(roster.agents[0].harness) if roster.agents else None


def project_chain(task: Task, primary: str | None) -> ProjectChain | None:
    """The chain of `task`'s project, or None when it sets no backup harness."""
    if not primary:
        return None
    values = effective(task)
    raw = values.get("quota_switch")
    if not isinstance(raw, list):
        return None
    chain: list[str] = [canonical(primary)]
    for item in raw:
        try:
            name = canonical(str(item).strip())
        except ValueError:
            continue
        if name not in chain:
            chain.append(name)
    if len(chain) < 2:
        return None
    parents = ancestors(task)
    project_id = (parents[-1].id if parents else None) or task.id
    return ProjectChain(project_id, tuple(chain), values.get("quota_switch_back") is True)


def start_harness(store: TaskRunStore, pc: ProjectChain, now: datetime | None = None) -> Start:
    """Where a new run of the project starts (see the module docstring); writes nothing."""
    position = store.project_position(pc.project_id)
    if position is None or position not in pc.chain or position == pc.primary:
        return Start(pc.primary)
    index = pc.chain.index(position)
    upper = pc.chain[index - 1]
    if pc.back and store.quota_available(upper, now):
        return Start(upper, position, RETURN, None if index - 1 == 0 else upper)
    return Start(position, pc.primary, QUOTA, position)


def next_harness(
    store: TaskRunStore,
    pc: ProjectChain,
    exhausted: str,
    tried: set[str],
    now: datetime | None = None,
) -> str | None:
    """The next harness of the chain after `exhausted` not in `tried` that has quota."""
    begin = pc.chain.index(exhausted) + 1 if exhausted in pc.chain else 0
    for harness in pc.chain[begin:]:
        if harness not in tried and harness != exhausted and store.quota_available(harness, now):
            return harness
    return None


def start_record(
    before: dict[str, str], after: dict[str, str], reason: str, pc: ProjectChain
) -> dict[str, Any]:
    """The ``harness_start`` record of a run: the same shape as ``harness_switch``."""
    return {"from": before, "to": after, "reason": reason, "auto": True, "source": pc.source}
