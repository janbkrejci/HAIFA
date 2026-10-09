"""Exercise real asynchronous API and saving through the built dashboard, with no model."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from test_f3_browser import _launch

from advice_fixture import make_repo
from advice_server import dashboard

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


def test_workflow_advice_browser(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    with dashboard(repo, tmp_path / "home") as (url, identifier), sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page()
        page.set_default_timeout(15000)
        try:
            # Existing task without workflow -> same editor -> agent -> save.
            page.goto(f"{url}/#/r/{identifier}/backlog/P01-S01-T01")
            page.locator('[data-test="edit"]').click()
            page.locator('[data-test="workflow-advice"] button').click()
            expect(page.locator('[data-test="advice-result"]')).to_contain_text("plan")
            expect(page.locator('[data-test="advice-result"]')).to_contain_text(
                "existující workflow"
            )
            page.locator('[data-test="save"]').click()
            expect(page.locator('dd[data-test="workflow"]')).to_contain_text("plan")
            # New unsaved task -> new workflow, persisted only after Save.
            page.goto(f"{url}/#/r/{identifier}/backlog/new")
            page.locator('[data-test="title"]').fill("New research task")
            page.locator('[data-test="body"]').fill(
                "Investigate options; no implementation needed."
            )
            page.locator('[data-test="workflow-advice"] button').click()
            expect(page.locator('[data-test="advice-result"]')).to_contain_text("nové workflow")
            assert not (repo / ".factory/workflows/research.yaml").exists()
            page.locator('[data-test="save"]').click()
            # the uncommitted config banner offers the commit of the new workflow
            expect(page.locator('[data-test="config-banner"]')).to_be_visible()
            expect(page.locator('[data-test="config-commit"]')).to_be_visible()
            assert (repo / ".factory/workflows/research.yaml").is_file()
            page.screenshot(path=str(tmp_path / "workflow-advice.png"), full_page=True)
        finally:
            browser.close()
