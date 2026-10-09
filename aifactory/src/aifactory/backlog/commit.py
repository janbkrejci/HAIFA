"""Commit the backlog's working-tree changes to ``base`` (``factory backlog commit``).

Task writes (``add``/``edit``/``link``) only change files under the backlog roots
(``backlog_dir`` or ``backlog_dirs``); a run reads the backlog from ``base``. This is the
one step that turns those edits into a commit: only paths under the backlog roots are
staged and committed (other staged or
unstaged changes stay as they are), and only when the main checkout is on ``base``
and the backlog is valid. With a configured ``remote`` the commit is pushed.

The move of ``base`` is recorded in the base-move journal (``run/basemoves.py``), so
a task run whose agent phase is going on meanwhile does not take it (nor the task
files it commits, journaled by ``run/mainwrites.py``) for a write of its agent.

Error codes (``TaskEditError.code``): ``invalid_config`` (2), ``missing_backlog_dir`` (2),
``backlog_invalid`` (1, ``errors()`` lists the problems), ``not_on_base`` (2),
``commit_failed`` (2), ``push_failed`` (2).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aifactory.backlog.edit import TaskEditError, load_for_edit
from aifactory.backlog.roots import is_glob, owning_root
from aifactory.backlog.validate import check_backlog
from aifactory.config import ProjectSettings
from aifactory.config.status import ConfigChange, working_tree_changes


@dataclass(frozen=True)
class BacklogCommit:
    committed: bool
    commit: str | None
    base: str
    paths: list[str]
    pushed: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "committed": self.committed,
            "commit": self.commit,
            "base": self.base,
            "paths": list(self.paths),
            "pushed": self.pushed,
        }


def _pathspecs(settings: ProjectSettings) -> list[str]:
    """Git pathspecs of every configured backlog root (wildcards stay inside one part)."""
    return [
        f":(glob){pattern}/**" if is_glob(pattern) else pattern
        for pattern in settings.backlog_patterns
    ]


def backlog_changes(root: Path, sha: str, settings: ProjectSettings) -> list[ConfigChange]:
    """Changes under the backlog roots not committed to ``sha`` (what ``commit_backlog`` takes).

    Plumbing only, nothing writes the index: the dashboard asks while runs go on.
    """
    return working_tree_changes(root, sha, _pathspecs(settings))


def _status_paths(root: Path, settings: ProjectSettings) -> tuple[list[str], list[str]]:
    """Changed paths under the backlog roots and the roots that hold them (incl. renames).

    The output is read as is: stripped, the first entry `` M <path>`` (a file edited, not
    staged) would lose its leading space and the path its first character.
    """
    from aifactory.providers import git as provider_git

    args = ["status", "--porcelain", "--untracked-files=all", "-z", "--", *_pathspecs(settings)]
    proc = provider_git.run_bytes(root, args)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise TaskEditError("commit_failed", f"git {' '.join(args)} failed: {detail}")
    entries = [e for e in proc.stdout.decode("utf-8").split("\0") if e]
    paths: list[str] = []
    roots: list[str] = []
    skip = False
    for entry in entries:
        if skip:  # the source path of a rename
            skip = False
            source_root = owning_root(entry, settings)
            if source_root is not None and source_root not in roots:
                roots.append(source_root)
            continue
        code, path = entry[:2], entry[3:]
        paths.append(path)
        owner = owning_root(path, settings)
        if owner is not None and owner not in roots:
            roots.append(owner)
        if "R" in code or "C" in code:
            skip = True
    return paths, sorted(roots)


def commit_backlog(repo: Path, message: str | None = None) -> BacklogCommit:
    """Commit every change under the backlog roots to ``base``; push it when a remote exists."""
    from aifactory.config import ConfigError, load_run_config
    from aifactory.providers import ProviderError
    from aifactory.providers import git as provider_git
    from aifactory.run import gitops
    from aifactory.run.errors import TaskRunError

    try:
        main = gitops.main_root(repo)
        rc = load_run_config(main)
    except TaskRunError as exc:
        raise TaskEditError("invalid_config", exc.message) from exc
    except ConfigError as exc:
        raise TaskEditError("invalid_config", str(exc)) from exc
    settings = rc.config.settings
    base = rc.base

    backlog = load_for_edit(main)
    issues = check_backlog(backlog)
    if issues:
        raise TaskEditError(
            "backlog_invalid",
            f"the backlog has {len(issues)} problem(s); fix them before committing",
            exit_code=1,
            issues=issues,
        )

    head = gitops.symbolic_head(main)
    current = head.removeprefix("refs/heads/") if head else "a detached HEAD"
    if head != f"refs/heads/{base}":
        raise TaskEditError(
            "not_on_base",
            f"main checkout is on {current}, not {base}; commit the backlog there",
        )

    paths, roots = _status_paths(main, settings)
    if not paths:
        return BacklogCommit(False, None, base, [], False)
    if not roots:  # `git add -A --` without a path would stage the whole checkout
        raise TaskEditError("commit_failed", f"no backlog root holds {', '.join(paths)}")

    subject = (message or "").strip() or f"backlog: {len(paths)} file(s) from factory"
    old = gitops.head(main)
    try:
        provider_git.git(main, "add", "-A", "--", *roots)
        provider_git.git(main, "commit", "-q", "-m", subject, "--", *roots)
        sha = provider_git.git(main, "rev-parse", "HEAD")
    except RuntimeError as exc:
        raise TaskEditError("commit_failed", str(exc)) from exc
    if old is not None:
        from aifactory.run import basemoves

        basemoves.record(
            main, f"refs/heads/{base}", old, sha, checkout=main, command="backlog commit"
        )

    pushed = False
    if provider_git.has_remote(main, settings.remote):
        try:
            provider_git.push(main, settings.remote, base)
        except ProviderError as exc:
            raise TaskEditError("push_failed", exc.message) from exc
        pushed = True
    return BacklogCommit(True, sha, base, paths, pushed)
