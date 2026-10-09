"""Choosing the provider from ``.factory/config.yaml``."""

from __future__ import annotations

from pathlib import Path

import pytest

from aifactory.config.errors import ConfigIssue
from aifactory.config.settings import ProjectSettings, parse_project_settings
from aifactory.providers import get_provider, task_id_from_branch
from aifactory.providers.azure import AzureProvider
from aifactory.providers.github import GitHubProvider
from aifactory.providers.local import LocalProvider


def _settings(text: str) -> ProjectSettings:
    issues: list[ConfigIssue] = []
    settings = parse_project_settings(text, ".factory/config.yaml", issues)
    assert settings is not None, issues
    return settings


def test_github_from_config(tmp_path: Path) -> None:
    provider = get_provider(_settings("git_provider: github\n"), tmp_path)
    assert isinstance(provider, GitHubProvider)
    assert provider.name == "github"


def test_local_is_default(tmp_path: Path) -> None:
    provider = get_provider(_settings("base: main\n"), tmp_path)
    assert isinstance(provider, LocalProvider)


def test_azure_from_config(tmp_path: Path) -> None:
    text = "git_provider: azure\nazure:\n  organization: contoso\n  project: P\n  repository: r\n"
    provider = get_provider(_settings(text), tmp_path)
    assert isinstance(provider, AzureProvider)
    assert provider.name == "azure"


def test_invalid_provider_is_a_config_issue() -> None:
    issues: list[ConfigIssue] = []
    assert parse_project_settings("git_provider: gitlab\n", "config.yaml", issues) is None
    assert any("git_provider" in str(issue) for issue in issues)


def test_merge_strategy_defaults_to_squash() -> None:
    assert _settings("git_provider: github\n").merge_strategy == "squash"
    assert _settings("merge_strategy: merge\n").merge_strategy == "merge"


@pytest.mark.parametrize(
    ("branch", "task_id"),
    [
        ("factory/M01-S01-T01-2", "M01-S01-T01"),
        ("main", None),
        ("factory/x", None),
    ],
)
def test_task_id_from_branch(branch: str, task_id: str | None) -> None:
    assert task_id_from_branch(branch) == task_id
