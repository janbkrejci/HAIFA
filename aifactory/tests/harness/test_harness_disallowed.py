"""``disallowed_commands``: claude gets ``--disallowedTools``, other harnesses are reported."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from harness_fakes import agent_phase, envelope_text, make_env, start_run, stream

from aifactory import harness
from aifactory.check.repo_rules import disallowed_commands as check_rule
from aifactory.engine import agent_cc
from aifactory.harness.config import normalize_raw

DENIED = ["just check", "just test *", "pytest", "just test *"]


def _agent(harness_name: str, commands: list[str]) -> Any:
    return SimpleNamespace(name="builder", coding_agent=harness_name, disallowed_commands=commands)


def test_claude_command_carries_disallowed_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(
        tmp_path,
        monkeypatch,
        "claude",
        extra_agents={
            "reviewer": {"harness": "claude", "model": "sonnet", "disallowed_commands": DENIED}
        },
    )
    env.spawner.add(stream("claude", envelope_text()))
    agent_phase(start_run(env), "reviewer", prompt="review it")
    (cmd,) = env.spawner.cmds
    at = cmd.index("--disallowedTools")
    rules = ["Bash(just check)", "Bash(just test *)", "Bash(pytest)"]
    assert cmd[at + 1 : at + 4] == rules
    # the flag is variadic: an option must end it before the prompt
    assert cmd[at + 4].startswith("--")
    assert cmd[-1].strip() == "review it"


def test_claude_command_without_disallowed_has_no_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path, monkeypatch, "claude")
    env.spawner.add(stream("claude", envelope_text()))
    agent_phase(start_run(env), "builder")
    assert "--disallowedTools" not in env.spawner.cmds[0]


def test_disallowed_tools_rules() -> None:
    assert agent_cc.disallowed_tools(["  just   test ", "", "Bash(rm -rf *)", "WebFetch"]) == [
        "Bash(just test)",
        "Bash(rm -rf *)",
        "Bash(WebFetch)",
    ]


def test_which_harness_can_forbid_commands() -> None:
    assert harness.supports_disallowed_commands("claude")
    assert harness.supports_disallowed_commands("claude_code")
    assert not harness.supports_disallowed_commands("codex")
    assert not harness.supports_disallowed_commands("pi")


@pytest.mark.parametrize("name", ["codex", "pi"])
def test_harness_without_support_is_reported(name: str) -> None:
    problem = harness.unenforced_disallowed(_agent(name, ["just test"]))
    assert problem is not None
    assert f"harness {name!r}" in problem and "`just test`" in problem


def test_nothing_to_report() -> None:
    assert harness.unenforced_disallowed(_agent("claude", ["just test"])) is None
    assert harness.unenforced_disallowed(_agent("codex", [])) is None
    assert harness.unenforced_disallowed(_agent("pi", ["  "])) is None


def test_agents_inherit_disallowed_commands_from_defaults() -> None:
    data = normalize_raw(
        {
            "defaults": {"harness": "claude", "disallowed_commands": ["just test"]},
            "agents": [{"name": "builder"}, {"name": "reviewer", "disallowed_commands": []}],
        }
    )
    builder, reviewer = data["agents"]
    assert builder["disallowed_commands"] == ["just test"]
    assert reviewer["disallowed_commands"] == []


def test_factory_check_reports_unenforced_restriction() -> None:
    roster = SimpleNamespace(
        agents=[
            _agent("claude", ["just test"]),
            SimpleNamespace(name="reviewer", coding_agent="codex", disallowed_commands=["pytest"]),
        ]
    )
    findings = list(check_rule(SimpleNamespace(roster=roster)))  # type: ignore[arg-type]
    assert [f.code for f in findings] == ["disallowed_commands_unenforced"]
    assert findings[0].severity == "warning"
    assert "'reviewer'" in findings[0].message and "codex" in findings[0].message
    assert list(check_rule(SimpleNamespace(roster=None))) == []  # type: ignore[arg-type]
