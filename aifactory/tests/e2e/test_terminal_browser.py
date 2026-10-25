"""Secret terminal in the shipped dashboard, with real loopback shell execution."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright
from test_f3_browser import _launch

from advice_fixture import make_repo
from advice_server import dashboard

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


@pytest.fixture
def terminal_page(tmp_path: Path) -> Iterator[Page]:
    repo = make_repo(tmp_path / "repo")
    with dashboard(repo, tmp_path / "home") as (url, identifier), sync_playwright() as p:
        browser = _launch(p)
        try:
            page = browser.new_page()
            page.set_default_timeout(15000)
            page.goto(f"{url}/#/r/{identifier}/runs")
            expect(page.locator('[data-test="assistant-toggle"]')).to_be_visible()
            expect(page.locator('[data-test="terminal-overlay"]')).to_have_count(0)
            yield page
        finally:
            browser.close()


def test_terminal_commands_browser(terminal_page: Page, tmp_path: Path) -> None:
    page = terminal_page
    for key in ("Control", "Shift", "Control", "Shift"):
        page.keyboard.press(key)
    overlay = page.get_by_role("dialog", name="Terminál", exact=True)
    expect(overlay).to_be_visible()
    command = overlay.get_by_role("textbox", name="Příkaz", exact=True)
    expect(command).to_be_focused()

    command.fill("echo haifa-terminal")
    command.press("Enter")
    # Check stdout alone: the command transcript also contains the sentinel.
    expect(overlay.get_by_role("log").locator(".stdout")).to_have_text("haifa-terminal")
    expect(command).not_to_have_attribute("readonly", "")

    target = (tmp_path / "terminal cwd").resolve()
    target.mkdir()
    command.fill(f'cd "{target}"')
    command.press("Enter")
    expect(overlay.locator('label[for="terminal-command"]')).to_have_text(f"{target} $")

    page.keyboard.press("Escape")
    expect(overlay).to_have_count(0)


def test_terminal_interrupted_sequence_browser(terminal_page: Page) -> None:
    for key in ("Control", "Shift", "A", "Control", "Shift"):
        terminal_page.keyboard.press(key)
    # Let Vue paint any overlay triggered by the last key before checking absence.
    terminal_page.evaluate("() => new Promise(resolve => requestAnimationFrame(resolve))")
    expect(terminal_page.locator('[data-test="terminal-overlay"]')).to_have_count(0)
