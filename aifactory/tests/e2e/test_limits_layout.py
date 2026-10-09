"""Measure the shipped dashboard in bundled Chromium, with no backend or network."""

import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Route, sync_playwright

STATIC = Path(__file__).resolve().parents[2] / "src/aifactory/web/static"
# Share the browser group so full-suite xdist runs do not launch layout browsers
# alongside the dashboard acceptance scenarios.
pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


def _provider(harness: str, state: str) -> dict[str, Any]:
    return {
        "harness": harness,
        "label": harness.title(),
        "stale": state == "stale",
        "error": "offline" if state != "live" else None,
        "measured_at": "2026-10-06T10:00:00+00:00",
        "windows": []
        if state == "unavailable"
        else [
            {"id": window, "label": window, "used": 0, "left": 100, "resets_at": None}
            for window in ("5h", "1w")
        ],
    }


@pytest.mark.parametrize("state", ["live", "stale", "unavailable"])
def test_stacked_limits_do_not_overlap_topbar_controls(state: str) -> None:
    def serve(route: Route) -> None:
        path = urlsplit(route.request.url).path
        if path.startswith("/api/"):
            data: Any = {}
            # The repo page asks the repo endpoint, other pages the global one.
            if path in ("/api/repos/haifa/limits", "/api/limits"):
                # Deliberately reversed: the UI owns the stable provider order.
                data = {"providers": [_provider("codex", state), _provider("claude", state)]}
            elif path == "/api/health":
                data = {"app": "haifa-dashboard", "version": "2.14.0", "home": "C:/haifa"}
            elif path == "/api/repos":
                data = {
                    "home": "C:/haifa",
                    "repos": [
                        {
                            "id": "haifa",
                            "name": "HAIFA",
                            "path": "C:/repos/HAIFA",
                            "added_at": "2026-10-06T10:00:00+00:00",
                            "status": "ok",
                            "factory": None,
                        }
                    ],
                }
            route.fulfill(
                content_type="application/json",
                body=json.dumps({"ok": True, "data": data, "error": None, "warnings": []}),
            )
            return
        asset = STATIC / (path.lstrip("/") or "index.html")
        if asset.is_file() and asset.resolve().is_relative_to(STATIC.resolve()):
            route.fulfill(
                body=asset.read_bytes(),
                content_type=mimetypes.guess_type(asset.name)[0] or "application/octet-stream",
            )
        else:
            route.abort()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route("**/*", serve)
        for width in (1600, 1366, 1280):
            page.set_viewport_size({"width": width, "height": 900})
            page.goto("http://haifa.test/#/r/haifa/backlog")
            page.locator('[data-test="limits-codex"]').wait_for()
            page.locator(".repo-switcher").wait_for()
            page.evaluate("document.fonts.ready")
            rows = [page.locator(f'[data-test="limits-{name}"]') for name in ("claude", "codex")]
            boxes = [row.bounding_box() for row in rows]
            assert all(box is not None for box in boxes)
            claude, codex = boxes
            assert claude is not None and codex is not None
            assert claude["y"] + claude["height"] <= codex["y"], (width, state, boxes)
            controls = page.locator(".theme-toggle, .repo-switcher, .view-toggle a, .brand")
            control_boxes = [control.bounding_box() for control in controls.all()]
            for row in rows:
                # Measure the actual contents: a shrinking parent can conceal overflow.
                contents = row.locator(
                    ".limit-name, .limit-window, [data-test$='-unavailable'], "
                    "[data-test='limits-stale']"
                )
                content_boxes: list[dict[str, float]] = []
                for content in contents.all():
                    box = content.bounding_box()
                    assert box is not None
                    assert 0 <= box["x"] and box["x"] + box["width"] <= width
                    for control in [*control_boxes, *content_boxes]:
                        assert control is not None
                        overlaps = (
                            box["x"] < control["x"] + control["width"]
                            and box["x"] + box["width"] > control["x"]
                            and box["y"] < control["y"] + control["height"]
                            and box["y"] + box["height"] > control["y"]
                        )
                        assert not overlaps, (
                            width,
                            state,
                            content.get_attribute("data-test"),
                            box,
                            control,
                        )
                    content_boxes.append(
                        {
                            "x": box["x"],
                            "y": box["y"],
                            "width": box["width"],
                            "height": box["height"],
                        }
                    )
            if state != "unavailable":
                assert page.locator(".limit-window").count() == 4
        # Resize the mounted dashboard across the inclusive CSS breakpoint.
        # Hidden limits must occupy no space, and must return when widened again.
        for width in (1180, 1179, 1024, 1181, 1280):
            page.set_viewport_size({"width": width, "height": 900})
            limits = page.locator('[data-test="limits"]')
            assert limits.count() == 1
            assert limits.is_visible() == (width > 1180), (width, state)
            for harness in ("claude", "codex"):
                row = page.locator(f'[data-test="limits-{harness}"]')
                assert row.is_visible() == (width > 1180), (width, state, harness)
                if width <= 1180:
                    assert row.bounding_box() is None
            assert page.locator(".theme-toggle").is_visible()
            assert page.locator(".repo-switcher").is_visible()
        browser.close()
