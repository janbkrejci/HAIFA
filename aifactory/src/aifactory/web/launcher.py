"""Start a task run from the dashboard as a separate ``factory`` process.

``RunLauncher.start`` (Spustit), ``start_return`` (Vrátit) and ``start_resolve`` (Vyřešit
konflikt) start ``<prefix> task run|return|resolve ID --repo ROOT --json`` with
``start_new_session``, stdin closed, the repository root as cwd and the server's
environment. The process's stdout (its JSON envelope) and stderr (its narration) go to two
new files with mode 0600 in ``logs/`` of the HAIFA home (``aifactory.home``), never into
the repository; their names carry the server's pid.

The caller (off the event loop, in a thread pool) waits until the run is claimed in
``task_runs`` and gets the row, or ``None`` when it is not claimed within ``timeout``
(``pending``; the process goes on). When the process exits before claiming, the error of
its envelope is raised as a ``TaskRunError`` with the envelope's code (the app maps it to
the same HTTP status as before); an unreadable envelope raises ``internal_error`` with the
tail of the process's output.

Runs are separate processes, so runs of several tasks of one repository, and of several
repositories (several servers), run concurrently; ``busy()`` is always False. The row
carries the run process's pid, so ``POST /api/runs/{id}/stop`` and ``factory task stop``
signal that process and the server keeps running. A daemon thread waits for each process,
so a finished or killed process never stays a zombie, and then reaps the store, so the row
of a killed process becomes ``aborted``. A run outlives the server (its own session, output
in files); a new server sees it as running through ``task_runs``.

The command prefix is ``python -m aifactory`` by default; ``set_command_prefix`` replaces
it (``validation.worker`` sets itself so runs go over the fake harness). The prefix and the
envelope helpers live in ``aifactory.run.members`` (the parallel auto-continue chain starts
its runs the same way) and are re-exported here.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import subprocess
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from aifactory import home, oscompat
from aifactory.config import ConfigError
from aifactory.run import members
from aifactory.run.errors import TaskRunError
from aifactory.run.members import DEFAULT_COMMAND, command_prefix, set_command_prefix
from aifactory.run.store import TaskRunRow
from aifactory.run.task import existing_store

_POLL = 0.05

__all__ = [
    "DEFAULT_COMMAND",
    "LaunchedRun",
    "Launcher",
    "RunLauncher",
    "command_prefix",
    "set_command_prefix",
]

_tail = members.tail
_parse_envelope = members.parse_envelope
_run_ids = members.run_ids
_new_row = members.new_row


class Launcher(Protocol):
    """What the app needs to start runs (``RunLauncher``; tests use a thread double)."""

    def start(
        self,
        repo: Path,
        task_id: str,
        *,
        note: str | None,
        force: bool,
        harness: str | None = None,
        model: str | None = None,
        thinking: str | None = None,
        auto: bool = False,
        timeout: float = 30.0,
    ) -> TaskRunRow | None: ...

    def start_return(
        self, repo: Path, task_id: str, note: str, *, timeout: float = 30.0
    ) -> TaskRunRow | None: ...

    def start_resolve(
        self, repo: Path, task_id: str, *, timeout: float = 30.0
    ) -> TaskRunRow | None: ...

    def busy(self) -> bool: ...

    def running(self) -> list[LaunchedRun]: ...


@dataclass(eq=False)
class LaunchedRun:
    """One run process started by this server."""

    task_id: str
    action: str
    argv: list[str]
    pid: int
    envelope_path: Path
    log_path: Path
    process: subprocess.Popen[bytes] = field(repr=False)
    started_at: float = field(default_factory=time.time)


def _launch_error(launched: LaunchedRun) -> TaskRunError | None:
    """The error of a process that exited without claiming; None when its envelope is ok."""
    return members.launch_error(
        launched.envelope_path,
        launched.log_path,
        launched.process.poll(),
        f"{launched.action} {launched.task_id}",
    )


class RunLauncher:
    """Starts every dashboard run as a separate ``factory`` process."""

    def __init__(self, command: Sequence[str] | None = None) -> None:
        self._command = None if command is None else tuple(command)
        self._lock = threading.Lock()
        self._live: list[LaunchedRun] = []
        self._waiters: list[threading.Thread] = []

    def busy(self) -> bool:
        """Always False: runs are separate processes and run concurrently."""
        return False

    def running(self) -> list[LaunchedRun]:
        """The run processes this launcher started that still run."""
        with self._lock:
            return [r for r in self._live if r.process.poll() is None]

    def wait(self, timeout: float | None = None) -> None:
        """Wait for every started process to exit and be cleaned up (tests)."""
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._lock:
            waiters = list(self._waiters)
        for thread in waiters:
            left = None if deadline is None else max(0.0, deadline - time.monotonic())
            thread.join(left)

    def start(
        self,
        repo: Path,
        task_id: str,
        *,
        note: str | None,
        force: bool,
        harness: str | None = None,
        model: str | None = None,
        thinking: str | None = None,
        auto: bool = False,
        timeout: float = 30.0,
    ) -> TaskRunRow | None:
        """``factory task run``; the claimed ``task_runs`` row, or None if not claimed in time.

        ``harness``/``model``/``thinking`` become ``--harness``/``--model``/``--thinking``
        (this run only), ``auto`` ``--auto`` (auto-continue after it).

        A ``TaskRunError`` from the process's envelope before the claim
        (``unmet_dependencies``, ``already_running``, ``no_writes``, ...) propagates.
        """
        if note is not None and not note.strip():
            note = None
        args = ["task", "run", task_id, "--repo", str(repo), "--json"]
        if note is not None:
            args.append(f"--note={note}")
        if force:
            args.append("--force")
        for key, value in (("harness", harness), ("model", model), ("thinking", thinking)):
            if value:
                args.append(f"--{key}={value}")
        if auto:
            args.append("--auto")
        return self._launch(repo, task_id, "run", args, timeout)

    def start_return(
        self, repo: Path, task_id: str, note: str, *, timeout: float = 30.0
    ) -> TaskRunRow | None:
        """``factory task return --note``; like ``start``."""
        args = ["task", "return", task_id, "--repo", str(repo), "--json", f"--note={note}"]
        return self._launch(repo, task_id, "return", args, timeout)

    def start_resolve(
        self, repo: Path, task_id: str, *, timeout: float = 30.0
    ) -> TaskRunRow | None:
        """``factory task resolve``; like ``start``."""
        args = ["task", "resolve", task_id, "--repo", str(repo), "--json"]
        return self._launch(repo, task_id, "resolve", args, timeout)

    def _launch(
        self, repo: Path, task_id: str, action: str, args: list[str], timeout: float
    ) -> TaskRunRow | None:
        known = _run_ids(repo, task_id)
        prefix = self._command if self._command is not None else command_prefix()
        argv = [*prefix, *args]
        logs = home.logs_dir()
        stem = (
            f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{action}-{task_id}-"
            f"{secrets.token_hex(4)}"
        )
        envelope_path = logs / f"{stem}.json"
        log_path = logs / f"{stem}.log"
        try:
            with home.create_private(envelope_path) as out, home.create_private(log_path) as err:
                process = subprocess.Popen(
                    argv,
                    cwd=repo,
                    env=dict(os.environ),
                    stdin=subprocess.DEVNULL,
                    stdout=out,
                    stderr=err,
                    start_new_session=True,
                    creationflags=oscompat.NEW_GROUP,
                    close_fds=True,
                )
        except OSError as exc:
            raise TaskRunError("internal_error", f"cannot start {argv[0]}: {exc}") from exc
        launched = LaunchedRun(
            task_id=task_id,
            action=action,
            argv=argv,
            pid=process.pid,
            envelope_path=envelope_path,
            log_path=log_path,
            process=process,
        )
        waiter = threading.Thread(
            target=self._reap,
            args=(launched, repo, task_id),
            daemon=True,
            name=f"factory-run-wait-{process.pid}",
        )
        with self._lock:
            self._live.append(launched)
            self._waiters = [t for t in self._waiters if t.is_alive()]
            self._waiters.append(waiter)
        waiter.start()
        deadline = time.monotonic() + timeout
        while True:
            row = _new_row(repo, task_id, known)
            if row is not None:
                return row
            if process.poll() is not None:
                row = _new_row(repo, task_id, known)
                if row is not None:
                    return row
                error = _launch_error(launched)
                if error is not None:
                    raise error
                return None
            if time.monotonic() >= deadline:
                return None
            time.sleep(_POLL)

    def _reap(self, launched: LaunchedRun, repo: Path, task_id: str) -> None:
        launched.process.wait()
        with self._lock:
            if launched in self._live:
                self._live.remove(launched)
        try:
            store = existing_store(repo)
            if store is None:
                return
            try:
                store.for_task(task_id)  # a killed process's `running` row becomes `aborted`
            finally:
                store.close()
        except (TaskRunError, ConfigError, sqlite3.Error, OSError):
            pass
