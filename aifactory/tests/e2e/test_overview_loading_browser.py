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
            page.add_init_script("localStorage.setItem('haifa.dashboard.locale', 'cs')")
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


def test_overview_shows_local_controls_without_legacy_preview() -> None:
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
    submitted: list[object] = []
    fallback = _server("live")

    def serve(route: Route) -> None:
        path = urlsplit(route.request.url).path
        data: dict[str, Any]
        if path == "/api/overview":
            data = {"repos": [item]}
        elif path.endswith("/settings/local/legacy"):
            submitted.append(route.request.method)
            data = {}
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
            page.add_init_script("localStorage.setItem('haifa.dashboard.locale', 'cs')")
            page.route("**/*", serve)
            page.goto("http://haifa.test/#/overview")
            controls = page.locator('[data-test="local-repo-controls"]')
            expect(controls).to_be_visible()
            expect(controls.locator('[data-test="legacy-preview"]')).to_have_count(0)
            expect(controls.locator('[data-test="legacy-panel"]')).to_have_count(0)
            expect(controls.locator('[data-test="local-auto-merge"]')).not_to_be_checked()
            expect(controls.locator('[data-test="local-auto-continue"]')).not_to_be_checked()
            assert submitted == []
        finally:
            browser.close()


def test_overview_backlog_indicator_refreshes_in_both_modes() -> None:
    counts = dict.fromkeys(
        (
            "todo",
            "ready",
            "human",
            "blocked",
            "failed",
            "running",
            "in review",
            "approved",
            "awaiting merge",
            "done",
            "cancelled",
        ),
        0,
    )
    counts["done"] = 1
    projects = [
        {"id": "A", "title": "Finished", "tasks": counts},
        {"id": "B", "title": "Also finished", "tasks": counts},
    ]
    calm: dict[str, Any] = {
        "id": "haifa",
        "name": "HAIFA",
        "path": "/repos/haifa",
        "state": "ok",
        "config": None,
        "factory": None,
        "tasks": counts,
        "projects": projects,
        "running": [],
        "review": [],
        "failed": [],
        "warnings": [],
        "last_activity": None,
        "backlog": {"state": "dirty", "count": 2, "error": None},
    }
    active = {
        **calm,
        "id": "active",
        "name": "Active",
        "review": [
            {
                "task_id": "B-T01",
                "task_title": "Review",
                "pr_id": "1",
                "project": "B",
                "url": "https://example.test/pr/1",
                "branch": "task",
                "opened_at": None,
                "age_s": None,
                "source": "trace",
            }
        ],
    }
    fallback = _server("live")

    def serve(route: Route) -> None:
        path = urlsplit(route.request.url).path
        if path == "/api/repos":
            route.fulfill(
                content_type="application/json",
                body=json.dumps(
                    {
                        "ok": True,
                        "data": {
                            "repos": [
                                {
                                    "id": item["id"],
                                    "name": item["name"],
                                    "path": item["path"],
                                    "added_at": "",
                                    "status": "ok",
                                    "factory": None,
                                }
                                for item in (calm, active)
                            ]
                        },
                        "warnings": [],
                    }
                ),
            )
            return
        if path != "/api/overview":
            fallback(route)
            return
        route.fulfill(
            content_type="application/json",
            body=json.dumps(
                {
                    "ok": True,
                    "data": {"repos": [calm, active]},
                    "warnings": [],
                }
            ),
        )

    with sync_playwright() as playwright:
        browser = _launch(playwright)
        try:
            page = browser.new_page()
            page.add_init_script("localStorage.setItem('haifa.dashboard.locale', 'cs')")
            page.route("**/*", serve)
            page.goto("http://haifa.test/#/overview")
            calm_row = page.locator('[data-test="calm-repo"][data-repo="haifa"]')
            active_card = page.locator('[data-test="overview-card"][data-repo="active"]')
            expect(calm_row.locator('[data-test="project-section"]')).to_have_count(0)
            expect(active_card.locator('[data-test="project-section"]')).to_have_count(1)
            expect(active_card.locator('[data-test="row-review"]')).to_have_count(1)
            expect(
                page.locator('[data-test="total-review"] [data-test="total-count"]')
            ).to_have_text("1")
            toggle = page.locator('[data-test="show-finished"]')
            toggle.check()
            expect(calm_row.locator('[data-test="project-section"]')).to_have_count(2)
            page.reload()
            expect(toggle).to_be_checked()
            expect(calm_row.locator('[data-test="project-section"]')).to_have_count(2)
            toggle.uncheck()
            # Reopening a task restores its project on the next overview read.
            projects[0]["tasks"] = {**counts, "done": 0, "ready": 1}
            page.locator('[data-test="overview-refresh"]').click()
            expect(calm_row.locator('[data-test="project-section"]')).to_have_count(1)
            expect(calm_row.locator('[data-test="project-section"]')).to_have_attribute(
                "data-project", "A"
            )
            page.locator('[data-test="by-project"]').uncheck()
            expect(toggle).to_have_count(0)
            expect(calm_row.locator('[data-test="task-summary"]')).to_contain_text("Hotovo")
            for grouped in (True, False):
                page.locator('[data-test="by-project"]').set_checked(grouped)
                for repo_id, selector in (("haifa", "calm-repo"), ("active", "overview-card")):
                    row = page.locator(f'[data-test="{selector}"][data-repo="{repo_id}"]')
                    link = row.locator('[data-test="repo-backlog-status"]')
                    expect(link).to_have_count(1)
                    expect(link).to_be_visible()
                    expect(link).to_have_text("Necommitnutý backlog: 2 soubory")
                    expect(link).to_have_attribute("href", f"#/r/{repo_id}/backlog")
            calm["backlog"] = {"state": "clean", "count": 0, "error": None}
            active["backlog"] = {"state": "error", "count": None, "error": "denied"}
            # The ordinary overview poll removes the committed indication without a reload.
            expect(
                page.locator('[data-repo="haifa"] [data-test="repo-backlog-status"]')
            ).to_have_count(0)
            expect(
                page.locator('[data-repo="active"] [data-test="repo-backlog-status"]')
            ).to_have_text("Stav backlogu se nepodařilo přečíst")
            page.locator('[data-repo="active"] [data-test="repo-backlog-status"]').click()
            expect(page).to_have_url("http://haifa.test/#/r/active/backlog")
        finally:
            browser.close()


@pytest.mark.parametrize(
    "locale,heading,running_label", [("en", "Overview", "Running"), ("cs", "Přehled", "Běží")]
)
def test_overview_locale_at_narrow_width(locale: str, heading: str, running_label: str) -> None:
    """Each client renders its own locale; long filter labels fit at 390 px."""
    item: dict[str, Any] = {
        "id": "haifa",
        "name": "Moje české repo",
        "path": "/work/ukázka",
        "state": "ok",
        "config": None,
        "factory": None,
        "tasks": None,
        "running": [],
        "review": [],
        "failed": [],
        "warnings": [],
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
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.add_init_script(
                f"localStorage.setItem('haifa.dashboard.locale', {json.dumps(locale)})"
            )
            page.route("**/*", serve)
            page.goto("http://haifa.test/#/overview")
            view = page.locator('[data-test="repo-page"]')
            expect(view.locator("h1")).to_have_text(heading)
            expect(view.locator('[data-test="total-running"]')).to_contain_text(running_label)
            expect(view.locator('[data-test="calm-repo"]')).to_contain_text("Moje české repo")
            for button in view.locator(".total").all():
                expect(button).to_be_visible()
                box = button.bounding_box()
                assert box is not None and box["x"] >= 0 and box["x"] + box["width"] <= 390
            assert view.evaluate("el => el.scrollWidth <= el.clientWidth")
            view.locator('[data-test="total-running"]').click()
            expect(view.locator('[data-test="total-running"]')).to_have_attribute(
                "aria-pressed", "true"
            )
            expect(view.locator('[data-test="calm-repo"]')).to_have_count(0)
            page.reload()
            expect(view.locator("h1")).to_have_text(heading)
        finally:
            browser.close()
