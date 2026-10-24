"""Theme regression coverage against shipped assets, without backend or live services."""

import json
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Locator, Route, expect, sync_playwright
from test_f3_browser import _launch

STATIC = Path(__file__).resolve().parents[2] / "src/aifactory/web/static"
pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


def _serve(route: Route) -> None:
    url = urlsplit(route.request.url)
    assert url.netloc == "haifa.test", route.request.url
    if url.path.startswith("/api/"):
        responses = {
            "/api/health": {"app": "haifa-dashboard", "version": "test", "home": "/home"},
            "/api/repos": {"home": "/home", "repos": []},
            "/api/limits": {"providers": []},
            "/api/library": {"exists": False, "items": []},
            "/api/library/overrides": {"overrides": [], "errors": []},
            "/api/library/inventory": {
                "repos": [{"id": "example", "name": "Example", "rules": []}],
                "items": [],
                "errors": [],
            },
            "/api/dashboard/settings": {"port": 4700, "registry": "/registry", "home": "/home"},
            "/api/machine/check": {"findings": [], "checked_at": "2026-10-24T00:00:00Z"},
        }
        route.fulfill(
            content_type="application/json",
            body=json.dumps(
                {"ok": True, "data": responses.get(url.path, {}), "error": None, "warnings": []}
            ),
        )
        return
    asset = STATIC / (url.path.lstrip("/") or "index.html")
    assert asset.resolve().is_relative_to(STATIC.resolve()) and asset.is_file(), url.path
    route.fulfill(
        body=asset.read_bytes(),
        content_type=mimetypes.guess_type(asset.name)[0] or "application/octet-stream",
    )


def _assert_field(field: Locator, palette: dict[str, str], radius: str = "6px") -> None:
    expect(field).to_have_css("background-color", palette["panel-2"])
    expect(field).to_have_css("color", palette["text"])
    expect(field).to_have_css("border-top-color", palette["border"])
    expect(field).to_have_css("border-top-width", "1px")
    expect(field).to_have_css("border-top-style", "solid")
    expect(field).to_have_css("border-radius", radius)


def test_theme_form_styles_browser() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        context = browser.new_context(color_scheme="dark", service_workers="block")
        try:
            page = context.new_page()
            page.route("**/*", _serve)
            failed: list[str] = []
            assets: list[str] = []
            page.on("requestfailed", lambda request: failed.append(request.url))
            page.on(
                "response",
                lambda response: (
                    assets.append(response.url)
                    if "/assets/" in response.url and response.ok
                    else None
                ),
            )
            page.goto("http://haifa.test/#/setup")
            port = page.locator('[data-test="dash-port"]')
            expect(port).to_be_visible()
            repo = page.locator('[data-test="inventory-repo"]')
            repo.scroll_into_view_if_needed()
            repo.click()
            page.locator('[role="option"][data-value="example"]').click()
            ignore = page.locator('[data-test="ignore-value"]')
            expect(ignore).to_be_visible()

            # Outside the app's .global-page styles: these controls have no local styling.
            page.evaluate("""() => {
                const probes = document.createElement('section');
                probes.id = 'theme-probes';
                probes.innerHTML = '<button id="theme-start">Start</button>' +
                    '<textarea placeholder="Note"></textarea>' +
                    '<input placeholder="Untyped">' +
                    ['text', 'search', 'number', 'url', 'password', 'email', 'tel']
                        .map(type => `<input type="${type}" placeholder="Value">`).join('') +
                    '<select><option>Option</option></select>' +
                    '<input type="checkbox"><input type="radio">' +
                    '<input type="checkbox" class="switch">';
                document.body.append(probes);
            }""")
            fields = page.locator(
                '#theme-probes textarea, #theme-probes input:not([type="checkbox"])'
                ':not([type="radio"]), #theme-probes select'
            )
            expect(fields).to_have_count(10)
            for theme in ("dark", "light"):
                if theme == "dark":
                    # Exercise the default :root palette without a theme attribute.
                    page.evaluate("document.documentElement.removeAttribute('data-theme')")
                else:
                    page.locator(".theme-toggle").click()
                expect(page.locator("html")).to_have_css("color-scheme", theme)
                palette: dict[str, str] = page.evaluate("""() => {
                    const probe = document.createElement('span');
                    document.body.append(probe);
                    const colors = {};
                    for (const name of ['panel', 'panel-2', 'panel-3', 'text', 'border',
                                        'faint', 'cyan', 'dim']) {
                        probe.style.color = `var(--${name})`;
                        colors[name] = getComputedStyle(probe).color;
                    }
                    probe.remove();
                    return colors;
                }""")
                # Theme variables must themselves stay dark/light, not merely match fields.
                text_rgb = [int(v) for v in palette["text"][4:-1].split(",")]
                panel_rgb = [int(v) for v in palette["panel-2"][4:-1].split(",")]
                assert all(v < 64 if theme == "dark" else v > 224 for v in panel_rgb)
                assert all(v > 224 if theme == "dark" else v < 64 for v in text_rgb)
                page.locator("#theme-start").focus()
                for field in fields.all():
                    _assert_field(field, palette)
                    expect(field).to_have_css(
                        "font-family",
                        page.locator("body").evaluate("el => getComputedStyle(el).fontFamily"),
                    )
                    if field.evaluate("el => el.tagName !== 'SELECT'"):
                        assert (
                            field.evaluate("el => getComputedStyle(el, '::placeholder').color")
                            == palette["faint"]
                        )
                    page.keyboard.press("Tab")
                    expect(field).to_be_focused()
                    expect(field).to_have_css("outline-color", palette["cyan"])
                    expect(field).to_have_css("outline-style", "solid")
                    expect(field).to_have_css("outline-width", "2px")

                _assert_field(ignore, palette)
                _assert_field(port, palette, radius="8px")
                # DashboardSettings' scoped size and radius override the global defaults.
                expect(port).to_have_css("font-size", "15px")
                expect(port).to_have_css("width", "110px")
                for kind, radius, width, height, background in (
                    ('[type="checkbox"]:not(.switch)', "5px", "18px", "18px", "panel"),
                    ('[type="radio"]', "50%", "18px", "18px", "panel"),
                    (".switch", "999px", "38px", "22px", "panel-3"),
                ):
                    control = page.locator(f"#theme-probes input{kind}")
                    expect(control).to_have_css("appearance", "none")
                    expect(control).to_have_css("border-radius", radius)
                    expect(control).to_have_css("width", width)
                    expect(control).to_have_css("height", height)
                    expect(control).to_have_css("background-color", palette[background])
                    control.check()
                    expect(control).to_have_css("background-color", palette["cyan"])
                # Reset even the radio so both themes exercise unchecked and checked states.
                page.locator("#theme-probes input:checked").evaluate_all(
                    "controls => controls.forEach(el => { el.checked = false })"
                )
            assert any(url.endswith(".css") for url in assets), assets
            assert any(url.endswith(".js") for url in assets), assets
            assert not failed
        finally:
            context.close()
            browser.close()
