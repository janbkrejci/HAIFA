"""The git calls a task run makes in the main checkout and in its worktree."""

from __future__ import annotations

import os
import subprocess
import tarfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from aifactory.run.errors import TaskRunError

BRANCH_PREFIX = "factory/"


class _Branches(Protocol):
    def branches(self, task_id: str) -> list[str]: ...


def git(root: Path, *args: str) -> str:
    """Run git in `root`; return stripped stdout, raise RuntimeError with stderr on failure."""
    proc = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8"
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


_COMMON_DIRS: dict[str, Path] = {}


def common_dir(root: Path) -> Path | None:
    """The absolute git common dir of the repo at ``root`` (None outside a repo).

    Remembered per path once found: the guard asks for it several times in every agent phase.
    """
    key = str(root)
    cached = _COMMON_DIRS.get(key)
    if cached is not None:
        return cached
    proc = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    out = proc.stdout.strip()
    if proc.returncode != 0 or not out:
        return None
    _COMMON_DIRS[key] = Path(out)
    return _COMMON_DIRS[key]


def git_ok(root: Path, *args: str) -> bool:
    proc = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8"
    )
    return proc.returncode == 0


def main_root(repo: Path) -> Path:
    """The top of the checkout that contains `repo`."""
    try:
        return Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
    except (RuntimeError, OSError) as exc:
        raise TaskRunError("invalid_config", f"{repo} is not a git repository: {exc}") from exc


def ensure_excluded(root: Path, lines: Iterable[str]) -> None:
    """Add `lines` to ``info/exclude`` of the shared ``.git`` unless present (idempotent)."""
    common = Path(git(root, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = root / common
    exclude = common / "info" / "exclude"
    existing = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    present = set(existing.splitlines())
    missing = [line for line in dict.fromkeys(lines) if line and line not in present]
    if not missing:
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    exclude.write_text(
        existing + prefix + "".join(f"{m}\n" for m in missing), encoding="utf-8", newline="\n"
    )


def next_branch(root: Path, task_id: str, store: _Branches) -> str:
    """``factory/<task-id>-<n>``, one above every existing branch and recorded run."""
    stem = f"{BRANCH_PREFIX}{task_id}-"
    names = git(root, "for-each-ref", "--format=%(refname:short)", f"refs/heads/{stem}*")
    highest = 0
    for name in [*names.splitlines(), *store.branches(task_id)]:
        name = name.strip()
        suffix = name.removeprefix(stem)
        if name.startswith(stem) and suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"{stem}{highest + 1}"


def _commit_dirs(root: Path, sha: str, pattern: str) -> list[str]:
    """Directories of commit `sha` that `pattern` names (``*`` stays inside one part)."""
    from fnmatch import fnmatchcase

    found = [""]
    for part in [p for p in pattern.strip("/").split("/") if p and p != "."]:
        nxt: list[str] = []
        for prefix in found:
            if not any(ch in part for ch in "*?["):
                path = f"{prefix}/{part}" if prefix else part
                if git_ok(root, "cat-file", "-e", f"{sha}:{path}"):
                    nxt.append(path)
                continue
            tree = f"{sha}:{prefix}" if prefix else sha
            try:
                out = git(root, "ls-tree", "-d", "-z", "--name-only", tree)
            except RuntimeError:
                continue
            for name in sorted(n for n in out.split("\0") if n):
                if name.startswith(".") and not part.startswith("."):
                    continue
                if fnmatchcase(name, part):
                    nxt.append(f"{prefix}/{name}" if prefix else name)
        found = nxt
    return found


def extract_backlog(root: Path, sha: str, backlog_dirs: str | Iterable[str], dest: Path) -> None:
    """Write the backlog roots as they are in commit `sha` under `dest` (nothing if absent).

    `backlog_dirs` is one root or the configured patterns (``ProjectSettings.backlog_patterns``).
    """
    patterns = [backlog_dirs] if isinstance(backlog_dirs, str) else list(backlog_dirs)
    rels: list[str] = []
    for pattern in patterns:
        rel = pattern.strip("/").removeprefix("./") or "."
        if rel == ".":
            matches = ["."]
        else:
            matches = _commit_dirs(root, sha, rel)
        rels.extend(m for m in matches if m not in rels)
    if not rels:
        return
    archive = dest / ".base.tar"
    with archive.open("wb") as out:
        subprocess.run(
            ["git", "archive", "--format=tar", sha, "--", *rels],
            cwd=root,
            stdout=out,
            stderr=subprocess.PIPE,
            check=True,
        )
    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter="data")
    archive.unlink()


def head(path: Path) -> str | None:
    """The commit `HEAD` points to in `path`, or None."""
    try:
        return git(path, "rev-parse", "HEAD")
    except (RuntimeError, OSError):
        return None


def symbolic_head(path: Path) -> str | None:
    """The branch `HEAD` is on in `path` (``refs/heads/...``), or None when detached."""
    try:
        return git(path, "symbolic-ref", "-q", "HEAD")
    except (RuntimeError, OSError):
        return None


def _stdout(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8"
    )
    return proc.stdout if proc.returncode == 0 else ""


def fingerprint(root: Path) -> dict[str, str]:
    """What `permissions.snapshot` records, for any checkout: numstat per tracked change,
    ``untracked`` per new file (gitignored files are invisible)."""
    prints: dict[str, str] = {}
    for line in _stdout(root, "diff", "HEAD", "--numstat").splitlines():
        fields = line.split("\t")
        if len(fields) >= 3:
            prints[fields[-1].strip()] = f"{fields[0]},{fields[1]}"
    for path in _stdout(root, "ls-files", "--others", "--exclude-standard").splitlines():
        if path.strip():
            prints[path.strip()] = "untracked"
    return prints


def pr_changed_files(
    main: Path, base: str, branch: str, base_sha: str | None = None
) -> list[str] | None:
    """The files `branch` changes since it left `base` (its pull request's diff), sorted.

    The merge base of ``refs/heads/<base>`` (else `base_sha`) and ``refs/heads/<branch>``
    in the main checkout; None when git cannot tell (a missing branch, ...). Never raises.
    """
    head_ref = f"refs/heads/{branch}"
    try:
        if git_ok(main, "rev-parse", "--verify", "-q", f"refs/heads/{base}"):
            start = git(main, "merge-base", f"refs/heads/{base}", head_ref)
        elif base_sha:
            start = git(main, "merge-base", base_sha, head_ref)
        else:
            return None
        proc = subprocess.run(
            ["git", "diff", "--name-only", "-z", start, head_ref],
            cwd=main,
            capture_output=True,
        )
    except (RuntimeError, OSError):
        return None
    if proc.returncode != 0:
        return None
    names = proc.stdout.decode("utf-8", errors="replace").split("\0")
    return sorted({n for n in names if n})


# ── read-only layout of a repository the dashboard does not know yet ────────────────

READ_ONLY_ENV = {"GIT_OPTIONAL_LOCKS": "0"}


def read_git(path: Path, *args: str) -> str | None:
    """Stripped stdout of a read-only git call in ``path``, or None when it fails.

    Runs with ``GIT_OPTIONAL_LOCKS=0`` so a read never refreshes the index. The dashboard
    calls only ``rev-parse``, ``cat-file``, ``ls-tree``, ``for-each-ref`` and
    ``remote get-url`` through it in a repository it has not registered.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=path,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, **READ_ONLY_ENV},
            encoding="utf-8",
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


@dataclass(frozen=True)
class RepoLayout:
    """Where ``path`` sits in git: bare, inside ``.git``, the git dirs and the top level."""

    bare: bool
    inside_git_dir: bool
    git_dir: Path
    common_dir: Path
    toplevel: Path | None

    @property
    def linked(self) -> bool:
        """A linked worktree (``git worktree add``): its git dir is not the common dir."""
        return self.git_dir.resolve() != self.common_dir.resolve()

    @property
    def main_checkout(self) -> Path | None:
        """The main checkout of a linked worktree when its common dir is a ``.git``."""
        common = self.common_dir.resolve()
        return common.parent if common.name == ".git" else None


def repo_layout(path: Path) -> RepoLayout | None:
    """The git layout of ``path`` (``rev-parse`` only), or None when it is in no repository."""
    out = read_git(
        path,
        "rev-parse",
        "--path-format=absolute",
        "--is-bare-repository",
        "--is-inside-git-dir",
        "--git-dir",
        "--git-common-dir",
    )
    if out is None:
        return None
    lines = out.splitlines()
    if len(lines) < 4:
        return None
    bare = lines[0].strip() == "true"
    inside = lines[1].strip() == "true"
    toplevel: Path | None = None
    if not bare and not inside:
        top = read_git(path, "rev-parse", "--show-toplevel")
        toplevel = Path(top).resolve() if top else None
    return RepoLayout(
        bare=bare,
        inside_git_dir=inside,
        git_dir=Path(lines[2].strip()),
        common_dir=Path(lines[3].strip()),
        toplevel=toplevel,
    )
