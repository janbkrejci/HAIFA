"""New work and blockers the agents of a run reported, filed in the backlog.

Agents never leave open work in the repository. Work that a task run found but does not
finish comes back in an envelope's ``follow_ups``. The run triages them before
``record`` applies recommendations to the fresh backlog: reuse, additive extension,
a human decision, or a new task in the project's ``TODO`` step. A follow-up with
``blocks_task`` and every not-done id in
``blocked_by`` become ``depends_on`` of the task: the run then fails as blocked
(``run/task.py``), so the task is neither done nor merged until its blockers are done.
A blocker that is ``cancelled`` (the operator waived it) blocks nothing.
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

import contextlib
import hashlib
import re
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from aifactory.backlog import (
    Backlog,
    Container,
    Task,
    TaskEditError,
    add_container,
    add_task,
    check_backlog,
    find_task,
    is_done,
    is_human,
    iter_tasks,
    link_task,
    load_backlog,
    load_for_edit,
)
from aifactory.backlog.derived import descendant_tasks
from aifactory.backlog.edit import _next_id, _write_checked, compose_id
from aifactory.backlog.model import HUMAN
from aifactory.backlog.roots import owning_root
from aifactory.config import ProjectSettings
from aifactory.run.scope import literal_prefix
from aifactory.workflow import WorkflowRun

if TYPE_CHECKING:
    from aifactory.run.triage import Decision

DecisionKind = Literal["covered", "extend", "decide", "new"]

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
    """A follow-up task in the backlog (``existed``: a task was reused)."""

    id: str
    title: str
    reason: str
    blocks: bool
    existed: bool = False
    assignee: str = "agent"
    decision: DecisionKind = "new"

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "reason": self.reason,
            "blocks": self.blocks,
            "existed": self.existed,
            "assignee": self.assignee,
            "decision": self.decision,
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
    return tuple(dict.fromkeys(paths))


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


def _cancelled(node: object) -> bool:
    return isinstance(node, Task) and node.status == "cancelled"


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


def _extension_marker(task_id: str, item: Reported, settings: ProjectSettings) -> str:
    return f"<!-- factory: extended-by={task_id} follow-up={_identity(item, settings)} -->"


def _identity(item: Reported, settings: ProjectSettings) -> str:
    identity = f"{_norm(item.title)}:{_for_human(item, settings)}"
    return hashlib.sha256(identity.encode()).hexdigest()[:24]


def _can_block(backlog: Backlog, source: Task, target: Task) -> bool:
    """Validate the proposed edge, including dependencies through containers."""
    if source.id == target.id:
        return False
    baseline = {(i.code, i.path, i.message) for i in check_backlog(backlog)}
    previous = source.depends_on
    try:
        source.depends_on = list(dict.fromkeys([*previous, target.id]))
        return all((i.code, i.path, i.message) in baseline for i in check_backlog(backlog))
    finally:
        source.depends_on = previous


@contextlib.contextmanager
def publication_lock(root: Path) -> Iterator[None]:
    """Use the run store's reentrant cross-process lock, also before a store exists."""
    from aifactory.config import load_local
    from aifactory.run.store import _path_lock

    db = load_local(root).trace_db_path(root)
    if db.exists():
        lock = db.with_name(db.name + ".lock")
    else:
        from aifactory.providers import git

        common = Path(git.git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        lock = common / "factory-followups.lock"
    with _path_lock(lock).hold(600):
        yield


def current_target(root: Path, base: str, settings: ProjectSettings) -> str:
    """Fetch before reading IDs; a failed fetch must never fall back to stale base."""
    from aifactory.providers import ProviderError, git

    if git.has_remote(root, settings.remote):
        git.fetch(root, settings.remote, base)
        target = git.remote_tip(root, settings.remote, base)
    else:
        target = git.rev_parse(root, f"refs/heads/{base}")
    if target is None:
        raise ProviderError("follow_up_collision", f"cannot read target branch {base}")
    return target


@contextlib.contextmanager
def _snapshot(root: Path, sha: str, settings: ProjectSettings) -> Iterator[Path]:
    from aifactory.run.gitops import extract_backlog

    with tempfile.TemporaryDirectory(prefix="factory-followups-") as tmp:
        stage = Path(tmp)
        extract_backlog(root, sha, settings.backlog_patterns, stage)
        yield stage


def reconcile_ids(
    root: Path, head: str, base: str, settings: ProjectSettings
) -> tuple[str, dict[str, str]]:
    """Repair newly added follow-ups, merge fresh base and validate the resulting backlog.

    Only references changed on this branch are rewritten: a target task with the
    colliding ID continues to mean that target task. Call under publication_lock.
    The returned commit is unpublished; conflicts leave both branches untouched.
    """
    from aifactory.providers import ProviderError, git

    target = current_target(root, base, settings)
    ancestor = git.git(root, "merge-base", head, target)
    changed = git.git(root, "diff", "--name-only", "-z", ancestor, head).split("\0")
    if not any(
        path.lower().endswith(".md") and owning_root(path, settings) is not None for path in changed
    ):
        return head, {}
    with (
        _snapshot(root, head, settings) as ours,
        _snapshot(root, ancestor, settings) as old,
        _snapshot(root, target, settings) as theirs,
    ):
        branch = load_backlog(ours, settings)
        duplicates = [i for i in check_backlog(branch) if i.code == "duplicate_id"]
        if duplicates:
            raise ProviderError("follow_up_collision", "; ".join(i.message for i in duplicates))
        previous = load_backlog(old, settings)
        latest = load_backlog(theirs, settings)
        additions = [t for t in iter_tasks(branch) if t.id not in previous.by_id]
        if not additions:
            return head, {}
        reserved = set(branch.by_id) | set(latest.by_id)
        renamed: dict[str, str] = {}
        paths: dict[str, str] = {}
        for task in additions:
            taken = latest.by_id.get(task.id)
            if taken is None:
                continue
            # The same follow-up already published by an earlier attempt is not a collision.
            markers = re.findall(r"<!-- factory: follow-up-of=([^ ]+) -->", task.body)
            same = (
                isinstance(taken, Task)
                and taken.path == task.path
                and _norm(taken.title) == _norm(task.title)
                and is_human(taken) == is_human(task)
                and (markers and all(follow_up_marker(m) in taken.body for m in markers))
            )
            if same:
                continue
            if not markers and not task.follows:
                raise ProviderError(
                    "follow_up_collision", f"duplicate id {task.id}: not a follow-up"
                )
            step = task.parent.id
            assert step is not None
            new_id = _next_id(task.parent, step, reserved)
            reserved.add(new_id)
            renamed[task.id] = new_id
            task_path = Path(task.path)
            paths[task.path] = task_path.with_name(
                task_path.name.replace(task.id, new_id, 1)
            ).as_posix()

        changes: list[git.TreeChange] = []
        if renamed:
            pattern = re.compile(
                r"(?<![\w.-])(" + "|".join(re.escape(k) for k in renamed) + r")(?![\w.-])"
            )
            before = _contents(old)
            for path, content in _contents(ours).items():
                if before.get(path) == content:
                    continue
                rewritten = pattern.sub(lambda m: renamed[m.group()], content.decode("utf-8"))
                destination = paths.get(path, path)
                if destination != path:
                    changes.append((path, None, None))
                if destination != path or rewritten.encode("utf-8") != content:
                    changes.append((destination, "100644", git.hash_blob(root, rewritten.encode())))
        fixed = (
            git.commit_tree_with(root, head, changes, "Renumber colliding follow-up IDs")
            if changes
            else head
        )
        if git.is_ancestor(root, target, fixed):
            merged = fixed
        else:
            try:
                tree = git.git(root, "merge-tree", "--write-tree", fixed, target).splitlines()[0]
            except RuntimeError as exc:
                raise ProviderError(
                    "follow_up_collision", f"cannot merge follow-ups into {base}: {exc}"
                ) from exc
            merged = git.git(
                root,
                "commit-tree",
                tree,
                "-p",
                fixed,
                "-p",
                target,
                input="Merge current target and reconcile follow-up IDs\n",
            )
        with _snapshot(root, merged, settings) as combined:
            baseline = {(i.code, i.path, i.message) for i in check_backlog(latest)}
            problems = [
                i
                for i in check_backlog(load_backlog(combined, settings))
                if i.code == "duplicate_id" or (i.code, i.path, i.message) not in baseline
            ]
            if problems:
                raise ProviderError("follow_up_collision", "; ".join(i.message for i in problems))
        return merged, renamed


def advance_pr(root: Path, branch: str, old: str, new: str) -> None:
    """Move a repaired PR branch without overwriting edits in a checked-out branch."""
    from aifactory.providers import ProviderError, git

    if git.rev_parse(root, f"refs/heads/{branch}") != old:
        raise ProviderError("follow_up_collision", f"{branch} moved during ID reconciliation")
    checkout = git.checked_out_in(root, branch)
    if checkout is not None:
        if git.git(checkout, "status", "--porcelain"):
            raise ProviderError("follow_up_collision", f"{branch} has uncommitted changes")
        git.git(checkout, "merge", "--ff-only", new)
    else:
        git.git(root, "update-ref", f"refs/heads/{branch}", new, old)


def record(
    main: Path,
    task_id: str,
    run_id: str,
    wf: WorkflowRun,
    *,
    blocking: bool = True,
    decisions: dict[Reported, Decision] | None = None,
    running: Callable[[str], object] | None = None,
) -> FollowUpOutcome:
    """Prepare follow-ups away from the operator's checkout, then publish only our edits."""
    from aifactory.config import load_run_config
    from aifactory.run import gitops

    reported, blocked_ids = collect(wf)
    if not reported and (not blocked_ids or not blocking):
        return FollowUpOutcome()
    main = gitops.main_root(main)
    rc = load_run_config(main)
    settings = rc.config.settings
    with publication_lock(main):
        target = current_target(main, rc.base, settings)
        return _record_current(
            main,
            target,
            rc.base,
            settings,
            task_id,
            run_id,
            wf,
            blocking=blocking,
            decisions=decisions,
            running=running,
        )


def _record_current(
    main: Path,
    target: str,
    base: str,
    settings: ProjectSettings,
    task_id: str,
    run_id: str,
    wf: WorkflowRun,
    *,
    blocking: bool,
    decisions: dict[Reported, Decision] | None,
    running: Callable[[str], object] | None,
) -> FollowUpOutcome:
    with _snapshot(main, target, settings) as stage:
        config = stage / ".factory/config.yaml"
        config.parent.mkdir()
        config.write_bytes((main / ".factory/config.yaml").read_bytes())
        before = _contents(stage)
        # Keep checkout line endings for additive extensions, without importing
        # uncommitted assignments or stale task state into the target snapshot.
        for path, data in before.items():
            local = main / path
            if local.is_file():
                checkout = local.read_bytes()
                if checkout != data and checkout.replace(b"\r\n", b"\n") == data.replace(
                    b"\r\n", b"\n"
                ):
                    (stage / path).write_bytes(checkout)
                    before[path] = checkout
        outcome = _record(
            stage, task_id, run_id, wf, blocking=blocking, decisions=decisions, running=running
        )
        contents = {p: data for p, data in _contents(stage).items() if before.get(p) != data}
        if contents:
            _publish(main, base, target, settings, contents, task_id, run_id, outcome)
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
        if result.renamed_ids:
            outcome.created = [
                replace(item, id=result.renamed_ids.get(item.id, item.id))
                for item in outcome.created
            ]
            outcome.blocked_by = [result.renamed_ids.get(ref, ref) for ref in outcome.blocked_by]
        outcome.warnings += list(result.warnings)
    except (ProviderError, RuntimeError) as exc:
        outcome.warnings.append(f"follow-up changes not published: {exc}")


def _record(
    main: Path,
    task_id: str,
    run_id: str,
    wf: WorkflowRun,
    *,
    blocking: bool = True,
    decisions: dict[Reported, Decision] | None = None,
    running: Callable[[str], object] | None = None,
) -> FollowUpOutcome:
    """Apply recommendations, file uncovered follow-ups and link the task to its blockers.

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
        blocked_ids = []
    project = task.parent.parent
    blockers: list[str] = []

    pending: list[tuple[Reported, Decision | None]] = []
    for original in reported:
        item = original if blocking else replace(original, blocks_task=False)
        decision = decisions.get(original) if decisions is not None else None
        backlog = load_for_edit(main)
        task = find_task(backlog, task_id)
        # A persisted marker acknowledges an earlier application, regardless of the
        # new recommendation. It does not authorize extending the target again.
        marker = _extension_marker(task_id, item, backlog.settings)
        applied = next((t for t in iter_tasks(backlog) if marker in t.body), None)
        if applied is not None:
            outcome.created.append(
                CreatedFollowUp(
                    applied.id,
                    applied.title,
                    item.reason,
                    item.blocks_task,
                    existed=True,
                    assignee=HUMAN if is_human(applied) else "agent",
                    decision="extend",
                )
            )
            if item.blocks_task and not (is_done(applied) or _cancelled(applied)):
                if _can_block(backlog, task, applied):
                    blockers.append(applied.id)
                else:
                    outcome.warnings.append(
                        f"applied extension {applied.id}: linking {task_id} to this task "
                        "would create a cycle; not linked"
                    )
                    blockers.append(f"(neuložená závislost: {applied.id})")
            continue
        target = backlog.by_id.get(decision.task_id or "") if decision else None
        if decision is not None and decision.action != "new":
            from aifactory.run.triage import TriageOutput, _violations

            errors = []
            if not isinstance(target, Task) or target.status != "todo":
                errors.append("target is no longer todo")
            elif target.id == task_id or (running is not None and running(target.id)):
                errors.append("target is the source task or is running")
            elif (
                decision.action in ("covered", "extend")
                and item.blocks_task
                and not _can_block(backlog, task, target)
            ):
                errors.append("target would create a dependency cycle")
            else:
                checked = replace(item, for_human=_for_human(item, backlog.settings))
                errors = _violations(
                    TriageOutput(
                        status="success",
                        decisions=[decision.model_copy(update={"follow_up_id": "f1"})],
                    ),
                    [checked],
                    backlog,
                )
            if errors:
                outcome.warnings.append(
                    f"follow-up '{item.title}' triage no longer applies; using new: "
                    + "; ".join(errors)
                )
                decision = None
            elif isinstance(target, Task) and decision.action in ("covered", "extend"):
                if decision.action == "extend":
                    marker = _extension_marker(task_id, item, backlog.settings)
                    original_text = (main / target.path).read_bytes().decode("utf-8")
                    if marker not in original_text:
                        section = (
                            f"\n\n### Doplnění z běhu {run_id} tasku {task_id}\n\n"
                            f"{decision.addition}\n\n{marker}\n"
                        )
                        try:
                            _write_checked(
                                backlog,
                                check_backlog(backlog),
                                {target.path: original_text + section},
                                "follow-ups",
                            )
                        except TaskEditError as exc:
                            outcome.warnings.append(f"extension not written: {_error(exc)}")
                            pending.append((item, None))
                            continue
                outcome.created.append(
                    CreatedFollowUp(
                        target.id,
                        target.title,
                        item.reason,
                        item.blocks_task,
                        existed=True,
                        assignee=HUMAN if is_human(target) else "agent",
                        decision=decision.action,
                    )
                )
                if item.blocks_task:
                    blockers.append(target.id)
                continue
        # Keep the historical title fallback only when no triage was supplied.
        if decisions is None:
            found = next(
                (
                    dep
                    for _, dep in open_dependencies(backlog, task)
                    if dep.id != task_id
                    and _norm(dep.title) == _norm(item.title)
                    and is_human(dep) == _for_human(item, backlog.settings)
                    and (not item.blocks_task or _can_block(backlog, task, dep))
                ),
                None,
            )
            if found is not None:
                outcome.created.append(
                    CreatedFollowUp(
                        found.id,
                        found.title,
                        item.reason,
                        item.blocks_task,
                        existed=True,
                        assignee=HUMAN if is_human(found) else "agent",
                        decision="covered",
                    )
                )
                if item.blocks_task:
                    blockers.append(found.id)
                continue
        pending.append((item, decision))
    reported = [item for item, _ in pending]

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
            for item, decision in pending:
                backlog = load_for_edit(main)
                task = find_task(backlog, task_id)
                assert step.id is not None
                refreshed_step = backlog.by_id[step.id]
                assert isinstance(refreshed_step, Container)
                step = refreshed_step
                deciding = decision is not None and decision.action == "decide"
                human = deciding or _for_human(item, backlog.settings)
                decision_marker = (
                    f"<!-- factory: decision-for={task_id} target={decision.task_id} "
                    f"follow-up={_identity(item, backlog.settings)} -->"
                    if deciding and decision
                    else ""
                )
                found = (
                    next(
                        (
                            candidate
                            for candidate in step.tasks
                            if decision_marker in candidate.body and is_human(candidate)
                        ),
                        None,
                    )
                    if deciding
                    else _existing(step, task_id, item.title, human)
                )
                kind: DecisionKind = "decide" if deciding else "new"
                if found is not None:
                    created = CreatedFollowUp(
                        found.id,
                        found.title,
                        item.reason,
                        item.blocks_task,
                        existed=True,
                        assignee=HUMAN if is_human(found) else "agent",
                        decision=kind,
                    )
                else:
                    assert step.id is not None
                    try:
                        result = add_task(
                            main,
                            step.id,
                            item.title,
                            related=[task_id, decision.task_id]
                            if deciding and decision and decision.task_id
                            else [task_id],
                            writes=list(item.writes) if item.writes is not None else None,
                            workflow=item.workflow,
                            assignee=HUMAN if human else None,
                            body=_task_body(item, task, run_id)
                            + (
                                "\n### Rozhodnutí člověka\n\n"
                                f"Navrhovaná změna tasku `{decision.task_id}`: "
                                f"{decision.proposal}\n\n"
                                f"Důvod triáže: {decision.reason}\n\n"
                                f"{decision_marker}\n\n"
                                "Zadání existujícího tasku se bez člověka nezužuje "
                                "ani zásadně nemění.\n"
                                if deciding and decision
                                else ""
                            ),
                        )
                    except TaskEditError as exc:
                        outcome.warnings.append(
                            f"follow-up '{item.title}' not filed: {_error(exc)}"
                        )
                        if item.blocks_task:
                            blockers.append(f"(neuložený task: {item.title})")
                        continue
                    created = CreatedFollowUp(
                        result.task.id,
                        result.task.title,
                        item.reason,
                        item.blocks_task,
                        assignee=HUMAN if is_human(result.task) else "agent",
                        decision=kind,
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
    # a cancelled blocker never gets done: the operator waived it, so it does not block
    # (a retry replays the follow-ups of earlier attempts and finds the cancelled task)
    open_blockers = [
        dep
        for dep in blockers
        if dep not in backlog.by_id
        or not (is_done(backlog.by_id[dep]) or _cancelled(backlog.by_id[dep]))
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
