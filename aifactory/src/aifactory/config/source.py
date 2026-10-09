"""Where configuration is read from: the working tree, or a commit's tree.

``CommitSource`` reads blobs straight from the object database
(``git ls-tree`` / ``git cat-file``): no checkout, no worktree, no index change.
``.factory/local.yaml`` is machine-local and is never read from a commit.

Every call runs with ``GIT_OPTIONAL_LOCKS=0``: reading the configuration (``git diff``
in ``config status``, ``factory check``, the dashboard) must not refresh the index and
take ``index.lock`` while task runs commit in the same repository.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from aifactory.config.errors import ConfigError, ConfigIssue

FACTORY_DIR = ".factory"
LOCAL_FILE = ".factory/local.yaml"
# git reads only: no optional locks (index refresh) during reads
READ_ENV = {"GIT_OPTIONAL_LOCKS": "0"}


class GitError(ConfigError):
    """A git command failed."""


def git(root: Path, *args: str) -> str:
    """Run ``git *args`` in ``root`` and return stdout; raise ``GitError`` on failure."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            env={**os.environ, **READ_ENV},
        )
    except OSError as exc:
        raise GitError([ConfigIssue(str(root), f"git {' '.join(args)}: {exc}")]) from exc
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f"exit status {proc.returncode}"
        raise GitError([ConfigIssue(str(root), f"git {' '.join(args)}: {detail}")])
    return proc.stdout


_TREES: dict[tuple[str, str], tuple[frozenset[str], dict[str, str]]] = {}
_BLOBS: dict[tuple[str, str], dict[str, bytes]] = {}
_CACHE_LIMIT = 64


def _remember(cache: dict[tuple[str, str], Any], key: tuple[str, str], value: Any) -> None:
    if len(cache) >= _CACHE_LIMIT:
        cache.pop(next(iter(cache)))
    cache[key] = value


def _commit_tree(root: Path, sha: str) -> tuple[frozenset[str], dict[str, str]]:
    """Paths under ``.factory/`` in commit ``sha`` and the blob id of each file."""
    key = (str(root), sha)
    cached = _TREES.get(key)
    if cached is not None:
        return cached
    out = git(root, "ls-tree", "-r", "-z", sha, "--", FACTORY_DIR)
    blobs: dict[str, str] = {}
    paths: list[str] = []
    for record in out.split("\0"):
        if not record:
            continue
        meta, _, path = record.partition("\t")
        paths.append(path)
        parts = meta.split(" ")
        if len(parts) == 3 and parts[1] == "blob":
            blobs[path] = parts[2]
    value = (frozenset(paths), blobs)
    _remember(_TREES, key, value)
    return value


def _commit_blobs(root: Path, sha: str, oids: dict[str, str]) -> dict[str, bytes]:
    key = (str(root), sha)
    cached = _BLOBS.get(key)
    if cached is None:
        cached = _read_blobs(root, oids)
        _remember(_BLOBS, key, cached)
    return cached


def _read_blobs(root: Path, oids: dict[str, str]) -> dict[str, bytes]:
    """Contents of the blobs ``path -> oid`` read with a single ``git cat-file --batch``."""
    order = list(oids.items())
    request = "".join(f"{oid}\n" for _, oid in order).encode()
    try:
        proc = subprocess.run(
            ["git", "cat-file", "--batch"],
            cwd=root,
            input=request,
            capture_output=True,
            check=False,
            env={**os.environ, **READ_ENV},
        )
    except OSError as exc:
        raise GitError([ConfigIssue(str(root), f"git cat-file --batch: {exc}")]) from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip() or f"exit status {proc.returncode}"
        raise GitError([ConfigIssue(str(root), f"git cat-file --batch: {detail}")])
    data, pos, contents = proc.stdout, 0, {}
    for path, oid in order:
        end = data.index(b"\n", pos)
        header = data[pos:end].split(b" ")
        if len(header) != 3 or header[1] != b"blob":
            problem = f"git cat-file --batch: {oid} ({path}) is not a blob"
            raise GitError([ConfigIssue(str(root), problem)])
        size = int(header[2])
        contents[path] = data[end + 1 : end + 1 + size]
        pos = end + 1 + size + 1
    return contents


def git_try(root: Path, *args: str) -> str | None:
    """stdout of a read-only git call, or None when it fails."""
    try:
        return git(root, *args)
    except GitError:
        return None


def repo_root(start: Path) -> Path:
    """The top level of the git repository containing ``start``."""
    try:
        out = git(start, "rev-parse", "--show-toplevel")
    except GitError as exc:
        raise ConfigError([ConfigIssue(str(start), "not a git repository")]) from exc
    return Path(out.strip()).resolve()


def resolve_commit(root: Path, ref: str) -> str:
    """The full sha of the commit ``ref`` names."""
    try:
        out = git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    except GitError as exc:
        raise ConfigError(
            [ConfigIssue(str(root), f"base '{ref}' does not resolve to a commit in {root}")]
        ) from exc
    return out.strip()


class ConfigSource(Protocol):
    def read_text(self, rel: str) -> str | None:
        """The file's text, or None when it does not exist."""
        ...

    def list_files(self, rel_dir: str) -> list[str]:
        """Repo-relative posix paths of every file under ``rel_dir``, sorted."""
        ...

    def label(self, rel: str) -> str:
        """How error messages name ``rel``."""
        ...

    @property
    def name(self) -> str:
        """How the source as a whole is named."""
        ...


def _under(rel_dir: str) -> str:
    return rel_dir.rstrip("/") + "/"


class WorktreeSource:
    """Reads files from the working tree on disk."""

    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def name(self) -> str:
        return str(self.root)

    def read_text(self, rel: str) -> str | None:
        path = self.root / rel
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def list_files(self, rel_dir: str) -> list[str]:
        base = self.root / rel_dir
        if not base.is_dir():
            return []
        return sorted(p.relative_to(self.root).as_posix() for p in base.rglob("*") if p.is_file())

    def label(self, rel: str) -> str:
        return str(self.root / rel)


class CommitSource:
    """Reads files from the tree of commit ``sha`` (named ``ref``) without a checkout."""

    def __init__(self, root: Path, ref: str, sha: str) -> None:
        self.root = root
        self.ref = ref
        self.sha = sha
        self._paths, self._oids = _commit_tree(root, sha)
        # Every blob of .factory/ is read with one `git cat-file --batch` on first use and kept
        # per commit (a commit never changes): a run loads the config of its base many times.
        self._contents: dict[str, bytes] | None = None

    @property
    def name(self) -> str:
        return f"{self.ref}@{self.sha[:7]}"

    def read_text(self, rel: str) -> str | None:
        if rel == LOCAL_FILE:
            raise ValueError("local.yaml is never read from a commit")
        if rel not in self._paths:
            return None
        if rel not in self._oids:
            return git(self.root, "cat-file", "blob", f"{self.sha}:{rel}")
        if self._contents is None:
            self._contents = _commit_blobs(self.root, self.sha, self._oids)
        return self._contents[rel].decode("utf-8")

    def list_files(self, rel_dir: str) -> list[str]:
        prefix = _under(rel_dir)
        return sorted(p for p in self._paths if p.startswith(prefix))

    def label(self, rel: str) -> str:
        return f"{self.name}:{rel}"


class OverlaySource:
    """Files of a plan laid over another source (or over nothing): the plan wins.

    ``factory init`` and ``factory config add|set|remove`` validate the configuration
    base (or the working tree) will have once the planned files are written, without
    writing them anywhere. An overlay value of None is a deleted file.
    """

    def __init__(self, base: ConfigSource | None, overlay: Mapping[str, bytes | None]) -> None:
        self.base = base
        self.overlay = dict(overlay)

    @property
    def name(self) -> str:
        return f"{self.base.name if self.base else 'empty'}+plan"

    def read_text(self, rel: str) -> str | None:
        if rel == LOCAL_FILE:
            raise ValueError("local.yaml is never read from a plan")
        if rel in self.overlay:
            data = self.overlay[rel]
            return None if data is None else data.decode("utf-8")
        return self.base.read_text(rel) if self.base is not None else None

    def list_files(self, rel_dir: str) -> list[str]:
        prefix = _under(rel_dir)
        found = {p for p, data in self.overlay.items() if p.startswith(prefix) and data is not None}
        if self.base is not None:
            found.update(
                p for p in self.base.list_files(rel_dir) if self.overlay.get(p, b"") is not None
            )
        return sorted(found)

    def label(self, rel: str) -> str:
        return f"{self.name}:{rel}"
