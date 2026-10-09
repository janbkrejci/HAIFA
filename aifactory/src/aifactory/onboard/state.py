"""The onboarding state of a repo (AR30), read from its base commit.

The state is decided by the first matching row, read from the tree of ``base``:

================  ====================================================================
``onboarded``     ``.factory/manifest.yaml``
``pre_library``   ``.factory/config.yaml`` or ``.factory/agents.yaml``, no manifest
``sssf``          ``adws/adw_sssf_config/*.yaml``, no factory configuration
``working_tree``  configuration only in the working tree (runs do not see it)
``none``          none of these
================  ====================================================================

Flags: ``sssf_leftover`` (``adws/`` next to ``.factory/`` in base) and
``alternate_rosters`` (more than one YAML in ``adws/adw_sssf_config/``).

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

RepoStateName = Literal["onboarded", "pre_library", "sssf", "working_tree", "none"]
RepoAction = Literal["init", "onboard", "adopt", "config_commit"]
REPO_STATES: tuple[RepoStateName, ...] = (
    "onboarded",
    "pre_library",
    "sssf",
    "working_tree",
    "none",
)
STATE_ACTIONS: dict[RepoStateName, RepoAction] = {
    "onboarded": "adopt",
    "pre_library": "onboard",
    "sssf": "onboard",
    "working_tree": "config_commit",
    "none": "init",
}

FACTORY_DIR = ".factory"
SSSF_DIR = "adws"
SSSF_CONFIG_DIR = "adws/adw_sssf_config"
CONFIG_FILES = (".factory/config.yaml", ".factory/agents.yaml")
WORKING_TREE_FILES = (MANIFEST_FILE, *CONFIG_FILES)


@dataclass(frozen=True)
class RepoState:
    """Where the repo stands for onboarding; ``action`` is what to run next."""

    repo: str
    base: str
    commit: str | None
    state: RepoStateName
    sssf_leftover: bool
    alternate_rosters: bool
    rosters: tuple[str, ...] = ()
    manifest: Manifest | None = None
    manifest_error: str | None = None

    @property
    def action(self) -> RepoAction:
        return STATE_ACTIONS[self.state]

    @property
    def onboarding(self) -> dict[str, Any] | None:
        """The ``onboarding`` block of the manifest in base (only ``onboarded``)."""
        if self.manifest is None or self.manifest.onboarding is None:
            return None
        return self.manifest.onboarding.model_dump(mode="json")

    @property
    def library(self) -> dict[str, Any] | None:
        """The ``library`` block of the manifest in base (only ``onboarded``)."""
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
            "sssf_leftover": self.sssf_leftover,
            "alternate_rosters": self.alternate_rosters,
            "rosters": list(self.rosters),
            "onboarding": self.onboarding,
            "library": self.library,
            "manifest_error": self.manifest_error,
        }


def _is_roster(path: str) -> bool:
    prefix = SSSF_CONFIG_DIR + "/"
    if not path.startswith(prefix):
        return False
    rest = path[len(prefix) :]
    return "/" not in rest and rest.endswith(".yaml")


def _base_paths(root: Path, sha: str) -> list[str]:
    """Entries directly under ``.factory/``, ``adws/`` and ``adws/adw_sssf_config/``."""
    out = git(
        root,
        "ls-tree",
        "-z",
        "--name-only",
        sha,
        "--",
        f"{FACTORY_DIR}/",
        f"{SSSF_DIR}/",
        f"{SSSF_CONFIG_DIR}/",
    )
    return [p for p in out.split("\0") if p]


def _working_tree_config(root: Path) -> bool:
    if any((root / rel).is_file() for rel in WORKING_TREE_FILES):
        return True
    config_dir = root / SSSF_CONFIG_DIR
    return config_dir.is_dir() and any(p.is_file() for p in config_dir.glob("*.yaml"))


def resolve_base(root: Path, base: str) -> str | None:
    """The sha of the commit ``base`` names, or None when it names none."""
    out = git_try(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}")
    return (out or "").strip() or None


def repo_state(root: Path, base: str | None = None) -> RepoState:
    """The onboarding state of the repo at ``root`` (its top level) from ``base``.

    ``base`` defaults to the ``base`` key of the working tree's config.yaml (``main``).
    Nothing is written: not the repo, not its index, not its refs.
    """
    ref = base if base is not None else worktree_base(root)
    sha = resolve_base(root, ref)
    paths = _base_paths(root, sha) if sha is not None else []
    has_factory = any(p.startswith(FACTORY_DIR + "/") for p in paths)
    has_adws = any(p.startswith(SSSF_DIR + "/") for p in paths)
    rosters = tuple(sorted(p for p in paths if _is_roster(p)))
    manifest: Manifest | None = None
    manifest_error: str | None = None
    state: RepoStateName
    if MANIFEST_FILE in paths and sha is not None:
        state = "onboarded"
        label = f"{ref}@{sha[:7]}:{MANIFEST_FILE}"
        try:
            text = git(root, "cat-file", "blob", f"{sha}:{MANIFEST_FILE}")
            manifest = parse_manifest(text, label)
        except ConfigError as exc:
            manifest_error = "; ".join(f"{i.path}: {i.message}" for i in exc.issues) or str(exc)
    elif any(rel in paths for rel in CONFIG_FILES):
        state = "pre_library"
    elif rosters:
        state = "sssf"
    elif _working_tree_config(root):
        state = "working_tree"
    else:
        state = "none"
    return RepoState(
        repo=str(root),
        base=ref,
        commit=sha,
        state=state,
        sssf_leftover=has_adws and has_factory,
        alternate_rosters=len(rosters) > 1,
        rosters=rosters,
        manifest=manifest,
        manifest_error=manifest_error,
    )
