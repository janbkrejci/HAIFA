"""The Codex guide uses the gate, with no path back to unrestricted task tools."""

from __future__ import annotations

import io
import json
import sqlite3
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
from multi_repo import init_repo, install, multi_client, register

from aifactory.engine.data_types import AgentRequest, AgentResult
from aifactory.harness import codex
from aifactory.home import haifa_home
from aifactory.web import assistant_codex as guide
from aifactory.web import assistant_gate as gate
from aifactory.web import assistant_mcp as mcp


@pytest.fixture(autouse=True)
def isolated_operator_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "operator-codex"))


def request_at(tmp_path: Path) -> AgentRequest:
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    return AgentRequest(
        prompt="Why did the run fail?",
        system_prompt="Use ./guide to read data.",
        model="gpt-5.5",
        thinking="medium",
        session_id="guide-test",
        session_dir=str(tmp_path / "sessions"),
        raw_output_path=str(tmp_path / "raw.jsonl"),
        cwd=str(work),
        allowed_commands=["./guide", "./guide *"],
    )


def fake_inspect(monkeypatch: pytest.MonkeyPatch, version: str = guide.SUPPORTED_VERSION) -> None:
    def inspect(args: list[str], cwd: str) -> str:
        if args == ["--version"]:
            return version
        assert args == ["debug", "models", "--bundled"]
        return json.dumps(
            {
                "models": [
                    {"slug": "gpt-5.5", "context_window": 272000, "shell_type": "unified_exec"}
                ]
            }
        )

    monkeypatch.setattr(guide, "_inspect", inspect)


def test_guide_launch_removes_model_tools_and_fixes_mcp_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_inspect(monkeypatch)
    request = request_at(tmp_path)
    args = guide.launch_args(request, tmp_path / "HAIFA home", "alpha")
    configs = [args[i + 1] for i, value in enumerate(args) if value == "-c"]
    config = tomllib.loads("\n".join(configs))
    server = config["mcp_servers"]["haifa_guide"]
    assert set(config["mcp_servers"]) == {"haifa_guide"}
    assert server["required"] is True
    assert server["enabled_tools"] == ["guide"]
    assert server["args"][-2:] == ["--repo", "alpha"]
    assert server["env"]["HAIFA_GUIDE_REPO"] == "alpha"
    assert config["features"]["shell_tool"] is False
    assert config["features"]["view_image"] is False
    assert config["features"]["plugins"] is False
    assert config["skills"]["include_instructions"] is False
    assert "--ignore-rules" in args and "--strict-config" in args
    catalog = json.loads(Path(config["model_catalog_json"]).read_text())
    model = catalog["models"][0]
    assert model["context_window"] == 272000
    assert model["apply_patch_tool_type"] is None
    assert model["shell_type"] == "disabled"
    assert model["experimental_supported_tools"] == []
    assert model["multi_agent_version"] is None
    assert model["node_repl_disabled"] is True
    assert model["tool_mode"] == "direct"


@pytest.mark.parametrize("thread", ["", "resumed-thread"])
def test_guide_overrides_apply_on_resume_without_changing_task_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, thread: str
) -> None:
    fake_inspect(monkeypatch)
    monkeypatch.setattr(codex, "CODEX_SANDBOX", "danger-full-access")
    monkeypatch.delenv("CODEX_SAFE_MODE", raising=False)
    request = request_at(tmp_path)
    extra = guide.launch_args(request, tmp_path, None)
    restricted = codex.build_command(request, thread, extra_args=extra)
    assert restricted.index("--strict-config") < restricted.index("--")
    assert 'sandbox_mode="read-only"' in restricted
    request.allowed_commands = []
    ordinary = codex.build_command(request, thread)
    assert 'sandbox_mode="danger-full-access"' in ordinary
    assert "--strict-config" not in ordinary
    assert "project_doc_max_bytes=0" not in ordinary
    assert not any("shell_tool=" in arg or "model_catalog_json=" in arg for arg in ordinary)


def test_run_keeps_request_and_callbacks_and_does_not_modify_task_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_inspect(monkeypatch)
    original = request_at(tmp_path)
    seen: list[AgentRequest] = []

    def callback(event: dict[str, Any]) -> None:
        pass

    def run(request: AgentRequest, **kwargs: Any) -> AgentResult:
        seen.append(request)
        assert kwargs["on_event"] is callback
        assert "--strict-config" in kwargs["extra_args"]
        return AgentResult(text="answer", returncode=0)

    monkeypatch.setattr(codex, "run", run)
    assert guide.run(original, home=tmp_path, repo_id=None, on_event=callback).text == "answer"
    assert "Transport:" not in original.system_prompt
    assert "haifa_guide MCP" in seen[0].system_prompt
    assert seen[0].session_id == original.session_id


@pytest.mark.parametrize("failure", ["version", "model", "default_allowlist", "timeout"])
def test_isolation_failure_never_starts_the_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    fake_inspect(
        monkeypatch, "codex-cli 0.168.0" if failure == "version" else guide.SUPPORTED_VERSION
    )
    request = request_at(tmp_path)
    if failure == "model":
        request.model = "unlisted-model"
    if failure == "default_allowlist":
        request.allowed_commands = []
    if failure == "timeout":

        def timeout(*args: Any, **kwargs: Any) -> str:
            raise subprocess.TimeoutExpired("codex --version", 30)

        monkeypatch.setattr(guide, "_inspect", timeout)

    def forbidden(*args: Any, **kwargs: Any) -> AgentResult:
        pytest.fail("a failed isolation check must not start the agent")

    monkeypatch.setattr(codex, "run", forbidden)
    with pytest.raises((ValueError, subprocess.TimeoutExpired)):
        guide.run(request, home=tmp_path, repo_id=None)


@pytest.mark.parametrize("catalog", [{}, {"models": []}, {"models": "bad"}])
def test_missing_catalog_never_uses_default_model_tools(catalog: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        guide.restricted_catalog(catalog, "gpt-5.5")


@pytest.mark.skipif(sys.platform == "win32", reason="Windows symlink support is optional")
def test_isolated_home_shares_only_the_login_file(tmp_path: Path) -> None:
    original = tmp_path / "operator-codex"
    original.mkdir()
    auth = original / "auth.json"
    auth.write_text("fake login, no credentials")
    (original / "AGENTS.md").write_text("must stay out of the guide")
    directory = guide.isolated_home(tmp_path / "haifa")
    assert (directory / "auth.json").is_symlink()
    assert (directory / "auth.json").resolve() == auth.resolve()
    assert not (directory / "AGENTS.md").exists()
    assert not (directory / "skills").exists()
    # A refresh replaces the shared file; the link still sees the current login.
    refreshed = original / "refreshed.json"
    refreshed.write_text("refreshed fake login")
    refreshed.replace(auth)
    assert (directory / "auth.json").read_text() == "refreshed fake login"


def test_missing_symlink_support_never_falls_back_to_operator_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_inspect(monkeypatch)
    original = tmp_path / "operator-codex"
    original.mkdir()
    (original / "auth.json").write_text("fake login")

    def refuse_link(*args: Any, **kwargs: Any) -> None:
        raise OSError("Windows symlink privilege is not available")

    def forbidden(*args: Any, **kwargs: Any) -> AgentResult:
        pytest.fail("must not fall back to an unrestricted home")

    monkeypatch.setattr(Path, "symlink_to", refuse_link)
    monkeypatch.setattr(codex, "run", forbidden)
    with pytest.raises(ValueError, match="Developer Mode"):
        guide.run(request_at(tmp_path), home=tmp_path, repo_id=None)


def test_separate_guide_login_works_without_symlink_privileges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = tmp_path / "operator-codex"
    original.mkdir()
    (original / "auth.json").write_text("fake operator login")
    directory = tmp_path / "haifa" / "assistant" / "codex"
    directory.mkdir(parents=True)
    (directory / "auth.json").write_text("fake guide login")

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("an existing guide login needs no symlink")

    monkeypatch.setattr(Path, "symlink_to", forbidden)
    assert guide.isolated_home(tmp_path / "haifa") == directory.resolve()
    assert (directory / "auth.json").read_text() == "fake guide login"
    assert (original / "auth.json").read_text() == "fake operator login"


def test_conflicting_concurrent_login_initialization_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = tmp_path / "operator-codex"
    original.mkdir()
    (original / "auth.json").write_text("fake operator login")

    def conflicting(path: Path, *args: Any, **kwargs: Any) -> None:
        path.write_text("unexpected file")
        raise FileExistsError()

    monkeypatch.setattr(Path, "symlink_to", conflicting)
    with pytest.raises(ValueError, match="does not point"):
        guide.isolated_home(tmp_path / "haifa")


def test_guide_home_with_instructions_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "assistant" / "codex"
    directory.mkdir(parents=True)
    (directory / "AGENTS.override.md").write_text("unexpected context")
    with pytest.raises(ValueError, match="must not contain"):
        guide.isolated_home(tmp_path)


def call(argv: list[str]) -> dict[str, Any]:
    return {"method": "tools/call", "params": {"name": "guide", "arguments": {"argv": argv}}}


def test_mcp_reads_redacted_scoped_data_and_refuses_writes(tmp_path: Path) -> None:
    home = haifa_home()
    repos = [init_repo(tmp_path / name) for name in ("alpha", "beta")]
    client = multi_client(home, tmp_path)
    for repo in repos:
        install(repo)
    ids = [register(client, repo)["id"] for repo in repos]
    secret = "guide-mcp-secret-value"
    (repos[0] / ".env").write_text(f"TOKEN={secret}\n")
    db = repos[0] / ".factory" / "trace.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE example (value TEXT)")
        conn.execute("INSERT INTO example VALUES (?)", (secret,))
    listed = mcp.dispatch(call(["repos"]), home, ids[0])
    assert json.loads(listed["content"][0]["text"])["data"] == [
        {"id": ids[0], "path": str(repos[0])}
    ]
    read = mcp.dispatch(call(["sql", ids[0], "SELECT * FROM example"]), home, ids[0])
    assert not read["isError"]
    assert secret not in str(read)
    assert "[redacted]" in str(read)
    before = db.read_bytes()
    for argv in (
        ["factory", ids[0], "task", "run", "X"],
        ["factory", ids[0], "config", "show", ".env"],
        ["sql", ids[0], "DELETE FROM example"],
        ["sql", ids[0], "ATTACH DATABASE '.env' AS secrets"],
        ["sql", ids[1], "SELECT 1"],
        ["shell", "cat", str(repos[0] / ".env")],
    ):
        assert mcp.dispatch(call(argv), home, ids[0])["isError"], argv
    assert db.read_bytes() == before


@pytest.mark.parametrize(
    "message",
    [
        {"method": "resources/read", "params": {"uri": "file:///.env"}},
        {"method": "tools/call", "params": {"name": "shell", "arguments": {"argv": ["ls"]}}},
        {"method": "tools/call", "params": {"name": "guide", "arguments": {"argv": "cat .env"}}},
        {"method": "tools/call", "params": {"name": "guide", "arguments": {"argv": [None]}}},
        {
            "method": "tools/call",
            "params": {"name": "guide", "arguments": {"argv": ["repos"], "repo_id": "beta"}},
        },
    ],
)
def test_mcp_rejects_invalid_calls_before_accessing_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, message: dict[str, Any]
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("invalid MCP calls must not reach the gate")

    monkeypatch.setattr(gate, "execute", forbidden)
    with pytest.raises(ValueError):
        mcp.dispatch(message, tmp_path, "alpha")


def test_stdio_protocol_does_not_disclose_internal_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: Any, **kwargs: Any) -> None:
        raise OSError("secret-in-internal-error")

    monkeypatch.setattr(gate, "execute", broken)
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26"},
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, **call(["repos"])},
    ]
    target = io.StringIO()
    mcp.serve(tmp_path, None, io.StringIO("\n".join(map(json.dumps, messages))), target)
    responses = [json.loads(line) for line in target.getvalue().splitlines()]
    assert [item["id"] for item in responses] == [1, 2, 3]
    assert responses[0]["result"]["protocolVersion"] == "2025-03-26"
    assert [tool["name"] for tool in responses[1]["result"]["tools"]] == ["guide"]
    assert responses[2]["error"]["code"] == -32603
    assert "secret-in-internal-error" not in target.getvalue()
