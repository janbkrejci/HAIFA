"""The harness is spelled out on the agent (or in defaults), never inferred (D13)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from harness_fakes import fake_pi_catalog

from aifactory.engine import agents
from aifactory.engine import data_types as dt
from aifactory.harness import codex
from aifactory.harness.config import (
    HarnessConfigError,
    load_config,
    normalize_raw,
    validate,
)
from aifactory.harness.config import SSSFConfig as HarnessSSSFConfig


def _write(tmp_path: Path, agent: dict[str, Any], defaults: dict[str, Any] | None = None) -> Path:
    prompts = tmp_path / "prompts"
    prompts.mkdir(exist_ok=True)
    (prompts / "system.md").write_text("system\n", encoding="utf-8", newline="\n")
    (prompts / "user.md").write_text("{{prompt}}\n", encoding="utf-8", newline="\n")
    engineering = {"system": str(prompts / "system.md"), "user": str(prompts / "user.md")}
    config = {
        "defaults": defaults or {},
        "agents": [{"name": "a", "prompt_engineering": engineering, **agent}],
    }
    path = tmp_path / "factory.config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8", newline="\n")
    return path


@pytest.fixture(autouse=True)
def _pi_catalog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_pi_catalog(monkeypatch, tmp_path)
    monkeypatch.setattr(agents, "INTERFACES", dict(agents.INTERFACES))


def test_harness_explicit_codex(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, {"harness": "codex", "model": "gpt-5.5"}))
    (agent,) = cfg.agents
    assert agent.coding_agent == "codex"
    assert agent.harness == "codex"
    validate(cfg, ["a"])
    assert agents.interface(agent) is codex
    assert isinstance(cfg, dt.SSSFConfig)
    assert isinstance(cfg, HarnessSSSFConfig)
    assert isinstance(agent, dt.AgentConfig)


def test_harness_inherited_from_defaults(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, {"model": "opus"}, {"harness": "claude"}))
    assert cfg.agents[0].harness == "claude"
    assert cfg.defaults.harness == "claude"


@pytest.mark.parametrize("key", ["harness", "coding_agent"])
def test_harness_alias_claude_code(tmp_path: Path, key: str) -> None:
    cfg = load_config(_write(tmp_path, {key: "claude_code", "model": "opus"}))
    assert cfg.agents[0].coding_agent == "claude"


def test_harness_missing_is_an_error_even_for_claude_models(tmp_path: Path) -> None:
    with pytest.raises(HarnessConfigError, match="harness is not set"):
        load_config(_write(tmp_path, {"model": "opus"}))


def test_harness_missing_collects_every_agent() -> None:
    raw = {"agents": [{"name": "x", "model": "opus"}, {"name": "y", "harness": "gpt"}]}
    with pytest.raises(HarnessConfigError) as info:
        normalize_raw(raw)
    problems = info.value.problems
    assert len(problems) == 2
    assert "agent 'x': harness is not set (claude|codex|pi)" in problems
    assert "unknown harness 'gpt'" in problems[1] and "available" in problems[1]


def test_harness_conflict_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(HarnessConfigError, match="conflicts with coding_agent 'pi'"):
        load_config(_write(tmp_path, {"harness": "codex", "coding_agent": "pi", "model": "x"}))


def test_harness_normalize_is_pure() -> None:
    raw = {"agents": [{"name": "x", "harness": "codex"}]}
    normalize_raw(raw)
    assert raw == {"agents": [{"name": "x", "harness": "codex"}]}


@pytest.mark.parametrize("name", ["pi", "codex"])
def test_harness_same_model_follows_the_config(tmp_path: Path, name: str) -> None:
    cfg = load_config(_write(tmp_path, {"harness": name, "model": "openai/gpt-5.5"}))
    validate(cfg, ["a"])
    assert cfg.agents[0].coding_agent == name


def test_harness_claude_with_openai_model_fails(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, {"harness": "claude", "model": "openai/gpt-5.5"}))
    with pytest.raises(SystemExit, match="not a Claude Code model"):
        validate(cfg, ["a"])
    assert cfg.agents[0].coding_agent == "claude"


def test_harness_engineering_is_pi_only(tmp_path: Path) -> None:
    cfg = load_config(
        _write(tmp_path, {"harness": "codex", "model": "gpt-5.5", "harness_engineering": ["x"]})
    )
    with pytest.raises(SystemExit, match="harness_engineering"):
        validate(cfg, ["a"])
