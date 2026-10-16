"""New work and blockers the agents of a run reported, filed in the backlog.

Agents never leave open work in the repository. Work that a task run found but does not
finish comes back in an envelope's ``follow_ups``; ``record`` files each one as a task
in the project's ``TODO`` step (the step is created when it is missing) and says where
and why it came from. A follow-up with ``blocks_task`` and every not-done id in
``blocked_by`` become ``depends_on`` of the task: the run then fails as blocked
(``run/task.py``), so the task is neither done nor merged until its blockers are done.
A follow-up with ``writes`` gets them as its own ``writes`` (they replace the inherited
value), for work outside the paths this task may change.

The backlog is written in the main checkout through ``aifactory.backlog.edit`` and
committed to ``base``. A follow-up task carries the marker
``<!-- factory: follow-up-of=<task id> -->``; a retry or a replayed journal finds it
by the marker and title and creates nothing new.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from aifactory.backlog import (
    Container,
    Task,
    TaskEditError,
    add_container,
    add_task,
    commit_backlog,
    find_task,
    is_done,
    link_task,
    load_for_edit,
)
from aifactory.backlog.edit import compose_id
from aifactory.workflow import WorkflowRun

TODO_CODE = "TODO"
TODO_TITLE = "TODO"
TODO_BODY = (
    "Práce, která vznikla při zpracování jiných tasků a nevešla se do nich. "
    "Tasky sem zakládá factory z hlášení agentů (follow_ups)."
)


def follow_up_marker(task_id: str) -> str:
    return f"<!-- factory: follow-up-of={task_id} -->"


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


@dataclass(frozen=True)
class Reported:
    """A follow-up as an agent reported it, with the step and agent that did."""

    step: str
    owner: str
    title: str
    reason: str
    details: str
    blocks_task: bool
    writes: tuple[str, ...] | None = None


@dataclass(frozen=True)
class CreatedFollowUp:
    """A follow-up task in the backlog (``existed``: an earlier attempt filed it)."""

    id: str
    title: str
    reason: str
    blocks: bool
    existed: bool = False

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "reason": self.reason,
            "blocks": self.blocks,
            "existed": self.existed,
        }


@dataclass
class FollowUpOutcome:
    """What ``record`` wrote: follow-up tasks, the ids that block the task, the TODO step."""

    created: list[CreatedFollowUp] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    step_id: str | None = None
    committed: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, object]:
        return {
            "created": [c.to_json() for c in self.created],
            "blocked_by": list(self.blocked_by),
            "step": self.step_id,
            "committed": self.committed,
            "warnings": list(self.warnings),
        }


def _owners(wf: WorkflowRun) -> dict[str, str]:
    return {record.step: record.owner for record in wf.records}


def collect(wf: WorkflowRun) -> tuple[list[Reported], list[str]]:
    """Follow-ups and ``blocked_by`` ids of every envelope of the run, deduplicated.

    Follow-ups are one per title (whitespace and case do not count); the first report
    wins, but the follow-up blocks the task when any report of it does.
    """
    owners = _owners(wf)
    reported: dict[str, Reported] = {}
    blocked: list[str] = []
    for key, envelope in wf.history:
        for item in getattr(envelope, "follow_ups", None) or []:
            title = str(getattr(item, "title", "") or "").strip()
            if not title:
                continue
            blocks = bool(getattr(item, "blocks_task", False))
            known = reported.get(_norm(title))
            if known is not None:
                if blocks and not known.blocks_task:
                    reported[_norm(title)] = Reported(
                        known.step,
                        known.owner,
                        known.title,
                        known.reason,
                        known.details,
                        True,
                        known.writes,
                    )
                continue
            reported[_norm(title)] = Reported(
                step=str(key),
                owner=owners.get(str(key), ""),
                title=title,
                reason=str(getattr(item, "reason", "") or "").strip(),
                details=str(getattr(item, "details", "") or "").strip(),
                blocks_task=blocks,
                writes=_writes(getattr(item, "writes", None)),
            )
        for raw in getattr(envelope, "blocked_by", None) or []:
            value = str(raw).strip()
            if value and value not in blocked:
                blocked.append(value)
    return list(reported.values()), blocked


def _writes(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    paths = [str(v).strip() for v in value if str(v).strip()]
    return tuple(dict.fromkeys(paths)) or None


def reported_any(wf: WorkflowRun) -> bool:
    reported, blocked = collect(wf)
    return bool(reported or blocked)


def reported_blockers(wf: WorkflowRun) -> bool:
    """Whether an agent of the run said the task cannot be finished yet."""
    reported, blocked = collect(wf)
    return bool(blocked) or any(r.blocks_task for r in reported)


def _todo_step(project: Container | None, roots: list[Container]) -> Container | None:
    children = project.children if project is not None else roots
    wanted = compose_id(project.id if project is not None else None, TODO_CODE)
    for child in children:
        if child.id == wanted or _norm(child.title or "") == _norm(TODO_TITLE):
            return child
    return None


def _task_body(item: Reported, task: Task, run_id: str) -> str:
    text = item.details or item.reason
    where = f"v kroku `{item.step}`" + (f" (agent {item.owner})" if item.owner else "")
    lines = [
        text,
        "",
        "### Původ",
        "",
        f"Vznikl při běhu `{run_id}` tasku `{task.id}` ({task.title}), {where}.",
        f"Důvod: {item.reason}",
    ]
    if item.blocks_task:
        lines.append(
            f"Task `{task.id}` na tomto tasku závisí a do jeho dokončení zůstává blokovaný."
        )
    lines += ["", follow_up_marker(task.id)]
    return "\n".join(lines) + "\n"


def _existing(step: Container, task_id: str, title: str) -> Task | None:
    marker = follow_up_marker(task_id)
    for candidate in step.tasks:
        if marker in candidate.body and _norm(candidate.title) == _norm(title):
            return candidate
    return None


def _error(exc: TaskEditError) -> str:
    return f"{exc.code}: {exc.message}"


def record(main: Path, task_id: str, run_id: str, wf: WorkflowRun) -> FollowUpOutcome:
    """File the run's follow-ups in the TODO step and link the task to its blockers.

    Returns what was written; problems that do not stop the rest (an unknown id, a
    rejected write, a commit that failed) are ``warnings``. A blocker counts even when
    its ``depends_on`` could not be written.
    """
    outcome = FollowUpOutcome()
    reported, blocked_ids = collect(wf)
    if not reported and not blocked_ids:
        return outcome
    backlog = load_for_edit(main)
    task = find_task(backlog, task_id)
    project = task.parent.parent
    wrote = False
    blockers: list[str] = []

    if reported:
        step = _todo_step(project, backlog.containers)
        if step is None:
            try:
                added = add_container(
                    main,
                    project.id if project is not None else None,
                    TODO_CODE,
                    TODO_TITLE,
                    body=TODO_BODY,
                )
                step, wrote = added.container, True
            except TaskEditError as exc:
                outcome.warnings.append(f"TODO step not created: {_error(exc)}")
        if step is not None:
            outcome.step_id = step.id
            for item in reported:
                found = _existing(step, task_id, item.title)
                if found is not None:
                    created = CreatedFollowUp(
                        found.id, found.title, item.reason, item.blocks_task, existed=True
                    )
                else:
                    assert step.id is not None
                    try:
                        result = add_task(
                            main,
                            step.id,
                            item.title,
                            related=[task_id],
                            writes=list(item.writes) if item.writes else None,
                            body=_task_body(item, task, run_id),
                        )
                    except TaskEditError as exc:
                        outcome.warnings.append(
                            f"follow-up '{item.title}' not filed: {_error(exc)}"
                        )
                        if item.blocks_task:
                            blockers.append(f"(neuložený task: {item.title})")
                        continue
                    wrote = True
                    created = CreatedFollowUp(
                        result.task.id, result.task.title, item.reason, item.blocks_task
                    )
                outcome.created.append(created)
                if item.blocks_task:
                    blockers.append(created.id)
        else:
            blockers += [f"(neuložený task: {r.title})" for r in reported if r.blocks_task]

    backlog = load_for_edit(main)
    for dep in blocked_ids:
        if dep == task_id:
            outcome.warnings.append(f"blocked_by: task {task_id} cannot block itself")
        elif dep not in backlog.by_id:
            outcome.warnings.append(f"blocked_by: unknown backlog id '{dep}', ignored")
        elif dep not in blockers:
            blockers.append(dep)
    open_blockers = [
        dep for dep in blockers if dep not in backlog.by_id or not is_done(backlog.by_id[dep])
    ]
    outcome.blocked_by = open_blockers

    task = find_task(backlog, task_id)
    links = [d for d in open_blockers if d in backlog.by_id and d not in task.depends_on]
    if links:
        try:
            link_task(main, task_id, depends_on=links)
            wrote = True
        except TaskEditError as exc:
            outcome.warnings.append(
                f"depends_on {', '.join(links)} not written to {task_id}: {_error(exc)}"
            )

    if wrote:
        try:
            done = commit_backlog(main, f"{task_id}: TODO tasky z běhu {run_id}")
            outcome.committed = done.committed
            outcome.warnings += list(done.warnings)
        except TaskEditError as exc:
            outcome.warnings.append(f"backlog changes are written but not committed: {_error(exc)}")
    return outcome
