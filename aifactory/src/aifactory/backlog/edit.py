"""Write operations on task files (add, edit, link), ``auto_continue``/``auto_merge`` flags and
the ``index.md`` of projects and steps (``add_container``, ``edit_container``).

Every write is first applied to a copy of the backlog roots in a temporary directory
and validated with ``check_backlog``. A change that would add a new problem (a cycle,
an unknown reference, a duplicate id, ...) is rejected and the real tree stays
untouched. Problems that were in the backlog before do not block a write. Files are
replaced atomically and only files under a backlog root are ever written. Every
written file is recorded in the journal of ``run/mainwrites.py``, so the guard of a
concurrent task run does not take the write for one of its agent.

Stable error codes (``TaskEditError.code`` / ``errors()[i]["code"]``):

=====================================  ====  ==========================================
code                                   exit  when
=====================================  ====  ==========================================
``invalid_config``                     2     invalid ``.factory/config.yaml`` (CLI)
``missing_backlog_dir``                2     a backlog root does not exist
``unknown_task``                       2     the id does not exist or is not a task
``unknown_step``                       2     no container with that id one level above tasks
``unknown_project``                    2     ``task list --project`` (CLI)
``unknown_container``                  2     no project or step with that id
``no_index``                           2     the container has no ``index.md``
``duplicate_id``                       2/1   target id is ambiguous (2); add would
                                             create a duplicate (1, from validation)
``invalid_id``, ``invalid_value``,     2     invalid input
``invalid_status``
``no_changes``, ``conflicting_options``, 2   wrong combination of options
``self_ref``
``not_done``                           2     ``follow_up_task`` of a task that is not done
``file_exists``                        2     the task file exists already
``outside_backlog``, ``write_failed``  2     path guard / I/O error
``backlog_invalid``                    1     the write would break the backlog; nothing
                                             was written. ``errors()`` lists the new
                                             problems with their ``backlog check``
                                             codes (``cycle``, ``unknown_ref``,
                                             ``id_prefix``, ``duplicate_id``, ...)
=====================================  ====  ==========================================
"""

from __future__ import annotations

import contextlib
import datetime
import os
import re
import shutil
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from aifactory.backlog.derived import is_human
from aifactory.backlog.loader import iter_containers, load_backlog
from aifactory.backlog.model import (
    ASSIGNEES,
    HARNESS_KEYS,
    INDEX_FILE,
    Backlog,
    Container,
    Issue,
    Task,
    node_file,
)
from aifactory.backlog.roots import backlog_roots, owning_root
from aifactory.backlog.taskfile import (
    mark_done,
    new_index_text,
    new_task_text,
    remove_field,
    replace_body,
    set_field,
)
from aifactory.backlog.validate import check_backlog

EDITABLE_STATUSES: tuple[str, ...] = ("todo", "cancelled")
_SLUG_MAX = 40


class TaskEditError(Exception):
    """A rejected task write or lookup, with a stable ``code``."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        exit_code: int = 2,
        path: str | None = None,
        id: str | None = None,
        issues: list[Issue] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.path = path
        self.id = id
        self.issues = list(issues or [])

    def errors(self) -> list[dict[str, object]]:
        if self.issues:
            return [i.to_dict() for i in self.issues]
        return [{"code": self.code, "message": self.message, "path": self.path, "id": self.id}]


@dataclass
class WriteResult:
    action: str
    changed: bool
    path: str
    task: Task
    backlog: Backlog
    issues: list[Issue] = field(default_factory=list)


def slugify(text: str) -> str:
    """ASCII lowercase slug: ``Migrace hlavičky faktury`` -> ``migrace-hlavicky-faktury``."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return slug[:_SLUG_MAX].strip("-")


def load_for_edit(root: Path) -> Backlog:
    """The backlog under ``root``; ``missing_backlog_dir`` when a backlog root is missing."""
    backlog = load_backlog(root)
    missing = next((i for i in backlog.issues if i.code == "missing_backlog_dir"), None)
    if missing is not None:
        raise TaskEditError("missing_backlog_dir", missing.message, path=missing.path)
    return backlog


def find_task(backlog: Backlog, task_id: str, issues: list[Issue] | None = None) -> Task:
    """The task ``task_id``; ``TaskEditError`` when it is unknown or ambiguous."""
    node = backlog.by_id.get(task_id)
    if not isinstance(node, Task):
        raise TaskEditError("unknown_task", f"unknown task '{task_id}'", id=task_id)
    if issues is None:
        issues = check_backlog(backlog)
    if any(i.code == "duplicate_id" and i.id == task_id for i in issues):
        raise TaskEditError(
            "duplicate_id", f"task id '{task_id}' is not unique", id=task_id, path=node.path
        )
    return node


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _issue_key(issue: Issue) -> tuple[str, str, str]:
    return issue.code, issue.path, issue.message


def _guard(root: Path, backlog: Backlog, rel: str) -> Path:
    owner = owning_root(rel, backlog.settings)
    target = (root / rel).resolve()
    base = (root / owner).resolve() if owner is not None else None
    if not rel.endswith(".md") or base is None or not target.is_relative_to(base) or target == base:
        raise TaskEditError(
            "outside_backlog", f"refusing to write '{rel}' outside the backlog", path=rel
        )
    return root / rel


def _atomic_write(path: Path, text: str, rel: str) -> None:
    tmp_name: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp_name = handle.name
            handle.write(text)
        os.replace(tmp_name, path)
    except OSError as exc:
        if tmp_name is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
        raise TaskEditError("write_failed", f"cannot write '{rel}': {exc}", path=rel) from exc


def _new_issues(backlog: Backlog, baseline: list[Issue], pending: dict[str, str]) -> list[Issue]:
    """The problems ``pending`` would add to the backlog, checked on a staged copy."""
    root = backlog.root
    settings = backlog.settings
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        for backlog_dir in backlog_roots(root, settings):
            if (root / backlog_dir).is_dir():
                shutil.copytree(root / backlog_dir, stage / backlog_dir)
        for rel, text in pending.items():
            staged = stage / rel
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_text(text, encoding="utf-8", newline="\n")
        candidate = check_backlog(load_backlog(stage, settings))
    known = {_issue_key(i) for i in baseline}
    return [i for i in candidate if _issue_key(i) not in known]


def _write_checked(
    backlog: Backlog, baseline: list[Issue], changes: dict[str, str], command: str
) -> bool:
    """Validate `changes` on a copy of the backlog, then write them; True when written.

    `command` names the factory command in the journal of factory writes.
    """
    root = backlog.root
    targets = {rel: _guard(root, backlog, rel) for rel in changes}
    pending = {
        rel: text
        for rel, text in changes.items()
        if not targets[rel].is_file() or targets[rel].read_text(encoding="utf-8") != text
    }
    if pending:
        new = _new_issues(backlog, baseline, pending)
        if new:
            raise TaskEditError(
                "backlog_invalid",
                f"change rejected: {len(new)} new problem(s) in the backlog",
                exit_code=1,
                issues=new,
            )
        from aifactory.database.backlog import publish
        from aifactory.run import mainwrites

        publish(root, pending)

        for rel, text in pending.items():
            target = targets[rel]
            try:
                old: bytes | None = target.read_bytes()
            except OSError:
                old = None
            _atomic_write(target, text, rel)
            try:
                written = target.read_bytes()
                mode = target.stat().st_mode & 0o777
            except OSError:
                written, mode = text.encode("utf-8"), 0
            mainwrites.record(root, rel, old, written, mode=mode, command=command)
    return bool(pending)


def _commit(
    backlog: Backlog,
    baseline: list[Issue],
    changes: dict[str, str],
    action: str,
    target_rel: str,
    task_id: str,
) -> WriteResult:
    changed = _write_checked(backlog, baseline, changes, f"task {action}")
    after = load_backlog(backlog.root, backlog.settings)
    issues = check_backlog(after)
    node = after.by_id.get(task_id)
    if not isinstance(node, Task):  # pragma: no cover - guarded by validation
        raise TaskEditError("unknown_task", f"task '{task_id}' not found after write", id=task_id)
    return WriteResult(action, changed, target_rel, node, after, issues)


def _find_step(backlog: Backlog, step: str) -> Container:
    levels = backlog.settings.levels
    for container in iter_containers(backlog.containers):
        if container.id == step and container.level == levels[-2]:
            return container
    raise TaskEditError("unknown_step", f"unknown {levels[-2]} '{step}'", id=step)


_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._]*$")


def compose_id(parent_id: str | None, code: str) -> str:
    """The full id of a new node from its short code: ``S10`` under ``HAIFA`` is ``HAIFA-S10``.

    The id is always composed (the parent's id, ``-``, the code); a code that already
    carries the parent's prefix is taken without it. A code is letters, digits, ``.``
    and ``_``, without ``-``.
    """
    value = code.strip()
    if parent_id and value.startswith(f"{parent_id}-"):
        value = value[len(parent_id) + 1 :]
    if not _CODE_RE.match(value):
        raise TaskEditError(
            "invalid_id",
            f"invalid code '{code}': letters, digits, '.' and '_' (e.g. S10, T05)",
            id=code,
        )
    return f"{parent_id}-{value}" if parent_id else value


def _next_id(container: Container, step: str) -> str:
    pattern = re.compile(rf"^{re.escape(step)}-T(\d+)$")
    numbers = [m.group(1) for t in container.tasks if (m := pattern.match(t.id))]
    n = 1 + max((int(x) for x in numbers), default=0)
    width = max([2, *(len(x) for x in numbers)])
    return f"{step}-T{n:0{width}d}"


def add_task(
    root: Path,
    step: str,
    title: str,
    *,
    task_id: str | None = None,
    slug: str | None = None,
    workflow: str | None = None,
    writes: list[str] | None = None,
    depends_on: list[str] | None = None,
    related: list[str] | None = None,
    body: str = "",
    parameters: dict[str, object] | None = None,
    assignee: str | None = None,
    follows: str | None = None,
) -> WriteResult:
    """Create a new ``todo`` task file in the directory of ``step``.

    `follows` is the id of the done task the new one continues (see ``follow_up_task``).
    """
    backlog = load_for_edit(root)
    container = _find_step(backlog, step)
    title = title.strip()
    if not title:
        raise TaskEditError("invalid_value", "title must not be empty")
    task_id = _next_id(container, step) if task_id is None else compose_id(step, task_id)
    if slug is None:
        slug = slugify(title)
    elif slugify(slug) != slug:
        raise TaskEditError(
            "invalid_value", f"invalid slug '{slug}', expected e.g. '{slugify(slug)}'"
        )
    if workflow is not None and not workflow.strip():
        raise TaskEditError("invalid_value", "workflow must not be empty")
    _check_assignee(assignee)
    if related and task_id in related:
        raise TaskEditError("self_ref", f"task '{task_id}' cannot relate to itself", id=task_id)
    name = f"{task_id}-{slug}.md" if slug else f"{task_id}.md"
    rel = f"{container.path}/{name}"
    if (root / rel).exists():
        raise TaskEditError("file_exists", f"file '{rel}' exists already", path=rel, id=task_id)
    fields: dict[str, object] = {
        "id": task_id,
        "title": title,
        "status": "todo",
        "assignee": assignee,
        "workflow": workflow,
        "depends_on": _dedupe(depends_on or []),
        "related": _dedupe(related) if related is not None else None,
        "follows": follows,
        "writes": _dedupe(writes) if writes is not None else None,
    }
    if parameters:
        _validate_parameters(parameters)
        fields.update({k: v for k, v in parameters.items() if v is not None})
    text = new_task_text(fields, body)
    return _commit(backlog, check_backlog(backlog), {rel: text}, "add", rel, task_id)


def follow_up_title(task: Task) -> str:
    """The default title of a task that follows `task`."""
    return f"Navazuje na {task.id}: {task.title}"


def follow_up_task(root: Path, task_id: str, body: str, *, title: str | None = None) -> WriteResult:
    """A new ``todo`` task that follows the done task `task_id` (``factory task follow-up``).

    It goes into the same step, gets ``follows: <task_id>``, the original's own ``writes``
    and ``workflow`` (an inherited value stays inherited) and `body` as its ``## Zadání``.
    The title defaults to ``follow_up_title``. A task that is not done is refused
    (``not_done``).
    """
    backlog = load_for_edit(root)
    original = find_task(backlog, task_id)
    if original.status != "done":
        raise TaskEditError(
            "not_done",
            f"task '{task_id}' is {original.status or 'without status'}, only a done task "
            "can be followed up",
            id=task_id,
            path=original.path,
        )
    if not body.strip():
        raise TaskEditError("invalid_value", "body of the follow-up task must not be empty")
    step = original.parent.id
    if step is None:
        raise TaskEditError(
            "unknown_step", f"the step of task '{task_id}' has no id", path=original.parent.path
        )
    workflow = original.own.get("workflow")
    return add_task(
        root,
        step,
        follow_up_title(original) if title is None or not title.strip() else title,
        workflow=str(workflow) if workflow is not None else None,
        writes=list(original.writes) if "writes" in original.own else None,
        body=body,
        follows=original.id,
    )


def _check_assignee(assignee: str | None) -> None:
    if assignee is not None and assignee not in ASSIGNEES:
        raise TaskEditError(
            "invalid_value", f"assignee must be one of {', '.join(ASSIGNEES)}, got '{assignee}'"
        )


def human_done_entry() -> str:
    """The ``## Běhy`` line of a task a person marked done."""
    return f"- {datetime.date.today().isoformat()} · hotovo ručně"


def _read(root: Path, task: Task) -> str:
    return (root / task.path).read_text(encoding="utf-8")


def _apply(text: str, fn: str, key: str, value: str | list[str] | bool | int | None = None) -> str:
    try:
        if fn == "set":
            assert value is not None
            return set_field(text, key, value)
        return remove_field(text, key)
    except ValueError as exc:
        raise TaskEditError("invalid_value", f"cannot edit field '{key}': {exc}") from exc


def edit_task(
    root: Path,
    task_id: str,
    *,
    title: str | None = None,
    status: str | None = None,
    workflow: str | None = None,
    clear_workflow: bool = False,
    writes: list[str] | None = None,
    clear_writes: bool = False,
    auto_merge: bool | None = None,
    clear_auto_merge: bool = False,
    body: str | None = None,
    depends_on: list[str] | None = None,
    related: list[str] | None = None,
    parameters: dict[str, object] | None = None,
    assignee: str | None = None,
    clear_assignee: bool = False,
) -> WriteResult:
    """Change header fields of a task: title, status (todo|cancelled), workflow, writes,
    auto_merge (``clear_auto_merge`` removes the task's own value, so it inherits again),
    assignee. ``status: done`` is set here only for a person's task (``assignee: human``)."""
    given = (title, status, workflow, writes, body, depends_on, related, parameters, assignee)
    if all(v is None for v in given) and not clear_assignee:
        if not clear_workflow and not clear_writes and auto_merge is None and not clear_auto_merge:
            raise TaskEditError("no_changes", "nothing to change, give at least one option")
    if workflow is not None and clear_workflow:
        raise TaskEditError("conflicting_options", "--workflow and --clear-workflow are exclusive")
    if writes is not None and clear_writes:
        raise TaskEditError("conflicting_options", "--writes and --clear-writes are exclusive")
    if auto_merge is not None and clear_auto_merge:
        raise TaskEditError("conflicting_options", "--auto-merge and inherit are exclusive")
    if assignee is not None and clear_assignee:
        raise TaskEditError("conflicting_options", "--assignee and inherit are exclusive")
    _check_assignee(assignee)
    backlog = load_for_edit(root)
    baseline = check_backlog(backlog)
    task = find_task(backlog, task_id, baseline)
    text = _read(root, task)
    if title is not None:
        if not title.strip():
            raise TaskEditError("invalid_value", "title must not be empty", id=task_id)
        text = _apply(text, "set", "title", title.strip())
    if status == "done" and task.status != "done":
        if not is_human(task):
            raise TaskEditError(
                "invalid_status",
                "'done' is set only by PR approval; a person's task (assignee: human) "
                "can be marked done",
                id=task_id,
            )
        text = mark_done(text, human_done_entry())
    elif status is not None:
        if status not in EDITABLE_STATUSES:
            raise TaskEditError(
                "invalid_status",
                f"status must be one of {', '.join(EDITABLE_STATUSES)}; "
                "'done' is set only by PR approval",
                id=task_id,
            )
        if task.status == "done" and status != "done":
            raise TaskEditError(
                "invalid_status",
                "task is done; its status changes only through PR approval",
                id=task_id,
            )
        text = _apply(text, "set", "status", status)
    if workflow is not None:
        if not workflow.strip():
            raise TaskEditError("invalid_value", "workflow must not be empty", id=task_id)
        text = _apply(text, "set", "workflow", workflow.strip())
    if clear_workflow:
        text = _apply(text, "remove", "workflow")
    if writes is not None:
        text = _apply(text, "set", "writes", _dedupe(writes))
    if clear_writes:
        text = _apply(text, "remove", "writes")
    if auto_merge is not None:
        text = _apply(text, "set", "auto_merge", auto_merge)
    if clear_auto_merge:
        text = _apply(text, "remove", "auto_merge")
    if assignee is not None:
        text = _apply(text, "set", "assignee", assignee)
    if clear_assignee:
        text = _apply(text, "remove", "assignee")
    for key, values in (("depends_on", depends_on), ("related", related)):
        if values is not None:
            if task_id in values:
                raise TaskEditError("self_ref", "task cannot reference itself", id=task_id)
            text = _apply(text, "set", key, _dedupe(values))
    if parameters is not None:
        _validate_parameters(parameters)
        for key, value in parameters.items():
            assert value is None or isinstance(value, (str, list, bool, int))
            text = _apply(text, "remove" if value is None else "set", key, value)
    if body is not None:
        text = replace_body(text, body)
    return _commit(backlog, baseline, {task.path: text}, "edit", task.path, task_id)


def complete_task(root: Path, task_id: str, entry: str) -> WriteResult:
    """``status: done`` and `entry` in ``## Běhy`` for a task that ends without a PR.

    For a run that found nothing to change and for a task done by a person. A cancelled
    task is not completed; a done one comes back unchanged.
    """
    backlog = load_for_edit(root)
    baseline = check_backlog(backlog)
    task = find_task(backlog, task_id, baseline)
    if task.status == "cancelled":
        raise TaskEditError("invalid_status", "task is cancelled", id=task_id)
    text = mark_done(_read(root, task), entry)
    return _commit(backlog, baseline, {task.path: text}, "done", task.path, task_id)


def link_task(
    root: Path,
    task_id: str,
    *,
    depends_on: list[str] | None = None,
    related: list[str] | None = None,
    remove: bool = False,
) -> WriteResult:
    """Add (or with ``remove`` drop) ``depends_on`` / ``related`` references of a task."""
    depends_on = _dedupe(depends_on or [])
    related = _dedupe(related or [])
    if not depends_on and not related:
        raise TaskEditError("no_changes", "give at least one --depends-on or --related id")
    if task_id in depends_on or task_id in related:
        raise TaskEditError("self_ref", f"task '{task_id}' cannot refer to itself", id=task_id)
    backlog = load_for_edit(root)
    baseline = check_backlog(backlog)
    task = find_task(backlog, task_id, baseline)
    text = _read(root, task)
    for key, refs, current in (
        ("depends_on", depends_on, task.depends_on),
        ("related", related, task.related),
    ):
        if not refs:
            continue
        if remove:
            new = [r for r in current if r not in refs]
        else:
            new = current + [r for r in refs if r not in current]
        if new == current:
            continue
        if not new and key == "related":
            text = _apply(text, "remove", key)
        else:
            text = _apply(text, "set", key, new)
    return _commit(backlog, baseline, {task.path: text}, "link", task.path, task_id)


@dataclass
class ContainerWriteResult:
    action: str
    changed: bool
    path: str
    container: Container
    backlog: Backlog
    issues: list[Issue] = field(default_factory=list)


def _find_container(backlog: Backlog, container_id: str) -> Container | None:
    for container in iter_containers(backlog.containers):
        if container.id == container_id:
            return container
    return None


def set_auto_continue(root: Path, container_id: str, enabled: bool | None) -> ContainerWriteResult:
    """Set (``True``/``False``) or remove (``None``) ``auto_continue`` in a container's index.md.

    Writes the working tree; runs read the backlog from base, so commit it first.
    """
    return _set_container_flag(
        root, container_id, "auto_continue", enabled, "backlog auto-continue"
    )


def set_auto_merge(root: Path, container_id: str, enabled: bool | None) -> ContainerWriteResult:
    """Set (``True``/``False``) or remove (``None``) ``auto_merge`` in a container's index.md.

    Writes the working tree; runs read the backlog from base, so commit it first.
    """
    return _set_container_flag(root, container_id, "auto_merge", enabled, "backlog auto-merge")


def _set_container_flag(
    root: Path, container_id: str, key: str, enabled: bool | None, command: str
) -> ContainerWriteResult:
    backlog = load_for_edit(root)
    container = _find_container(backlog, container_id)
    if container is None:
        names = " or ".join(backlog.settings.levels[:-1])
        raise TaskEditError("unknown_container", f"no {names} '{container_id}'", id=container_id)
    rel = container.index_path
    if rel is None:
        raise TaskEditError(
            "no_index", f"'{container_id}' has no index.md", id=container_id, path=container.path
        )
    text = (root / rel).read_text(encoding="utf-8")
    if enabled is None:
        new_text = _apply(text, "remove", key)
    else:
        new_text = _apply(text, "set", key, enabled)
    changed = _write_checked(backlog, check_backlog(backlog), {rel: new_text}, command)
    after = load_backlog(root, backlog.settings)
    found = _find_container(after, container_id)
    if found is None:  # pragma: no cover - guarded by validation
        raise TaskEditError("unknown_container", f"'{container_id}' not found after write")
    return ContainerWriteResult(key, changed, rel, found, after, check_backlog(after))


# ── projects and steps (containers): add and edit index.md ───────────────────

# keys of a container's index.md that ``edit_container`` sets or removes
CONTAINER_KEYS: tuple[str, ...] = (
    "harness",
    "model",
    "thinking",
    "workflow",
    "writes",
    "auto_continue",
    "auto_heal",
    "quota_switch",
    "quota_switch_back",
)
_STR_KEYS = (
    "workflow",
    "harness",
    "model",
    "thinking",
)


def _container_depth(backlog: Backlog, container: Container) -> int:
    return backlog.settings.levels.index(container.level)


def find_container(
    backlog: Backlog, container_id: str, issues: list[Issue] | None = None
) -> Container:
    """The project or step ``container_id``; ``TaskEditError`` when unknown or ambiguous."""
    container = _find_container(backlog, container_id)
    if container is None:
        names = " or ".join(backlog.settings.levels[:-1])
        raise TaskEditError("unknown_container", f"no {names} '{container_id}'", id=container_id)
    if issues is None:
        issues = check_backlog(backlog)
    if any(i.code == "duplicate_id" and i.id == container_id for i in issues):
        raise TaskEditError(
            "duplicate_id",
            f"id '{container_id}' is not unique",
            id=container_id,
            path=container.index_path,
        )
    return container


def _local_code(container_id: str, parent: Container | None) -> str:
    """The directory code: a step ``M01-S03`` of project ``M01`` lives in ``S03-<slug>``."""
    if parent is not None and parent.id and container_id.startswith(f"{parent.id}-"):
        return container_id[len(parent.id) + 1 :]
    return container_id


def _container_result(
    backlog: Backlog, action: str, changed: bool, rel: str, container_id: str
) -> ContainerWriteResult:
    after = load_backlog(backlog.root, backlog.settings)
    found = _find_container(after, container_id)
    if found is None:  # pragma: no cover - guarded by validation
        raise TaskEditError("unknown_container", f"'{container_id}' not found after write")
    return ContainerWriteResult(action, changed, rel, found, after, check_backlog(after))


def add_container(
    root: Path,
    parent: str | None,
    container_id: str,
    title: str,
    *,
    body: str = "",
) -> ContainerWriteResult:
    """Create a project (``parent`` is ``None``) or a step of project ``parent``.

    ``container_id`` is the short code (``S03``); the id is composed with the parent's
    (``M01-S03``, see ``compose_id``). Writes ``<backlog_dir>/<code>-<slug>/index.md`` (a
    step's directory is in its project's directory: ``S03-<slug>``). The id is unique; a
    write that breaks the backlog is rejected with ``backlog_invalid``.
    """
    backlog = load_for_edit(root)
    levels = backlog.settings.levels
    container_id = compose_id(parent, container_id)
    title = title.strip()
    if not title:
        raise TaskEditError("invalid_value", "title must not be empty", id=container_id)
    baseline = check_backlog(backlog)
    parent_node: Container | None = None
    if parent is not None:
        parent_node = find_container(backlog, parent, baseline)
        if _container_depth(backlog, parent_node) + 1 > len(levels) - 2:
            raise TaskEditError(
                "invalid_value",
                f"'{parent}' is a {parent_node.level}; it holds {levels[-1]}s, not {levels[-2]}s",
                id=parent,
            )
    level = levels[0] if parent_node is None else levels[_container_depth(backlog, parent_node) + 1]
    slug = slugify(title)
    code = _local_code(container_id, parent_node)
    name = f"{code}-{slug}" if slug else code
    if parent_node is not None:
        base = parent_node.path
    else:
        if not backlog.roots:  # pragma: no cover - load_for_edit needs a root
            raise TaskEditError("missing_backlog_dir", "no backlog directory exists")
        base = backlog.roots[0]
    rel_dir = f"{base}/{name}"
    rel = f"{rel_dir}/{INDEX_FILE}"
    if container_id in backlog.by_id:
        other = backlog.by_id[container_id]
        where = node_file(other)
        raise TaskEditError(
            "backlog_invalid",
            f"change rejected: id '{container_id}' exists already",
            exit_code=1,
            issues=[
                Issue(
                    "duplicate_id",
                    f"duplicate id '{container_id}' in {rel} (first defined in {where})",
                    rel,
                    container_id,
                )
            ],
        )
    if (root / rel_dir).exists():
        raise TaskEditError(
            "file_exists", f"directory '{rel_dir}' exists already", path=rel_dir, id=container_id
        )
    text = new_index_text(container_id, title, body)
    changed = _write_checked(backlog, baseline, {rel: text}, f"backlog add {level}")
    return _container_result(backlog, "add", changed, rel, container_id)


def _check_chain(value: object) -> list[str]:
    """``quota_switch``: the canonical names of known harnesses, each at most once."""
    from aifactory.harness import canonical

    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise TaskEditError("invalid_value", "'quota_switch' must be a list of harness names")
    chain: list[str] = []
    for item in value:
        try:
            name = canonical(item.strip())
        except ValueError as exc:
            raise TaskEditError("invalid_value", str(exc)) from exc
        if name in chain:
            raise TaskEditError("invalid_value", f"harness {name} is twice in quota_switch")
        chain.append(name)
    return chain


def _check_container_value(key: str, value: object) -> str | list[str] | bool:
    if key in ("harness", "model", "thinking"):
        from aifactory.workflow.task_advice import TaskParameters

        try:
            TaskParameters.model_validate({key: value})
        except ValueError as exc:
            raise TaskEditError("invalid_value", str(exc)) from exc
    if key in _STR_KEYS:
        if not isinstance(value, str) or not value.strip():
            raise TaskEditError("invalid_value", f"'{key}' must be a non-empty string")
        return value.strip()
    if key == "writes":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise TaskEditError("invalid_value", "'writes' must be a list of strings")
        return _dedupe([str(v) for v in value])
    if key == "quota_switch":
        return _check_chain(value)
    if key in ("auto_continue", "auto_heal", "quota_switch_back"):
        if not isinstance(value, bool):
            raise TaskEditError("invalid_value", f"'{key}' must be true or false")
        return value
    raise TaskEditError(  # pragma: no cover - keys are checked by the caller
        "invalid_value", f"unknown key '{key}'"
    )


def edit_container(
    root: Path,
    container_id: str,
    *,
    title: str | None = None,
    values: dict[str, object] | None = None,
    clear: list[str] | tuple[str, ...] = (),
) -> ContainerWriteResult:
    """Change the title of a project or step and set (``values``) or remove (``clear``) the
    keys ``CONTAINER_KEYS`` of its ``index.md``. Other keys and the body stay as they are.

    Writes the working tree; runs read the backlog from base, so commit it first.
    """
    values = dict(values or {})
    clear = list(dict.fromkeys(clear))
    for key in [*values, *clear]:
        if key not in CONTAINER_KEYS:
            raise TaskEditError(
                "invalid_value",
                f"unknown key '{key}', allowed: {', '.join(CONTAINER_KEYS)}",
                id=container_id,
            )
    both = [k for k in clear if k in values]
    if both:
        raise TaskEditError(
            "conflicting_options",
            f"'{both[0]}' cannot be set and removed at once",
            id=container_id,
        )
    if title is None and not values and not clear:
        raise TaskEditError("no_changes", "nothing to change, give at least one option")
    checked = {k: _check_container_value(k, v) for k, v in values.items()}
    backlog = load_for_edit(root)
    baseline = check_backlog(backlog)
    container = find_container(backlog, container_id, baseline)
    if container.parent is not None and any(k in values for k in HARNESS_KEYS):
        raise TaskEditError("invalid_value", "harness settings are only allowed on a project")
    rel = container.index_path
    if rel is None:
        raise TaskEditError(
            "no_index", f"'{container_id}' has no index.md", id=container_id, path=container.path
        )
    text = (root / rel).read_text(encoding="utf-8")
    if title is not None:
        if not title.strip():
            raise TaskEditError("invalid_value", "title must not be empty", id=container_id)
        text = _apply(text, "set", "title", title.strip())
    for key, value in checked.items():
        text = _apply(text, "set", key, value)
    for key in clear:
        text = _apply(text, "remove", key)
    changed = _write_checked(backlog, baseline, {rel: text}, "backlog edit")
    return _container_result(backlog, "edit", changed, rel, container_id)


def _validate_parameters(parameters: dict[str, object]) -> None:
    from pydantic import ValidationError

    from aifactory.workflow.task_advice import TaskParameters

    try:
        TaskParameters.model_validate(parameters)
    except ValidationError as exc:
        raise TaskEditError("invalid_value", "invalid task parameters") from exc


@dataclass
class NewTask:
    """One task of a batch (``add_batch``); ``depends_on`` may name codes of the batch."""

    code: str
    title: str
    body: str = ""
    workflow: str | None = None
    writes: list[str] | None = None
    depends_on: list[str] = field(default_factory=list)


@dataclass
class BatchTask:
    id: str
    title: str
    body: str
    workflow: str | None
    writes: list[str] | None
    depends_on: list[str]
    path: str


@dataclass
class BatchResult:
    """A planned (``written`` False) or written batch of one step and its new tasks."""

    step_id: str
    step_title: str
    step_body: str
    step_path: str
    new_step: bool
    tasks: list[BatchTask]
    files: list[str]
    written: bool


def add_batch(
    root: Path,
    tasks: list[NewTask],
    *,
    step: str | None = None,
    project: str | None = None,
    step_code: str | None = None,
    step_title: str | None = None,
    step_body: str = "",
    write: bool = False,
) -> BatchResult:
    """Add ``tasks`` to the existing ``step``, or to a new step ``step_code`` of ``project``.

    Every problem is collected first and raised together as ``backlog_invalid`` (codes as
    in ``factory backlog check`` plus ``invalid_id``, ``invalid_value``, ``self_ref``,
    ``duplicate_id``, ``file_exists``); then the whole batch is validated on a copy of the
    backlog like ``add_task``. Without ``write`` nothing is written; nothing is committed.
    """
    if (step is None) == (project is None):
        raise TaskEditError("conflicting_options", "give either a step or a project")
    backlog = load_for_edit(root)
    baseline = check_backlog(backlog)
    levels = backlog.settings.levels
    problems: list[Issue] = []
    new_step = project is not None
    if step is not None:
        container = _find_step(backlog, step)
        step_id = container.id or step
        title = container.title or ""
        body = container.body
        rel_dir = container.path
        existing = {t.id for t in container.tasks}
    else:
        assert project is not None
        parent = find_container(backlog, project, baseline)
        if _container_depth(backlog, parent) != len(levels) - 3:
            raise TaskEditError(
                "invalid_value", f"'{project}' does not hold {levels[-2]}s", id=project
            )
        step_id = compose_id(parent.id, step_code or "")
        title = (step_title or "").strip()
        body = step_body
        if not title:
            problems.append(Issue("invalid_value", f"{levels[-2]} title must not be empty", ""))
        if step_id in backlog.by_id:
            where = node_file(backlog.by_id[step_id])
            problems.append(
                Issue("duplicate_id", f"id '{step_id}' exists already ({where})", where, step_id)
            )
        slug = slugify(title)
        code = _local_code(step_id, parent)
        rel_dir = f"{parent.path}/{code}-{slug}" if slug else f"{parent.path}/{code}"
        if (root / rel_dir).exists():
            problems.append(
                Issue("file_exists", f"directory '{rel_dir}' exists already", rel_dir, step_id)
            )
        existing = set()
    ids: dict[str, str] = {}
    for task in tasks:
        try:
            task_id = compose_id(step_id, task.code)
        except TaskEditError as exc:
            problems.append(Issue(exc.code, exc.message, "", task.code))
            continue
        if task_id in ids.values() or task_id in backlog.by_id or task_id in existing:
            problems.append(
                Issue("duplicate_id", f"task id '{task_id}' is not unique", "", task_id)
            )
        ids[task.code] = task_id
        ids.setdefault(task_id, task_id)
    planned: list[BatchTask] = []
    changes: dict[str, str] = {}
    if new_step:
        changes[f"{rel_dir}/{INDEX_FILE}"] = new_index_text(step_id, title, body)
    for task in tasks:
        if task.code not in ids:
            continue
        task_id = ids[task.code]
        task_title = task.title.strip()
        if not task_title:
            problems.append(Issue("invalid_value", "title must not be empty", "", task_id))
        if task.workflow is not None and not task.workflow.strip():
            problems.append(Issue("invalid_value", "workflow must not be empty", "", task_id))
        depends = _dedupe([ids.get(ref, ref) for ref in task.depends_on])
        if task_id in depends:
            problems.append(
                Issue("self_ref", f"task '{task_id}' cannot depend on itself", "", task_id)
            )
        slug = slugify(task_title)
        rel = f"{rel_dir}/{task_id}-{slug}.md" if slug else f"{rel_dir}/{task_id}.md"
        if (root / rel).exists():
            problems.append(Issue("file_exists", f"file '{rel}' exists already", rel, task_id))
        writes = _dedupe(task.writes) if task.writes is not None else None
        fields: dict[str, object] = {
            "id": task_id,
            "title": task_title,
            "status": "todo",
            "workflow": task.workflow,
            "depends_on": depends,
            "writes": writes,
        }
        changes[rel] = new_task_text(fields, task.body)
        planned.append(
            BatchTask(task_id, task_title, task.body.strip(), task.workflow, writes, depends, rel)
        )
    if not tasks:
        problems.append(Issue("invalid_value", "the batch has no task", "", step_id))
    if not problems:
        for rel in changes:
            try:
                _guard(root, backlog, rel)
            except TaskEditError as exc:
                problems.append(Issue(exc.code, exc.message, rel))
    if not problems:
        problems = _new_issues(backlog, baseline, changes)
    if problems:
        raise TaskEditError(
            "backlog_invalid",
            f"change rejected: {len(problems)} problem(s)",
            exit_code=1,
            issues=problems,
        )
    if write:
        _write_checked(backlog, baseline, changes, "backlog propose")
    return BatchResult(
        step_id=step_id,
        step_title=title,
        step_body=body.strip(),
        step_path=rel_dir,
        new_step=new_step,
        tasks=planned,
        files=list(changes),
        written=write,
    )
