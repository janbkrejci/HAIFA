"""Runs of a parallel auto-continue chain as separate ``factory`` processes.

``run_task`` cannot run twice in one process at once: it changes the working
directory (``os.chdir`` into the worktree), sets environment variables and the
engine depends on the process's cwd. With ``max_parallel_runs`` above 1,
``queue.run_chain`` therefore starts every task of the chain as its own process,
``<prefix> task run ID --repo ROOT --json --member``, the same way the dashboard
starts runs (``web.launcher``): ``start_new_session``, stdin closed, the repository
root as cwd, stdout (the JSON envelope) and stderr (the narration) in two new files
with mode 0600 in ``logs/`` of the HAIFA home.

``--member`` runs exactly one task (never a chain). With ``auto_merge`` inherited by
the task, the member process merges its own PR (only it holds the workflow run with
the last review), under the merge lock of the store (``<trace db>.merge.lock``), so
parallel merges into base go one after another. A PR in conflict is resolved once
(``resolve_and_merge``, the lock not held) and merged under the lock; the envelope's
``resolve_run`` names the resolve run, which the chain adds to its runs. The chain
reads the outcome from the envelope and from ``task_runs``/``task_prs``.

``ProcessRunner.start`` returns once the run is claimed in ``task_runs``, so the next
selection of the chain already sees it running. ``wait_any`` waits for any member to
exit and returns its ``TaskRunResult`` (``workflow_run`` is None: it lives in the
member process). The chain's ``code`` and ``provider`` (tests) do not reach member
processes; they apply to the sequential chain (``max_parallel_runs: 1``) only.

The command prefix is ``python -m aifactory`` by default; ``set_command_prefix``
replaces it for the dashboard and the chain alike (``validation.worker``).
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from aifactory import home, oscompat
from aifactory.config import ConfigError
from aifactory.run.errors import TaskRunError
from aifactory.run.store import FAILED, STARTED_MANUAL, TaskRunRow
from aifactory.run.task import TaskRunResult, existing_store, task_runs_for

_TAIL_LINES = 20
_TAIL_CHARS = 2000

DEFAULT_COMMAND: tuple[str, ...] = (sys.executable, "-m", "aifactory")
_command: tuple[str, ...] | None = None


def set_command_prefix(prefix: Sequence[str] | None) -> None:
    """Replace the command that starts ``factory`` (None restores ``DEFAULT_COMMAND``)."""
    global _command
    _command = None if prefix is None else tuple(prefix)


def command_prefix() -> tuple[str, ...]:
    """The command that starts ``factory`` for a dashboard run or a chain member."""
    return DEFAULT_COMMAND if _command is None else _command


def tail(path: Path) -> str:
    """The last lines of a log file ('' when unreadable)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    last = "\n".join(text.splitlines()[-_TAIL_LINES:])
    return last[-_TAIL_CHARS:]


def parse_envelope(text: str) -> object:
    """The JSON envelope in a process's stdout (also after narration lines); None if none."""
    try:
        return json.loads(text)
    except ValueError:
        pass
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line == "{":
            try:
                return json.loads("\n".join(lines[i:]))
            except ValueError:
                return None
    return None


def read_envelope(path: Path) -> object:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    return parse_envelope(text)


def launch_error(
    envelope_path: Path, log_path: Path, returncode: int | None, label: str
) -> TaskRunError | None:
    """The error of a process that exited without claiming; None when its envelope is ok."""
    envelope = read_envelope(envelope_path)
    if isinstance(envelope, dict):
        if envelope.get("ok") is True:
            return None
        error = envelope.get("error")
        if envelope.get("ok") is False and isinstance(error, dict):
            code, message = error.get("code"), error.get("message")
            if isinstance(code, str) and isinstance(message, str):
                return TaskRunError(code, message)
    return TaskRunError(
        "internal_error",
        f"{label}: process exited with {returncode} "
        f"without a readable envelope; log tail:\n{tail(log_path)}",
    )


def run_ids(repo: Path, task_id: str) -> set[str]:
    try:
        return {r.run_id for r in task_runs_for(repo, task_id)}
    except (TaskRunError, sqlite3.Error):
        return set()


def new_row(repo: Path, task_id: str, known: set[str]) -> TaskRunRow | None:
    """The newest run of `task_id` that is not in `known`."""
    try:
        rows = task_runs_for(repo, task_id)  # newest first
    except (TaskRunError, sqlite3.Error):
        return None
    return next((r for r in rows if r.run_id not in known), None)


class ChainRunner(Protocol):
    """Starts and waits for the runs of a parallel chain (``ProcessRunner``; tests a double)."""

    def start(
        self,
        task_id: str,
        *,
        note: str | None = None,
        force: bool = False,
        started_by: str = STARTED_MANUAL,
        agents_override: dict[str, str] | None = None,
    ) -> TaskRunRow:
        """Start `task_id`; return its claimed row or raise ``TaskRunError``.

        ``agents_override``: harness/model/thinking for this run only (the first run).
        """
        ...

    def wait_any(self) -> TaskRunResult:
        """Wait for any started run to end; its result."""
        ...

    def active(self) -> list[str]:
        """Task ids of the started runs that have not been returned by ``wait_any``."""
        ...


@dataclass(eq=False)
class _Member:
    task_id: str
    process: subprocess.Popen[bytes] = field(repr=False)
    envelope_path: Path
    log_path: Path
    row: TaskRunRow | None = None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def member_result(
    repo: Path,
    task_id: str,
    row: TaskRunRow | None,
    envelope: object,
    log_tail: str = "",
    returncode: int | None = None,
) -> TaskRunResult:
    """A member's ``TaskRunResult`` from its envelope and the store.

    The row and the PR come from ``task_runs``/``task_prs`` (the newest state), the PR
    error and the auto-merge from the envelope. Without a row the result is a failed run.
    """
    # Local import: aifactory.review imports aifactory.run.
    from aifactory.review.automerge import AutoMergeResult

    data: dict[str, Any] = {}
    warnings: tuple[str, ...] = ()
    error_message: str | None = None
    if isinstance(envelope, dict):
        raw = envelope.get("data")
        if isinstance(raw, dict):
            data = raw
        raw_warnings = envelope.get("warnings")
        if isinstance(raw_warnings, list):
            warnings = tuple(str(w) for w in raw_warnings)
        error = envelope.get("error")
        if isinstance(error, dict):
            error_message = _text(error.get("message"))
    run_data = data.get("run")
    run_id = row.run_id if row is not None else None
    if run_id is None and isinstance(run_data, dict):
        run_id = _text(run_data.get("run_id"))
    store = None
    try:
        store = existing_store(repo)
    except (TaskRunError, ConfigError, sqlite3.Error, OSError):
        store = None
    final: TaskRunRow | None = None
    pr = None
    trace_db = Path()
    try:
        if store is not None:
            trace_db = store.db_path
            if run_id is not None:
                found = store.for_task(task_id)  # reaps a dead `running` row
                final = next((r for r in found if r.run_id == run_id), None)
            if final is not None:
                pr = store.pr_for_branch(final.branch)
    except sqlite3.Error:
        final = final or row
    finally:
        if store is not None:
            store.close()
    if final is None and row is not None:
        final = row
    if final is None:
        message = error_message or (
            f"process exited with {returncode} without a run; log tail:\n{log_tail}"
        )
        final = TaskRunRow(
            run_id=run_id or f"none-{secrets.token_hex(4)}",
            task_id=task_id,
            branch="",
            worktree="",
            base="",
            base_sha="",
            head_sha=None,
            state=FAILED,
            started_at="",
            error=message[:2000],
        )
    result = TaskRunResult(
        run=final,
        workflow_run=None,
        warnings=warnings,
        trace_db=trace_db,
        pr=pr,
        pr_error=_text(data.get("pr_error")),
        auto_merge=AutoMergeResult.from_json(data.get("auto_merge")),
        resolve_run=_resolve_run(repo, data.get("resolve_run"), trace_db),
    )
    return result


def _resolve_run(repo: Path, data: object, trace_db: Path) -> TaskRunResult | None:
    """The member's auto-resolve run (envelope ``resolve_run``) from the store; None if none."""
    if not isinstance(data, dict):
        return None
    run_id = _text(data.get("run_id"))
    if run_id is None:
        return None
    row: TaskRunRow | None = None
    pr = None
    try:
        store = existing_store(repo)
    except (TaskRunError, ConfigError, sqlite3.Error, OSError):
        return None
    if store is None:
        return None
    try:
        row = store.get(run_id)
        if row is not None:
            pr = store.pr_for_branch(row.branch)
    except sqlite3.Error:
        return None
    finally:
        store.close()
    if row is None:
        return None
    return TaskRunResult(run=row, workflow_run=None, warnings=(), trace_db=trace_db, pr=pr)


class ProcessRunner:
    """Starts every run of a parallel chain as a separate ``factory task run --member``."""

    def __init__(
        self,
        repo: Path,
        command: Sequence[str] | None = None,
        *,
        poll: float = 0.2,
        claim_timeout: float = 120.0,
    ) -> None:
        self.repo = repo
        self._command = None if command is None else tuple(command)
        self.poll = poll
        self.claim_timeout = claim_timeout
        self._members: list[_Member] = []

    def active(self) -> list[str]:
        return [m.task_id for m in self._members]

    def start(
        self,
        task_id: str,
        *,
        note: str | None = None,
        force: bool = False,
        started_by: str = STARTED_MANUAL,
        agents_override: dict[str, str] | None = None,
    ) -> TaskRunRow:
        known = run_ids(self.repo, task_id)
        prefix = self._command if self._command is not None else command_prefix()
        argv = [*prefix, "task", "run", task_id, "--repo", str(self.repo), "--json", "--member"]
        if note is not None and note.strip():
            argv.append(f"--note={note}")
        if force:
            argv.append("--force")
        if started_by != STARTED_MANUAL:
            argv.append(f"--started-by={started_by}")
        for key, value in (agents_override or {}).items():
            if value:
                argv.append(f"--{key}={value}")
        logs = home.logs_dir()
        stem = (
            f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-chain-{task_id}-{secrets.token_hex(4)}"
        )
        envelope_path = logs / f"{stem}.json"
        log_path = logs / f"{stem}.log"
        try:
            with home.create_private(envelope_path) as out, home.create_private(log_path) as err:
                process = subprocess.Popen(
                    argv,
                    cwd=self.repo,
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
        member = _Member(task_id, process, envelope_path, log_path)
        deadline = time.monotonic() + self.claim_timeout
        while True:
            row = new_row(self.repo, task_id, known)
            if row is None and process.poll() is not None:
                row = new_row(self.repo, task_id, known)
                if row is None:
                    error = launch_error(
                        envelope_path, log_path, process.returncode, f"run {task_id}"
                    )
                    raise error or TaskRunError(
                        "internal_error", f"run {task_id}: exited without a run"
                    )
            if row is not None:
                member.row = row
                self._members.append(member)
                return row
            if time.monotonic() >= deadline:
                with contextlib.suppress(OSError):
                    oscompat.kill_group(process.pid, force=False)
                process.wait()
                raise TaskRunError(
                    "internal_error", f"run {task_id} was not claimed in {self.claim_timeout}s"
                )
            time.sleep(min(self.poll, 0.05))

    def wait_any(self) -> TaskRunResult:
        if not self._members:
            raise RuntimeError("no active member runs")
        while True:
            for member in list(self._members):
                if member.process.poll() is None:
                    continue
                self._members.remove(member)
                return member_result(
                    self.repo,
                    member.task_id,
                    member.row,
                    read_envelope(member.envelope_path),
                    tail(member.log_path),
                    member.process.returncode,
                )
            time.sleep(self.poll)
