"""Publish a commit to ``base``: commit without a checkout, push first, then move base.

The commit is built on the sha of ``base`` in a throwaway index (``commit-tree``), so
the operator's checkout, index and other staged or unstaged work stay as they are.

Direct target with a remote: the remote base is fetched first. A remote that moved on
is a blocker (``base_behind``: run ``factory config pull``; ``base_diverged``: fix it by
hand). The commit is pushed without force; a rejected push (``push_failed``) changes
nothing in the repository but an unreachable object. Only after the push succeeded is
the local base fast-forwarded, under the trace DB's lock file and only when no run
with a live process is in progress (a run reads base when it starts). Paths whose
working-tree content already equals the plan are staged just before the move, so the
checkout on base comes out clean. When the move fails after a successful push, the
result carries a warning and nothing is rolled back (``factory config pull`` catches
up later). Without a remote there is only the commit and the move.

PR target: the commit goes to a new branch ``<prefix><n>``, which is pushed and gets a
pull request through the ``GitProvider``; base and the checkout are not touched.

``factory init --commit`` installs factory through the same path (``plan_contents`` builds
its plan from bytes in memory; ``materialize`` writes the new files to the checkout of base
only when base moves; it has no store when the repo has no trace DB yet). Blockers may name
the command that removes them (``Blocker.fix``).
"""

from __future__ import annotations

import contextlib
import difflib
import hashlib
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from aifactory.config.settings import ProjectSettings
from aifactory.providers import git
from aifactory.providers.base import GitProvider, ProviderError, PullRequest

if TYPE_CHECKING:
    from aifactory.run.store import TaskRunRow, TaskRunStore

DIRECT, PR = "direct", "pr"
Action = Literal["create", "modify", "delete"]
_READ_ENV = {"GIT_OPTIONAL_LOCKS": "0"}


def _file_mode(path: Path, base_mode: str | None = None) -> str:
    if sys.platform == "win32":
        # no exec bit on Windows (os.access X_OK is true for every file): keep the mode
        # the path has in base, as git does with core.fileMode=false
        return "100755" if base_mode == "100755" else "100644"
    return "100755" if os.access(path, os.X_OK) else "100644"


def _text(content: bytes | None) -> str | None:
    if content is None:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


@dataclass(frozen=True)
class PlannedFile:
    """One path of the plan: its state in base and the content it gets."""

    path: str
    action: Action
    old_mode: str | None  # None = not in base
    old_blob: str | None
    mode: str | None  # None = delete
    content: bytes | None
    old_content: bytes | None = field(default=None, repr=False)

    def diff(self) -> str:
        old, new = _text(self.old_content or b""), _text(self.content or b"")
        if old is None or new is None:
            return f"Binary files a/{self.path} and b/{self.path} differ\n"
        lines = difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile="/dev/null" if self.action == "create" else f"a/{self.path}",
            tofile="/dev/null" if self.action == "delete" else f"b/{self.path}",
        )
        return "".join(line if line.endswith("\n") else line + "\n" for line in lines)

    def to_json(self) -> dict[str, Any]:
        text = _text(self.content)
        return {
            "path": self.path,
            "action": self.action,
            "old_blob": self.old_blob,
            "mode": self.mode,
            "diff": self.diff(),
            "content": text,
            "binary": self.content is not None and text is None,
        }


@dataclass(frozen=True)
class Blocker:
    code: str
    message: str
    fix: str | None = None  # the command that removes the blocker, when there is one

    def to_json(self) -> dict[str, str]:
        out = {"code": self.code, "message": self.message}
        if self.fix is not None:
            out["fix"] = self.fix
        return out


@dataclass(frozen=True)
class PublishPlan:
    base: str
    base_sha: str
    target: str  # DIRECT | PR
    files: tuple[PlannedFile, ...]
    blockers: tuple[Blocker, ...]
    digest: str

    def to_json(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "base_sha": self.base_sha,
            "target": self.target,
            "digest": self.digest,
            "files": [f.to_json() for f in self.files],
            "blockers": [b.to_json() for b in self.blockers],
        }


def plan_digest(base: str, base_sha: str, files: Sequence[PlannedFile]) -> str:
    """sha256 over base, its sha and (path, blob in base, new content) of every file.

    The target and the commit message are not part of it: the same change reviewed
    once may be committed directly or as a PR, with any message.
    """
    h = hashlib.sha256(b"aifactory-publish-v1\0")
    h.update(base.encode() + b"\0" + base_sha.encode() + b"\0")
    for f in sorted(files, key=lambda f: f.path):
        h.update(f.path.encode() + b"\0" + (f.old_blob or "").encode() + b"\0")
        if f.content is None:
            h.update(b"D\0")
        else:
            h.update(b"F" + str(len(f.content)).encode() + b"\0" + f.content)
    return h.hexdigest()


def plan_files(root: Path, base_sha: str, paths: Iterable[str]) -> list[PlannedFile]:
    """The planned change of each path: working-tree bytes against the blob in `base_sha`."""
    files: list[PlannedFile] = []
    for path in sorted(set(paths)):
        old = git.blob_at(root, base_sha, path)
        disk = root / path
        content = disk.read_bytes() if disk.is_file() else None
        mode = _file_mode(disk, old[0] if old else None) if content is not None else None
        if old is None and content is None:
            continue
        if old is not None and content is not None:
            if mode == old[0] and git.hash_blob(root, content, write=False) == old[1]:
                continue
        action: Action = "create" if old is None else "delete" if content is None else "modify"
        files.append(
            PlannedFile(
                path=path,
                action=action,
                old_mode=old[0] if old else None,
                old_blob=old[1] if old else None,
                mode=mode,
                content=content,
                old_content=git.read_blob(root, old[1]) if old else None,
            )
        )
    return files


def plan_contents(root: Path, base_sha: str, contents: Mapping[str, bytes]) -> list[PlannedFile]:
    """The planned change of each path to the given bytes (mode 100644) against `base_sha`.

    Paths whose blob in base already has these bytes are left out.
    """
    files: list[PlannedFile] = []
    for path in sorted(contents):
        content = contents[path]
        old = git.blob_at(root, base_sha, path)
        if old is not None and old[0] == "100644":
            if git.hash_blob(root, content, write=False) == old[1]:
                continue
        files.append(
            PlannedFile(
                path=path,
                action="create" if old is None else "modify",
                old_mode=old[0] if old else None,
                old_blob=old[1] if old else None,
                mode="100644",
                content=content,
                old_content=git.read_blob(root, old[1]) if old else None,
            )
        )
    return files


def remote_state(
    root: Path, remote: str, base: str, base_sha: str
) -> tuple[list[Blocker], list[str]]:
    """Fetch the remote base and compare it with `base_sha` (raises ``fetch_failed``)."""
    git.fetch(root, remote, base)
    return compare_remote(root, remote, base, base_sha, git.remote_tip(root, remote, base))


def compare_remote(
    root: Path, remote: str, base: str, base_sha: str, theirs: str | None
) -> tuple[list[Blocker], list[str]]:
    """Compare the fetched remote base `theirs` with `base_sha` (no fetch)."""
    if theirs is None or theirs == base_sha:
        return [], []
    if git.is_ancestor(root, base_sha, theirs):
        n = git.count_commits(root, base_sha, theirs)
        msg = f"{remote}/{base} is {n} commit(s) ahead of {base}; run factory config pull"
        return [Blocker("base_behind", msg)], []
    if git.is_ancestor(root, theirs, base_sha):
        n = git.count_commits(root, theirs, base_sha)
        return [], [
            f"{base} is {n} commit(s) ahead of {remote}/{base}; "
            "they are pushed together with this commit"
        ]
    msg = f"{base} and {remote}/{base} have diverged; reconcile them by hand"
    return [Blocker("base_diverged", msg)], []


def direct_blockers(
    root: Path,
    *,
    remote: str,
    base: str,
    base_sha: str,
    store: TaskRunStore | None,
    check_remote: bool,
) -> tuple[list[Blocker], list[str]]:
    """Blockers of a direct commit to base: ``not_on_base``, ``run_in_progress`` and,
    with `check_remote` and a remote, ``base_behind``/``base_diverged`` (raises
    ``fetch_failed``). Without a store no run can be in progress."""
    from aifactory.run import gitops

    blockers: list[Blocker] = []
    warnings: list[str] = []
    head = gitops.symbolic_head(root)
    if head != f"refs/heads/{base}":
        current = head.removeprefix("refs/heads/") if head else "a detached HEAD"
        blockers.append(
            Blocker("not_on_base", f"main checkout is on {current}, not {base}; use --pr")
        )
    running = run_blocker(store) if store is not None else None
    if running is not None:
        blockers.append(running)
    if check_remote and git.has_remote(root, remote):
        found, notes = remote_state(root, remote, base, base_sha)
        blockers += found
        warnings += notes
    return blockers, warnings


def _run_message(row: TaskRunRow) -> str:
    return f"run {row.run_id} of {row.task_id} (pid {row.pid}) is running"


def run_blocker(store: TaskRunStore) -> Blocker | None:
    """``run_in_progress`` when a run with a live process is in progress."""
    live = store.live_runs()
    if not live:
        return None
    return Blocker("run_in_progress", f"{_run_message(live[0])}; wait for it or stop it")


@dataclass(frozen=True)
class PublishResult:
    commit: str
    pushed: bool
    advanced: bool
    branch: str | None = None
    pr: PullRequest | None = None
    warnings: tuple[str, ...] = ()


def _changes(root: Path, files: Sequence[PlannedFile]) -> list[git.TreeChange]:
    out: list[git.TreeChange] = []
    for f in files:
        if f.content is None:
            out.append((f.path, None, None))
        else:
            out.append((f.path, f.mode, git.hash_blob(root, f.content)))
    return out


def _prune_dirs(checkout: Path, folder: Path) -> None:
    """Remove `folder` and its parents while they are empty, never the checkout root."""
    root = checkout.resolve()
    current = folder.resolve()
    while current != root and root in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _stage_matching(
    checkout: Path, files: Sequence[PlannedFile], warnings: list[str], *, materialize: bool = False
) -> None:
    """Stage planned paths whose working-tree state already equals the plan; nothing else.

    With `materialize`, a planned file that is absent on disk, or still has its content
    in base, first gets the planned content written; a planned deletion whose file still
    has its content in base is deleted (empty folders go with it).
    """
    add: list[str] = []
    remove: list[str] = []
    for f in files:
        disk = checkout / f.path
        if materialize and f.content is not None:
            absent = not disk.exists() and not disk.is_symlink()
            unchanged = (
                f.old_content is not None and disk.is_file() and disk.read_bytes() == f.old_content
            )
            if absent or unchanged:
                disk.parent.mkdir(parents=True, exist_ok=True)
                disk.write_bytes(f.content)
                disk.chmod(0o755 if f.mode == "100755" else 0o644)  # git add stages the mode
        if materialize and f.content is None and disk.is_file() and not disk.is_symlink():
            if f.old_content is not None and disk.read_bytes() == f.old_content:
                disk.unlink()
                _prune_dirs(checkout, disk.parent)
        if f.content is None:
            if disk.exists() or disk.is_symlink():
                warnings.append(f"{f.path} changed after the plan; it stays uncommitted")
            else:
                remove.append(f.path)
        elif disk.is_file() and disk.read_bytes() == f.content:
            add.append(f.path)
        else:
            warnings.append(f"{f.path} changed after the plan; it stays uncommitted")
    if add:
        git.git(checkout, "add", "--", *add)
    if remove:
        git.git(checkout, "update-index", "--force-remove", "--", *remove)


def _advance(
    root: Path,
    base: str,
    sha: str,
    old: str,
    files: Sequence[PlannedFile],
    store: TaskRunStore | None,
    *,
    materialize: bool = False,
    command: str = "config commit",
) -> list[str]:
    """Fast-forward `base` from `old` to `sha` under the trace DB lock file; return warnings.

    Without a store (no trace DB) there is no lock and no run to wait for.
    """
    warnings: list[str] = []
    with store.serialized() if store is not None else contextlib.nullcontext():
        live = store.live_runs_locked() if store is not None else []
        if live:
            return [f"{base} not advanced: {_run_message(live[0])}; run factory config pull later"]
        current = git.rev_parse(root, f"refs/heads/{base}")
        if current != old:
            return [f"{base} not advanced: it moved meanwhile ({(current or '-')[:7]})"]
        where = git.checked_out_in(root, base)
        if where is not None:
            _stage_matching(where, files, warnings, materialize=materialize)
        git.git(root, "update-ref", f"refs/heads/{base}", sha, old)
        from aifactory.run import basemoves

        basemoves.record(root, f"refs/heads/{base}", old, sha, checkout=where, command=command)
    return warnings


def publish_direct(
    root: Path,
    *,
    settings: ProjectSettings,
    plan: PublishPlan,
    message: str,
    store: TaskRunStore | None,
    materialize: bool = False,
    command: str = "config commit",
) -> PublishResult:
    """Commit `plan` on base, push it (when a remote exists), then fast-forward base.

    The caller checked that the plan has no blockers. Raises ``commit_failed``,
    ``base_moved`` or ``push_failed``; in each case base and the checkout are unchanged.
    With `materialize` the planned files missing in the checkout of base are written to it
    when base moves (``factory init``: nothing reaches the working tree before the push).
    """
    base, remote = plan.base, settings.remote
    sha = git.commit_tree_with(root, plan.base_sha, _changes(root, plan.files), message)
    pushed = False
    if git.has_remote(root, remote):
        if git.rev_parse(root, f"refs/heads/{base}") != plan.base_sha:
            raise ProviderError("base_moved", f"{base} moved since the plan; nothing pushed")
        git.push_ref(root, remote, sha, base)
        pushed = True
    try:
        warnings = _advance(
            root,
            base,
            sha,
            plan.base_sha,
            plan.files,
            store,
            materialize=materialize,
            command=command,
        )
    except Exception as exc:  # after a push nothing is rolled back, whatever failed
        warnings = [f"{base} not advanced: {exc}"]
    advanced = git.rev_parse(root, f"refs/heads/{base}") == sha
    if not advanced:
        hint = "run factory config pull" if pushed else f"the commit is {sha}"
        warnings.append(f"{base} stays at {plan.base_sha[:7]}; {hint}")
    return PublishResult(sha, pushed, advanced, warnings=tuple(warnings))


def publish_pr(
    root: Path,
    *,
    provider: GitProvider,
    settings: ProjectSettings,
    plan: PublishPlan,
    message: str,
    body: str,
    prefix: str,
    branch: str | None = None,
    reuse_plan: bool = False,
) -> PublishResult:
    """Commit `plan` on base to a new branch ``<prefix><n>`` (or `branch`), push it and open
    a PR. A `branch` that already exists locally is ``commit_failed``. With
    `reuse_plan`, an implicit branch is identified by the digest and an existing PR is adopted."""
    sha = git.commit_tree_with(root, plan.base_sha, _changes(root, plan.files), message)
    if reuse_plan and branch is None:
        return _publish_plan_pr(root, provider, settings, plan, sha, message, body, prefix)
    if branch is None:
        branch = git.next_numbered_branch(root, settings.remote, prefix)
    try:
        git.git(root, "update-ref", f"refs/heads/{branch}", sha, "")
    except RuntimeError as exc:
        raise ProviderError("commit_failed", str(exc)) from exc
    try:
        provider.push(root, branch)
    except ProviderError:
        git.git_ok(root, "update-ref", "-d", f"refs/heads/{branch}", sha)
        raise
    pushed = git.has_remote(root, settings.remote)
    title = message.strip().splitlines()[0] if message.strip() else branch
    pr = provider.create_pr(branch, title, body)
    return PublishResult(sha, pushed, False, branch=branch, pr=pr)


def _publish_plan_pr(
    root: Path,
    provider: GitProvider,
    settings: ProjectSettings,
    plan: PublishPlan,
    candidate: str,
    message: str,
    body: str,
    prefix: str,
) -> PublishResult:
    """Reuse the branch identified by the plan, including an interrupted PR creation.

    Check the parent and entire tree before adoption; never overwrite an edited branch.
    The digest includes base and contents, but not commit timestamps or the message.
    """
    branch = f"{prefix}plan-{plan.digest}"
    ref = f"refs/heads/{branch}"
    local = git.rev_parse(root, ref)
    remote = git.has_remote(root, settings.remote)
    remote_exists = git.remote_branch_exists(root, settings.remote, branch) if remote else False
    if remote_exists is None:
        raise ProviderError("fetch_failed", f"cannot inspect {settings.remote}/{branch}")
    tip = local
    if remote_exists:
        git.fetch(root, settings.remote, branch)
        tip = git.rev_parse(root, "FETCH_HEAD")
        if local is not None and local != tip:
            raise ProviderError("plan_changed", f"{branch} differs locally and on the remote")
    if tip is not None:
        parents = git.git(root, "rev-list", "--parents", "-n", "1", tip).split()[1:]
        if parents != [plan.base_sha] or git.rev_parse(root, f"{tip}^{{tree}}") != git.rev_parse(
            root, f"{candidate}^{{tree}}"
        ):
            raise ProviderError("plan_changed", f"the published branch {branch} was changed")
    else:
        tip = candidate
    created = local is None
    if created:
        git.git(root, "update-ref", ref, tip, "")
    if not remote_exists:
        try:
            provider.push(root, branch)
        except ProviderError:
            if created:
                git.git_ok(root, "update-ref", "-d", ref, tip)
            raise
    title = message.strip().splitlines()[0] if message.strip() else branch
    pr = provider.find_open_pr(branch)
    if pr is None:
        pr = provider.create_pr(branch, title, body)
    return PublishResult(tip, remote, False, branch=branch, pr=pr)


@dataclass(frozen=True)
class PullResult:
    base: str
    remote: str
    before: str
    after: str
    updated: bool
    warnings: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "remote": self.remote,
            "before": self.before,
            "after": self.after,
            "updated": self.updated,
        }


def _dirty(checkout: Path) -> bool:
    proc = git.run_bytes(checkout, ["status", "--porcelain", "--untracked-files=no"], env=_READ_ENV)
    return proc.returncode != 0 or bool(proc.stdout.strip())


def plan_pull_base(root: Path, *, settings: ProjectSettings, store: TaskRunStore) -> dict[str, Any]:
    """Fetch and review a fast-forward without moving a checkout or local branch."""
    base, remote = settings.base, settings.remote
    blockers: list[Blocker] = []
    ours = git.rev_parse(root, f"refs/heads/{base}") or ""
    theirs = ours
    if not ours:
        blockers.append(Blocker("unknown_base", f"base {base!r} does not exist"))
    elif not git.has_remote(root, remote):
        blockers.append(Blocker("no_remote", f"remote {remote!r} is not configured"))
    else:
        git.fetch(root, remote, base)
        theirs = git.remote_tip(root, remote, base) or ours
        if theirs != ours and git.is_ancestor(root, theirs, ours):
            theirs = ours
        elif theirs != ours and not git.is_ancestor(root, ours, theirs):
            blockers.append(Blocker("base_diverged", f"{base} and {remote}/{base} have diverged"))
        where = git.checked_out_in(root, base)
        if where is not None and _dirty(where):
            blockers.append(Blocker("dirty_base", f"{base} has uncommitted changes"))
    with store.serialized():
        live = store.live_runs_locked()
        if live:
            blockers.append(Blocker("run_in_progress", f"{len(live)} live run(s); wait for them"))
    files: list[PlannedFile] = []
    if ours and theirs != ours:
        proc = git.run_bytes(root, ["diff", "--name-only", "-z", ours, theirs], env=_READ_ENV)
        if proc.returncode:
            raise ProviderError("pull_failed", "cannot read base diff")
        for raw in proc.stdout.split(b"\0"):
            if not raw:
                continue
            path = raw.decode("utf-8")
            old, new = git.blob_at(root, ours, path), git.blob_at(root, theirs, path)
            files.append(
                PlannedFile(
                    path,
                    "create" if old is None else "delete" if new is None else "modify",
                    old[0] if old else None,
                    old[1] if old else None,
                    new[0] if new else None,
                    git.read_blob(root, new[1]) if new else None,
                    git.read_blob(root, old[1]) if old else None,
                )
            )
    digest = hashlib.sha256(
        f"aifactory-pull-v1\0{root.resolve()}\0{base}\0{remote}\0{ours}\0{theirs}".encode()
    ).hexdigest()
    return {
        "action": "pull",
        "base": base,
        "remote": remote,
        "base_sha": ours,
        "before": ours,
        "after": theirs,
        "files": [f.to_json() for f in files],
        "blockers": [b.to_json() for b in blockers],
        "digest": digest,
    }


def pull_base(
    root: Path, *, settings: ProjectSettings, store: TaskRunStore, expect: str | None = None
) -> PullResult:
    """Fast-forward local base to the remote one, when nothing runs; else change nothing."""
    if expect is not None:
        plan = plan_pull_base(root, settings=settings, store=store)
        if plan["digest"] != expect:
            raise ProviderError("plan_changed", "base pull plan changed; review and confirm again")
        if plan["blockers"]:
            first = plan["blockers"][0]
            raise ProviderError(first["code"], first["message"])
    base, remote = settings.base, settings.remote
    if not git.has_remote(root, remote):
        raise ProviderError("no_remote", f"remote {remote!r} is not configured")
    ours = git.rev_parse(root, f"refs/heads/{base}")
    if ours is None:
        raise ProviderError("unknown_base", f"base {base!r} does not exist")
    git.fetch(root, remote, base)
    theirs = git.remote_tip(root, remote, base)
    if (
        expect is not None
        and (theirs or ours) != plan["after"]
        and not (plan["after"] == ours and theirs and git.is_ancestor(root, theirs, ours))
    ):
        raise ProviderError("plan_changed", "remote moved; review and confirm again")
    if theirs is None or theirs == ours:
        return PullResult(base, remote, ours, ours, False)
    if git.is_ancestor(root, theirs, ours):
        n = git.count_commits(root, theirs, ours)
        warning = f"{base} is {n} commit(s) ahead of {remote}/{base}; nothing to pull"
        return PullResult(base, remote, ours, ours, False, (warning,))
    if not git.is_ancestor(root, ours, theirs):
        raise ProviderError(
            "base_diverged", f"{base} and {remote}/{base} have diverged; nothing changed"
        )
    where = git.checked_out_in(root, base)
    if where is not None and _dirty(where):
        raise ProviderError(
            "dirty_base", f"{base} is checked out in {where} with uncommitted changes"
        )
    with store.serialized():
        live = store.live_runs_locked()
        if live:
            raise ProviderError(
                "run_in_progress", f"{_run_message(live[0])}; wait for it or stop it"
            )
        git.advance_branch(root, base, theirs, ours, command="config pull")
    return PullResult(base, remote, ours, theirs, True)
