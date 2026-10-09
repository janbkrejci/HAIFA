"""Local roster switches preserve roles and never change the committed run config."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from config_repo import make_repo, write

from aifactory.cli import main
from aifactory.config import ConfigError, load_run_config
from aifactory.config.roster import roster
from cli_json import read_envelope


def test_presets_and_role_switch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo(tmp_path / "repo")
    path = write(
        repo,
        ".factory/agents.yaml",
        """# retained comment
defaults:
  harness: claude # subscription
  model: sonnet
  tools: [Read]
  custom: retained
agents:
  - name: planner
    model: opus
    thinking: high
    writes: [specs/]
    purpose: plan
  - name: builder
    coding_agent: claude_code
    model: sonnet
    prompt_engineering: {system: custom.md, user: user.md}
""",
    )
    before = path.read_bytes()
    assert (
        main(["config", "roster", "set", "codex", "--repo", str(repo), "--dry-run", "--json"]) == 0
    )
    data = read_envelope(capsys)["data"]
    assert data["changed"] and data["diff"]
    assert path.read_bytes() == before
    assert main(["config", "roster", "set", "codex", "--repo", str(repo), "--json"]) == 0
    assert read_envelope(capsys)["warnings"]
    parsed = yaml.safe_load(path.read_text())
    assert "# retained comment" in path.read_text()
    assert "# subscription" in path.read_text()
    assert parsed["defaults"]["custom"] == "retained"
    assert parsed["defaults"]["tools"] == ["Read"]
    assert parsed["agents"][0] == {
        "name": "planner",
        "writes": ["specs/"],
        "purpose": "plan",
    }
    assert parsed["agents"][1]["prompt_engineering"] == {"system": "custom.md", "user": "user.md"}
    assert all(a["harness"] == "codex" for a in roster(repo)["agents"])
    assert (
        main(
            [
                "config",
                "roster",
                "set",
                "claude",
                "--agent",
                "planner",
                "--repo",
                str(repo),
                "--json",
            ]
        )
        == 0
    )
    mixed = read_envelope(capsys)["data"]["agents"]
    assert mixed[0]["model"] == "claude-opus-5-5"
    assert mixed[1]["model"] == "gpt-6.1-sol"
    assert mixed[1]["thinking"] == "medium"
    # Neither command changes the base used by tasks/workflows.
    assert load_run_config(repo).config.agents.agents[1].harness == "claude"
    roster(repo, change=True, preset="claude")
    assert all(a["model"] == "claude-opus-5-5" for a in roster(repo)["agents"])
    assert main(["config", "roster", "show", "--repo", str(repo), "--json"]) == 0
    assert read_envelope(capsys)["data"]["agents"][0]["thinking"] == "medium"


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"agent": "missing", "preset": "codex"},
        {"preset": "unknown"},
        {"harness": "unknown"},
        {"preset": "codex", "model": "claude-opus-5-5"},
        {"thinking": "invalid"},
        {"model": ""},
        {"preset": "codex", "thinking": "off"},
        {"preset": "codex", "model": "gpt with spaces"},
    ],
)
def test_invalid_switch_never_writes(tmp_path: Path, options: dict[str, Any]) -> None:
    repo = make_repo(tmp_path / "repo")
    path = repo / ".factory/agents.yaml"
    before = path.read_bytes()
    with pytest.raises(ConfigError):
        roster(repo, change=True, **options)
    assert path.read_bytes() == before


def test_explicit_override_and_atomic_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path / "repo")
    path = repo / ".factory/agents.yaml"
    roster(repo, change=True, preset="codex", model="openai/gpt-6.1-sol", thinking="max")
    assert roster(repo)["agents"][0]["thinking"] == "max"
    before = path.read_bytes()

    def fail(source: str, destination: Path) -> None:
        raise OSError("cannot replace")

    monkeypatch.setattr("aifactory.config.roster.os.replace", fail)
    with pytest.raises(ConfigError):
        roster(repo, change=True, preset="claude")
    assert path.read_bytes() == before
    assert not list(path.parent.glob(".agents-*.yaml"))


def test_flow_yaml_retains_unknown_fields(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(
        repo,
        ".factory/agents.yaml",
        "defaults: {harness: claude, model: opus}\nagents: [{name: builder, extra: {a: 1}}]\n",
    )
    result = roster(repo, change=True, preset="codex")
    assert result["comments_preserved"] is False
    assert yaml.safe_load((repo / ".factory/agents.yaml").read_text())["agents"][0]["extra"] == {
        "a": 1
    }


def test_role_preset_does_not_mutate_aliased_defaults(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write(
        repo,
        ".factory/agents.yaml",
        """defaults: &shared
  harness: claude
  model: opus
  thinking: medium
agents:
  - <<: *shared
    name: builder
  - <<: *shared
    name: reviewer
""",
    )
    roster(repo, change=True, agent="builder", preset="codex")
    builder, reviewer = roster(repo)["agents"]
    assert builder["harness"] == "codex" and reviewer["harness"] == "claude"
    assert reviewer["model"] == "opus"
    raw = yaml.safe_load((repo / ".factory/agents.yaml").read_text())
    assert raw["defaults"] == {"harness": "claude", "model": "opus", "thinking": "medium"}


def test_explicit_defaults_leave_role_overrides_and_workflows(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    workflow = repo / ".factory/workflows/plan-build.yaml"
    before = workflow.read_bytes()
    roster(repo, change=True, model="haiku", thinking="high")
    planner, builder = roster(repo)["agents"]
    assert planner["model"] == "opus" and builder["model"] == "haiku"
    assert planner["thinking"] == builder["thinking"] == "high"
    assert workflow.read_bytes() == before
