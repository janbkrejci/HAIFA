"""Nový záměr in the built dashboard: propose without a target (the agent places it, also in a
new project), progress, edit, Upřesni, Použít; fake harness."""

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
from intent_fixture import export_step, install_fake, placed, task

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


def test_intent_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path / "repo")
    # CI has no global git identity; the backlog commit of Použít needs one
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    head = git(repo, "rev-parse", "HEAD").strip()
    release = threading.Event()

    reason = "Export patří k datům projektu P01."

    def first(request: Any) -> dict[str, Any]:
        assert release.wait(20), "the test did not see the progress"
        assert '"kind": "auto"' in request.prompt
        return placed(export_step(), reason, existing_project="P01")

    def revised(request: Any) -> dict[str, Any]:
        assert "## Continuation" in request.prompt
        assert "Přidej dokumentaci." in request.prompt
        extra = task("T03", "Dokumentace exportu", depends_on=["T02"])
        return placed(export_step(extra), reason, existing_project="P01")

    def new_project(request: Any) -> dict[str, Any]:
        answer = export_step()
        answer["step"] = {"code": "S01", "title": "Reporty CSV", "body": "Reporty do CSV."}
        project = {"code": "P02", "title": "Reporty", "body": "Reporty a exporty dat."}
        return placed(answer, "Reporty jsou samostatný projekt.", project=project)

    seen = install_fake(monkeypatch, [first, revised, new_project])
    with dashboard(repo, tmp_path / "home") as (url, identifier), sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page()
        page.set_default_timeout(15000)
        try:
            page.goto(f"{url}/#/r/{identifier}/backlog")
            page.locator('[data-test="new-intent"]').click()
            dialog = page.locator('[data-test="intent-dialog"]')
            expect(dialog.locator('[data-test="intent-target"]')).to_have_count(0)
            dialog.locator('[data-test="intent-text"]').fill("Export dat do CSV")
            dialog.locator('[data-test="intent-propose"]').click()

            progress = dialog.locator('[data-test="intent-progress"]')
            expect(progress).to_contain_text("Agent navrhuje")
            expect(progress).to_contain_text("Agent proposer pracuje")
            release.set()

            tasks = dialog.locator('[data-test="intent-task"]')
            expect(tasks).to_have_count(2)
            project = dialog.locator('[data-test="intent-project"]')
            expect(project).to_contain_text("P01")
            expect(project).to_contain_text("existující")
            expect(dialog.locator('[data-test="intent-step"]')).to_contain_text("P01-S02")
            expect(dialog.locator('[data-test="intent-reason"]')).to_contain_text(reason)
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

            # a second intent the agent places in a new project
            page.locator('[data-test="new-intent"]').click()
            dialog = page.locator('[data-test="intent-dialog"]')
            dialog.locator('[data-test="intent-text"]').fill("Reporty do CSV")
            dialog.locator('[data-test="intent-propose"]').click()
            project = dialog.locator('[data-test="intent-project"]')
            expect(project).to_contain_text("P02")
            expect(project).to_contain_text("nový")
            expect(dialog.locator('[data-test="intent-result"]')).to_contain_text(
                "Reporty a exporty dat."
            )
            expect(dialog.locator('[data-test="intent-step"]')).to_contain_text("P02-S01")
            expect(dialog.locator('[data-test="intent-reason"]')).to_contain_text(
                "Reporty jsou samostatný projekt."
            )
            dialog.locator('[data-test="intent-apply"]').click()
            page.wait_for_url("**/backlog/graph/P02-S01")
            expect(page.locator('[data-test="graph-title"]')).to_contain_text("Reporty CSV")
        finally:
            browser.close()

    assert git(repo, "rev-parse", "HEAD").strip() != head
    assert git(repo, "status", "--porcelain", "--untracked-files=all") == ""
    backlog = load_backlog(repo)
    assert check_backlog(backlog) == []
    assert backlog.by_id["P01-S02-T02"].title == "CLI pro export"
    assert "P01-S02-T03" not in backlog.by_id
    assert backlog.by_id["P02"].title == "Reporty"
    assert backlog.by_id["P02-S01-T02"].parent.id == "P02-S01"  # type: ignore[union-attr]
    assert len(seen) == 3
