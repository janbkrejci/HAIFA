"""Onboard sssf with local remotes, then adopt on another machine without a model."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from f3_repo import obs_server, registered_id
from multi_repo_e2e import diagnostic_tripwire
from playwright.sync_api import Route, expect, sync_playwright
from test_f3_browser import _launch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "onboard"))
from onboard_repo import (  # noqa: E402
    commit_all,
    git,
    patch_omnibus,
    sssf_repo,
    worktree_snapshot,
)

from aifactory.library import store

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


def test_onboarding_and_adoption_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")
    home = tmp_path / "machine1"
    monkeypatch.setenv("HAIFA_HOME", str(home))
    library_remote = tmp_path / "library.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(library_remote))
    store.init_library("team", remote=str(library_remote))
    repo = sssf_repo(tmp_path, "legacy", origin=True)
    patch_omnibus(repo)
    commit_all(repo, "custom sssf")
    git(repo, "push", "origin", "main")
    adws_before = worktree_snapshot(repo / "adws")
    script = tmp_path / "fake.json"
    script.write_text(json.dumps({"agents": {}}), encoding="utf-8")
    wire, marker = diagnostic_tripwire(tmp_path)
    external: list[str] = []
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        try:
            for machine in (home, tmp_path / "machine2"):
                with obs_server(
                    None, script, wire, tmp_path / f"{machine.name}.log", machine
                ) as server:
                    context = browser.new_context(base_url=server.url, service_workers="block")
                    context.set_default_timeout(60_000)
                    expect.set_options(timeout=60_000)

                    def local_only(route: Route) -> None:
                        if route.request.url.startswith(server.url + "/"):
                            route.continue_()
                        else:
                            external.append(route.request.url)
                            route.abort()

                    context.route("**/*", local_only)
                    page = context.new_page()
                    try:
                        if machine == home:
                            # Existing registered repositories may still use the Factory-tab
                            # migration; adding a new repository instead removes legacy sssf.
                            response = context.request.post("/api/repos", data={"path": str(repo)})
                            assert response.ok
                            repo_id = registered_id(machine, repo)
                            page.goto(f"/#/r/{repo_id}/factory")
                            expect(page.locator('[data-test="onboarding-perform"]')).to_be_enabled()
                            page.locator('[data-test="onboarding-perform"]').click()
                            expect(page.locator('[data-test="confirm-dialog"]')).to_contain_text(
                                "adws/ zůstane beze změny"
                            )
                            page.locator('[data-test="confirm-ok"]').click()
                            expect(page.locator('[data-test="factory-verdict"]')).to_be_visible()
                            assert git(repo, "rev-parse", "main") == git(
                                tmp_path / "legacy.git", "rev-parse", "main"
                            )
                            assert git(home / "library", "rev-parse", "HEAD") == git(
                                library_remote, "rev-parse", "main"
                            )
                        else:
                            page.goto("/#/repos/add")
                            page.locator('[data-test="add-path"]').fill(str(repo))
                            page.locator('[data-test="add-inspect"]').click()
                            expect(page.locator('[data-test="inspect-onboard"]')).to_have_count(0)
                            page.locator('[data-test="inspect-add"]').click()
                            expect(page.locator('[data-test="repo-added"]')).to_be_visible()
                            repo_id = registered_id(machine, repo)
                            page.goto(f"/#/r/{repo_id}/factory")
                            expect(page.locator('[data-test="adopt-clone"]')).to_contain_text(
                                str(library_remote)
                            )
                            page.locator('[data-test="adopt-clone"]').click()
                            page.locator('[data-test="confirm-ok"]').click()
                            expect(page.locator('[data-test="onboarding-plan"]')).to_be_visible()
                            expect(page.locator('[data-test="onboarding-panel"]')).to_contain_text(
                                "Knihovna nevyžaduje doplnění"
                            )
                            expect(
                                page.locator('[data-test="onboarding-panel"]')
                            ).not_to_contain_text("Onboarding — jednou")
                        if machine == home:
                            assert worktree_snapshot(repo / "adws") == adws_before
                        else:
                            assert not (repo / "adws").exists()
                        expect(page.locator('[data-test="factory-recheck"]')).to_be_enabled()
                        page.screenshot(path=str(tmp_path / f"{machine.name}.png"))
                    finally:
                        context.close()
        finally:
            browser.close()
    assert external == []
    assert not marker.exists()
