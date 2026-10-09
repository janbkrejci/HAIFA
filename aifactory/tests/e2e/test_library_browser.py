"""First start creates a seeded library after reviewing its plan, with no external calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from f3_repo import api_get, git, obs_server
from multi_repo_e2e import diagnostic_tripwire
from playwright.sync_api import Dialog, Route, expect, sync_playwright
from test_f3_browser import _launch

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


def test_library_seed_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    script = tmp_path / "fake.json"
    script.write_text(json.dumps({"agents": {}}), encoding="utf-8")
    wire, marker = diagnostic_tripwire(tmp_path)
    home = tmp_path / "haifa-home"
    external: list[str] = []
    dialogs: list[str] = []
    with obs_server(None, script, wire, tmp_path / "obs.log", home) as server:
        with sync_playwright() as playwright:
            browser = _launch(playwright)
            context = browser.new_context(base_url=server.url, service_workers="block")
            context.set_default_timeout(60_000)
            expect.set_options(timeout=60_000)

            def local_only(route: Route) -> None:
                if not route.request.url.startswith(server.url + "/"):
                    external.append(route.request.url)
                    route.abort()
                elif "/api/machine/check" in route.request.url:
                    # Real machine probes, explicitly offline even on an authenticated machine.
                    query = "&" if "?" in route.request.url else "?"
                    route.continue_(url=route.request.url + query + "offline=1")
                else:
                    route.continue_()

            context.route("**/*", local_only)
            page = context.new_page()

            def dismiss(dialog: Dialog) -> None:
                dialogs.append(dialog.message)
                dialog.dismiss()

            page.on("dialog", dismiss)
            try:
                page.goto("/")
                expect(page).to_have_url(f"{server.url}/#/overview")
                page.locator('[data-test="readiness-warning"]').click()
                expect(page).to_have_url(f"{server.url}/#/problems")
                page.locator('[data-test="readiness-warning"] a[href="#/setup"]').first.click()
                expect(page).to_have_url(f"{server.url}/#/setup")
                expect(page.locator("h1")).to_have_text("Tento počítač")
                page.locator('[data-test="library-init"]').click()
                modal = page.locator('[data-test="confirm-dialog"]')
                expect(modal).to_contain_text("Založit knihovnu ze semínka")
                expect(modal).to_contain_text("agent/builder")
                assert not (home / "library").exists()
                modal.locator('[data-test="confirm-ok"]').click()
                expect(page.locator('[data-test="library-path"]')).to_have_text(
                    str(home / "library")
                )
                assert git(home / "library", "rev-list", "--count", "HEAD") == "1"
                page.locator('[data-test="switcher-button"]').click()
                page.locator('[data-test="switch-library"]').click()
                expect(page).to_have_url(f"{server.url}/#/library")
                expect(page.locator('[data-test="library-items"]')).to_contain_text("builder")
                expect(page.locator('[data-test="library-items"]')).to_contain_text("v1 ·")
                page.locator('[data-test="library-item"] button').filter(has_text="builder").click()
                expect(page.locator('[data-test="library-detail"]')).to_contain_text("system.md")
                expect(page.locator('[data-test="item-history"]')).to_contain_text("v1 ·")
                page.locator('[data-test="tab-workflow"]').click()
                expect(page.locator('[data-test="library-item"]').first).to_be_visible()
                assert api_get(server.url, "/api/library")["exists"]
                assert api_get(server.url, "/api/repos")["repos"] == []
                assert not marker.exists()
                assert external == [] and dialogs == []
            finally:
                context.close()
                browser.close()
