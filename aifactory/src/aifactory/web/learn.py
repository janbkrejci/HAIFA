"""The *Lekce* section of the Factory screen: the lessons of ``factory learn`` and the scan.

``state`` lists the stored lessons (``learn.view``) with the repo's scan job. *Najít lekce*
(``start``) runs ``factory learn scan`` in a thread, one at a time per repo; the job stays
until the next scan. *Přijmout* (``accept``) and *Zamítnout* (``dismiss``) are
``factory learn accept`` and ``factory learn dismiss``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aifactory.backlog import TaskEditError
from aifactory.engine.utils import now_iso
from aifactory.errors import UsageError
from aifactory.learn.accept import accept
from aifactory.learn.scan import dismiss, scan
from aifactory.learn.view import lessons

MAX_ACTIVE = 2
_REASON_LIMIT = 2000

Scanner = Callable[[Path, str | None], dict[str, Any]]


@dataclass
class ScanJob:
    repo: Path
    since: str | None
    started_at: str
    state: str = "running"  # running | done | failed
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def json(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "since": self.since,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
        }


def _error_text(exc: BaseException) -> str:
    if isinstance(exc, TaskEditError | UsageError):
        return exc.message
    return f"Hledání lekcí selhalo: {exc}"


def _optional_text(body: dict[str, Any], key: str, limit: int) -> str | None:
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise UsageError(f"{key} must be a string")
    if len(value) > limit:
        raise UsageError(f"{key} is longer than {limit} characters")
    return value.strip() or None


class LearnManager:
    def __init__(self, scanner: Scanner = scan) -> None:
        self.scanner = scanner
        self.pool = ThreadPoolExecutor(max_workers=MAX_ACTIVE, thread_name_prefix="learn")
        self.lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.jobs: dict[Path, ScanJob] = {}
        self.closed = False

    def close(self) -> None:
        with self.lock:
            self.closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)

    def state(self, repo: Path) -> dict[str, Any]:
        with self.lock:
            job = self.jobs.get(repo.resolve())
            scan_json = job.json() if job is not None else None
        return {"lessons": lessons(repo), "scan": scan_json}

    def start(self, repo: Path, body: dict[str, Any]) -> dict[str, Any]:
        if set(body) - {"since"}:
            raise UsageError("expected only since")
        since = _optional_text(body, "since", 64)
        key = repo.resolve()
        with self.lock:
            current = self.jobs.get(key)
            if current is not None and current.state == "running":
                raise TaskEditError("busy", "lessons are being searched already")
            if self.closed:
                raise TaskEditError("busy", "the dashboard is shutting down")
            job = ScanJob(key, since, now_iso())
            self.jobs[key] = job
            self.pool.submit(self._run, job)
            return job.json()

    def _run(self, job: ScanJob) -> None:
        try:
            data = self.scanner(job.repo, job.since)
        except BaseException as exc:
            with self.lock:
                job.state, job.error, job.finished_at = "failed", _error_text(exc), now_iso()
            return
        result = {
            "objections": data.get("objections", 0),
            "runs": data.get("runs", 0),
            "lessons": len(data.get("lessons") or []),
            "repeats": sum(int(r.get("added") or 0) for r in data.get("repeats") or []),
        }
        with self.lock:
            job.state, job.result, job.finished_at = "done", result, now_iso()

    def accept(self, repo: Path, lesson_id: str, body: dict[str, Any]) -> dict[str, Any]:
        if set(body) - {"project"}:
            raise UsageError("expected only project")
        project = _optional_text(body, "project", 200)
        with self.write_lock:
            outcome = accept(repo, lesson_id, project)
        return {**outcome.to_json(), "warnings": list(outcome.warnings)}

    def dismiss(self, repo: Path, lesson_id: str, body: dict[str, Any]) -> dict[str, Any]:
        if set(body) - {"reason"}:
            raise UsageError("expected only reason")
        reason = _optional_text(body, "reason", _REASON_LIMIT)
        with self.write_lock:
            return dismiss(repo, lesson_id, reason)
