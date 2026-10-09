"""Plain git operations for the providers (ported from the prototype's ``gitops``).

Merges that must not touch the operator's checkout happen in a temporary
detached worktree; a branch is then moved with ``merge --ff-only`` where it is
checked out, or ``update-ref`` where it is not.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path

from aifactory.providers.base import ProviderError


def _run(cwd: Path, args: tuple[str, ...], input: str | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, input=input, encoding="utf-8"
    )


def git(cwd: Path, *args: str, input: str | None = None) -> str:
    result = _run(cwd, args, input)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def git_ok(cwd: Path, *args: str) -> bool:
    return _run(cwd, args, None).returncode == 0


def rev_parse(cwd: Path, ref: str) -> str | None:
    result = _run(cwd, ("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"), None)
    return result.stdout.strip() if result.returncode == 0 else None


def is_ancestor(cwd: Path, ancestor: str, descendant: str) -> bool:
    return git_ok(cwd, "merge-base", "--is-ancestor", ancestor, descendant)


def has_remote(root: Path, remote: str) -> bool:
    return git_ok(root, "remote", "get-url", remote)


def remote_branches(root: Path, remote: str, prefix: str) -> list[str] | None:
    """Branch names under `prefix` on `remote` (``git ls-remote``); None when unreachable."""
    result = _run(root, ("ls-remote", "--heads", remote, f"refs/heads/{prefix}*"), None)
    if result.returncode != 0:
        return None
    names: list[str] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2 and parts[1].startswith("refs/heads/"):
            names.append(parts[1].removeprefix("refs/heads/"))
    return names


def remote_branch_exists(root: Path, remote: str, branch: str) -> bool | None:
    """Whether `branch` exists on `remote` (``git ls-remote --heads``); None when unreachable."""
    ref = f"refs/heads/{branch}"
    result = _run(root, ("ls-remote", "--heads", remote, ref), None)
    if result.returncode != 0:
        return None
    return any(line.endswith("\t" + ref) for line in result.stdout.splitlines())


def remote_url(root: Path, remote: str) -> str | None:
    result = _run(root, ("remote", "get-url", remote), None)
    return result.stdout.strip() if result.returncode == 0 else None


# A push that fails with one of these (lowercased stderr) failed on the way, not because
# the remote refused it: it is retried. A rejected push (non-fast-forward, stale lease,
# missing rights, hook) is never retried.
TRANSIENT_PUSH_ERRORS = (
    "rpc failed",
    "http2 framing layer",
    "remote end hung up",
    "early eof",
    "timed out",
    "timeout",
    "connection reset",
    "connection refused",
    "connection closed",
    "could not resolve host",
    "unable to access",
    "network is unreachable",
    "operation too slow",
    "broken pipe",
    "the requested url returned error: 5",
    "gnutls",
    "ssl_read",
    "ssl_error",
)
REJECTED_PUSH_ERRORS = (
    "[rejected]",
    "[remote rejected]",
    "non-fast-forward",
    "stale info",
    "fetch first",
    "permission denied",
    "permission to ",
    "403",
    "authentication failed",
    "protected branch",
    "pre-receive hook declined",
)
PUSH_ATTEMPTS = 4
PUSH_DELAY = 3.0  # seconds before the 2nd attempt; doubles after every failure
_sleep: Callable[[float], None] = time.sleep  # tests replace it


def transient_push_error(stderr: str) -> bool:
    """Whether a failed push may succeed when tried again (network, HTTP2, timeout)."""
    text = stderr.lower()
    if any(marker in text for marker in REJECTED_PUSH_ERRORS):
        return False
    return any(marker in text for marker in TRANSIENT_PUSH_ERRORS)


def push(cwd: Path, remote: str, branch: str, lease: str | None = None) -> None:
    """Push `branch`; with `lease` force-push, but only if the remote branch is still `lease`.

    A transient failure (``transient_push_error``) is tried again, at most ``PUSH_ATTEMPTS``
    times with a growing pause; a rejected push fails at once with ``push_failed``.
    """
    args: tuple[str, ...] = ("push", "-u")
    if lease is not None:
        args += (f"--force-with-lease=refs/heads/{branch}:{lease}",)
    delay = PUSH_DELAY
    for attempt in range(1, PUSH_ATTEMPTS + 1):
        result = _run(cwd, (*args, remote, f"refs/heads/{branch}:refs/heads/{branch}"), None)
        if result.returncode == 0:
            return
        detail = result.stderr.strip() or "failed"
        if attempt < PUSH_ATTEMPTS and transient_push_error(detail):
            _sleep(delay)
            delay *= 2
            continue
        if attempt > 1:
            detail = f"{detail} (gave up after {attempt} attempts)"
        raise ProviderError("push_failed", f"git push {remote} {branch}: {detail}")


def fetch(root: Path, remote: str, branch: str) -> None:
    result = _run(root, ("fetch", "--quiet", remote, branch), None)
    if result.returncode != 0:
        raise ProviderError(
            "fetch_failed", f"git fetch {remote} {branch}: {result.stderr.strip() or 'failed'}"
        )


def checked_out_in(root: Path, branch: str) -> Path | None:
    """The worktree where `branch` is checked out, if any."""
    out = git(root, "worktree", "list", "--porcelain")
    current: Path | None = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            current = Path(line.removeprefix("worktree "))
        elif line == f"branch refs/heads/{branch}" and current is not None:
            return current
    return None


def advance_branch(
    root: Path, branch: str, new_sha: str, old_sha: str, *, command: str = "advance"
) -> None:
    """Move `branch` from `old_sha` forward to `new_sha` (a descendant).

    The move is recorded in the base-move journal (``run/basemoves.py``) so the
    guard of a concurrent task run does not blame its agent for it.
    """
    from aifactory.run import basemoves

    current = rev_parse(root, f"refs/heads/{branch}")
    if current != old_sha:
        raise ProviderError("base_moved", f"{branch} moved while merging ({current} != {old_sha})")
    where = checked_out_in(root, branch)
    if where is not None:
        result = _run(where, ("merge", "--ff-only", "--quiet", new_sha), None)
        if result.returncode != 0:
            raise ProviderError(
                "dirty_base",
                f"cannot fast-forward {branch} checked out in {where}: {result.stderr.strip()}",
            )
    else:
        git(root, "update-ref", f"refs/heads/{branch}", new_sha, old_sha)
    basemoves.record(
        root, f"refs/heads/{branch}", old_sha, new_sha, checkout=where, command=command
    )


def remove_worktree(root: Path, path: Path) -> bool:
    """Remove the worktree at `path`; return whether there was one."""
    if path.resolve() == Path(git(root, "rev-parse", "--show-toplevel")).resolve():
        raise ProviderError("worktree_remove_failed", f"{path} is the main checkout")
    existed = path.exists()
    if existed:
        result = _run(root, ("worktree", "remove", "--force", str(path)), None)
        if result.returncode != 0:
            raise ProviderError(
                "worktree_remove_failed", f"git worktree remove {path}: {result.stderr.strip()}"
            )
    git_ok(root, "worktree", "prune")
    return existed


@contextlib.contextmanager
def detached_worktree(root: Path, start: str) -> Iterator[Path]:
    """A throwaway worktree on `start` (detached HEAD), outside the repo."""
    parent = Path(tempfile.mkdtemp(prefix="aifactory-merge-"))
    path = parent / "wt"
    try:
        git(root, "worktree", "add", "--detach", "--quiet", str(path), start)
        yield path
    finally:
        remove_worktree(root, path)
        shutil.rmtree(parent, ignore_errors=True)


def trial_merge(root: Path, base_sha: str, branch_sha: str) -> bool:
    """Whether `branch_sha` merges into `base_sha` without conflicts."""
    with detached_worktree(root, base_sha) as wt:
        result = _run(wt, ("merge", "--no-commit", "--no-ff", branch_sha), None)
        clean = result.returncode == 0
        git_ok(wt, "merge", "--abort")
        return clean


def merge_commit(root: Path, base_sha: str, tip: str, strategy: str, subject: str) -> str:
    """Build the squash or merge commit of `tip` onto `base_sha`; raise ``conflict``."""
    with detached_worktree(root, base_sha) as wt:
        if strategy == "squash":
            result = _run(wt, ("merge", "--squash", tip), None)
        else:
            result = _run(wt, ("merge", "--no-ff", "-m", subject, tip), None)
        if result.returncode != 0:
            git_ok(wt, "merge", "--abort")
            git_ok(wt, "reset", "--hard", "--quiet")
            raise ProviderError(
                "conflict", f"{tip[:7]} does not merge cleanly: {result.stdout.strip()}"
            )
        if strategy == "squash":
            git(wt, "commit", "--quiet", "-m", subject)
        return git(wt, "rev-parse", "HEAD")


# -- commits without a checkout (see ``providers.publish``) --

# (path, mode, blob); mode and blob None = delete the path
TreeChange = tuple[str, str | None, str | None]


def run_bytes(
    cwd: Path,
    args: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        input=input_bytes,
        env={**os.environ, **(env or {})},
    )


def _checked(proc: subprocess.CompletedProcess[bytes], code: str, what: str) -> bytes:
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip() or "failed"
        raise ProviderError(code, f"git {what}: {detail}")
    return proc.stdout


def hash_blob(root: Path, content: bytes, *, write: bool = True) -> str:
    """The blob sha of `content` (``git hash-object --stdin``); with `write` it is stored."""
    args = ["hash-object", "--stdin"] + (["-w"] if write else [])
    out = _checked(run_bytes(root, args, input_bytes=content), "commit_failed", "hash-object")
    return out.decode().strip()


def blob_at(root: Path, commit: str, path: str) -> tuple[str, str] | None:
    """(mode, blob sha) of `path` in `commit`, or None when it is not a file there."""
    out = _checked(
        run_bytes(root, ["ls-tree", "-z", commit, "--", path]), "commit_failed", "ls-tree"
    )
    for entry in out.decode("utf-8", "surrogateescape").split("\0"):
        header, _, name = entry.partition("\t")
        parts = header.split()
        if name == path and len(parts) == 3 and parts[1] == "blob":
            return parts[0], parts[2]
    return None


def read_blob(root: Path, blob: str) -> bytes:
    return _checked(run_bytes(root, ["cat-file", "blob", blob]), "commit_failed", "cat-file")


def commit_tree_with(
    root: Path, parent: str | None, changes: Sequence[TreeChange], message: str
) -> str:
    """A commit on `parent` with `changes` applied; neither the index nor HEAD is touched.

    The tree is built in a throwaway index (``GIT_INDEX_FILE``) and committed with
    ``commit-tree``; the commit is not on any branch until the caller moves one. Without
    `parent` the commit is a root commit on an empty tree.
    """
    tmp = Path(tempfile.mkdtemp(prefix="aifactory-index-"))
    env = {"GIT_INDEX_FILE": str(tmp / "index")}
    try:
        start = [parent] if parent is not None else ["--empty"]
        _checked(run_bytes(root, ["read-tree", *start], env=env), "commit_failed", "read-tree")
        for path, mode, blob in changes:
            if blob is None or mode is None:
                args = ["update-index", "--force-remove", "--", path]
            else:
                args = ["update-index", "--add", "--cacheinfo", f"{mode},{blob},{path}"]
            _checked(run_bytes(root, args, env=env), "commit_failed", "update-index")
        tree = _checked(run_bytes(root, ["write-tree"], env=env), "commit_failed", "write-tree")
        out = _checked(
            run_bytes(
                root,
                [
                    "commit-tree",
                    tree.decode().strip(),
                    *(["-p", parent] if parent is not None else []),
                    "-F",
                    "-",
                ],
                env=env,
                input_bytes=message.encode("utf-8"),
            ),
            "commit_failed",
            "commit-tree",
        )
        return out.decode().strip()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def push_ref(cwd: Path, remote: str, sha: str, branch: str) -> None:
    """Push `sha` to `branch` on `remote`: no ``-u``, never forced (a non-fast-forward fails)."""
    result = _run(cwd, ("push", "--quiet", remote, f"{sha}:refs/heads/{branch}"), None)
    if result.returncode != 0:
        raise ProviderError(
            "push_failed", f"git push {remote} {branch}: {result.stderr.strip() or 'failed'}"
        )


def remote_tip(root: Path, remote: str, branch: str) -> str | None:
    """The fetched tip of `branch` (the remote-tracking ref, else ``FETCH_HEAD``)."""
    return rev_parse(root, f"refs/remotes/{remote}/{branch}") or rev_parse(root, "FETCH_HEAD")


def count_commits(root: Path, start: str, end: str) -> int:
    """Commits reachable from `end` but not from `start`."""
    out = git(root, "rev-list", "--count", f"{start}..{end}")
    return int(out) if out.isdigit() else 0


def next_numbered_branch(root: Path, remote: str, prefix: str) -> str:
    """The first free ``<prefix><n>``: unknown locally, in remote-tracking refs and on `remote`."""
    local = git(root, "for-each-ref", "--format=%(refname:short)", f"refs/heads/{prefix}*")
    tracking = git(
        root, "for-each-ref", "--format=%(refname:short)", f"refs/remotes/{remote}/{prefix}*"
    )
    names = [*local.splitlines(), *(n.removeprefix(f"{remote}/") for n in tracking.splitlines())]
    if has_remote(root, remote):
        names += remote_branches(root, remote, prefix) or []
    highest = 0
    for name in names:
        suffix = name.strip().removeprefix(prefix)
        if name.strip().startswith(prefix) and suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"{prefix}{highest + 1}"


def redact_url(url: str) -> str:
    """`url` without user and password: ``https://u:p@host/x`` becomes ``https://host/x``.

    Only URLs with a scheme carry credentials. The ssh user (``ssh://git@host/x`` and the scp
    form ``git@host:path``) names the account ssh logs in as, not a secret, so it stays; an
    ssh password is dropped.
    """
    scheme, sep, rest = url.partition("://")
    if not sep:
        return url
    authority, slash, path = rest.partition("/")
    userinfo, at, host = authority.rpartition("@")
    if at and scheme.lower() in ("ssh", "git+ssh", "ssh+git"):
        user = userinfo.partition(":")[0]
        host = f"{user}@{host}" if user else host
    return f"{scheme}://{host}{slash}{path}"


def ls_remote_refs(cwd: Path, url: str) -> list[str] | None:
    """Every ref name on the remote at `url`; None when git cannot read it."""
    result = _run(cwd, ("ls-remote", url), None)
    if result.returncode != 0:
        return None
    return [line.split("\t", 1)[1] for line in result.stdout.splitlines() if "\t" in line]
