"""Stop a running task run (``factory task stop``, the dashboard's Stop button).

``stop_run`` is the one function both call. It marks the run ``stopped`` first
(so the dying process's ``finish(FAILED)`` cannot overwrite it), then sends
SIGTERM to the coding-agent children recorded in the trace's ``processes``
table, and last to the run's own process. A pid whose command no longer
matches what was recorded is left alone (the pid was recycled). What does not
exit within ``timeout`` seconds gets SIGKILL. The worktree and the branch stay;
``factory task clean`` removes them like those of any other unfinished run.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from aifactory import oscompat
from aifactory.run.errors import TaskRunError
from aifactory.run.store import RUNNING, TaskRunRow, TaskRunStore, _alive
from aifactory.run.task import existing_store

STOP_NOTE = "stopped by user"
_POLL = 0.1


@dataclass
class StopResult:
    """The run after the stop and the pids that were signalled."""

    run: TaskRunRow
    signalled: list[int] = field(default_factory=list)
    killed: list[int] = field(default_factory=list)

    def to_json(self) -> dict[str, object]:
        return {
            "run": self.run.to_json(),
            "signalled": list(self.signalled),
            "killed": list(self.killed),
        }


def _ps(pid: int, column: str) -> str | None:
    """``ps -p PID -o COLUMN=`` or None when the pid is gone (or ps failed)."""
    try:
        done = subprocess.run(
            ["ps", "-p", str(pid), "-o", f"{column}="],
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
        )
    except OSError:
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip()


def _running(pid: int) -> bool:
    """The pid exists and is not a zombie (Windows has neither zombies nor ``ps``)."""
    if sys.platform == "win32":
        return oscompat.alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    state = _ps(pid, "stat")
    if state is None:
        return False
    return not state.startswith("Z")


def _same_command(pid: int, recorded: str) -> bool:
    """The live pid still runs what the trace recorded (its first word, the harness)."""
    words = recorded.split()
    if not words:
        return False
    if sys.platform == "win32":
        current = oscompat.image_path(pid)  # no ``ps``: the executable's path
    else:
        current = _ps(pid, "command")
    return bool(current) and words[0] in (current or "")


def _signal(pid: int, *, force: bool) -> bool:
    try:
        oscompat.kill(pid, force=force)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _open(repo: Path, run_id: str) -> TaskRunStore:
    store = existing_store(repo)
    if store is None:
        raise TaskRunError("unknown_run", f"no run {run_id}: there is no trace database")
    return store


def stop_run(repo: Path, run_id: str, *, timeout: float = 10.0) -> StopResult:
    """Stop the running run `run_id` of the repository at `repo` and mark it ``stopped``."""
    store = _open(repo, run_id)
    try:
        row = store.get(run_id)
        if row is None:
            raise TaskRunError("unknown_run", f"no run {run_id}")
        if not store.owned_here(run_id):
            raise TaskRunError("remote_run", "stop this run on the machine that started it")
        if row.state == RUNNING and not _alive(row.pid):
            store.for_task(row.task_id)  # reaps it: the process is gone
            row = store.get(run_id) or row
        if row.state != RUNNING:
            raise TaskRunError(
                "run_not_running", f"run {run_id} of task {row.task_id} is {row.state}"
            )
        if row.pid == os.getpid():
            raise TaskRunError(
                "run_not_running", f"run {run_id} runs in this process and cannot stop itself"
            )
        processes = store.live_processes(run_id)
        if not store.mark_stopped(run_id, STOP_NOTE):
            current = store.get(run_id)
            state = current.state if current else "gone"
            raise TaskRunError("run_not_running", f"run {run_id} of task {row.task_id} is {state}")

        signalled: list[int] = []
        # Children first, then the parent (like sssf `just kill`).
        for kind, _name, pid, command in processes:
            if kind != "agent" or pid in signalled or pid == os.getpid():
                continue
            if not _running(pid) or not _same_command(pid, command):
                continue
            if _signal(pid, force=False):
                signalled.append(pid)
        if row.pid is not None and row.pid not in signalled and _signal(row.pid, force=False):
            signalled.append(row.pid)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and any(_running(p) for p in signalled):
            time.sleep(_POLL)
        killed = [p for p in signalled if _running(p) and _signal(p, force=True)]

        store.close_processes(run_id)
        final = store.get(run_id) or row
        return StopResult(final, signalled, killed)
    finally:
        store.close()


def running_run(repo: Path, task_id: str) -> TaskRunRow | None:
    """The running run of `task_id`, or None (also when there is no trace DB yet)."""
    store = existing_store(repo)
    if store is None:
        return None
    try:
        return store.running(task_id)
    finally:
        store.close()
