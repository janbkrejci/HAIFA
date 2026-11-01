"""Lekce on the Factory screen of the built dashboard: Najít lekce (in this repo or in every
repo), then Přijmout; fake harness."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from test_f3_browser import _launch

from advice_fixture import git
from advice_server import dashboard
from aifactory.backlog import Task, load_backlog
from aifactory.home import haifa_home
from aifactory.learn.sources import FACTORY_REPO_ENV
from aifactory.learn.store import ACCEPTED, LessonStore
from learn_fixture import fake_learner, make_learn_repo, register_learn_repos

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
            # Ze všech rep is on by default; this repo alone has the objections here
            switch = section.locator('[data-test="lessons-all"]')
            expect(switch).to_be_checked()
            switch.uncheck()
            section.locator('[data-test="lessons-scan"]').click()

            card = section.locator('[data-test="lesson"][data-state="proposed"]')
            expect(card).to_have_count(1)
            expect(card.locator('[data-test="lesson-rule"]')).to_have_text(RULE)
            expect(card.locator('[data-test="lesson-occurrences"]')).to_have_text("2 běhy")
            expect(card.locator('[data-test="lesson-run"]')).to_have_text(["run-a", "run-b"])
            expect(section.locator('[data-test="lessons-scan-done"]')).to_contain_text("lekcí: 1")
            expect(section.locator('[data-test="lessons-elsewhere"]')).to_have_count(0)

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


def test_learn_browser_all_repos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FACTORY_REPO_ENV, "haifa")
    repos = register_learn_repos(tmp_path, "haifa", "app")
    _, answers = fake_learner(monkeypatch)
    # c1-c3 are the objections of haifa, c4-c6 those of app; the rule belongs to app
    answers.append(
        {
            "status": "success",
            "summary": "one lesson",
            "lessons": [
                {"rule": RULE, "target": "AGENTS.md", "repo": "app", "complaints": ["c1", "c4"]}
            ],
        }
    )
    with dashboard(repos["haifa"], haifa_home()) as (url, identifier), sync_playwright() as p:
        assert identifier == "haifa"
        browser = _launch(p)
        page = browser.new_page()
        page.set_default_timeout(20000)
        try:
            page.goto(f"{url}/#/r/haifa/factory")
            section = page.locator('[data-test="lessons"]')
            expect(section.locator('[data-test="lessons-empty"]')).to_be_visible()
            expect(section.locator('[data-test="lessons-all"]')).to_be_checked()
            section.locator('[data-test="lessons-scan"]').click()

            expect(section.locator('[data-test="lessons-scan-done"]')).to_contain_text(
                "ze všech rep (2)"
            )
            notice = section.locator('[data-test="lessons-elsewhere"]')
            expect(notice).to_contain_text("Do jiných rep se uložilo 1 lekce")
            expect(section.locator('[data-test="lesson"]')).to_have_count(0)
            notice.locator('[data-test="lessons-elsewhere-link"]').click()
            page.wait_for_url("**/#/r/app/factory/lessons")

            card = page.locator('[data-test="lessons"] [data-test="lesson"][data-state="proposed"]')
            expect(card).to_have_count(1)
            expect(card.locator('[data-test="lesson-rule"]')).to_have_text(RULE)
            expect(card.locator('[data-test="lesson-origin"]')).to_have_text(["haifa", "app"])
            expect(card.locator('[data-test="lesson-complaint-repo"]')).to_have_text(
                ["haifa", "app"]
            )
            expect(card.locator('[data-test="lesson-run"]').first).to_have_attribute(
                "href", "#/r/haifa/runs/run-a"
            )
            page.screenshot(path=str(tmp_path / "learn-all.png"), full_page=True)
        finally:
            browser.close()

    store = LessonStore(repos["app"] / ".factory/trace.db")
    try:
        [lesson] = store.all()
        assert lesson.rule == RULE and lesson.origin == ["app", "haifa"]
    finally:
        store.close()
