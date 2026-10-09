"""Git hosting providers: ``local`` (a branch is the PR), ``github`` (``gh``), ``azure`` (``az``).

The provider is chosen by ``git_provider`` in ``.factory/config.yaml``.
"""

from __future__ import annotations

from pathlib import Path

from aifactory.config.settings import ProjectSettings
from aifactory.providers.base import (
    BRANCH_PREFIX,
    CHECKS_FAILING,
    CHECKS_NONE,
    CHECKS_PASSING,
    CHECKS_PENDING,
    CLOSED,
    CONFLICT,
    MERGEABILITY,
    MERGEABLE,
    MERGED,
    OPEN,
    PR_STATES,
    STRATEGIES,
    UNKNOWN,
    ChecksStatus,
    GitProvider,
    MergeFailed,
    ProviderError,
    PrStatus,
    PullRequest,
    task_id_from_branch,
)

__all__ = [
    "BRANCH_PREFIX",
    "CHECKS_FAILING",
    "CHECKS_NONE",
    "CHECKS_PASSING",
    "CHECKS_PENDING",
    "CLOSED",
    "CONFLICT",
    "MERGEABILITY",
    "MERGEABLE",
    "MERGED",
    "OPEN",
    "PR_STATES",
    "STRATEGIES",
    "UNKNOWN",
    "ChecksStatus",
    "GitProvider",
    "MergeFailed",
    "PrStatus",
    "ProviderError",
    "PullRequest",
    "get_provider",
    "task_id_from_branch",
]


def get_provider(settings: ProjectSettings, root: Path) -> GitProvider:
    """The provider named by ``settings.git_provider``."""
    if settings.git_provider == "local":
        from aifactory.providers.local import LocalProvider

        return LocalProvider(root, settings)
    if settings.git_provider == "github":
        from aifactory.providers.github import GitHubProvider

        return GitHubProvider(root, settings)
    if settings.git_provider == "azure":
        from aifactory.providers.azure import AzureProvider

        return AzureProvider(root, settings)
    raise ProviderError("invalid_config", f"unknown git_provider {settings.git_provider!r}")
