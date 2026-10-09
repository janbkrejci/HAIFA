"""Fake child processes for harness tests: scripted JSONL instead of a real CLI.

No ``conftest.py`` lives here (mypy would see two modules named ``conftest``);
tests import these helpers directly, like ``engine_fakes``.
"""

from __future__ import annotations

import io
import json
import sqlite3
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from aifactory import harness
from aifactory.engine import agent_cc, agent_pi, agents, session
from aifactory.engine.data_types import AgentCall, EnvelopeBase, GenericOutput, PhaseParams
from aifactory.engine.runner import Run
from aifactory.harness import codex
from aifactory.harness.config import SSSFConfig, load_config

FIXTURES = Path(__file__).parent / "fixtures"
PID = 4242
TIMING_KEYS = ("started_at", "ended_at", "duration_ms")
THREAD_ID = "019a0000-0000-7000-8000-000000000001"
NAMES = ["claude", "codex", "pi"]
# codex and pi get the same OpenAI model: the harness comes from the config only.
MODELS = {"claude": "sonnet", "codex": "gpt-5.5", "pi": "openai/gpt-5.5"}
# The real Popen, taken before any test replaces it.
REAL_POPEN = subprocess.Popen


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def harness_binaries() -> set[str]:
    return {agent_cc.CLAUDE_PATH, codex.CODEX_PATH, agent_pi.PI_PATH}


class FakePopen:
    """Stands in for ``subprocess.Popen``; replays one scripted stdout."""

    def __init__(
        self, cmd: list[str], stdout_text: str, stderr_text: str, returncode: int, **kw: Any
    ) -> None:
        self.cmd = list(cmd)
        self.kwargs = kw
        self.stdout = io.StringIO(stdout_text)
        self.stderr = io.StringIO(stderr_text)
        self.pid = PID
        self.returncode = returncode

    def wait(self) -> int:
        return self.returncode


class FakeSpawner:
    """One FakePopen per queued stdout, in order; every harness call is remembered.

    Queue items are fixture file names (``*.jsonl``) or JSONL text. Commands that
    are not a harness binary (git, run by ``subprocess.run`` under the same
    patched module) go to the real ``Popen``.
    """

    def __init__(self, outputs: Iterable[str] = (), returncode: int = 0, stderr: str = "") -> None:
        self._queue = list(outputs)
        self._returncode = returncode
        self._stderr = stderr
        self.calls: list[FakePopen] = []

    def add(self, *outputs: str) -> None:
        self._queue.extend(outputs)

    def __call__(self, cmd: Any, *args: Any, **kw: Any) -> Any:
        if not isinstance(cmd, list | tuple) or not cmd or cmd[0] not in harness_binaries():
            return REAL_POPEN(cmd, *args, **kw)
        if not self._queue:
            raise AssertionError(f"unexpected extra harness spawn: {cmd}")
        item = self._queue.pop(0)
        text = fixture_text(item) if item.endswith(".jsonl") else item
        process = FakePopen(list(cmd), text, self._stderr, self._returncode, **kw)
        self.calls.append(process)
        return process

    @property
    def cmds(self) -> list[list[str]]:
        return [call.cmd for call in self.calls]


def fake_popen(
    monkeypatch: pytest.MonkeyPatch,
    outputs: Iterable[str] = (),
    returncode: int = 0,
    stderr: str = "",
) -> FakeSpawner:
    """Replace ``subprocess.Popen`` (shared by every adapter) with a spawner."""
    spawner = FakeSpawner(outputs, returncode, stderr)
    # Native npm launch resolution is tested separately. Preserve the fake CLI
    # name here so Windows never sends a scripted harness test to the real CLI.
    monkeypatch.setattr(codex, "launch_command", lambda command: command)
    monkeypatch.setattr(subprocess, "Popen", spawner)
    return spawner


def normalize(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tool-call records without their wall-clock fields."""
    return [{k: v for k, v in r.items() if k not in TIMING_KEYS} for r in records]


def fake_pi_catalog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """pi's model catalog without ``pi --list-models``."""
    monkeypatch.setattr(agent_pi, "_pi_catalog", lambda: [("openai", "gpt-5.5", 272000)])
    monkeypatch.setattr(agent_pi, "MODELS_JSON", str(tmp_path / "no-models.json"))


# ── scripted streams, shaped like the recorded fixtures ─────────────────────


def _jsonl(events: Sequence[dict[str, Any]]) -> str:
    return "".join(json.dumps(event) + "\n" for event in events)


def claude_stream(text: str, *, tool: bool = True) -> str:
    events: list[dict[str, Any]] = [
        {"type": "system", "subtype": "init", "session_id": "s", "model": "claude-sonnet-5"}
    ]
    if tool:
        events += [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "Bash",
                            "input": {"command": "ls"},
                        }
                    ],
                    "usage": {"input_tokens": 100, "output_tokens": 20},
                },
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_1",
                            "content": "README.md",
                            "is_error": False,
                        }
                    ],
                },
            },
        ]
    events += [
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": 150, "output_tokens": 30},
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": text,
            "total_cost_usd": 0.05,
            "modelUsage": {
                "claude-sonnet-5": {
                    "inputTokens": 250,
                    "outputTokens": 50,
                    "cacheReadInputTokens": 0,
                    "cacheCreationInputTokens": 0,
                    "costUSD": 0.05,
                    "contextWindow": 1000000,
                }
            },
        },
    ]
    return _jsonl(events)


def pi_stream(text: str, *, tool: bool = True) -> str:
    usage = {"input": 100, "output": 20, "cacheRead": 0, "cacheWrite": 0, "cost": {"total": 0.01}}
    events: list[dict[str, Any]] = []
    if tool:
        events += [
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "toolCall",
                            "id": "call_1",
                            "name": "bash",
                            "arguments": {"command": "ls"},
                        }
                    ],
                    "usage": usage,
                    "stopReason": "toolUse",
                },
            },
            {
                "type": "tool_execution_start",
                "toolCallId": "call_1",
                "toolName": "bash",
                "args": {"command": "ls"},
            },
            {
                "type": "tool_execution_end",
                "toolCallId": "call_1",
                "toolName": "bash",
                "result": {"content": [{"type": "text", "text": "README.md"}]},
                "isError": False,
            },
        ]
    events.append(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
                "usage": usage,
                "stopReason": "stop",
            },
        }
    )
    return _jsonl(events)


def codex_stream(
    text: str,
    *,
    thread_id: str = THREAD_ID,
    usage: dict[str, int] | None = None,
    tool: bool = True,
) -> str:
    events: list[dict[str, Any]] = [
        {"type": "thread.started", "thread_id": thread_id},
        {"type": "turn.started"},
    ]
    if tool:
        command = {"id": "item_1", "type": "command_execution", "command": "ls"}
        events += [
            {
                "type": "item.started",
                "item": {
                    **command,
                    "aggregated_output": "",
                    "exit_code": None,
                    "status": "in_progress",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    **command,
                    "aggregated_output": "README.md\n",
                    "exit_code": 0,
                    "status": "completed",
                },
            },
        ]
    events += [
        {"type": "item.completed", "item": {"id": "item_9", "type": "agent_message", "text": text}},
        {
            "type": "turn.completed",
            "usage": usage
            or {
                "input_tokens": 1000,
                "cached_input_tokens": 0,
                "output_tokens": 100,
                "reasoning_output_tokens": 0,
            },
        },
    ]
    return _jsonl(events)


def stream(name: str, text: str, *, turn: int = 1) -> str:
    """A scripted turn for harness ``name`` whose final answer is ``text``."""
    if name == "claude":
        return claude_stream(text)
    if name == "pi":
        return pi_stream(text)
    spent = 1000 * turn
    return codex_stream(
        text,
        usage={
            "input_tokens": spent,
            "cached_input_tokens": 0,
            "output_tokens": spent // 10,
            "reasoning_output_tokens": 0,
        },
    )


def envelope_text(**fields: Any) -> str:
    return json.dumps({"status": "success", "summary": "done", **fields})


# ── engine environment ──────────────────────────────────────────────────────


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def build_repo(repo: Path) -> None:
    """A git repo with one commit: ``README.md`` and ``protected.md``."""
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "tester@example.com")
    _git(repo, "config", "user.name", "tester")
    (repo / "README.md").write_text("readme\n", encoding="utf-8", newline="\n")
    (repo / "protected.md").write_text("protected\n", encoding="utf-8", newline="\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")


def rows(db: Path, sql: str, *args: object) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(db)
    try:
        return list(conn.execute(sql, args).fetchall())
    finally:
        conn.close()


@dataclass
class HarnessEnv:
    cfg: SSSFConfig
    repo: Path
    db_path: Path
    data_dir: Path
    spawner: FakeSpawner
    module: ModuleType


def write_config(
    root: Path, agents_spec: dict[str, dict[str, Any]], data_dir: Path, db_path: Path
) -> Path:
    """Prompts plus a roster YAML; each agent entry spells out its own ``harness``."""
    prompts = root / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "system.md").write_text("system\n", encoding="utf-8", newline="\n")
    (prompts / "user.md").write_text("{{prompt}}\n", encoding="utf-8", newline="\n")
    engineering = {"system": str(prompts / "system.md"), "user": str(prompts / "user.md")}
    roster = [
        {"name": name, "prompt_engineering": engineering, **spec}
        for name, spec in agents_spec.items()
    ]
    config = {
        "defaults": {"data_dir": str(data_dir), "protected_files": ["protected.md"]},
        "observability": {"db": str(db_path)},
        "agents": roster,
    }
    path = root / "factory.config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8", newline="\n")
    return path


def make_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    *,
    agent: str = "builder",
    extra_agents: dict[str, dict[str, Any]] | None = None,
) -> HarnessEnv:
    """A temp repo, a roster with ``harness: <name>`` and every harness spawn faked."""
    repo = tmp_path / "repo"
    build_repo(repo)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("ENGINEER_NAME", "tester")
    data_dir = tmp_path / "data"
    db_path = data_dir / "sssf.db"
    spec = {agent: {"harness": name, "model": MODELS[name]}, **(extra_agents or {})}
    cfg = load_config(write_config(tmp_path, spec, data_dir, db_path))
    fake_pi_catalog(monkeypatch, tmp_path)
    for each in NAMES:
        monkeypatch.setitem(agents.INTERFACES, each, harness.load(each))
    spawner = fake_popen(monkeypatch)
    # The engine installs SIGINT/SIGTERM handlers per run; keep pytest's own.
    monkeypatch.setattr(session, "_finalize_when_killed", lambda run: None)
    return HarnessEnv(cfg, repo, db_path, data_dir, spawner, harness.load(name))


def start_run(env: HarnessEnv, adw_id: str = "h0000001") -> Run:
    run = session.ensure(env.cfg, adw_id)
    assert isinstance(run, Run)
    return run


def agent_phase(
    run: Run,
    owner: str,
    *,
    retries: int = 0,
    gates: Sequence[Callable[..., Any]] = (),
    prompt: str = "do it",
) -> EnvelopeBase:
    """Open one agent phase owned by ``owner`` and make its single agent call."""
    params = PhaseParams(
        name=owner,
        kind="agent",
        owner=owner,
        description=f"Run the {owner} agent for the test",
        retries=retries,
    )
    with run.phase(params) as ph:
        envelope = ph.call(AgentCall(output_type=GenericOutput, prompt=prompt, gates=list(gates)))
    assert isinstance(envelope, EnvelopeBase)
    return envelope


def events_of(db: Path, phase_id: str) -> list[tuple[str, str, dict[str, Any]]]:
    found = rows(
        db,
        "SELECT type, name, payload_json FROM events WHERE phase_id=? ORDER BY rowid",
        phase_id,
    )
    return [(str(t), str(n), json.loads(p)) for t, n, p in found]
