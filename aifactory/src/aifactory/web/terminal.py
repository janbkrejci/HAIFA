"""Loopback-only, stateless shell commands; nothing is persisted or traced."""

from __future__ import annotations

import asyncio
import codecs
import json
import os
import shlex
import sys
from collections.abc import AsyncGenerator
from contextlib import aclosing
from pathlib import Path
from typing import Any

import anyio
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.types import Receive, Scope, Send

from aifactory import oscompat
from aifactory.skill.envelope import envelope_fail, envelope_ok
from aifactory.web.server import LOOPBACK

TERMINAL_TIMEOUT_S = 600.0


def _shell() -> str:
    return "cmd" if sys.platform == "win32" else os.environ.get("SHELL") or "/bin/sh"


def _enabled(request: Request) -> bool:
    return bool(
        request.app.state.terminal_enabled
        and request.client is not None
        and request.client.host in LOOPBACK
    )


async def terminal_get(request: Request) -> Response:
    return JSONResponse(
        envelope_ok(
            {
                "enabled": _enabled(request),
                "cwd": str(Path.home()),
                "shell": _shell(),
                "pty": os.name == "posix",
            }
        )
    )


def _line(event: dict[str, Any]) -> str:
    return json.dumps(event) + "\n"


def _cd(command: str, cwd: Path) -> Path | None:
    # Only a standalone cd is handled here; shell compound commands keep shell semantics.
    lexer = shlex.shlex(command, posix=sys.platform != "win32", punctuation_chars=";&|<>()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        words = list(lexer)
    except ValueError:
        return None
    if not words or words[0] != "cd" or len(words) > 2:
        return None
    if len(words) == 1:
        return Path.home().resolve()
    target = Path(words[1].strip('"') if sys.platform == "win32" else words[1]).expanduser()
    return (cwd / target).resolve()


async def _run(command: str, cwd: Path, shell: str) -> AsyncGenerator[str, None]:
    argv = [shell, "/c" if sys.platform == "win32" else "-c", command]
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            creationflags=oscompat.NEW_GROUP,
        )
    except OSError as error:
        yield _line({"type": "out", "stream": "stderr", "text": f"{error}\n"})
        yield _line({"type": "exit", "code": 1, "cwd": str(cwd)})
        return

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=16)

    async def read(pipe: asyncio.StreamReader | None, stream: str) -> None:
        assert pipe is not None
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while chunk := await pipe.read(4096):
            text = decoder.decode(chunk)
            if text:
                await queue.put({"type": "out", "stream": stream, "text": text})
        text = decoder.decode(b"", final=True)
        if text:
            await queue.put({"type": "out", "stream": stream, "text": text})
        await queue.put(None)

    readers = [
        asyncio.create_task(read(process.stdout, "stdout")),
        asyncio.create_task(read(process.stderr, "stderr")),
    ]
    code = 124
    timed_out = False
    try:
        try:
            async with asyncio.timeout(TERMINAL_TIMEOUT_S):
                finished = 0
                while finished < 2:
                    event = await queue.get()
                    if event is None:
                        finished += 1
                    else:
                        yield _line(event)
                code = await process.wait()
        except TimeoutError:
            timed_out = True
    finally:
        # StreamingResponse cancels its iterator on disconnect. Shield reaping from that
        # cancellation, and kill the group even if the shell left children behind.
        with anyio.CancelScope(shield=True):
            try:
                await asyncio.to_thread(oscompat.kill_group, process.pid, force=True)
            except ProcessLookupError:
                pass
            for reader in readers:
                reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
            await process.wait()
    if timed_out:
        yield _line({"type": "out", "stream": "stderr", "text": "Command timed out.\n"})
    yield _line({"type": "exit", "code": code, "cwd": str(cwd)})


class _TerminalResponse(StreamingResponse):
    def __init__(self, stream: AsyncGenerator[str, None]) -> None:
        super().__init__(
            stream,
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )
        self.stream = stream

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # A disconnect can also cancel a blocked send while the generator is suspended.
            with anyio.CancelScope(shield=True):
                await self.stream.aclose()


async def terminal_exec(request: Request) -> Response:
    if not _enabled(request):
        return JSONResponse(
            envelope_fail("terminal_disabled", "Terminal requires a loopback server and client."),
            status_code=403,
        )
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("Expected a JSON object.")
        command = body.get("command")
        if not isinstance(command, str) or not command.strip() or "\0" in command:
            raise ValueError("command must be a non-empty string.")
        raw_cwd = body.get("cwd", str(Path.home()))
        if not isinstance(raw_cwd, str):
            raise ValueError("cwd must be a directory path.")
        cwd = Path(raw_cwd).expanduser().resolve()
        if not cwd.is_dir():
            raise ValueError("cwd does not exist or is not a directory.")
        target = _cd(command.strip(), cwd)
    except (ValueError, OSError, RuntimeError) as error:
        return JSONResponse(envelope_fail("usage_error", str(error)), status_code=400)

    async def stream() -> AsyncGenerator[str, None]:
        if target is not None:
            exists = target.is_dir()
            if not exists:
                yield _line(
                    {
                        "type": "out",
                        "stream": "stderr",
                        "text": f"cd: {target}: no such directory\n",
                    }
                )
            yield _line(
                {"type": "exit", "code": 0 if exists else 1, "cwd": str(target if exists else cwd)}
            )
        else:
            async with aclosing(_run(command, cwd, _shell())) as output:
                async for line in output:
                    yield line

    return _TerminalResponse(stream())
