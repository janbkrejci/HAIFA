"""The configuration a run uses: shared files from the ``base`` commit, local.yaml from disk."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aifactory.config.errors import ConfigError, ConfigIssue
from aifactory.config.loader import FactoryConfig, load_config
from aifactory.config.settings import CONFIG_FILE, LocalSettings, load_local_checked
from aifactory.config.source import CommitSource, WorktreeSource, repo_root, resolve_commit
from aifactory.config.status import ConfigChange, change_warnings, config_changes

DEFAULT_BASE = "main"


@dataclass(frozen=True)
class RunConfig:
    base: str
    commit: str
    config: FactoryConfig
    local: LocalSettings
    changes: tuple[ConfigChange, ...]
    warnings: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "commit": self.commit,
            "source": self.config.source,
            "digest": self.config.digest,
            "agents": [agent.name for agent in self.config.agents.agents],
            "roles": self.config.roles.known_steps(),
            "workflows": sorted(self.config.workflows),
            "prompts": list(self.config.prompts),
            "settings": self.config.settings.model_dump(mode="json"),
            "local": {"trace_db": self.local.trace_db},
            "changes": [change.to_dict() for change in self.changes],
            "warnings": list(self.warnings),
        }


def worktree_base(root: Path) -> str:
    """The ``base`` key of the working tree's config.yaml, or ``main``.

    Only this key is read from the working tree: it says where to read the rest
    from. Other problems in the file are ignored here.
    """
    source = WorktreeSource(root)
    try:
        text = source.read_text(CONFIG_FILE)
    except OSError:
        return DEFAULT_BASE
    if text is None:
        return DEFAULT_BASE
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return DEFAULT_BASE
    if isinstance(data, dict) and isinstance(data.get("base"), str) and data["base"].strip():
        return str(data["base"]).strip()
    return DEFAULT_BASE


def load_run_config(root: Path, base: str | None = None) -> RunConfig:
    """Load the configuration for a run from the tree of the ``base`` commit.

    Two runs started from the same commit get the same configuration, however
    the working tree changes in between. Uncommitted shared-config changes are
    returned as ``warnings``.
    """
    root = repo_root(root)
    name = base.strip() if base else worktree_base(root)
    if not name:
        raise ConfigError([ConfigIssue(str(root), "base must not be empty")])
    sha = resolve_commit(root, name)
    config = load_config(CommitSource(root, name, sha))
    local, local_warnings = load_local_checked(root)
    changes = config_changes(root, sha)
    warnings = change_warnings(changes, name, sha)
    warnings.extend(local_warnings)
    if config.settings.base != name:
        warnings.append(f"committed base is '{config.settings.base}' but the run uses '{name}'")
    return RunConfig(
        base=name,
        commit=sha,
        config=config,
        local=local,
        changes=tuple(changes),
        warnings=tuple(warnings),
    )
