"""Sharing the library through a git remote (AR17): clone, status, pull and push.

The remote is ``origin`` of the library repository, stored without user and password.
Pull only fast-forwards, push never forces; a dirty or diverged library is refused. Writes
with a remote (``store.import_item``) fetch first and push before the local branch moves.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from aifactory import __version__
from aifactory.library.reseed import seed_updates
from aifactory.library.store import (
    FORMAT,
    LIBRARY_FILE,
    REMOTE,
    LibraryStoreError,
    _dirty,
    _git_detail,
    _home_dir,
    behind_error,
    current_branch,
    diverged_error,
    fetch_remote,
    library_root,
    push_commit,
    read_meta,
    remote_tip,
    require_library,
    write_lock,
)
from aifactory.providers import git
from aifactory.providers.base import ProviderError

_NUMBER = re.compile(r"\d+")


def version_key(version: str) -> tuple[int, ...]:
    """Leading numbers of the dotted parts: ``0.10.2rc1`` is ``(0, 10, 2)``."""
    key: list[int] = []
    for part in version.split("."):
        match = _NUMBER.match(part)
        if match is None:
            break
        key.append(int(match.group()))
    return tuple(key)


def compatible(minimum: object, installed: str = __version__) -> bool | None:
    """Whether `installed` is at least `minimum`; None when the library sets no minimum."""
    if minimum is None or str(minimum).strip() == "":
        return None
    return version_key(installed) >= version_key(str(minimum))


def library_min_factory_version(environ: Mapping[str, str] | None = None) -> str | None:
    """``min_factory_version`` of the library's HEAD; None without a library or a minimum."""
    root = library_root(environ)
    try:
        head = require_library(root)
        minimum = read_meta(root, head).get("min_factory_version")
    except (LibraryStoreError, ProviderError, OSError, ValueError):
        return None
    if minimum is None or str(minimum).strip() == "":
        return None
    return str(minimum).strip()


def _remote(root: Path) -> str | None:
    """The stored URL of ``origin`` (not rewritten by ``insteadOf``), without credentials."""
    proc = git.run_bytes(root, ["config", "--get", f"remote.{REMOTE}.url"], env={})
    url = proc.stdout.decode("utf-8", "replace").strip()
    return git.redact_url(url) if proc.returncode == 0 and url else None


def remote_url(root: Path) -> str | None:
    """The URL of the library remote ``origin`` without user and password, or None."""
    return _remote(root)


def _require_remote(root: Path) -> str:
    url = _remote(root)
    if url is None:
        raise LibraryStoreError(
            "no_remote", f"the library at {root} has no remote {REMOTE}; it is not shared"
        )
    return url


def _last_fetch(root: Path) -> str | None:
    path = root / ".git" / "FETCH_HEAD"
    if not path.is_file():
        return None
    stamp = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    return stamp.isoformat(timespec="seconds").replace("+00:00", "Z")


def _counts(root: Path, head: str, tip: str | None) -> tuple[int, int]:
    """(ahead, behind) of `head` against `tip`; a missing tip means every commit is ahead."""
    if tip is None:
        out = git.git(root, "rev-list", "--count", head)
        return (int(out) if out.isdigit() else 0), 0
    return git.count_commits(root, tip, head), git.count_commits(root, head, tip)


# ── status ────────────────────────────────────────────────────────────────────


def library_status(fetch: bool = False, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Path, identity, remote, branch, ahead/behind, last fetch, uncommitted changes and
    whether the installed seed has versions the library's ``seed`` lacks."""
    root = library_root(environ)
    require_library(root)
    remote = _remote(root)
    if fetch:
        _require_remote(root)
        with write_lock(environ):
            fetch_remote(root)
    head = require_library(root)
    branch = current_branch(root)
    ahead: int | None = None
    behind: int | None = None
    tip: str | None = None
    if remote is not None:
        tip = remote_tip(root, branch)
        ahead, behind = _counts(root, head, tip)
    meta = read_meta(root, head)
    minimum = meta.get("min_factory_version")
    uncommitted = _dirty(root)
    updates = seed_updates(meta)
    return {
        "library": str(root),
        "id": meta.get("id"),
        "name": meta.get("name"),
        "remote": remote,
        "branch": branch,
        "head": head,
        "remote_head": tip,
        "ahead": ahead,
        "behind": behind,
        "fetched": fetch,
        "last_fetch": _last_fetch(root) if remote is not None else None,
        "dirty": bool(uncommitted),
        "uncommitted": uncommitted,
        "min_factory_version": None if minimum is None else str(minimum),
        "factory_version": __version__,
        "compatible": compatible(minimum),
        "seed_update_available": bool(updates),
        "seed_updates": updates,
    }


# ── pull and push ─────────────────────────────────────────────────────────────


def pull_library(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Fetch and fast-forward the library to the remote branch."""
    root = library_root(environ)
    require_library(root)
    remote = _require_remote(root)
    with write_lock(environ):
        head = require_library(root)
        dirty = _dirty(root)
        if dirty:
            raise LibraryStoreError(
                "library_dirty",
                f"the library at {root} has uncommitted changes: {', '.join(dirty[:5])}",
            )
        branch = current_branch(root)
        fetch_remote(root)
        tip = remote_tip(root, branch)
        after = head
        if tip is not None and tip != head and not git.is_ancestor(root, tip, head):
            if not git.is_ancestor(root, head, tip):
                ahead, behind = _counts(root, head, tip)
                raise diverged_error(branch, ahead, behind)
            proc = git.run_bytes(root, ["merge", "--ff-only", "--quiet", tip])
            if proc.returncode != 0:
                raise LibraryStoreError(
                    "pull_failed", f"cannot fast-forward the library: {_git_detail(proc)}"
                )
            after = tip
    pulled = git.count_commits(root, head, after) if after != head else 0
    return {
        "library": str(root),
        "remote": remote,
        "branch": branch,
        "before": head,
        "after": after,
        "pulled": pulled,
    }


def push_library(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Push local commits of the library to the remote branch, never forced."""
    root = library_root(environ)
    require_library(root)
    remote = _require_remote(root)
    with write_lock(environ):
        head = require_library(root)
        branch = current_branch(root)
        fetch_remote(root)
        tip = remote_tip(root, branch)
        ahead, behind = _counts(root, head, tip)
        if behind and ahead:
            raise diverged_error(branch, ahead, behind)
        if behind:
            raise behind_error(branch, behind)
        if ahead:
            push_commit(root, REMOTE, head, branch)
    return {
        "library": str(root),
        "remote": remote,
        "branch": branch,
        "head": head,
        "pushed": ahead,
    }


# ── clone ─────────────────────────────────────────────────────────────────────


def _check_meta(repo: Path, head: str) -> None:
    """``invalid_library`` unless `head` has a valid ``library.yaml``."""
    found = git.blob_at(repo, head, LIBRARY_FILE)
    if found is None:
        raise LibraryStoreError("invalid_library", f"the remote has no {LIBRARY_FILE}")
    try:
        meta = yaml.safe_load(git.read_blob(repo, found[1]))
    except yaml.YAMLError as exc:
        raise LibraryStoreError("invalid_library", f"{LIBRARY_FILE} is not YAML: {exc}") from exc
    if not isinstance(meta, dict):
        raise LibraryStoreError("invalid_library", f"{LIBRARY_FILE} is not a mapping")
    fmt = meta.get("format")
    if not isinstance(fmt, int) or isinstance(fmt, bool) or fmt < 1:
        raise LibraryStoreError("invalid_library", f"{LIBRARY_FILE} has no valid format")
    if fmt > FORMAT:
        raise LibraryStoreError(
            "invalid_library", f"{LIBRARY_FILE} has format {fmt}, this HAIFA reads {FORMAT}"
        )
    for key in ("id", "name"):
        if not isinstance(meta.get(key), str) or not meta[key].strip():
            raise LibraryStoreError("invalid_library", f"{LIBRARY_FILE} has no {key}")


def clone_library(
    url: str, branch: str | None = None, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Clone a shared library into the library path and return its status."""
    root = library_root(environ)
    shown = git.redact_url(url)

    def exists() -> bool:
        return root.exists() and (not root.is_dir() or any(root.iterdir()))

    if exists():
        raise LibraryStoreError("library_exists", f"{root} already exists")
    _home_dir(environ)
    root.parent.mkdir(parents=True, exist_ok=True)
    with write_lock(environ):
        if exists():
            raise LibraryStoreError("library_exists", f"{root} already exists")
        tmp = Path(tempfile.mkdtemp(prefix=".library-clone-", dir=root.parent))
        try:
            target = tmp / "library"
            args = ["clone", "--quiet", *(["--branch", branch] if branch else []), "--"]
            proc = git.run_bytes(tmp, [*args, url, str(target)])
            if proc.returncode != 0:
                raise LibraryStoreError(
                    "clone_failed", f"git clone {shown}: {_git_detail(proc, url)}"
                )
            head = git.rev_parse(target, "HEAD")
            if head is None:
                raise LibraryStoreError("invalid_library", f"the remote {shown} has no commit")
            _check_meta(target, head)
            git.git(target, "remote", "set-url", REMOTE, shown)
            if root.exists():
                root.rmdir()
            target.rename(root)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return library_status(environ=environ)
