"""A claude conversation opened by a turn that died is rejoined, never created twice."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from harness_fakes import FakeSpawner, fake_popen

from aifactory.engine import agent_cc
from aifactory.engine.data_types import AgentRequest

IN_USE = "Error: Session ID {} is already in use."


def _request(tmp_path: Path) -> AgentRequest:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    return AgentRequest(
        prompt="plan it",
        system_prompt="You are the planner.",
        model="claude-opus-5",
        thinking="medium",
        session_id="sssf-adw1-planner-abc",
        session_dir=str(tmp_path / "sessions"),
        raw_output_path=str(tmp_path / "raw_output.jsonl"),
        cwd=str(repo),
    )


class _Sequence(FakeSpawner):
    """Per spawn: (returncode, stderr), in order."""

    def __init__(self, outputs: list[str], results: list[tuple[int, str]]) -> None:
        super().__init__(outputs)
        self._results = results

    def __call__(self, cmd: Any, *args: Any, **kw: Any) -> Any:
        if self._results and isinstance(cmd, list) and cmd and cmd[0] == agent_cc.CLAUDE_PATH:
            self._returncode, self._stderr = self._results.pop(0)
        return super().__call__(cmd, *args, **kw)


def test_unrecorded_conversation_in_use_is_rejoined_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    request = _request(tmp_path)
    conversation = agent_cc.session_uuid(request.session_id)
    fake_popen(monkeypatch)  # patches launch resolution; the sequence replaces Popen below
    spawner = _Sequence(["", "claude_turn.jsonl"], [(1, IN_USE.format(conversation)), (0, "")])
    monkeypatch.setattr("subprocess.Popen", spawner)

    agent_cc.run(request)

    first, second = spawner.cmds
    assert first[first.index("--session-id") + 1] == conversation
    assert second[second.index("--resume") + 1] == conversation


def test_conversation_is_recorded_as_soon_as_claude_opens_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    request = _request(tmp_path)
    init = '{"type": "system", "subtype": "init"}\n'
    fake_popen(monkeypatch, [init], returncode=1, stderr="killed")

    with pytest.raises(RuntimeError):
        agent_cc.run(request)

    spawner = fake_popen(monkeypatch, ["claude_turn.jsonl"])
    agent_cc.run(request)
    (call,) = spawner.calls
    assert "--resume" in call.cmd and "--session-id" not in call.cmd
