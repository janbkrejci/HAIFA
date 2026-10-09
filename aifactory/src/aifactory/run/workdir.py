"""Project agent cwd without changing repository-relative guards, outputs or git operations."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from aifactory import harness
from aifactory.backlog import Task
from aifactory.backlog.derived import ancestors
from aifactory.config import ProjectSettings, check_relative_dir
from aifactory.engine.data_types import AgentRequest
from aifactory.run import gitops
from aifactory.run.errors import TaskRunError

_agent_cwd: ContextVar[Path | None] = ContextVar("project_agent_cwd", default=None)


def project_workdir(task: Task, settings: ProjectSettings) -> str:
    chain = ancestors(task)
    if "workdir" in task.own or any("workdir" in c.defaults for c in chain[:-1]):
        raise TaskRunError("invalid_config", "workdir is only allowed on a project")
    project = chain[-1]
    value = project.defaults.get("workdir")
    try:
        return Path(check_relative_dir(settings.workdir if value is None else value)).as_posix()
    except ValueError as exc:
        raise TaskRunError("invalid_config", str(exc)) from exc


def validate_base_dirs(root: Path, commit: str, paths: tuple[str, ...], workdir: str) -> None:
    """Reject symlink directories and missing cwd in the exact tree a run will use."""
    for path in paths:
        parts = Path(path).parts
        for depth in range(1, len(parts) + 1):
            rel = Path(*parts[:depth]).as_posix()
            entry = gitops.git(root, "ls-tree", commit, "--", rel).strip()
            if entry and not entry.startswith("040000 "):
                raise TaskRunError("invalid_config", f"{rel!r} is not a directory in base")
        if path == workdir and path != ".":
            entry = gitops.git(root, "ls-tree", commit, "--", path.rstrip("/")).strip()
            if not entry.startswith("040000 "):
                raise TaskRunError("invalid_config", f"workdir {path!r} is not a directory in base")


class _WorkingHarness:
    """Delegate the adapter API; change only agent subprocess cwd in this context."""

    def __init__(self, adapter: Any) -> None:
        self.adapter = adapter

    def __getattr__(self, name: str) -> Any:
        return getattr(self.adapter, name)

    def run(self, request: AgentRequest, **kwargs: Any) -> Any:
        cwd = _agent_cwd.get()
        if cwd is not None:
            # Resolve runs may rebase before spawning another agent. Recheck the directory.
            root = Path(request.cwd).resolve()
            target = (root / cwd).resolve()
            if not target.is_relative_to(root) or not target.is_dir():
                raise TaskRunError("invalid_config", f"workdir {cwd} must stay inside the worktree")
            request = request.model_copy(update={"cwd": str(target)})
        return self.adapter.run(request, **kwargs)


@contextmanager
def agent_workdir(relative: str) -> Iterator[None]:
    """Install context-aware adapters; repository roots remain untouched in the engine."""
    agents = harness.install()
    replaced: dict[str, Any] = {}
    for name, adapter in list(agents.INTERFACES.items()):
        if not isinstance(adapter, _WorkingHarness):
            replaced[name] = adapter
            agents.INTERFACES[name] = _WorkingHarness(adapter)
    token = _agent_cwd.set(Path(relative))
    try:
        yield
    finally:
        _agent_cwd.reset(token)
        for name, adapter in replaced.items():
            agents.INTERFACES[name] = adapter
