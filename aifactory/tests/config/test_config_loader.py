"""Loading the whole `.factory/` from the working tree."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from config_repo import AGENTS_YAML, make_repo, write

from aifactory.config import ConfigError, load_worktree_config, write_prompts
from aifactory.engine.role_registry import DEFAULT_ROLES_PATH


def test_sample_config_loads(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    config = load_worktree_config(repo)
    agents = {agent.name: agent for agent in config.agents.agents}
    assert [a.name for a in config.agents.agents] == ["planner", "builder", "tester"]
    assert all(a.coding_agent == "claude" for a in agents.values())
    assert agents["planner"].model == "opus"
    assert agents["builder"].model == "sonnet"
    assert agents["planner"].writes == ["specs/"]
    assert agents["planner"].prompt_engineering.system == ".factory/prompts/planner/system.md"
    assert "{{prompt}}" in config.prompts["planner"].user
    assert config.prompts["builder"].system == "You are the builder.\n"
    assert config.workflows["plan-build"] == {"name": "plan-build", "steps": ["plan", "build"]}
    assert config.source == str(repo.resolve())


def test_missing_roles_uses_packaged_default(tmp_path: Path) -> None:
    config = load_worktree_config(make_repo(tmp_path / "repo"))
    assert config.roles.is_role("plan")
    assert ".factory/roles.yaml" not in config.files


def test_invalid_roles_names_the_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(
        repo,
        ".factory/roles.yaml",
        "roles:\n  plan:\n    agent: planner\n    output_type: NoSuchOutput\n"
        "    gates: []\n    description: Plan it\n",
    )
    with pytest.raises(ConfigError) as info:
        load_worktree_config(repo)
    assert Path(info.value.issues[0].path).as_posix().endswith(".factory/roles.yaml")
    assert "unknown_output_type" in str(info.value)


def test_custom_roles_are_used(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    data = yaml.safe_load(DEFAULT_ROLES_PATH.read_text(encoding="utf-8"))
    del data["roles"]["scout"]
    write(repo, ".factory/roles.yaml", yaml.safe_dump(data))
    config = load_worktree_config(repo)
    assert config.roles.is_role("plan")
    assert not config.roles.is_role("scout")


def test_agent_without_harness_is_an_error(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, ".factory/agents.yaml", AGENTS_YAML.replace("  harness: claude\n", ""))
    with pytest.raises(ConfigError) as info:
        load_worktree_config(repo)
    assert all(Path(i.path).as_posix().endswith(".factory/agents.yaml") for i in info.value.issues)
    assert "harness is not set" in str(info.value)


def test_missing_prompt_names_the_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    (repo / ".factory/prompts/builder/system.md").unlink()
    with pytest.raises(ConfigError) as info:
        load_worktree_config(repo)
    assert str(Path(".factory/prompts/builder/system.md")) in str(info.value)
    assert "missing prompt for agent 'builder'" in str(info.value)


def test_prompt_engineering_in_agents_is_an_error(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(
        repo,
        ".factory/agents.yaml",
        AGENTS_YAML + "    prompt_engineering: {system: a.md, user: b.md}\n",
    )
    with pytest.raises(ConfigError, match="prompt_engineering is not allowed"):
        load_worktree_config(repo)


def test_invalid_workflow_names_the_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, ".factory/workflows/broken.yaml", "steps: [plan\n")
    with pytest.raises(ConfigError) as info:
        load_worktree_config(repo)
    assert str(Path(".factory/workflows/broken.yaml")) in str(info.value)


def test_workflow_root_must_be_mapping(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, ".factory/workflows/list.yaml", "- plan\n- build\n")
    with pytest.raises(ConfigError, match="must be a mapping"):
        load_worktree_config(repo)


def test_nested_and_non_yaml_workflow_files_are_ignored(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, ".factory/workflows/README.md", "notes\n")
    write(repo, ".factory/workflows/old/x.yaml", "name: x\n")
    assert list(load_worktree_config(repo).workflows) == ["plan-build"]


def test_missing_agents_gives_empty_roster(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    (repo / ".factory/agents.yaml").unlink()
    config = load_worktree_config(repo)
    assert config.agents.agents == []
    assert set(config.prompts) == {"builder", "planner"}


def test_all_issues_are_reported(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, ".factory/config.yaml", "git_provider: svn\n")
    (repo / ".factory/prompts/planner/user.md").unlink()
    with pytest.raises(ConfigError) as info:
        load_worktree_config(repo)
    paths = [Path(i.path).as_posix() for i in info.value.issues]
    assert len(paths) >= 2
    assert any(p.endswith(".factory/config.yaml") for p in paths)
    assert any(p.endswith(".factory/prompts/planner/user.md") for p in paths)


def test_write_prompts(tmp_path: Path) -> None:
    config = load_worktree_config(make_repo(tmp_path / "repo"))
    dest = tmp_path / "session" / "prompts"
    roster = write_prompts(config, dest)
    planner = next(a for a in roster.agents if a.name == "planner")
    system = Path(planner.prompt_engineering.system)
    assert system.is_file()
    assert system.is_relative_to(dest.resolve())
    assert system.read_text() == config.prompts["planner"].system
    assert Path(planner.prompt_engineering.user).read_text() == config.prompts["planner"].user
    assert planner.model == "opus"


def test_overlay_roles_merge_with_packaged(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, ".factory/roles.yaml", "roles:\n  build: {agent: planner}\n")
    config = load_worktree_config(repo)
    assert config.roles.roles["build"].agent == "planner"
    assert config.roles.roles["build"].output_type_name == "BuildOutput"
    assert config.roles.is_role("scout")
    assert config.roles.is_code("test")
