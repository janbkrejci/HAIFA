"""Moving a repo's own copy of a library workflow to the library from the Library page.

The move is a reviewed plan, without live services.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from f3_repo import api_get, git, obs_server
from multi_repo_e2e import diagnostic_tripwire
from playwright.sync_api import Route, expect, sync_playwright
from test_f3_browser import _launch

from aifactory.library.install import init_repo
from aifactory.library.store import init_library

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


def test_factory_move_to_library_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")
    home = tmp_path / "home"
    init_library("test", {"HAIFA_HOME": str(home)})
    lib = home / "library"
    library_head = git(lib, "rev-parse", "HEAD")
    # The repo's own copy of a library workflow, so the Library page lists it as an override.
    mine = "# Our own copy.\n" + git(lib, "show", "HEAD:workflows/simple-sdlc.yaml") + "\n"
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-qb", "main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("Test repo\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "Initial")
    init_repo(repo)
    (repo / ".factory/workflows").mkdir(parents=True)
    (repo / ".factory/workflows/simple-sdlc.yaml").write_text(mine)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "Install factory with an own workflow")
    before = git(repo, "rev-parse", "HEAD")
    script = tmp_path / "fake.json"
    script.write_text(json.dumps({"agents": {}}))
    wire, marker = diagnostic_tripwire(tmp_path)
    external: list[str] = []
    with obs_server(repo, script, wire, tmp_path / "obs.log", home) as server:
        with sync_playwright() as playwright:
            browser = _launch(playwright)
            context = browser.new_context(base_url=server.url, service_workers="block")
            context.set_default_timeout(30_000)
            expect.set_options(timeout=30_000)

            def local_only(route: Route) -> None:
                if not route.request.url.startswith(server.url + "/"):
                    external.append(route.request.url)
                    route.abort()
                elif "/factory/check" in route.request.url or "/machine/check" in route.request.url:
                    query = "&" if "?" in route.request.url else "?"
                    route.continue_(url=route.request.url + query + "offline=1")
                else:
                    route.continue_()

            context.route("**/*", local_only)
            page = context.new_page()
            try:
                page.goto("/#/setup/library")
                page.locator('[data-test="tab-workflow"]').click()
                expect(page.locator('[data-test="override-count-simple-sdlc"]')).to_have_text("1")
                page.locator(
                    '[data-test="library-item"] button:has(.item-name:text-is("simple-sdlc"))'
                ).click()
                row = page.locator(f'[data-test="override-{server.repo_id}"]')
                expect(row).to_contain_text("liší se")
                row.locator('[data-test="override-move"]').click()
                modal = page.locator('[data-test="confirm-dialog"]')
                expect(modal).to_contain_text("workflow/simple-sdlc")
                modal.locator('[data-test="confirm-cancel"]').click()
                plan = page.locator('[data-test="override-plan"]')
                expect(plan).to_contain_text("workflows/simple-sdlc.yaml")
                apply = page.locator('[data-test="override-move-apply"]')
                expect(apply).to_be_enabled()
                assert git(repo, "rev-parse", "HEAD") == before
                assert git(lib, "rev-parse", "HEAD") == library_head
                apply.click()
                modal.locator('[data-test="confirm-ok"]').click()
                expect(page.locator('[data-test="item-no-overrides"]')).to_be_visible()
                expect(page.locator('[data-test="override-count-simple-sdlc"]')).to_have_text("—")
                assert git(lib, "show", "HEAD:workflows/simple-sdlc.yaml") + "\n" == mine
                assert git(lib, "rev-parse", "HEAD") != library_head
                assert git(repo, "rev-parse", "HEAD") != before
                assert not (repo / ".factory/workflows/simple-sdlc.yaml").exists()
                assert git(repo, "status", "--porcelain") == ""
                items = api_get(server.url, f"/api/repos/{server.repo_id}/factory/items")
                assert {
                    "type": "workflow",
                    "name": "simple-sdlc",
                    "origin": "library",
                } in items["items"]
                assert not marker.exists() and external == []
            finally:
                context.close()
                browser.close()
