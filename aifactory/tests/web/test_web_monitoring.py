"""Server startup checks run without a browser, including after an upgrade restart."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from aifactory.web import create_multi_app, machine
from aifactory.web.limits import LimitsSource
from aifactory.web.updates import Updates


def test_each_server_start_checks_without_browser_reloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from factory_check_repo import FakeMachine

    real_check = machine.check_view
    ready = threading.Event()

    def check(*args: Any, **kwargs: Any) -> Any:
        result = real_check(*args, **kwargs)
        ready.set()
        return result

    monkeypatch.setattr(machine, "check_view", check)
    monkeypatch.setattr(machine.GlobalState, "harnesses", lambda *args, **kwargs: {})
    for _ in range(2):  # Initial start and the new process after installation.
        ready.clear()
        fake = FakeMachine()
        app = create_multi_app(
            home=tmp_path,
            background_checks=True,
            limits_source=LimitsSource(readers={}),
        )
        app.state.check_machine = fake
        app.state.updates = Updates(fetch=lambda _: {})
        with TestClient(app, base_url="http://127.0.0.1:4700") as client:
            assert ready.wait(5), "server must check without an HTTP request"
            calls = len(fake.calls)
            assert calls > 0
            for _ in range(3):
                assert client.get("/api/machine/check").json()["data"]["cached"]
            assert len(fake.calls) == calls
