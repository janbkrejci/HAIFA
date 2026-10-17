"""Nový záměr in the built dashboard: propose, progress, edit, Upřesni, Použít; fake harness."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import expect, sync_playwright
from test_f3_browser import _launch

from advice_fixture import git, make_repo
from advice_server import dashboard
from aifactory.backlog import check_backlog, load_backlog
from intent_fixture import export_step, install_fake, task

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


def test_intent_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path / "repo")
    head = git(repo, "rev-parse", "HEAD").strip()
    release = threading.Event()

    def first(request: Any) -> dict[str, Any]:
        assert release.wait(20), "the test did not see the progress"
        return export_step()

    def revised(request: Any) -> dict[str, Any]:
        assert "## Continuation" in request.prompt
        assert "Přidej dokumentaci." in request.prompt
        return export_step(task("T03", "Dokumentace exportu", depends_on=["T02"]))

    seen = install_fake(monkeypatch, [first, revised])
    with dashboard(repo, tmp_path / "home") as (url, identifier), sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page()
        page.set_default_timeout(15000)
        try:
            page.goto(f"{url}/#/r/{identifier}/backlog")
            page.locator('[data-test="new-intent"]').click()
            dialog = page.locator('[data-test="intent-dialog"]')
            dialog.locator('[data-test="intent-text"]').fill("Export dat do CSV")
            dialog.locator('[data-test="intent-target"]').click()
            page.locator('[data-test="select-list"] [role="option"]', has_text="P01").filter(
                has_text="nový"
            ).click()
            dialog.locator('[data-test="intent-propose"]').click()

            progress = dialog.locator('[data-test="intent-progress"]')
            expect(progress).to_contain_text("Agent navrhuje")
            expect(progress).to_contain_text("Agent proposer pracuje")
            release.set()

            tasks = dialog.locator('[data-test="intent-task"]')
            expect(tasks).to_have_count(2)
            expect(dialog.locator('[data-test="intent-step"]')).to_contain_text("P01-S02")
            first_task = dialog.locator('[data-task="P01-S02-T01"]')
            first_task.locator("summary").click()
            expect(first_task).to_contain_text("Hotovo znamená")

            # Upřesni: the same agent session revises the proposal
            dialog.locator('[data-test="intent-note"]').fill("Přidej dokumentaci.")
            dialog.locator('[data-test="intent-refine"]').click()
            expect(tasks).to_have_count(3)
            assert len(seen) == 2 and seen[1].session_id == seen[0].session_id
            expect(dialog.locator('[data-test="intent-notes"]')).to_contain_text(
                "Přidej dokumentaci."
            )

            # edit T02, remove T03, Použít
            second = dialog.locator('[data-task="P01-S02-T02"]')
            second.locator('[data-test="intent-task-edit"]').click()
            second.locator('[data-test="intent-task-title"]').fill("CLI pro export")
            dialog.locator('[data-task="P01-S02-T03"] [data-test="intent-task-remove"]').click()
            apply = dialog.locator('[data-test="intent-apply"]')
            expect(apply).to_contain_text("Použít (2)")
            page.screenshot(path=str(tmp_path / "intent.png"), full_page=True)
            apply.click()
            page.wait_for_url("**/backlog/graph/P01-S02")
            expect(page.locator('[data-test="graph-title"]')).to_contain_text("Export")
        finally:
            browser.close()

    assert git(repo, "rev-parse", "HEAD").strip() != head
    assert git(repo, "status", "--porcelain", "--untracked-files=all") == ""
    backlog = load_backlog(repo)
    assert check_backlog(backlog) == []
    assert backlog.by_id["P01-S02-T02"].title == "CLI pro export"
    assert "P01-S02-T03" not in backlog.by_id
