"""A slow repository stays in a loading card until its overview arrives."""

import json
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Route, expect, sync_playwright
from test_f3_browser import _launch
from test_limits_layout import _server

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


def test_slow_repo_loading_overlay() -> None:
    item: dict[str, Any] = {
        "id": "haifa",
        "name": "HAIFA",
        "path": "C:/repos/HAIFA",
        "state": "timeout",
        "config": None,
        "factory": None,
        "tasks": None,
        "running": [],
        "review": [],
        "failed": [],
        "warnings": ["repository haifa did not answer within 2 s"],
        "last_activity": None,
    }
    fallback = _server("live")

    def serve(route: Route) -> None:
        if urlsplit(route.request.url).path != "/api/overview":
            fallback(route)
            return
        route.fulfill(
            content_type="application/json",
            body=json.dumps({"ok": True, "data": {"repos": [item]}, "warnings": []}),
        )

    with sync_playwright() as playwright:
        browser = _launch(playwright)
        try:
            page = browser.new_page()
            page.route("**/*", serve)
            page.goto("http://haifa.test/#/overview")
            card = page.locator('[data-test="overview-card"][data-repo="haifa"]')
            overlay = card.locator('[data-test="repo-loading"]')
            expect(overlay).to_be_visible()
            expect(card).to_have_attribute("aria-busy", "true")
            expect(card.locator('[data-test="spinner"]')).to_be_visible()
            expect(page.get_by_text("Repo neodpovědělo včas")).to_have_count(0)
            expect(card.locator('[data-test="card-warnings"]')).to_have_count(0)
            card_box, overlay_box = card.bounding_box(), overlay.bounding_box()
            assert card_box is not None and overlay_box is not None
            assert overlay_box["height"] > 50
            assert overlay_box["x"] >= card_box["x"]
            assert overlay_box["y"] + overlay_box["height"] <= (card_box["y"] + card_box["height"])

            item.update(state="ok", warnings=[])
            page.locator('[data-test="overview-refresh"]').click()
            expect(page.locator('[data-test="repo-loading"]')).to_have_count(0)
            expect(page.locator('[data-test="calm-repo"][data-repo="haifa"]')).to_be_visible()
        finally:
            browser.close()


def test_overview_legacy_preview_requires_explicit_repository_decision() -> None:
    settings = {
        "settings": {"version": 1, "auto_merge": False, "auto_continue": False, "harness": None},
        "effective_harness": None,
    }
    item: dict[str, Any] = {
        "id": "haifa",
        "name": "HAIFA",
        "path": "C:/repos/HAIFA",
        "state": "ok",
        "config": None,
        "factory": None,
        "tasks": None,
        "running": [],
        "review": [],
        "failed": [],
        "warnings": [],
        "last_activity": None,
        "local_settings": settings,
    }
    preview = {
        "local_exists": False,
        "nodes": [
            {
                "id": "P",
                "level": "project",
                "values": {"auto_merge": {"value": True, "origin": {"id": "P"}}},
            },
            {
                "id": "P-S-T01",
                "level": "task",
                "values": {"auto_merge": {"value": False, "origin": {"id": "P-S-T01"}}},
            },
        ],
        "proposals": {
            "auto_merge": {"conflict": True, "value": None},
            "auto_continue": {"conflict": False, "value": False},
            "harness": {"conflict": False, "value": None},
        },
    }
    submitted: list[object] = []
    fallback = _server("live")

    def serve(route: Route) -> None:
        path = urlsplit(route.request.url).path
        data: dict[str, Any]
        if path == "/api/overview":
            data = {"repos": [item]}
        elif path.endswith("/settings/local/legacy"):
            if route.request.method == "POST":
                submitted.append(route.request.post_data_json)
                data = settings
            else:
                data = preview
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
            page = browser.new_page()
            page.route("**/*", serve)
            page.goto("http://haifa.test/#/overview")
            controls = page.locator('[data-test="local-repo-controls"]')
            controls.locator('[data-test="legacy-preview"]').click()
            expect(controls.locator('[data-test="legacy-panel"]')).to_contain_text("P-S-T01")
            take = controls.locator('[data-test="legacy-import"]')
            expect(take).to_be_disabled()
            assert submitted == []
            controls.locator('[data-test="legacy-choice-auto_merge"]').click()
            page.get_by_role("option", name="Vypnuto", exact=True).click()
            expect(take).to_be_enabled()
            take.click()
            expect(controls.locator('[data-test="legacy-panel"]')).to_have_count(0)
            expect(controls.locator('[data-test="local-auto-merge"]')).not_to_be_checked()
            assert submitted == [{"choices": {"auto_merge": False}, "overwrite": False}]
        finally:
            browser.close()
