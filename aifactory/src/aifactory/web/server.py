"""Run the dashboard with uvicorn: on 127.0.0.1 unless the operator picks another address.

``factory obs --host`` or ``HAIFA_DASH_HOST`` (e.g. in ``<HAIFA home>/env``) picks the
address; 0.0.0.0 serves the whole network, with no login.
"""

from __future__ import annotations

import errno
import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from typing import Final

import uvicorn
from starlette.types import ASGIApp

HOST: Final = "127.0.0.1"
"""The default address of the dashboard."""

HOST_ENV: Final = "HAIFA_DASH_HOST"
"""Another address for this machine (``--host`` still wins)."""

LOOPBACK: Final = frozenset({"127.0.0.1", "localhost", "::1"})
_ANY: Final = frozenset({"0.0.0.0", "::", ""})

_BROWSER_WAIT_S = 10.0

APP_NAME: Final = "haifa-dashboard"
"""``app`` of ``GET /api/health`` that marks a running HAIFA dashboard."""

RESTART_ENV = "HAIFA_OBS_RESTART"
"""Set for the process that replaces a restarted dashboard: no new browser tab, port waited for."""


class PortInUseError(Exception):
    """The dashboard port on its host is taken."""

    def __init__(self, port: int, host: str = HOST) -> None:
        super().__init__(f"port {port} on {host} is already in use")
        self.port = port


def resolve_host(host: str | None) -> str:
    """``host`` if given, else ``$HAIFA_DASH_HOST``, else 127.0.0.1."""
    return host or os.environ.get(HOST_ENV) or HOST


def allowed_hosts(host: str) -> list[str]:
    """Host headers the app accepts: the loopback names, or any when it serves the network."""
    return ["127.0.0.1", "localhost"] if host in LOOPBACK else ["*"]


def dashboard_url(port: int, host: str = HOST) -> str:
    """The URL to open on this machine (127.0.0.1 when the server listens on every address)."""
    shown = HOST if host in _ANY else host
    if ":" in shown:
        shown = f"[{shown}]"
    return f"http://{shown}:{port}/"


def check_port(port: int, *, wait: float = 0.0, host: str = HOST) -> None:
    """Raise ``PortInUseError`` when ``port`` on ``host`` cannot be bound within ``wait`` s."""
    deadline = time.monotonic() + wait
    while True:
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        # bind like uvicorn does: connections in TIME_WAIT left by the previous server are no
        # "port in use" (on macOS they hold the port for about 30 s), a listening socket is
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return
        except OSError as exc:
            if exc.errno not in (errno.EADDRINUSE, errno.EACCES):
                raise
            if time.monotonic() >= deadline:
                raise PortInUseError(port, host) from exc
        finally:
            sock.close()
        time.sleep(0.2)


def probe_dashboard(port: int, host: str = HOST, timeout: float = 1.0) -> bool:
    """True when a HAIFA dashboard answers ``/api/health`` on ``host``:``port``."""
    try:
        with urllib.request.urlopen(  # noqa: S310 - our own http URL
            f"{dashboard_url(port, host)}api/health", timeout=timeout
        ) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - anything else on the port is not ours
        return False
    if not isinstance(body, dict) or body.get("ok") is not True:
        return False
    data = body.get("data")
    return isinstance(data, dict) and data.get("app") == APP_NAME


def restart_process() -> None:
    """Replace this process with a fresh ``factory obs``: same command line, the code on disk."""
    os.environ[RESTART_ENV] = "1"
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(sys.executable, [sys.executable, *sys.orig_argv[1:]])


def _open_when_started(server: uvicorn.Server, url: str) -> None:
    deadline = time.monotonic() + _BROWSER_WAIT_S
    while not server.started:
        if time.monotonic() > deadline or server.should_exit:
            return
        time.sleep(0.05)
    webbrowser.open(url)


def serve(
    app: ASGIApp, port: int, *, open_browser: bool, host: str = HOST, open_path: str = ""
) -> None:
    """Serve ``app`` on ``host``:``port`` until interrupted; optionally open the browser.

    The browser opens the dashboard URL followed by ``open_path`` (e.g. ``#/r/<id>/backlog``).
    """
    # an open /api/live stream must not keep Ctrl+C waiting
    config = uvicorn.Config(
        app, host=host, port=port, log_level="warning", timeout_graceful_shutdown=2
    )
    server = uvicorn.Server(config)
    if open_browser:
        threading.Thread(
            target=_open_when_started,
            args=(server, dashboard_url(port, host) + open_path),
            daemon=True,
        ).start()
    server.run()
