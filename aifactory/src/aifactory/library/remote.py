"""Sharing the library through a git remote (AR17): clone, status, pull and push.

The remote is ``origin`` of the library repository, stored without user and password.
``clone`` without a URL clones the default library (``share.default_library_url``).
Changes never go to the library branch of the remote directly: push and every write with a
remote (``store.import_item``) send them as a pull request (``library.share``) and the
library maintainer merges it. Pull fast-forwards; when the local library has commits the
remote lacks (sent and merged, or still waiting), pull rebases them onto the remote, which
drops the merged ones. A dirty library or a conflicting rebase is refused.
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

from aifactory import __version__, yamlload
from aifactory.library import share
from aifactory.library.reseed import seed_updates
from aifactory.library.store import (
    FORMAT,
    LIBRARY_FILE,
    REMOTE,
    LibraryStoreError,
    _check_empty_remote,
    _connect_remote,
    _dirty,
    _git_detail,
    _home_dir,
    behind_error,
    check_identity,
    current_branch,
    diverged_error,
    fetch_remote,
    init_library,
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
    pulls: list[share.Proposal] = []
    pulls_error: str | None = None
    unsent = 0
    if remote is not None:
        pulls = share.settle(root, head, tip)
        if fetch:
            pulls, pulls_error = share.refresh(root)
        unsent = len(share.unsent_commits(root, head, tip))
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
        "unsent": unsent,
        "sync_state": share.sync_state(remote, bool(uncommitted), unsent, ahead, behind),
        "pull_requests": [p.to_json() for p in pulls],
        "pull_requests_error": pulls_error,
        "default_url": share.default_library_url(environ),
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
        pulled = 0
        if tip is not None and tip != head and not git.is_ancestor(root, tip, head):
            pulled = git.count_commits(root, head, tip)
            if git.is_ancestor(root, head, tip):
                proc = git.run_bytes(root, ["merge", "--ff-only", "--quiet", tip])
                if proc.returncode != 0:
                    raise LibraryStoreError(
                        "pull_failed", f"cannot fast-forward the library: {_git_detail(proc)}"
                    )
                after = tip
            else:
                after = _rebase(root, head, tip, branch)
        pulls = share.settle(root, after, tip)
    return {
        "library": str(root),
        "remote": remote,
        "branch": branch,
        "before": head,
        "after": after,
        "pulled": pulled,
        "local": len(share.ahead_commits(root, after, tip)),
        "pull_requests": [p.to_json() for p in pulls],
    }


def _rebase(root: Path, head: str, tip: str, branch: str) -> str:
    """Replay the local commits onto the remote `tip`; commits whose change the remote has
    (a merged pull request) drop out. A conflict aborts and is ``library_diverged``."""
    check_identity(root)
    proc = git.run_bytes(
        root, ["rebase", "--quiet", "--empty=drop", tip], env={"GIT_EDITOR": "true"}
    )
    if proc.returncode != 0:
        git.run_bytes(root, ["rebase", "--abort"])
        ahead, behind = _counts(root, head, tip)
        raise diverged_error(branch, ahead, behind)
    after = git.rev_parse(root, "HEAD")
    if after is None:
        raise LibraryStoreError("pull_failed", "the library has no HEAD after the rebase")
    return after


def push_library(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Send the local commits that are in no open pull request as one pull request to
    the remote branch; never a push to that branch (``library.share``)."""
    root = library_root(environ)
    require_library(root)
    remote = _require_remote(root)
    proposal: dict[str, Any] | None = None
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
        unsent = share.unsent_commits(root, head, tip) if ahead else []
        if unsent:
            if tip is None:
                raise LibraryStoreError(
                    "push_failed", f"the remote has no branch {branch} to send a pull request to"
                )
            message = _push_message(root, unsent)
            ids = share.patch_ids(root, unsent)
            if unsent == share.ahead_commits(root, head, tip):
                sha = head
            else:
                sha = share.transplant(root, tip, unsent, message)
            proposal = share.propose(root, sha, branch, message, list(ids.values())).to_json()
    return {
        "library": str(root),
        "remote": remote,
        "branch": branch,
        "head": head,
        "pushed": len(unsent),
        "pull_request": proposal,
    }


def _push_message(root: Path, commits: list[str]) -> str:
    subjects = [git.git(root, "log", "-1", "--format=%s", c) for c in commits]
    if len(subjects) == 1:
        return git.git(root, "log", "-1", "--format=%B", commits[0]) + "\n"
    lines = [f"library: {len(subjects)} changes", "", *(f"- {s}" for s in subjects)]
    return "\n".join(lines) + "\n"


def connect_library(url: str, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Share a library that has no remote yet: push its branch to the empty remote `url`
    and record it as ``origin`` (without user and password).

    Refused with ``remote_exists`` when the library already has ``origin`` and with
    ``remote_not_empty`` when the remote has refs (join such a remote with clone).
    """
    root = library_root(environ)
    require_library(root)
    with write_lock(environ):
        head = require_library(root)
        existing = _remote(root)
        if existing is not None:
            raise LibraryStoreError(
                "remote_exists", f"the library at {root} is already shared through {existing}"
            )
        _check_empty_remote(root, url)
        branch = current_branch(root)
        push_commit(root, url, head, branch)
        _connect_remote(root, url, head, branch)
    return {
        "library": str(root),
        "remote": git.redact_url(url),
        "branch": branch,
        "head": head,
        "pushed": True,
    }


# ── clone ─────────────────────────────────────────────────────────────────────


def _check_meta(repo: Path, head: str) -> None:
    """``invalid_library`` unless `head` has a valid ``library.yaml``."""
    found = git.blob_at(repo, head, LIBRARY_FILE)
    if found is None:
        raise LibraryStoreError("invalid_library", f"the remote has no {LIBRARY_FILE}")
    try:
        meta = yamlload.safe_load(git.read_blob(repo, found[1]))
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


def clone_or_seed(
    url: str | None = None, branch: str | None = None, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Clone the library (the default one without `url`); when the clone fails (no
    network, no access), create a local library from the seed instead. An existing
    library is refused (``library_exists``) and stays unchanged. ``fallback`` and
    ``warning`` say whether the seed was used."""
    try:
        return {**clone_library(url, branch, environ), "fallback": False, "warning": None}
    except LibraryStoreError as exc:
        if exc.code not in ("clone_failed", "invalid_library"):
            raise
        reason = exc.message
    init_library(environ=environ)
    warning = (
        f"cannot clone the library ({reason}); created a local library from the seed. "
        "Clone the team library later: remove it and run factory library clone"
    )
    return {**library_status(environ=environ), "fallback": True, "warning": warning}


def clone_library(
    url: str | None = None, branch: str | None = None, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Clone a shared library (the default one without `url`) into the library path and
    return its status."""
    url = url or share.default_library_url(environ)
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
