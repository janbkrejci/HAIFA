"""The state of a repo for HAIFA, read from its base commit.

The state is decided by the first matching row, read from the tree of ``base``:

===============  =====================================================================
``installed``    ``.factory/config.yaml``
``unsupported``  an sssf installation in ``adws/`` without ``.factory/config.yaml``
``uncommitted``  ``.factory/config.yaml`` only in the working tree (runs do not see it)
``none``         none of these
===============  =====================================================================

HAIFA does not convert or run sssf. Agents and workflows the repo lacks are inherited
from the library (``aifactory.library.inherit``), so ``config.yaml`` is all a repo needs.

Reading only: ``git rev-parse``, ``git ls-tree`` and ``git cat-file`` with
``GIT_OPTIONAL_LOCKS=0`` (``aifactory.config.source.git``); no fetch, no index refresh
and no command that runs hooks. The working tree is looked at on the file system only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from aifactory.config.run import worktree_base
from aifactory.config.settings import CONFIG_FILE
from aifactory.config.source import git, git_try

RepoStateName = Literal["installed", "unsupported", "uncommitted", "none"]
RepoAction = Literal["init", "config_commit"]
REPO_STATES: tuple[RepoStateName, ...] = ("installed", "unsupported", "uncommitted", "none")
STATE_ACTIONS: dict[RepoStateName, RepoAction | None] = {
    "installed": None,
    "unsupported": None,
    "uncommitted": "config_commit",
    "none": "init",
}

FACTORY_DIR = ".factory"
SSSF_DIR = "adws"


@dataclass(frozen=True)
class RepoState:
    """Where the repo stands; ``action`` is what to run next (None when nothing).

    ``config_in_base`` is true for ``installed`` (``.factory/config.yaml`` in base). It is
    not part of :meth:`to_json`.
    """

    repo: str
    base: str
    commit: str | None
    state: RepoStateName
    config_in_base: bool

    @property
    def action(self) -> RepoAction | None:
        return STATE_ACTIONS[self.state]

    def to_json(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "base": self.base,
            "commit": self.commit,
            "state": self.state,
            "action": self.action,
        }


def _base_paths(root: Path, sha: str) -> list[str]:
    """Entries directly under ``.factory/`` and ``adws/``."""
    out = git(root, "ls-tree", "-z", "--name-only", sha, "--", f"{FACTORY_DIR}/", f"{SSSF_DIR}/")
    return [p for p in out.split("\0") if p]


def _working_tree_config(root: Path) -> bool:
    return (root / CONFIG_FILE).is_file()


def resolve_base(root: Path, base: str) -> str | None:
    """The sha of the commit ``base`` names, or None when it names none."""
    out = git_try(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}")
    return (out or "").strip() or None


def repo_state(root: Path, base: str | None = None) -> RepoState:
    """The state of the repo at ``root`` (its top level) from ``base``.

    ``base`` defaults to the ``base`` key of the working tree's config.yaml (``main``).
    Nothing is written: not the repo, not its index, not its refs.
    """
    ref = base if base is not None else worktree_base(root)
    sha = resolve_base(root, ref)
    paths = _base_paths(root, sha) if sha is not None else []
    has_adws = any(p.startswith(SSSF_DIR + "/") for p in paths)
    state: RepoStateName
    if CONFIG_FILE in paths:
        state = "installed"
    elif has_adws:
        state = "unsupported"
    elif _working_tree_config(root):
        state = "uncommitted"
    else:
        state = "none"
    return RepoState(
        repo=str(root),
        base=ref,
        commit=sha,
        state=state,
        config_in_base=state == "installed",
    )
