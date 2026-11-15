"""Localized guide in shipped assets, with static API fixtures and no live services."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Route, expect, sync_playwright
from test_f3_browser import _launch
from test_theme_forms_browser import _serve

from aifactory import guide

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


def _guide_serve(route: Route) -> None:
    url = urlsplit(route.request.url)
    if url.path != "/api/guide":
        _serve(route)
        return
    locale = parse_qs(url.query)["locale"][0]
    assert locale in {"en", "cs"}
    route.fulfill(
        content_type="application/json",
        body=json.dumps(
            {
                "ok": True,
                "data": {"chapters": [c.as_dict() for c in guide.chapters(locale=locale)]},
                "error": None,
                "warnings": [],
            }
        ),
    )


def test_guide_default_english_saved_czech_and_return_to_english() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        context = browser.new_context(
            locale="cs-CZ", viewport={"width": 390, "height": 844}, service_workers="block"
        )
        try:
            page = context.new_page()
            page.route("**/*", _guide_serve)
            page.goto("http://haifa.test/#/guide/prvni-beh/harnessy-tohoto-pocitace")
            article = page.locator('[data-test="guide-article"]')
            search = page.locator('[data-test="guide-search"]')
            section = article.locator("#harnessy-tohoto-pocitace")
            # Czech browser language must not select Czech UI automatically.
            expect(page).to_have_title("Guide · GIRO")
            expect(page.locator("a.brand")).to_have_text("giro")
            expect(page.locator("a.brand")).to_have_attribute(
                "aria-label", "GIRO — Goal in. Release out."
            )
            expect(article.locator("h1")).to_have_text("First run")
            expect(section).to_have_text("Harnesses on this machine")
            expect(search).to_have_attribute("aria-label", "Search the guide")
            expect(article).not_to_contain_text("<!-- section:")
            assert page.locator(".guide").evaluate("el => el.scrollWidth <= el.clientWidth")

            # Exercise the saved preference directly; GuideView.test.ts covers live switching.
            page.evaluate("localStorage.setItem('haifa.dashboard.locale', 'cs')")
            page.reload()
            expect(article.locator("h1")).to_have_text("První běh")
            expect(section).to_have_text("Harnessy tohoto počítače")
            expect(search).to_have_attribute("aria-label", "Hledat v příručce")
            page.reload()
            expect(article.locator("h1")).to_have_text("První běh")
            search.fill("výchozí model")
            expect(page.locator('[data-test="guide-hit"]').first).to_have_attribute(
                "href", "#/guide/prvni-beh/harnessy-tohoto-pocitace"
            )
            page.evaluate("localStorage.setItem('haifa.dashboard.locale', 'en')")
            page.reload()
            expect(article.locator("h1")).to_have_text("First run")
            expect(section).to_have_text("Harnesses on this machine")
            expect(page).to_have_url("http://haifa.test/#/guide/prvni-beh/harnessy-tohoto-pocitace")
        finally:
            context.close()
            browser.close()
