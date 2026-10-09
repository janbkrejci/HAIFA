"""Version history of a library item (AR15).

``git log -- <item path>`` lists the commits that touched the item; the version of the
item in each of them is its content hash there. A commit's version never changes, so it
is kept in ``$HAIFA_HOME/cache/library/<type>/<name>.json`` (``{commit: version}``); a
deleted cache is computed again.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aifactory.home import haifa_home
from aifactory.library.model import ItemType
from aifactory.library.tree import item_tree_path, item_versions
from aifactory.providers.git import run_bytes

_SEP = "\x1f"


def short(version: str | None) -> str | None:
    """The first 8 hex digits of a version."""
    return None if version is None else version.removeprefix("sha256:")[:8]


@dataclass(frozen=True)
class Change:
    """One commit that touched an item."""

    commit: str
    date: str
    author: str


@dataclass(frozen=True)
class Revision:
    """One version of an item in the history: the commit where it appeared."""

    n: int
    version: str
    commit: str
    date: str
    author: str

    def to_json(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "version": self.version,
            "short_version": short(self.version),
            "commit": self.commit,
            "date": self.date,
            "author": self.author,
        }


def cache_dir(environ: Mapping[str, str] | None = None) -> Path:
    return haifa_home(environ) / "cache" / "library"


def changes(root: Path, path: str, rev: str = "HEAD") -> list[Change]:
    """Commits that touched `path`, newest first."""
    proc = run_bytes(
        root,
        ["log", f"--format=%H{_SEP}%aI{_SEP}%an <%ae>", rev, "--", path],
        env={"GIT_OPTIONAL_LOCKS": "0"},
    )
    if proc.returncode != 0:
        return []
    out: list[Change] = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split(_SEP)
        if len(parts) == 3:
            out.append(Change(*parts))
    return out


def _cache_file(type: ItemType, name: str, environ: Mapping[str, str] | None) -> Path:
    return cache_dir(environ) / type / f"{name}.json"


def _load(path: Path) -> dict[str, str | None]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    commits = raw.get("commits") if isinstance(raw, dict) else None
    if not isinstance(commits, dict):
        return {}
    return {str(k): (v if isinstance(v, str) else None) for k, v in commits.items()}


def _save(path: Path, commits: Mapping[str, str | None]) -> None:
    with contextlib.suppress(OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"commits": dict(commits)}, handle, indent=1, sort_keys=True)
        os.replace(tmp, path)


def versions(
    root: Path,
    type: ItemType,
    name: str,
    commits: list[str],
    environ: Mapping[str, str] | None = None,
    save: bool = True,
) -> dict[str, str | None]:
    """The item's version in each commit (None: missing or unreadable there).

    ``save=False`` reads the cache but never writes it (``factory check``)."""
    path = _cache_file(type, name, environ)
    known = _load(path)
    missing = [c for c in commits if c not in known]
    for commit in missing:
        known[commit] = item_versions(root, commit, [(type, name)])[(type, name)]
    if missing and save:
        _save(path, known)
    return {c: known.get(c) for c in commits}


def history(
    root: Path,
    type: ItemType,
    name: str,
    environ: Mapping[str, str] | None = None,
    save: bool = True,
) -> list[Revision]:
    """Versions of the item, oldest first; a version repeats only after another one."""
    log = list(reversed(changes(root, item_tree_path(type, name))))
    found = versions(root, type, name, [c.commit for c in log], environ, save)
    out: list[Revision] = []
    for change in log:
        version = found.get(change.commit)
        if version is None or (out and out[-1].version == version):
            continue
        out.append(Revision(len(out) + 1, version, change.commit, change.date, change.author))
    return out
