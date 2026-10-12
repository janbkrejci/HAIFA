"""Prompts travel through stdin and files, so argv stays under the Windows limit."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from harness_fakes import THREAD_ID, fake_pi_catalog, fake_popen

from aifactory.engine import agent_cc, agent_pi
from aifactory.engine.data_types import AgentRequest
from aifactory.engine.utils import send_stdin
from aifactory.harness import codex

# CreateProcess accepts at most 32 767 characters on the command line.
WINDOWS_LIMIT = 32_767
# Everything left on the command line (flags, paths, a role prompt for codex).
ARGV_BUDGET = 8_192
PROMPT = "Návrh parametrů tasku. " + "x" * 40_000 + "\nend"
SYSTEM = "You are the planner.\n" + "y" * 40_000

HARNESSES: dict[str, tuple[ModuleType, str, str]] = {
    "claude": (agent_cc, "claude-opus-5", "claude_turn.jsonl"),
    "codex": (codex, "gpt-5.5", "codex_turn.jsonl"),
    "pi": (agent_pi, "openai/gpt-5.5", "pi_turn.jsonl"),
}


def _request(tmp_path: Path, model: str, system: str) -> AgentRequest:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    return AgentRequest(
        prompt=PROMPT,
        system_prompt=system,
        model=model,
        thinking="high",
        session_id="sssf-adw1-planner-abc",
        session_dir=str(tmp_path / "sessions"),
        raw_output_path=str(tmp_path / "raw_output.jsonl"),
        cwd=str(repo),
    )


@pytest.mark.parametrize("name", sorted(HARNESSES))
def test_long_prompt_stays_off_the_command_line(
    name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module, model, fixture = HARNESSES[name]
    fake_pi_catalog(monkeypatch, tmp_path)
    spawner = fake_popen(monkeypatch, [fixture])
    # codex cannot read its developer instructions from a file; the others can.
    system = "You are the planner." if name == "codex" else SYSTEM
    request = _request(tmp_path, model, system)
    assert len(PROMPT) > WINDOWS_LIMIT

    module.run(request)

    (call,) = spawner.calls
    line = subprocess.list2cmdline(call.cmd)
    assert len(line) < ARGV_BUDGET < WINDOWS_LIMIT
    assert call.kwargs["stdin"] is subprocess.PIPE
    assert call.prompt == PROMPT


def test_codex_resume_prompt_stays_off_the_command_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cmd = codex.build_command(_request(tmp_path, "gpt-5.5", "You are the planner."), THREAD_ID)
    assert cmd[-2:] == [THREAD_ID, "-"]
    assert len(subprocess.list2cmdline(cmd)) < ARGV_BUDGET


@pytest.mark.parametrize("name", ["claude", "pi"])
def test_system_prompt_file_holds_the_prompt(
    name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module, model, fixture = HARNESSES[name]
    fake_pi_catalog(monkeypatch, tmp_path)
    spawner = fake_popen(monkeypatch, [fixture])
    module.run(_request(tmp_path, model, SYSTEM))

    cmd = spawner.calls[0].cmd
    flag = "--system-prompt-file" if name == "claude" else "--system-prompt"
    path = Path(cmd[cmd.index(flag) + 1])
    assert path.is_absolute()
    assert path.read_text(encoding="utf-8") == SYSTEM


def test_send_stdin_delivers_utf8_bytes_unchanged() -> None:
    """A real child gets the exact prompt: no CRLF translation, no size cap."""
    child = "import sys; sys.stdout.write(sys.stdin.buffer.read().hex())"
    process = subprocess.Popen(
        [sys.executable, "-c", child],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    send_stdin(process, PROMPT)
    out = process.stdout.read() if process.stdout else ""
    assert process.wait() == 0
    assert bytes.fromhex(out) == PROMPT.encode("utf-8")
