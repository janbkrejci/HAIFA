"""Global locale acceptance against shipped assets, with canned APIs and no live models."""

import json
from datetime import UTC, datetime
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Route, expect, sync_playwright
from test_f3_browser import _choose, _launch
from test_run_waterfall_scroll_browser import _detail, _long_phases, _serve
from test_runs_overflow_browser import _assert_document_fits
from test_theme_forms_browser import _serve as _global_serve

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]
LANGUAGE = '[data-test="language-select"]'


def _language(page: Page, language: str) -> None:
    selector = (
        f'[data-test="assistant-panel"] {LANGUAGE}'
        if page.locator('[data-test="assistant-panel"]').count()
        else LANGUAGE
    )
    _choose(page, selector, language)
    expect(page.locator("html")).to_have_attribute("lang", language)
    assert page.evaluate("localStorage.getItem('haifa.dashboard.locale')") == language


@pytest.mark.parametrize("width", [1366, 390])
def test_global_locale_browser(width: int) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    detail = _detail("watched", "running", start, _long_phases("watched", start))
    run_serve = _serve({"watched": detail})
    registered = False
    writes: list[str] = []

    def serve(route: Route) -> None:
        path = urlsplit(route.request.url).path
        data: object
        if route.request.method == "POST":
            writes.append(path)
        if path == "/api/repos":
            data = {
                "home": "/home",
                "repos": [
                    {"id": name, "name": name, "path": f"/repos/{name}", "status": "ok"}
                    for name in (["haifa", "second"] if registered else [])
                ],
            }
        elif path == "/api/repos/haifa/backlog":
            data = {
                "levels": ["project", "step", "task"],
                "backlog_dir": "factory/backlog",
                "filters": {"status": None},
                "states": ["todo", "ready", "running", "done"],
                "workflows": [],
                "steps": [],
                "items": [],
                "tasks": [],
                "issues": [],
                "counts": {},
            }
        elif path == "/api/dashboard/settings" and route.request.method == "POST":
            route.fulfill(
                status=400,
                content_type="application/json",
                body=json.dumps(
                    {
                        "ok": False,
                        "data": None,
                        "warnings": [],
                        "error": {
                            "code": "invalid_settings",
                            "message": "Raw server diagnostic",
                            "issues": [{"code": "invalid", "id": "port", "message": "raw"}],
                        },
                    }
                ),
            )
            return
        elif path.startswith("/api/repos/") and (
            "/runs" in path or path.endswith("/live") or path.endswith("/limits")
        ):
            run_serve(route)
            return
        else:
            _global_serve(route)
            return
        route.fulfill(
            content_type="application/json",
            body=json.dumps({"ok": True, "data": data, "error": None, "warnings": []}),
        )

    with sync_playwright() as playwright:
        browser = _launch(playwright)
        context = browser.new_context(
            locale="cs-CZ", viewport={"width": width, "height": 900}, service_workers="block"
        )
        try:
            page = context.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script("""window.EventSource = class extends EventTarget {
                constructor() { super(); window.localeStreams = (window.localeStreams || 0) + 1; }
                close() {}
            }""")
            page.route("**/*", serve)
            response = page.goto("http://haifa.test/#/overview")
            assert response is not None and '<html lang="en">' in response.text()
            # A Czech browser still boots in English, even with no repositories.
            expect(page.locator("html")).to_have_attribute("lang", "en")
            expect(page.locator("main h1")).to_have_text("No repositories")
            expect(page.locator(LANGUAGE)).to_have_attribute("aria-label", "Language")
            # Keyboard selection is available in the global topbar.
            page.locator(LANGUAGE).focus()
            page.keyboard.press("ArrowDown")
            page.keyboard.press("End")
            page.keyboard.press("Enter")
            expect(page.locator("html")).to_have_attribute("lang", "cs")
            expect(page.locator("main h1")).to_have_text("Žádné repozitáře")
            page.reload()
            expect(page.locator("html")).to_have_attribute("lang", "cs")
            registered = True
            for identifier in ("haifa", "second"):
                page.goto(f"http://haifa.test/#/r/{identifier}/runs")
                expect(page.locator("nav.screen-tabs")).to_contain_text("Běhy")
                expect(page.locator("html")).to_have_attribute("lang", "cs")
            _language(page, "en")
            page.reload()
            expect(page.locator("html")).to_have_attribute("lang", "en")

            # A form and the open assistant panel retain their DOM and unfinished input.
            page.goto("http://haifa.test/#/setup")
            port = page.locator('[data-test="dash-port"]')
            port.fill("4801")
            page.locator('[data-test="assistant-toggle"]').click()
            panel = page.locator('[data-test="assistant-panel"]')
            draft = page.locator('[data-test="assistant-input"]')
            draft.fill("Český user draft")
            port.evaluate("el => { window.localePort = el }")
            panel.evaluate("el => { window.localePanel = el }")
            for language in ("cs", "en"):
                _language(page, language)
                expect(port).to_have_value("4801")
                expect(draft).to_have_value("Český user draft")
                assert port.evaluate("el => el === window.localePort")
                assert panel.evaluate("el => el === window.localePanel")
                expect(page.locator('[data-test="assistant-send"]')).to_have_text(
                    "Odeslat" if language == "cs" else "Send"
                )
            page.locator('[data-test="assistant-close"]').click()
            page.locator('[data-test="dash-port-save"]').click()
            failure = page.locator('[data-test="dash-port-error"]')
            expect(failure).to_have_text("The port must be an integer from 1 to 65535.")
            _language(page, "cs")
            expect(failure).to_have_text("Port musí být celé číslo od 1 do 65535.")
            _language(page, "en")
            expect(failure).to_have_text("The port must be an integer from 1 to 65535.")
            assert writes == ["/api/dashboard/settings"]
            _assert_document_fits(page)

            # Switching cannot submit, clear or recreate a drafted Intent.
            page.goto("http://haifa.test/#/r/haifa/backlog/intent")
            intent = page.locator('[data-test="intent-text"]')
            intent.fill("Můj rozepsaný Intent")
            intent.evaluate("el => { window.localeIntent = el }")
            for language in ("cs", "en"):
                _language(page, language)
                expect(intent).to_have_value("Můj rozepsaný Intent")
                assert intent.evaluate("el => el === window.localeIntent")
            assert writes == ["/api/dashboard/settings"]
            # Accept the normal unsaved-work warning for this abandoned draft.
            page.once("dialog", lambda dialog: dialog.accept())
            page.reload()
            page.goto("http://haifa.test/#/r/haifa/runs/watched")
            region = page.locator('[data-test="waterfall-scroll"]')
            expect(region).to_be_visible()
            expect(region).to_have_attribute("data-overflow", "true")
            follow = page.locator(".wf-follow input")
            follow.uncheck()
            region.evaluate("el => { window.localeWaterfall = el; el.scrollLeft = 250 }")
            streams = page.evaluate("window.localeStreams")
            for language in ("cs", "en"):
                _language(page, language)
                expect(follow).not_to_be_checked()
                assert region.evaluate("el => el === window.localeWaterfall")
                assert abs(region.evaluate("el => el.scrollLeft") - 250) < 2
                assert page.evaluate("window.localeStreams") == streams
                expect(page.locator('.lane[data-lane="engineer"] .lane-meta')).to_have_text(
                    "požadavek" if language == "cs" else "request"
                )
            _assert_document_fits(page)
            assert not errors, errors
        finally:
            context.close()
            browser.close()
