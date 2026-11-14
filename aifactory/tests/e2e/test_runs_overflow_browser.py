"""Runs with many phases stay inside their scroll region, using only canned APIs."""

import json
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Page, Route, expect, sync_playwright
from test_f3_browser import _choose, _launch
from test_limits_layout import _server

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


def test_runs_paging_browser() -> None:
    fallback = _server("live")
    requests: list[dict[str, list[str]]] = []

    def serve(route: Route) -> None:
        url = urlsplit(route.request.url)
        if url.path != "/api/repos/haifa/runs":
            fallback(route)
            return
        query = parse_qs(url.query)
        requests.append(query)
        offset = int(query.get("offset", ["0"])[0])
        total = 1 if query.get("state") else 101
        rows = [
            {
                "run_id": f"run-{i}",
                "task_id": "T1",
                "state": "failed",
                "started_at": "2026-01-01T00:00:00Z",
                "phases": [],
            }
            for i in range(offset, min(offset + 100, total))
        ]
        route.fulfill(
            content_type="application/json",
            body=json.dumps(
                {
                    "ok": True,
                    "data": {
                        "runs": rows,
                        "tasks": ["T1"],
                        "total": total,
                        "offset": offset,
                        "limit": 100,
                    },
                    "error": None,
                    "warnings": [],
                }
            ),
        )

    with sync_playwright() as playwright:
        browser = _launch(playwright)
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.route("**/*", serve)
            page.goto("http://haifa.test/#/r/haifa/runs")
            expect(page.locator('[data-test="page-count"]')).to_have_text("1–100 z 101")
            page.locator('[data-test="next-page"]').click()
            expect(page.locator('[data-test="page-count"]')).to_have_text("101–101 z 101")
            expect(page.locator('[data-test="next-page"]')).to_be_disabled()
            page.locator('[data-test="state-filter"]').scroll_into_view_if_needed()
            page.evaluate(
                "() => new Promise(resolve => requestAnimationFrame("
                "() => requestAnimationFrame(resolve)))"
            )
            _choose(page, '[data-test="state-filter"]', "failed")
            expect(page.locator('[data-test="page-count"]')).to_have_text("1–1 z 1")
            expect(page.locator('[data-test="previous-page"]')).to_be_disabled()
            assert requests[-1] == {"state": ["failed"]}
            _assert_document_fits(page)
        finally:
            browser.close()


def _assert_document_fits(page: Page) -> None:
    size = page.evaluate("""() => ({
        viewport: document.documentElement.clientWidth,
        document: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
        x: window.scrollX
    })""")
    if size["document"] > size["viewport"]:
        size["overflowing"] = page.locator("body *").evaluate_all("""els => els
            .filter(el => el.getBoundingClientRect().right > innerWidth)
            .map(el => ({tag: el.tagName, class: el.className,
                right: el.getBoundingClientRect().right})).slice(0, 20)""")
    assert size["document"] <= size["viewport"], size
    assert size["x"] == 0, size


@pytest.mark.parametrize("width", [1366, 390])
def test_runs_overflow_browser(width: int) -> None:
    run: dict[str, Any] = {
        "run_id": "many-phases",
        "task_id": "HAIFA-S01-T111",
        "task_title": "VelmiDlouhyNazevBezMezer" * 20,
        "workflow": "build-review",
        "state": "succeeded",
        "started_at": "2026-01-01T10:00:00+00:00",
        "duration_s": 300,
        "tokens": 1180,
        "cost": 0.25,
        "started_by": "manual",
        "pr": {"url": "https://example.test/pr/7", "pr_id": "7", "state": "open"},
        "archived": False,
        # Reverse the input to also verify ordering, without mutating the fixture.
        "phases": [
            {"seq": seq, "name": f"phase-{seq}", "status": "success"}
            for seq in reversed(range(100))
        ],
    }
    actions: list[str] = []
    fallback = _server("live")

    def serve(route: Route) -> None:
        url = urlsplit(route.request.url)
        assert url.netloc == "haifa.test", route.request.url
        path = url.path
        data: dict[str, Any]
        if path == "/api/repos/haifa/runs":
            data = {"runs": [run]}
        elif path in (
            "/api/repos/haifa/runs/many-phases/archive",
            "/api/repos/haifa/runs/many-phases/unarchive",
            "/api/repos/haifa/runs/many-phases/delete",
        ):
            action = path.rsplit("/", 1)[1]
            assert route.request.method == "POST", (path, route.request.method)
            assert action in ("archive", "unarchive", "delete"), action
            actions.append(action)
            data = {"run": run, "deleted": [run["run_id"]]}
        else:
            fallback(route)
            return
        route.fulfill(
            content_type="application/json",
            body=json.dumps({"ok": True, "data": data, "error": None, "warnings": []}),
        )

    with sync_playwright() as playwright:
        browser = _launch(playwright)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.route("**/*", serve)
            page.goto("http://haifa.test/#/r/haifa/runs")
            region = page.get_by_role("region", name="Seznam běhů")
            expect(region).to_be_visible()
            page.evaluate("document.fonts.ready")
            _assert_document_fits(page)
            # Wrapped topbar controls remain inside the viewport and the header.
            header = page.locator(".topbar").bounding_box()
            assert header is not None
            for control in page.locator(".topbar a, .topbar button").all():
                if not control.is_visible():
                    continue
                box = control.bounding_box()
                assert box is not None
                assert 0 <= box["x"] and box["x"] + box["width"] <= width, box
                assert box["y"] + box["height"] <= header["y"] + header["height"], box
            expect(region.locator(".task-link")).to_contain_text(run["task_title"])
            expect(region.locator('[data-col="pr"]')).to_have_attribute("href", run["pr"]["url"])
            dots = region.locator(".d")
            expect(dots).to_have_count(100)
            assert dots.evaluate_all("els => els.map(el => el.getAttribute('aria-label'))") == [
                f"phase-{seq} — success" for seq in range(100)
            ]
            geometry = region.locator(".dots").evaluate("""el => {
                const box = el.getBoundingClientRect();
                const dots = [...el.querySelectorAll('.d')].map(d => d.getBoundingClientRect());
                return {
                    width: box.width,
                    rows: new Set(dots.map(d => d.top)).size,
                    contained: dots.every(d => d.width >= 15 && d.height > 0 &&
                        d.left >= box.left && d.right <= box.right + 1 &&
                        d.top >= box.top && d.bottom <= box.bottom + 1)
                };
            }""")
            assert geometry["width"] <= 152 and geometry["rows"] > 1, geometry
            assert geometry["contained"], geometry
            expect(region).to_have_css("overflow-x", "auto")
            if width == 390:
                assert region.evaluate("el => el.scrollWidth > el.clientWidth")
                region.focus()
                page.keyboard.press("ArrowRight")
                page.wait_for_function("document.querySelector('.table-scroll').scrollLeft > 0")
                _assert_document_fits(page)

            # Tab reaches every phase, including the wrapped rows and the final icon.
            dots.first.focus()
            for seq in range(100):
                expect(dots.nth(seq)).to_be_focused()
                page.keyboard.press("Tab")
            archive = region.locator('[data-test="archive"]')
            expect(archive).to_be_focused()
            dots.last.scroll_into_view_if_needed()
            dots.last.hover()
            tooltip = page.get_by_role("tooltip", name="phase-99 — success", exact=True)
            expect(tooltip).to_have_text("phase-99 — success")
            expect(tooltip).to_be_visible()
            page.mouse.move(0, 0)
            dots.last.focus()
            expect(tooltip).to_have_text("phase-99 — success")
            page.keyboard.press("Escape")
            expect(tooltip).to_have_count(0)
            _assert_document_fits(page)

            with page.expect_response(lambda response: response.url.endswith("/archive")):
                archive.click()
            expect(page).to_have_url("http://haifa.test/#/r/haifa/runs")
            page.locator('[data-test="view-archived"]').click()
            expect(region.locator('[data-test="unarchive"]')).to_be_enabled()
            with page.expect_response(lambda response: response.url.endswith("/unarchive")):
                region.locator('[data-test="unarchive"]').click()
            region.locator('[data-test="delete"]').click()
            with page.expect_response(lambda response: response.url.endswith("/delete")):
                page.locator('[data-test="confirm-ok"]').click()
            expect(page.locator('[data-test="confirm-dialog"]')).to_have_count(0)
            assert actions == ["archive", "unarchive", "delete"]
            _assert_document_fits(page)

            # Both a link and the rest of the row still open the same run.
            region.locator('[data-col="tokens"]').click()
            expect(page).to_have_url("http://haifa.test/#/r/haifa/runs/many-phases")
            page.goto("http://haifa.test/#/r/haifa/runs")
            page.locator(".task-link").click()
            expect(page).to_have_url("http://haifa.test/#/r/haifa/runs/many-phases")
        finally:
            browser.close()
