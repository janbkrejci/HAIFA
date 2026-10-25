"""The hidden terminal: real local processes, no models or external services."""

from __future__ import annotations

import asyncio
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from starlette.requests import Request
from starlette.testclient import TestClient
from starlette.types import Message

from aifactory import oscompat
from aifactory.codeprint import CodeWatch
from aifactory.skill import envelope_problems
from aifactory.web import create_multi_app, terminal
from aifactory.web.server import allowed_hosts


def _client(tmp_path: Path, host: str = "127.0.0.1", peer: str = "127.0.0.1") -> TestClient:
    app = create_multi_app(
        home=tmp_path / "haifa",
        allowed_hosts=allowed_hosts(host),
        code_watch=CodeWatch(tmp_path / "code"),
    )
    return TestClient(app, base_url="http://127.0.0.1:4700", client=(peer, 12345))


def _python(code: str) -> str:
    argv = [sys.executable, "-u", "-c", code]
    return subprocess.list2cmdline(argv) if sys.platform == "win32" else shlex.join(argv)


def _events(client: TestClient, command: str, cwd: Path | None = None) -> list[dict[str, Any]]:
    body = {"command": command}
    if cwd is not None:
        body["cwd"] = str(cwd)
    response = client.post("/api/terminal/exec", json=body)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in response.text.splitlines()]


def test_get_and_echo(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/terminal")
        assert envelope_problems(response.json()) == []
        assert response.json()["data"] == {
            "enabled": True,
            "cwd": str(Path.home()),
            "shell": terminal._shell(),
            "pty": sys.platform != "win32",
        }
        events = _events(client, "echo terminal-output")
    assert "terminal-output" in "".join(e["text"] for e in events if e["type"] == "out")
    assert events[-1] == {"type": "exit", "code": 0, "cwd": str(Path.home().resolve())}


def test_stderr_utf8_exit_and_stdin(tmp_path: Path) -> None:
    command = _python(
        "import sys; assert sys.stdin.read() == ''; "
        "sys.stderr.buffer.write(b'bad\\xff'); sys.exit(7)"
    )
    with _client(tmp_path) as client:
        events = _events(client, command, tmp_path)
    assert {"type": "out", "stream": "stderr", "text": "bad\ufffd"} in events
    assert events[-1] == {"type": "exit", "code": 7, "cwd": str(tmp_path.resolve())}


def test_cd(tmp_path: Path) -> None:
    target = tmp_path / "with spaces"
    target.mkdir()
    with _client(tmp_path) as client:
        assert _events(client, 'cd "with spaces"', tmp_path) == [
            {"type": "exit", "code": 0, "cwd": str(target.resolve())}
        ]
        events = _events(client, "cd missing", target)
        assert events[0]["stream"] == "stderr"
        assert events[-1] == {"type": "exit", "code": 1, "cwd": str(target.resolve())}
        assert _events(client, "cd", target)[-1]["cwd"] == str(Path.home().resolve())
        events = _events(client, _python("import os; print(os.getcwd())"), target)
        assert str(target.resolve()) in "".join(e.get("text", "") for e in events)


@pytest.mark.parametrize(
    "host,peer", [("0.0.0.0", "127.0.0.1"), ("192.0.2.1", "127.0.0.1"), ("127.0.0.1", "192.0.2.2")]
)
def test_disabled(tmp_path: Path, host: str, peer: str) -> None:
    with _client(tmp_path, host, peer) as client:
        assert client.get("/api/terminal").json()["data"]["enabled"] is False
        response = client.post("/api/terminal/exec", json={"command": "echo forbidden"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "terminal_disabled"
    assert envelope_problems(response.json()) == []


@pytest.mark.parametrize(
    "headers,status,code",
    [
        ({"Origin": "http://evil.example"}, 403, "cross_origin"),
        ({"Sec-Fetch-Site": "cross-site"}, 403, "cross_origin"),
        ({"Content-Type": "text/plain"}, 415, "unsupported_media_type"),
    ],
)
def test_write_guard(tmp_path: Path, headers: dict[str, str], status: int, code: str) -> None:
    with _client(tmp_path) as client:
        response = client.post("/api/terminal/exec", json={"command": "echo no"}, headers=headers)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


@pytest.mark.parametrize(
    "body",
    [
        {"command": ""},
        {"command": "  "},
        {"command": 12},
        {"command": "echo no", "cwd": "/nonexistent-terminal-dir"},
        [],
        {"command": "echo no", "cwd": None},
    ],
)
def test_usage_error(tmp_path: Path, body: Any) -> None:
    with _client(tmp_path) as client:
        response = client.post("/api/terminal/exec", json=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "usage_error"


def test_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(terminal, "TERMINAL_TIMEOUT_S", 0.3)
    killed: list[int] = []
    real_kill = oscompat.kill_group

    def kill(pid: int, *, force: bool) -> None:
        killed.append(pid)
        real_kill(pid, force=force)

    monkeypatch.setattr(oscompat, "kill_group", kill)
    with _client(tmp_path) as client:
        events = _events(client, _python("import time; time.sleep(60)"), tmp_path)
    assert killed
    assert events[-1]["code"] == 124
    assert not oscompat.alive(killed[0])


def test_timeout_kills_parent_and_child_before_blocked_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(terminal, "TERMINAL_TIMEOUT_S", 2)

    def stopped(pid: int) -> bool:
        if not oscompat.alive(pid):
            return True
        if sys.platform == "win32":
            return False
        # An orphan killed with its parent may await reaping by the system's init.
        result = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
        )
        return not result.stdout.strip() or result.stdout.strip().startswith("Z")

    async def scenario() -> None:
        disconnect = asyncio.Event()
        sending_timeout = asyncio.Event()
        release_send = asyncio.Event()
        pids: list[int] = []
        stdout = ""

        async def receive() -> Message:
            await disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            nonlocal stdout
            if message["type"] != "http.response.body" or not message.get("body"):
                return
            event = json.loads(message["body"])
            if event.get("stream") == "stdout":
                stdout += event["text"]
                if "\n" in stdout:
                    pids[:] = json.loads(stdout)
            if "timed out" in event.get("text", ""):
                sending_timeout.set()
                await release_send.wait()

        command = _python(
            "import json, os, subprocess, sys; "
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
            "print(json.dumps([os.getpid(), child.pid]), flush=True); child.wait()"
        )

        async def body() -> Message:
            return {"type": "http.request", "body": json.dumps({"command": command}).encode()}

        request = Request(
            {"type": "http", "app": _client(tmp_path).app, "client": ("127.0.0.1", 12345)},
            body,
        )
        response = await terminal.terminal_exec(request)
        task = asyncio.create_task(
            response({"type": "http", "asgi": {"spec_version": "2.0"}}, receive, send)
        )
        try:
            await asyncio.wait_for(sending_timeout.wait(), timeout=10)
            assert len(pids) == 2, stdout
            for _ in range(100):
                if all(stopped(pid) for pid in pids):
                    break
                await asyncio.sleep(0.01)
            assert all(stopped(pid) for pid in pids)
            assert not release_send.is_set()
            assert not disconnect.is_set()
        finally:
            disconnect.set()
            await asyncio.wait_for(task, timeout=5)

    asyncio.run(scenario())


@pytest.mark.parametrize("blocked_send", [False, True])
def test_disconnect_streams_and_kills_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, blocked_send: bool
) -> None:
    monkeypatch.setattr(terminal, "TERMINAL_TIMEOUT_S", 5)
    killed: list[int] = []
    real_kill = oscompat.kill_group

    def kill(pid: int, *, force: bool) -> None:
        killed.append(pid)
        real_kill(pid, force=force)

    monkeypatch.setattr(oscompat, "kill_group", kill)

    async def scenario() -> None:
        disconnect = asyncio.Event()
        output: list[Message] = []

        async def receive() -> Message:
            await disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            output.append(message)
            if message["type"] == "http.response.body" and message.get("body"):
                disconnect.set()
                if blocked_send:
                    await asyncio.Event().wait()

        command = _python("import time; print('ready', flush=True); time.sleep(60)")

        async def body() -> Message:
            return {"type": "http.request", "body": json.dumps({"command": command}).encode()}

        request = Request(
            {"type": "http", "app": _client(tmp_path).app, "client": ("127.0.0.1", 12345)},
            body,
        )
        response = await terminal.terminal_exec(request)
        await response({"type": "http", "asgi": {"spec_version": "2.0"}}, receive, send)
        assert any(b"ready" in m.get("body", b"") for m in output)

    asyncio.run(scenario())
    assert killed
    assert not oscompat.alive(killed[0])


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell selection")
def test_shell_environment_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/bin/custom-shell")
    assert terminal._shell() == "/bin/custom-shell"
    monkeypatch.delenv("SHELL")
    assert terminal._shell() == "/bin/sh"
