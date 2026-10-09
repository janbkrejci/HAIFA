"""Filters, JSON and the text tree for ``factory backlog list``."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from aifactory.backlog.derived import (
    blocks,
    derived_state,
    descendant_tasks,
    effective,
    effective_sources,
    effective_workflow,
    effective_writes,
    is_done,
    progress,
    unmet,
)
from aifactory.backlog.loader import iter_containers, iter_tasks
from aifactory.backlog.model import Backlog, Container, Issue, Task

STATUS_FILTERS: tuple[str, ...] = ("todo", "done", "cancelled", "ready", "blocked")


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, _dt.date | _dt.datetime):
        return value.isoformat()
    return str(value)


def counts(backlog: Backlog) -> dict[str, int]:
    """Number of items per level, keyed by the configured level names."""
    levels = backlog.settings.levels
    result = {level: 0 for level in levels}
    for container in iter_containers(backlog.containers):
        result[container.level] += 1
    result[levels[-1]] = sum(1 for _ in iter_tasks(backlog))
    return result


def task_matches(backlog: Backlog, task: Task, status: str | None) -> bool:
    if status is None:
        return True
    return task.status == status or derived_state(backlog, task) == status


def select_projects(backlog: Backlog, project: str | None) -> list[Container]:
    """Top-level containers (projects), or those whose id or directory name is ``project``."""
    if project is None:
        return list(backlog.containers)
    found = [c for c in backlog.containers if c.id == project or Path(c.path).name == project]
    if not found:
        raise LookupError(project)
    return found


def _container_shown(backlog: Backlog, container: Container, status: str | None) -> bool:
    if status is None:
        return True
    return any(task_matches(backlog, t, status) for t in descendant_tasks(container))


def issues_to_json(backlog: Backlog, issues: list[Issue]) -> dict[str, object]:
    return {
        "ok": not issues,
        "errors": [i.to_dict() for i in issues],
        "counts": counts(backlog),
    }


def task_to_json(backlog: Backlog, task: Task, reverse: dict[str, list[str]]) -> dict[str, object]:
    return {
        "kind": "task",
        "id": task.id,
        "title": task.title,
        "level": task.level,
        "path": task.path,
        "status": task.status,
        "state": derived_state(backlog, task),
        "workflow": _jsonable(effective_workflow(task)),
        "effective": _jsonable(effective(task)),
        "depends_on": list(task.depends_on),
        "related": list(task.related),
        "writes": effective_writes(task),
        "own_writes": list(task.writes),
        "blocked_by": [u.to_dict() for u in unmet(backlog, task)] if task.status == "todo" else [],
        "blocks": list(reverse.get(task.id, [])),
    }


def container_to_json(
    backlog: Backlog,
    container: Container,
    reverse: dict[str, list[str]],
    status: str | None = None,
) -> dict[str, object]:
    done, total = progress(container)
    children: list[dict[str, object]] = [
        container_to_json(backlog, c, reverse, status)
        for c in container.children
        if _container_shown(backlog, c, status)
    ]
    children.extend(
        task_to_json(backlog, t, reverse)
        for t in container.tasks
        if task_matches(backlog, t, status)
    )
    return {
        "kind": "container",
        "id": container.id,
        "title": container.title,
        "level": container.level,
        "path": container.path,
        "progress": {"done": done, "total": total},
        "done": is_done(container),
        "defaults": _jsonable(container.defaults),
        "blocks": list(reverse.get(container.id, [])) if container.id else [],
        "children": children,
    }


def backlog_to_json(
    backlog: Backlog,
    issues: list[Issue],
    *,
    status: str | None = None,
    project: str | None = None,
) -> dict[str, object]:
    """The (filtered) tree as JSON. Raises ``LookupError`` for an unknown ``project``."""
    reverse = blocks(backlog)
    items = [
        container_to_json(backlog, c, reverse, status)
        for c in select_projects(backlog, project)
        if _container_shown(backlog, c, status)
    ]
    return {
        "ok": not issues,
        "levels": list(backlog.settings.levels),
        "backlog_dir": backlog.settings.backlog_patterns[0],
        "backlog_dirs": list(backlog.roots),
        "filters": {"status": status, "project": project},
        "items": items,
        "issues": [i.to_dict() for i in issues],
    }


def waits_for(backlog: Backlog, task: Task) -> str:
    waits: list[str] = []
    for u in unmet(backlog, task):
        if u.reason == "incomplete":
            waits.append(f"{u.id} [{', '.join(u.missing)}]")
        elif u.reason == "not_done":
            waits.append(u.id)
        else:
            waits.append(f"{u.id} ({u.reason})")
    return ", ".join(waits)


def format_tree(
    backlog: Backlog, *, status: str | None = None, project: str | None = None
) -> list[str]:
    """Human-readable tree with derived states, two spaces per level.

    Raises ``LookupError`` for an unknown ``project``.
    """
    reverse = blocks(backlog)
    lines: list[str] = []

    def blocks_suffix(node_id: str | None) -> str:
        if node_id and reverse.get(node_id):
            return f"  (blocks: {', '.join(reverse[node_id])})"
        return ""

    def walk(container: Container, depth: int) -> None:
        if not _container_shown(backlog, container, status):
            return
        pad = "  " * depth
        done, total = progress(container)
        if container.id is None:
            head = f"? {container.path}"
        else:
            head = f"{container.id} {container.title or ''}".rstrip()
        text = f"{pad}{head}  [{done}/{total}]"
        if is_done(container):
            text += "  done"
        lines.append(text + blocks_suffix(container.id))
        for child in container.children:
            walk(child, depth + 1)
        for task in container.tasks:
            if not task_matches(backlog, task, status):
                continue
            state = derived_state(backlog, task)
            line = f"{pad}  {task.id} {task.title}  {state}"
            if state == "blocked":
                line += f" (waits for: {waits_for(backlog, task)})"
            elif state == "invalid":
                line += f" (status: {task.status!r})"
            lines.append(line + blocks_suffix(task.id))

    for container in select_projects(backlog, project):
        walk(container, 0)
    return lines


def container_detail_json(backlog: Backlog, container: Container) -> dict[str, object]:
    """A project or step: title, description (``body``), its own values (``own``: inherited
    keys of its ``index.md``; ``extra``: other keys) and ``effective`` values with their
    origin (``effective_sources``)."""
    effective_values = effective_sources(container, backlog.settings)
    return {
        "kind": "container",
        "id": container.id,
        "title": container.title,
        "level": container.level,
        "path": container.path,
        "index_path": container.index_path,
        "parent": container.parent.id if container.parent is not None else None,
        "children": [c.id for c in container.children if c.id is not None],
        "body": container.body,
        "own": _jsonable(dict(container.defaults)),
        "extra": _jsonable(dict(container.extra)),
        "effective": _jsonable(effective_values),
    }
