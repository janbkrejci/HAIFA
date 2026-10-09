"""Adding a library skill to builder requires a reviewed commit, without live services."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from f3_repo import api_get, git, obs_server
from multi_repo_e2e import diagnostic_tripwire
from playwright.sync_api import Route, expect, sync_playwright
from test_f3_browser import _choose, _launch

from aifactory.library.install import init_repo
from aifactory.library.store import init_library

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


def test_factory_add_skill_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")
    home = tmp_path / "home"
    env = {"HAIFA_HOME": str(home)}
    init_library("test", env)
    lib = home / "library"
    skill = lib / "skills/lint/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: lint\ndescription: Lint code.\n---\nRun lint.\n")
    git(lib, "add", "-A")
    git(lib, "commit", "-qm", "Add lint skill")
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-qb", "main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("Test repo\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "Initial")
    init_repo(repo, agents=["builder"], workflows=["plan-build"], environ=env)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "Install factory")
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
                page.locator('[data-test="item-add"]').click()
                page.locator('[data-test="item-operation"]').scroll_into_view_if_needed()
                page.evaluate(
                    "() => new Promise(resolve => requestAnimationFrame(() => "
                    "requestAnimationFrame(resolve)))"
                )
                _choose(page, '[data-test="item-type"]', "skill")
                _choose(page, '[data-test="item-name"]', "lint")
                _choose(page, '[data-test="item-agent"]', "builder")
                page.locator('[data-test="item-preview"]').click()
                expect(page.locator('[data-test="item-operation"]')).to_contain_text("skill/lint")
                expect(page.locator('[data-test="item-apply"]')).to_be_enabled()
                assert git(repo, "rev-parse", "HEAD") == before
                page.locator('[data-test="item-apply"]').click()
                assert not (repo / ".claude/skills/lint/SKILL.md").exists()
                page.locator('[data-test="confirm-ok"]').click()
                expect(
                    page.locator('[data-test="item-skill-lint"] [data-state]')
                ).to_have_attribute("data-state", "synced")
                expect(page.locator('[data-test="item-agent-builder"]')).to_contain_text("lint")
                assert git(repo, "rev-parse", "HEAD") != before
                assert git(repo, "status", "--porcelain") == ""
                roster = yaml.safe_load((repo / ".factory/agents.yaml").read_text())
                assert "lint" in roster["agents"][0]["skills"]
                item_data = api_get(server.url, f"/api/repos/{server.repo_id}/factory/items")
                assert any(
                    i["name"] == "lint" and i["state"] == "synced" for i in item_data["items"]
                )
                assert not marker.exists() and external == []
            finally:
                context.close()
                browser.close()
