"""Local dashboard with a deterministic recommendation runner for browser acceptance."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import uvicorn

from advice_fixture import output
from aifactory.codeprint import CodeWatch
from aifactory.web.app import create_multi_app
from aifactory.web.registry import Registry
from aifactory.web.workflow_advice import AdviceManager


@contextmanager
def dashboard(repo: Path, home: Path) -> Iterator[tuple[str, str]]:
    entry, _ = Registry(home).add(repo)
    app = create_multi_app(home=home, code_watch=CodeWatch(home / "test-code"))
    app.state.workflow_advice.close()

    def runner(
        root: Path, ctx: dict[str, Any], identifier: str, cancelled: threading.Event
    ) -> dict[str, object]:
        new = "new" in ctx["draft"]["title"].lower()
        return output("research" if new else "plan", new=new)

    app.state.workflow_advice = AdviceManager(runner)
    app.state.limits = type("NoLimits", (), {"get": lambda self, root: {"providers": []}})()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise AssertionError("dashboard did not start")
            time.sleep(0.01)
        yield f"http://127.0.0.1:{port}", entry.id
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
