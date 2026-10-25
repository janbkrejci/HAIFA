"""Real Windows ConPTY sessions, without models or external services."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import Message
from test_web_terminal import _client, _python

from aifactory import oscompat
from aifactory.web import terminal, terminal_pty

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows ConPTY sessions")
BASE = "/api/terminal/sessions"


async def _call(
    app: Starlette, token: str = "", suffix: str = "", body: Any = None, method: str = "POST"
) -> Response:
    async def receive() -> Message:
        return {"type": "http.request", "body": json.dumps(body).encode()}

    return await terminal_pty.terminal_session(
        Request(
            {
                "type": "http",
                "app": app,
                "client": ("127.0.0.1", 123),
                "path": BASE + ("/" + token if token else "") + suffix,
                "headers": [],
                "method": method,
                "path_params": {"id": token} if token else {},
            },
            receive,
        )
    )


@pytest.mark.parametrize("cleanup", ["delete", "disconnect", "blocked_send", "exit"])
def test_conpty_session(tmp_path: Path, cleanup: str) -> None:
    async def scenario() -> None:
        app = cast(Starlette, _client(tmp_path).app)
        created = await _call(app, body={"cols": 80, "rows": 24, "cwd": str(tmp_path)})
        assert isinstance(created, JSONResponse)
        assert created.status_code == 200, bytes(created.body)
        token = json.loads(bytes(created.body))["data"]["id"]
        session = app.state.terminal_sessions[token]
        assert isinstance(session, terminal_pty.WindowsSession)
        process = session.process
        assert process.argv == [terminal._shell()]
        assert Path(process.launch_dir) == tmp_path.resolve()
        assert "TERM=xterm-256color\0" in process.env
        assert process.getwinsize() == (24, 80)
        output = bytearray()
        changed = asyncio.Event()
        disconnect = asyncio.Event()
        block_send = False

        async def receive() -> Message:
            await disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            if message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                output.extend(chunk)
                if b"\x1b[6n" in chunk:
                    await session.write(b"\x1b[1;1R")
                changed.set()
                if block_send and chunk:
                    disconnect.set()
                    await asyncio.Event().wait()

        def plain_output() -> bytes:
            return re.sub(rb"\x1b\[[0-?]*[ -/]*[@-~]", b"", bytes(output))

        async def expect(value: bytes) -> None:
            async with asyncio.timeout(20):
                while value not in plain_output():
                    changed.clear()
                    await changed.wait()

        response = await _call(app, token, "/stream", method="GET")
        assert response.headers["cache-control"] == "no-store"
        task = asyncio.create_task(
            response({"type": "http", "asgi": {"spec_version": "2.0"}}, receive, send)
        )
        child_pid = None
        try:
            assert (await _call(app, token, "/stream", method="GET")).status_code == 409
            # The caret keeps echoed input from satisfying the execution assertion.
            assert (
                await _call(app, token, "/input", {"data": "@echo off\r\necho pty-^ok\r\n"})
            ).status_code == 200
            await expect(b"pty-ok")
            assert (
                await _call(app, token, "/resize", {"cols": 103, "rows": 37})
            ).status_code == 200
            assert process.getwinsize() == (37, 103)
            if cleanup == "exit":
                await _call(app, token, "/input", {"data": "echo final-^ok & exit\r\n"})
            else:
                command = _python(
                    "import os,time; print('CHILD:%s!' % os.getpid(), flush=True); "
                    "[(print('tick', flush=True), time.sleep(0.2)) for _ in range(500)]"
                )
                await _call(app, token, "/input", {"data": command + "\r\n"})
                async with asyncio.timeout(20):
                    while not (match := re.search(rb"CHILD:(\d+)!", plain_output())):
                        changed.clear()
                        await changed.wait()
                child_pid = int(match[1])
                assert oscompat.alive(child_pid)
                if cleanup == "delete":
                    assert (await _call(app, token, method="DELETE")).status_code == 200
                elif cleanup == "disconnect":
                    disconnect.set()
                else:
                    block_send = True
                    # The child's next tick blocks send() while its process is still alive.
            await asyncio.wait_for(task, 20)
            await asyncio.wait_for(session.watcher, 5)
            if cleanup == "exit":
                assert b"final-ok" in plain_output()
            assert token not in app.state.terminal_sessions
            assert not oscompat.alive(process.pid)
            if child_pid is not None:
                assert not oscompat.alive(child_pid)
            assert session.reader.done()
            assert process.fileobj.fileno() == -1
            assert process._server.fileno() == -1
        finally:
            disconnect.set()
            await session.close(app.state.terminal_sessions, token)
            await asyncio.wait_for(task, 10)
            await asyncio.wait_for(session.watcher, 5)

    asyncio.run(scenario())


def test_capabilities_limit_and_shutdown(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        info = client.get("/api/terminal").json()["data"]
        assert info["pty"] is True
        assert info["shell"] == terminal._shell()
        for _ in range(4):
            assert client.post(BASE, json={"cols": 80, "rows": 24}).status_code == 200
        processes = [
            s.process for s in cast(Starlette, client.app).state.terminal_sessions.values()
        ]
        assert client.post(BASE, json={"cols": 80, "rows": 24}).status_code == 429
        assert (
            client.post(BASE, json={}, headers={"Origin": "http://evil.example"}).status_code == 403
        )
    assert all(not oscompat.alive(process.pid) for process in processes)


@pytest.mark.parametrize("host,peer", [("0.0.0.0", "127.0.0.1"), ("127.0.0.1", "192.0.2.1")])
def test_loopback_gate(tmp_path: Path, host: str, peer: str) -> None:
    with _client(tmp_path, host, peer) as client:
        assert client.post(BASE, json={"cols": 80, "rows": 24}).status_code == 403
