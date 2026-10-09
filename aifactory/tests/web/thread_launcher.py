"""Test double of the dashboard's launcher: an in-process thread (not a fixture).

For tests whose fake harnesses live in the test process (``workflow_fakes``), so a run
must not leave it. ``ThreadLauncher`` calls ``run_chain``, ``return_task`` and
``resolve_task`` (looked up on ``aifactory.review`` at call time, tests patch them) on a
daemon thread and waits until the run is claimed in ``task_runs``, like the launcher of
the dashboard did before runs became separate processes: one run at a time.
"""

from __future__ import annotations

import sys
import threading
import time
import traceback
from collections.abc import Callable
from pathlib import Path

import aifactory.review as review_core
from aifactory.review.errors import ReviewError
from aifactory.run import queue as run_queue
from aifactory.run.errors import TaskRunError
from aifactory.run.store import TaskRunRow
from aifactory.web.launcher import LaunchedRun, _new_row, _run_ids

_POLL = 0.05


class ThreadLauncher:
    """One run at a time, on a daemon thread of the test process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._label: str | None = None
        self.last_error: BaseException | None = None

    def busy(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def running(self) -> list[LaunchedRun]:
        return []

    def wait(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

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
        if note is not None and not note.strip():
            note = None
        override = {
            k: v for k, v in (("harness", harness), ("model", model), ("thinking", thinking)) if v
        }
        return self._start(
            repo,
            task_id,
            lambda: run_queue.run_chain(
                repo, task_id, note=note, force=force, auto=auto, agents_override=override or None
            ),
            f"task {task_id}",
            timeout,
        )

    def start_return(
        self, repo: Path, task_id: str, note: str, *, timeout: float = 30.0
    ) -> TaskRunRow | None:
        return self._start(
            repo,
            task_id,
            lambda: review_core.return_task(repo, task_id, note),
            f"return {task_id}",
            timeout,
        )

    def start_resolve(
        self, repo: Path, task_id: str, *, timeout: float = 30.0
    ) -> TaskRunRow | None:
        return self._start(
            repo,
            task_id,
            lambda: review_core.resolve_task(repo, task_id),
            f"resolve {task_id}",
            timeout,
        )

    def _start(
        self, repo: Path, task_id: str, job: Callable[[], object], label: str, timeout: float
    ) -> TaskRunRow | None:
        with self._lock:
            if self.busy():
                raise TaskRunError("already_running", f"{self._label} is still running")
            known = _run_ids(repo, task_id)
            self.last_error = None
            self._label = label
            thread = threading.Thread(target=self._work, args=(job,), daemon=True)
            self._thread = thread
            thread.start()
        deadline = time.monotonic() + timeout
        while True:
            row = _new_row(repo, task_id, known)
            if row is not None:
                return row
            if not thread.is_alive():
                row = _new_row(repo, task_id, known)
                if row is not None:
                    return row
                error = self.last_error
                if isinstance(error, TaskRunError | ReviewError):
                    raise error
                if error is not None:
                    raise TaskRunError("internal_error", f"{type(error).__name__}: {error}")
                return None
            if time.monotonic() >= deadline:
                return None
            time.sleep(_POLL)

    def _work(self, job: Callable[[], object]) -> None:
        try:
            job()
        except BaseException as exc:  # noqa: BLE001 - reported through _start()
            self.last_error = exc
            if not isinstance(exc, TaskRunError | ReviewError):
                traceback.print_exc(file=sys.stderr)
