"""``GET /api/overview``: what runs, waits for review and failed in every registered repository.

For each repository of the registry the overview returns ``running`` (runs in the ``running``
state with their running phase, attempt, start and cost so far), ``review`` (open task PRs of
``task_prs`` for tasks without an active run that are neither ``done`` nor ``cancelled`` in the
backlog and that wait for the user; ``source: trace`` says they come from the trace, not from
the hosting), ``automerge`` (the same kind of open PR, but the factory merges it by itself:
the task has an effective ``auto_merge`` and the PR no ``auto_merge_error``,
``web.backlog.waits_for_automerge``),
``merged_outside`` (tasks without an active run whose newest PR is merged, that are neither
``done`` nor ``cancelled`` in the backlog and whose ``## Běhy`` does not have the PR yet: a
merge outside factory that ``factory backlog sync`` would mark done), ``sync_pr`` (the newest
open sync PR ``{url, branch, tasks}`` or ``null``), ``failed`` (tasks whose newest run ended
``failed`` or ``aborted`` and that are neither ``done`` nor ``cancelled`` in the backlog, with
``failure_kind``; a run that ended blocked, kind ``blocked``, is not a failure and is left
out), ``auto_actions`` (the newest ``AUTO_ACTIONS_LIMIT`` automatic actions of
the repository's auto-continue chains after a failure, newest first: ``task_chains.events``,
``run.heal.HealEvent.to_json()`` with the ``chain_id``),
``config`` (whether the factory is installed, an invalid configuration in base and uncommitted
shared configuration, D4),
``last_activity`` and ``warnings``; ``totals`` sums them up. Every item of ``running`` has
``pause`` (``null``, ``pausing`` or ``paused``; ``null`` for a trace DB without the column).

``tasks`` counts the backlog's tasks per kanban board state (``web.backlog.BOARD_STATES``,
every state present, zeros included), computed by ``board_state`` from the trace rows read
here: a task with a running row whose process did not end is ``running``, one with an open PR
``awaiting merge`` when the factory merges it by itself, otherwise ``in review``. ``factory``
is what the Overview's factory controls need (``control.py``):
``max_parallel_runs`` (``.factory/config.yaml`` of the main checkout; ``null`` when invalid),
``running`` (running rows whose process did not end), ``in_review`` (tasks with an open PR
and no such row: waiting for review or for auto-merge, they hold a slot too), ``free_slots``
(``max_parallel_runs`` minus the tasks of ``running`` and ``in_review``, each once,
``run.queue.Slots``), ``ready`` (tasks in
board state ``ready`` not excluded from auto-continue in the kanban, ``task_queue``),
``can_start`` (a ready task, a free slot and a configuration in state ``ok`` or
``uncommitted``: runs read the base commit), ``paused`` and ``pausing`` (running rows by
``pause``) and ``control`` (``FactoryControl.snapshot``: the progress of a stop or pause the
dashboard started, or ``null``). A repository that is missing, not git, slow or broken has
``tasks`` and ``factory`` ``null``.

It only reads. The trace DB is opened with a ``mode=ro`` sqlite connection (``query_only``;
``immutable`` for a WAL DB nobody has open, so no ``-wal``/``-shm`` file appears),
never through ``TaskRunStore``, which creates tables and reaps dead runs: a running row whose
process is gone is shown with ``status_label`` "proces skončil" and stays as it is. A missing
trace DB is not created. Git is read only through the config readers, which run with
``GIT_OPTIONAL_LOCKS=0``; there is no ``git fetch`` and no provider call. The PR states in
``task_prs`` are kept fresh by the dashboard's background refresh (``pr_refresh.py``). The
config state is kept for ``CONFIG_TTL`` seconds and the task titles for ``TASKS_TTL`` seconds
per repository. Repositories are computed concurrently with ``REPO_TIMEOUT`` seconds each; a
slow or broken repository comes back with ``state`` ``timeout`` or ``error`` and a warning, the
others as usual.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import quote

from aifactory import database, failure, oscompat
from aifactory.backlog import Backlog, Task, TaskEditError, iter_tasks, load_for_edit
from aifactory.backlog.taskfile import has_entry
from aifactory.config import ConfigError
from aifactory.config.loader import load_config
from aifactory.config.repo_state import repo_state
from aifactory.config.source import CommitSource
from aifactory.config.status import config_changes
from aifactory.run.gitops import repo_layout
from aifactory.run.queue import Slots
from aifactory.web.backlog import BOARD_STATES, _Runtime, board_state, waits_for_automerge
from aifactory.web.chains import max_parallel_runs_in
from aifactory.web.config_cache import CONFIG_TTL as CONFIG_TTL
from aifactory.web.config_cache import ConfigCache
from aifactory.web.control import FactoryControl
from aifactory.web.registry import Registry, RepoEntry
from aifactory.web.repos import trace_db_of

JsonDict = dict[str, Any]
T = TypeVar("T")

TASKS_TTL = 60.0  # s, task titles and statuses per repository
REPO_TIMEOUT = 2.0  # s, per repository
if sys.platform == "win32":  # a cold repository runs ~8 git processes, each 0.15-0.3 s there
    REPO_TIMEOUT = 10.0
DB_TIMEOUT = 0.5  # s, sqlite busy wait of the read-only connection
CLOSED_STATUSES = frozenset({"done", "cancelled"})
FAILED_STATES = frozenset({"failed", "aborted"})
AUTO_ACTIONS_LIMIT = 5
# the chains whose events the overview reads, newest first
_CHAINS_READ = 20
PROCESS_ENDED = "proces skončil"
MAX_ISSUES = 20
WORKERS = 8  # threads computing repositories

TaskIndex = dict[str, tuple[str, str, str]]  # task id -> (title, status, path)
STARTABLE_STATES = frozenset({"ok", "uncommitted"})


@dataclass
class _Tasks:
    index: TaskIndex
    backlog: Backlog | None


def _time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.astimezone()


def _process(pid: int | None) -> str:
    """``alive``, ``ended`` or ``unknown`` (no pid) for the process of a running row."""
    if pid is None:
        return "unknown"
    if sys.platform == "win32":  # there os.kill(pid, 0) would terminate the process
        return "alive" if pid > 0 and oscompat.alive(pid) else "ended"
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "ended"
    except PermissionError:
        return "alive"
    except (OSError, OverflowError, ValueError):
        return "unknown"
    return "alive"


class _TtlCache:
    """Values per key for ``ttl`` seconds; thread-safe; only stores completed computations."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._items: dict[object, tuple[float, Any]] = {}

    def get(self, key: object, ttl: float, compute: Callable[[], T]) -> T:
        now = self._clock()
        with self._lock:
            hit = self._items.get(key)
            if hit is not None and now - hit[0] < ttl:
                value: T = hit[1]
                return value
        value = compute()
        with self._lock:
            self._items[key] = (now, value)
        return value

    def prune(self, keep: set[object]) -> None:
        with self._lock:
            for key in [k for k in self._items if k not in keep]:
                del self._items[key]


# --- trace DB (read-only) ---------------------------------------------------------------


def _closed_wal(db: Path) -> bool:
    """A WAL-mode DB without a ``-wal`` file: no connection has it open, all of it is in ``db``.

    Opening such a DB with ``mode=ro`` alone would create ``-wal`` and ``-shm`` next to it,
    so it is opened ``immutable`` instead (no lock, no side file). A writer that opens the DB
    while the overview reads can at worst make this read fail, which becomes a warning.
    """
    try:
        with db.open("rb") as handle:
            header = handle.read(20)
    except OSError:
        return False
    wal = header[:16] == b"SQLite format 3\x00" and len(header) == 20 and header[18] == 2
    return wal and not Path(f"{db}-wal").exists()


def _open_ro(db: Path) -> sqlite3.Connection | None:
    """A read-only connection to ``db``, or None when the file does not exist."""
    if not database.available(db):
        return None
    flags = "mode=ro&immutable=1" if _closed_wal(db) else "mode=ro"
    conn = database.connect(
        f"file:{quote(str(db))}?{flags}",
        uri=True,
        timeout=DB_TIMEOUT,
        isolation_level=None,
        check_same_thread=False,
    )
    try:
        conn.execute("PRAGMA query_only = ON")
    except sqlite3.Error:
        conn.close()
        raise
    return conn


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


@dataclass
class _Trace:
    runs: list[sqlite3.Row]
    prs: list[sqlite3.Row]
    phases: dict[str, JsonDict]
    costs: dict[str, tuple[float, int]]
    excluded: frozenset[str] = frozenset()
    sync_prs: list[sqlite3.Row] = field(default_factory=list)
    auto_actions: list[JsonDict] = field(default_factory=list)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _read_trace(conn: sqlite3.Connection) -> _Trace:
    conn.row_factory = sqlite3.Row
    runs: list[sqlite3.Row] = []
    prs: list[sqlite3.Row] = []
    phases: dict[str, JsonDict] = {}
    costs: dict[str, tuple[float, int]] = {}
    excluded: frozenset[str] = frozenset()
    sync_prs: list[sqlite3.Row] = []
    if _has_table(conn, "task_runs"):
        run_columns = _columns(conn, "task_runs")
        pause = "pause" if "pause" in run_columns else "NULL AS pause"
        kind = "failure_kind" if "failure_kind" in run_columns else "NULL AS failure_kind"
        runs = conn.execute(
            "SELECT rowid, run_id, task_id, state, started_at, ended_at, pid, workflow, error, "
            f"{pause}, {kind} FROM task_runs ORDER BY started_at DESC, rowid DESC"
        ).fetchall()
    if _has_table(conn, "task_queue"):
        excluded = frozenset(
            str(row[0]) for row in conn.execute("SELECT task_id FROM task_queue WHERE excluded")
        )
    if _has_table(conn, "task_prs"):
        columns = _columns(conn, "task_prs")
        merged = "merged_at" if "merged_at" in columns else "NULL AS merged_at"
        error = "auto_merge_error" if "auto_merge_error" in columns else "NULL AS auto_merge_error"
        prs = conn.execute(
            "SELECT rowid, branch, task_id, pr_id, url, state, created_at, updated_at, "
            f"{merged}, {error} FROM task_prs"
        ).fetchall()
    if _has_table(conn, "sync_prs"):
        sync_prs = conn.execute(
            "SELECT branch, url, state, tasks, created_at FROM sync_prs "
            "WHERE state = 'open' ORDER BY created_at DESC, rowid DESC"
        ).fetchall()
    auto_actions = _auto_actions(conn)
    running_ids = [r["run_id"] for r in runs if r["state"] == "running"]
    if running_ids and _has_table(conn, "phases"):
        marks = ", ".join("?" for _ in running_ids)
        for row in conn.execute(
            "SELECT adw_id, name, attempt, started_at FROM phases "
            f"WHERE status = 'running' AND adw_id IN ({marks}) ORDER BY seq, rowid",
            running_ids,
        ):
            phases[row["adw_id"]] = {
                "name": row["name"],
                "attempt": row["attempt"],
                "started_at": row["started_at"],
            }
    if running_ids and _has_table(conn, "sessions"):
        marks = ", ".join("?" for _ in running_ids)
        for row in conn.execute(
            f"SELECT adw_id, total_cost, total_tokens FROM sessions WHERE adw_id IN ({marks})",
            running_ids,
        ):
            costs[row["adw_id"]] = (float(row["total_cost"] or 0.0), int(row["total_tokens"] or 0))
    return _Trace(runs, prs, phases, costs, excluded, sync_prs, auto_actions)


def _auto_actions(conn: sqlite3.Connection) -> list[JsonDict]:
    """The newest automatic actions of the chains (``task_chains.events``), newest first."""
    if not _has_table(conn, "task_chains") or "events" not in _columns(conn, "task_chains"):
        return []
    actions: list[JsonDict] = []
    for row in conn.execute(
        f"SELECT chain_id, events FROM task_chains ORDER BY started_at DESC, rowid DESC "
        f"LIMIT {_CHAINS_READ}"
    ):
        try:
            events = json.loads(row["events"] or "[]")
        except ValueError:
            continue
        if not isinstance(events, list):
            continue
        actions += [{**e, "chain_id": row["chain_id"]} for e in events if isinstance(e, dict)]
    actions.sort(key=lambda e: str(e.get("at") or ""), reverse=True)
    return actions[:AUTO_ACTIONS_LIMIT]


def _trace_view(db: Path) -> tuple[_Trace | None, list[str]]:
    """The trace rows the overview needs; None without a trace DB. Never writes."""
    try:
        conn = _open_ro(db)
    except sqlite3.Error as exc:
        return _Trace([], [], {}, {}), [f"trace DB {db} is not readable: {exc}"]
    if conn is None:
        return None, []
    try:
        return _read_trace(conn), []
    except sqlite3.Error as exc:
        return _Trace([], [], {}, {}), [f"trace DB {db} is not readable: {exc}"]
    finally:
        conn.close()


def _closed(tasks: TaskIndex, task_id: str) -> bool:
    hit = tasks.get(task_id)
    return hit is not None and hit[1] in CLOSED_STATUSES


def _merged_outside(
    trace: _Trace, tasks: TaskIndex, active: set[str], root: Path
) -> list[JsonDict]:
    """Tasks whose newest PR is merged but which ``base`` does not have as done yet."""
    newest: dict[str, sqlite3.Row] = {}
    for pr in trace.prs:
        seen = newest.get(pr["task_id"])
        if seen is None or ((pr["created_at"] or ""), pr["rowid"]) > (
            (seen["created_at"] or ""),
            seen["rowid"],
        ):
            newest[pr["task_id"]] = pr
    found: list[JsonDict] = []
    for task_id, pr in newest.items():
        hit = tasks.get(task_id)
        if pr["state"] != "merged" or task_id in active or hit is None:
            continue
        title, status, path = hit
        if status in CLOSED_STATUSES:
            continue
        try:
            text = (root / path).read_text(encoding="utf-8")
        except OSError:
            continue
        if pr["url"] and has_entry(text, pr["url"]):
            continue  # reopened after the merge
        found.append(
            {
                "task_id": task_id,
                "task_title": title,
                "pr_id": pr["pr_id"],
                "url": pr["url"],
                "branch": pr["branch"],
                "merged_at": pr["merged_at"],
            }
        )
    found.sort(key=lambda item: item["merged_at"] or "", reverse=True)
    return found


def _sync_pr(trace: _Trace) -> JsonDict | None:
    """The newest open sync PR, or None."""
    if not trace.sync_prs:
        return None
    row = trace.sync_prs[0]
    try:
        parsed = json.loads(row["tasks"] or "[]")
    except (TypeError, ValueError):
        parsed = []
    ids = [str(t) for t in parsed] if isinstance(parsed, list) else []
    return {"url": row["url"], "branch": row["branch"], "tasks": ids}


def _newest_open_prs(prs: list[sqlite3.Row]) -> dict[str, sqlite3.Row]:
    """The newest open PR of each task (by ``created_at``, then ``rowid``)."""
    newest: dict[str, sqlite3.Row] = {}
    for pr in prs:
        if pr["state"] != "open":
            continue
        seen = newest.get(pr["task_id"])
        key = (pr["created_at"] or "", pr["rowid"] or 0)
        if seen is None or key > (seen["created_at"] or "", seen["rowid"] or 0):
            newest[pr["task_id"]] = pr
    return newest


def _lists(
    trace: _Trace,
    tasks: TaskIndex,
    now: datetime,
    root: Path,
    backlog: Backlog | None = None,
) -> tuple[JsonDict, str | None]:
    def title(task_id: str) -> str | None:
        hit = tasks.get(task_id)
        return hit[0] if hit else None

    running: list[JsonDict] = []
    active: set[str] = set()
    for row in trace.runs:
        if row["state"] != "running":
            continue
        process = _process(row["pid"])
        if process != "ended":
            active.add(row["task_id"])
        cost, tokens = trace.costs.get(row["run_id"], (0.0, 0))
        running.append(
            {
                "run_id": row["run_id"],
                "task_id": row["task_id"],
                "task_title": title(row["task_id"]),
                "workflow": row["workflow"],
                "started_at": row["started_at"],
                "phase": trace.phases.get(row["run_id"]),
                "cost": round(cost, 6),
                "tokens": tokens,
                "process": process,
                "status_label": PROCESS_ENDED if process == "ended" else None,
                "pause": row["pause"],
            }
        )

    open_prs = [
        pr
        for pr in _newest_open_prs(trace.prs).values()
        if pr["task_id"] not in active and not _closed(tasks, pr["task_id"])
    ]
    review: list[JsonDict] = []
    automerge: list[JsonDict] = []
    for pr in sorted(open_prs, key=lambda p: p["created_at"] or "", reverse=True):
        opened = _time(pr["created_at"])
        age = None if opened is None else round(max(0.0, (now - opened).total_seconds()), 1)
        task = backlog.by_id.get(pr["task_id"]) if backlog is not None else None
        merges = waits_for_automerge(
            task if isinstance(task, Task) else None, pr["auto_merge_error"]
        )
        (automerge if merges else review).append(
            {
                "task_id": pr["task_id"],
                "task_title": title(pr["task_id"]),
                "pr_id": pr["pr_id"],
                "url": pr["url"],
                "branch": pr["branch"],
                "opened_at": pr["created_at"],
                "age_s": age,
                "source": "trace",
            }
        )

    failed: list[JsonDict] = []
    newest: set[str] = set()
    for row in trace.runs:  # newest first
        if row["task_id"] in newest:
            continue
        newest.add(row["task_id"])
        if row["state"] not in FAILED_STATES:
            continue
        if _closed(tasks, row["task_id"]):
            continue
        # the typed kind (``aifactory.failure``); a run recorded before it: other or blocked
        kind = failure.shown_kind(row["failure_kind"], row["error"])
        if kind == failure.BLOCKED:
            continue  # waits for its blockers: not a failure
        failed.append(
            {
                "run_id": row["run_id"],
                "task_id": row["task_id"],
                "task_title": title(row["task_id"]),
                "state": row["state"],
                "workflow": row["workflow"],
                "ended_at": row["ended_at"],
                "error": row["error"],
                "failure_kind": kind,
            }
        )

    last: tuple[datetime, str] | None = None
    stamps = [v for r in trace.runs for v in (r["started_at"], r["ended_at"])]
    stamps += [p["updated_at"] for p in trace.prs]
    for value in stamps:
        parsed = _time(value)
        if parsed is not None and (last is None or parsed > last[0]):
            last = (parsed, value)
    lists = {
        "running": running,
        "review": review,
        "automerge": automerge,
        "failed": failed,
        "auto_actions": [
            {**action, "task_title": title(str(action.get("task_id") or ""))}
            for action in trace.auto_actions
        ],
        "merged_outside": _merged_outside(trace, tasks, active, root),
        "sync_pr": _sync_pr(trace),
    }
    return lists, (last[1] if last else None)


# --- config and backlog -----------------------------------------------------------------


def _config_view(root: Path) -> tuple[JsonDict | None, list[str]]:
    """The config state of ``root``: installed, invalid in base, uncommitted (D4)."""
    try:
        st = repo_state(root)
    except ConfigError as exc:
        return None, [f"the configuration state is not available: {exc}"]
    warnings: list[str] = []
    invalid = False
    issues: list[str] = []
    if st.commit and st.config_in_base:
        try:
            load_config(CommitSource(root, st.base, st.commit))
        except ConfigError as exc:
            invalid = True
            issues = [f"{i.path}: {i.message}" for i in exc.issues][:MAX_ISSUES] or [str(exc)]
    uncommitted: list[JsonDict] = []
    if st.commit:
        try:
            uncommitted = [c.to_dict() for c in config_changes(root, st.commit)]
        except ConfigError as exc:
            warnings.append(f"uncommitted configuration is not known: {exc}")
    config = {
        "factory_state": st.state,
        "installed": st.config_in_base or st.state == "uncommitted",
        "base": st.base,
        "commit": st.commit,
        "invalid": invalid,
        "issues": issues,
        "uncommitted": uncommitted,
        "clean": not uncommitted,
    }
    return config, warnings


def _task_index(root: Path) -> tuple[_Tasks, list[str]]:
    try:
        backlog = load_for_edit(root)
    except (ConfigError, TaskEditError, OSError, ValueError) as exc:
        return _Tasks({}, None), [f"task titles are not available: {exc}"]
    index = {t.id: (t.title, t.status, t.path) for t in iter_tasks(backlog)}
    return _Tasks(index, backlog), []


def _active_runs(trace: _Trace | None) -> list[sqlite3.Row]:
    """Running rows whose process did not end (newest first)."""
    if trace is None:
        return []
    return [r for r in trace.runs if r["state"] == "running" and _process(r["pid"]) != "ended"]


def _task_summary(
    backlog: Backlog, trace: _Trace | None, active: list[sqlite3.Row]
) -> tuple[JsonDict, list[str]]:
    """The number of tasks per kanban board state (every state present) and the ready ids."""
    rt = _Runtime()
    if trace is not None:
        rt.running = {r["task_id"] for r in active}
        newest = _newest_open_prs(trace.prs)
        rt.in_review = set(newest)
        rt.merge_blocked = {t for t, p in newest.items() if p["auto_merge_error"]}
    counts: JsonDict = dict.fromkeys(BOARD_STATES, 0)
    ready: list[str] = []
    for task in iter_tasks(backlog):
        state = board_state(backlog, task, rt)
        counts[state] += 1
        if state == "ready":
            ready.append(task.id)
    return counts, ready


def _factory(
    root: Path,
    state: str,
    ready_ids: list[str],
    trace: _Trace | None,
    active: list[sqlite3.Row],
    control: FactoryControl | None,
) -> JsonDict:
    limit = max_parallel_runs_in(root)
    excluded = trace.excluded if trace is not None else frozenset()
    ready = sum(1 for t in ready_ids if t not in excluded)
    prs = trace.prs if trace is not None else []
    slots = Slots.count(
        (r["task_id"] for r in active), (p["task_id"] for p in prs if p["state"] == "open")
    )
    free = slots.free(limit) if limit is not None else 0
    pauses = [r["pause"] for r in active]
    snapshot = (
        control.snapshot(root, [r["run_id"] for r in active]) if control is not None else None
    )
    return {
        "max_parallel_runs": limit,
        "running": len(active),
        "in_review": len(slots.in_review),
        "free_slots": free,
        "ready": ready,
        "can_start": ready > 0 and free > 0 and state in STARTABLE_STATES,
        "paused": pauses.count("paused"),
        "pausing": pauses.count("pausing"),
        "control": snapshot,
    }


def _state(config: JsonDict | None) -> str:
    if config is None:
        return "error"
    if not config["installed"]:
        return "not_installed"
    if config["invalid"]:
        return "invalid_config"
    if config["factory_state"] == "working_tree" or config["uncommitted"]:
        return "uncommitted"
    return "ok"


def _stub(entry: RepoEntry, state: str, warnings: list[str]) -> JsonDict:
    return {
        "id": entry.id,
        "name": entry.name,
        "path": entry.path,
        "state": state,
        "has_trace": False,
        "running": [],
        "review": [],
        "automerge": [],
        "failed": [],
        "auto_actions": [],
        "merged_outside": [],
        "sync_pr": None,
        "config": None,
        "last_activity": None,
        "warnings": warnings,
        "tasks": None,
        "factory": None,
    }


class Overview:
    """Computes the overview of every repository in ``registry``; reads only."""

    def __init__(
        self,
        registry: Registry,
        *,
        timeout: float = REPO_TIMEOUT,
        clock: Callable[[], float] = time.monotonic,
        control: FactoryControl | None = None,
    ) -> None:
        self.registry = registry
        self.control = control
        self.timeout = timeout
        self._configs = ConfigCache(clock)
        self._tasks = _TtlCache(clock)
        # Own threads: a repository stuck past the limit never blocks the loop's executor, and
        # while its computation still runs a new request waits for it instead of adding a thread.
        self._pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="overview")
        self._inflight: dict[tuple[str, str], Future[JsonDict]] = {}
        self._inflight_lock = threading.Lock()

    def repo(self, entry: RepoEntry) -> JsonDict:
        """One repository item (synchronous; the caller runs it in a thread)."""
        path = Path(entry.path)
        if not path.is_dir():
            return _stub(entry, "missing", [f"the folder {entry.path} is missing"])
        layout = repo_layout(path)
        if layout is None or layout.toplevel is None:
            return _stub(entry, "not_git", [f"{entry.path} is not a git working tree"])
        root = layout.toplevel
        key = (entry.id, entry.path)
        config, config_warnings = self._configs.get(key, root, lambda: _config_view(root))
        tasks, task_warnings = self._tasks.get(key, TASKS_TTL, lambda: _task_index(root))
        trace, trace_warnings = _trace_view(trace_db_of(root))
        item = _stub(entry, _state(config), [*config_warnings, *task_warnings, *trace_warnings])
        item["config"] = config
        active = _active_runs(trace)
        summary, ready = (
            (None, []) if tasks.backlog is None else _task_summary(tasks.backlog, trace, active)
        )
        item["tasks"] = summary
        item["factory"] = _factory(root, item["state"], ready, trace, active, self.control)
        if trace is not None:
            lists, last = _lists(trace, tasks.index, datetime.now(UTC), root, tasks.backlog)
            item.update(lists)
            item["has_trace"] = True
            item["last_activity"] = last
        return item

    async def _bounded(self, entry: RepoEntry) -> JsonDict:
        key = (entry.id, entry.path)
        with self._inflight_lock:
            future = self._inflight.get(key)
            if future is None or future.done():
                future = self._pool.submit(self.repo, entry)
                self._inflight[key] = future
        try:
            return await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), self.timeout)
        except TimeoutError:
            warning = f"repository {entry.id} did not answer within {self.timeout:g} s"
            return _stub(entry, "timeout", [warning])
        except Exception as exc:  # one broken repository never fails the response
            return _stub(entry, "error", [f"{type(exc).__name__}: {exc}"])

    async def collect(self) -> tuple[JsonDict, list[str]]:
        """``({repos, totals}, registry warnings)`` for every registered repository."""
        state, warnings = await asyncio.to_thread(self.registry.snapshot)
        keep: set[object] = {(e.id, e.path) for e in state.repos}
        self._configs.prune(keep)
        self._tasks.prune(keep)
        with self._inflight_lock:
            for key in [k for k in self._inflight if k not in keep]:
                del self._inflight[key]
        repos = list(await asyncio.gather(*(self._bounded(e) for e in state.repos)))
        totals = {
            "repos": len(repos),
            "running": sum(len(r["running"]) for r in repos),
            "review": sum(len(r["review"]) for r in repos),
            "automerge": sum(len(r["automerge"]) for r in repos),
            "failed": sum(len(r["failed"]) for r in repos),
            "merged_outside": sum(len(r["merged_outside"]) for r in repos),
            "process_ended": sum(
                1 for r in repos for run in r["running"] if run["process"] == "ended"
            ),
            "with_warnings": sum(1 for r in repos if r["warnings"]),
        }
        return {"repos": repos, "totals": totals}, list(warnings)
