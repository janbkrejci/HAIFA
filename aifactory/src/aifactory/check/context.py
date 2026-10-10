"""Everything the rules of ``factory check`` read, computed lazily and only by reading.

Git calls go through ``aifactory.config.source.git`` (``GIT_OPTIONAL_LOCKS=0``), so
the check never refreshes the index nor takes ``index.lock``. The backlog of the base
commit is unpacked into a temporary directory outside the repository and removed at
once; the loaded ``Backlog`` lives in memory.

Outside a git repository (``require_repo=False``) only the machine and the library are
read: ``in_repo`` is false, ``roster`` is None and ``settings`` the defaults.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Mapping
from functools import cached_property
from pathlib import Path
from typing import Any

from aifactory.backlog import Backlog, check_backlog, load_backlog
from aifactory.backlog.model import Issue
from aifactory.check.machine import Machine
from aifactory.config.errors import ConfigError, ConfigIssue
from aifactory.config.loader import FactoryConfig, load_config
from aifactory.config.run import worktree_base
from aifactory.config.settings import CONFIG_FILE, ProjectSettings, parse_project_settings
from aifactory.config.source import CommitSource, WorktreeSource, git_try, repo_root
from aifactory.config.status import ConfigChange, config_changes
from aifactory.harness.config import SSSFConfig
from aifactory.library.remote import library_status
from aifactory.library.state import repo_items
from aifactory.library.store import LibraryStoreError
from aifactory.onboard.state import RepoState, repo_state
from aifactory.run.gitops import extract_backlog


class NotARepositoryError(Exception):
    """The folder is not inside a git repository; the check cannot run."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"{path} is not a git repository")
        self.path = path


def main_checkout(start: Path) -> Path:
    """The main checkout of the repository containing ``start`` (also from a linked worktree)."""
    try:
        root = repo_root(start)
    except ConfigError as exc:
        raise NotARepositoryError(start) from exc
    out = git_try(root, "worktree", "list", "--porcelain")
    if out:
        first = out.splitlines()[0]
        if first.startswith("worktree "):
            path = Path(first.removeprefix("worktree ")).resolve()
            if path.is_dir():
                return path
    return root


class CheckContext:
    """What the rules read; every property is computed on first use."""

    def __init__(
        self, start: Path, *, offline: bool, machine: Machine, require_repo: bool = True
    ) -> None:
        self._main: Path | None
        try:
            self._main = main_checkout(start)
        except NotARepositoryError:
            if require_repo:
                raise
            self._main = None
        self.offline = offline
        self.machine = machine

    @property
    def in_repo(self) -> bool:
        """The check runs inside a git repository (else only machine and library rules)."""
        return self._main is not None

    @property
    def main(self) -> Path:
        """The main checkout; only rules with ``needs_repo`` read it."""
        assert self._main is not None, "the check runs outside a git repository"
        return self._main

    # -- machine and library --

    @cached_property
    def environ(self) -> Mapping[str, str]:
        return self.machine.environment()

    @cached_property
    def library(self) -> dict[str, Any] | None:
        """``library_status`` without fetch, or None when there is no library."""
        try:
            return library_status(fetch=False, environ=self.environ)
        except LibraryStoreError as exc:
            if exc.code == "library_missing":
                return None
            raise

    @cached_property
    def items(self) -> list[dict[str, Any]]:
        """States of the items in base (AR23); only for an onboarded repo with a manifest."""
        if self.state.state != "onboarded" or self.state.manifest_error is not None:
            return []
        if self.commit is None:
            return []
        data = repo_items(self.main, self.base, self.environ, save_cache=False)
        return list(data["items"])

    # -- base commit --

    @cached_property
    def base(self) -> str:
        return worktree_base(self.main)

    @cached_property
    def commit(self) -> str | None:
        out = git_try(self.main, "rev-parse", "--verify", "--quiet", f"{self.base}^{{commit}}")
        if out is None:
            return None
        return out.strip() or None

    def base_file(self, rel: str) -> str | None:
        """The text of ``rel`` in the base commit, or None."""
        if self.commit is None or not self.base_has(rel):
            return None
        return git_try(self.main, "cat-file", "blob", f"{self.commit}:{rel}")

    def base_has(self, rel: str) -> bool:
        if self.commit is None:
            return False
        return git_try(self.main, "cat-file", "-e", f"{self.commit}:{rel}") is not None

    @cached_property
    def state(self) -> RepoState:
        """The onboarding state of the repo, read from base (AR30)."""
        return repo_state(self.main, self.base)

    @property
    def committed(self) -> bool:
        """The factory configuration is committed to base (onboarded or pre_library)."""
        return self.state.state in ("onboarded", "pre_library")

    @property
    def installed(self) -> bool:
        """Factory is installed, in base or only in the working tree; the rules run."""
        return self.committed or self.state.state == "working_tree"

    # -- configuration --

    @cached_property
    def _base_loaded(self) -> tuple[FactoryConfig | None, tuple[ConfigIssue, ...]]:
        if not self.committed or self.commit is None:
            return None, ()
        try:
            return load_config(CommitSource(self.main, self.base, self.commit)), ()
        except ConfigError as exc:
            return None, tuple(exc.issues)

    @property
    def base_config(self) -> FactoryConfig | None:
        return self._base_loaded[0]

    @property
    def base_issues(self) -> tuple[ConfigIssue, ...]:
        return self._base_loaded[1]

    @cached_property
    def _worktree_loaded(self) -> tuple[FactoryConfig | None, tuple[ConfigIssue, ...]]:
        if not (self.main / CONFIG_FILE).is_file():
            return None, ()
        try:
            return load_config(WorktreeSource(self.main)), ()
        except ConfigError as exc:
            return None, tuple(exc.issues)

    @property
    def worktree_config(self) -> FactoryConfig | None:
        return self._worktree_loaded[0]

    @property
    def worktree_issues(self) -> tuple[ConfigIssue, ...]:
        return self._worktree_loaded[1]

    @cached_property
    def changes(self) -> tuple[ConfigChange, ...]:
        """Uncommitted shared-config changes against the base commit (D4)."""
        if self.commit is None:
            return ()
        return tuple(config_changes(self.main, self.commit))

    @cached_property
    def settings(self) -> ProjectSettings:
        """Settings from config.yaml in base, else in the working tree, else the defaults."""
        if not self.in_repo:
            return ProjectSettings()
        if self.committed:
            text = self.base_file(CONFIG_FILE)
        else:
            text = WorktreeSource(self.main).read_text(CONFIG_FILE)
        if text is None:
            return ProjectSettings()
        settings = parse_project_settings(text, CONFIG_FILE, [])
        return settings if settings is not None else ProjectSettings()

    @cached_property
    def roster(self) -> SSSFConfig | None:
        if not self.in_repo:
            return None
        if self.base_config is not None:
            return self.base_config.agents
        if self.worktree_config is not None:
            return self.worktree_config.agents
        return None

    # -- remote --

    @cached_property
    def remotes(self) -> tuple[str, ...]:
        out = git_try(self.main, "remote") or ""
        return tuple(line.strip() for line in out.splitlines() if line.strip())

    @cached_property
    def remote_ref(self) -> str | None:
        """``refs/remotes/<remote>/<base>`` when it exists locally (no fetch)."""
        ref = f"refs/remotes/{self.settings.remote}/{self.base}"
        if self.settings.remote not in self.remotes:
            return None
        if git_try(self.main, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") is None:
            return None
        return ref

    @cached_property
    def ahead_behind(self) -> tuple[int, int] | None:
        """(ahead, behind) of the base commit against the remote-tracking ref."""
        if self.commit is None or self.remote_ref is None:
            return None
        out = git_try(
            self.main, "rev-list", "--left-right", "--count", f"{self.commit}...{self.remote_ref}"
        )
        if out is None:
            return None
        parts = out.split()
        if len(parts) != 2:
            return None
        return int(parts[0]), int(parts[1])

    # -- backlog --

    @cached_property
    def base_backlog(self) -> Backlog | None:
        """The backlog as committed in base, or None without a valid base configuration."""
        if self.base_config is None or self.commit is None:
            return None
        settings = self.base_config.settings
        with tempfile.TemporaryDirectory(prefix="factory-check-") as tmp:
            dest = Path(tmp)
            try:
                extract_backlog(self.main, self.commit, settings.backlog_patterns, dest)
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(f"cannot read the backlog from {self.base}: {exc}") from exc
            return load_backlog(dest, settings)

    @cached_property
    def backlog_issues(self) -> tuple[Issue, ...]:
        if self.base_backlog is None:
            return ()
        return tuple(check_backlog(self.base_backlog))

    @property
    def backlog_summary(self) -> dict[str, int]:
        """Number of backlog issues per code."""
        summary: dict[str, int] = {}
        for issue in self.backlog_issues:
            summary[issue.code] = summary.get(issue.code, 0) + 1
        return dict(sorted(summary.items()))
