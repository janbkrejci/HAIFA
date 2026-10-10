"""App-owned bounded jobs and transactional saving of validated recommendations."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aifactory import backlog as core
from aifactory import oscompat
from aifactory.config import load_run_config
from aifactory.errors import UsageError
from aifactory.harness import HARNESSES, canonical
from aifactory.harness import settings as harness_settings
from aifactory.home import haifa_home
from aifactory.run import gitops, mainwrites
from aifactory.workflow.adaptive import (
    WorkflowRecommendationOutput,
    context,
    fingerprint,
    recommend,
    validate,
)
from aifactory.workflow.task_advice import TaskRecommendationOutput, validate_task

Runner = Callable[[Path, dict[str, Any], str, threading.Event], dict[str, Any]]


class Cancellation(threading.Event):
    def __init__(self) -> None:
        super().__init__()
        self.process_lock = threading.Lock()
        self.pids: set[int] = set()

    def register(self, pid: int) -> None:
        with self.process_lock:
            if self.is_set():
                self._kill(pid)
            else:
                self.pids.add(pid)

    def unregister(self, pid: int) -> None:
        with self.process_lock:
            self.pids.discard(pid)

    def _kill(self, pid: int) -> None:
        try:
            oscompat.kill(pid, force=True)
        except (OSError, ProcessLookupError):
            pass

    def set(self) -> None:
        with self.process_lock:
            super().set()
            for pid in self.pids:
                self._kill(pid)


@dataclass
class Job:
    id: str
    repo: Path
    context: dict[str, Any]
    fingerprint: str
    state: str = "queued"
    result: dict[str, Any] | None = None
    error: str | None = None
    completed: float | None = None
    cancelled: Cancellation = field(default_factory=Cancellation)
    usage: dict[str, Any] | None = None
    saved: bool = False
    saved_request: str | None = None
    saved_task_content: bytes | None = None
    saved_response: tuple[dict[str, Any], list[str]] | None = None

    def json(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "state": self.state,
            "fingerprint": self.fingerprint,
            "recommendation": self.result,
            "error": self.error,
            "usage": self.usage,
            "warnings": self.result.get("warnings", []) if self.result else [],
        }


@contextmanager
def repo_lock(repo: Path) -> Iterator[None]:
    common = gitops.common_dir(repo)
    if common is None:
        raise UsageError("repository has no git common directory")
    path = common / "haifa/workflow-advice.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        oscompat.lock(fd, blocking=True)
        yield
    finally:
        oscompat.unlock(fd)
        os.close(fd)


def _create_workflow(repo: Path, target: Path, content: bytes) -> tuple[int, int]:
    """Publish complete YAML exclusively, anchored to directory descriptors when supported."""
    descriptors = []
    temporary = f".{uuid.uuid4().hex}.tmp"
    workflow_fd: int | None = None
    wrote_temporary = False
    try:
        if os.open in os.supports_dir_fd and os.link in os.supports_dir_fd:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            factory_fd = os.open(repo / ".factory", flags)
            descriptors.append(factory_fd)
            workflow_fd = os.open("workflows", flags, dir_fd=factory_fd)
            descriptors.append(workflow_fd)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644, dir_fd=workflow_fd)
        else:
            fd = os.open(target.parent / temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        wrote_temporary = True
        stat = os.fstat(fd)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if workflow_fd is not None:
            os.link(temporary, target.name, src_dir_fd=workflow_fd, dst_dir_fd=workflow_fd)
        else:
            os.link(target.parent / temporary, target)
        return stat.st_dev, stat.st_ino
    except FileExistsError as exc:
        raise UsageError("workflow name already exists; request another recommendation") from exc
    finally:
        if wrote_temporary:
            if workflow_fd is not None:
                os.unlink(temporary, dir_fd=workflow_fd)
            else:
                (target.parent / temporary).unlink(missing_ok=True)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _remove_created(target: Path, identity: tuple[int, int], content: bytes) -> None:
    """A rollback must preserve a concurrent replacement or edit of the product file."""
    if target.is_symlink() or not target.is_file():
        return
    stat = target.stat()
    if (stat.st_dev, stat.st_ino) == identity and target.read_bytes() == content:
        target.unlink()


def _resolve(repo: Path, explicit: dict[str, str]) -> dict[str, str]:
    """Advisor harness/model: explicit choice, computer default, else the roster plan agent."""
    try:
        selection = harness_settings.effective_override({}, explicit)
    except ValueError as exc:
        raise UsageError(str(exc)) from exc
    if selection.get("harness"):
        return selection
    rc = load_run_config(repo)
    role = rc.config.roles.roles.get("plan")
    agent = next(
        (a for a in rc.config.agents.agents if role is not None and a.name == role.agent), None
    )
    if agent is None:
        return {}
    return {"harness": canonical(agent.coding_agent), "model": agent.model}


class AdviceManager:
    def __init__(
        self,
        runner: Runner = recommend,
        clock: Callable[[], float] = time.monotonic,
        *,
        task_parameters: bool = False,
    ):
        self.task_parameters = task_parameters
        self.runner = runner
        self.clock = clock
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="workflow-advice")
        self.lock = threading.RLock()
        self.jobs: dict[str, Job] = {}
        self.closed = False

    def _expire(self) -> None:
        self.jobs = {
            key: job
            for key, job in self.jobs.items()
            if job.completed is None or self.clock() - job.completed < 1800
        }

    def options(self, repo: Path) -> dict[str, Any]:
        data = harness_settings.catalog(haifa_home())
        configured = data["settings"]["harnesses"]
        harnesses = [
            {
                "name": name,
                "default_model": configured[name].get("model") or "",
                "models": list(data["models"][name]),
            }
            for name in HARNESSES
            if configured.get(name, {}).get("enabled") and data["available"].get(name)
        ]
        try:
            resolved = _resolve(repo, {})
        except UsageError:
            resolved = {}
        default = (
            {"harness": resolved["harness"], "model": resolved.get("model", "")}
            if resolved.get("harness")
            else None
        )
        return {"default": default, "harnesses": harnesses}

    def start(self, repo: Path, body: dict[str, Any]) -> dict[str, Any]:
        if set(body) - (
            {"task_id", "draft", "harness", "model"}
            if self.task_parameters
            else {"task_id", "draft"}
        ) or not isinstance(body.get("draft"), dict):
            raise UsageError("expected task_id (optional) and draft object")
        task_id = body.get("task_id")
        if task_id is not None and not isinstance(task_id, str):
            raise UsageError("task_id must be a string")
        repo = repo.resolve()
        ctx = context(repo, task_id, body["draft"], task_parameters=self.task_parameters)
        if self.task_parameters:
            harness = body.get("harness")
            model = body.get("model")
            if not isinstance(harness, str | None) or not isinstance(model, str | None):
                raise UsageError("harness and model must be strings")
            offered = {h["name"]: h["models"] for h in self.options(repo)["harnesses"]}
            if harness and harness not in offered:
                raise UsageError("choose an enabled harness")
            if model and (not harness or model not in offered[harness]):
                raise UsageError("choose a model of the selected harness")
            ctx["task_parameters"] = True
            ctx["advisor"] = _resolve(
                repo, {k: v for k, v in (("harness", harness), ("model", model)) if v}
            )
            ctx["available_tasks"] = [
                {"id": t.id, "title": t.title, "depends_on": t.depends_on}
                for t in core.load_for_edit(repo).by_id.values()
                if isinstance(t, core.Task)
            ][:1000]
        digest = fingerprint(ctx)
        with self.lock:
            self._expire()
            for job in self.jobs.values():
                if (
                    job.repo == repo
                    and job.fingerprint == digest
                    and job.state in {"queued", "running"}
                ):
                    return job.json()
            if (
                self.closed
                or sum(j.state in {"queued", "running"} for j in self.jobs.values()) >= 4
            ):
                raise core.TaskEditError("busy", "workflow agents are busy; try again shortly")
            job = Job(uuid.uuid4().hex, repo, ctx, digest)
            self.jobs[job.id] = job
            self.pool.submit(self._run, job)
            return job.json()

    def _run(self, job: Job) -> None:
        with self.lock:
            job.state = "running"
        try:
            result = self.runner(job.repo, job.context, job.id, job.cancelled)
            # Injectable runners receive exactly the same validation as the real agent.
            if self.task_parameters:
                output_task = TaskRecommendationOutput.model_validate(
                    {k: v for k, v in result.items() if k not in {"warnings", "usage"}}
                )
                usage = result.get("usage")
                job.usage = usage
                result = validate_task(job.repo, output_task, job.context)
                result["usage"] = usage
            else:
                output = WorkflowRecommendationOutput.model_validate(
                    {
                        key: value
                        for key, value in result.items()
                        if key not in {"outline", "warnings"}
                    }
                )
                warnings = result.get("warnings", [])
                result = validate(job.repo, output, job.context["catalog"])
                result["warnings"] = (
                    [v for v in warnings if isinstance(v, str)]
                    if isinstance(warnings, list)
                    else []
                )
            with self.lock:
                job.result = result
        except BaseException as exc:
            with self.lock:
                job.error = (
                    exc.message
                    if isinstance(exc, UsageError)
                    else (
                        "Agent nedokončil validní návrh parametrů tasku. Zkus návrh znovu."
                        if self.task_parameters
                        else "Agent nedokončil validní návrh workflow. Zkus návrh znovu."
                    )
                )
        finally:
            if self.task_parameters and job.usage is None:
                trace = job.repo / ".factory/data/workflow-advice" / job.id / "trace.db"
                if trace.is_file():
                    try:
                        with sqlite3.connect(f"{trace.as_uri()}?mode=ro", uri=True) as db:
                            usage = db.execute(
                                "SELECT total_tokens, total_cost FROM sessions WHERE adw_id=?",
                                (job.id,),
                            ).fetchone()
                        chosen = job.context.get("advisor", {}).get("harness")
                        provider = canonical(chosen) if chosen else None
                        if usage:
                            job.usage = {
                                "tokens": usage[0],
                                "cost_usd": usage[1] if provider in {"claude", "pi"} else None,
                            }
                    except sqlite3.Error:
                        pass
            with self.lock:
                job.state = "succeeded" if job.result is not None else "failed"
                job.completed = self.clock()

    def get(self, repo: Path, identifier: str) -> Job:
        with self.lock:
            self._expire()
            job = self.jobs.get(identifier)
            if job is None or job.repo != repo.resolve():
                raise core.TaskEditError(
                    "unknown_workflow_advice", "workflow advice expired or not found"
                )
            return job

    def close(self) -> None:
        with self.lock:
            self.closed = True
            for job in self.jobs.values():
                job.cancelled.set()
        self.pool.shutdown(wait=False, cancel_futures=True)

    def save(
        self,
        repo: Path,
        task_id: str | None,
        body: dict[str, Any],
        writer: Callable[[Path, dict[str, Any]], tuple[dict[str, Any], list[str]]],
    ) -> tuple[dict[str, Any], list[str]]:
        """Validate both changes before persisting; roll back only our newly created YAML."""
        clean = dict(body)
        identifier = clean.pop("workflow_advice_id", None)
        if not isinstance(identifier, str):
            raise UsageError("workflow_advice_id must be a string")
        with repo_lock(repo), self.lock:
            job = self.get(repo, identifier)
            if job.state != "succeeded" or job.result is None or job.context["task_id"] != task_id:
                raise UsageError("workflow advice is not ready for this task")
            result = job.result
            if clean.get("workflow") != result["workflow_name"]:
                raise UsageError("selected workflow differs from recommendation")
            if job.saved_response is not None:
                data, warnings = job.saved_response
                task_path = repo / data["path"]
                if (
                    job.saved_request != fingerprint(clean)
                    or not task_path.is_file()
                    or task_path.read_bytes() != job.saved_task_content
                ):
                    raise UsageError("saved task changed; request workflow advice again")
                if result["decision"] == "new":
                    target = repo / data["workflow_path"]
                    if (
                        target.is_symlink()
                        or not target.is_file()
                        or target.read_text() != result["workflow_yaml"]
                    ):
                        raise UsageError("saved workflow changed; request workflow advice again")
                return dict(data), list(warnings)
            original = job.context["draft"]
            if task_id:
                current = context(repo, task_id, {})["draft"]
                draft = {
                    **original,
                    "title": clean.get("title", current["title"]),
                    "writes": clean.get("writes", current["writes"]),
                    "body": clean.get("body", current["body"]),
                    "depends_on": clean.get("depends_on", current["depends_on"]),
                    "related": clean.get("related", current["related"]),
                }
                if clean.get("clear_writes"):
                    draft["writes"] = None
            else:
                draft = {
                    "step": clean.get("step"),
                    "title": clean.get("title"),
                    "workflow": original["workflow"],
                    "writes": clean.get("writes"),
                    "body": clean.get("body") or "",
                    "depends_on": clean.get("depends_on") or [],
                    "related": clean.get("related") or [],
                }
            if "parameters" in clean:
                draft["parameters"] = clean["parameters"]
            ctx = context(repo, task_id, draft)
            if fingerprint(ctx) != job.fingerprint:
                raise UsageError("task or context changed; request workflow advice again")
            value = WorkflowRecommendationOutput.model_validate(
                {key: v for key, v in result.items() if key not in {"outline", "warnings"}}
            )
            validate(repo, value, ctx["catalog"])
            # Core validation on a disposable copy, with the same repository settings.
            with tempfile.TemporaryDirectory(prefix="factory-advice-save-") as tmp:
                stage = Path(tmp)
                for root in core.load_for_edit(repo).roots:
                    shutil.copytree(repo / root, stage / root)
                (stage / ".factory").mkdir(exist_ok=True)
                shutil.copyfile(repo / ".factory/config.yaml", stage / ".factory/config.yaml")
                writer(stage, clean)
            created: Path | None = None
            created_identity: tuple[int, int] | None = None
            content = b""
            if value.decision == "new":
                folder = repo / ".factory/workflows"
                for parent in (repo / ".factory", folder):
                    if parent.is_symlink():
                        raise UsageError("workflow directory must not be a symlink")
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / f"{value.workflow_name}.yaml"
                if not target.resolve().is_relative_to(repo.resolve()) or target.is_symlink():
                    raise UsageError("unsafe workflow path")
                content = (value.workflow_yaml or "").encode()
                if target.exists():
                    if not job.saved or target.read_bytes() != content:
                        raise UsageError(
                            "workflow name already exists; request another recommendation"
                        )
                else:
                    created_identity = _create_workflow(repo, target, content)
                    created = target
            try:
                data, warnings = writer(repo, clean)
            except BaseException:
                if created and created_identity:
                    _remove_created(created, created_identity, content)
                raise
            if created:
                mainwrites.record(
                    repo,
                    created.relative_to(repo).as_posix(),
                    None,
                    created.read_bytes(),
                    mode=0o644,
                    command="workflow advice save",
                )
            job.saved = True
            if value.decision == "new":
                data.update(
                    requires_config_commit=True,
                    created_workflow=value.workflow_name,
                    workflow_path=f".factory/workflows/{value.workflow_name}.yaml",
                )
                warnings.append(
                    "Nové workflow je uložené. Zveřejni konfiguraci před spuštěním tasku."
                )
            job.saved_request = fingerprint(clean)
            job.saved_task_content = (repo / data["path"]).read_bytes()
            job.saved_response = (dict(data), list(warnings))
            return data, warnings
