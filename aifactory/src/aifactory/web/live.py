"""Live updates of the dashboard: watch ``backlog/``, ``.factory/`` and the trace DB.

``LiveWatcher`` is synchronous and polled: every ``poll()`` compares a snapshot of the
watched files (``mtime_ns``, size) with the previous one and checks the trace DB with
``PRAGMA data_version``; new rows are found with a ``rowid`` cursor, never by reading a
whole table. ``LiveHub`` runs the watcher on a thread while someone listens and fans
its events out to the ``/api/live`` Server-Sent Events streams. The multi-repo app keeps
one hub per repository (``/api/repos/{id}/live``) and closes it when the repository leaves
the registry; ``aclose`` may be called more than once.

Only the standard library watches: polling every 0.5 s keeps changes under the 2 s the
screens promise. ``.factory/worktrees``, ``.factory/data`` and the trace DB files are not
watched as files (checkouts and logs of the runs themselves).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from starlette.concurrency import run_in_threadpool

from aifactory import database
from aifactory.backlog.roots import backlog_roots
from aifactory.config import ConfigError
from aifactory.config.settings import CONFIG_FILE, load_local, parse_project_settings
from aifactory.run import gitops
from aifactory.run.errors import TaskRunError
from aifactory.run.task import FACTORY_DATA_DIR

MAX_PATHS = 200
"""At most this many changed paths go into one ``files`` event (``truncated`` beyond)."""

QUEUE_SIZE = 100
_IGNORED_SUFFIXES = ("~", ".swp", ".swx")
_IGNORED_DIRS = {"__pycache__", ".git"}
_DB_SUFFIXES = ("", "-wal", "-shm", "-journal")

Snapshot = dict[str, tuple[int, int]]


@dataclass(frozen=True)
class LiveEvent:
    """One live update: ``kind`` is ``files``, ``trace`` or ``resync``."""

    kind: str
    data: dict[str, Any] = field(default_factory=dict)


def _main_root(repo: Path) -> Path:
    try:
        return gitops.main_root(repo)
    except TaskRunError:
        return repo.resolve()


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


class LiveWatcher:
    """Poll the files of ``backlog/`` and ``.factory/`` and the trace DB of ``repo``.

    The first ``poll()`` takes the baseline and returns nothing; each later one
    returns the changes since the previous call.
    """

    def __init__(self, repo: Path) -> None:
        self.root = _main_root(repo)
        self._config_stamp: tuple[int, int] | None = None
        self._roots: list[tuple[str, Path]] = []
        self._skip_dirs: set[Path] = set()
        self._skip_files: set[Path] = set()
        self._db: Path | None = None
        self._conn: sqlite3.Connection | None = None
        self._data_version: int | None = None
        self._configure()
        self._snapshot: Snapshot | None = None
        self._max_events = 0
        self._max_phases = 0
        self._runs: dict[str, tuple[Any, ...]] = {}
        self._prs: dict[str, tuple[Any, ...]] = {}
        self._running: dict[str, str] = {}
        self._trace_ready = False

    # -- configuration ---------------------------------------------------------------

    def _stamp(self, path: Path) -> tuple[int, int] | None:
        try:
            st = path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def _configure(self) -> None:
        config = self.root / CONFIG_FILE
        self._config_stamp = self._stamp(config)
        backlog_dirs = ["backlog"]
        worktrees_dir = ".factory/worktrees"
        try:
            text = config.read_text(encoding="utf-8") if config.is_file() else None
        except OSError:
            text = None
        settings = parse_project_settings(text, str(config), [])
        if settings is not None:
            backlog_dirs = backlog_roots(self.root, settings)
            worktrees_dir = settings.worktrees_dir
        try:
            db: Path | None = load_local(self.root).trace_db_path(self.root)
        except (ConfigError, OSError):
            db = self.root / ".factory" / "trace.db"
        self._roots = [
            *(("backlog", (self.root / d).resolve()) for d in backlog_dirs),
            ("factory", (self.root / ".factory").resolve()),
        ]
        self._skip_dirs = {
            (self.root / worktrees_dir).resolve(),
            (self.root / FACTORY_DATA_DIR).resolve(),
        }
        if db is not None and db != self._db:
            self._close_db()
        self._db = db
        self._skip_files = (
            {Path(f"{db}{suffix}") for suffix in _DB_SUFFIXES} if db is not None else set()
        )

    # -- files -----------------------------------------------------------------------

    def _scan(self) -> dict[str, tuple[str, tuple[int, int]]]:
        out: dict[str, tuple[str, tuple[int, int]]] = {}
        for area, top in self._roots:
            if not top.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(top):
                current = Path(dirpath)
                dirnames[:] = [
                    d
                    for d in dirnames
                    if d not in _IGNORED_DIRS and (current / d) not in self._skip_dirs
                ]
                for name in filenames:
                    if name.endswith(_IGNORED_SUFFIXES):
                        continue
                    path = current / name
                    if path in self._skip_files:
                        continue
                    try:
                        st = path.stat()
                    except OSError:
                        continue
                    try:
                        rel = path.relative_to(self.root).as_posix()
                    except ValueError:
                        rel = path.as_posix()
                    # backlog/ may lie inside .factory/ (it never should): first area wins
                    out.setdefault(rel, (area, (st.st_mtime_ns, st.st_size)))
        return out

    def _poll_files(self) -> LiveEvent | None:
        if self._stamp(self.root / CONFIG_FILE) != self._config_stamp:
            self._configure()
        scan = self._scan()
        snapshot: Snapshot = {rel: stamp for rel, (_area, stamp) in scan.items()}
        areas_of = {rel: area for rel, (area, _stamp) in scan.items()}
        previous = self._snapshot
        self._snapshot = snapshot
        if previous is None:
            return None
        changed = {rel for rel, stamp in snapshot.items() if previous.get(rel) != stamp}
        removed = set(previous) - set(snapshot)
        paths = sorted(changed | removed)
        if not paths:
            return None
        areas = set()
        for rel in paths:
            area = areas_of.get(rel) or self._area_of(rel)
            areas.add(area)
        return LiveEvent(
            "files",
            {
                "areas": sorted(areas),
                "paths": paths[:MAX_PATHS],
                "truncated": len(paths) > MAX_PATHS,
            },
        )

    def _area_of(self, rel: str) -> str:
        path = (self.root / rel).resolve()
        for area, top in self._roots:
            if path == top or top in path.parents:
                return area
        return "factory"

    # -- trace -----------------------------------------------------------------------

    def _close_db(self) -> None:
        if self._conn is not None:
            with contextlib.suppress(sqlite3.Error):
                self._conn.close()
        self._conn = None
        self._data_version = None

    def _connect(self) -> sqlite3.Connection | None:
        if self._conn is not None:
            return self._conn
        if self._db is None or not database.available(self._db):
            return None
        conn = database.connect(
            f"file:{self._db}?mode=ro", uri=True, check_same_thread=False, isolation_level=None
        )
        self._conn = conn
        return conn

    def _max_rowid(self, conn: sqlite3.Connection, table: str) -> int:
        if not _has_table(conn, table):
            return 0
        row = conn.execute(f"SELECT MAX(rowid) FROM {table}").fetchone()
        return int(row[0] or 0) if row else 0

    def _poll_trace(self) -> LiveEvent | None:
        try:
            conn = self._connect()
            if conn is None:
                return None
            version = int(conn.execute("PRAGMA data_version").fetchone()[0])
            if version == self._data_version:
                return None
            self._data_version = version
            return self._read_trace(conn)
        except sqlite3.Error:
            self._close_db()
            return None

    def _read_trace(self, conn: sqlite3.Connection) -> LiveEvent | None:
        max_events = self._max_rowid(conn, "events")
        max_phases = self._max_rowid(conn, "phases")
        run_ids: set[str] = set()
        if max_events > self._max_events and _has_table(conn, "events"):
            rows = conn.execute(
                "SELECT DISTINCT adw_id FROM events WHERE rowid > ?", (self._max_events,)
            ).fetchall()
            run_ids.update(str(r[0]) for r in rows if r[0] is not None)
        if max_phases > self._max_phases and _has_table(conn, "phases"):
            rows = conn.execute(
                "SELECT DISTINCT adw_id FROM phases WHERE rowid > ?", (self._max_phases,)
            ).fetchall()
            run_ids.update(str(r[0]) for r in rows if r[0] is not None)
        running: dict[str, str] = {}
        if _has_table(conn, "phases"):
            rows = conn.execute(
                "SELECT phase_id, adw_id FROM phases WHERE status = 'running'"
            ).fetchall()
            running = {str(r[0]): str(r[1]) for r in rows}
        for phase_id in set(running) ^ set(self._running):
            run_ids.add(running.get(phase_id) or self._running[phase_id])
        runs: dict[str, tuple[Any, ...]] = {}
        if _has_table(conn, "task_runs"):
            columns = {c[1] for c in conn.execute("PRAGMA table_info(task_runs)")}
            archived = "archived" if "archived" in columns else "0"
            pause = "pause" if "pause" in columns else "NULL"  # pausing -> paused shows at once
            rows = conn.execute(
                f"SELECT run_id, task_id, state, ended_at, head_sha, {archived}, {pause} "
                "FROM task_runs"
            ).fetchall()
            runs = {str(r[0]): tuple(r) for r in rows}
        prs: dict[str, tuple[Any, ...]] = {}
        if _has_table(conn, "task_prs"):
            rows = conn.execute(
                "SELECT branch, task_id, state, updated_at FROM task_prs"
            ).fetchall()
            prs = {str(r[0]): tuple(r) for r in rows}
        task_ids: set[str] = set()
        for new, old in ((runs, self._runs), (prs, self._prs)):
            for key in set(new) | set(old):
                if new.get(key) != old.get(key):
                    row = new.get(key) or old[key]
                    task_ids.add(str(row[1]))
        runs_changed = bool(task_ids)
        for run_id in run_ids:
            run = runs.get(run_id)
            if run is not None:
                task_ids.add(str(run[1]))
        first = not self._trace_ready
        self._max_events, self._max_phases = max_events, max_phases
        self._runs, self._prs, self._running = runs, prs, running
        if first or not (run_ids or task_ids):
            return None
        return LiveEvent(
            "trace",
            {
                "events": max_events,
                "phases": max_phases,
                "run_ids": sorted(run_ids),
                "task_ids": sorted(task_ids),
                "runs_changed": runs_changed,
            },
        )

    # -- public ----------------------------------------------------------------------

    def poll(self) -> list[LiveEvent]:
        """The changes since the previous call (``[]`` on the first, the baseline)."""
        events: list[LiveEvent] = []
        files = self._poll_files()
        if files is not None:
            events.append(files)
        if self._db is not None and database.is_remote(self._db):
            # Remote Markdown edits become local file events on the next scan.
            from aifactory.backlog.edit import TaskEditError
            from aifactory.backlog.loader import load_backlog

            try:
                load_backlog(self.root)
            except (sqlite3.Error, ConfigError, OSError, TaskEditError):
                pass
        trace = self._poll_trace()
        if trace is not None:
            events.append(trace)
        self._trace_ready = True  # a trace DB created later reports its rows
        return events

    def close(self) -> None:
        self._close_db()


class LiveHub:
    """Fan the watcher's events out to every ``/api/live`` subscriber.

    The watcher polls only while someone is subscribed; each event gets a rising
    ``seq``. A subscriber whose queue is full gets its queue replaced by one
    ``resync`` event, so a slow client never holds the others up.
    """

    def __init__(self, repo: Path, *, interval: float = 0.5) -> None:
        self.repo = repo
        self.interval = interval
        self._queues: set[asyncio.Queue[LiveEvent | None]] = set()
        self._task: asyncio.Task[None] | None = None
        self._seq = 0

    async def subscribe(self) -> asyncio.Queue[LiveEvent | None]:
        queue: asyncio.Queue[LiveEvent | None] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._queues.add(queue)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return queue

    def unsubscribe(self, queue: asyncio.Queue[LiveEvent | None]) -> None:
        self._queues.discard(queue)
        if not self._queues and self._task is not None:
            self._task.cancel()
            self._task = None

    def publish(self, event: LiveEvent) -> None:
        self._seq += 1
        stamped = LiveEvent(event.kind, {**event.data, "seq": self._seq})
        for queue in list(self._queues):
            try:
                queue.put_nowait(stamped)
            except asyncio.QueueFull:
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(LiveEvent("resync", {"seq": self._seq}))

    async def _run(self) -> None:
        watcher = await run_in_threadpool(LiveWatcher, self.repo)
        try:
            await run_in_threadpool(watcher.poll)
            while True:
                await asyncio.sleep(self.interval)
                for event in await run_in_threadpool(watcher.poll):
                    self.publish(event)
        finally:
            watcher.close()

    async def aclose(self) -> None:
        for queue in list(self._queues):
            while not queue.empty():
                queue.get_nowait()
            queue.put_nowait(None)
        self._queues.clear()
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
