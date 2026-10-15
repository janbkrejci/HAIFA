"""The Overview's factory controls: ``POST /api/repos/{id}/control/start|pause|resume|stop``.

``start`` is ``run.queue.start_factory``: it picks ready tasks of the whole repository the
way auto-continue does and starts each like the Spustit button (``factory task run ID`` as
a separate process through the launcher), at most as many as there are free parallel
slots (``max_parallel_runs`` minus the live runs). ``pause``, ``resume`` and ``stop`` call
``pause_run``, ``resume_run`` and ``stop_run`` for every running run of the repository.

``stop_run`` marks a run ``stopped`` at once and then waits for its processes to end (up
to 10 s), so the trace DB cannot tell that a run is still dying: the stops run in
background threads and their progress (``pending``) is kept here, in memory, per
repository root. When the last stop ends, runs started after the stop began (a chain
filled a slot just before its member was stopped) are stopped too, at most
``SWEEP_ROUNDS`` times. A finished stop is kept for ``KEEP_SECONDS`` so the Overview can
show "Zastaveno". A pause is recorded with the runs it affects while any of them still
runs; the Overview tells "pozastavuje se" from "pozastaveno" by the runs' ``pause``.

A run paused during its last phase ends anyway, and its auto-continue chain (a separate
process that knows nothing of this pause) then starts the next task. So while a pause is
recorded, a watcher thread looks every ``HOLD_SECONDS`` for runs started after the pause
began and pauses them too (``hold``). The record (and its watcher) stays until resume or
stop, or until none of its runs runs and no chain of the repository runs any more.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aifactory.config import ConfigError
from aifactory.engine.utils import now_iso
from aifactory.run import pause as run_pause
from aifactory.run import stop as run_stop
from aifactory.run.errors import TaskRunError
from aifactory.run.queue import start_factory
from aifactory.run.store import PAUSED, PAUSING, TaskRunRow
from aifactory.run.task import existing_store

if TYPE_CHECKING:
    from aifactory.web.launcher import Launcher

JsonDict = dict[str, Any]

KEEP_SECONDS = 60.0  # a finished stop stays visible this long
SWEEP_ROUNDS = 3
HOLD_SECONDS = 2.0  # how often a pause looks for runs a chain started after it


def control_key(root: Path) -> str:
    """The key of a repository's control state: its resolved root.

    The dashboard serves only main checkouts (a linked worktree is refused), so the root of
    a request and the Overview's git toplevel are the same folder; no git is run here.
    """
    return str(root.resolve())


def _now() -> str:
    """The time in the format of ``task_runs.started_at`` (compared as text)."""
    return str(now_iso())


def running_runs(repo: Path) -> list[TaskRunRow]:
    """The live runs of the repository (dead ones are reaped); none without a trace DB."""
    store = existing_store(repo)
    if store is None:
        return []
    try:
        return store.live_runs()
    finally:
        store.close()


def running_chains(repo: Path) -> int:
    """How many auto-continue chains of the repository run (dead ones are reaped)."""
    store = existing_store(repo)
    if store is None:
        return 0
    try:
        return len(store.chains(0))
    finally:
        store.close()


def _error(
    row: TaskRunRow | None, run_id: str, exc: TaskRunError | ConfigError | OSError
) -> JsonDict:
    if isinstance(exc, TaskRunError):
        code, message = exc.code, exc.message
    elif isinstance(exc, ConfigError):
        code, message = "invalid_config", str(exc)
    else:
        code, message = "os_error", str(exc)
    return {
        "run_id": run_id,
        "task_id": row.task_id if row is not None else None,
        "code": code,
        "message": message,
    }


@dataclass
class _Stop:
    run_ids: list[str]
    pending: set[str]
    started_at: str
    errors: list[JsonDict] = field(default_factory=list)
    finished_at: str | None = None
    finished_clock: float | None = None
    rounds: int = 0


@dataclass
class _Pause:
    run_ids: list[str]
    started_at: str
    ended: threading.Event = field(default_factory=threading.Event)


class FactoryControl:
    """Repo-wide start, pause, resume and stop; the progress of a stop per repository root."""

    def __init__(
        self,
        stop: Callable[[Path, str], object] = run_stop.stop_run,
        *,
        clock: Callable[[], float] = time.monotonic,
        hold_poll: float | None = HOLD_SECONDS,
    ) -> None:
        """``hold_poll`` None: no watcher for a pause, ``hold`` is called by hand (tests)."""
        self._stop = stop
        self._clock = clock
        self._hold_poll = hold_poll
        self._lock = threading.Lock()
        self._stops: dict[str, _Stop] = {}
        self._pauses: dict[str, _Pause] = {}
        self._threads: list[threading.Thread] = []
        self._watchers: list[threading.Thread] = []

    # -- start --

    def start(self, repo: Path, launcher: Launcher) -> JsonDict:
        """Start ready tasks into the free slots (``start_factory``); what started and why not."""
        result = start_factory(
            repo, lambda task_id: launcher.start(repo, task_id, note=None, force=False)
        )
        return result.to_json()

    # -- pause and resume --

    def pause(self, repo: Path) -> JsonDict:
        """Ask every running run without a pause to pause; the runs asked and the errors."""
        runs = running_runs(repo)
        requested: list[str] = []
        errors: list[JsonDict] = []
        for row in runs:
            if row.pause is not None:
                continue
            requested.append(row.run_id)
            try:
                run_pause.pause_run(repo, row.run_id)
            except (TaskRunError, ConfigError, OSError) as exc:
                errors.append(_error(row, row.run_id, exc))
        affected = [r.run_id for r in runs if r.pause in (PAUSING, PAUSED)] + [
            rid for rid in requested if rid not in {e["run_id"] for e in errors}
        ]
        key = control_key(repo)
        with self._lock:
            if affected:
                self._end_pause(key)
                pause = self._pauses[key] = _Pause(affected, _now())
                if self._hold_poll is not None:
                    self._watch(repo, key, pause, self._hold_poll)
        return {"action": "pause", "run_ids": requested, "errors": errors}

    def _end_pause(self, key: str) -> None:
        """Drop the pause record of `key` and end its watcher; the caller holds the lock."""
        pause = self._pauses.pop(key, None)
        if pause is not None:
            pause.ended.set()

    def _watch(self, repo: Path, key: str, pause: _Pause, poll: float) -> None:
        """Start the watcher of a new pause; the caller holds the lock."""

        def loop() -> None:
            while not pause.ended.wait(poll):
                if not self._hold(repo, key, pause):
                    return

        thread = threading.Thread(target=loop, name=f"factory-pause-{key}", daemon=True)
        self._watchers = [t for t in self._watchers if t.is_alive()]
        self._watchers.append(thread)
        thread.start()

    def hold(self, repo: Path) -> list[str]:
        """Pause the runs started after the repository's pause began; the runs now pausing.

        A chain fills a slot when a run ends, also a run paused during its last phase.
        Without a pause record of the repository nothing happens.
        """
        key = control_key(repo)
        with self._lock:
            pause = self._pauses.get(key)
        if pause is None:
            return []
        before = len(pause.run_ids)
        self._hold(repo, key, pause)
        with self._lock:
            return pause.run_ids[before:]

    def _hold(self, repo: Path, key: str, pause: _Pause) -> bool:
        """Pause late runs of `pause`; False when the pause is over (record dropped)."""
        try:
            runs = running_runs(repo)
            for row in runs:
                if (
                    row.run_id in pause.run_ids
                    or row.pause is not None
                    or row.started_at < pause.started_at
                ):
                    continue
                try:
                    run_pause.pause_run(repo, row.run_id)
                except (TaskRunError, ConfigError, OSError):
                    continue  # ended meanwhile, or paused by hand: try again next time
                with self._lock:
                    if self._pauses.get(key) is not pause:
                        return False
                    pause.run_ids.append(row.run_id)
            live = {r.run_id for r in runs}
            chains = 0 if live & set(pause.run_ids) else running_chains(repo)
        except (TaskRunError, ConfigError, OSError, sqlite3.Error):
            return True  # a busy or broken DB: look again next time (resume and stop end it)
        with self._lock:
            if self._pauses.get(key) is not pause:
                return False
            if live & set(pause.run_ids) or chains:
                return True
            self._end_pause(key)
            return False

    def resume(self, repo: Path) -> JsonDict:
        """Drop the pause of every paused (or pausing) run; the runs resumed and the errors."""
        requested: list[str] = []
        errors: list[JsonDict] = []
        for row in running_runs(repo):
            if row.pause not in (PAUSING, PAUSED):
                continue
            requested.append(row.run_id)
            try:
                run_pause.resume_run(repo, row.run_id)
            except (TaskRunError, ConfigError, OSError) as exc:
                errors.append(_error(row, row.run_id, exc))
        with self._lock:
            self._end_pause(control_key(repo))
        return {"action": "resume", "run_ids": requested, "errors": errors}

    # -- stop --

    def stop(self, repo: Path) -> JsonDict:
        """Stop every running run in background threads; returns at once with the pending runs."""
        key = control_key(repo)
        runs = running_runs(repo)
        with self._lock:
            self._end_pause(key)
            state = self._stops.get(key)
            if state is None or not state.pending:
                state = _Stop([], set(), _now())
                self._stops[key] = state
            new = [r for r in runs if r.run_id not in state.pending]
            self._launch(repo, key, state, new)
            if not state.pending:  # nothing to stop: finished at once
                self._finish(state)
            data = {
                "action": "stop",
                "run_ids": [r.run_id for r in runs],
                "pending": sorted(state.pending),
            }
        return data

    def _launch(self, repo: Path, key: str, state: _Stop, rows: list[TaskRunRow]) -> None:
        """Start one stop thread per row; the caller holds the lock."""
        for row in rows:
            if row.run_id not in state.run_ids:
                state.run_ids.append(row.run_id)
            state.pending.add(row.run_id)
            state.finished_at = state.finished_clock = None
            thread = threading.Thread(
                target=self._stop_one,
                args=(repo, key, state, row),
                name=f"factory-stop-{row.run_id}",
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

    def _finish(self, state: _Stop) -> None:
        state.finished_at = _now()
        state.finished_clock = self._clock()

    def _stop_one(self, repo: Path, key: str, state: _Stop, row: TaskRunRow) -> None:
        error: JsonDict | None = None
        try:
            self._stop(repo, row.run_id)
        except (TaskRunError, ConfigError, OSError) as exc:
            if not (isinstance(exc, TaskRunError) and exc.code == "run_not_running"):
                error = _error(row, row.run_id, exc)
        with self._lock:
            if error is not None:
                state.errors.append(error)
            state.pending.discard(row.run_id)
            if state.pending:
                return
        self._sweep(repo, key, state)

    def _sweep(self, repo: Path, key: str, state: _Stop) -> None:
        """Stop runs started after the stop began (a chain refilled a slot meanwhile)."""
        try:
            late = [
                r
                for r in running_runs(repo)
                if r.run_id not in state.run_ids and r.started_at >= state.started_at
            ]
        except (TaskRunError, ConfigError, OSError):
            late = []
        with self._lock:
            if state.pending:
                return
            if late and state.rounds < SWEEP_ROUNDS:
                state.rounds += 1
                self._launch(repo, key, state, late)
                return
            self._finish(state)

    # -- progress --

    def snapshot(self, root: Path, running: list[str] | None = None) -> JsonDict | None:
        """The progress of the newest stop or pause of the repository, or None.

        ``running`` (the running run ids the caller sees) hides a pause none of whose runs
        runs any more; without it a pause is shown. A hidden pause is kept: a chain may
        still start a run, and ``hold`` drops the pause once no chain runs.
        """
        with self._lock:
            if not self._stops and not self._pauses:
                return None
        key = control_key(root)
        with self._lock:
            stop = self._stops.get(key)
            if stop is not None:
                done = stop.finished_clock
                if done is not None and self._clock() - done > KEEP_SECONDS:
                    del self._stops[key]
                    stop = None
            if stop is not None:
                return {
                    "action": "stop",
                    "run_ids": list(stop.run_ids),
                    "pending": sorted(stop.pending),
                    "errors": list(stop.errors),
                    "started_at": stop.started_at,
                    "finished_at": stop.finished_at,
                }
            pause = self._pauses.get(key)
            if pause is None:
                return None
            if running is not None and not set(pause.run_ids) & set(running):
                return None
            return {
                "action": "pause",
                "run_ids": list(pause.run_ids),
                "pending": [],
                "errors": [],
                "started_at": pause.started_at,
                "finished_at": None,
            }

    def wait(self, timeout: float | None = None) -> None:
        """Wait for the stop threads, also those a sweep starts (tests)."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._lock:
                threads = [t for t in self._threads if t.is_alive()]
                self._threads = threads
            if not threads:
                return
            for thread in threads:
                left = None if deadline is None else max(0.0, deadline - time.monotonic())
                thread.join(left)
            if deadline is not None and time.monotonic() >= deadline:
                return
