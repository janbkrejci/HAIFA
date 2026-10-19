"""New work and blockers the agents of a run reported, filed in the backlog.

Agents never leave open work in the repository. Work that a task run found but does not
finish comes back in an envelope's ``follow_ups``; ``record`` files each one as a task
in the project's ``TODO`` step (the step is created when it is missing) and says where
and why it came from. A follow-up with ``blocks_task`` and every not-done id in
``blocked_by`` become ``depends_on`` of the task: the run then fails as blocked
(``run/task.py``), so the task is neither done nor merged until its blockers are done.
A follow-up with ``writes`` gets them as its own ``writes`` (they replace the inherited
value), for work outside the paths this task may change, and ``workflow`` its own
workflow. A follow-up only a person can do (``for_human``, or ``writes`` that reach the
backlog or ``protected_files``) gets ``assignee: human``: no run starts it.

The backlog is edited in a temporary copy through ``aifactory.backlog.edit`` and
published on ``base`` without writing pending files to the main checkout.
A follow-up task carries the marker
``<!-- factory: follow-up-of=<task id> -->``; a retry or a replayed journal finds it
by the marker and title and creates nothing new.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

from aifactory.backlog import (
    Backlog,
    Container,
    Task,
    TaskEditError,
    add_container,
    add_task,
    find_task,
    is_done,
    is_human,
    link_task,
    load_for_edit,
)
from aifactory.backlog.derived import descendant_tasks
from aifactory.backlog.edit import compose_id
from aifactory.backlog.model import HUMAN
from aifactory.backlog.roots import backlog_roots
from aifactory.config import ProjectSettings
from aifactory.run.scope import literal_prefix
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
    for_human: bool = False
    workflow: str | None = None
    origins: tuple[tuple[str, str], ...] = ()


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


def collect(
    wf: WorkflowRun, settings: ProjectSettings | None = None
) -> tuple[list[Reported], list[str]]:
    """Follow-ups and ``blocked_by`` ids of every envelope of the run, deduplicated.

    Follow-ups are one per title and assignee within this task's run. Preserve all
    reporting phases and block the task when any report of the goal does.
    """
    owners = _owners(wf)
    reported: dict[tuple[str, bool], Reported] = {}
    blocked: list[str] = []
    for key, envelope in wf.history:
        for item in getattr(envelope, "follow_ups", None) or []:
            title = str(getattr(item, "title", "") or "").strip()
            if not title:
                continue
            blocks = bool(getattr(item, "blocks_task", False))
            item_report = Reported(
                step=str(key),
                owner=owners.get(str(key), ""),
                title=title,
                reason=str(getattr(item, "reason", "") or "").strip(),
                details=str(getattr(item, "details", "") or "").strip(),
                blocks_task=blocks,
                writes=_writes(getattr(item, "writes", None)),
                for_human=bool(getattr(item, "for_human", False)),
                workflow=str(getattr(item, "workflow", None) or "").strip() or None,
                origins=((str(key), owners.get(str(key), "")),),
            )
            human = _for_human(item_report, settings) if settings else item_report.for_human
            identity = (_norm(title), human)
            known = reported.get(identity)
            if known is not None:
                item_report = replace(
                    known,
                    blocks_task=known.blocks_task or blocks,
                    origins=tuple(dict.fromkeys((*known.origins, *item_report.origins))),
                )
            reported[identity] = item_report
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


def _for_human(item: Reported, settings: ProjectSettings) -> bool:
    """A person's task: the agent said so, or one of its writes lies in what no run may
    change (the backlog, ``protected_files``)."""
    if item.for_human:
        return True
    closed = [c.rstrip("/") for c in (*settings.backlog_patterns, *settings.protected_files)]
    prefixes = [literal_prefix(w).rstrip("/") for w in item.writes or ()]
    return any(p and (p == c or p.startswith(c + "/")) for p in prefixes for c in closed if c)


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
    where = ", ".join(
        f"v kroku `{step}`" + (f" (agent {owner})" if owner else "")
        for step, owner in item.origins or ((item.step, item.owner),)
    )
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


def _existing(step: Container, task_id: str, title: str, human: bool) -> Task | None:
    marker = follow_up_marker(task_id)
    for candidate in step.tasks:
        if (
            marker in candidate.body
            and _norm(candidate.title) == _norm(title)
            and is_human(candidate) == human
        ):
            return candidate
    return None


def open_dependencies(backlog: Backlog, task: Task) -> list[tuple[Task, Task]]:
    """Open dependency tasks of this task and the tasks it explicitly relates to."""
    result: list[tuple[Task, Task]] = []
    for task_id in dict.fromkeys([task.id, *task.related]):
        affected = backlog.by_id.get(task_id)
        if not isinstance(affected, Task):
            continue
        for dep in affected.depends_on:
            node = backlog.by_id.get(dep)
            candidates = descendant_tasks(node) if isinstance(node, Container) else [node]
            for candidate in candidates:
                if isinstance(candidate, Task) and candidate.status == "todo":
                    result.append((affected, candidate))
    return result


def dependency_prompt(backlog: Backlog, task: Task) -> str:
    dependencies = open_dependencies(backlog, task)
    if not dependencies:
        return ""
    lines = [
        "\n## Existing open dependencies",
        "Do not report follow_ups for work already covered by these tasks, even with a "
        "different title. If one blocks completion, report its id in blocked_by instead.",
    ]
    for affected, dependency in dependencies:
        assignee = "human" if is_human(dependency) else "agent"
        lines += [
            f"\n### {dependency.id}: {dependency.title}",
            f"- {affected.id} depends_on {dependency.id}; assignee: {assignee}",
            f"- task file: {dependency.path}",
            dependency.body.strip(),
        ]
    return "\n".join(lines) + "\n"


def _error(exc: TaskEditError) -> str:
    return f"{exc.code}: {exc.message}"


def record(
    main: Path, task_id: str, run_id: str, wf: WorkflowRun, *, blocking: bool = True
) -> FollowUpOutcome:
    """Prepare follow-ups away from the operator's checkout, then publish only our edits."""
    from aifactory.config import load_run_config
    from aifactory.run import gitops

    reported, blocked_ids = collect(wf)
    if not reported and (not blocked_ids or not blocking):
        return FollowUpOutcome()
    main = gitops.main_root(main)
    rc = load_run_config(main)
    with tempfile.TemporaryDirectory(prefix="factory-followups-") as tmp:
        stage = Path(tmp)
        config = stage / ".factory/config.yaml"
        config.parent.mkdir()
        config.write_bytes((main / ".factory/config.yaml").read_bytes())
        for directory in backlog_roots(main, load_for_edit(main).settings):
            shutil.copytree(main / directory, stage / directory, dirs_exist_ok=True)
        before = _contents(stage)
        outcome = _record(stage, task_id, run_id, wf, blocking=blocking)
        contents = {p: data for p, data in _contents(stage).items() if before.get(p) != data}
        if contents:
            _publish(
                main, rc.base, rc.commit, rc.config.settings, contents, task_id, run_id, outcome
            )
        return outcome


def _contents(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*.md")}


def _publish(
    main: Path,
    base: str,
    base_sha: str,
    settings: ProjectSettings,
    contents: dict[str, bytes],
    task_id: str,
    run_id: str,
    outcome: FollowUpOutcome,
) -> None:
    from aifactory.backlog.commit import BACKLOG_BRANCH_PREFIX
    from aifactory.library.install_commit import _store
    from aifactory.providers import ProviderError, get_provider, publish

    subject = f"{task_id}: TODO tasky z běhu {run_id}"
    try:
        files = publish.plan_contents(main, base_sha, contents)
        if not files:
            return
        plan = publish.PublishPlan(
            base,
            base_sha,
            settings.base_changes,
            tuple(files),
            (),
            publish.plan_digest(base, base_sha, files),
        )
        if publish.uses_pr(settings):
            provider = get_provider(settings, main)
            result = publish.publish_pr(
                main,
                provider=provider,
                settings=settings,
                plan=plan,
                message=subject,
                body=subject + "\n",
                prefix=BACKLOG_BRANCH_PREFIX,
            )
            store = _store(main) if settings.base_pr_merge == "auto" else None
            try:
                result = publish.finish_pr(
                    main,
                    provider=provider,
                    settings=settings,
                    plan=plan,
                    result=result,
                    message=subject,
                    store=store,
                    materialize=True,
                    command="follow-ups",
                )
            finally:
                if store is not None:
                    store.close()
        else:
            result = publish.publish_direct(
                main,
                settings=settings,
                plan=plan,
                message=subject,
                store=None,
                materialize=True,
                command="follow-ups",
            )
        outcome.committed = True
        outcome.warnings += list(result.warnings)
    except (ProviderError, RuntimeError) as exc:
        outcome.warnings.append(f"follow-up changes not published: {exc}")


def _record(
    main: Path, task_id: str, run_id: str, wf: WorkflowRun, *, blocking: bool = True
) -> FollowUpOutcome:
    """File the run's follow-ups in the TODO step and link the task to its blockers.

    Returns what was written; problems that do not stop the rest (an unknown id or a
    rejected write) are ``warnings``. A blocker counts even when
    its ``depends_on`` could not be written. ``blocking=False`` (a resolve run, whose
    task is built already) files every follow-up as not blocking and ignores
    ``blocked_by``.
    """
    outcome = FollowUpOutcome()
    reported, blocked_ids = collect(wf)
    if not reported and (not blocked_ids or not blocking):
        return outcome
    backlog = load_for_edit(main)
    task = find_task(backlog, task_id)
    reported, blocked_ids = collect(wf, backlog.settings)
    if not blocking:
        reported = [replace(r, blocks_task=False) for r in reported]
        blocked_ids = []
    project = task.parent.parent
    blockers: list[str] = []

    uncovered: list[Reported] = []
    dependencies = open_dependencies(backlog, task)
    for item in reported:
        found = next(
            (
                dep
                for _, dep in dependencies
                if dep.id != task_id
                and _norm(dep.title) == _norm(item.title)
                and is_human(dep) == _for_human(item, backlog.settings)
            ),
            None,
        )
        if found is None:
            uncovered.append(item)
        else:
            outcome.created.append(
                CreatedFollowUp(found.id, found.title, item.reason, item.blocks_task, existed=True)
            )
            if item.blocks_task:
                blockers.append(found.id)
    reported = uncovered

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
                step = added.container
            except TaskEditError as exc:
                outcome.warnings.append(f"TODO step not created: {_error(exc)}")
        if step is not None:
            outcome.step_id = step.id
            for item in reported:
                found = _existing(step, task_id, item.title, _for_human(item, backlog.settings))
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
                            workflow=item.workflow,
                            assignee=HUMAN if _for_human(item, backlog.settings) else None,
                            body=_task_body(item, task, run_id),
                        )
                    except TaskEditError as exc:
                        outcome.warnings.append(
                            f"follow-up '{item.title}' not filed: {_error(exc)}"
                        )
                        if item.blocks_task:
                            blockers.append(f"(neuložený task: {item.title})")
                        continue
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
        except TaskEditError as exc:
            outcome.warnings.append(
                f"depends_on {', '.join(links)} not written to {task_id}: {_error(exc)}"
            )

    return outcome
