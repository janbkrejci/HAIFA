"""Manual machine check in the shipped assets: progress in the chip, timeout and retry.

The API is stubbed (no backend, no live services); the explicit check request is held
until the test answers it, as a slow check would be.
"""

import json
import mimetypes
import re
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import uvicorn
from playwright.sync_api import Route, expect, sync_playwright
from test_f3_browser import _launch

from aifactory.codeprint import CodeWatch
from aifactory.web import create_multi_app, machine
from aifactory.web.limits import LimitsSource

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "check"))
from factory_check_repo import FakeMachine  # noqa: E402

STATIC = Path(__file__).resolve().parents[2] / "src/aifactory/web/static"
pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]

JOB = {
    "seq": 2,
    "offline": False,
    "step": "machine: logins",
    "detail": "claude auth status",
    "started_at": "2026-11-10T10:00:00Z",
    "elapsed": 3,
    "budget": 60,
    "running": True,
}
CHECK = {"ok": True, "findings": [], "checked_at": "2026-11-10T09:00:00Z", "cached": True}


def _envelope(data: Any, code: str | None = None) -> str:
    error = None if code is None else {"code": code, "message": code, "issues": []}
    return json.dumps({"ok": code is None, "data": data, "error": error, "warnings": []})


def test_manual_check_shows_progress_timeout_and_retry_browser() -> None:
    held: list[Route] = []

    def serve(route: Route) -> None:
        url = urlsplit(route.request.url)
        assert url.netloc == "haifa.test", route.request.url
        if url.path == "/api/machine/check" and "fresh=1" in url.query:
            held.append(route)  # answered by the test, like a slow check
            return
        if url.path.startswith("/api/"):
            responses = {
                "/api/health": {"app": "haifa-dashboard", "version": "test", "home": "/home"},
                "/api/repos": {"home": "/home", "repos": []},
                "/api/limits": {"providers": []},
                "/api/library": {"exists": True, "items": []},
                "/api/machine/check": CHECK,
                "/api/machine/progress": {"job": JOB, "checked_at": CHECK["checked_at"]},
            }
            route.fulfill(
                content_type="application/json", body=_envelope(responses.get(url.path, {}))
            )
            return
        asset = STATIC / (url.path.lstrip("/") or "index.html")
        assert asset.resolve().is_relative_to(STATIC.resolve()) and asset.is_file(), url.path
        route.fulfill(
            body=asset.read_bytes(),
            content_type=mimetypes.guess_type(asset.name)[0] or "application/octet-stream",
        )

    with sync_playwright() as playwright:
        browser = _launch(playwright)
        context = browser.new_context(service_workers="block")
        context.set_default_timeout(30_000)
        try:
            page = context.new_page()
            page.route("**/*", serve)
            page.goto("http://haifa.test/#/problems")
            page.locator("[data-test='readiness-retry']").click()
            # The chip and the page name what the check waits for and for how long.
            progress = page.locator("[data-test='readiness-progress']")
            expect(progress).to_contain_text(
                "kontrola počítače: machine: logins (claude auth status)"
            )
            expect(progress).to_contain_text(" s")
            chip = page.locator(".status-icon-chip[data-test='readiness-checking']")
            expect(chip).to_have_attribute(
                "aria-label",
                re.compile(
                    r"^Probíhá kontrola – čeká na: kontrola počítače: machine: logins "
                    r"\(claude auth status\) · \d+ s$"
                ),
            )
            expect(chip.locator("[data-test='readiness-elapsed']")).to_contain_text(" s")
            # The server ends the check at its budget with the last known result.
            assert len(held) == 1
            stale = {
                **CHECK,
                "ok": False,
                "stale": True,
                "timed_out": True,
                "progress": {**JOB, "elapsed": 60},
            }
            held.pop().fulfill(
                content_type="application/json", body=_envelope(stale, "check_timeout")
            )
            timeout = page.locator("[data-test='readiness-warning'] li").filter(
                has_text="Kontrola nedoběhla do 60 s"
            )
            expect(timeout).to_contain_text(
                "Nedokončený krok: kontrola počítače: machine: logins (claude auth status)."
            )
            expect(timeout).to_contain_text("Zobrazen poslední známý výsledek z")
            expect(page.locator(".status-icon-chip[data-test='readiness-warning']")).to_be_visible()
            # Retry runs a new check; its answer replaces the timeout.
            timeout.locator("[data-test='readiness-timeout-retry']").click()
            expect(page.locator("[data-test='readiness-checking']").first).to_be_visible()
            for _ in range(100):
                if held:
                    break
                page.wait_for_timeout(50)
            assert len(held) == 1
            held.pop().fulfill(
                content_type="application/json",
                body=_envelope({**CHECK, "checked_at": "2026-11-10T10:01:00Z", "cached": False}),
            )
            expect(page.locator("text=Kontrola nedoběhla")).to_have_count(0)
        finally:
            context.close()
            browser.close()


def test_readiness_on_kanban_does_not_request_a_second_board_browser() -> None:
    requests: list[str] = []

    def serve(route: Route) -> None:
        path = urlsplit(route.request.url).path
        if path.startswith("/api/"):
            requests.append(path)
            responses: dict[str, Any] = {
                "/api/health": {"app": "haifa-dashboard", "version": "test", "home": "/home"},
                "/api/repos": {
                    "repos": [
                        {
                            "id": "a",
                            "name": "A",
                            "path": "/repo",
                            "status": "ok",
                            "added_at": "",
                            "factory": None,
                        }
                    ]
                },
                "/api/library": {"exists": True},
                "/api/machine/check": CHECK,
                "/api/repos/a/factory/roster": {"agents": [{"name": "builder"}]},
                "/api/repos/a/backlog/summary": {"projects": 1},
                "/api/repos/a/backlog": {
                    "levels": ["project", "step", "task"],
                    "items": [],
                    "tasks": [],
                    "steps": [],
                    "states": [],
                    "workflows": [],
                    "issues": [],
                    "state_counts": {},
                    "counts": {},
                    "filters": {"status": None},
                },
                "/api/repos/a/backlog/names": {"levels": ["project", "step", "task"], "names": {}},
                "/api/limits": {"providers": []},
            }
            route.fulfill(content_type="application/json", body=_envelope(responses.get(path, {})))
            return
        asset = STATIC / (path.lstrip("/") or "index.html")
        assert asset.resolve().is_relative_to(STATIC.resolve()) and asset.is_file()
        route.fulfill(
            body=asset.read_bytes(),
            content_type=mimetypes.guess_type(asset.name)[0] or "application/octet-stream",
        )

    with sync_playwright() as playwright:
        browser = _launch(playwright)
        try:
            page = browser.new_page(service_workers="block")
            page.route("**/*", serve)
            page.goto("http://haifa.test/#/r/a/backlog")
            expect(page.locator("[data-test='readiness-success']")).to_be_visible()
            expect(page.locator("h1")).to_contain_text("Backlog")
            # Wait for the page's own board response to finish rendering as well.
            page.locator("[data-test=mode-kanban]").click()
            expect(page.locator("[data-test=kanban]")).to_be_visible()
            assert requests.count("/api/repos/a/backlog/summary") == 1
            assert requests.count("/api/repos/a/backlog") == 1
        finally:
            browser.close()


@pytest.mark.parametrize("previous_result", [False, True])
def test_new_overview_tab_never_starts_a_server_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, previous_result: bool
) -> None:
    """Use the real API: both missing and invalidated caches must stay read-only."""
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    home = tmp_path / "home"
    app = create_multi_app(
        home=home,
        user_home=tmp_path,
        code_watch=CodeWatch(tmp_path / "code"),
        limits_source=LimitsSource(readers={}),
    )
    fake = FakeMachine()
    app.state.check_machine = fake
    global_state = app.state.library
    if previous_result:
        # The same explicit check as startup, followed by a library/harness write.
        machine.check_view(home, global_state, offline=False, fresh=True, machine=fake)
        global_state.invalidate()
    calls, seq = list(fake.calls), global_state.seq
    requests: list[str] = []
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline, "server did not start"
            time.sleep(0.01)
        with sync_playwright() as playwright:
            browser = _launch(playwright)
            context = browser.new_context(service_workers="block")
            context.set_default_timeout(30_000)
            context.on("request", lambda request: requests.append(request.url))
            try:
                for _ in range(2):
                    page = context.new_page()
                    with page.expect_response(lambda r: "/api/machine/check" in r.url) as answer:
                        page.goto(f"http://127.0.0.1:{port}/#/overview")
                    data = answer.value.json()["data"]
                    assert not data["ok"]
                    if previous_result:
                        assert data["stale"]
                    else:
                        assert data["checked"] is False
                    expect(page.locator(".topbar [data-test='readiness-warning']")).to_be_visible()
                    assert fake.calls == calls and global_state.seq == seq
                checks = [url for url in requests if "/api/machine/check" in url]
                assert len(checks) == 2 and all("fresh=" not in url for url in checks)
                assert not global_state.jobs
            finally:
                context.close()
                browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        sock.close()
