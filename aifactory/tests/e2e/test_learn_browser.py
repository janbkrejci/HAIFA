"""Lekce on the Factory screen of the built dashboard: Najít lekce, then Přijmout; fake harness."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from test_f3_browser import _launch

from advice_fixture import git
from advice_server import dashboard
from aifactory.backlog import Task, load_backlog
from aifactory.learn.store import ACCEPTED, LessonStore
from learn_fixture import fake_learner, make_learn_repo

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]

RULE = "Add a test for every new CLI command."


def test_learn_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_learn_repo(tmp_path)
    head = git(repo, "rev-parse", "HEAD").strip()
    _, answers = fake_learner(monkeypatch)
    answers.append(
        {
            "status": "success",
            "summary": "one lesson",
            "lessons": [{"rule": RULE, "target": "AGENTS.md", "complaints": ["c1", "c2"]}],
        }
    )
    with dashboard(repo, tmp_path / "home") as (url, identifier), sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page()
        page.set_default_timeout(20000)
        try:
            page.goto(f"{url}/#/r/{identifier}/factory")
            section = page.locator('[data-test="lessons"]')
            expect(section.locator('[data-test="lessons-empty"]')).to_be_visible()
            section.locator('[data-test="lessons-scan"]').click()

            card = section.locator('[data-test="lesson"][data-state="proposed"]')
            expect(card).to_have_count(1)
            expect(card.locator('[data-test="lesson-rule"]')).to_have_text(RULE)
            expect(card.locator('[data-test="lesson-occurrences"]')).to_have_text("2 běhy")
            expect(card.locator('[data-test="lesson-run"]')).to_have_text(["run-a", "run-b"])
            expect(section.locator('[data-test="lessons-scan-done"]')).to_contain_text("lekcí: 1")

            card.locator('[data-test="lesson-accept"]').click()
            expect(section.locator('[data-test="lessons-notice"]')).to_contain_text("P01-LEARN-T01")
            accepted = section.locator('[data-test="lesson"][data-state="accepted"]')
            expect(accepted.locator('[data-test="lesson-task"]')).to_have_text("P01-LEARN-T01")
            expect(accepted.locator('[data-test="lesson-waiting"]')).to_be_visible()
            expect(card).to_have_count(0)
            page.screenshot(path=str(tmp_path / "learn.png"), full_page=True)

            accepted.locator('[data-test="lesson-task"]').click()
            page.wait_for_url("**/backlog/P01-LEARN-T01")
        finally:
            browser.close()

    assert git(repo, "rev-parse", "HEAD").strip() != head
    task = load_backlog(repo).by_id["P01-LEARN-T01"]
    assert isinstance(task, Task) and RULE in task.body
    store = LessonStore(repo / ".factory/trace.db")
    try:
        [lesson] = store.all()
        assert lesson.state == ACCEPTED and lesson.task_id == "P01-LEARN-T01"
    finally:
        store.close()
