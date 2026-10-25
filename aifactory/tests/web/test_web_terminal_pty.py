"""Real POSIX PTYs, exercised without models or external services."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, cast

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import Message
from test_web_terminal import _client

from aifactory import oscompat
from aifactory.web import terminal_pty

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX PTY sessions")
BASE = "/api/terminal/sessions"


@pytest.fixture(autouse=True)
def shell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/bin/sh")


def test_interactive_pty(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = cast(Starlette, _client(tmp_path).app)

        async def call(path: str, body: Any = None, method: str = "POST") -> Response:
            async def receive() -> Message:
                return {"type": "http.request", "body": json.dumps(body).encode()}

            return await terminal_pty.terminal_session(
                Request(
                    {
                        "type": "http",
                        "app": app,
                        "client": ("127.0.0.1", 123),
                        "path": BASE + path,
                        "headers": [],
                        "method": method,
                        "path_params": {"id": token} if path else {},
                    },
                    receive,
                )
            )

        token = ""
        created = await call("", {"cols": 80, "rows": 24, "cwd": str(tmp_path)})
        assert isinstance(created, JSONResponse)
        token = json.loads(bytes(created.body))["data"]["id"]
        session = app.state.terminal_sessions[token]
        pid = session.process.pid
        disconnect = asyncio.Event()
        changed = asyncio.Event()
        output = bytearray()

        async def receive() -> Message:
            await disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            if message["type"] == "http.response.body":
                output.extend(message.get("body", b""))
                changed.set()

        async def expect(value: bytes) -> None:
            async with asyncio.timeout(10):
                while value not in output:
                    changed.clear()
                    await changed.wait()
            output.clear()

        response = await call("/stream", method="GET")
        assert response.headers["content-type"] == "application/octet-stream"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-accel-buffering"] == "no"
        task = asyncio.create_task(
            response({"type": "http", "asgi": {"spec_version": "2.0"}}, receive, send)
        )
        try:
            assert (await call("/stream", method="GET")).status_code == 409
            # Disable echo so all assertions prove command execution, not input echoing.
            await call("/input", {"data": "stty -echo; printf 'ready!\\n'\r"})
            await expect(b"ready!\r\n")
            await call("/input", {"data": "echo pty-ok\r"})
            await expect(b"pty-ok\r\n")
            await call("/input", {"data": 'python3 -c "import sys;print(sys.stdin.isatty())"\r'})
            await expect(b"True\r\n")
            await call("/resize", {"cols": 103, "rows": 37})
            await call("/input", {"data": "stty size\r"})
            await expect(b"37 103\r\n")
            await call("/input", {"data": "printf 'sleeping\\n'; sleep 100; echo interrupted\r"})
            await expect(b"sleeping\r\n")
            await asyncio.sleep(0.1)
            await call("/input", {"data": "\x03"})
            await call("/input", {"data": "echo alive-after-interrupt\r"})
            await expect(b"alive-after-interrupt\r\n")
            await call("/input", {"data": "exit\r"})
            await asyncio.wait_for(task, 5)
            assert token not in app.state.terminal_sessions
            assert not oscompat.alive(pid)
        finally:
            disconnect.set()
            await session.close(app.state.terminal_sessions, token)
            await asyncio.wait_for(task, 5)

    asyncio.run(scenario())


@pytest.mark.parametrize("blocked_send", [False, True])
def test_disconnect_cleanup(tmp_path: Path, blocked_send: bool) -> None:
    async def scenario() -> None:
        with _client(tmp_path) as client:
            # Keep creation and streaming on the application's event loop.
            async def run() -> None:
                app = cast(Starlette, client.app)

                async def body() -> Message:
                    return {"type": "http.request", "body": b'{"cols":80,"rows":24}'}

                scope: dict[str, Any] = {
                    "type": "http",
                    "app": app,
                    "client": ("127.0.0.1", 1),
                    "headers": [],
                    "path": BASE,
                    "method": "POST",
                    "path_params": {},
                }
                created = await terminal_pty.terminal_session(Request(scope, body))
                assert isinstance(created, JSONResponse)
                token = json.loads(bytes(created.body))["data"]["id"]
                session = app.state.terminal_sessions[token]
                scope.update(
                    method="GET", path=BASE + "/" + token + "/stream", path_params={"id": token}
                )
                response = await terminal_pty.terminal_session(Request(scope))
                disconnect = asyncio.Event()

                async def receive() -> Message:
                    await disconnect.wait()
                    return {"type": "http.disconnect"}

                async def send(message: Message) -> None:
                    if message["type"] == "http.response.body" and message.get("body"):
                        disconnect.set()
                        if blocked_send:
                            await asyncio.Event().wait()

                await asyncio.wait_for(
                    response({"type": "http", "asgi": {"spec_version": "2.0"}}, receive, send), 10
                )
                assert not oscompat.alive(session.process.pid)
                assert token not in app.state.terminal_sessions
                with pytest.raises(OSError):
                    os.fstat(session.fd)

            assert client.portal is not None
            await asyncio.to_thread(client.portal.call, run)

    asyncio.run(scenario())


def test_limit_delete_and_shutdown(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        tokens = [
            client.post(BASE, json={"cols": 80, "rows": 24}).json()["data"]["id"] for _ in range(4)
        ]
        processes = [
            s.process.pid for s in cast(Starlette, client.app).state.terminal_sessions.values()
        ]
        response = client.post(BASE, json={"cols": 80, "rows": 24})
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "terminal_busy"
        assert client.delete(BASE + "/" + tokens[0]).status_code == 200
        assert not oscompat.alive(processes[0])
        assert client.post(BASE, json={"cols": 80, "rows": 24}).status_code == 200
    assert all(not oscompat.alive(pid) for pid in processes)


@pytest.mark.parametrize(
    "suffix,method",
    [
        ("", "POST"),
        ("/missing/stream", "GET"),
        ("/missing/input", "POST"),
        ("/missing/resize", "POST"),
        ("/missing", "DELETE"),
    ],
)
@pytest.mark.parametrize("host,peer", [("0.0.0.0", "127.0.0.1"), ("127.0.0.1", "192.0.2.1")])
def test_disabled(tmp_path: Path, suffix: str, method: str, host: str, peer: str) -> None:
    with _client(tmp_path, host, peer) as client:
        response = client.request(method, BASE + suffix, json={"cols": 80, "rows": 24})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "terminal_disabled"


@pytest.mark.parametrize(
    "suffix,method",
    [("", "POST"), ("/missing/input", "POST"), ("/missing/resize", "POST"), ("/missing", "DELETE")],
)
def test_origin(tmp_path: Path, suffix: str, method: str) -> None:
    with _client(tmp_path) as client:
        response = client.request(
            method, BASE + suffix, json={}, headers={"Origin": "http://evil.example"}
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "cross_origin"


@pytest.mark.parametrize(
    "suffix,method",
    [
        ("/missing/stream", "GET"),
        ("/missing/input", "POST"),
        ("/missing/resize", "POST"),
        ("/missing", "DELETE"),
    ],
)
def test_unknown(tmp_path: Path, suffix: str, method: str) -> None:
    with _client(tmp_path) as client:
        response = client.request(method, BASE + suffix, json={})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "terminal_session_not_found"


@pytest.mark.parametrize(
    "body",
    [
        [],
        {},
        {"cols": 0, "rows": 24},
        {"cols": 80, "rows": 1001},
        {"cols": True, "rows": 24},
        {"cols": 80.0, "rows": 24},
        {"cols": "80", "rows": 24},
        {"cols": 80, "rows": 24, "cwd": "/nonexistent-terminal-dir"},
        {"cols": 80, "rows": 24, "cwd": None},
    ],
)
def test_invalid(tmp_path: Path, body: Any) -> None:
    with _client(tmp_path) as client:
        response = client.post(BASE, json=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "usage_error"


def test_invalid_input_resize_and_json(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        token = client.post(BASE, json={"cols": 80, "rows": 24}).json()["data"]["id"]
        for suffix, body in [("/input", {"data": 3}), ("/resize", {"cols": -1, "rows": 24})]:
            response = client.post(BASE + "/" + token + suffix, json=body)
            assert response.status_code == 400
            assert response.json()["error"]["code"] == "usage_error"
        response = client.post(BASE, content="{", headers={"Content-Type": "application/json"})
        assert response.status_code == 400


def test_unsupported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(terminal_pty, "SUPPORTED", False)
    with _client(tmp_path) as client:
        response = client.post(BASE, json={"cols": 80, "rows": 24})
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "terminal_pty_unsupported"


def test_concurrent_limit(tmp_path: Path) -> None:
    with _client(tmp_path) as client:

        async def scenario() -> None:
            async def create() -> Response:
                async def body() -> Message:
                    return {"type": "http.request", "body": b'{"cols":80,"rows":24}'}

                return await terminal_pty.terminal_session(
                    Request(
                        {
                            "type": "http",
                            "app": client.app,
                            "client": ("127.0.0.1", 1),
                            "path": BASE,
                            "headers": [],
                            "method": "POST",
                            "path_params": {},
                        },
                        body,
                    )
                )

            responses = await asyncio.gather(*(create() for _ in range(8)))
            assert sorted(r.status_code for r in responses) == [200] * 4 + [429] * 4

        assert client.portal is not None
        client.portal.call(scenario)


@pytest.mark.parametrize("delete", [False, True])
def test_foreground_cleanup_and_raw_bytes(tmp_path: Path, delete: bool) -> None:
    import re
    import subprocess

    with _client(tmp_path) as client:
        token = client.post(BASE, json={"cols": 80, "rows": 24}).json()["data"]["id"]

        async def scenario() -> None:
            app = cast(Starlette, client.app)
            session = app.state.terminal_sessions[token]
            disconnect = asyncio.Event()
            output = bytearray()
            child_pid = 0
            # Binary output without a newline proves there is no decoding or line buffering.
            command = (
                "stty -echo; python3 -c 'import os,time; "
                'os.write(1,b"\\xffRAW:"+str(os.getpid()).encode()+b"!"); time.sleep(100)' + "'\r"
            )
            await session.write(command.encode())

            async def receive() -> Message:
                await disconnect.wait()
                return {"type": "http.disconnect"}

            async def send(message: Message) -> None:
                nonlocal child_pid
                if message["type"] != "http.response.body":
                    return
                output.extend(message.get("body", b""))
                match = re.search(rb"\xffRAW:(\d+)!", output)
                if match and not child_pid:
                    child_pid = int(match[1])
                    if delete:
                        await session.close(app.state.terminal_sessions, token)
                    else:
                        disconnect.set()

            response = await terminal_pty.terminal_session(
                Request(
                    {
                        "type": "http",
                        "app": app,
                        "client": ("127.0.0.1", 1),
                        "path": BASE + "/" + token + "/stream",
                        "method": "GET",
                        "headers": [],
                        "path_params": {"id": token},
                    }
                )
            )
            try:
                await asyncio.wait_for(
                    response({"type": "http", "asgi": {"spec_version": "2.0"}}, receive, send), 10
                )
                assert child_pid
                assert not oscompat.alive(session.process.pid)
                # A killed orphan can remain a zombie until init reaps it on Linux.
                state = subprocess.run(
                    ["ps", "-o", "stat=", "-p", str(child_pid)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                assert not state.stdout.strip() or state.stdout.strip().startswith("Z")
            finally:
                await session.close(app.state.terminal_sessions, token)

        assert client.portal is not None
        client.portal.call(scenario)


def test_input_backpressure_does_not_block_cleanup(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        token = client.post(BASE, json={"cols": 80, "rows": 24}).json()["data"]["id"]

        async def scenario() -> None:
            app = cast(Starlette, client.app)
            session = app.state.terminal_sessions[token]
            await session.write(b"stty -echo -icanon; sleep 100\r")
            await asyncio.sleep(0.1)
            writer = asyncio.create_task(session.write(b"x" * 2_000_000))
            try:
                await asyncio.sleep(0.1)
                assert not writer.done()
                await session.close(app.state.terminal_sessions, token)
                with pytest.raises(OSError):
                    await asyncio.wait_for(writer, 5)
            finally:
                await session.close(app.state.terminal_sessions, token)
                writer.cancel()
                await asyncio.gather(writer, return_exceptions=True)

        assert client.portal is not None
        client.portal.call(scenario)


def test_resize_racing_delete_does_not_touch_closed_fd(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        token = client.post(BASE, json={"cols": 80, "rows": 24}).json()["data"]["id"]

        async def scenario() -> None:
            app = cast(Starlette, client.app)
            session = app.state.terminal_sessions[token]

            async def body() -> Message:
                # A slow request body can arrive after a concurrent DELETE completes.
                await session.close(app.state.terminal_sessions, token)
                return {"type": "http.request", "body": b'{"cols":100,"rows":40}'}

            response = await terminal_pty.terminal_session(
                Request(
                    {
                        "type": "http",
                        "app": app,
                        "client": ("127.0.0.1", 1),
                        "headers": [],
                        "path": BASE + "/" + token + "/resize",
                        "method": "POST",
                        "path_params": {"id": token},
                    },
                    body,
                )
            )
            assert response.status_code == 404
            assert isinstance(response, JSONResponse)
            assert json.loads(bytes(response.body))["error"]["code"] == "terminal_session_not_found"

        assert client.portal is not None
        client.portal.call(scenario)
