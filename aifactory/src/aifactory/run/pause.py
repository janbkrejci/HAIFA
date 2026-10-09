"""Pause and resume a running task run (``factory task pause|resume``, the dashboard).

A pause takes effect at a phase boundary. ``pause_run`` only records the request
(``task_runs.pause = pausing``): the phase in progress (an agent, a test) runs to its
end. Before the next phase the run's own process calls its ``PauseGate``, which turns
the request into ``paused`` and waits, polling the trace DB, until ``resume_run`` drops
the pause. The process stays alive and the run stays ``running`` in the DB, so it keeps
its task lock, its place among the parallel runs (``max_parallel_runs``) and its chain
waiting; it is shown as ``paused``. ``factory task stop`` stops a paused run like any
other: the waiting process gets SIGTERM, and should it outlive that it sees the state
is no longer ``running`` and gives up.

A pause asked for during the last phase has no next phase to hold: the run finishes as
usual and the request is dropped with the rest of the run's pause (``store.finish``).
Nothing is frozen (no SIGSTOP): an agent would lose its API connection and a test would
run out of its time limit.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from aifactory.run.errors import TaskRunError
from aifactory.run.store import PAUSED, PAUSING, RUNNING, TaskRunRow, TaskRunStore, _alive

POLL_SECONDS = 1.0


class RunNoLongerRunning(RuntimeError):
    """The paused run was stopped (or otherwise ended) while it waited."""


@dataclass
class PauseGate:
    """Called by the workflow before every phase: waits while the run is paused."""

    store: TaskRunStore
    run_id: str
    poll: float | None = None  # seconds between two looks at the DB; None: POLL_SECONDS
    sleep: Callable[[float], None] | None = None  # None: time.sleep

    def __call__(self) -> None:
        current = self.store.pause_of(self.run_id)
        if current is None or current[1] is None:
            return
        if current[1] == PAUSING:
            self.store.enter_pause(self.run_id)
        sleep = self.sleep or time.sleep
        while True:
            current = self.store.pause_of(self.run_id)
            if current is None or current[0] != RUNNING:
                state = current[0] if current else "gone"
                raise RunNoLongerRunning(f"run {self.run_id} is {state} while paused")
            if current[1] != PAUSED:
                return
            sleep(self.poll if self.poll is not None else POLL_SECONDS)


def _running_row(store: TaskRunStore, run_id: str) -> TaskRunRow:
    row = store.get(run_id)
    if row is None:
        raise TaskRunError("unknown_run", f"no run {run_id}")
    if row.state == RUNNING and store.owned_here(run_id) and not _alive(row.pid):
        store.for_task(row.task_id)  # reaps it: the process is gone
        row = store.get(run_id) or row
    if row.state != RUNNING:
        raise TaskRunError("run_not_running", f"run {run_id} of task {row.task_id} is {row.state}")
    return row


def _open(repo: Path, run_id: str) -> TaskRunStore:
    from aifactory.run.task import existing_store  # task.py imports this module

    store = existing_store(repo)
    if store is None:
        raise TaskRunError("unknown_run", f"no run {run_id}: there is no trace database")
    return store


def pause_run(repo: Path, run_id: str) -> TaskRunRow:
    """Ask the running run `run_id` to pause before its next phase; the run after the request."""
    store = _open(repo, run_id)
    try:
        row = _running_row(store, run_id)
        if not store.request_pause(run_id):
            current = store.get(run_id) or row
            if current.state != RUNNING:
                raise TaskRunError(
                    "run_not_running", f"run {run_id} of task {row.task_id} is {current.state}"
                )
            raise TaskRunError(
                "run_already_paused",
                f"run {run_id} of task {row.task_id} is already {current.pause}",
            )
        return store.get(run_id) or row
    finally:
        store.close()


def resume_run(repo: Path, run_id: str) -> TaskRunRow:
    """Let the paused run `run_id` go on with its next phase (or drop a pending pause)."""
    store = _open(repo, run_id)
    try:
        row = _running_row(store, run_id)
        if not store.request_resume(run_id):
            current = store.get(run_id) or row
            if current.state != RUNNING:
                raise TaskRunError(
                    "run_not_running", f"run {run_id} of task {row.task_id} is {current.state}"
                )
            raise TaskRunError(
                "run_not_paused", f"run {run_id} of task {row.task_id} is not paused"
            )
        return store.get(run_id) or row
    finally:
        store.close()
