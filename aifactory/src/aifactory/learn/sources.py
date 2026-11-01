"""Where ``factory learn`` reads objections from: every repo the dashboard knows.

The repos are the entries of the dashboard registry (``dashboard.yaml`` in the HAIFA
home). A repo whose folder is gone or that has no trace DB is skipped with a warning;
one broken repo never fails the whole read.

Objections read through ``collect_all`` carry the registry id in ``repo`` and a key
prefixed with it (``<repo_id>:<envelope_id>#<n>``), unique across all repos. Keys without
the prefix (stored by lessons made from one repo) belong to the repo the lesson came from.

The factory repo is the registered repo holding the HAIFA source: the one named by
``HAIFA_FACTORY_REPO`` (a registry id), else the one whose ``aifactory/pyproject.toml``
names the project ``aifactory``.
"""

from __future__ import annotations

import os
import sqlite3
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path

from aifactory import database
from aifactory.config.settings import load_local
from aifactory.home import haifa_home
from aifactory.learn.collect import Objection, collect
from aifactory.web.registry import ID_RE, Registry, RepoEntry, same_repo

FACTORY_REPO_ENV = "HAIFA_FACTORY_REPO"
FACTORY_PROJECT = "aifactory"


@dataclass(frozen=True)
class SourceRepo:
    """A registered repo and its trace DB."""

    id: str
    name: str
    path: Path
    trace_db: Path


def _entries(home: Path | None) -> tuple[tuple[RepoEntry, ...], list[str]]:
    state, warnings = Registry(home or haifa_home()).snapshot()
    return state.repos, list(warnings)


def _source(entry: RepoEntry) -> tuple[SourceRepo | None, str | None]:
    """The repo of ``entry``, or the warning why it is skipped."""
    root = Path(entry.path)
    if not root.is_dir():
        return None, f"{entry.id}: {root} does not exist; skipped"
    try:
        trace_db = load_local(root).trace_db_path(root)
    except Exception as exc:  # a broken local.yaml or database config of one repo
        return None, f"{entry.id}: cannot locate the trace DB: {exc}; skipped"
    if not database.available(trace_db):
        return None, f"{entry.id}: no trace DB at {trace_db}; skipped"
    return SourceRepo(id=entry.id, name=entry.name, path=root, trace_db=trace_db), None


def registered_repos(home: Path | None = None) -> tuple[list[SourceRepo], list[str]]:
    """The registered repos with a trace DB, and warnings for the skipped ones."""
    entries, warnings = _entries(home)
    repos: list[SourceRepo] = []
    for entry in entries:
        repo, warning = _source(entry)
        if repo is not None:
            repos.append(repo)
        if warning:
            warnings.append(warning)
    return repos, warnings


def _is_factory(root: Path) -> bool:
    try:
        with (root / "aifactory" / "pyproject.toml").open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    project = data.get("project")
    return isinstance(project, dict) and project.get("name") == FACTORY_PROJECT


def factory_repo(home: Path | None = None) -> RepoEntry | None:
    """The registered repo holding the HAIFA source, None when there is none.

    ``HAIFA_FACTORY_REPO`` (a registry id) decides when set; an id that is not registered
    gives None.
    """
    entries, _warnings = _entries(home)
    wanted = os.environ.get(FACTORY_REPO_ENV, "").strip()
    if wanted:
        return next((e for e in entries if e.id == wanted), None)
    return next((e for e in entries if _is_factory(Path(e.path))), None)


def _read(repo: SourceRepo, since: str | None) -> list[Objection]:
    return [
        replace(o, key=f"{repo.id}:{o.key}", repo=repo.id) for o in collect(repo.trace_db, since)
    ]


def collect_all(
    since: str | None = None, home: Path | None = None
) -> tuple[list[Objection], list[str]]:
    """The objections of every registered repo (keys ``<repo_id>:...``), and warnings."""
    repos, warnings = registered_repos(home)
    found: list[Objection] = []
    for repo in repos:
        try:
            found.extend(_read(repo, since))
        except (sqlite3.Error, OSError) as exc:
            warnings.append(f"{repo.id}: cannot read the trace DB: {exc}; skipped")
    return found, warnings


def _split(key: str, known: set[str]) -> tuple[str | None, str]:
    """``(repo_id, key)`` of a prefixed key, ``(None, key)`` of one without a prefix."""
    head, sep, rest = key.partition(":")
    if sep and ID_RE.match(head) and head in known:
        return head, rest
    return None, key


def resolve_objections(
    keys: Iterable[str], origin_repo: Path, home: Path | None = None
) -> list[Objection]:
    """The objections of ``keys`` in their order; unknown repos and keys are left out.

    A key without a prefix belongs to ``origin_repo`` (a repo root) and is returned as
    is; a prefixed key belongs to the registered repo of its prefix.
    """
    entries, _warnings = _entries(home)
    known = {e.id for e in entries}
    by_repo: dict[str | None, dict[str, Objection]] = {}

    def objections(repo_id: str | None) -> dict[str, Objection]:
        if repo_id in by_repo:
            return by_repo[repo_id]
        found: dict[str, Objection] = {}
        try:
            if repo_id is None:
                origin = next((e.id for e in entries if same_repo(e.path, origin_repo)), "")
                trace_db = load_local(origin_repo).trace_db_path(origin_repo)
                found = {o.key: replace(o, repo=origin) for o in collect(trace_db)}
            else:
                entry = next(e for e in entries if e.id == repo_id)
                repo, _warning = _source(entry)
                if repo is not None:
                    found = {o.key: o for o in _read(repo, None)}
        except Exception:  # an unreadable repo resolves to nothing
            found = {}
        by_repo[repo_id] = found
        return found

    resolved: list[Objection] = []
    for key in keys:
        repo_id, _rest = _split(key, known)
        objection = objections(repo_id).get(key)
        if objection is not None:
            resolved.append(objection)
    return resolved
