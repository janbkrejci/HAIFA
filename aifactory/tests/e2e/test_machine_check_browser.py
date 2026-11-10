"""Manual machine check in the shipped assets: progress in the chip, timeout and retry.

The API is stubbed (no backend, no live services); the explicit check request is held
until the test answers it, as a slow check would be.
"""

import json
import mimetypes
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Route, expect, sync_playwright
from test_f3_browser import _launch

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
