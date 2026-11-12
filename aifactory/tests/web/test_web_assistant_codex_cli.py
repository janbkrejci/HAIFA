"""Offline audit of the installed CLI against a fake Responses server and real MCP gate.

No credentials or live models/services. Skip when the audited CLI is not installed;
the guide itself refuses those versions. Unit tests cover that refusal separately.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from aifactory.engine.data_types import AgentRequest, AgentResult
from aifactory.engine.utils import agent_environment
from aifactory.harness import codex
from aifactory.web import assistant_codex as guide


@pytest.fixture
def audited_cli() -> str:
    executable = shutil.which(codex.CODEX_PATH)
    if executable is None:
        pytest.skip("Codex CLI is not installed (offline CLI audit only)")
    version = subprocess.run(
        codex.launch_command([executable, "--version"]),
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    ).stdout.strip()
    if version != guide.SUPPORTED_VERSION:
        pytest.skip(f"guide refuses {version}; this audit is for {guide.SUPPORTED_VERSION}")
    return executable


class FakeModel(ThreadingHTTPServer):
    requests: list[dict[str, Any]]
    env_file: Path
    marker: Path

    def __init__(self, root: Path) -> None:
        super().__init__(("127.0.0.1", 0), Handler)
        self.requests = []
        self.env_file = root / ".env"
        self.marker = root / "unexpected-write"


class Handler(BaseHTTPRequestHandler):
    server: FakeModel

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_POST(self) -> None:
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        index = len(self.server.requests)
        self.server.requests.append(request)
        item: dict[str, Any]
        if index == 0:
            # Deliberately return an unadvertised native tool. The registry must
            # reject it even if a model hallucinates a shell call.
            item = {
                "type": "function_call",
                "id": f"fc_{index}",
                "call_id": f"call_{index}",
                "name": "exec_command",
                "arguments": json.dumps(
                    {"cmd": f'cat "{self.server.env_file}"; echo bad > "{self.server.marker}"'}
                ),
            }
        elif index in (1, 2):
            argv = ["shell", "cat", str(self.server.env_file)] if index == 1 else ["repos"]
            item = {
                "type": "function_call",
                "id": f"fc_{index}",
                "call_id": f"call_{index}",
                "namespace": "mcp__haifa_guide",
                "name": "guide",
                "arguments": json.dumps({"argv": argv}),
            }
        else:
            item = {
                "type": "message",
                "id": f"msg_{index}",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "safe answer", "annotations": []}],
            }
        response = {
            "id": f"resp_{index}",
            "object": "response",
            "status": "completed",
            "output": [item],
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        }
        events: list[tuple[str, dict[str, Any]]] = [
            (
                "response.created",
                {"response": {"id": response["id"], "status": "in_progress", "output": []}},
            ),
            ("response.output_item.done", {"output_index": 0, "item": item}),
            ("response.completed", {"response": response}),
        ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for kind, data in events:
            self.wfile.write(
                f"event: {kind}\ndata: {json.dumps({'type': kind, **data})}\n\n".encode()
            )


@pytest.fixture
def model_server(tmp_path: Path) -> Iterator[FakeModel]:
    server = FakeModel(tmp_path)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


@pytest.mark.parametrize("model", ["gpt-5.5", "gpt-6.1-sol"])
def test_native_tools_are_absent_and_hallucinated_shell_is_blocked_on_new_and_resumed_turns(
    audited_cli: str,
    model_server: FakeModel,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    model: str,
) -> None:
    monkeypatch.setattr(codex, "CODEX_PATH", audited_cli)
    monkeypatch.setattr(codex, "CODEX_SANDBOX", "danger-full-access")
    home = tmp_path / "haifa"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    # Ambient operator configuration/instructions must never enter the guide.
    (codex_home / "config.toml").write_text('developer_instructions = "AMBIENT_CONFIG_SENTINEL"\n')
    (codex_home / "AGENTS.md").write_text("AMBIENT_INSTRUCTIONS_SENTINEL")
    skill = codex_home / "skills" / "ambient" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: ambient\ndescription: AMBIENT_SKILL_SENTINEL\n---\nSKILL_BODY_SENTINEL"
    )
    secret = "OFFLINE_GUIDE_ENV_SECRET_1729"
    model_server.env_file.write_text(f"SECRET={secret}\n")
    request = AgentRequest(
        prompt="Diagnose the run. $ambient",
        system_prompt="Use ./guide to read data.",
        model=model,
        thinking="low",
        session_id="guide-offline-audit",
        session_dir=str(tmp_path / "sessions"),
        raw_output_path=str(tmp_path / "raw.jsonl"),
        cwd=str(work),
        allowed_commands=["./guide", "./guide *"],
    )
    real_run = codex.run

    def run_fake_provider(
        request: AgentRequest, *, extra_args: list[str], **kw: Any
    ) -> AgentResult:
        # Only the test changes the provider. Production shares the operator's
        # file login with the isolated home, without cloning refresh tokens.
        provider = {
            "name": "Offline guide test",
            "base_url": f"http://127.0.0.1:{model_server.server_port}/v1",
            "wire_api": "responses",
            "request_max_retries": 0,
            "stream_max_retries": 0,
        }
        return real_run(
            request,
            extra_args=[
                *extra_args,
                "-c",
                'model_provider="offline"',
                "-c",
                f"model_providers.offline={guide._toml(provider)}",
            ],
            **kw,
        )

    monkeypatch.setattr(codex, "run", run_fake_provider)
    events: list[dict[str, Any]] = []
    with agent_environment({"CODEX_HOME": str(codex_home)}):
        first = guide.run(request, home=home, repo_id=None, on_event=events.append)
        state = json.loads(codex.state_path(request).read_text())
        second = guide.run(request, home=home, repo_id=None, on_event=events.append)
    assert first.text == second.text == "safe answer"
    assert state["thread_id"] == json.loads(codex.state_path(request).read_text())["thread_id"]
    assert not model_server.marker.exists()
    assert model_server.env_file.read_text() == f"SECRET={secret}\n"
    wire = json.dumps(model_server.requests)
    assert secret not in wire
    for sentinel in (
        "AMBIENT_CONFIG_SENTINEL",
        "AMBIENT_INSTRUCTIONS_SENTINEL",
        "AMBIENT_SKILL_SENTINEL",
        "SKILL_BODY_SENTINEL",
    ):
        assert sentinel not in wire
    assert len(model_server.requests) == 5
    for payload in model_server.requests:
        tools = payload["tools"]
        assert {tool.get("name") for tool in tools} == {
            "list_mcp_resources",
            "list_mcp_resource_templates",
            "read_mcp_resource",
            "mcp__haifa_guide",
        }
        namespace = next(tool for tool in tools if tool.get("name") == "mcp__haifa_guide")
        assert [tool["name"] for tool in namespace["tools"]] == ["guide"]
    final_input = model_server.requests[3]["input"]
    outputs = {
        item["call_id"]: str(item["output"])
        for item in final_input
        if item.get("type") == "function_call_output"
    }
    assert "unsupported" in outputs["call_0"]
    assert "refused" in outputs["call_1"]
    assert "data" in outputs["call_2"]
    assert any(event.get("type") == "item.completed" for event in events)
