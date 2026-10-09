"""The dashboard's Backlog screen: tree, kanban, task detail and task writes.

Reads the backlog of the main checkout with ``aifactory.backlog`` and the task runs and
pull requests from the trace DB (a missing trace DB is not created). Every write goes
through the same core functions as ``factory task add|edit|link``
(``aifactory.backlog.add_task``, ``edit_task``, ``link_task``): the change is validated
before anything is written and only files under the backlog roots change. Nothing is
committed except by ``commit`` (``factory backlog commit``), which commits the backlog
changes to ``base``.

Board states (the kanban columns), first match wins: ``done``, ``cancelled``,
``running`` (a running run in the trace DB), ``in review`` (an open PR), ``blocked``,
``ready`` (only with an effective workflow), otherwise ``todo`` (no workflow yet, or an
invalid ``status`` flagged with ``invalid``).
"""

from __future__ import annotations

import sqlite3
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aifactory import backlog as core
from aifactory.backlog import Backlog, Container, Task
from aifactory.config import ConfigError, load_local, load_run_config
from aifactory.config.loader import WORKFLOWS_DIR
from aifactory.config.run import worktree_base
from aifactory.config.source import resolve_commit
from aifactory.errors import UsageError as UsageError
from aifactory.harness import canonical
from aifactory.harness.override import THINKING_LEVELS
from aifactory.run import gitops, task_prs_for, task_runs_for
from aifactory.run.errors import TaskRunError
from aifactory.run.scope import effective_task_writes
from aifactory.run.store import QueuePrefs, TaskRunStore, is_db_busy
from aifactory.run.task import existing_store, resolve_test_command
from aifactory.web.launcher import Launcher
from aifactory.web.settings import config_status
from aifactory.workflow import DEFAULT_WORKFLOWS_DIR

if TYPE_CHECKING:
    from aifactory.web.workflow_advice import AdviceManager

JsonDict = dict[str, Any]

BOARD_STATES: tuple[str, ...] = (
    "todo",
    "ready",
    "blocked",
    "running",
    "in review",
    "done",
    "cancelled",
)

ADD_KEYS = (
    "parameters",
    "workflow_advice_id",
    "step",
    "title",
    "id",
    "slug",
    "workflow",
    "writes",
    "depends_on",
    "related",
    "body",
)
EDIT_KEYS = (
    "parameters",
    "workflow_advice_id",
    "title",
    "status",
    "workflow",
    "clear_workflow",
    "writes",
    "clear_writes",
    "auto_merge",
    "clear_auto_merge",
    "body",
    "depends_on",
    "related",
)
LINK_KEYS = ("depends_on", "related", "remove")
RUN_KEYS = ("note", "force", "harness", "model", "thinking", "auto")
QUEUE_ORDER_KEYS = ("order",)
EXCLUDE_KEYS = ("excluded",)
AUTO_KEYS = ("mode",)
COMMIT_KEYS = ("message",)
AUTO_MODES: dict[str, bool | None] = {"on": True, "off": False, "inherit": None}


@dataclass
class _Runtime:
    running: set[str] = field(default_factory=set)
    in_review: set[str] = field(default_factory=set)
    last_run: dict[str, str] = field(default_factory=dict)
    queue: QueuePrefs = field(default_factory=QueuePrefs)


def _runs_hidden(exc: Exception) -> str:
    """The warning for runs that could not be read; a busy trace DB says so plainly."""
    if is_db_busy(exc):
        return "runs are not shown: the trace DB is busy with other runs; refresh in a moment"
    if isinstance(exc, sqlite3.Error):
        return f"runs are not shown: trace DB: {exc}"
    return f"runs are not shown: {exc}"


def _runtime(repo: Path) -> tuple[_Runtime, list[str]]:
    """Running tasks, tasks with an open PR and the state of each task's newest run."""
    rt = _Runtime()
    try:
        store = existing_store(repo)
        if store is None:
            return rt, []
        try:
            for run in store.all_runs():  # newest first
                rt.last_run.setdefault(run.task_id, run.state)
                if run.state == "running":
                    rt.running.add(run.task_id)
            rt.in_review = {pr.task_id for pr in store.open_prs()}
            rt.queue = store.queue_prefs()
        finally:
            store.close()
    except TaskRunError as exc:
        if exc.code == "invalid_config":
            raise
        return _Runtime(), [f"runs are not shown: {exc.message}"]
    except sqlite3.Error as exc:
        return _Runtime(), [_runs_hidden(exc)]
    return rt, []


def board_state(backlog: Backlog, task: Task, rt: _Runtime) -> str:
    """The kanban column of ``task`` (see the module docstring)."""
    if task.status == "done":
        return "done"
    if task.status == "cancelled":
        return "cancelled"
    if task.id in rt.running:
        return "running"
    if task.id in rt.in_review:
        return "in review"
    state = core.derived_state(backlog, task)
    if state == "blocked":
        return "blocked"
    if state == "ready" and core.effective_workflow(task):
        return "ready"
    return "todo"


def _task_json(
    backlog: Backlog, task: Task, reverse: dict[str, list[str]], rt: _Runtime
) -> JsonDict:
    data: JsonDict = dict(core.task_to_json(backlog, task, reverse))
    data["board_state"] = board_state(backlog, task, rt)
    own_workflow = task.own.get("workflow")
    data["own_workflow"] = None if own_workflow is None else str(own_workflow)
    own_merge = task.own.get("auto_merge")
    data["own_parameters"] = {
        k: task.own.get(k)
        for k in (
            "harness",
            "model",
            "thinking",
            "source",
            "target",
            "test",
            "test_timeout",
            "specs_dir",
            "docs_dir",
            "auto_continue",
            "auto_merge",
        )
    }
    data["own_auto_merge"] = own_merge if isinstance(own_merge, bool) else None
    data["effective_auto_merge"] = core.effective(task).get("auto_merge") is True
    data["invalid"] = core.derived_state(backlog, task) == "invalid"
    data["last_run"] = rt.last_run.get(task.id)
    rank = rt.queue.order.index(task.id) if task.id in rt.queue.order else None
    data["queue_rank"] = rank
    data["auto_excluded"] = task.id in rt.queue.excluded
    return data


def _queue_sorted(tasks: list[Task], rt: _Runtime) -> list[Task]:
    """The kanban's manual queue first (by rank), then the rest in backlog order."""
    rank = {task_id: i for i, task_id in enumerate(rt.queue.order)}
    ranked = sorted((t for t in tasks if t.id in rank), key=lambda t: rank[t.id])
    return [*ranked, *(t for t in tasks if t.id not in rank)]


def _container_json(
    backlog: Backlog,
    container: Container,
    reverse: dict[str, list[str]],
    rt: _Runtime,
    keep: Callable[[Task], bool],
    filtered: bool,
) -> JsonDict | None:
    children: list[JsonDict] = []
    for child in container.children:
        node = _container_json(backlog, child, reverse, rt, keep, filtered)
        if node is not None:
            children.append(node)
    children.extend(_task_json(backlog, t, reverse, rt) for t in container.tasks if keep(t))
    if filtered and not children:
        return None
    done, total = core.progress(container)
    return {
        "auto_continue": _own_flag(container, "auto_continue"),
        "auto_merge": _own_flag(container, "auto_merge"),
        "effective_auto_continue": _effective_flag(container, "auto_continue"),
        "effective_auto_merge": _effective_flag(container, "auto_merge"),
        "can_toggle": container.index_path is not None,
        "kind": "container",
        "id": container.id,
        "title": container.title,
        "level": container.level,
        "path": container.path,
        "progress": {"done": done, "total": total},
        "state_counts": _state_counts(backlog, list(_subtree_tasks(container)), rt),
        "done": core.is_done(container),
        "blocks": list(reverse.get(container.id, [])) if container.id else [],
        "children": children,
    }


def _own_flag(container: Container, key: str) -> bool | None:
    value = container.defaults.get(key)
    return value if isinstance(value, bool) else None


def _effective_flag(container: Container, key: str) -> bool:
    """The first `key` bool (``auto_continue``, ``auto_merge``) from `container` up, else False."""
    node: Container | None = container
    while node is not None:
        value = _own_flag(node, key)
        if value is not None:
            return value
        node = node.parent
    return False


def workflow_names(repo: Path) -> list[str]:
    """Names of the repository's and the packaged workflows (files are not parsed)."""
    names = {p.stem for p in (repo / WORKFLOWS_DIR).glob("*.yaml")}
    names.update(p.stem for p in DEFAULT_WORKFLOWS_DIR.glob("*.yaml"))
    return sorted(names)


def _warnings(issues: list[Any]) -> list[str]:
    return [f"{len(issues)} problem(s), run 'factory backlog check'"] if issues else []


def _state_counts(backlog: Backlog, tasks: list[Task], rt: _Runtime) -> dict[str, int]:
    """Number of `tasks` per board state (the status filter ignored)."""
    result = dict.fromkeys(BOARD_STATES, 0)
    for task in tasks:
        result[board_state(backlog, task, rt)] += 1
    return result


def backlog_view(repo: Path, *, status: str | None = None) -> tuple[JsonDict, list[str]]:
    """The tree, the flat task list for the kanban, workflows and steps."""
    if status is not None and status not in BOARD_STATES:
        raise core.TaskEditError(
            "invalid_status",
            f"invalid status filter '{status}', allowed: {', '.join(BOARD_STATES)}",
        )
    backlog = core.load_for_edit(repo)
    issues = core.check_backlog(backlog)
    reverse = core.blocks(backlog)
    rt, warnings = _runtime(repo)

    def keep(task: Task) -> bool:
        return status is None or board_state(backlog, task, rt) == status

    filtered = status is not None
    items = [
        node
        for c in backlog.containers
        if (node := _container_json(backlog, c, reverse, rt, keep, filtered)) is not None
    ]
    all_tasks = sorted(core.iter_tasks(backlog), key=lambda t: t.path)
    step_level = backlog.settings.levels[-2] if len(backlog.settings.levels) > 1 else None
    steps: list[JsonDict] = []
    for c in core.iter_containers(backlog.containers):
        if c.level != step_level or c.id is None:
            continue
        top = c
        while top.parent is not None:
            top = top.parent
        steps.append(
            {
                "id": c.id,
                "title": c.title,
                "path": c.path,
                "project": top.id if top is not c else None,
                **({"harness": top.defaults["harness"]} if top.defaults.get("harness") else {}),
            }
        )
    data: JsonDict = {
        "levels": list(backlog.settings.levels),
        "backlog_dir": backlog.settings.backlog_patterns[0],
        "backlog_dirs": list(backlog.roots),
        "filters": {"status": status},
        "states": list(BOARD_STATES),
        "workflows": workflow_names(repo),
        "steps": steps,
        "items": items,
        "tasks": [
            _task_json(backlog, t, reverse, rt) for t in _queue_sorted(all_tasks, rt) if keep(t)
        ],
        "issues": [i.to_dict() for i in issues],
        "counts": core.counts(backlog),
        "state_counts": _state_counts(backlog, all_tasks, rt),
    }
    return data, warnings + _warnings(issues)


def names(repo: Path) -> tuple[JsonDict, list[str]]:
    """The title and level of every container and task id (tooltips of codes in the UI)."""
    backlog = core.load_for_edit(repo)
    result: dict[str, JsonDict] = {}
    for container in core.iter_containers(backlog.containers):
        if container.id is not None:
            result[container.id] = {"title": container.title, "level": container.level}
    for task in core.iter_tasks(backlog):
        result[task.id] = {"title": task.title, "level": task.level}
    data: JsonDict = {"levels": list(backlog.settings.levels), "names": result}
    return data, []


def _depends_ref(backlog: Backlog, dep: str, rt: _Runtime) -> JsonDict:
    node = backlog.by_id.get(dep)
    if node is None:
        return {"id": dep, "kind": "unknown", "title": None, "state": "unknown"}
    if isinstance(node, Task):
        return {
            "id": dep,
            "kind": "task",
            "title": node.title,
            "state": board_state(backlog, node, rt),
        }
    done, total = core.progress(node)
    state = "done" if core.is_done(node) else f"{done}/{total}"
    return {"id": dep, "kind": "container", "title": node.title, "state": state}


def task_detail(repo: Path, task_id: str) -> tuple[JsonDict, list[str]]:
    """``factory task show --json`` plus ``depends`` and ``blocks`` with titles and states."""
    backlog = core.load_for_edit(repo)
    issues = core.check_backlog(backlog)
    task = core.find_task(backlog, task_id, issues)
    reverse = core.blocks(backlog)
    rt, warnings = _runtime(repo)
    own_issues = [i.to_dict() for i in issues if i.path == task.path]
    try:
        runs = [r.to_json() for r in task_runs_for(repo, task.id)]
        prs = [p.to_json() for p in task_prs_for(repo, task.id)]
    except (TaskRunError, sqlite3.Error) as exc:
        if isinstance(exc, TaskRunError) and exc.code == "invalid_config":
            raise
        runs, prs = [], []
        if not warnings:
            warnings = [_runs_hidden(exc)]
    blocked: list[JsonDict] = []
    for bid in reverse.get(task.id, []):
        node = backlog.by_id.get(bid)
        if isinstance(node, Task):
            blocked.append(
                {"id": bid, "title": node.title, "board_state": board_state(backlog, node, rt)}
            )
    data: JsonDict = {
        "task": _task_json(backlog, task, reverse, rt),
        "body": task.body,
        "issues": own_issues,
        "runs": runs,
        "prs": prs,
        "depends": [_depends_ref(backlog, d, rt) for d in task.depends_on],
        "blocks": blocked,
    }
    return data, warnings + _warnings(own_issues)


def _write_json(repo: Path, result: core.WriteResult) -> tuple[JsonDict, list[str]]:
    rt, warnings = _runtime(repo)
    reverse = core.blocks(result.backlog)
    data: JsonDict = {
        "action": result.action,
        "changed": result.changed,
        "path": result.path,
        "task": _task_json(result.backlog, result.task, reverse, rt),
        "issues": [i.to_dict() for i in result.issues],
    }
    return data, warnings + _warnings(result.issues)


def _check_keys(body: JsonDict, allowed: tuple[str, ...]) -> None:
    for key in body:
        if key not in allowed:
            raise UsageError(f"unknown field '{key}', allowed: {', '.join(allowed)}")


def _opt_str(body: JsonDict, key: str) -> str | None:
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise core.TaskEditError("invalid_value", f"'{key}' must be a string")
    return value


def _req_str(body: JsonDict, key: str) -> str:
    value = _opt_str(body, key)
    if value is None:
        raise UsageError(f"missing required field '{key}'")
    return value


def _opt_str_list(body: JsonDict, key: str) -> list[str] | None:
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise core.TaskEditError("invalid_value", f"'{key}' must be a list of strings")
    return list(value)


def _opt_flag(body: JsonDict, key: str) -> bool | None:
    """A bool, or ``None`` when `key` is missing or null."""
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise core.TaskEditError("invalid_value", f"'{key}' must be true or false")
    return value


def _opt_bool(body: JsonDict, key: str) -> bool:
    value = body.get(key)
    if value is None:
        return False
    if not isinstance(value, bool):
        raise core.TaskEditError("invalid_value", f"'{key}' must be true or false")
    return value


def add(
    repo: Path, body: JsonDict, *, advice: AdviceManager | None = None
) -> tuple[JsonDict, list[str]]:
    """``factory task add``: a new ``todo`` task in ``step``."""
    _check_keys(body, ADD_KEYS)
    if "workflow_advice_id" in body:
        if advice is None:
            raise UsageError("workflow advice service is unavailable")
        return advice.save(repo, None, body, add)
    step = _req_str(body, "step")
    title = _req_str(body, "title")
    task_id = _opt_str(body, "id")
    slug = _opt_str(body, "slug")
    workflow = _opt_str(body, "workflow")
    writes = _opt_str_list(body, "writes")
    depends_on = _opt_str_list(body, "depends_on")
    related = _opt_str_list(body, "related")
    text = _opt_str(body, "body") or ""
    result = core.add_task(
        repo,
        step,
        title,
        task_id=task_id,
        slug=slug,
        workflow=workflow,
        writes=writes,
        depends_on=depends_on,
        related=related,
        body=text,
        parameters=_parameters(body),
    )
    return _write_json(repo, result)


def edit(
    repo: Path, task_id: str, body: JsonDict, *, advice: AdviceManager | None = None
) -> tuple[JsonDict, list[str]]:
    """``factory task edit``: title, status, workflow (assign or clear), writes, auto_merge."""
    _check_keys(body, EDIT_KEYS)
    if "workflow_advice_id" in body:
        if advice is None:
            raise UsageError("workflow advice service is unavailable")
        return advice.save(repo, task_id, body, lambda root, values: edit(root, task_id, values))
    title = _opt_str(body, "title")
    status = _opt_str(body, "status")
    workflow = _opt_str(body, "workflow")
    clear_workflow = _opt_bool(body, "clear_workflow")
    writes = _opt_str_list(body, "writes")
    clear_writes = _opt_bool(body, "clear_writes")
    auto_merge = _opt_flag(body, "auto_merge")
    clear_auto_merge = _opt_bool(body, "clear_auto_merge")
    result = core.edit_task(
        repo,
        task_id,
        title=title,
        status=status,
        workflow=workflow,
        clear_workflow=clear_workflow,
        writes=writes,
        clear_writes=clear_writes,
        auto_merge=auto_merge,
        clear_auto_merge=clear_auto_merge,
        parameters=_parameters(body),
        body=_opt_str(body, "body"),
        depends_on=_opt_str_list(body, "depends_on"),
        related=_opt_str_list(body, "related"),
    )
    return _write_json(repo, result)


def link(repo: Path, task_id: str, body: JsonDict) -> tuple[JsonDict, list[str]]:
    """``factory task link``: add (or with ``remove``) drop depends_on / related ids."""
    _check_keys(body, LINK_KEYS)
    depends_on = _opt_str_list(body, "depends_on")
    related = _opt_str_list(body, "related")
    remove = _opt_bool(body, "remove")
    result = core.link_task(repo, task_id, depends_on=depends_on, related=related, remove=remove)
    return _write_json(repo, result)


def status(repo: Path) -> tuple[JsonDict, list[str]]:
    """Backlog changes in the main checkout not committed to base: runs read base (D4).

    Cheap on purpose (the dashboard asks after every backlog write): the base, its commit
    and the backlog roots of the working tree's config.yaml, no run config.
    """
    main = gitops.main_root(repo)
    try:
        base = worktree_base(main)
        sha = resolve_commit(main, base)
        changes = core.backlog_changes(main, sha, core.load_settings(main))
    except ConfigError as exc:  # git failures included (GitError)
        raise TaskRunError("invalid_config", str(exc)) from exc
    data: JsonDict = {
        "base": base,
        "commit": sha,
        "clean": not changes,
        "changes": [c.to_dict() for c in changes],
    }
    return data, []


def commit(repo: Path, body: JsonDict) -> tuple[JsonDict, list[str]]:
    """``factory backlog commit [-m]``: commit the backlog changes to ``base``."""
    _check_keys(body, COMMIT_KEYS)
    message = _opt_str(body, "message")
    result = core.commit_backlog(repo, message)
    return result.to_json(), []


# ── run a task, dependency graph, auto-continue, auto-merge ──────────────────


def run_check(
    repo: Path, task_id: str, *, launcher_busy: bool = False
) -> tuple[JsonDict, list[str]]:
    """What the operator should know before ``factory task run``: D4, unmet deps, a live run."""
    backlog = core.load_for_edit(repo)
    issues = core.check_backlog(backlog)
    task = core.find_task(backlog, task_id, issues)
    main = gitops.main_root(repo)
    config, warnings = config_status(main)
    try:
        rc = load_run_config(main)
    except ConfigError as exc:
        raise TaskRunError("invalid_config", str(exc)) from exc
    with tempfile.TemporaryDirectory(prefix="factory-check-") as tmp:
        dest = Path(tmp)
        try:
            gitops.extract_backlog(main, rc.commit, rc.config.settings.backlog_patterns, dest)
        except (OSError, RuntimeError) as exc:
            raise TaskRunError("invalid_config", f"cannot read the backlog: {exc}") from exc
        base = core.load_backlog(dest, rc.config.settings)
        base_task = base.by_id.get(task.id)
        in_base = isinstance(base_task, Task)
        unmet = (
            [u.to_dict() for u in core.unmet(base, base_task)]
            if isinstance(base_task, Task)
            else []
        )
        effective_values: JsonDict = {"workflow": None, "writes": [], "test": None}
        if isinstance(base_task, Task):
            workflow = core.effective_workflow(base_task)
            effective_values = {
                "workflow": None if workflow is None else str(workflow),
                "writes": list(effective_task_writes(base_task)),
                "test": " ".join(resolve_test_command(base_task, rc.config.settings)),
            }
    running: JsonDict | None = None
    try:
        store = existing_store(repo)
        if store is not None:
            try:
                row = store.running(task.id)
            finally:
                store.close()
            running = None if row is None else row.to_json()
    except (TaskRunError, sqlite3.Error) as exc:
        if isinstance(exc, TaskRunError) and exc.code == "invalid_config":
            raise
        warnings.append(_runs_hidden(exc))
    if not in_base:
        warnings.append(f"task {task.id} is not committed to {rc.base}")
    data: JsonDict = {
        "task_id": task.id,
        "base": rc.base,
        "config": config,
        "in_base": in_base,
        "unmet": unmet,
        "running": running,
        "launcher_busy": launcher_busy,
        **effective_values,
    }
    return data, warnings


def start_run(
    repo: Path, task_id: str, body: JsonDict, launcher: Launcher
) -> tuple[JsonDict, list[str]]:
    """``factory task run [--note] [--force] [--harness] [--model] [--thinking] [--auto]``
    as a separate process (``launcher.py``). Empty harness/model/thinking mean the roster."""
    _check_keys(body, RUN_KEYS)
    note = _opt_str(body, "note")
    force = _opt_bool(body, "force")
    auto = _opt_bool(body, "auto")
    harness = (_opt_str(body, "harness") or "").strip() or None
    model = (_opt_str(body, "model") or "").strip() or None
    thinking = (_opt_str(body, "thinking") or "").strip() or None
    if harness is not None:
        try:
            canonical(harness)
        except ValueError as exc:
            raise core.TaskEditError("invalid_value", str(exc)) from None
    if thinking is not None and thinking not in THINKING_LEVELS:
        raise core.TaskEditError(
            "invalid_value", f"thinking {thinking!r} is not one of {list(THINKING_LEVELS)}"
        )
    row = launcher.start(
        repo,
        task_id,
        note=note,
        force=force,
        harness=harness,
        model=model,
        thinking=thinking,
        auto=auto,
    )
    data: JsonDict = {
        "task_id": task_id,
        "run": None if row is None else row.to_json(),
        "pending": row is None,
        "force": force,
        "auto": auto,
    }
    return data, []


# ── kanban queue: order and exclusion for auto-continue ──────────────────────


def _queue_store(repo: Path) -> TaskRunStore:
    """The trace DB store of `repo`, created when it does not exist yet."""
    store = existing_store(repo)
    if store is not None:
        return store
    try:
        main = gitops.main_root(repo)
    except TaskRunError:
        main = repo.resolve()
    try:
        local = load_local(main)
    except ConfigError as exc:
        raise TaskRunError("invalid_config", str(exc)) from exc
    return TaskRunStore(local.trace_db_path(main))


def queue_order(repo: Path, body: JsonDict) -> tuple[JsonDict, list[str]]:
    """Save the kanban's order of ready tasks; auto-continue takes them in this order."""
    _check_keys(body, QUEUE_ORDER_KEYS)
    order = body.get("order")
    if not isinstance(order, list) or not all(isinstance(v, str) and v.strip() for v in order):
        raise core.TaskEditError("invalid_value", "'order' must be a list of task ids")
    if len(set(order)) != len(order):
        raise core.TaskEditError("invalid_value", "'order' has a task id twice")
    backlog = core.load_for_edit(repo)
    unknown = [i for i in order if not isinstance(backlog.by_id.get(i), Task)]
    if unknown:
        raise core.TaskEditError("unknown_task", f"unknown task(s): {', '.join(unknown)}")
    store = _queue_store(repo)
    try:
        store.set_queue_order(order)
        saved = list(store.queue_prefs().order)
    finally:
        store.close()
    return {"order": saved}, []


def auto_exclude(repo: Path, task_id: str, body: JsonDict) -> tuple[JsonDict, list[str]]:
    """Exclude a task from auto-continue (``{excluded: true}``) or include it again."""
    _check_keys(body, EXCLUDE_KEYS)
    excluded = body.get("excluded")
    if not isinstance(excluded, bool):
        raise core.TaskEditError("invalid_value", "'excluded' must be true or false")
    backlog = core.load_for_edit(repo)
    if not isinstance(backlog.by_id.get(task_id), Task):
        raise core.TaskEditError("unknown_task", f"unknown task '{task_id}'")
    store = _queue_store(repo)
    try:
        store.set_excluded(task_id, excluded)
    finally:
        store.close()
    return {"task_id": task_id, "excluded": excluded}, []


def _find_container(backlog: Backlog, container_id: str) -> Container:
    for container in core.iter_containers(backlog.containers):
        if container.id == container_id:
            return container
    raise core.TaskEditError(
        "unknown_container",
        f"no {' or '.join(backlog.settings.levels[:-1])} '{container_id}'",
        id=container_id,
    )


def _subtree_tasks(container: Container) -> Iterator[Task]:
    for child in container.children:
        yield from _subtree_tasks(child)
    yield from container.tasks


def _nearest_id(task: Task) -> str | None:
    node: Container | None = task.parent
    while node is not None:
        if node.id is not None:
            return node.id
        node = node.parent
    return None


def _container_info(container: Container) -> JsonDict:
    return {
        "id": container.id,
        "title": container.title,
        "level": container.level,
        "path": container.path,
        "auto_continue": _own_flag(container, "auto_continue"),
        "effective_auto_continue": _effective_flag(container, "auto_continue"),
        "auto_merge": _own_flag(container, "auto_merge"),
        "effective_auto_merge": _effective_flag(container, "auto_merge"),
        "can_toggle": container.index_path is not None,
    }


def container_graph(repo: Path, container_id: str) -> tuple[JsonDict, list[str]]:
    """Tasks of a module or step (nodes, with board states) and their ``depends_on`` (edges)."""
    backlog = core.load_for_edit(repo)
    container = _find_container(backlog, container_id)
    rt, warnings = _runtime(repo)
    tasks = sorted(_subtree_tasks(container), key=lambda t: t.path)
    inside = {t.id for t in tasks}
    nodes: list[JsonDict] = [
        {
            "id": t.id,
            "title": t.title,
            "kind": "task",
            "board_state": board_state(backlog, t, rt),
            "step": _nearest_id(t),
            "external": False,
        }
        for t in tasks
    ]
    edges: list[JsonDict] = []
    external: dict[str, JsonDict] = {}
    for task in tasks:
        for dep in task.depends_on:
            edges.append({"from": dep, "to": task.id})
            if dep in inside or dep in external:
                continue
            ref = _depends_ref(backlog, dep, rt)
            is_task = ref["kind"] == "task"
            node = backlog.by_id.get(dep)
            external[dep] = {
                "id": dep,
                "title": ref["title"],
                "kind": ref["kind"],
                "board_state": ref["state"] if is_task else None,
                "state": ref["state"],
                "step": _nearest_id(node) if isinstance(node, Task) else None,
                "external": True,
            }
    nodes.extend(external[k] for k in sorted(external))
    data: JsonDict = {"container": _container_info(container), "nodes": nodes, "edges": edges}
    return data, warnings


def auto_continue(repo: Path, container_id: str, body: JsonDict) -> tuple[JsonDict, list[str]]:
    """``factory backlog auto-continue ID --on|--off|--inherit`` (writes index.md, no commit)."""
    return _container_flag(repo, container_id, body, "auto_continue", core.set_auto_continue)


def auto_merge(repo: Path, container_id: str, body: JsonDict) -> tuple[JsonDict, list[str]]:
    """``factory backlog auto-merge ID --on|--off|--inherit`` (writes index.md, no commit)."""
    return _container_flag(repo, container_id, body, "auto_merge", core.set_auto_merge)


def _container_flag(
    repo: Path,
    container_id: str,
    body: JsonDict,
    key: str,
    setter: Callable[[Path, str, bool | None], core.ContainerWriteResult],
) -> tuple[JsonDict, list[str]]:
    _check_keys(body, AUTO_KEYS)
    mode = _req_str(body, "mode")
    if mode not in AUTO_MODES:
        raise core.TaskEditError("invalid_value", "'mode' must be on, off or inherit")
    result = setter(repo, container_id, AUTO_MODES[mode])
    container = result.container
    data: JsonDict = {
        "changed": result.changed,
        "id": container.id,
        "level": container.level,
        "path": result.path,
        key: _own_flag(container, key),
        f"effective_{key}": _effective_flag(container, key),
        "issues": [i.to_dict() for i in result.issues],
    }
    return data, _warnings(result.issues)


# ── projects and steps: detail, add, edit (index.md) ─────────────────────────

CONTAINER_ADD_KEYS = ("parent", "id", "title", "body", "backlog_dir")
CONTAINER_EDIT_KEYS = ("title", *core.CONTAINER_KEYS, "clear")


def container_detail(repo: Path, container_id: str) -> tuple[JsonDict, list[str]]:
    """A project or step: title, description, own values and effective values with origin."""
    backlog = core.load_for_edit(repo)
    issues = core.check_backlog(backlog)
    container = core.find_container(backlog, container_id, issues)
    own_issues = [i.to_dict() for i in issues if i.path == container.index_path]
    data: JsonDict = {
        "container": core.container_detail_json(backlog, container),
        "editable_keys": [
            key
            for key in core.CONTAINER_KEYS
            if key not in ("workdir", "harness", "model", "thinking") or container.parent is None
        ],
        "issues": own_issues,
    }
    return data, _warnings(own_issues)


def _container_write_json(result: core.ContainerWriteResult) -> tuple[JsonDict, list[str]]:
    data: JsonDict = {
        "action": result.action,
        "changed": result.changed,
        "path": result.path,
        "container": core.container_detail_json(result.backlog, result.container),
        "issues": [i.to_dict() for i in result.issues],
    }
    return data, _warnings(result.issues)


def add_container(repo: Path, body: JsonDict) -> tuple[JsonDict, list[str]]:
    """``factory backlog add [PARENT] --id --title [--body] [--backlog-dir]``: a new
    project (in backlog root ``backlog_dir``) or step."""
    _check_keys(body, CONTAINER_ADD_KEYS)
    parent = _opt_str(body, "parent")
    container_id = _req_str(body, "id")
    title = _req_str(body, "title")
    text = _opt_str(body, "body") or ""
    backlog_dir = _opt_str(body, "backlog_dir")
    result = core.add_container(
        repo, parent, container_id, title, body=text, backlog_dir=backlog_dir
    )
    return _container_write_json(result)


def edit_container(repo: Path, container_id: str, body: JsonDict) -> tuple[JsonDict, list[str]]:
    """``factory backlog edit ID``: the title, and the keys of ``CONTAINER_KEYS`` set to a
    value or removed (``null``, or listed in ``clear``)."""
    _check_keys(body, CONTAINER_EDIT_KEYS)
    title = _opt_str(body, "title")
    clear = _opt_str_list(body, "clear") or []
    values: dict[str, object] = {}
    for key in core.CONTAINER_KEYS:
        if key not in body:
            continue
        if body[key] is None:
            clear.append(key)
        else:
            values[key] = body[key]
    result = core.edit_container(repo, container_id, title=title, values=values, clear=clear)
    return _container_write_json(result)


def _parameters(body: JsonDict) -> dict[str, object] | None:
    if "parameters" not in body:
        return None
    value = body["parameters"]
    if not isinstance(value, dict):
        raise UsageError("parameters must be an object")
    return {str(k): v for k, v in value.items()}
