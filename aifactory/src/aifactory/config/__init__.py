"""Project configuration in ``.factory/``.

Shared files (``config.yaml``, ``agents.yaml``, ``roles.yaml``, ``manifest.yaml``,
``prompts/``, ``workflows/``) are committed; a run reads them from the tree of the ``base``
commit without a checkout (``load_run_config``). ``local.yaml`` is machine-local,
never committed, and always read from the working tree (``load_local``).
"""

from aifactory.config.errors import ConfigError, ConfigIssue
from aifactory.config.loader import (
    AgentPrompts,
    FactoryConfig,
    load_config,
    load_worktree_config,
    write_prompts,
)
from aifactory.config.manifest import (
    MANIFEST_FILE,
    MANIFEST_FORMAT,
    LibraryRef,
    Manifest,
    ManifestEntry,
    ManifestItems,
    Onboarding,
    dump_manifest,
    parse_manifest,
    read_manifest,
    write_manifest,
)
from aifactory.config.run import RunConfig, load_run_config, worktree_base
from aifactory.config.settings import (
    GeneratedOutput,
    LocalSettings,
    ProjectSettings,
    check_relative_dir,
    check_timeout,
    load_local,
    load_local_checked,
    split_command,
)
from aifactory.config.source import CommitSource, WorktreeSource, repo_root, resolve_commit
from aifactory.config.status import ConfigChange, change_warnings, config_changes

__all__ = [
    "MANIFEST_FILE",
    "MANIFEST_FORMAT",
    "AgentPrompts",
    "CommitSource",
    "ConfigChange",
    "ConfigError",
    "ConfigIssue",
    "FactoryConfig",
    "GeneratedOutput",
    "LibraryRef",
    "LocalSettings",
    "Manifest",
    "ManifestEntry",
    "ManifestItems",
    "Onboarding",
    "ProjectSettings",
    "RunConfig",
    "WorktreeSource",
    "change_warnings",
    "check_relative_dir",
    "check_timeout",
    "config_changes",
    "dump_manifest",
    "load_config",
    "load_local",
    "load_local_checked",
    "load_run_config",
    "load_worktree_config",
    "parse_manifest",
    "read_manifest",
    "repo_root",
    "resolve_commit",
    "split_command",
    "worktree_base",
    "write_manifest",
    "write_prompts",
]
