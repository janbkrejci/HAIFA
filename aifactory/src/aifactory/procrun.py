"""Bounded child processes and a per-thread time budget for read-only probes.

``budget(seconds)`` sets a deadline for the current thread (a ``ContextVar``; other
threads, such as running tasks, never see it). Inside it ``limit(timeout)`` shortens a
command's timeout to the time left and raises ``BudgetExceeded`` once nothing is left,
so a check with one budget cannot run past it, whatever its probes ask for.

``run(argv, timeout)`` runs one command with its output in temporary files and stops the
command with every process it started (``oscompat.ProcessTree``) on timeout. Waiting for
the process, not for EOF on pipes, keeps a helper that inherited the pipes (an npm shim's
node, a credential daemon) from blocking the caller after the timeout. Only the tree of
the command itself is stopped, never another process.
"""

from __future__ import annotations

import subprocess
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from aifactory import oscompat

_deadline: ContextVar[float | None] = ContextVar("aifactory_probe_deadline", default=None)
_clock = time.monotonic


class BudgetExceeded(subprocess.TimeoutExpired):
    """The thread's time budget is spent; the command was not started."""

    def __init__(self, cmd: Sequence[str] | str) -> None:
        super().__init__(cmd, 0)

    def __str__(self) -> str:
        return f"time budget spent before {self.cmd!r} could run"


@contextmanager
def budget(seconds: float) -> Iterator[float]:
    """Give the current thread ``seconds`` for its commands; yields the deadline."""
    deadline = _clock() + seconds
    current = _deadline.get()
    if current is not None:
        deadline = min(deadline, current)
    token = _deadline.set(deadline)
    try:
        yield deadline
    finally:
        _deadline.reset(token)


def remaining() -> float | None:
    """Seconds left of the current thread's budget, None without one."""
    deadline = _deadline.get()
    return None if deadline is None else deadline - _clock()


def limit(timeout: float | None, cmd: Sequence[str] | str = "") -> float | None:
    """``timeout`` shortened to the budget left; ``BudgetExceeded`` when none is left."""
    left = remaining()
    if left is None:
        return timeout
    if left <= 0:
        raise BudgetExceeded(cmd)
    return left if timeout is None else min(timeout, left)


@dataclass(frozen=True)
class Finished:
    returncode: int
    stdout: str
    stderr: str


def run(
    argv: Sequence[str],
    timeout: float,
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Finished:
    """Run ``argv`` (stdin closed) for at most ``timeout`` seconds, also bounded by the
    thread's budget. Raises ``subprocess.TimeoutExpired`` after stopping the command's
    process tree, ``OSError`` when it cannot start."""
    seconds = limit(timeout, argv)
    assert seconds is not None
    with (
        tempfile.TemporaryFile() as out,
        tempfile.TemporaryFile() as err,
        oscompat.ProcessTree() as tree,
        subprocess.Popen(
            list(argv),
            cwd=cwd,
            env=None if env is None else dict(env),
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            start_new_session=True,
            creationflags=oscompat.NEW_GROUP | tree.creationflags,
        ) as process,
    ):
        tree.adopt(process)
        try:
            returncode = process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            with suppress(Exception):
                tree.kill(process)
            if process.poll() is None:
                process.kill()
            process.wait()
            raise subprocess.TimeoutExpired(list(argv), seconds) from None
        out.seek(0)
        err.seek(0)
        return Finished(returncode, _text(out.read()), _text(err.read()))


def _text(data: bytes) -> str:
    return data.decode("utf-8", "replace")
