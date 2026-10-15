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
    agents = {a["name"]: a for a in roster(repo)["agents"]}
    builder, reviewer = agents["builder"], agents["reviewer"]
    assert builder["harness"] == "codex" and reviewer["harness"] == "claude"
    assert reviewer["model"] == "opus"
    raw = yaml.safe_load((repo / ".factory/agents.yaml").read_text())
    assert raw["defaults"] == {"harness": "claude", "model": "opus", "thinking": "medium"}


def test_explicit_defaults_leave_role_overrides_and_workflows(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    workflow = repo / ".factory/workflows/plan-build.yaml"
    before = workflow.read_bytes()
    roster(repo, change=True, model="haiku", thinking="high")
    agents = {a["name"]: a for a in roster(repo)["agents"]}
    planner, builder = agents["planner"], agents["builder"]
    assert planner["model"] == "opus" and builder["model"] == "haiku"
    assert planner["thinking"] == builder["thinking"] == "high"
    assert workflow.read_bytes() == before


def test_inherited_agent_gets_an_override_entry(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    agents = {a["name"]: a for a in roster(repo)["agents"]}
    assert agents["reviewer"]["origin"] == "library"
    assert agents["planner"]["origin"] == "repo"
    result = roster(repo, change=True, agent="reviewer", harness="codex", model="gpt-6.1-sol")
    assert result["comments_preserved"] is True
    raw = yaml.safe_load((repo / ".factory/agents.yaml").read_text())
    assert raw["agents"][-1] == {"name": "reviewer", "harness": "codex", "model": "gpt-6.1-sol"}
    reviewer = next(a for a in roster(repo)["agents"] if a["name"] == "reviewer")
    assert (reviewer["harness"], reviewer["origin"]) == ("codex", "library")


def test_roster_without_agents_yaml_is_created(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    (repo / ".factory/agents.yaml").unlink()
    assert {a["origin"] for a in roster(repo)["agents"]} == {"library"}
    roster(repo, change=True, preset="codex")
    raw = yaml.safe_load((repo / ".factory/agents.yaml").read_text())
    assert raw["defaults"]["harness"] == "codex"
    assert all(a["harness"] == "codex" for a in roster(repo)["agents"])


def test_reset_returns_an_inherited_agent_to_the_library(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    library = {a["name"]: a for a in roster(repo)["agents"]}["reviewer"]
    roster(repo, change=True, agent="reviewer", model="opus", thinking="high")
    path = repo / ".factory/agents.yaml"
    written = path.read_bytes()
    preview = roster(repo, change=True, agent="reviewer", reset=("model",), dry_run=True)
    assert preview["changed"] and "-    model: opus" in preview["diff"].replace('"', "")
    assert path.read_bytes() == written
    roster(repo, change=True, agent="reviewer", reset=("model",))
    raw = yaml.safe_load(path.read_text())
    assert raw["agents"][-1] == {"name": "reviewer", "thinking": "high"}
    result = roster(repo, change=True, agent="reviewer", reset=("harness", "model", "thinking"))
    assert result["changed"]
    raw = yaml.safe_load(path.read_text())
    assert all(a.get("name") != "reviewer" for a in raw["agents"])
    reviewer = {a["name"]: a for a in roster(repo)["agents"]}["reviewer"]
    assert (reviewer["harness"], reviewer["model"]) == (library["harness"], library["model"])
    again = roster(repo, change=True, agent="reviewer", reset=("model",))
    assert again["changed"] is False and again["diff"] == ""


@pytest.mark.parametrize(
    "options",
    [
        {"reset": ("model",)},
        {"agent": "reviewer", "reset": ("model",), "model": "opus"},
        {"agent": "reviewer", "reset": ("tools",)},
    ],
)
def test_invalid_reset_is_a_config_error(tmp_path: Path, options: dict[str, Any]) -> None:
    repo = make_repo(tmp_path / "repo")
    with pytest.raises(ConfigError):
        roster(repo, change=True, **options)


def test_inherited_bindings_list_overrides_and_library_values(tmp_path: Path) -> None:
    from aifactory.config.roster import inherited_bindings

    repo = make_repo(tmp_path / "repo")
    library = {a["name"]: a for a in roster(repo)["agents"]}["reviewer"]
    roster(repo, change=True, agent="reviewer", model="gpt-6.1-sol", harness="codex")
    text = (repo / ".factory/agents.yaml").read_text()
    (repo / ".factory/agents.yaml").write_text(
        text.replace("harness: codex", "coding_agent: codex")
    )
    bindings = inherited_bindings(repo)
    assert sorted(bindings["reviewer"]["overridden"]) == ["harness", "model"]
    assert bindings["reviewer"]["inherited"] == {
        "harness": library["harness"],
        "model": library["model"],
        "thinking": library["thinking"],
    }
    assert bindings["planner"]["inherited"] is None
