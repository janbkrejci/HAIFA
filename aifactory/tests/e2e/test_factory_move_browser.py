"""Moving the repo's own workflow to the library is a reviewed plan, without live services."""

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

MINE = "name: mine\ndescription: Our own workflow.\nsteps:\n  - plan\n"

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
    (repo / ".factory/workflows/mine.yaml").write_text(MINE)
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
                page.goto(f"/#/r/{server.repo_id}/factory")
                expect(page.locator('[data-test="item-workflow-simple-sdlc"]')).to_contain_text(
                    "z knihovny"
                )
                expect(page.locator('[data-test="item-workflow-mine"]')).to_contain_text(
                    "vlastní kopie"
                )
                page.locator('[data-test="item-move-workflow-mine"]').click()
                plan = page.locator('[data-test="item-move-plan"]')
                expect(plan).to_contain_text("workflows/mine.yaml")
                expect(page.locator('[data-test="item-move-apply"]')).to_be_enabled()
                assert git(repo, "rev-parse", "HEAD") == before
                assert git(lib, "rev-parse", "HEAD") == library_head
                page.locator('[data-test="item-move-apply"]').click()
                page.locator('[data-test="confirm-ok"]').click()
                expect(page.locator('[data-test="item-workflow-mine"]')).to_contain_text(
                    "z knihovny"
                )
                assert git(lib, "show", "HEAD:workflows/mine.yaml") + "\n" == MINE
                assert git(repo, "rev-parse", "HEAD") != before
                assert not (repo / ".factory/workflows/mine.yaml").exists()
                assert git(repo, "status", "--porcelain") == ""
                items = api_get(server.url, f"/api/repos/{server.repo_id}/factory/items")
                assert {"type": "workflow", "name": "mine", "origin": "library"} in items["items"]
                assert not marker.exists() and external == []
            finally:
                context.close()
                browser.close()
