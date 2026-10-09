"""The dashboard server binds 127.0.0.1 only and reports a taken port."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
import uvicorn

from aifactory.web import HOST, PortInUseError, check_port, create_app, dashboard_url, serve


def test_host_is_loopback() -> None:
    assert HOST == "127.0.0.1"
    assert dashboard_url(4700) == "http://127.0.0.1:4700/"


def test_check_port_detects_taken_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = sock.getsockname()[1]
        with pytest.raises(PortInUseError) as info:
            check_port(port)
        assert info.value.port == port


def test_check_port_ignores_time_wait_left_by_a_stopped_server() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, 0))
    server.listen()
    port = server.getsockname()[1]
    client = socket.create_connection((HOST, port))
    accepted, _ = server.accept()
    accepted.close()  # the server side closes first: its end of the connection stays in TIME_WAIT
    server.close()
    client.close()
    check_port(port)


def test_check_port_accepts_free_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    check_port(port)


def test_serve_binds_loopback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    configs: list[uvicorn.Config] = []
    opened: list[str] = []

    def fake_run(self: uvicorn.Server) -> None:
        configs.append(self.config)

    monkeypatch.setattr(uvicorn.Server, "run", fake_run)
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
    serve(create_app(tmp_path), 4799, open_browser=False)
    assert len(configs) == 1
    assert configs[0].host == "127.0.0.1"
    assert configs[0].port == 4799
    assert opened == []
