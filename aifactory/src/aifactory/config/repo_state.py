"""The state of a repo for HAIFA, read from its base commit.

The state is decided by the first matching row, read from the tree of ``base``:

===============  =====================================================================
``installed``    ``.factory/manifest.yaml``
``unsupported``  ``.factory/config.yaml`` or ``.factory/agents.yaml`` without a manifest,
                 or an sssf installation in ``adws/``
``uncommitted``  configuration only in the working tree (runs do not see it)
``none``         none of these
===============  =====================================================================

HAIFA does not take over a repo in state ``unsupported``: it neither converts nor runs
a configuration it did not install. A repo gets into HAIFA only through ``factory init``.

Reading only: ``git rev-parse``, ``git ls-tree`` and ``git cat-file`` with
``GIT_OPTIONAL_LOCKS=0`` (``aifactory.config.source.git``); no fetch, no index refresh
and no command that runs hooks. The working tree is looked at on the file system only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from aifactory.config.errors import ConfigError
from aifactory.config.manifest import MANIFEST_FILE, Manifest, parse_manifest
from aifactory.config.run import worktree_base
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
CONFIG_FILES = (".factory/config.yaml", ".factory/agents.yaml")
WORKING_TREE_FILES = (MANIFEST_FILE, *CONFIG_FILES)


@dataclass(frozen=True)
class RepoState:
    """Where the repo stands; ``action`` is what to run next (None when nothing).

    ``config_in_base`` is true when factory configuration is committed in base: always
    for ``installed``, and for ``unsupported`` with ``.factory/config.yaml`` or
    ``.factory/agents.yaml``. It is not part of :meth:`to_json`.
    """

    repo: str
    base: str
    commit: str | None
    state: RepoStateName
    config_in_base: bool
    manifest: Manifest | None = None
    manifest_error: str | None = None

    @property
    def action(self) -> RepoAction | None:
        return STATE_ACTIONS[self.state]

    @property
    def onboarding(self) -> dict[str, Any] | None:
        """The ``onboarding`` block of the manifest in base (only ``installed``)."""
        if self.manifest is None or self.manifest.onboarding is None:
            return None
        return self.manifest.onboarding.model_dump(mode="json")

    @property
    def library(self) -> dict[str, Any] | None:
        """The ``library`` block of the manifest in base (only ``installed``)."""
        if self.manifest is None or self.manifest.library is None:
            return None
        return self.manifest.library.model_dump(mode="json")

    def to_json(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "base": self.base,
            "commit": self.commit,
            "state": self.state,
            "action": self.action,
            "onboarding": self.onboarding,
            "library": self.library,
            "manifest_error": self.manifest_error,
        }


def _base_paths(root: Path, sha: str) -> list[str]:
    """Entries directly under ``.factory/`` and ``adws/``."""
    out = git(root, "ls-tree", "-z", "--name-only", sha, "--", f"{FACTORY_DIR}/", f"{SSSF_DIR}/")
    return [p for p in out.split("\0") if p]


def _working_tree_config(root: Path) -> bool:
    return any((root / rel).is_file() for rel in WORKING_TREE_FILES)


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
    manifest: Manifest | None = None
    manifest_error: str | None = None
    state: RepoStateName
    config_in_base = False
    if MANIFEST_FILE in paths and sha is not None:
        state = "installed"
        config_in_base = True
        label = f"{ref}@{sha[:7]}:{MANIFEST_FILE}"
        try:
            text = git(root, "cat-file", "blob", f"{sha}:{MANIFEST_FILE}")
            manifest = parse_manifest(text, label)
        except ConfigError as exc:
            manifest_error = "; ".join(f"{i.path}: {i.message}" for i in exc.issues) or str(exc)
    elif any(rel in paths for rel in CONFIG_FILES):
        state = "unsupported"
        config_in_base = True
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
        config_in_base=config_in_base,
        manifest=manifest,
        manifest_error=manifest_error,
    )
