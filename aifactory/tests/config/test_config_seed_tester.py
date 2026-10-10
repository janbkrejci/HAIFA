"""A roster from before 3.0 has no tester: it gets the seed's, prompts included."""

from __future__ import annotations

from pathlib import Path

from config_repo import make_repo, write

from aifactory.config import load_worktree_config


def test_roster_without_tester_gets_the_seed_tester(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    config = load_worktree_config(repo)
    tester = next(a for a in config.agents.agents if a.name == "tester")
    assert tester.coding_agent == "claude"  # the roster default (harness: claude)
    assert tester.writes == []
    assert "# Tester Agent" in config.prompts["tester"].system
    assert "{{failed_test}}" in config.prompts["tester"].user


def test_roster_without_defaults_takes_the_seed_harness(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(
        repo,
        ".factory/agents.yaml",
        "agents:\n  - name: planner\n    harness: codex\n    model: m\n  - name: builder\n"
        "    harness: codex\n    model: m\n",
    )
    tester = next(a for a in load_worktree_config(repo).agents.agents if a.name == "tester")
    assert tester.coding_agent == "claude"
    assert tester.model == "claude-opus-5-5"


def test_own_tester_wins(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(
        repo,
        ".factory/agents.yaml",
        "defaults:\n  harness: claude\n  model: sonnet\nagents:\n  - name: planner\n"
        "  - name: builder\n  - name: tester\n    model: haiku\n",
    )
    write(repo, ".factory/prompts/tester/system.md", "own system\n")
    write(repo, ".factory/prompts/tester/user.md", "own user\n")
    config = load_worktree_config(repo)
    tester = next(a for a in config.agents.agents if a.name == "tester")
    assert tester.model == "haiku"
    assert config.prompts["tester"].system == "own system\n"
