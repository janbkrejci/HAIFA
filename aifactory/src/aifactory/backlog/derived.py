"""Values computed from the tree: inheritance, done-ness, ready/blocked, "blocks"."""

from __future__ import annotations

from aifactory.backlog.loader import iter_tasks
from aifactory.backlog.model import (
    HUMAN,
    INHERITED_KEYS,
    Backlog,
    Container,
    Node,
    Task,
    Unmet,
    node_file,
)
from aifactory.config import ProjectSettings
from aifactory.config.settings import CONFIG_FILE


def ancestors(node: Node) -> list[Container]:
    """Parents from the nearest up to the top level."""
    result: list[Container] = []
    current = node.parent
    while current is not None:
        result.append(current)
        current = current.parent
    return result


def harness_values(node: Node) -> dict[str, object]:
    """Inherited binding; switching harness drops the previous harness's model."""
    result: dict[str, object] = {}
    for values in [*(own_values(c) for c in reversed(ancestors(node))), own_values(node)]:
        harness = values.get("harness")
        if harness and harness != result.get("harness"):
            result.pop("model", None)
        result.update({k: values[k] for k in ("harness", "model", "thinking") if values.get(k)})
    return result


def effective(task: Task) -> dict[str, object]:
    """Inherited values: top ancestor first, nearer ancestors override, the task wins."""
    values: dict[str, object] = {}
    for container in reversed(ancestors(task)):
        values.update(container.defaults)
    values.update(task.own)
    return {k: values[k] for k in INHERITED_KEYS if k in values}


DEFAULT_WORKFLOW = "simple-sdlc"
"""The workflow of a task when no level sets ``workflow`` (an explicit ``null`` means none)."""
DEFAULT_WRITES: tuple[str, ...] = ("**",)
"""The writes of a task when no level sets ``writes``: the whole repo; protected files stay
protected (``protected_files``, enforced by the engine and the guard)."""


def effective_workflow(task: Task) -> object:
    values = effective(task)
    return values["workflow"] if "workflow" in values else DEFAULT_WORKFLOW


def has_workflow(task: Task) -> bool:
    """False only when the nearest level sets ``workflow: null``; unset means the default."""
    return effective_workflow(task) is not None


def is_human(task: Task) -> bool:
    """A task for a person (``assignee: human``, inherited): no run starts it."""
    return effective(task).get("assignee") == HUMAN


def waits_for_human(backlog: Backlog, task: Task) -> list[str]:
    """The unmet dependencies of `task` (tasks, or tasks of a container) that are a person's."""
    result: list[str] = []
    for item in unmet(backlog, task):
        for dep in item.missing or [item.id]:
            node = backlog.by_id.get(dep)
            if isinstance(node, Task) and is_human(node) and dep not in result:
                result.append(dep)
    return result


def effective_test_timeout(task: Task) -> object:
    """The nearest ``test_timeout``: the task's own, then ``index.md`` upwards; ``None``
    when unset. A level without the key or with ``null`` is skipped."""
    return _nearest(task, "test_timeout")


def _nearest(task: Task, key: str) -> object:
    for values in (task.own, *(c.defaults for c in ancestors(task))):
        value = values.get(key)
        if value is not None:
            return value
    return None


def effective_writes(task: Task) -> list[str]:
    """The task's writes, inherited; ``DEFAULT_WRITES`` when no level sets the key."""
    values = effective(task)
    if "writes" not in values:
        return list(DEFAULT_WRITES)
    value = values["writes"]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def descendant_tasks(container: Container) -> list[Task]:
    result = list(container.tasks)
    for child in container.children:
        result.extend(descendant_tasks(child))
    return sorted(result, key=lambda t: t.path)


def active_tasks(container: Container) -> list[Task]:
    return [t for t in descendant_tasks(container) if t.status != "cancelled"]


def is_done(node: Node) -> bool:
    """A task is done by status; a container when all its non-cancelled tasks are done."""
    if isinstance(node, Task):
        return node.status == "done"
    active = active_tasks(node)
    return bool(active) and all(t.status == "done" for t in active)


def unmet(backlog: Backlog, task: Task) -> list[Unmet]:
    """Dependencies of ``task`` that are not satisfied yet."""
    result: list[Unmet] = []
    for dep in task.depends_on:
        node = backlog.by_id.get(dep)
        if node is None:
            result.append(Unmet(dep, "unknown", [dep]))
        elif isinstance(node, Task):
            if node.status == "cancelled":
                result.append(Unmet(dep, "cancelled", [dep]))
            elif node.status != "done":
                result.append(Unmet(dep, "not_done", [dep]))
        else:
            active = active_tasks(node)
            if not active:
                result.append(Unmet(dep, "empty", []))
            else:
                missing = sorted(t.id for t in active if t.status != "done")
                if missing:
                    result.append(Unmet(dep, "incomplete", missing))
    return result


def derived_state(backlog: Backlog, task: Task) -> str:
    """``done``/``cancelled`` as stored; ``todo`` becomes ``blocked``, else ``human`` for a
    person's task and ``ready`` for an agent's."""
    if task.status in ("done", "cancelled"):
        return task.status
    if task.status != "todo":
        return "invalid"
    if unmet(backlog, task):
        return "blocked"
    return "human" if is_human(task) else "ready"


def blocks(backlog: Backlog) -> dict[str, list[str]]:
    """Reverse of ``depends_on``, computed in memory only."""
    result: dict[str, set[str]] = {}
    for task in iter_tasks(backlog):
        for dep in task.depends_on:
            if dep in backlog.by_id:
                result.setdefault(dep, set()).add(task.id)
    return {k: sorted(v) for k, v in sorted(result.items())}


def followed_by(backlog: Backlog, task_id: str) -> list[str]:
    """Ids of the tasks whose ``follows`` is `task_id`, in backlog order."""
    return [t.id for t in iter_tasks(backlog) if t.follows == task_id]


def progress(container: Container) -> tuple[int, int]:
    """(done, total) over descendant tasks, cancelled tasks excluded."""
    active = active_tasks(container)
    return sum(1 for t in active if t.status == "done"), len(active)


# keys whose ``null`` at a level is skipped (the next level up decides); for the other
# inherited keys the nearest level that has the key wins, even with ``null``
_SKIP_NULL_KEYS: tuple[str, ...] = (
    "test_timeout",
    "auto_continue",
    "auto_merge",
    "auto_heal",
    "quota_switch",
    "quota_switch_back",
)
# inherited keys with a fallback in ``.factory/config.yaml`` (key -> setting)
CONFIG_FALLBACK: dict[str, str] = {
    "test_timeout": "test_timeout",
}
# inherited flags that are ``false`` when no level sets them
_FLAG_DEFAULTS: tuple[str, ...] = ("auto_continue", "auto_merge", "quota_switch_back")
# inherited lists that are ``[]`` when no level sets them (``quota_switch``: no chain)
_LIST_DEFAULTS: tuple[str, ...] = ("quota_switch",)
# inherited flags that are ``true`` when no level sets them (``auto_heal``: the chain's
# automatic actions after a failure, ``run.heal``)
_TRUE_FLAG_DEFAULTS: tuple[str, ...] = ("auto_heal",)


def own_values(node: Node) -> dict[str, object]:
    """The inherited keys set in ``node``'s own file (``index.md`` or the task file)."""
    return dict(node.own if isinstance(node, Task) else node.defaults)


def effective_sources(node: Node, settings: ProjectSettings) -> dict[str, dict[str, object]]:
    """Every inherited key of ``node``: its effective ``value`` and its ``origin``.

    ``origin`` is ``{"source": "own"|"inherited", "level", "id", "path"}`` for a value of a
    level (``own``: ``node`` itself), ``{"source": "config", "path": ".factory/config.yaml",
    "key"}`` for a fallback of ``.factory/config.yaml``, ``{"source": "default"}`` for a
    flag no level sets (``false``, ``auto_heal`` ``true``) and for ``quota_switch``
    (``[]``), and ``None`` when nothing gives a value.
    """
    chain: list[Node] = [node, *ancestors(node)]
    result: dict[str, dict[str, object]] = {}
    for key in INHERITED_KEYS:
        entry: dict[str, object] | None = None
        for level_node in chain:
            values = own_values(level_node)
            if key not in values:
                continue
            if values[key] is None and key in _SKIP_NULL_KEYS:
                continue
            entry = {
                "value": values[key],
                "origin": {
                    "source": "own" if level_node is node else "inherited",
                    "level": level_node.level,
                    "id": level_node.id,
                    "path": node_file(level_node),
                },
            }
            break
        if entry is None and key in CONFIG_FALLBACK:
            setting = CONFIG_FALLBACK[key]
            value = getattr(settings, setting)
            if value is not None:
                if isinstance(value, tuple):
                    value = list(value)
                entry = {
                    "value": value,
                    "origin": {"source": "config", "path": CONFIG_FILE, "key": setting},
                }
        if entry is None and key in _FLAG_DEFAULTS:
            entry = {"value": False, "origin": {"source": "default"}}
        if entry is None and key in _TRUE_FLAG_DEFAULTS:
            entry = {"value": True, "origin": {"source": "default"}}
        if entry is None and key in _LIST_DEFAULTS:
            entry = {"value": [], "origin": {"source": "default"}}
        result[key] = entry or {"value": None, "origin": None}
    return result
