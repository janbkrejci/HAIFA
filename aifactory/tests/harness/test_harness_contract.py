"""Contract: claude, codex and pi answer to one interface and leave one trace shape."""

from __future__ import annotations

import inspect
import json
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from harness_fakes import (
    MODELS,
    NAMES,
    PID,
    THREAD_ID,
    agent_phase,
    build_repo,
    envelope_text,
    events_of,
    fake_pi_catalog,
    fake_popen,
    fixture_text,
    make_env,
    normalize,
    rows,
    start_run,
    stream,
)

from aifactory import harness
from aifactory.engine import agent_cc, agent_pi
from aifactory.engine.data_types import AgentRequest, EnvelopeBase, GateCheck, GateReport
from aifactory.engine.runner import Run
from aifactory.harness import codex

SYSTEM_PROMPT = 'You are "builder".\nReply with JSON only.'
RECORD_KEYS = {"tool", "tool_call_id", "args", "ok", "label", "result_snippet"}
CORRECTION_PREFIX = "Your previous response failed validation:"

EXPECTED: dict[str, dict[str, Any]] = {
    "claude": {
        "model": "claude-opus-5",
        "fixture": "claude_turn.jsonl",
        "text": '{"status":"success"}',
        "tokens": 450,
        "cost": 0.05,
        "usage": {"input_tokens": 250, "output_tokens": 50, "cache_read_tokens": 150},
        "records": [
            {
                "tool": "Bash",
                "tool_call_id": "toolu_1",
                "args": {"command": "ls"},
                "ok": True,
                "label": "Bash: ls",
                "result_snippet": "README.md\nsrc",
            }
        ],
    },
    "pi": {
        "model": "openai/gpt-5.5",
        "fixture": "pi_turn.jsonl",
        "text": '{"status":"success"}',
        "tokens": 450,
        "cost": 0.03,
        "usage": {"input_tokens": 250, "output_tokens": 50, "cache_read_tokens": 150},
        "records": [
            {
                "tool": "bash",
                "tool_call_id": "call_1",
                "args": {"command": "ls"},
                "ok": True,
                "label": "bash: ls",
                "result_snippet": "README.md\nsrc",
            }
        ],
    },
    "codex": {
        "model": "gpt-5.5",
        "fixture": "codex_turn.jsonl",
        "text": "not json",
        "tokens": 1500,
        "cost": 0.0,
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 300,
            "cache_read_tokens": 200,
            "reasoning_tokens": 100,
        },
        "records": [
            {
                "tool": "bash",
                "tool_call_id": "item_1",
                "args": {"command": "ls"},
                "ok": True,
                "label": "bash: ls",
                "result_snippet": "README.md\nsrc\n",
            },
            {
                "tool": "edit",
                "tool_call_id": "item_2",
                "args": {
                    "path": "src/app.py",
                    "changes": [{"path": "src/app.py", "kind": "update"}],
                },
                "ok": True,
                "label": "edit: src/app.py",
                "result_snippet": "update src/app.py",
            },
        ],
    },
}


@pytest.fixture
def registered(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    """Registered harnesses, with pi's model catalog faked (no `pi --list-models`)."""
    agents = harness.install()
    fake_pi_catalog(monkeypatch, tmp_path)
    return agents


def _request(tmp_path: Path, model: str, prompt: str = "list the repo") -> AgentRequest:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    return AgentRequest(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        model=model,
        thinking="high",
        session_id="sssf-adw1-builder-abc",
        session_dir=str(tmp_path / "sessions"),
        raw_output_path=str(tmp_path / "raw_output.jsonl"),
        cwd=str(repo),
    )


class Collector:
    def __init__(self, module: ModuleType) -> None:
        self.tracker = module.ToolCallTracker()
        self.records: list[dict[str, Any]] = []
        self.spawned: list[int] = []
        self.exited: list[int] = []

    def on_event(self, event: dict[str, Any]) -> None:
        record = self.tracker.observe(event)
        if record is not None:
            self.records.append(record)

    def run(self, module: ModuleType, request: AgentRequest) -> Any:
        return module.run(
            request,
            on_event=self.on_event,
            on_spawn=self.spawned.append,
            on_exit=self.exited.append,
        )


# ── 1. the adapter on its own ───────────────────────────────────────────────


@pytest.mark.parametrize("name", NAMES)
def test_harness_interface_is_shared(registered: ModuleType, name: str) -> None:
    module = registered.INTERFACES[name]
    assert harness.check_interface(module) == []
    params = inspect.signature(module.run).parameters
    for param in ("request", "on_event", "on_spawn", "on_exit", "on_wait"):
        assert param in params


@pytest.mark.parametrize("name", NAMES)
def test_harness_recorded_turn_gives_expected_result(
    registered: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    expected = EXPECTED[name]
    module = registered.INTERFACES[name]
    spawner = fake_popen(monkeypatch, [expected["fixture"]])
    request = _request(tmp_path, expected["model"])
    collector = Collector(module)

    result = collector.run(module, request)

    assert result.text == expected["text"]
    assert result.tokens == expected["tokens"]
    assert result.cost == pytest.approx(expected["cost"])
    for field, value in expected["usage"].items():
        assert getattr(result.usage, field) == value, field
    assert normalize(collector.records) == expected["records"]
    for record in collector.records:
        assert set(record) - {"started_at", "ended_at", "duration_ms"} <= RECORD_KEYS
        assert "ended_at" in record
    assert collector.spawned == [PID]
    assert collector.exited == [PID]
    assert Path(request.raw_output_path).read_text() == fixture_text(expected["fixture"])
    (call,) = spawner.calls
    assert call.kwargs["cwd"] == request.cwd
    assert call.kwargs["stdin"] is subprocess.DEVNULL


def test_harness_codex_first_turn_command(
    registered: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawner = fake_popen(monkeypatch, ["codex_turn.jsonl"])
    request = _request(tmp_path, "gpt-5.5")
    codex.run(request)

    cmd = spawner.calls[0].cmd
    assert cmd[:2] == [codex.CODEX_PATH, "exec"]
    assert "resume" not in cmd
    assert "--json" in cmd
    assert cmd[cmd.index("-m") + 1] == "gpt-5.5"
    assert cmd[cmd.index("-C") + 1] == request.cwd
    assert f"developer_instructions={json.dumps(SYSTEM_PROMPT)}" in cmd
    assert 'model_reasoning_effort="high"' in cmd
    assert cmd[-1] == request.prompt
    state = json.loads(codex.state_path(request).read_text())
    assert state["thread_id"] == THREAD_ID


def test_harness_codex_correction_turn_resumes_same_thread(
    registered: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawner = fake_popen(monkeypatch, ["codex_turn.jsonl", "codex_resume.jsonl"])
    collector = Collector(codex)
    collector.run(codex, _request(tmp_path, "gpt-5.5"))

    correction = _request(tmp_path, "gpt-5.5", prompt="Your reply was not valid JSON. Fix it.")
    result = collector.run(codex, correction)

    call = spawner.calls[1]
    assert call.cmd[:3] == [codex.CODEX_PATH, "exec", "resume"]
    assert "-C" not in call.cmd
    assert call.cmd[-2:] == [THREAD_ID, correction.prompt]
    assert f"developer_instructions={json.dumps(SYSTEM_PROMPT)}" in call.cmd
    assert call.kwargs["cwd"] == correction.cwd
    assert result.text == '{"status":"success"}'
    assert result.tokens == (2000 - 1200) + (450 - 300)
    assert result.usage.cache_read_tokens == 300
    assert result.usage.input_tokens == 800 - 300
    assert result.usage.reasoning_tokens == 50
    assert result.cost == 0.0
    assert collector.spawned == [PID, PID]


def test_harness_codex_counter_reset_is_taken_as_is(
    registered: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_popen(monkeypatch, ["codex_resume.jsonl", "codex_turn.jsonl"])
    codex.run(_request(tmp_path, "gpt-5.5"))
    result = codex.run(_request(tmp_path, "gpt-5.5"))
    assert result.tokens == 1200 + 300


def test_harness_codex_failed_turn_raises(
    registered: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_popen(monkeypatch, ["codex_failed.jsonl"], returncode=1, stderr="boom")
    with pytest.raises(RuntimeError, match="not available"):
        codex.run(_request(tmp_path, "gpt-5.5"))


@pytest.mark.parametrize("pattern", ["gpt-5.5", "openai/gpt-5.5"])
def test_harness_codex_resolve_model_accepts_openai(pattern: str) -> None:
    assert codex.resolve_model(pattern) == ("openai", "gpt-5.5")


@pytest.mark.parametrize(
    "pattern", ["", "anthropic/claude-opus-5", "claude-opus-5", "opus", "google/gemini-x"]
)
def test_harness_codex_resolve_model_rejects_others(pattern: str) -> None:
    with pytest.raises(ValueError):
        codex.resolve_model(pattern)


def test_harness_codex_sandbox_setting(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    request = _request(tmp_path, "gpt-5.5")
    default = codex.build_command(request)
    assert "--dangerously-bypass-approvals-and-sandbox" in default

    monkeypatch.setattr(codex, "CODEX_SANDBOX", "workspace-write")
    for thread in ("", THREAD_ID):
        cmd = codex.build_command(request, thread)
        assert 'sandbox_mode="workspace-write"' in cmd
        assert "--dangerously-bypass-approvals-and-sandbox" not in cmd
        assert "-s" not in cmd


@pytest.mark.parametrize("thinking", ["low", "medium", "high", "xhigh", "max"])
def test_codex_sol_effort_and_context(tmp_path: Path, thinking: str) -> None:
    request = _request(tmp_path, "openai/gpt-6.1-sol")
    request.thinking = thinking
    for thread in ("", THREAD_ID):
        cmd = codex.build_command(request, thread)
        assert cmd[cmd.index("-m") + 1] == "gpt-6.1-sol"
        assert f'model_reasoning_effort="{thinking}"' in cmd
        assert cmd[-1] == request.prompt
    assert codex.context_window("openai", "gpt-6.1-sol") == 1_050_000
    assert codex.reasoning_effort("gpt-5.5", "max") == "xhigh"


@pytest.mark.parametrize("thinking", ["off", "minimal", "invalid"])
def test_codex_sol_rejects_unsupported_effort(thinking: str) -> None:
    with pytest.raises(ValueError):
        codex.reasoning_effort("gpt-6.1-sol", thinking)


# ── 2. through the engine: one envelope shape ───────────────────────────────


def test_harness_envelope_shape_is_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    envelopes: dict[str, dict[str, Any]] = {}
    envelope_rows: dict[str, list[tuple[Any, ...]]] = {}
    for name in NAMES:
        with monkeypatch.context() as mp:
            env = make_env(tmp_path / name, mp, name)
            env.spawner.add(stream(name, envelope_text(artifacts=["specs/x.md"])))
            run = start_run(env)
            envelope = agent_phase(run, "builder")
            assert envelope.summary == "done"
            envelopes[name] = json.loads(
                (run.session_dir / "builder" / "envelope.json").read_text()
            )
            found = rows(
                env.db_path,
                "SELECT output_type, valid, attempt, payload_json FROM envelopes"
                " WHERE phase_id=? ORDER BY created_at",
                f"{run.adw_id}_01_builder",
            )
            envelope_rows[name] = [(o, v, a, json.loads(p)) for o, v, a, p in found]
            assert len(env.spawner.calls) == 1
    assert envelopes["claude"] == envelopes["codex"] == envelopes["pi"]
    assert envelopes["claude"]["artifacts"] == ["specs/x.md"]
    assert envelope_rows["claude"] == envelope_rows["codex"] == envelope_rows["pi"]
    assert len(envelope_rows["claude"]) == 1


# ── 3. a correction round resumes the same session ──────────────────────────


def summary_fixed(envelope: EnvelopeBase, run: Run) -> GateReport:
    return GateReport(checks=[GateCheck(item="summary", ok=envelope.summary == "fixed")])


@pytest.mark.parametrize("name", NAMES)
def test_harness_correction_resumes_same_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    env = make_env(tmp_path, monkeypatch, name)
    env.spawner.add(
        stream(name, envelope_text(summary="wrong"), turn=1),
        stream(name, envelope_text(summary="fixed"), turn=2),
    )
    run = start_run(env)

    envelope = agent_phase(run, "builder", retries=1, gates=[summary_fixed])

    assert envelope.summary == "fixed"
    first, second = env.spawner.cmds
    assert second[-1].startswith(CORRECTION_PREFIX)
    session_id = run.agent_map["builder"]["session_id"]
    if name == "claude":
        conversation = agent_cc.session_uuid(session_id)
        assert first[first.index("--session-id") + 1] == conversation
        assert "--resume" not in first
        assert second[second.index("--resume") + 1] == conversation
        assert "--session-id" not in second
    elif name == "pi":
        for flag in ("--session-id", "--session-dir"):
            assert first[first.index(flag) + 1] == second[second.index(flag) + 1]
        assert first[first.index("--session-id") + 1] == session_id
    else:
        assert first[:2] == [codex.CODEX_PATH, "exec"]
        assert "resume" not in first and "-C" in first
        assert second[:3] == [codex.CODEX_PATH, "exec", "resume"]
        assert "-C" not in second
        assert second[-2] == THREAD_ID
    phase_id = f"{run.adw_id}_01_builder"
    results = rows(
        env.db_path,
        "SELECT attempt, passed FROM gate_results WHERE phase_id=? ORDER BY id",
        phase_id,
    )
    assert results == [(1, 0), (2, 1)]


# ── 4. events land in the trace ─────────────────────────────────────────────


@pytest.mark.parametrize("name", NAMES)
def test_harness_events_are_traced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    env = make_env(tmp_path, monkeypatch, name)
    env.spawner.add(stream(name, envelope_text()))
    run = start_run(env)
    agent_phase(run, "builder")

    events = events_of(env.db_path, f"{run.adw_id}_01_builder")
    types = [t for t, _, _ in events]
    (start,) = [p for t, _, p in events if t == "agent_start"]
    assert start["coding_agent"] == name
    assert start["model"] == MODELS[name]
    tool_label = "Bash: ls" if name == "claude" else "bash: ls"
    tool_calls = [(n, p) for t, n, p in events if t == "tool_call"]
    assert tool_calls, types
    assert any(label == tool_label for label, _ in tool_calls)
    for _, payload in tool_calls:
        assert {"tool", "tool_call_id", "args", "ok", "agent"} <= set(payload)
        assert payload["agent"] == "builder"
    assert "handoff" in types
    assert "agent_end" in types
    assert types.index("agent_start") < types.index("tool_call") < types.index("agent_end")

    procs = rows(
        env.db_path,
        "SELECT name, ended_at FROM processes WHERE adw_id=? AND kind='agent' AND pid=?",
        run.adw_id,
        PID,
    )
    assert procs and procs[0][0] == "builder" and procs[0][1]
    sessions = rows(
        env.db_path,
        "SELECT coding_agent, model FROM agent_sessions WHERE adw_id=? AND agent='builder'",
        run.adw_id,
    )
    assert sessions == [(name, MODELS[name])]


# ── 5. the agent works in the directory its caller hands over ───────────────


@pytest.mark.parametrize("name", NAMES)
def test_harness_cwd_is_callers_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    env = make_env(tmp_path, monkeypatch, name)
    caller_dir = tmp_path / "caller_dir"
    build_repo(caller_dir)
    env.spawner.add(
        stream(name, envelope_text(summary="wrong"), turn=1),
        stream(name, envelope_text(summary="fixed"), turn=2),
    )
    run = start_run(env)
    run.repo_root = caller_dir

    agent_phase(run, "builder", retries=1, gates=[summary_fixed])

    assert caller_dir != Path.cwd()
    assert len(env.spawner.calls) == 2
    for call in env.spawner.calls:
        assert call.kwargs["cwd"] == str(caller_dir)
    if name == "codex":
        first = env.spawner.calls[0].cmd
        assert first[first.index("-C") + 1] == str(caller_dir)


def test_harness_pi_catalog_is_faked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_env(tmp_path, monkeypatch, "pi")
    assert agent_pi.resolve_model("openai/gpt-5.5") == ("openai", "gpt-5.5")
