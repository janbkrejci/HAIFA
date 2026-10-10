"""Repositories of the multi-repo dashboard: inspect, status and per-repo contexts.

``inspect_repo`` and ``vet_path`` look at a folder the dashboard may not know yet. They
only read: ``~`` is expanded, the folder must exist, the repository's top level is taken
and the only git commands are ``rev-parse``, ``cat-file``, ``ls-tree``, ``for-each-ref``
and ``remote get-url`` (with ``GIT_OPTIONAL_LOCKS=0``). HAIFA never runs ``git init``.
A folder without git, a bare repository, a linked worktree (the main checkout is offered),
a path under ``.factory/worktrees/``, a repository without a commit and a repository whose
trace DB another registered repository already uses are refused.

``repo_status`` is one item of ``GET /api/repos``: ``ok``, ``uncommitted``,
``not_installed``, ``missing`` or ``not_git``, with the factory state from
``aifactory.config.repo_state.repo_state``. ``RepoContexts`` keeps one ``LiveHub`` per
registered repository and closes it when the repository leaves the registry.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aifactory.config import ConfigError
from aifactory.config.repo_state import RepoState, repo_state
from aifactory.config.settings import load_local
from aifactory.run.gitops import read_git, repo_layout
from aifactory.web import settings as web_settings
from aifactory.web.backlog import UsageError
from aifactory.web.factory import FactoryState
from aifactory.web.live import LiveHub
from aifactory.web.registry import Registry, RegistryState, RepoEntry, RepoError, same_repo

JsonDict = dict[str, Any]

REPO_STATUSES = ("ok", "uncommitted", "not_installed", "missing", "not_git")
RUN_WORKTREE_PARTS = (".factory", "worktrees")
DEFAULT_TRACE_DB = ".factory/trace.db"


def _input_path(raw: object) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise UsageError("path must be a non-empty string")
    path = Path(raw.strip()).expanduser()
    if not path.is_absolute():
        raise UsageError(f"path must be absolute (or start with ~), got {raw!r}")
    return path


def in_run_worktree(path: Path) -> bool:
    """``path`` lies under a ``.factory/worktrees/`` directory (a task run's checkout)."""
    parts = path.parts
    n = len(RUN_WORKTREE_PARTS)
    return any(parts[i : i + n] == RUN_WORKTREE_PARTS for i in range(len(parts) - n + 1))


def trace_db_of(root: Path) -> Path:
    """The trace DB of the repository at ``root`` (from ``.factory/local.yaml`` on disk)."""
    try:
        return load_local(root).trace_db_path(root)
    except (ConfigError, OSError):
        return (root / DEFAULT_TRACE_DB).resolve()


def same_file(a: Path, b: Path) -> bool:
    if os.path.realpath(a) == os.path.realpath(b):
        return True
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


@dataclass
class Examined:
    """What ``examine`` found out about a path; ``problem`` is the first refusal."""

    path: Path
    root: Path | None = None
    subdir: str | None = None
    has_commit: bool = False
    trace_db: Path | None = None
    registered: str | None = None
    problem: RepoError | None = None


def _vet(ex: Examined, state: RegistryState) -> None:
    path = ex.path
    if not path.exists():
        raise RepoError("path_not_found", f"{path} does not exist")
    if not path.is_dir():
        raise RepoError("not_a_directory", f"{path} is not a directory")
    real = path.resolve()
    if in_run_worktree(real):
        raise RepoError("run_worktree", f"{path} is a worktree of a task run, not a repository")
    layout = repo_layout(real)
    if layout is not None and layout.bare:
        raise RepoError("bare_repo", f"{path} is a bare repository without a working tree")
    if layout is None or layout.inside_git_dir:
        raise RepoError(
            "not_git", f"{path} is not in a git repository; HAIFA does not run git init"
        )
    if layout.toplevel is not None and in_run_worktree(layout.toplevel):
        raise RepoError("run_worktree", f"{path} is a worktree of a task run, not a repository")
    if layout.linked:
        main = layout.main_checkout
        hint = f"; add the main checkout {main}" if main is not None else ""
        raise RepoError(
            "linked_worktree",
            f"{path} is a linked worktree{hint}",
            data={"main_checkout": str(main) if main is not None else None},
        )
    if layout.toplevel is None:
        raise RepoError(
            "not_git", f"{path} is not in a git repository; HAIFA does not run git init"
        )
    root = layout.toplevel
    ex.root = root
    if real != root:
        ex.subdir = real.relative_to(root).as_posix() if root in real.parents else None
    for entry in state.repos:
        if same_repo(entry.path, root):
            ex.registered = entry.id
            break
    if read_git(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}") is None:
        raise RepoError("no_commits", f"{root} has no commit yet; commit something first")
    ex.has_commit = True
    ex.trace_db = trace_db_of(root)
    check_trace_db(root, state)


def check_trace_db(root: Path, state: RegistryState) -> None:
    """``trace_db_shared`` when another registered repository uses the trace DB of ``root``."""
    db = trace_db_of(root)
    for entry in state.repos:
        other = Path(entry.path)
        if not other.is_dir() or same_repo(other, root):
            continue
        if same_file(trace_db_of(other), db):
            raise RepoError(
                "trace_db_shared",
                f"the trace DB {db} is already used by the registered repository {entry.id}",
                data={"repo": entry.id},
            )


def examine(raw: object, state: RegistryState) -> Examined:
    """Look at the path ``raw`` (body ``path``); ``UsageError`` for a bad value."""
    ex = Examined(_input_path(raw))
    try:
        _vet(ex, state)
    except RepoError as exc:
        ex.problem = exc
    return ex


def vet_path(raw: object, state: RegistryState) -> Examined:
    """``examine`` that raises the first refusal."""
    ex = examine(raw, state)
    if ex.problem is not None:
        raise ex.problem
    return ex


def register_repo(registry: Registry, raw: object) -> tuple[RepoEntry, bool, list[str]]:
    """Vet the path ``raw`` and register its repository: ``(entry, created, warnings)``.

    The validation of ``POST /api/repos`` and ``factory obs --repo``; raises
    ``UsageError`` for a bad value and ``RepoError`` for a refused folder.
    """
    state, warnings = registry.snapshot()
    examined = vet_path(raw, state)
    root = examined.root
    assert root is not None
    entry, created = registry.add(root, check=lambda current: check_trace_db(root, current))
    return entry, created, warnings


def add_repo(
    registry: Registry, raw: object, environ: Mapping[str, str] | None = None
) -> tuple[RepoEntry, bool, JsonDict, list[str]]:
    """The dashboard's "add": register the repository and install factory in one go.

    The install comes from the library (else the seed) and replaces an existing
    ``.factory/`` in one commit on base, pushed when there is a remote (see
    ``plan_init(replace=True)``). A refused install leaves no new registry entry.
    Returns ``(entry, created, install, warnings)``.
    """
    from aifactory.library.install_commit import commit_init
    from aifactory.library.store import LibraryStoreError

    entry, created, warnings = register_repo(registry, raw)
    try:
        result = commit_init(Path(entry.path), replace=True, environ=environ)
    except LibraryStoreError as exc:
        if created:
            registry.remove(entry.id)
        raise RepoError(exc.code, exc.message, data=dict(exc.data or {})) from exc
    install = {
        "committed": result.committed,
        "commit": result.commit,
        "pushed": result.pushed,
        "files": [f.to_json() for f in result.plan.publish.files],
    }
    return entry, created, install, [*warnings, *result.warnings]


def remove_repo(
    registry: Registry,
    repo_id: str,
    *,
    export: list[tuple[str, str]],
    uninstall: bool = True,
    environ: Mapping[str, str] | None = None,
) -> tuple[RepoEntry, JsonDict | None]:
    """The dashboard's "remove": export chosen items, delete ``.factory/``, unregister."""
    from aifactory.library.store import LibraryStoreError
    from aifactory.library.uninstall import uninstall as remove_factory

    entry = registry.snapshot()[0].by_id(repo_id)
    if entry is None:
        raise RepoError("unknown_repo", f"no registered repository {repo_id!r}")
    done: JsonDict | None = None
    if uninstall and (Path(entry.path) / ".git").exists():
        try:
            done = remove_factory(Path(entry.path), export=export, environ=environ).to_json()
        except LibraryStoreError as exc:
            raise RepoError(exc.code, exc.message, data=dict(exc.data or {})) from exc
    removed = registry.remove(repo_id)
    if removed is None:
        raise RepoError("unknown_repo", f"no registered repository {repo_id!r}")
    return removed, done


def _problem_json(exc: RepoError) -> JsonDict:
    return {"code": exc.code, "message": exc.message, **exc.data}


def _factory(root: Path) -> RepoState | None:
    try:
        return repo_state(root)
    except (ConfigError, OSError):
        return None


def inspect_repo(raw: object, state: RegistryState) -> JsonDict:
    """What adding the folder ``raw`` would do; reads only (``POST /api/repos/inspect``)."""
    ex = examine(raw, state)
    root = ex.root
    branch: str | None = None
    remote: JsonDict | None = None
    factory: JsonDict | None = None
    if root is not None and ex.has_commit:
        branch = read_git(root, "rev-parse", "--abbrev-ref", "HEAD") or None
        url = read_git(root, "remote", "get-url", "origin")
        remote = {"name": "origin", "url": url} if url else None
        found = _factory(root)
        factory = found.to_json() if found is not None else None
    return {
        "path": str(ex.path),
        "root": str(root) if root is not None else None,
        "subdir": ex.subdir,
        "registered": ex.registered,
        "addable": ex.problem is None,
        "problem": _problem_json(ex.problem) if ex.problem is not None else None,
        "branch": branch,
        "remote": remote,
        "trace_db": str(ex.trace_db) if ex.trace_db is not None else None,
        "factory": factory,
    }


def repo_status(entry: RepoEntry) -> JsonDict:
    """One item of ``GET /api/repos``: the entry, its ``status`` and ``factory`` state."""
    item: JsonDict = {**entry.to_json(), "status": "ok", "factory": None}
    root = Path(entry.path)
    if not root.is_dir():
        item["status"] = "missing"
        return item
    layout = repo_layout(root)
    if layout is None or layout.toplevel is None:
        item["status"] = "not_git"
        return item
    factory = _factory(layout.toplevel)
    item["factory"] = factory.to_json() if factory is not None else None
    if factory is None:
        item["status"] = "not_git"
        return item
    state = factory.state
    if state == "none" or (state == "unsupported" and not factory.config_in_base):
        item["status"] = "not_installed"
    elif state == "uncommitted":
        item["status"] = "uncommitted"
    else:
        data, _warnings = web_settings.config_status(layout.toplevel)
        if data is not None and data.get("clean") is False:
            item["status"] = "uncommitted"
    return item


@dataclass
class RepoContext:
    """One repository the API serves: its registry ``id`` (None for one repo), root, hub.

    ``factory`` holds the Factory tab's lock (one apply or pull at a time) and check cache.
    """

    id: str | None
    root: Path
    live: LiveHub = field(repr=False)
    factory: FactoryState = field(default_factory=FactoryState, repr=False)


class RepoContexts:
    """The contexts of the registered repositories, created on first use."""

    def __init__(self, registry: Registry, live_interval: float) -> None:
        self.registry = registry
        self.live_interval = live_interval
        self._contexts: dict[str, tuple[str, RepoContext]] = {}

    async def _prune(self, state: RegistryState) -> None:
        for repo_id, (path, ctx) in list(self._contexts.items()):
            entry = state.by_id(repo_id)
            if entry is None or entry.path != path:
                del self._contexts[repo_id]
                await ctx.live.aclose()

    async def resolve(self, repo_id: str) -> RepoContext:
        """The context of ``repo_id``; ``unknown_repo`` or ``repo_missing`` (HTTP 404)."""
        state, _warnings = self.registry.snapshot()
        await self._prune(state)
        entry = state.by_id(repo_id)
        if entry is None:
            raise RepoError("unknown_repo", f"no registered repository {repo_id!r}")
        root = Path(entry.path)
        if not root.is_dir():
            raise RepoError(
                "repo_missing",
                f"the folder {entry.path} of repository {repo_id!r} is missing",
                data={"repo": repo_id, "path": entry.path},
            )
        known = self._contexts.get(repo_id)
        if known is not None:
            return known[1]
        ctx = RepoContext(
            repo_id, root.resolve(), LiveHub(root.resolve(), interval=self.live_interval)
        )
        self._contexts[repo_id] = (entry.path, ctx)
        return ctx

    async def drop(self, repo_id: str) -> None:
        """Close the hub of ``repo_id`` and forget its context."""
        known = self._contexts.pop(repo_id, None)
        if known is not None:
            await known[1].live.aclose()

    async def aclose(self) -> None:
        for repo_id in list(self._contexts):
            await self.drop(repo_id)
