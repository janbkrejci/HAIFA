"""The shipped shell exposes the migration on every screen, in EN and CS."""

import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Route, expect, sync_playwright
from test_f3_browser import _launch

STATIC = Path(__file__).resolve().parents[2] / "src/aifactory/web/static"
pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


@pytest.mark.parametrize(
    ("locale", "title", "action", "waiting"),
    [
        (
            "en",
            "HAIFA is becoming GIRO",
            "Click here to transition",
            "The update is waiting for active tasks",
        ),
        (
            "cs",
            "HAIFA se přejmenovává na GIRO",
            "Klikněte zde pro přechod",
            "Aktualizace čeká na dokončení běžících tasků",
        ),
    ],
)
def test_global_migration_alert_retry_and_duplicate_click_browser(
    locale: str, title: str, action: str, waiting: str
) -> None:
    attempts: list[Route] = []
    giro = False

    def envelope(data: Any) -> str:
        return json.dumps({"ok": True, "data": data, "error": None, "warnings": []})

    def serve(route: Route) -> None:
        nonlocal giro
        url = urlsplit(route.request.url)
        assert url.netloc == "haifa.test", route.request.url
        if url.path == "/api/updates/migrate":
            attempts.append(route)
            if len(attempts) == 1:
                route.fulfill(
                    status=409,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "ok": False,
                            "error": {"code": "runs_active", "message": "task 42 is active"},
                        }
                    ),
                )
            elif len(attempts) == 3:
                giro = True
                route.fulfill(
                    content_type="application/json", body=envelope({"status": "installing"})
                )
            return
        if url.path.startswith("/api/"):
            responses = {
                "/api/health": {"app": "haifa-dashboard", "version": "0.1.999", "home": "/home"},
                "/api/repos": {"home": "/home", "repos": []},
                "/api/updates": {
                    "status": "current",
                    "current_version": "1.0.1" if giro else "0.1.999",
                },
                "/api/code": {"started": "new" if giro else "old", "stale": False},
                "/api/limits": {"providers": []},
                "/api/library": {"exists": True, "items": []},
                "/api/machine/check": {"ok": True, "findings": []},
                "/api/guide": {"chapters": []},
            }
            route.fulfill(
                content_type="application/json", body=envelope(responses.get(url.path, {}))
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
        context.add_init_script(
            f'localStorage.setItem("haifa.dashboard.locale", {json.dumps(locale)});'
        )
        context.set_default_timeout(30_000)
        try:
            page = context.new_page()
            page.route("**/*", serve)
            page.goto("http://haifa.test/#/")
            banner = page.locator('[data-test="migration-banner"]')
            expect(banner).to_contain_text(title)
            button = page.locator('[data-test="migration-action"]')
            expect(button).to_have_text(action)
            expect(button).to_be_enabled()
            assert attempts == []
            for screen in ("#/problems", "#/guide", "#/repos/add", "#/setup"):
                page.evaluate("hash => location.hash = hash", screen)
                expect(banner).to_be_visible()
            button.click()
            expect(banner.get_by_role("status")).to_contain_text(waiting)
            banner.locator("summary").click()
            expect(banner.locator("pre")).to_have_text("task 42 is active")
            button.click()
            expect(button).to_be_disabled()
            page.evaluate("document.querySelector('[data-test=migration-action]').click()")
            assert len(attempts) == 2
            attempts[-1].fulfill(
                status=409,
                content_type="application/json",
                body=json.dumps(
                    {
                        "ok": False,
                        "error": {"code": "update_unavailable", "message": "GIRO hosting offline"},
                    }
                ),
            )
            expect(button).to_be_enabled()
            expect(banner.locator("pre")).to_have_text("GIRO hosting offline")
            with page.expect_event("load"):
                button.click()
            expect(page.locator(".brand")).to_be_visible()
            expect(banner).to_have_count(0)
            assert len(attempts) == 3
            assert page.evaluate('localStorage.getItem("haifa.dashboard.locale")') == locale
        finally:
            context.close()
            browser.close()
