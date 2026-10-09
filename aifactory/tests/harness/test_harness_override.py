"""A workflow step overrides harness, model and thinking explicitly (D13)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from harness_fakes import (
    MODELS,
    agent_phase,
    codex_stream,
    envelope_text,
    events_of,
    fake_pi_catalog,
    make_env,
    pi_stream,
    start_run,
    stream,
)

from aifactory.engine import agent_cc, agent_pi
from aifactory.harness import codex
from aifactory.harness.config import AgentConfig, HarnessConfigError, SSSFConfig
from aifactory.harness.override import (
    StepOverride,
    check_override,
    effective_agent,
    step_override,
)

ENGINEERING = {"system": "system.md", "user": "user.md"}


def _agent(harness: str = "claude", model: str = "sonnet", **extra: object) -> AgentConfig:
    return AgentConfig.model_validate(
        {
            "name": "builder",
            "coding_agent": harness,
            "model": model,
            "prompt_engineering": ENGINEERING,
            **extra,
        }
    )


@pytest.fixture(autouse=True)
def _pi_catalog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_pi_catalog(monkeypatch, tmp_path)


def test_harness_override_all_fields() -> None:
    agent = _agent(thinking="low", color="#fff")
    effective = effective_agent(
        agent, StepOverride(harness="codex", model="gpt-5.5", thinking="high")
    )
    assert (effective.coding_agent, effective.model, effective.thinking) == (
        "codex",
        "gpt-5.5",
        "high",
    )
    assert effective.color == "#fff"
    assert agent.coding_agent == "claude"


def test_harness_override_model_alone_keeps_harness() -> None:
    agent = _agent()
    override = StepOverride(model="gpt-5.5")
    assert effective_agent(agent, override).coding_agent == "claude"
    problems = check_override(agent, override)
    assert len(problems) == 1 and "'claude' cannot run model 'gpt-5.5'" in problems[0]


def test_harness_override_rejects_bad_values() -> None:
    agent = _agent()
    assert "unknown harness" in check_override(agent, StepOverride(harness="gpt"))[0]
    assert "thinking 'huge'" in check_override(agent, StepOverride(thinking="huge"))[0]
    assert check_override(agent, StepOverride(harness="claude_code", thinking="max")) == []


def test_harness_override_leaving_pi_drops_extensions() -> None:
    agent = _agent("pi", "openai/gpt-5.5", harness_engineering=["ext.ts"])
    assert effective_agent(agent, StepOverride(thinking="low")).harness_engineering == ["ext.ts"]
    moved = effective_agent(agent, StepOverride(harness="claude", model="opus"))
    assert moved.coding_agent == "claude"
    assert moved.harness_engineering == []


def _cfg() -> SSSFConfig:
    return SSSFConfig.model_validate({"agents": [_agent().model_dump()]})


def test_harness_step_override_swaps_and_restores() -> None:
    cfg = _cfg()
    original = cfg.agents[0]
    with step_override(cfg, "builder", StepOverride(harness="codex", model="gpt-5.5")) as agent:
        assert cfg.agents[0] is agent
        assert agent.coding_agent == "codex"
    assert cfg.agents[0] is original

    with pytest.raises(RuntimeError, match="boom"):
        with step_override(cfg, "builder", StepOverride(thinking="high")):
            raise RuntimeError("boom")
    assert cfg.agents[0] is original


def test_harness_step_override_invalid_changes_nothing() -> None:
    cfg = _cfg()
    original = cfg.agents[0]
    with pytest.raises(HarnessConfigError):
        with step_override(cfg, "builder", StepOverride(model="gpt-5.5")):
            raise AssertionError("body must not run")
    assert cfg.agents[0] is original
    with pytest.raises(HarnessConfigError, match="not defined"):
        with step_override(cfg, "nobody", StepOverride()):
            pass


def test_harness_step_override_through_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extra = {
        name: {"harness": "claude", "model": MODELS["claude"]} for name in ("planner", "reviewer")
    }
    env = make_env(tmp_path, monkeypatch, "claude", extra_agents=extra)
    env.spawner.add(
        stream("claude", envelope_text()),
        codex_stream(envelope_text()),
        pi_stream(envelope_text()),
    )
    run = start_run(env)
    steps = [
        ("planner", StepOverride(harness="claude")),
        ("builder", StepOverride(harness="codex", model="gpt-5.5", thinking="high")),
        ("reviewer", StepOverride(harness="pi", model="openai/gpt-5.5", thinking="low")),
    ]
    for owner, override in steps:
        with step_override(env.cfg, owner, override):
            agent_phase(run, owner)

    cmds = env.spawner.cmds
    assert [cmd[0] for cmd in cmds] == [agent_cc.CLAUDE_PATH, codex.CODEX_PATH, agent_pi.PI_PATH]
    assert 'model_reasoning_effort="high"' in cmds[1]
    assert cmds[2][cmds[2].index("--thinking") + 1] == "low"
    started = []
    for seq, (owner, _) in enumerate(steps, start=1):
        phase_events = events_of(env.db_path, f"{run.adw_id}_{seq:02d}_{owner}")
        started += [p["coding_agent"] for t, _, p in phase_events if t == "agent_start"]
    assert started == ["claude", "codex", "pi"]
    # the roster is untouched after the steps
    assert [a.coding_agent for a in env.cfg.agents] == ["claude"] * 3
    assert (
        json.loads((run.session_dir / "agent_map.json").read_text())["builder"]["coding_agent"]
        == "codex"
    )
