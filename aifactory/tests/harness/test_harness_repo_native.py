"""Harnesses load the repo's instructions and skills natively; *_SAFE_MODE=1 isolates."""

from __future__ import annotations

from pathlib import Path

import pytest
from harness_fakes import THREAD_ID, fake_pi_catalog, fake_popen

from aifactory.engine import agent_cc, agent_pi
from aifactory.engine.data_types import AgentRequest
from aifactory.engine.utils import env_flag, flag_value
from aifactory.harness import codex

SYSTEM_PROMPT = 'You are "builder".\nReply with JSON only.'
SAFE_SWITCHES = ("CLAUDE_SAFE_MODE", "CODEX_SAFE_MODE", "PI_SAFE_MODE")


@pytest.fixture(autouse=True)
def _no_safe_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """The operator's environment must not decide what a test sees."""
    for name in SAFE_SWITCHES:
        monkeypatch.delenv(name, raising=False)


def _request(tmp_path: Path, model: str, **extra: object) -> AgentRequest:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    return AgentRequest(
        prompt="list the repo",
        system_prompt=SYSTEM_PROMPT,
        model=model,
        thinking="high",
        session_id="sssf-adw1-builder-abc",
        session_dir=str(tmp_path / "sessions"),
        raw_output_path=str(tmp_path / "raw_output.jsonl"),
        cwd=str(repo),
        **extra,  # type: ignore[arg-type]
    )


def _value_after(cmd: list[str], flag: str) -> str:
    return cmd[cmd.index(flag) + 1]


# ── switches ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", " on "])
def test_flag_on(value: str) -> None:
    assert flag_value(value)


@pytest.mark.parametrize("value", [None, "", "0", "false", "no", "off"])
def test_flag_off(value: str | None) -> None:
    assert not flag_value(value)


def test_env_flag_reads_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    assert not env_flag("PI_SAFE_MODE")
    monkeypatch.setenv("PI_SAFE_MODE", "1")
    assert env_flag("PI_SAFE_MODE")


# ── claude ──────────────────────────────────────────────────────────────────


def _claude_cmd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    spawner = fake_popen(monkeypatch, ["claude_turn.jsonl"])
    agent_cc.run(_request(tmp_path, "claude-opus-5"))
    (call,) = spawner.calls
    return call.cmd


def test_claude_default_loads_repo_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cmd = _claude_cmd(monkeypatch, tmp_path)
    assert _value_after(cmd, "--setting-sources") == "project,local"
    assert "--strict-mcp-config" in cmd
    assert "--safe-mode" not in cmd
    assert _value_after(cmd, "--system-prompt") == SYSTEM_PROMPT
    assert cmd[-1] == "list the repo"


def test_claude_safe_mode_isolates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_SAFE_MODE", "1")
    cmd = _claude_cmd(monkeypatch, tmp_path)
    assert "--safe-mode" in cmd
    assert "--strict-mcp-config" in cmd
    assert "--setting-sources" not in cmd


def test_claude_with_mcp_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(agent_cc, "MCP_CONFIG", "/x/mcp.json")
    cmd = _claude_cmd(monkeypatch, tmp_path)
    assert _value_after(cmd, "--mcp-config") == "/x/mcp.json"
    assert _value_after(cmd, "--setting-sources") == "project,local"

    monkeypatch.setenv("CLAUDE_SAFE_MODE", "1")
    cmd = _claude_cmd(monkeypatch, tmp_path / "again")
    assert "--mcp-config" in cmd
    assert "--safe-mode" not in cmd
    assert "--setting-sources" not in cmd


def test_claude_disallowed_tools_still_followed_by_option(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawner = fake_popen(monkeypatch, ["claude_turn.jsonl"])
    agent_cc.run(_request(tmp_path, "claude-opus-5", disallowed_commands=["git push"]))
    cmd = spawner.calls[0].cmd
    rule = cmd.index("--disallowedTools") + 1
    assert cmd[rule + 1].startswith("--")


# ── codex ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("thread_id", ["", THREAD_ID])
def test_codex_default_reads_agents_md(tmp_path: Path, thread_id: str) -> None:
    cmd = codex.build_command(_request(tmp_path, "gpt-5.5"), thread_id)
    assert "--ignore-user-config" in cmd
    assert "project_doc_max_bytes=0" not in cmd
    assert any(item.startswith("developer_instructions=") for item in cmd)


@pytest.mark.parametrize("thread_id", ["", THREAD_ID])
def test_codex_safe_mode_isolates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, thread_id: str
) -> None:
    monkeypatch.setenv("CODEX_SAFE_MODE", "1")
    cmd = codex.build_command(_request(tmp_path, "gpt-5.5"), thread_id)
    index = cmd.index("project_doc_max_bytes=0")
    assert cmd[index - 1] == "-c"
    assert "--ignore-user-config" in cmd


# ── pi ──────────────────────────────────────────────────────────────────────


def _pi_cmd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **extra: object) -> list[str]:
    fake_pi_catalog(monkeypatch, tmp_path)
    spawner = fake_popen(monkeypatch, ["pi_turn.jsonl"])
    agent_pi.run(_request(tmp_path, "openai/gpt-5.5", **extra))
    (call,) = spawner.calls
    return call.cmd


def test_pi_default_trusts_project_and_loads_repo_skills(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    skills = tmp_path / "repo" / ".agents" / "skills"
    (skills / "demo").mkdir(parents=True)
    (skills / "demo" / "SKILL.md").write_text(
        "---\nname: demo\n---\n", encoding="utf-8", newline="\n"
    )
    cmd = _pi_cmd(monkeypatch, tmp_path, extensions=["/x/ext.ts"])
    for flag in ("--approve", "--no-skills", "--no-extensions", "--no-prompt-templates"):
        assert flag in cmd, flag
    assert _value_after(cmd, "--skill") == str(skills.resolve())
    assert Path(_value_after(cmd, "--skill")).is_absolute()
    assert "--no-context-files" not in cmd
    assert "--no-approve" not in cmd
    assert _value_after(cmd, "--system-prompt") == SYSTEM_PROMPT
    assert _value_after(cmd, "-e") == "/x/ext.ts"


def test_pi_default_without_repo_skills(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cmd = _pi_cmd(monkeypatch, tmp_path)
    assert "--approve" in cmd
    assert "--skill" not in cmd


def test_pi_safe_mode_isolates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PI_SAFE_MODE", "1")
    (tmp_path / "repo" / ".agents" / "skills").mkdir(parents=True)
    cmd = _pi_cmd(monkeypatch, tmp_path)
    for flag in (
        "--no-approve",
        "--no-context-files",
        "--no-skills",
        "--no-extensions",
        "--no-prompt-templates",
    ):
        assert flag in cmd, flag
    assert "--approve" not in cmd
    assert "--skill" not in cmd
