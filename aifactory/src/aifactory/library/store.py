"""The HAIFA library in the home directory (AR13, AR14, AR17).

The library is a git repository at ``$HAIFA_HOME/library`` (``$HAIFA_LIBRARY`` overrides
it). Reads use the tree of HEAD, never the working tree. Every write is a plan (files
with diffs and a digest) applied under the flock ``$HAIFA_HOME/library.lock``: a library
with uncommitted changes is refused (``library_dirty``), the commit is built on HEAD
without a checkout (``providers.git.commit_tree_with``) and the branch and working tree
are moved by a fast-forward merge. Nothing is forced and no history is rewritten.

A library with the remote ``origin`` is shared (``library.remote``): a write first fetches
it and refuses a library that is behind (``library_behind``) or diverged
(``library_diverged``), then pushes the new commit without force before it moves the local
branch, so a rejected push (``push_failed``) changes no local ref, index or file.
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from aifactory import __version__, oscompat
from aifactory.engine.role_registry import Issue
from aifactory.home import haifa_home
from aifactory.library import history as hist
from aifactory.library.load import (
    PROMPT_FILES,
    _read_file,
    _read_tree,
    check_library_item,
    load_library_item,
)
from aifactory.library.load import library_path as item_library_path
from aifactory.library.model import ITEM_TYPES, ItemType, check_name
from aifactory.library.seed import SEED_DIR, SEED_WORKFLOWS_ROOT
from aifactory.library.tree import (
    item_paths,
    item_tree_path,
    item_versions,
    read_blobs,
    read_items,
    tree_files,
)
from aifactory.providers import git
from aifactory.providers.publish import PlannedFile, plan_digest

LIBRARY_ENV = "HAIFA_LIBRARY"
LIBRARY_FILE = "library.yaml"
LOCK_FILE = "library.lock"
FORMAT = 1
BRANCH = "main"
REMOTE = "origin"
_READ_ENV = {"GIT_OPTIONAL_LOCKS": "0"}


class LibraryStoreError(Exception):
    """A library command cannot proceed; ``code`` is the ``error.code``."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        issues: Sequence[Issue] = (),
        data: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.issues = list(issues)
        self.data = data


# ── paths and lock ────────────────────────────────────────────────────────────


def library_root(environ: Mapping[str, str] | None = None) -> Path:
    """``$HAIFA_LIBRARY``, else ``$HAIFA_HOME/library``."""
    env = os.environ if environ is None else environ
    explicit = env.get(LIBRARY_ENV)
    if explicit:
        return Path(explicit).expanduser()
    return haifa_home(environ) / "library"


def _home_dir(environ: Mapping[str, str] | None) -> Path:
    path = haifa_home(environ)
    if not path.is_dir():
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    return path


@contextlib.contextmanager
def write_lock(environ: Mapping[str, str] | None = None) -> Iterator[None]:
    """Hold the flock ``$HAIFA_HOME/library.lock`` (blocks until it is free)."""
    path = _home_dir(environ) / LOCK_FILE
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        oscompat.lock(fd, blocking=True)
        try:
            yield
        finally:
            oscompat.unlock(fd)
    finally:
        os.close(fd)


# ── git state ─────────────────────────────────────────────────────────────────


def _head(root: Path) -> str | None:
    return git.rev_parse(root, "HEAD")


def require_library(root: Path) -> str:
    """The HEAD commit of the library; ``library_missing`` when there is none."""
    if not (root / ".git").exists():
        raise LibraryStoreError(
            "library_missing", f"no library at {root}; create it with factory library init"
        )
    head = _head(root)
    if head is None:
        raise LibraryStoreError("library_missing", f"the library at {root} has no commit")
    return head


def _dirty(root: Path) -> list[str]:
    proc = git.run_bytes(root, ["status", "--porcelain", "--untracked-files=all"], env=_READ_ENV)
    if proc.returncode != 0:
        return ["git status failed"]
    return [line for line in proc.stdout.decode("utf-8", "replace").splitlines() if line]


def _identity_value(cwd: Path, key: str, envs: tuple[str, str]) -> bool:
    if all(os.environ.get(e) for e in envs):
        return True
    proc = subprocess.run(
        ["git", "config", "--get", key], cwd=cwd, capture_output=True, text=True, encoding="utf-8"
    )
    return proc.returncode == 0 and bool(proc.stdout.strip())


def check_identity(cwd: Path) -> None:
    """``git_identity_missing`` without ``user.name`` and ``user.email``."""
    missing = [
        key
        for key, envs in (
            ("user.name", ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME")),
            ("user.email", ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL")),
        )
        if not _identity_value(cwd, key, envs)
    ]
    if missing:
        raise LibraryStoreError(
            "git_identity_missing",
            f"git has no {' and '.join(missing)}; set them with git config --global",
        )


# ── plans ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NewFile:
    """A file the plan writes: path from the library root, executable bit, content."""

    path: str
    executable: bool
    data: bytes


@dataclass(frozen=True)
class PlanItem:
    type: ItemType
    name: str
    version: str
    previous: str | None
    action: str  # create | update | unchanged; library seed also kept | take
    diff: tuple[PlannedFile, ...] = ()  # kept: the change the seed would make

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": self.type,
            "name": self.name,
            "version": self.version,
            "short_version": hist.short(self.version),
            "previous_version": self.previous,
            "action": self.action,
        }
        if self.action == "kept":
            data["diff"] = [f.to_json() for f in self.diff]
        return data


@dataclass(frozen=True)
class LibraryPlan:
    library: str
    head: str | None
    source: str
    items: tuple[PlanItem, ...]
    files: tuple[PlannedFile, ...]
    digest: str
    message: str

    def to_json(self) -> dict[str, Any]:
        return {
            "library": self.library,
            "head": self.head,
            "source": self.source,
            "digest": self.digest,
            "items": [i.to_json() for i in self.items],
            "files": [f.to_json() for f in self.files],
            "message": self.message,
        }


@dataclass
class WriteResult:
    plan: LibraryPlan
    dry_run: bool
    committed: bool
    commit: str | None
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            **self.plan.to_json(),
            "dry_run": self.dry_run,
            "committed": self.committed,
            "commit": self.commit,
        }


def _mode(executable: bool) -> str:
    return "100755" if executable else "100644"


def _blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _write_blobs(root: Path, contents: Sequence[bytes]) -> list[str]:
    """Store every content as a blob in one ``git hash-object -w --stdin-paths``."""
    if not contents:
        return []
    with tempfile.TemporaryDirectory(prefix="aifactory-blobs-") as tmp:
        paths = []
        for n, data in enumerate(contents):
            path = Path(tmp) / str(n)
            path.write_bytes(data)
            paths.append(str(path))
        proc = git.run_bytes(
            root,
            ["hash-object", "-w", "--no-filters", "--stdin-paths"],
            input_bytes="".join(f"{p}\n" for p in paths).encode(),
        )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip() or "failed"
        raise LibraryStoreError("commit_failed", f"git hash-object: {detail}")
    shas = proc.stdout.decode().split()
    if len(shas) != len(contents):
        raise LibraryStoreError("commit_failed", "git hash-object returned too few objects")
    return shas


def _planned(
    root: Path, head: str | None, new: Sequence[NewFile], replace: Sequence[str]
) -> list[PlannedFile]:
    """The change from HEAD to `new`; files of HEAD below `replace` not in `new` are deleted."""
    old = {f.path: f for f in tree_files(root, head, replace)} if head and replace else {}
    wanted = {f.path: f for f in new}
    blobs = read_blobs(root, (f.blob for f in old.values()))
    out: list[PlannedFile] = []
    for path in sorted(set(old) | set(wanted)):
        before, after = old.get(path), wanted.get(path)
        if after is not None and before is not None:
            if _blob_sha(after.data) == before.blob and _mode(after.executable) == before.mode:
                continue
        out.append(
            PlannedFile(
                path=path,
                action="create" if before is None else "delete" if after is None else "modify",
                old_mode=before.mode if before else None,
                old_blob=before.blob if before else None,
                mode=_mode(after.executable) if after else None,
                content=after.data if after else None,
                old_content=blobs.get(before.blob) if before else None,
            )
        )
    return out


def _commit(root: Path, plan: LibraryPlan) -> str:
    """Commit `plan` on its head without a checkout; no ref moves."""
    written = iter(_write_blobs(root, [f.content for f in plan.files if f.content is not None]))
    changes: list[git.TreeChange] = [
        (f.path, f.mode, next(written) if f.content is not None else None) for f in plan.files
    ]
    return git.commit_tree_with(root, plan.head, changes, plan.message)


def _advance(root: Path, sha: str) -> None:
    """Fast-forward the branch and working tree of the library to `sha`."""
    proc = git.run_bytes(root, ["merge", "--ff-only", "--quiet", sha])
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise LibraryStoreError(
            "commit_failed", f"cannot fast-forward the library to {sha[:12]}: {detail}"
        )


def _apply(root: Path, plan: LibraryPlan) -> str:
    """Commit `plan`, push it when the library has a remote, then fast-forward the branch."""
    sha = _commit(root, plan)
    if git.has_remote(root, REMOTE):
        push_commit(root, REMOTE, sha, current_branch(root))
    _advance(root, sha)
    return sha


# ── remote ────────────────────────────────────────────────────────────────────


def current_branch(root: Path) -> str:
    """The branch checked out in the library (``main`` when HEAD is detached)."""
    proc = git.run_bytes(root, ["symbolic-ref", "--quiet", "--short", "HEAD"], env=_READ_ENV)
    name = proc.stdout.decode("utf-8", "replace").strip()
    return name if proc.returncode == 0 and name else BRANCH


def _git_detail(proc: subprocess.CompletedProcess[bytes], url: str | None = None) -> str:
    detail = proc.stderr.decode("utf-8", "replace").strip() or "failed"
    return detail.replace(url, git.redact_url(url)) if url else detail


def fetch_remote(root: Path) -> None:
    """Fetch every branch of ``origin`` into ``refs/remotes/origin/``; ``fetch_failed``."""
    proc = git.run_bytes(
        root, ["fetch", "--quiet", REMOTE, f"+refs/heads/*:refs/remotes/{REMOTE}/*"]
    )
    if proc.returncode != 0:
        raise LibraryStoreError("fetch_failed", f"git fetch {REMOTE}: {_git_detail(proc)}")


def remote_tip(root: Path, branch: str) -> str | None:
    """The last fetched tip of `branch` on ``origin`` (None when the remote lacks it)."""
    return git.rev_parse(root, f"refs/remotes/{REMOTE}/{branch}")


def check_remote(root: Path, head: str, branch: str) -> str | None:
    """Fetch and refuse a library that is behind or diverged; the remote tip."""
    fetch_remote(root)
    tip = remote_tip(root, branch)
    if tip is None or tip == head or git.is_ancestor(root, tip, head):
        return tip
    behind = git.count_commits(root, head, tip)
    ahead = git.count_commits(root, tip, head)
    raise behind_error(branch, behind) if ahead == 0 else diverged_error(branch, ahead, behind)


def behind_error(branch: str, behind: int) -> LibraryStoreError:
    return LibraryStoreError(
        "library_behind",
        f"the library is {behind} commit(s) behind {REMOTE}/{branch}; run factory library pull",
        data={"branch": branch, "ahead": 0, "behind": behind, "fix": "factory library pull"},
    )


def diverged_error(branch: str, ahead: int, behind: int) -> LibraryStoreError:
    return LibraryStoreError(
        "library_diverged",
        f"the library and {REMOTE}/{branch} have diverged ({ahead} ahead, {behind} behind); "
        "nothing changed",
        data={"branch": branch, "ahead": ahead, "behind": behind, "fix": None},
    )


def push_commit(root: Path, remote: str, sha: str, branch: str) -> None:
    """Push `sha` to `branch` of `remote` (a name or URL) without force; ``push_failed``."""
    proc = git.run_bytes(root, ["push", "--quiet", remote, f"{sha}:refs/heads/{branch}"])
    if proc.returncode != 0:
        raise LibraryStoreError(
            "push_failed",
            f"git push {git.redact_url(remote)} {branch}: {_git_detail(proc, remote)}; "
            "the library is unchanged",
        )


def _connect_remote(root: Path, url: str, sha: str, branch: str) -> None:
    """Record ``origin`` (without credentials) and its tip `sha` after the first push."""
    git.git(root, "remote", "add", REMOTE, git.redact_url(url))
    git.git(root, "update-ref", f"refs/remotes/{REMOTE}/{branch}", sha)
    git.git(root, "config", f"branch.{branch}.remote", REMOTE)
    git.git(root, "config", f"branch.{branch}.merge", f"refs/heads/{branch}")


# ── init ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SeedItem:
    """One item of a seed: its version and its files in the library layout."""

    type: ItemType
    name: str
    version: str
    files: tuple[NewFile, ...]

    @property
    def key(self) -> str:
        return f"{self.type}/{self.name}"


def read_seed(agents_root: Path, workflows_root: Path) -> tuple[SeedItem, ...]:
    """The seed items below `agents_root`/agents and `workflows_root`/workflows, validated."""
    keys: list[tuple[ItemType, str]] = []
    agents = agents_root / "agents"
    if agents.is_dir():
        keys += [("agent", p.name) for p in sorted(agents.iterdir()) if p.is_dir()]
    workflows = workflows_root / "workflows"
    if workflows.is_dir():
        keys += [("workflow", p.stem) for p in sorted(workflows.glob("*.yaml"))]
    out: list[SeedItem] = []
    for kind, name in sorted(keys, key=lambda k: (ITEM_TYPES.index(k[0]), k[1])):
        base = agents_root if kind == "agent" else workflows_root
        item = load_library_item(base, kind, name)
        rel = item_library_path(kind, name)
        names = ["agent.yaml", *PROMPT_FILES] if kind == "agent" else [""]
        files: list[NewFile] = []
        for leaf in names:
            src = base / rel / leaf if leaf else base / rel
            path = f"{rel}/{leaf}" if leaf else rel
            files.append(NewFile(path, bool(src.stat().st_mode & stat.S_IXUSR), src.read_bytes()))
        out.append(SeedItem(kind, name, item.version, tuple(files)))
    return tuple(out)


@functools.cache
def packaged_seed() -> tuple[SeedItem, ...]:
    """The seed shipped in the package (validated once per process)."""
    return read_seed(SEED_DIR, SEED_WORKFLOWS_ROOT)


def seed_versions(seed: Sequence[SeedItem]) -> dict[str, str]:
    """``type/name`` to version of every seed item, the form of ``seed`` in library.yaml."""
    return {i.key: i.version for i in seed}


def _message(subject: str, items: Sequence[PlanItem], source: str) -> str:
    lines = [subject, ""]
    lines += [f"- {i.type}/{i.name} {i.version}" for i in items if i.action != "unchanged"]
    lines += ["", f"source: {source}"]
    return "\n".join(lines) + "\n"


def init_library(
    name: str | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    remote: str | None = None,
) -> WriteResult:
    """Create the library from the seed in one commit; with `remote`, push it there first.

    The remote must be empty (``remote_not_empty``); it is stored as ``origin`` without
    user and password. A failed push removes the new library again.
    """
    root = library_root(environ)
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise LibraryStoreError("library_exists", f"{root} already exists")
    home = _home_dir(environ)
    probe = root.parent if root.parent.is_dir() else home
    check_identity(probe)
    seed_items = packaged_seed()
    seed = seed_versions(seed_items)
    items = [PlanItem(i.type, i.name, i.version, None, "create") for i in seed_items]
    meta = {
        "format": FORMAT,
        "id": str(uuid.uuid4()),
        "name": name or "library",
        "min_factory_version": None,
        "seed": seed,
    }
    files = [
        NewFile(LIBRARY_FILE, False, yaml.safe_dump(meta, sort_keys=False).encode()),
        *(f for i in seed_items for f in i.files),
    ]
    source = f"seed of aifactory {__version__}"
    with write_lock(environ):
        if root.exists() and (not root.is_dir() or any(root.iterdir())):
            raise LibraryStoreError("library_exists", f"{root} already exists")
        if remote is not None:
            _check_empty_remote(probe, remote)
        created = not root.exists()
        root.mkdir(parents=True, exist_ok=True)
        try:
            git.git(root, "init", "--quiet")
            git.git(root, "symbolic-ref", "HEAD", f"refs/heads/{BRANCH}")
            planned = _planned(root, None, files, [])
            message = _message(f"library: init {meta['name']} from the seed", items, source)
            plan = LibraryPlan(
                str(root),
                None,
                source,
                tuple(items),
                tuple(planned),
                plan_digest("library", "", planned),
                message,
            )
            sha = _commit(root, plan)
            if remote is not None:
                push_commit(root, remote, sha, BRANCH)
                _connect_remote(root, remote, sha, BRANCH)
            _advance(root, sha)
        except BaseException:
            if created:
                shutil.rmtree(root, ignore_errors=True)
            else:
                for child in root.iterdir():
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
            raise
    return WriteResult(plan, False, True, sha)


def _check_empty_remote(cwd: Path, url: str) -> None:
    refs = git.ls_remote_refs(cwd, url)
    shown = git.redact_url(url)
    if refs is None:
        raise LibraryStoreError("fetch_failed", f"cannot read the remote {shown}")
    if refs:
        raise LibraryStoreError(
            "remote_not_empty",
            f"the remote {shown} is not empty ({len(refs)} ref(s)); "
            "use factory library clone to join it",
        )


# ── reading ───────────────────────────────────────────────────────────────────


def read_meta(root: Path, commit: str) -> dict[str, Any]:
    """``library.yaml`` of `commit` (empty when missing or invalid)."""
    found = git.blob_at(root, commit, LIBRARY_FILE)
    if found is None:
        return {}
    try:
        raw = yaml.safe_load(git.read_blob(root, found[1]))
    except yaml.YAMLError:
        return {}
    return raw if isinstance(raw, dict) else {}


def list_items(type: str | None = None, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Items of HEAD with their version and last change."""
    root = library_root(environ)
    head = require_library(root)
    keys = item_paths(tree_files(root, head))
    if type is not None:
        keys = [k for k in keys if k[0] == type]
    found = item_versions(root, head, keys)
    items: list[dict[str, Any]] = []
    for kind, name in keys:
        last = hist.changes(root, item_tree_path(kind, name), head)[:1]
        version = found[(kind, name)]
        items.append(
            {
                "type": kind,
                "name": name,
                "version": version,
                "short_version": hist.short(version),
                "commit": last[0].commit if last else None,
                "date": last[0].date if last else None,
                "author": last[0].author if last else None,
            }
        )
    meta = read_meta(root, head)
    return {"library": str(root), "head": head, "name": meta.get("name"), "items": items}


def _resolve_version(revisions: list[hist.Revision], wanted: str) -> hist.Revision:
    digits = wanted.removeprefix("sha256:").lower()
    hits = [r for r in revisions if r.version.removeprefix("sha256:").startswith(digits)]
    distinct = {r.version for r in hits}
    if len(digits) < 4 or not hits:
        raise LibraryStoreError("unknown_version", f"no version {wanted!r} in the history")
    if len(distinct) > 1:
        raise LibraryStoreError("unknown_version", f"version {wanted!r} is ambiguous")
    return hits[-1]


def _file_json(rel: str, f: Any, data: bytes) -> dict[str, Any]:
    try:
        text: str | None = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    return {
        "path": f.path.removeprefix(rel + "/") if f.path != rel else f.path.rsplit("/", 1)[-1],
        "executable": f.mode == "100755",
        "size": len(data),
        "content": text,
        "binary": text is None,
    }


def show_item(
    type: str,
    name: str,
    version: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Files of an item (at HEAD or at `version`) and its version history."""
    root = library_root(environ)
    head = require_library(root)
    if type not in ITEM_TYPES:
        raise LibraryStoreError("invalid_value", f"unknown item type {type!r}")
    kind: ItemType = type
    if not check_name(name):
        raise LibraryStoreError("unknown_item", f"no {type} {name!r} in the library")
    revisions = hist.history(root, kind, name, environ)
    commit = head
    if version is not None:
        commit = _resolve_version(revisions, version).commit
    item, issues, files = read_items(root, commit, [(kind, name)])[(kind, name)]
    if not files:
        raise LibraryStoreError("unknown_item", f"no {type} {name!r} in the library")
    blobs = read_blobs(root, (f.blob for f in files))
    rel = item_library_path(kind, name)
    current = item.version if item is not None else None
    return {
        "library": str(root),
        "type": kind,
        "name": name,
        "commit": commit,
        "version": current,
        "short_version": hist.short(current),
        "purpose": item.purpose if item is not None and kind == "agent" else None,
        "valid": item is not None and not issues,
        "issues": [i.to_dict() for i in issues],
        "files": [_file_json(rel, f, blobs[f.blob]) for f in files],
        "history": [r.to_json() for r in revisions],
    }


# ── import ────────────────────────────────────────────────────────────────────


def _under(path: Path, home: Path) -> bool:
    return path == home or home in path.parents


def _check_source(path: Path, home: Path) -> Path:
    """The real source path; ``outside_home`` when it or a symlink in it leaves home."""
    absolute = Path(os.path.abspath(path.expanduser()))
    real = absolute.resolve()
    if not _under(real, home):
        raise LibraryStoreError("outside_home", f"{path} is not under the home directory {home}")
    if not real.exists():
        raise LibraryStoreError("invalid_value", f"{path} does not exist")
    if real.is_dir():
        for dirpath, dirnames, filenames in os.walk(real, followlinks=False):
            for entry in (*dirnames, *filenames):
                candidate = Path(dirpath) / entry
                if candidate.is_symlink() and not _under(candidate.resolve(), home):
                    raise LibraryStoreError(
                        "outside_home", f"{candidate} links outside the home directory {home}"
                    )
    return real


def _default_name(path: Path, type: str) -> str:
    if type == "workflow":
        for suffix in (".yaml", ".yml"):
            if path.name.endswith(suffix):
                return path.name.removesuffix(suffix)
    return path.name


def _source_files(path: Path, kind: ItemType, name: str) -> tuple[list[NewFile], list[Issue]]:
    """The files of the item at `path` in the library layout, read without following links."""
    issues: list[Issue] = []
    rel = item_library_path(kind, name)
    base, leaf = path.parent, path.name
    if kind == "workflow":
        found = _read_file(base, leaf, issues, "missing_item")
        return ([NewFile(rel, found.executable, found.data)] if found else []), issues
    files = _read_tree(base, leaf, issues)
    if files is None:
        return [], issues
    if kind == "agent":
        allowed = {"agent.yaml", *PROMPT_FILES}
        for extra in (f for f in files if f.path not in allowed):
            issues.append(
                Issue("unexpected_file", f"an agent has only {sorted(allowed)}", extra.path)
            )
    return [NewFile(f"{rel}/{f.path}", f.executable, f.data) for f in files], issues


def _import_plan(root: Path, head: str, path: Path, kind: ItemType, name: str) -> LibraryPlan:
    new, issues = _source_files(path, kind, name)
    if issues:
        raise LibraryStoreError("invalid_item", f"{path} is not a valid {kind}", issues=issues)
    with tempfile.TemporaryDirectory(prefix="aifactory-import-") as tmp:
        for f in new:
            target = Path(tmp) / f.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f.data)
            target.chmod(0o755 if f.executable else 0o644)
        item, issues = check_library_item(Path(tmp), kind, name)
    if issues or item is None:
        raise LibraryStoreError("invalid_item", f"{path} is not a valid {kind}", issues=issues)
    rel = item_library_path(kind, name)
    spec = rel if kind == "workflow" else rel + "/"
    existed = bool(tree_files(root, head, [spec]))
    previous = item_versions(root, head, [(kind, name)])[(kind, name)]
    planned = _planned(root, head, new, [spec])
    action = "unchanged" if not planned else "update" if existed else "create"
    plan_item = PlanItem(kind, name, item.version, previous, action)
    source = str(path)
    return LibraryPlan(
        str(root),
        head,
        source,
        (plan_item,),
        tuple(planned),
        plan_digest("library", head, planned),
        _message(f"library: import {kind}/{name}", [plan_item], source),
    )


def import_item(
    source: Path,
    type: str,
    name: str | None = None,
    *,
    dry_run: bool = False,
    environ: Mapping[str, str] | None = None,
) -> WriteResult:
    """Plan the import of a folder or file under home and, without `dry_run`, commit it."""
    if type not in ITEM_TYPES:
        raise LibraryStoreError("invalid_value", f"unknown item type {type!r}")
    kind: ItemType = type
    home = Path.home().resolve()
    path = _check_source(source, home)
    item_name = name or _default_name(Path(os.path.abspath(source.expanduser())), kind)
    if not check_name(item_name):
        raise LibraryStoreError(
            "invalid_item",
            f"invalid name {item_name!r}",
            issues=[Issue("invalid_name", "names match [a-z0-9][a-z0-9-]{0,47}", item_name)],
        )
    root = library_root(environ)
    if dry_run:
        head = require_library(root)
        plan = _import_plan(root, head, path, kind, item_name)
        warnings = (
            [f"the library at {root} has uncommitted changes; the import will be refused"]
            if _dirty(root)
            else []
        )
        return WriteResult(plan, True, False, None, warnings)
    require_library(root)
    check_identity(root)
    with write_lock(environ):
        head = require_library(root)
        dirty = _dirty(root)
        if dirty:
            raise LibraryStoreError(
                "library_dirty",
                f"the library at {root} has uncommitted changes: {', '.join(dirty[:5])}",
            )
        plan = _import_plan(root, head, path, kind, item_name)
        if not plan.files:
            return WriteResult(plan, False, False, None)
        if git.has_remote(root, REMOTE):
            check_remote(root, head, current_branch(root))
        sha = _apply(root, plan)
    return WriteResult(plan, False, True, sha)


def _items_plan(
    root: Path, head: str, items: Sequence[SeedItem], source: str, subject: str
) -> LibraryPlan:
    """The plan that writes `items` (files in the library layout) on `head`."""
    issues: list[Issue] = []
    with tempfile.TemporaryDirectory(prefix="aifactory-import-") as tmp:
        for f in (f for i in items for f in i.files):
            target = Path(tmp) / f.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f.data)
            target.chmod(0o755 if f.executable else 0o644)
        for i in items:
            issues += check_library_item(Path(tmp), i.type, i.name)[1]
    if issues:
        raise LibraryStoreError("invalid_item", "an item to import is not valid", issues=issues)
    specs: list[str] = []
    plan_items: list[PlanItem] = []
    for i in items:
        rel = item_library_path(i.type, i.name)
        spec = rel if i.type == "workflow" else rel + "/"
        specs.append(spec)
        existed = bool(tree_files(root, head, [spec]))
        previous = item_versions(root, head, [(i.type, i.name)])[(i.type, i.name)]
        changed = bool(_planned(root, head, i.files, [spec]))
        action = "unchanged" if not changed else "update" if existed else "create"
        plan_items.append(PlanItem(i.type, i.name, i.version, previous, action))
    planned = _planned(root, head, [f for i in items for f in i.files], specs)
    return LibraryPlan(
        str(root),
        head,
        source,
        tuple(plan_items),
        tuple(planned),
        plan_digest("library", head, planned),
        _message(subject, plan_items, source),
    )


def import_items(
    items: Sequence[SeedItem],
    source: str,
    subject: str,
    *,
    dry_run: bool = False,
    environ: Mapping[str, str] | None = None,
    expect_head: str | None = None,
) -> WriteResult:
    """Write `items` (already in the library layout) into the library in one commit.

    The write goes like ``import_item``: ``library.lock``, ``library_dirty``, fetch and
    refusal of a library behind or diverged from its remote, commit on HEAD without a
    checkout, push without force, then fast-forward. With `expect_head`, a library whose
    HEAD moved since the plan was made is ``plan_changed`` and nothing is written.
    """
    root = library_root(environ)
    if dry_run:
        head = require_library(root)
        plan = _items_plan(root, head, items, source, subject)
        warnings = (
            [f"the library at {root} has uncommitted changes; the import will be refused"]
            if _dirty(root)
            else []
        )
        return WriteResult(plan, True, False, None, warnings)
    require_library(root)
    check_identity(root)
    with write_lock(environ):
        head = require_library(root)
        dirty = _dirty(root)
        if dirty:
            raise LibraryStoreError(
                "library_dirty",
                f"the library at {root} has uncommitted changes: {', '.join(dirty[:5])}",
            )
        if expect_head is not None and head != expect_head:
            raise LibraryStoreError(
                "plan_changed",
                f"the library HEAD moved since the plan ({expect_head[:12]} -> {head[:12]}); "
                "run --dry-run again",
            )
        plan = _items_plan(root, head, items, source, subject)
        if not plan.files:
            return WriteResult(plan, False, False, None)
        if git.has_remote(root, REMOTE):
            check_remote(root, head, current_branch(root))
        sha = _apply(root, plan)
    return WriteResult(plan, False, True, sha)
