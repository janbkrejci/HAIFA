"""The Backlog's *Nový záměr* dialog: a proposal from an intent, refined and applied.

One job is one open proposal (``workflow.propose``) for a requested target (a project or a
step) or, without one, for the place the agent chooses (automatic placement); the job keeps
its requested ``Target`` for every turn and reports where the latest proposal goes.
The proposer agent runs in a thread,
in an isolated clone kept for the job (``advice_dir``), so a refinement (*Upřesni*)
continues the same agent session with the person's note and the proposal as they edited
it. ``get`` reports the progress of the current turn from the job's ``events.jsonl``.
*Použít* (``apply``) writes the edited proposal like ``factory backlog propose --apply``
and commits the backlog like the dashboard's backlog commit (``factory backlog commit``).
A job ends when it is applied, closed, or idle for ``IDLE_SECONDS``.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from aifactory import backlog as core
from aifactory.backlog import TaskEditError
from aifactory.errors import UsageError
from aifactory.workflow.adaptive import advice_dir
from aifactory.workflow.propose import (
    BacklogProposalOutput,
    Refinement,
    Target,
    edited,
    plan,
    review,
    run_proposer,
    to_json,
    workflow_catalog,
)
from aifactory.workflow.propose_check import Finding

IDLE_SECONDS = 3600
MAX_ACTIVE = 2
PROGRESS_LIMIT = 40
_NOTE_LIMIT = 8000
_INTENT_LIMIT = 8000


class Runner(Protocol):
    def __call__(
        self,
        repo: Path,
        intent: str,
        target: Target,
        *,
        job_id: str | None = ...,
        workdir: Path | None = ...,
        refinement: Refinement | None = ...,
    ) -> tuple[BacklogProposalOutput, core.BatchResult, list[Finding]]: ...


@dataclass
class IntentJob:
    id: str
    repo: Path
    intent: str
    target: Target
    workdir: Path
    stack: ExitStack
    state: str = "queued"  # queued | running | ready | failed | applied | closed
    round: int = 1
    proposal: BacklogProposalOutput | None = None
    data: dict[str, Any] | None = None
    error: str | None = None
    issues: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    applied: dict[str, Any] | None = None
    events_from: int = 0
    touched: float = 0.0

    @property
    def events(self) -> Path:
        return self.repo / ".factory/data/backlog-propose" / self.id / "events.jsonl"

    def progress(self) -> list[dict[str, str]]:
        """What the agent did in the current turn, newest last."""
        try:
            with self.events.open("rb") as stream:
                stream.seek(self.events_from)
                lines = stream.read().decode("utf-8", "replace").splitlines()
        except OSError:
            return []
        items = [item for item in map(_progress_item, lines) if item is not None]
        return items[-PROGRESS_LIMIT:]

    def placement(self) -> dict[str, Any]:
        """Where the latest proposal goes (the agent's choice without a requested target);
        ``{project: null, step: null}`` until there is one."""
        if self.data is None:
            return {"project": None, "step": None}
        project = self.data.get("project") or {}
        step = self.data.get("step") or {}
        return {
            "project": self.data["target"]["project"],
            "step": self.data["target"]["step"],
            "new_project": bool(project.get("new")),
            "new_step": bool(step.get("new")),
        }

    def json(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "state": self.state,
            "round": self.round,
            "intent": self.intent,
            "target": self.placement(),
            "requested": {"project": self.target.project, "step": self.target.step},
            "proposal": self.data,
            "error": self.error,
            "issues": self.issues,
            "notes": list(self.notes),
            "progress": self.progress() if self.state in {"queued", "running"} else [],
            "applied": self.applied,
        }


def _progress_item(line: str) -> dict[str, str] | None:
    try:
        event = json.loads(line)
    except ValueError:
        return None
    if not isinstance(event, dict):
        return None
    kind = event.get("type")
    name = str(event.get("name") or "")
    raw = event.get("payload")
    payload: dict[str, Any] = raw if isinstance(raw, dict) else {}
    text: str | None = None
    if kind == "agent_start":
        model = payload.get("model") or ""
        text = f"Agent {name} pracuje" + (f" ({model})" if model else "")
    elif kind == "tool_call":
        text = name
    elif kind == "gate_fail":
        text = "Kontrola vrátila návrh agentovi k opravě"
    elif kind == "log" and name == "provider_backoff":
        text = "Provider je přetížený, agent čeká"
    elif kind == "log" and name == "session_fallback":
        text = "Předchozí session agenta chybí, pokračuje v nové"
    elif kind == "agent_end":
        text = "Agent odevzdal návrh"
    elif kind == "error":
        text = f"Chyba: {str(payload.get('error') or '')[:200]}"
    if text is None:
        return None
    return {"kind": str(kind), "text": text[:300], "ts": str(event.get("ts") or "")}


def _target(body: dict[str, Any]) -> Target:
    project = body.get("project")
    step = body.get("step")
    if not isinstance(project, str | None) or not isinstance(step, str | None):
        raise UsageError("project and step must be strings")
    project = (project or "").strip() or None
    step = (step or "").strip() or None
    if project is not None and step is not None:
        raise UsageError(
            "choose a project (a new step), a step (new tasks), or neither (the agent places it)"
        )
    return Target(project=project, step=step)


def _text(body: dict[str, Any], key: str, limit: int) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise UsageError(f"{key} must be a non-empty string")
    if len(value) > limit:
        raise UsageError(f"{key} is longer than {limit} characters")
    return value.strip()


def _tasks(body: dict[str, Any]) -> list[dict[str, Any]] | None:
    tasks = body.get("tasks")
    if tasks is None:
        return None
    if not isinstance(tasks, list) or not all(isinstance(t, dict) for t in tasks):
        raise UsageError("tasks must be a list of {code, title, body}")
    return tasks


def _error_text(exc: BaseException) -> tuple[str, list[dict[str, Any]]]:
    if isinstance(exc, TaskEditError):
        return exc.message, [i.to_dict() for i in exc.issues]
    if isinstance(exc, UsageError):
        return exc.message, []
    return "Agent nedokončil návrh. Zkus to znovu.", []


class IntentManager:
    def __init__(self, runner: Runner = run_proposer, clock: Callable[[], float] = time.monotonic):
        self.runner = runner
        self.clock = clock
        self.pool = ThreadPoolExecutor(max_workers=MAX_ACTIVE, thread_name_prefix="intent")
        self.lock = threading.RLock()
        self.write_lock = threading.Lock()
        self.jobs: dict[str, IntentJob] = {}
        self.closed = False

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def _finish(self, job: IntentJob, state: str) -> None:
        job.state = state
        try:
            job.stack.close()
        except OSError:
            pass

    def _expire(self) -> None:
        now = self.clock()
        for key, job in list(self.jobs.items()):
            idle = now - job.touched >= IDLE_SECONDS
            if job.state in {"queued", "running"} or not idle:
                continue
            if job.state not in {"applied", "closed"}:
                self._finish(job, "closed")
            del self.jobs[key]

    def close(self) -> None:
        with self.lock:
            self.closed = True
            for job in self.jobs.values():
                if job.state not in {"queued", "running"}:
                    self._finish(job, "closed" if job.state != "applied" else job.state)
        self.pool.shutdown(wait=False, cancel_futures=True)

    # ── requests ──────────────────────────────────────────────────────────────
    def start(self, repo: Path, body: dict[str, Any]) -> dict[str, Any]:
        if set(body) - {"intent", "project", "step"}:
            raise UsageError("expected intent, and optionally project or step")
        intent = _text(body, "intent", _INTENT_LIMIT)
        target = _target(body)
        repo = repo.resolve()
        with self.lock:
            self._expire()
            active = sum(j.state in {"queued", "running"} for j in self.jobs.values())
            if self.closed or active >= MAX_ACTIVE:
                raise TaskEditError("busy", "the proposer agents are busy; try again shortly")
            stack = ExitStack()
            workdir = stack.enter_context(advice_dir())
            identifier = f"intent-{uuid.uuid4().hex[:12]}"
            job = IntentJob(identifier, repo, intent, target, workdir, stack, touched=self.clock())
            self.jobs[job.id] = job
            self.pool.submit(self._run, job, None)
            return job.json()

    def get(self, repo: Path, identifier: str) -> IntentJob:
        with self.lock:
            self._expire()
            job = self.jobs.get(identifier)
            if job is None or job.repo != repo.resolve() or job.state == "closed":
                raise TaskEditError("unknown_intent", "the proposal expired or was closed")
            job.touched = self.clock()
            return job

    def refine(self, repo: Path, identifier: str, body: dict[str, Any]) -> dict[str, Any]:
        if set(body) - {"note", "tasks"}:
            raise UsageError("expected note and tasks")
        note = _text(body, "note", _NOTE_LIMIT)
        tasks = _tasks(body)
        with self.lock:
            job = self.get(repo, identifier)
            if job.state != "ready" or job.proposal is None:
                raise UsageError("the proposal is not ready to be refined")
            current = edited(job.proposal, job.target, tasks) if tasks is not None else job.proposal
            job.notes.append(note)
            job.round += 1
            job.error = None
            job.issues = []
            job.state = "queued"
            self.pool.submit(self._run, job, Refinement(note, current))
            return job.json()

    def _run(self, job: IntentJob, refinement: Refinement | None) -> None:
        with self.lock:
            if job.state == "closed":
                job.stack.close()
                return
            job.state = "running"
            try:
                job.events_from = job.events.stat().st_size
            except OSError:
                job.events_from = 0
        try:
            proposal, result, findings = self.runner(
                job.repo,
                job.intent,
                job.target,
                job_id=job.id,
                workdir=job.workdir,
                refinement=refinement,
            )
            data = to_json(proposal, result, job.target, findings)
        except BaseException as exc:
            message, issues = _error_text(exc)
            with self.lock:
                job.error = message
                job.issues = issues
                if job.state == "closed":
                    job.stack.close()
                else:
                    # a failed refinement keeps the proposal the person had
                    job.state = "ready" if job.proposal is not None else "failed"
                    if job.state == "failed":
                        self._finish(job, "failed")
                job.touched = self.clock()
            return
        with self.lock:
            job.proposal = proposal
            job.data = data
            job.touched = self.clock()
            if job.state == "closed":
                job.stack.close()
            else:
                job.state = "ready"

    def apply(self, repo: Path, identifier: str, body: dict[str, Any]) -> dict[str, Any]:
        """Write the edited proposal (validated like ``propose --apply``) and commit it."""
        if set(body) - {"tasks"}:
            raise UsageError("expected tasks")
        tasks = _tasks(body)
        with self.write_lock:
            with self.lock:
                job = self.get(repo, identifier)
                if job.state != "ready" or job.proposal is None:
                    raise UsageError("the proposal is not ready to be applied")
                proposal = (
                    edited(job.proposal, job.target, tasks) if tasks is not None else job.proposal
                )
                job.state = "applying"
            try:
                result = plan(
                    job.repo, proposal, job.target, workflow_catalog(job.repo), write=True
                )
            except BaseException:
                with self.lock:
                    job.state = "ready"
                raise
            findings = review(job.repo, proposal, job.target)
            data = to_json(proposal, result, job.target, [f for f in findings if not f.blocking])
            warnings: list[str] = []
            commit: dict[str, Any] | None = None
            try:
                commit = core.commit_backlog(job.repo).to_json()
            except TaskEditError as exc:
                warnings.append(
                    f"Návrh je zapsaný, ale commit backlogu selhal: {exc.message}. "
                    "Commitni backlog ručně."
                )
            data["commit"] = commit
            data["warnings"] = warnings
            with self.lock:
                job.proposal = proposal
                job.data = data
                job.applied = {"files": data["files"], "commit": commit, "warnings": warnings}
                self._finish(job, "applied")
            return data

    def discard(self, repo: Path, identifier: str) -> dict[str, Any]:
        with self.lock:
            job = self.get(repo, identifier)
            if job.state in {"queued", "running"}:
                job.state = "closed"  # the running turn closes the clone when it ends
            elif job.state != "applied":
                self._finish(job, "closed")
            self.jobs.pop(identifier, None)
            return {"job_id": identifier, "closed": True}
