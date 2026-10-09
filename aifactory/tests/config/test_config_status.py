"""Uncommitted shared-config changes against the base commit."""

from __future__ import annotations

from pathlib import Path

from config_repo import git, make_repo, write

from aifactory.config import ConfigChange, change_warnings, config_changes
from aifactory.config.status import is_shared_config_path


def _head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()


def test_clean_repo_has_no_changes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    assert config_changes(repo, _head(repo)) == []


def test_every_kind_of_change(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, ".factory/agents.yaml", "agents: []\n")
    (repo / ".factory/prompts/builder/user.md").unlink()
    write(repo, ".factory/workflows/new.yaml", "name: new\n")
    write(repo, ".factory/roles.yaml", "roles: {}\n")
    git(repo, "add", ".factory/roles.yaml")
    assert config_changes(repo, _head(repo)) == [
        ConfigChange(".factory/agents.yaml", "modified"),
        ConfigChange(".factory/prompts/builder/user.md", "deleted"),
        ConfigChange(".factory/roles.yaml", "added"),
        ConfigChange(".factory/workflows/new.yaml", "untracked"),
    ]


def test_local_files_are_not_reported(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, ".factory/local.yaml", "port: 1234\n")
    write(repo, ".factory/worktrees/x", "run\n")
    write(repo, ".factory/trace.db", "db\n")
    assert config_changes(repo, _head(repo)) == []


def test_shared_paths() -> None:
    assert is_shared_config_path(".factory/config.yaml")
    assert is_shared_config_path(".factory/prompts/a/system.md")
    assert not is_shared_config_path(".factory/local.yaml")
    assert not is_shared_config_path(".factory/trace.db")


def test_warnings_name_path_base_and_commit() -> None:
    sha = "1234567890abcdef"
    [warning] = change_warnings([ConfigChange(".factory/agents.yaml", "modified")], "main", sha)
    assert ".factory/agents.yaml" in warning
    assert "main" in warning
    assert "1234567" in warning
    assert "modified" in warning
