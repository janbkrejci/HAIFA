"""``GET /api/overview``: what runs, waits for review and failed in every registered repository.

For each repository of the registry the overview returns ``running`` (runs in the ``running``
state with their running phase, attempt, start and cost so far), ``review`` (open task PRs of
``task_prs`` for tasks without an active run; ``source: trace`` says they come from the trace,
not from the hosting), ``failed`` (tasks whose newest run ended ``failed`` or ``aborted`` and
that are neither ``done`` nor ``cancelled`` in the backlog), ``config`` (whether the factory is
installed, an invalid configuration in base and uncommitted shared configuration, D4),
``last_activity`` and ``warnings``; ``totals`` sums them up.

It only reads. The trace DB is opened with a ``mode=ro`` sqlite connection (``query_only``;
``immutable`` for a WAL DB nobody has open, so no ``-wal``/``-shm`` file appears),
never through ``TaskRunStore``, which creates tables and reaps dead runs: a running row whose
process is gone is shown with ``status_label`` "proces skončil" and stays as it is. A missing
trace DB is not created. Git is read only through the config readers, which run with
``GIT_OPTIONAL_LOCKS=0``; there is no ``git fetch`` and no provider call. The config state is
kept for ``CONFIG_TTL`` seconds and the task titles for ``TASKS_TTL`` seconds per repository.
Repositories are computed concurrently with ``REPO_TIMEOUT`` seconds each; a slow or broken
repository comes back with ``state`` ``timeout`` or ``error`` and a warning, the others as usual.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import quote

from aifactory import database, oscompat
from aifactory.backlog import TaskEditError, iter_tasks, load_for_edit
from aifactory.config import ConfigError
from aifactory.config.loader import load_config
from aifactory.config.source import CommitSource
from aifactory.config.status import config_changes
from aifactory.onboard.state import repo_state
from aifactory.run.gitops import repo_layout
from aifactory.web.registry import Registry, RepoEntry
from aifactory.web.repos import trace_db_of

JsonDict = dict[str, Any]
T = TypeVar("T")

CONFIG_TTL = 15.0  # s, config state per repository
TASKS_TTL = 60.0  # s, task titles and statuses per repository
REPO_TIMEOUT = 2.0  # s, per repository
if sys.platform == "win32":  # a cold repository runs ~8 git processes, each 0.15-0.3 s there
    REPO_TIMEOUT = 10.0
DB_TIMEOUT = 0.5  # s, sqlite busy wait of the read-only connection
CLOSED_STATUSES = frozenset({"done", "cancelled"})
FAILED_STATES = frozenset({"failed", "aborted"})
NOT_INSTALLED = frozenset({"none", "sssf"})
LOADABLE = frozenset({"onboarded", "pre_library"})
PROCESS_ENDED = "proces skončil"
MAX_ISSUES = 20
WORKERS = 8  # threads computing repositories

TaskIndex = dict[str, tuple[str, str]]


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


def _read_trace(conn: sqlite3.Connection) -> _Trace:
    conn.row_factory = sqlite3.Row
    runs: list[sqlite3.Row] = []
    prs: list[sqlite3.Row] = []
    phases: dict[str, JsonDict] = {}
    costs: dict[str, tuple[float, int]] = {}
    if _has_table(conn, "task_runs"):
        runs = conn.execute(
            "SELECT rowid, run_id, task_id, state, started_at, ended_at, pid, workflow, error "
            "FROM task_runs ORDER BY started_at DESC, rowid DESC"
        ).fetchall()
    if _has_table(conn, "task_prs"):
        prs = conn.execute(
            "SELECT branch, task_id, pr_id, url, state, created_at, updated_at FROM task_prs"
        ).fetchall()
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
    return _Trace(runs, prs, phases, costs)


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


def _lists(trace: _Trace, tasks: TaskIndex, now: datetime) -> tuple[JsonDict, str | None]:
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
            }
        )

    open_prs: dict[str, sqlite3.Row] = {}
    for pr in trace.prs:
        if pr["state"] != "open" or pr["task_id"] in active:
            continue
        seen = open_prs.get(pr["task_id"])
        if seen is None or (pr["created_at"] or "") > (seen["created_at"] or ""):
            open_prs[pr["task_id"]] = pr
    review: list[JsonDict] = []
    for pr in sorted(open_prs.values(), key=lambda p: p["created_at"] or "", reverse=True):
        opened = _time(pr["created_at"])
        age = None if opened is None else round(max(0.0, (now - opened).total_seconds()), 1)
        review.append(
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
        hit = tasks.get(row["task_id"])
        if hit is not None and hit[1] in CLOSED_STATUSES:
            continue
        failed.append(
            {
                "run_id": row["run_id"],
                "task_id": row["task_id"],
                "task_title": title(row["task_id"]),
                "state": row["state"],
                "workflow": row["workflow"],
                "ended_at": row["ended_at"],
                "error": row["error"],
            }
        )

    last: tuple[datetime, str] | None = None
    stamps = [v for r in trace.runs for v in (r["started_at"], r["ended_at"])]
    stamps += [p["updated_at"] for p in trace.prs]
    for value in stamps:
        parsed = _time(value)
        if parsed is not None and (last is None or parsed > last[0]):
            last = (parsed, value)
    lists = {"running": running, "review": review, "failed": failed}
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
    if st.commit and st.state in LOADABLE:
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
        "installed": st.state not in NOT_INSTALLED,
        "base": st.base,
        "commit": st.commit,
        "invalid": invalid,
        "issues": issues,
        "uncommitted": uncommitted,
        "clean": not uncommitted,
    }
    return config, warnings


def _task_index(root: Path) -> tuple[TaskIndex, list[str]]:
    try:
        backlog = load_for_edit(root)
    except (ConfigError, TaskEditError, OSError, ValueError) as exc:
        return {}, [f"task titles are not available: {exc}"]
    return {t.id: (t.title, t.status) for t in iter_tasks(backlog)}, []


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
        "failed": [],
        "config": None,
        "last_activity": None,
        "warnings": warnings,
    }


class Overview:
    """Computes the overview of every repository in ``registry``; reads only."""

    def __init__(
        self,
        registry: Registry,
        *,
        timeout: float = REPO_TIMEOUT,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.registry = registry
        self.timeout = timeout
        self._configs = _TtlCache(clock)
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
        config, config_warnings = self._configs.get(key, CONFIG_TTL, lambda: _config_view(root))
        tasks, task_warnings = self._tasks.get(key, TASKS_TTL, lambda: _task_index(root))
        trace, trace_warnings = _trace_view(trace_db_of(root))
        item = _stub(entry, _state(config), [*config_warnings, *task_warnings, *trace_warnings])
        item["config"] = config
        if trace is not None:
            lists, last = _lists(trace, tasks, datetime.now(UTC))
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
            "failed": sum(len(r["failed"]) for r in repos),
            "process_ended": sum(
                1 for r in repos for run in r["running"] if run["process"] == "ended"
            ),
            "with_warnings": sum(1 for r in repos if r["warnings"]),
        }
        return {"repos": repos, "totals": totals}, list(warnings)
