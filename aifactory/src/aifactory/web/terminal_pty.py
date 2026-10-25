"""Ephemeral loopback PTYs; no terminal input or output is persisted."""

from __future__ import annotations

import asyncio
import os
import secrets
import struct
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import anyio
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.types import Receive, Scope, Send

from aifactory import oscompat
from aifactory.skill.envelope import envelope_fail, envelope_ok
from aifactory.web.terminal import _enabled, _shell

SUPPORTED = os.name == "posix"
# setsid is performed by the subprocess launcher before this code claims fd 0.
_BOOTSTRAP = (
    "import fcntl, os, sys, termios; "
    "fcntl.ioctl(0, termios.TIOCSCTTY, 0); "
    "os.execv(sys.argv[1], [sys.argv[1], '-il'])"
)


def _error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(envelope_fail(code, message), status_code=status)


def _size(body: dict[str, Any]) -> bytes:
    cols, rows = body.get("cols"), body.get("rows")
    if any(type(n) is not int or not 1 <= n <= 1000 for n in (cols, rows)):
        raise ValueError("cols and rows must be integers between 1 and 1000.")
    return struct.pack("HHHH", rows, cols, 0, 0)


class Session:
    def __init__(self, process: asyncio.subprocess.Process, fd: int) -> None:
        self.process = process
        self.fd = fd
        self.attached = False
        self.closed = False
        self.output: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.loop = asyncio.get_running_loop()
        self.loop.add_reader(fd, self.read)
        self.watcher: asyncio.Task[None]
        self.write_lock = asyncio.Lock()

    def read(self) -> None:
        try:
            data = os.read(self.fd, 65536)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if data:
            self.output.put_nowait(data)
            if self.output.qsize() >= 16:
                self.loop.remove_reader(self.fd)
        else:
            self.loop.remove_reader(self.fd)

    async def close(self, sessions: dict[str, Session], token: str) -> None:
        with anyio.CancelScope(shield=True):
            if not self.closed:
                self.closed = True
                self.loop.remove_reader(self.fd)
                self.loop.remove_writer(self.fd)
                # Job control gives a foreground program its own process group.
                groups = {self.process.pid}
                try:
                    groups.add(os.tcgetpgrp(self.fd))
                except OSError:
                    pass
                for group in groups:
                    if group > 0:
                        try:
                            oscompat.kill_group(group, force=True)
                        except ProcessLookupError:
                            pass
                os.close(self.fd)
                self.output.put_nowait(None)
            await self.process.wait()
            sessions.pop(token, None)

    async def watch(self, sessions: dict[str, Session], token: str) -> None:
        await self.process.wait()
        # Preserve the final output already available on the master, within the buffer bound.
        if not self.closed:
            for _ in range(16):
                before = self.output.qsize()
                self.read()
                if self.output.qsize() == before:
                    break
        await self.close(sessions, token)

    async def stream(self) -> AsyncIterator[bytes]:
        while (data := await self.output.get()) is not None:
            if not self.closed:
                self.loop.add_reader(self.fd, self.read)
            yield data

    async def write(self, data: bytes) -> None:
        async with self.write_lock:
            while data:
                if self.closed:
                    raise OSError("Session has ended.")
                try:
                    count = os.write(self.fd, data)
                    data = data[count:]
                except BlockingIOError:
                    ready: asyncio.Future[None] = self.loop.create_future()

                    def writable(ready: asyncio.Future[None] = ready) -> None:
                        if not ready.done():
                            ready.set_result(None)

                    self.loop.add_writer(self.fd, writable)
                    try:
                        # Also wake on DELETE, which removes the fd from the loop.
                        await asyncio.wait(
                            [ready, self.watcher], return_when=asyncio.FIRST_COMPLETED
                        )
                    finally:
                        if not self.closed:
                            self.loop.remove_writer(self.fd)
                        ready.cancel()


class _Response(StreamingResponse):
    def __init__(self, session: Session, sessions: dict[str, Session], token: str) -> None:
        self.session, self.sessions, self.token = session, sessions, token
        super().__init__(
            session.stream(),
            media_type="application/octet-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.session.close(self.sessions, self.token)


async def terminal_session(request: Request) -> Response:
    # Serialize creation, including subprocess startup, so concurrent requests respect the cap.
    if request.method == "POST" and not request.path_params.get("id"):
        async with request.app.state.terminal_session_lock:
            return await _dispatch(request)
    return await _dispatch(request)


async def _dispatch(request: Request) -> Response:
    """Dispatch all PTY operations after the same loopback gate as exec."""
    if not _enabled(request):
        return _error("terminal_disabled", "Terminal requires a loopback server and client.", 403)
    if not SUPPORTED:
        return _error("terminal_pty_unsupported", "PTY sessions require POSIX.", 501)
    sessions: dict[str, Session] = request.app.state.terminal_sessions
    token = str(request.path_params.get("id", ""))
    session = sessions.get(token) if token else None
    if token and (session is None or session.closed):
        return _error("terminal_session_not_found", "Unknown terminal session.", 404)
    if request.method == "GET":
        assert session is not None
        if session.attached:
            return _error("terminal_attached", "Session already has a stream.", 409)
        session.attached = True
        return _Response(session, sessions, token)
    if request.method == "DELETE":
        assert session is not None
        await session.close(sessions, token)
        return JSONResponse(envelope_ok({}))
    try:
        body = await request.json()
        if session is not None and session.closed:
            return _error("terminal_session_not_found", "Unknown terminal session.", 404)
        if not isinstance(body, dict):
            raise ValueError("Expected a JSON object.")
        if request.url.path.endswith("/input"):
            data = body.get("data")
            if not isinstance(data, str):
                raise ValueError("data must be a string.")
            assert session is not None
            await session.write(data.encode("utf-8"))
        else:
            import fcntl
            import termios

            size = _size(body)
            if session is not None:
                # The kernel sends SIGWINCH to the foreground process group.
                fcntl.ioctl(session.fd, termios.TIOCSWINSZ, size)
            else:
                cwd = body.get("cwd", str(Path.home()))
                if not isinstance(cwd, str) or "\0" in cwd:
                    raise ValueError("cwd must be a directory path.")
                directory = Path(cwd).expanduser().resolve()
                if not directory.is_dir():
                    raise ValueError("cwd does not exist or is not a directory.")
                if len(sessions) >= 4:
                    return _error("terminal_busy", "At most four sessions may run.", 429)
                master, slave = os.openpty()
                token = secrets.token_urlsafe()
                try:
                    fcntl.ioctl(slave, termios.TIOCSWINSZ, size)
                    os.set_blocking(master, False)
                    process = await asyncio.create_subprocess_exec(
                        sys.executable,
                        "-c",
                        _BOOTSTRAP,
                        _shell(),
                        stdin=slave,
                        stdout=slave,
                        stderr=slave,
                        cwd=directory,
                        env={**os.environ, "TERM": "xterm-256color", "COLORTERM": "truecolor"},
                        start_new_session=True,
                    )
                except BaseException:
                    os.close(master)
                    raise
                finally:
                    os.close(slave)
                session = Session(process, master)
                sessions[token] = session
                session.watcher = asyncio.create_task(session.watch(sessions, token))
                return JSONResponse(envelope_ok({"id": token}))
    except (ValueError, OSError, RuntimeError) as error:
        return _error("usage_error", str(error), 400)
    return JSONResponse(envelope_ok({}))


async def close_sessions(sessions: dict[str, Session]) -> None:
    for token, session in list(sessions.items()):
        await session.close(sessions, token)
