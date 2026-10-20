"""The ``task_runs``, ``task_prs``, ``sync_prs`` and ``task_chains`` tables in the trace DB.

``task_operations`` records a task, action, process and start time before claim or
while publishing again. Launchers remove completed operations; ``live_operations``
reaps dead local processes. Operations are display evidence, not run claims or slots.

``task_runs`` has one row per run and is the lock between runs; ``task_prs`` has
one row per branch with a pull request (``open``, ``merged`` or ``closed``);
``sync_prs`` has one row per ``backlog sync`` pull request (it belongs to no task).
``task_prs.merged_by`` says who merged the PR (``auto-merge`` or ``operator``);
``task_prs.auto_merge_error`` why auto-merge left the PR open. ``task_runs.started_by``
says who started a run: ``manual`` (``factory task run|return|resolve``, the dashboard),
``auto-continue`` (a chain), ``auto-resolve`` (auto-merge resolving a conflict) or
``auto-ci-fix`` (approve repairing the PR's red CI checks); NULL for runs recorded before.
``task_runs.library_commit`` is the library commit the run read its inherited agents,
workflows and skills from (NULL: the seed, or recorded before). Older trace DBs get these
columns added when the store opens them, and ``task_runs.archived`` too.

``task_runs.failure_kind`` is the typed kind of a run that did not succeed (one of
``aifactory.failure.FAILURE_KINDS``) and ``task_runs.failure_detail`` its facts as a JSON
object; ``error`` stays the free text. ``finish`` records them, ``mark_stopped`` sets
``stopped``, the reaping of a dead run ``process_gone``, ``reclaim`` clears them. A
failed, stopped or aborted run recorded before the columns existed reads as ``other``,
or ``blocked`` when its error starts with ``blocked: `` (``TaskRunRow.shown_failure_kind``).

``task_chains`` has one row per auto-continue chain (``queue.run_chain``): its runs
in start order, the tasks the last selection skipped and why, the tasks that ran
alone (wide writes), its automatic actions after a failure (``events``, ``run.heal``),
and the chain's state (``running``, ``finished`` with its
``stop``, or ``aborted`` when the chain's process is gone). ``dismiss_chain`` erases an
ended chain (its runs stay).

``task_queue`` holds the operator's queue preferences from the kanban: the order of
ready tasks auto-continue takes them in (``rank``, NULL without a manual order) and
the tasks auto-continue never starts (``excluded``). They are operating preferences,
not task content, so they live here and need no backlog commit (``queue_prefs``,
``set_queue_order``, ``set_excluded``).

``task_priority`` holds the tasks that ended blocked during a run and their blockers
(``failure_kind`` ``blocked``, including existing tasks from ``blocked_by``): ``finish`` of a
blocked run writes the row, ``finish`` of a succeeded run of the task deletes it, and so
does ``clear_priority`` (the operator in the kanban). The selection puts these tasks and
their blockers before the kanban's queue (``queue.priority_order``); a task no longer
``todo`` (done, cancelled) has no priority any more (``prune_priority``). ``queue_prefs``
returns the rows with the queue preferences.

``harness_quota`` holds the harnesses that ran out of quota on this computer and when they
may have it again (``retry_at``); ``project_harness`` the harness of a project's quota chain
(``quota_switch``) the project's runs are on now (``run/quota_chain.py``). Both are machine
state, like the queue preferences, and need no backlog commit.

``task_runs.retries`` is a JSON list, one item per retry of the run (``factory task retry``,
``run.retry``): when it started, the phase it continued from, the operator's note and the
base it was rebased onto. A retry is another attempt of the same run: ``reclaim`` turns the
failed, stopped or aborted row back into ``running`` under the same ``run_id`` (the same
task lock as ``claim``), so its phases, tokens and costs add up in the same trace session.

``task_runs.archived`` (0 or 1) hides a finished run from the dashboard's list of
active runs (``archive``, ``archive_finished``, ``unarchive``). ``delete_run`` and
``delete_archived`` erase archived runs: the ``task_runs`` row and the run's rows in
the engine's trace tables, in one transaction. A running run is never archived.

``claim`` inserts the ``running`` row in a ``BEGIN IMMEDIATE`` transaction, so a
second start of the same task fails with ``already_running`` even when two
processes race. A ``running`` row whose process is gone becomes ``aborted``.
``mark_stopped`` sets ``stopped`` (``factory task stop``, the dashboard); a
stopped run stays stopped: ``finish`` of the dying process does not overwrite it.
``task_runs.pause`` is the pause of a running run (``factory task pause|resume``):
NULL, ``pausing`` (asked for; the current phase still runs) or ``paused`` (the run's
process waits before its next phase). The state stays ``running`` meanwhile, so a paused
run keeps its task lock, its place among the parallel runs and its chain waiting.
``request_pause``, ``request_resume``, ``enter_pause`` and ``pause_of`` manage it;
``finish``, ``mark_stopped`` and the reaping of a dead run clear it.
``serialized`` is a lock file next to the trace DB (``trace.db.lock``, ``flock``)
held around the few steps that touch the shared ``.git`` of the main checkout;
``claim`` takes it too, so no run starts inside such a block. It is not the DB
write lock: no write transaction is open while git (or anything slow) runs, so
other runs and the dashboard can write meanwhile.

Every connection waits up to ``BUSY_TIMEOUT`` seconds for a busy DB (SQLite's
busy handler retries until then) instead of failing at once; when the wait runs
out the error is ``sqlite3.OperationalError`` "database is locked", which the
dashboard shows as ``trace_db_locked`` with a plain message (see ``is_db_busy``).

The store switches the trace DB to WAL before the engine's Tracer opens it: the
Tracer asks for WAL before it sets ``busy_timeout`` and would fail at once on a
fresh DB while another run holds the write lock.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import sqlite3
import threading
import time
from collections.abc import Collection, Iterator, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aifactory import database, failure, oscompat
from aifactory.engine.tracer import BUSY_TIMEOUT
from aifactory.engine.utils import now_iso
from aifactory.providers.base import PullRequest
from aifactory.run.errors import TaskRunError

RUNNING, SUCCEEDED, FAILED, ABORTED = "running", "succeeded", "failed", "aborted"
STOPPED = "stopped"
# the states a run can be retried from (``factory task retry``)
RETRYABLE = (FAILED, STOPPED, ABORTED)
# ``task_runs.pause`` of a running run; PAUSED is also the state a paused run is shown in
PAUSING, PAUSED = "pausing", "paused"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS task_operations (
  operation_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  action TEXT NOT NULL,
  pid INTEGER NOT NULL,
  started_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_runs (
  run_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  branch TEXT NOT NULL,
  worktree TEXT NOT NULL,
  base TEXT NOT NULL,
  base_sha TEXT NOT NULL,
  head_sha TEXT,
  state TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  pid INTEGER,
  workflow TEXT,
  note TEXT,
  error TEXT,
  archived INTEGER NOT NULL DEFAULT 0,
  started_by TEXT,
  pause TEXT,
  pr_error TEXT,
  library_commit TEXT,
  pr_body TEXT,
  retries TEXT,
  stacked_on TEXT,
  failure_kind TEXT,
  failure_detail TEXT
);
CREATE INDEX IF NOT EXISTS task_runs_task ON task_runs(task_id);
CREATE TABLE IF NOT EXISTS task_prs (
  branch TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  pr_id TEXT NOT NULL,
  url TEXT NOT NULL,
  base TEXT NOT NULL,
  base_sha TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  state TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  merged_at TEXT,
  merge_sha TEXT,
  merged_by TEXT,
  auto_merge_error TEXT,
  approved_at TEXT
);
CREATE INDEX IF NOT EXISTS task_prs_task ON task_prs(task_id);
CREATE TABLE IF NOT EXISTS sync_prs (
  branch TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  pr_id TEXT NOT NULL,
  url TEXT NOT NULL,
  base TEXT NOT NULL,
  base_sha TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  state TEXT NOT NULL,
  tasks TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  merged_at TEXT,
  merge_sha TEXT
);
CREATE TABLE IF NOT EXISTS task_chains (
  chain_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  pid INTEGER,
  max_parallel INTEGER NOT NULL,
  state TEXT NOT NULL,
  stop TEXT,
  started_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  ended_at TEXT,
  run_ids TEXT NOT NULL DEFAULT '[]',
  skipped TEXT NOT NULL DEFAULT '[]',
  exclusive TEXT NOT NULL DEFAULT '[]',
  events TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS task_queue (
  task_id TEXT PRIMARY KEY,
  rank INTEGER,
  excluded INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS task_priority (
  task_id TEXT PRIMARY KEY,
  blockers TEXT NOT NULL DEFAULT '[]',
  run_id TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS harness_quota (
  harness TEXT PRIMARY KEY,
  exhausted_at TEXT NOT NULL,
  retry_at TEXT NOT NULL,
  message TEXT
);
CREATE TABLE IF NOT EXISTS project_harness (
  project_id TEXT PRIMARY KEY,
  harness TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""
_PR_COLUMNS = (
    "branch",
    "task_id",
    "provider",
    "pr_id",
    "url",
    "base",
    "base_sha",
    "title",
    "body",
    "state",
    "created_at",
    "updated_at",
    "merged_at",
    "merge_sha",
    "merged_by",
    "auto_merge_error",
    "approved_at",
)
# columns added to task_prs after its first release; older DBs get them on open
_PR_ADDED_COLUMNS = {"merged_by": "TEXT", "auto_merge_error": "TEXT", "approved_at": "TEXT"}
MERGED_BY_AUTO = "auto-merge"
MERGED_BY_OPERATOR = "operator"
_SYNC_COLUMNS = (
    "branch",
    "provider",
    "pr_id",
    "url",
    "base",
    "base_sha",
    "title",
    "body",
    "state",
    "tasks",
    "created_at",
    "updated_at",
    "merged_at",
    "merge_sha",
)
_CHAIN_COLUMNS = (
    "chain_id",
    "task_id",
    "pid",
    "max_parallel",
    "state",
    "stop",
    "started_at",
    "updated_at",
    "ended_at",
    "run_ids",
    "skipped",
    "exclusive",
    "events",
)
# columns added to task_chains after its first release; older DBs get them on open
_CHAIN_ADDED_COLUMNS = {"events": "TEXT NOT NULL DEFAULT '[]'"}
CHAIN_FINISHED = "finished"
# the stop of a chain whose finished task has auto-continue off (``queue.STOP_DISABLED``)
_CHAIN_DISABLED = "disabled"
_COLUMNS = (
    "run_id",
    "task_id",
    "branch",
    "worktree",
    "base",
    "base_sha",
    "head_sha",
    "state",
    "started_at",
    "ended_at",
    "pid",
    "workflow",
    "note",
    "error",
    "archived",
    "started_by",
    "pause",
    "pr_error",
    "library_commit",
    "retries",
    "stacked_on",
    "failure_kind",
    "failure_detail",
    "harness_start",
)
# columns added to task_runs after its first release; older DBs get them on open
# (``pr_body``: the PR body a succeeded run could not send; not part of ``TaskRunRow``)
_RUN_ADDED_COLUMNS = {
    "archived": "INTEGER NOT NULL DEFAULT 0",
    "started_by": "TEXT",
    "pause": "TEXT",
    "pr_error": "TEXT",
    "pr_body": "TEXT",
    "library_commit": "TEXT",
    "retries": "TEXT",
    "stacked_on": "TEXT",
    "failure_kind": "TEXT",
    "failure_detail": "TEXT",
    "harness_start": "TEXT",
}
# who started a run (``task_runs.started_by``)
STARTED_MANUAL, STARTED_AUTO_CONTINUE, STARTED_AUTO_RESOLVE = (
    "manual",
    "auto-continue",
    "auto-resolve",
)
STARTED_AUTO_CI_FIX = "auto-ci-fix"
# the engine's trace tables with rows of a run (``adw_id``), children first
_TRACE_TABLES = (
    "events",
    "envelopes",
    "gate_results",
    "processes",
    "agent_sessions",
    "phases",
    "sessions",
)


@dataclass
class TaskRunRow:
    run_id: str
    task_id: str
    branch: str
    worktree: str
    base: str
    base_sha: str
    head_sha: str | None
    state: str
    started_at: str
    ended_at: str | None = None
    pid: int | None = None
    workflow: str | None = None
    note: str | None = None
    error: str | None = None
    archived: int = 0  # 1 = hidden from the list of active runs
    started_by: str | None = None  # manual, auto-continue, auto-resolve, auto-ci-fix; None: none
    pause: str | None = None  # of a running run: None, PAUSING or PAUSED
    pr_error: str | None = None  # why a succeeded run has no PR (push or hosting failed)
    library_commit: str | None = None  # the library commit the run read; None: the seed
    retries: str | None = None  # JSON list of the run's retries (``retry_list``); None: none
    # the branch of the dependency's open PR the run forked from (``stacked_prs``); None: base
    stacked_on: str | None = None
    # of a run that did not succeed: one of ``failure.FAILURE_KINDS``; None: older run
    failure_kind: str | None = None
    failure_detail: str | None = None  # JSON object with the failure's facts
    # JSON object: the harness switch at the start of a run (``run/quota_chain.py``); None: none
    harness_start: str | None = None

    def retry_list(self) -> list[dict[str, Any]]:
        """One item per retry, oldest first (see the module docstring)."""
        return [r for r in _json_list(self.retries) if isinstance(r, dict)]

    @property
    def attempt(self) -> int:
        """1 for the first attempt, +1 for every retry."""
        return 1 + len(self.retry_list())

    @property
    def shown_state(self) -> str:
        """The state to show: ``paused`` for a running run that waits, else ``state``."""
        return PAUSED if self.state == RUNNING and self.pause == PAUSED else self.state

    @property
    def shown_failure_kind(self) -> str | None:
        """The failure kind; for an ended unsuccessful run recorded without one ``other``
        (``blocked`` when its error says so, ``failure.shown_kind``)."""
        if self.state in (RUNNING, SUCCEEDED):
            return None
        return failure.shown_kind(self.failure_kind, self.error)

    def failure_detail_dict(self) -> dict[str, Any] | None:
        """The failure's facts; ``{}`` when the run has none, None when it did not fail."""
        if self.shown_failure_kind is None:
            return None
        try:
            loaded = json.loads(self.failure_detail or "{}")
        except ValueError:
            loaded = {}
        detail: dict[str, Any] = loaded if isinstance(loaded, dict) else {}
        if self.shown_failure_kind == failure.BLOCKED and "blockers" not in detail:
            # a run recorded before the kind: the blockers are in its error
            detail["blockers"] = failure.error_blockers(self.error) or []
        return detail

    def harness_start_dict(self) -> dict[str, Any] | None:
        """The switch the run started with (the project's quota chain); None without one."""
        try:
            loaded = json.loads(self.harness_start or "null")
        except ValueError:
            return None
        return loaded if isinstance(loaded, dict) else None

    def to_json(self) -> dict[str, object]:
        data: dict[str, object] = dict(asdict(self))
        data["retries"] = self.retry_list()
        data["attempt"] = self.attempt
        data["failure_kind"] = self.shown_failure_kind
        data["failure_detail"] = self.failure_detail_dict()
        return data


@dataclass
class TaskPrRow:
    """The factory's record of a task's pull request (``state``: open, merged, closed)."""

    branch: str
    task_id: str
    provider: str
    pr_id: str
    url: str
    base: str
    base_sha: str
    title: str
    body: str
    state: str
    created_at: str
    updated_at: str
    merged_at: str | None = None
    merge_sha: str | None = None
    merged_by: str | None = None  # MERGED_BY_AUTO | MERGED_BY_OPERATOR once merged
    auto_merge_error: str | None = None  # why auto-merge left the PR open
    approved_at: str | None = None  # operator approval waiting for CI and merge

    def to_json(self) -> dict[str, object]:
        return dict(asdict(self))

    def request(self) -> PullRequest:
        return PullRequest(self.pr_id, self.url, self.branch, self.base, self.title)


@dataclass
class SyncPrRow:
    """A ``backlog sync`` pull request; ``tasks`` is a JSON list of the task ids it marks done."""

    branch: str
    provider: str
    pr_id: str
    url: str
    base: str
    base_sha: str
    title: str
    body: str
    state: str
    tasks: str
    created_at: str
    updated_at: str
    merged_at: str | None = None
    merge_sha: str | None = None

    def task_ids(self) -> list[str]:
        loaded = json.loads(self.tasks or "[]")
        return [str(t) for t in loaded] if isinstance(loaded, list) else []

    def to_json(self) -> dict[str, object]:
        data: dict[str, object] = dict(asdict(self))
        data["tasks"] = self.task_ids()
        return data

    def request(self) -> PullRequest:
        return PullRequest(self.pr_id, self.url, self.branch, self.base, self.title)


@dataclass
class TaskChainRow:
    """One auto-continue chain (``state``: running, finished, aborted).

    ``run_ids`` (in start order), ``skipped`` (``Skip.to_json()`` of the last selection),
    ``exclusive`` (task ids that ran alone: wide writes) and ``events`` (the chain's
    automatic actions after a failure, ``heal.HealEvent.to_json()``) are JSON lists.
    """

    chain_id: str
    task_id: str
    pid: int | None
    max_parallel: int
    state: str
    started_at: str
    updated_at: str
    stop: str | None = None
    ended_at: str | None = None
    run_ids: str = "[]"
    skipped: str = "[]"
    exclusive: str = "[]"
    events: str = "[]"

    def run_id_list(self) -> list[str]:
        return [str(r) for r in _json_list(self.run_ids)]

    def skipped_list(self) -> list[dict[str, Any]]:
        return [s for s in _json_list(self.skipped) if isinstance(s, dict)]

    def exclusive_list(self) -> list[str]:
        return [str(t) for t in _json_list(self.exclusive)]

    def event_list(self) -> list[dict[str, Any]]:
        return [e for e in _json_list(self.events) if isinstance(e, dict)]

    def to_json(self) -> dict[str, object]:
        data: dict[str, object] = dict(asdict(self))
        data["run_ids"] = self.run_id_list()
        data["skipped"] = self.skipped_list()
        data["exclusive"] = self.exclusive_list()
        data["events"] = self.event_list()
        return data


def _json_list(text: str | None) -> list[Any]:
    try:
        loaded = json.loads(text or "[]")
    except ValueError:
        return []
    return loaded if isinstance(loaded, list) else []


def _detail_json(detail: dict[str, Any]) -> str:
    """A failure detail as stored in ``task_runs.failure_detail``."""
    return json.dumps(detail, ensure_ascii=False, default=str)


def _now() -> str:
    return str(now_iso())


def _marks(values: list[str]) -> str:
    return ", ".join("?" for _ in values)


def _alive(pid: int | None) -> bool:
    if pid is None:
        return True  # unknown owner: never assume it is gone
    return oscompat.alive(pid)


_WAL_ATTEMPTS = 50  # x 0.1 s, on top of busy_timeout
SERIAL_TIMEOUT = 60.0  # seconds to wait for the lock file of ``serialized``


def is_db_busy(exc: BaseException) -> bool:
    """True for SQLite's "database is locked/busy" and for a lock wait that ran out."""
    if isinstance(exc, TaskRunError):
        return exc.code == "trace_db_locked"
    if isinstance(exc, sqlite3.OperationalError):
        text = str(exc).lower()
        return "locked" in text or "busy" in text
    return False


class _PathLock:
    """A cross-process ``flock`` on one file, re-entrant within the process."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.local = threading.RLock()
        self.depth = 0
        self.fd: int | None = None

    @contextlib.contextmanager
    def hold(self, timeout: float) -> Iterator[None]:
        deadline = time.monotonic() + timeout
        if not self.local.acquire(timeout=timeout):
            raise TaskRunError("trace_db_locked", f"{self.path} is held by another thread")
        try:
            if self.depth == 0:
                self.fd = self._lock(deadline)
            self.depth += 1
            try:
                yield
            finally:
                self.depth -= 1
                if self.depth == 0 and self.fd is not None:
                    with contextlib.suppress(OSError):
                        oscompat.unlock(self.fd)
                    os.close(self.fd)
                    self.fd = None
        finally:
            self.local.release()

    def _lock(self, deadline: float) -> int:
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        while True:
            try:
                oscompat.lock(fd, blocking=False)
                return fd
            except OSError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise TaskRunError(
                        "trace_db_locked", f"{self.path} is held by another process"
                    ) from None
                time.sleep(0.05)


_PATH_LOCKS: dict[str, _PathLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _path_lock(path: Path) -> _PathLock:
    key = str(path.resolve())
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = _PATH_LOCKS[key] = _PathLock(path)
        return lock


def _ensure_wal(conn: sqlite3.Connection, db_path: Path) -> None:
    """Switch the trace DB to WAL, with a busy timeout and retries (see the module docstring)."""
    for _ in range(_WAL_ATTEMPTS):
        try:
            mode = conn.execute("PRAGMA journal_mode=WAL;").fetchone()
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) and "busy" not in str(exc):
                raise
        else:
            if mode is not None and str(mode[0]).lower() == "wal":
                return
        time.sleep(0.1)
    raise TaskRunError("trace_db_locked", f"cannot switch {db_path} to WAL")


def already_running(row: TaskRunRow) -> TaskRunError:
    return TaskRunError(
        "already_running",
        f"task {row.task_id} is already running: run {row.run_id} (pid {row.pid}) "
        f"since {row.started_at} on {row.branch}",
    )


def _add_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    """Add `columns` missing in `table` (a trace DB created by an older version)."""
    present = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, kind in columns.items():
        if name in present:
            continue
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
        except sqlite3.OperationalError as exc:  # another process added it meanwhile
            if "duplicate column" not in str(exc).lower():
                raise


@dataclass(frozen=True)
class Priority:
    """A task that ended blocked during a run, with the blockers it waits for."""

    task_id: str
    blockers: tuple[str, ...] = ()
    run_id: str | None = None
    created_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "blockers": list(self.blockers),
            "run_id": self.run_id,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class QueuePrefs:
    """Kanban preferences for auto-continue: manual order and excluded tasks.

    ``priority``: the blocked tasks with their blockers (``task_priority``), oldest first.
    """

    order: tuple[str, ...] = ()
    excluded: frozenset[str] = frozenset()
    priority: tuple[Priority, ...] = ()


class TaskRunStore:
    """The ``task_runs`` table in the trace DB, on its own sqlite connection."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.conn = database.connect(str(db_path), isolation_level=None, timeout=BUSY_TIMEOUT)
        self.conn.execute(f"PRAGMA busy_timeout={int(BUSY_TIMEOUT * 1000)};")
        _ensure_wal(self.conn, db_path)
        self.conn.executescript(_SCHEMA)
        _add_columns(self.conn, "task_prs", _PR_ADDED_COLUMNS)
        _add_columns(self.conn, "task_runs", _RUN_ADDED_COLUMNS)
        _add_columns(self.conn, "task_chains", _CHAIN_ADDED_COLUMNS)
        if database.is_remote(db_path):
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS haifa_owners "
                "(id TEXT PRIMARY KEY, machine TEXT NOT NULL)"
            )

    def owned_here(self, id: str) -> bool:
        if not database.is_remote(self.db_path):
            return True
        owner = self.conn.execute("SELECT machine FROM haifa_owners WHERE id = ?", (id,)).fetchone()
        return owner is not None and owner[0] == database.MACHINE

    def _own(self, id: str) -> None:
        if database.is_remote(self.db_path):
            self.conn.execute(
                "INSERT OR REPLACE INTO haifa_owners VALUES (?, ?)", (id, database.MACHINE)
            )

    def _row(self, values: tuple[Any, ...]) -> TaskRunRow:
        return TaskRunRow(**dict(zip(_COLUMNS, values, strict=True)))

    def _select(self, where: str, args: tuple[Any, ...]) -> list[TaskRunRow]:
        sql = (
            f"SELECT {', '.join(_COLUMNS)} FROM task_runs WHERE {where} "
            "ORDER BY started_at DESC, rowid DESC"
        )
        return [self._row(r) for r in self.conn.execute(sql, args).fetchall()]

    def _reap(self, task_id: str | None = None) -> None:
        """Mark `running` rows whose process is gone as `aborted`. Caller holds the txn."""
        where = "state = ?"
        args: tuple[str, ...] = (RUNNING,)
        if task_id is not None:
            where, args = "state = ? AND task_id = ?", (RUNNING, task_id)
        for row in self._select(where, args):
            if self.owned_here(row.run_id) and not _alive(row.pid):
                self.conn.execute(
                    "UPDATE task_runs SET state = ?, ended_at = ?, error = ?, pause = NULL, "
                    "failure_kind = ?, failure_detail = ? WHERE run_id = ?",
                    (
                        ABORTED,
                        _now(),
                        f"process {row.pid} is gone",
                        failure.PROCESS_GONE,
                        _detail_json({"pid": row.pid}),
                        row.run_id,
                    ),
                )

    @contextlib.contextmanager
    def _txn(self) -> Iterator[None]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    @contextlib.contextmanager
    def serialized(self) -> Iterator[None]:
        """Hold the lock file next to the trace DB: one process at a time in the block.

        No DB transaction stays open in the block, so slow work (git) inside it
        does not keep other runs or the dashboard from writing the trace DB.
        """
        lock = _path_lock(self.db_path.with_name(self.db_path.name + ".lock"))
        with lock.hold(SERIAL_TIMEOUT):
            yield

    @contextlib.contextmanager
    def merge_lock(self, timeout: float = 600.0) -> Iterator[None]:
        """Hold ``<trace db>.merge.lock``: one auto-merge into base at a time, across processes."""
        lock = _path_lock(self.db_path.with_name(self.db_path.name + ".merge.lock"))
        with lock.hold(timeout):
            yield

    def claim(self, row: TaskRunRow) -> None:
        """Insert a `running` row unless the task is running already, atomically."""
        with self.serialized(), self._txn():
            self._reap(row.task_id)
            busy = self._select("state = ? AND task_id = ?", (RUNNING, row.task_id))
            if busy:
                raise already_running(busy[0])
            self._own(row.run_id)
            self.conn.execute(
                f"INSERT INTO task_runs ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in _COLUMNS)})",
                tuple(getattr(row, c) for c in _COLUMNS),
            )

    def reclaim(
        self, run_id: str, pid: int, retry: dict[str, Any], note: str | None = None
    ) -> TaskRunRow:
        """Turn the ended run `run_id` back into ``running`` for a retry, atomically.

        Like ``claim``: fails with ``already_running`` while a run of the task is running.
        Only a ``failed``, ``stopped`` or ``aborted`` run can be retried
        (``run_not_retryable``). `retry` is appended to ``retries``. `note` (a retry on
        another harness: the new roster override) replaces the run's note.
        """
        with self.serialized(), self._txn():
            row = self.get(run_id)
            if row is None:
                raise TaskRunError("unknown_run", f"no run {run_id}")
            self._reap(row.task_id)
            busy = self._select("state = ? AND task_id = ?", (RUNNING, row.task_id))
            if busy:
                raise already_running(busy[0])
            row = self.get(run_id) or row
            if row.state not in RETRYABLE:
                raise TaskRunError(
                    "run_not_retryable",
                    f"run {run_id} of task {row.task_id} is {row.state}; only a failed, "
                    "stopped or aborted run can be retried",
                )
            retries = json.dumps([*row.retry_list(), retry], ensure_ascii=False)
            self._own(run_id)
            self.conn.execute(
                "UPDATE task_runs SET state = ?, pid = ?, ended_at = NULL, error = NULL, "
                "pause = NULL, pr_error = NULL, pr_body = NULL, retries = ?, "
                "failure_kind = NULL, failure_detail = NULL, note = COALESCE(?, note) "
                "WHERE run_id = ?",
                (RUNNING, pid, retries, note, run_id),
            )
        final = self.get(run_id)
        assert final is not None
        return final

    def set_base_sha(self, run_id: str, base_sha: str) -> None:
        """The commit of base the run's branch now starts from (after a retry's rebase)."""
        self.conn.execute("UPDATE task_runs SET base_sha = ? WHERE run_id = ?", (base_sha, run_id))

    def start_operation(self, task_id: str, action: str, pid: int) -> str:
        """Publish process ownership before a run exists, or while publishing again."""
        operation_id = "operation-" + secrets.token_hex(8)
        self.conn.execute(
            "INSERT INTO task_operations VALUES (?, ?, ?, ?, ?)",
            (operation_id, task_id, action, pid, now_iso()),
        )
        self._own(operation_id)
        return operation_id

    def finish_operation(self, operation_id: str) -> None:
        self.conn.execute("DELETE FROM task_operations WHERE operation_id = ?", (operation_id,))

    def live_operations(self) -> list[TaskRunRow]:
        """Live operation evidence without changing run claims; reap dead owners."""
        rows = self.conn.execute(
            "SELECT operation_id, task_id, action, pid, started_at FROM task_operations "
            "ORDER BY started_at DESC, rowid DESC"
        ).fetchall()
        result = []
        for operation_id, task_id, action, pid, started_at in rows:
            if self.owned_here(operation_id) and not _alive(pid):
                self.finish_operation(operation_id)
                continue
            result.append(
                TaskRunRow(
                    run_id=operation_id,
                    task_id=task_id,
                    branch="",
                    worktree="",
                    base="",
                    base_sha="",
                    head_sha=None,
                    state=RUNNING,
                    started_at=started_at,
                    pid=pid,
                    workflow=action,
                )
            )
        return result

    def live_runs_locked(self) -> list[TaskRunRow]:
        """`running` rows whose process is alive (dead ones become `aborted`).

        The caller holds ``serialized()``, so no run can start before it lets go.
        """
        with self._txn():
            self._reap()
            self.live_operations()
            return self._select("state = ?", (RUNNING,))

    def live_runs(self) -> list[TaskRunRow]:
        with self.serialized():
            return self.live_runs_locked()

    def running(self, task_id: str) -> TaskRunRow | None:
        with self._txn():
            self._reap(task_id)
        busy = self._select("state = ? AND task_id = ?", (RUNNING, task_id))
        return busy[0] if busy else None

    def finish(
        self,
        run_id: str,
        state: str,
        head_sha: str | None,
        error: str | None,
        failure_kind: str | None = None,
        failure_detail: dict[str, Any] | None = None,
    ) -> None:
        """Record the end of a run; a `stopped` run keeps its state (the user stopped it).

        A run that did not succeed gets `failure_kind` (``other`` when None) and
        `failure_detail`; a succeeded run gets neither.
        """
        kind: str | None = None
        detail: str | None = None
        if state != SUCCEEDED:
            kind = failure_kind or failure.OTHER
            detail = _detail_json(failure_detail or {})
        cursor = self.conn.execute(
            "UPDATE task_runs SET state = ?, head_sha = ?, error = ?, ended_at = ?, pause = NULL, "
            "failure_kind = ?, failure_detail = ? WHERE run_id = ? AND state != ?",
            (state, head_sha, error, _now(), kind, detail, run_id, STOPPED),
        )
        if cursor.rowcount:
            self._note_priority(run_id, state, kind, error, failure_detail)

    def _note_priority(
        self,
        run_id: str,
        state: str,
        kind: str | None,
        error: str | None,
        detail: dict[str, Any] | None,
    ) -> None:
        """A blocked run gives its task priority; a succeeded run takes it away."""
        found = self.conn.execute(
            "SELECT task_id FROM task_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if found is None:
            return
        task_id = str(found[0])
        if state == SUCCEEDED:
            self.clear_priority(task_id)
            return
        if kind != failure.BLOCKED and failure.error_blockers(error) is None:
            return  # neither the kind nor the error says blocked
        raw = (detail or {}).get("blockers")
        if isinstance(raw, list):
            blockers = [str(b) for b in raw if str(b).strip()]
        else:
            blockers = failure.error_blockers(error) or []
        self.set_priority(task_id, blockers, run_id)

    def set_pr_error(self, run_id: str, error: str | None, body: str | None = None) -> None:
        """Record why the run's push or PR failed (None: it is published now).

        `body` is the PR body the run meant to send; ``factory task publish`` sends it
        later. Clearing the error drops the kept body.
        """
        if error is None:
            self.conn.execute(
                "UPDATE task_runs SET pr_error = NULL, pr_body = NULL WHERE run_id = ?",
                (run_id,),
            )
            return
        self.conn.execute(
            "UPDATE task_runs SET pr_error = ?, pr_body = COALESCE(?, pr_body) WHERE run_id = ?",
            (error, body, run_id),
        )

    def pr_body_of(self, run_id: str) -> str | None:
        """The PR body kept by ``set_pr_error``, or None."""
        row = self.conn.execute(
            "SELECT pr_body FROM task_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return None if row is None or row[0] is None else str(row[0])

    def mark_stopped(self, run_id: str, note: str) -> bool:
        """Set a `running` run to `stopped`; False when it is not running (any more)."""
        with self._txn():
            cursor = self.conn.execute(
                "UPDATE task_runs SET state = ?, ended_at = ?, error = ?, pause = NULL, "
                "failure_kind = ?, failure_detail = ? WHERE run_id = ? AND state = ?",
                (
                    STOPPED,
                    _now(),
                    note,
                    failure.STOPPED,
                    _detail_json({"note": note}),
                    run_id,
                    RUNNING,
                ),
            )
            return cursor.rowcount == 1

    # -- pause --

    def request_pause(self, run_id: str) -> bool:
        """Ask a `running` run without a pause to pause (``pausing``); False otherwise."""
        with self._txn():
            cursor = self.conn.execute(
                "UPDATE task_runs SET pause = ? WHERE run_id = ? AND state = ? AND pause IS NULL",
                (PAUSING, run_id, RUNNING),
            )
            return cursor.rowcount == 1

    def request_resume(self, run_id: str) -> bool:
        """Drop the pause (``paused`` or ``pausing``) of a `running` run; False when it has none."""
        with self._txn():
            cursor = self.conn.execute(
                "UPDATE task_runs SET pause = NULL "
                "WHERE run_id = ? AND state = ? AND pause IN (?, ?)",
                (run_id, RUNNING, PAUSING, PAUSED),
            )
            return cursor.rowcount == 1

    def enter_pause(self, run_id: str) -> bool:
        """Turn an asked-for pause (``pausing``) into ``paused``; False when none was asked."""
        with self._txn():
            cursor = self.conn.execute(
                "UPDATE task_runs SET pause = ? WHERE run_id = ? AND state = ? AND pause = ?",
                (PAUSED, run_id, RUNNING, PAUSING),
            )
            return cursor.rowcount == 1

    def pause_of(self, run_id: str) -> tuple[str, str | None] | None:
        """(state, pause) of the run, or None when there is no such run."""
        row = self.conn.execute(
            "SELECT state, pause FROM task_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return None if row is None else (str(row[0]), row[1])

    def _has_table(self, name: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
        return row is not None

    def live_processes(self, run_id: str) -> list[tuple[str, str, int, str]]:
        """(kind, name, pid, command) of the run's processes believed alive, newest first."""
        if not self._has_table("processes"):
            return []
        rows = self.conn.execute(
            "SELECT kind, name, pid, command FROM processes "
            "WHERE adw_id = ? AND ended_at IS NULL ORDER BY id DESC",
            (run_id,),
        ).fetchall()
        return [(str(k or ""), str(n or ""), int(p), str(c or "")) for k, n, p, c in rows]

    def close_processes(self, run_id: str) -> None:
        """Close the run's process rows and a still `running` session in the trace."""
        now = _now()
        if self._has_table("processes"):
            self.conn.execute(
                "UPDATE processes SET ended_at = ? WHERE adw_id = ? AND ended_at IS NULL",
                (now, run_id),
            )
        if self._has_table("sessions"):
            self.conn.execute(
                "UPDATE sessions SET status = 'fail', ended_at = ? "
                "WHERE adw_id = ? AND status = 'running'",
                (now, run_id),
            )

    def get(self, run_id: str) -> TaskRunRow | None:
        rows = self._select("run_id = ?", (run_id,))
        return rows[0] if rows else None

    def for_task(self, task_id: str) -> list[TaskRunRow]:
        """Every run of `task_id`, newest first (dead `running` rows become `aborted`)."""
        with self._txn():
            self._reap(task_id)
        return self._select("task_id = ?", (task_id,))

    def branches(self, task_id: str) -> list[str]:
        return [r.branch for r in self._select("task_id = ?", (task_id,))]

    def runs_on_branch(self, branch: str) -> list[TaskRunRow]:
        """Runs on `branch`, newest first."""
        return self._select("branch = ?", (branch,))

    def all_runs(self) -> list[TaskRunRow]:
        """Every run, newest first (dead `running` rows become `aborted`)."""
        with self._txn():
            self._reap()
        return self._select("1 = 1", ())

    # -- archive --

    def archive(self, run_id: str) -> bool:
        """Archive a finished run; False when there is no such run.

        A running run (whose process is alive) raises ``run_running``.
        """
        with self._txn():
            self._reap()
            row = self.get(run_id)
            if row is None:
                return False
            if row.state == RUNNING:
                raise TaskRunError("run_running", f"run {run_id} is still running")
            self.conn.execute("UPDATE task_runs SET archived = 1 WHERE run_id = ?", (run_id,))
            return True

    def archive_finished(self) -> list[str]:
        """Archive every finished run that is not archived yet; their ids, newest first."""
        with self._txn():
            self._reap()
            ids = [r.run_id for r in self._select("archived = 0 AND state != ?", (RUNNING,))]
            if ids:
                self.conn.execute(
                    f"UPDATE task_runs SET archived = 1 WHERE run_id IN ({_marks(ids)})",
                    tuple(ids),
                )
            return ids

    def unarchive(self, run_id: str) -> bool:
        """Return an archived run to the active ones; False when there is no such run."""
        cursor = self.conn.execute("UPDATE task_runs SET archived = 0 WHERE run_id = ?", (run_id,))
        return cursor.rowcount == 1

    def _purge(self, ids: list[str]) -> None:
        """Delete the runs `ids` and their trace rows. Caller holds the txn."""
        for table in _TRACE_TABLES:
            if self._has_table(table):
                self.conn.execute(
                    f"DELETE FROM {table} WHERE adw_id IN ({_marks(ids)})", tuple(ids)
                )
        self.conn.execute(f"DELETE FROM task_runs WHERE run_id IN ({_marks(ids)})", tuple(ids))

    def delete_run(self, run_id: str) -> bool:
        """Erase an archived run with its trace; False when there is no such run.

        A run that is not archived raises ``run_not_archived``.
        """
        with self._txn():
            row = self.get(run_id)
            if row is None:
                return False
            if not row.archived:
                raise TaskRunError("run_not_archived", f"run {run_id} is not archived")
            self._purge([run_id])
            return True

    def delete_archived(self) -> list[str]:
        """Erase every archived run with its trace, in one transaction; their ids."""
        with self._txn():
            ids = [r.run_id for r in self._select("archived = 1", ())]
            if ids:
                self._purge(ids)
            return ids

    # -- task_prs --

    def _prs(self, where: str, args: tuple[Any, ...]) -> list[TaskPrRow]:
        sql = (
            f"SELECT {', '.join(_PR_COLUMNS)} FROM task_prs WHERE {where} "
            "ORDER BY created_at DESC, rowid DESC"
        )
        return [
            TaskPrRow(**dict(zip(_PR_COLUMNS, r, strict=True)))
            for r in self.conn.execute(sql, args).fetchall()
        ]

    def save_pr(self, row: TaskPrRow) -> None:
        self.conn.execute(
            f"INSERT OR REPLACE INTO task_prs ({', '.join(_PR_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in _PR_COLUMNS)})",
            tuple(getattr(row, c) for c in _PR_COLUMNS),
        )

    def update_pr(self, branch: str, **fields: object) -> None:
        """Set `fields` of the PR of `branch`; ``updated_at`` is set too."""
        unknown = set(fields) - set(_PR_COLUMNS)
        if unknown:
            raise ValueError(f"unknown task_prs columns: {sorted(unknown)}")
        fields.setdefault("updated_at", _now())
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE task_prs SET {sets} WHERE branch = ?", (*fields.values(), branch)
        )

    def pr_for_branch(self, branch: str) -> TaskPrRow | None:
        rows = self._prs("branch = ?", (branch,))
        return rows[0] if rows else None

    def latest_pr(self, task_id: str) -> TaskPrRow | None:
        """The newest PR of `task_id`, in any state."""
        rows = self._prs("task_id = ?", (task_id,))
        return rows[0] if rows else None

    def open_pr(self, task_id: str) -> TaskPrRow | None:
        rows = self._prs("task_id = ? AND state = 'open'", (task_id,))
        return rows[0] if rows else None

    def prs_for_task(self, task_id: str) -> list[TaskPrRow]:
        return self._prs("task_id = ?", (task_id,))

    def done_prs(self) -> list[TaskPrRow]:
        """Merged and closed pull requests, newest first (merged_at, else updated_at)."""
        sql = (
            f"SELECT {', '.join(_PR_COLUMNS)} FROM task_prs "
            "WHERE state IN ('merged', 'closed') "
            "ORDER BY COALESCE(merged_at, updated_at) DESC, created_at DESC, rowid DESC"
        )
        return [
            TaskPrRow(**dict(zip(_PR_COLUMNS, r, strict=True)))
            for r in self.conn.execute(sql).fetchall()
        ]

    def open_prs(self) -> list[TaskPrRow]:
        """Every open pull request, newest first."""
        return self._prs("state = 'open'", ())

    def merged_task_ids(self) -> list[str]:
        """Distinct ids of tasks with at least one merged PR, in id order."""
        rows = self.conn.execute(
            "SELECT DISTINCT task_id FROM task_prs WHERE state = 'merged' ORDER BY task_id"
        ).fetchall()
        return [str(r[0]) for r in rows]

    # -- sync_prs --

    def _sync_prs(self, where: str, args: tuple[Any, ...]) -> list[SyncPrRow]:
        sql = (
            f"SELECT {', '.join(_SYNC_COLUMNS)} FROM sync_prs WHERE {where} "
            "ORDER BY created_at DESC, rowid DESC"
        )
        return [
            SyncPrRow(**dict(zip(_SYNC_COLUMNS, r, strict=True)))
            for r in self.conn.execute(sql, args).fetchall()
        ]

    def save_sync_pr(self, row: SyncPrRow) -> None:
        self.conn.execute(
            f"INSERT OR REPLACE INTO sync_prs ({', '.join(_SYNC_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in _SYNC_COLUMNS)})",
            tuple(getattr(row, c) for c in _SYNC_COLUMNS),
        )

    def update_sync_pr(self, branch: str, **fields: object) -> None:
        """Set `fields` of the sync PR of `branch`; ``updated_at`` is set too."""
        unknown = set(fields) - set(_SYNC_COLUMNS)
        if unknown:
            raise ValueError(f"unknown sync_prs columns: {sorted(unknown)}")
        fields.setdefault("updated_at", _now())
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE sync_prs SET {sets} WHERE branch = ?", (*fields.values(), branch)
        )

    def sync_pr_for_branch(self, branch: str) -> SyncPrRow | None:
        rows = self._sync_prs("branch = ?", (branch,))
        return rows[0] if rows else None

    def open_sync_prs(self) -> list[SyncPrRow]:
        """Every open sync pull request, newest first."""
        return self._sync_prs("state = 'open'", ())

    def sync_branches(self) -> list[str]:
        return [r.branch for r in self._sync_prs("1 = 1", ())]

    # -- task_chains --

    def _chains(
        self, where: str, args: tuple[Any, ...], limit: int | None = None
    ) -> list[TaskChainRow]:
        sql = (
            f"SELECT {', '.join(_CHAIN_COLUMNS)} FROM task_chains WHERE {where} "
            "ORDER BY started_at DESC, rowid DESC"
        )
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        return [
            TaskChainRow(**dict(zip(_CHAIN_COLUMNS, r, strict=True)))
            for r in self.conn.execute(sql, args).fetchall()
        ]

    def start_chain(self, row: TaskChainRow) -> None:
        self._own(row.chain_id)
        self.conn.execute(
            f"INSERT OR REPLACE INTO task_chains ({', '.join(_CHAIN_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in _CHAIN_COLUMNS)})",
            tuple(getattr(row, c) for c in _CHAIN_COLUMNS),
        )

    def update_chain(
        self,
        chain_id: str,
        *,
        run_ids: list[str] | None = None,
        skipped: list[dict[str, Any]] | None = None,
        exclusive: list[str] | None = None,
        events: list[dict[str, Any]] | None = None,
        state: str | None = None,
        stop: str | None = None,
    ) -> None:
        """Set the given fields of a chain; ``updated_at`` always, ``ended_at`` when it ends."""
        now = _now()
        fields: dict[str, object] = {"updated_at": now}
        if run_ids is not None:
            fields["run_ids"] = json.dumps(run_ids)
        if skipped is not None:
            fields["skipped"] = json.dumps(skipped, ensure_ascii=False)
        if exclusive is not None:
            fields["exclusive"] = json.dumps(exclusive)
        if events is not None:
            fields["events"] = json.dumps(events, ensure_ascii=False)
        if state is not None:
            fields["state"] = state
            if state != RUNNING:
                fields["ended_at"] = now
        if stop is not None:
            fields["stop"] = stop
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE task_chains SET {sets} WHERE chain_id = ?", (*fields.values(), chain_id)
        )

    def delete_chain(self, chain_id: str) -> None:
        self.conn.execute("DELETE FROM task_chains WHERE chain_id = ?", (chain_id,))

    def get_chain(self, chain_id: str) -> TaskChainRow | None:
        rows = self._chains("chain_id = ?", (chain_id,))
        return rows[0] if rows else None

    def _reap_chains(self) -> None:
        """A `running` chain whose process is gone becomes `aborted`."""
        with self._txn():
            for row in self._chains("state = ?", (RUNNING,)):
                if self.owned_here(row.chain_id) and not _alive(row.pid):
                    now = _now()
                    self.conn.execute(
                        "UPDATE task_chains SET state = ?, ended_at = ?, updated_at = ? "
                        "WHERE chain_id = ?",
                        (ABORTED, now, now, row.chain_id),
                    )

    def chains(self, limit: int = 10) -> list[TaskChainRow]:
        """Running chains, then the newest ended ones, up to `limit` rows in all.

        A `running` chain whose process is gone becomes `aborted`. A chain that stopped
        ``disabled`` after at most one run is left out: a single run without
        auto-continue (such runs no longer get a row, older ones may have one).
        """
        self._reap_chains()
        running = self._chains("state = ?", (RUNNING,))
        rest = max(0, limit - len(running))
        ended = (
            self._chains(
                "state != ? AND NOT (stop IS ? AND json_array_length(run_ids) <= 1)",
                (RUNNING, _CHAIN_DISABLED),
                rest,
            )
            if rest
            else []
        )
        return [*running, *ended]

    def dismiss_chain(self, chain_id: str) -> bool:
        """Erase an ended chain (its runs stay); False when there is no such chain.

        A running chain (whose process is alive) raises ``chain_running``.
        """
        self._reap_chains()
        with self._txn():
            row = self.get_chain(chain_id)
            if row is None:
                return False
            if row.state == RUNNING:
                raise TaskRunError("chain_running", f"chain {chain_id} is still running")
            self.delete_chain(chain_id)
            return True

    # -- task_queue --

    def queue_prefs(self) -> QueuePrefs:
        """The manual order of tasks for auto-continue and the excluded tasks."""
        if not self._has_table("task_queue"):
            return QueuePrefs(priority=self.priorities())
        rows = self.conn.execute(
            "SELECT task_id, rank, excluded FROM task_queue ORDER BY rank, task_id"
        ).fetchall()
        order = tuple(str(r[0]) for r in rows if r[1] is not None)
        excluded = frozenset(str(r[0]) for r in rows if r[2])
        return QueuePrefs(order, excluded, self.priorities())

    def set_queue_order(self, task_ids: Sequence[str]) -> None:
        """Rank `task_ids` in this order; every other task loses its manual rank."""
        ids = list(task_ids)
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate task id in queue order")
        now = _now()
        with self._txn():
            self.conn.execute("UPDATE task_queue SET rank = NULL, updated_at = ?", (now,))
            for rank, task_id in enumerate(ids):
                self.conn.execute(
                    "INSERT INTO task_queue (task_id, rank, excluded, updated_at) "
                    "VALUES (?, ?, 0, ?) "
                    "ON CONFLICT(task_id) DO UPDATE SET rank = excluded.rank, "
                    "updated_at = excluded.updated_at",
                    (task_id, rank, now),
                )
            self._prune_queue()

    def set_excluded(self, task_id: str, excluded: bool) -> None:
        """Exclude `task_id` from auto-continue (or include it again)."""
        now = _now()
        with self._txn():
            self.conn.execute(
                "INSERT INTO task_queue (task_id, rank, excluded, updated_at) "
                "VALUES (?, NULL, ?, ?) "
                "ON CONFLICT(task_id) DO UPDATE SET excluded = excluded.excluded, "
                "updated_at = excluded.updated_at",
                (task_id, int(excluded), now),
            )
            self._prune_queue()

    def _prune_queue(self) -> None:
        self.conn.execute("DELETE FROM task_queue WHERE rank IS NULL AND excluded = 0")

    # -- task_priority --

    def priorities(self) -> tuple[Priority, ...]:
        """The tasks blocked during a run with their blockers, oldest first."""
        if not self._has_table("task_priority"):
            return ()
        rows = self.conn.execute(
            "SELECT task_id, blockers, run_id, created_at FROM task_priority "
            "ORDER BY created_at, task_id"
        ).fetchall()
        out: list[Priority] = []
        for task_id, blockers, run_id, created in rows:
            try:
                ids = json.loads(blockers or "[]")
            except ValueError:
                ids = []
            listed = tuple(str(i) for i in ids) if isinstance(ids, list) else ()
            out.append(Priority(str(task_id), listed, run_id, str(created)))
        return tuple(out)

    def set_priority(self, task_id: str, blockers: Sequence[str], run_id: str | None) -> None:
        """Give `task_id` priority with `blockers`; a new block keeps the first time."""
        ids = list(dict.fromkeys(b for b in blockers if b != task_id))
        self.conn.execute(
            "INSERT INTO task_priority (task_id, blockers, run_id, created_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(task_id) DO UPDATE SET blockers = excluded.blockers, "
            "run_id = excluded.run_id",
            (task_id, json.dumps(ids, ensure_ascii=False), run_id, _now()),
        )

    def clear_priority(self, task_id: str) -> bool:
        """Take the priority away from `task_id`; False when it had none."""
        if not self._has_table("task_priority"):
            return False
        cursor = self.conn.execute("DELETE FROM task_priority WHERE task_id = ?", (task_id,))
        return bool(cursor.rowcount)

    def prune_priority(self, active: Collection[str]) -> list[str]:
        """Drop the priority of every task not in `active` (no longer ``todo``)."""
        gone = [p.task_id for p in self.priorities() if p.task_id not in active]
        for task_id in gone:
            self.clear_priority(task_id)
        return gone

    # ── quota state of the harnesses and the projects' place in their chain ──

    def mark_quota(self, harness: str, message: str | None, retry_at: str) -> None:
        """Record that `harness` ran out of quota on this computer until `retry_at`."""
        self.conn.execute(
            "INSERT OR REPLACE INTO harness_quota (harness, exhausted_at, retry_at, message) "
            "VALUES (?, ?, ?, ?)",
            (harness, _now(), retry_at, (message or "")[:500] or None),
        )

    def clear_quota(self, harness: str) -> None:
        """`harness` has quota again (a run on it succeeded)."""
        self.conn.execute("DELETE FROM harness_quota WHERE harness = ?", (harness,))

    def quota_retry_at(self, harness: str) -> str | None:
        """When `harness` may have quota again; None when it is not known to be out."""
        row = self.conn.execute(
            "SELECT retry_at FROM harness_quota WHERE harness = ?", (harness,)
        ).fetchone()
        return str(row[0]) if row is not None else None

    def quota_available(self, harness: str, now: datetime | None = None) -> bool:
        """True unless `harness` ran out of quota and its ``retry_at`` is still ahead."""
        retry_at = self.quota_retry_at(harness)
        if retry_at is None:
            return True
        try:
            when = datetime.fromisoformat(retry_at)
        except ValueError:
            return True
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return when <= (now or datetime.now(UTC))

    def project_position(self, project_id: str) -> str | None:
        """The harness of the project's quota chain it is on now; None: its own harness."""
        row = self.conn.execute(
            "SELECT harness FROM project_harness WHERE project_id = ?", (project_id,)
        ).fetchone()
        return str(row[0]) if row is not None else None

    def set_project_position(self, project_id: str, harness: str | None) -> None:
        """Put the project on `harness` of its chain; None: back on its own harness."""
        if harness is None:
            self.conn.execute("DELETE FROM project_harness WHERE project_id = ?", (project_id,))
            return
        self.conn.execute(
            "INSERT OR REPLACE INTO project_harness (project_id, harness, updated_at) "
            "VALUES (?, ?, ?)",
            (project_id, harness, _now()),
        )

    def close(self) -> None:
        self.conn.close()
