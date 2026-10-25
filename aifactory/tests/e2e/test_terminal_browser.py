"""Secret terminal in the shipped dashboard, with real loopback shell execution."""

from __future__ import annotations

import shlex
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright
from test_f3_browser import _launch

from advice_fixture import make_repo
from advice_server import dashboard

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


@pytest.fixture
def terminal_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Page]:
    if sys.platform != "win32":
        # Avoid user shell plugins and startup services in this isolated browser test.
        monkeypatch.setenv("SHELL", "/bin/sh")
    repo = make_repo(tmp_path / "repo")
    with dashboard(repo, tmp_path / "home") as (url, identifier), sync_playwright() as p:
        browser = _launch(p)
        try:
            page = browser.new_page()
            page.set_default_timeout(15000)
            info = page.request.get(f"{url}/api/terminal")
            assert info.ok, info.text()
            capabilities = info.json()
            assert capabilities["ok"], capabilities
            if sys.platform == "win32" and not capabilities["data"]["pty"]:
                pytest.skip("GET /api/terminal reports pty: false on Windows")
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
    expect(overlay.locator(".xterm")).to_be_visible()
    terminal = overlay.locator(".xterm-helper-textarea")
    expect(terminal).to_be_focused()
    screen = overlay.locator(".xterm-rows")

    # The marker is absent from the command's echo, so only shell output satisfies this.
    page.keyboard.insert_text(
        "echo haifa-^terminal" if sys.platform == "win32" else 'echo haifa-"terminal"'
    )
    page.keyboard.press("Enter")
    expect(screen).to_contain_text("haifa-terminal")

    target = (tmp_path / "terminal cwd").resolve()
    target.mkdir()
    page.keyboard.insert_text(f'cd "{target}"')
    page.keyboard.press("Enter")
    page.keyboard.insert_text(
        "echo haifa-cwd-%CD%" if sys.platform == "win32" else 'echo haifa-cwd-"$PWD"'
    )
    page.keyboard.press("Enter")
    expect(screen).to_contain_text(f"haifa-cwd-{target}")

    python = f'"{sys.executable}"' if sys.platform == "win32" else shlex.quote(sys.executable)
    page.keyboard.insert_text(f"{python} -c \"import sys;print('tty', sys.stdin.isatty())\"")
    page.keyboard.press("Enter")
    expect(screen).to_contain_text("tty True")

    # Keep output markers out of command echo, and wait until each input() is ready.
    script = target / "interactive.py"
    script.write_text(
        'value = input("haifa-" + "input-ready:")\n'
        'print("haifa-" + "input-result", value, flush=True)\n'
        'value = input("haifa-" + "escape-ready:")\n'
        'print("haifa-" + "escape-result", ord(value), flush=True)\n',
        encoding="utf-8",
    )
    page.keyboard.insert_text(f'{python} "{script}"')
    page.keyboard.press("Enter")
    expect(screen).to_contain_text("haifa-input-ready:")
    page.keyboard.press("q")
    page.keyboard.press("Enter")
    expect(screen).to_contain_text("haifa-input-result q")
    expect(screen).to_contain_text("haifa-escape-ready:")
    page.keyboard.press("Escape")
    expect(overlay).to_be_visible()
    page.keyboard.press("Enter")
    expect(screen).to_contain_text("haifa-escape-result 27")

    # Windows has no standard sleep command; use the same interpreter there.
    sleep = (
        f"{python} -c \"import time;print('haifa-' + 'sleep-ready', flush=True);time.sleep(100)\""
        if sys.platform == "win32"
        else 'echo haifa-"sleep-ready"; sleep 100'
    )
    page.keyboard.insert_text(sleep)
    page.keyboard.press("Enter")
    expect(screen).to_contain_text("haifa-sleep-ready")
    page.keyboard.press("Control+c")
    page.keyboard.insert_text(
        "echo haifa-^after-interrupt" if sys.platform == "win32" else 'echo haifa-"after-interrupt"'
    )
    page.keyboard.press("Enter")
    expect(screen).to_contain_text("haifa-after-interrupt")

    for key in ("Control", "Shift", "Control", "Shift"):
        page.keyboard.press(key)
    expect(overlay).to_have_count(0)


def test_terminal_vim_browser(terminal_page: Page, tmp_path: Path) -> None:
    if not shutil.which("vim"):
        pytest.skip("vim is not installed on this machine")
    page = terminal_page
    for key in ("Control", "Shift", "Control", "Shift"):
        page.keyboard.press(key)
    overlay = page.get_by_role("dialog", name="Terminál", exact=True)
    expect(overlay.locator(".xterm-helper-textarea")).to_be_focused()
    target = tmp_path / "vim-screen.txt"
    target.write_text("haifa-vim-screen\n", encoding="utf-8")
    separator = "&" if sys.platform == "win32" else ";"
    after_vim = "echo haifa-^after-vim" if sys.platform == "win32" else 'echo haifa-"after-vim"'
    # Let the shell emit the marker after vim exits. Typing a new command immediately
    # after :q can race with vim restoring terminal modes and flushing pending input.
    page.keyboard.insert_text(f'vim -Nu NONE -n "{target}" {separator} {after_vim}')
    page.keyboard.press("Enter")
    screen = overlay.locator(".xterm-rows")
    expect(screen).to_contain_text("haifa-vim-screen")
    viewport = overlay.locator(".terminal-viewport").bounding_box()
    assert viewport is not None
    page_size = page.viewport_size
    assert page_size is not None
    assert viewport["height"] > page_size["height"] * 0.7
    page.keyboard.press("i")
    expect(screen).to_contain_text("INSERT")
    page.keyboard.press("Escape")
    expect(overlay).to_be_visible()
    page.keyboard.insert_text(":q")
    page.keyboard.press("Enter")
    # The marker is not present literally in the command echo; the shell must run it.
    expect(screen).to_contain_text("haifa-after-vim")
    for key in ("Control", "Shift", "Control", "Shift"):
        page.keyboard.press(key)
    expect(overlay).to_have_count(0)


def test_terminal_interrupted_sequence_browser(terminal_page: Page) -> None:
    for key in ("Control", "Shift", "A", "Control", "Shift"):
        terminal_page.keyboard.press(key)
    # Let Vue paint any overlay triggered by the last key before checking absence.
    terminal_page.evaluate("() => new Promise(resolve => requestAnimationFrame(resolve))")
    expect(terminal_page.locator('[data-test="terminal-overlay"]')).to_have_count(0)
