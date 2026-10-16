"""The AI guide panel in the built dashboard: a conversation with a fake harness, no model."""

from __future__ import annotations

import re
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright
from test_f3_browser import _launch

from advice_fixture import make_repo
from aifactory.codeprint import CodeWatch
from aifactory.engine import agent_cc
from aifactory.engine.data_types import AgentResult
from aifactory.web.app import create_multi_app
from aifactory.web.registry import Registry

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


@contextmanager
def dashboard(repo: Path, home: Path) -> Iterator[tuple[str, str]]:
    entry, _ = Registry(home).add(repo)
    app = create_multi_app(home=home, code_watch=CodeWatch(home / "test-code"))
    app.state.limits = type("NoLimits", (), {"get": lambda self, root: {"providers": []}})()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise AssertionError("dashboard did not start")
            time.sleep(0.01)
        yield f"http://127.0.0.1:{port}", entry.id
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


def fake_harness(monkeypatch: pytest.MonkeyPatch, release: threading.Event) -> list[Any]:
    """claude's adapter: streams a first part, waits for ``release``, then answers."""
    seen: list[Any] = []

    def run(request: Any, **kwargs: Any) -> AgentResult:
        seen.append(request)
        on_event = kwargs["on_event"]
        first = "Hledám v **trace DB**…"
        on_event({"type": "assistant", "message": {"content": [{"type": "text", "text": first}]}})
        release.wait(30)
        text = "Task `P01-S01-T01` selhal v testech, běh `abcd1234`."
        on_event({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
        return AgentResult(text=text, returncode=0, tokens=10, cost=0.01)

    monkeypatch.setattr(agent_cc, "run", run)
    return seen


def test_assistant_conversation_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path / "repo")
    release = threading.Event()
    seen = fake_harness(monkeypatch, release)
    with dashboard(repo, tmp_path / "home") as (url, identifier), sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page()
        page.set_default_timeout(15000)
        try:
            page.goto(f"{url}/#/r/{identifier}/runs")
            page.locator('[data-test="assistant-toggle"]').click()
            panel = page.locator('[data-test="assistant-panel"]')
            expect(panel.locator('[data-test="assistant-context"]')).to_have_text(
                f"repo {identifier}"
            )
            expect(panel.locator('[data-test="assistant-suggestion"]')).to_have_count(3)

            panel.locator('[data-test="assistant-input"]').fill("Proč selhal první task?")
            panel.locator('[data-test="assistant-send"]').click()
            # the first part streams in while the agent still works
            streaming = panel.locator('[data-test="assistant-streaming"]')
            expect(streaming.locator("strong")).to_have_text("trace DB")
            expect(panel.locator('[data-test="assistant-harness"]')).to_have_text(
                "claude · claude-opus-5-5"
            )
            release.set()
            answer = panel.locator('[data-test="assistant-answer"]')
            expect(answer).to_contain_text("selhal v testech")
            expect(streaming).to_have_count(0)
            assert seen[0].prompt.count(f"`{identifier}`") >= 1
            assert "Screen the user is looking at" in seen[0].prompt
            page.screenshot(path=str(tmp_path / "assistant.png"))

            # a task mention is a dashboard link; the panel keeps the thread on the new screen
            answer.get_by_role("link", name="P01-S01-T01").click()
            page.wait_for_url(re.compile(r".*/backlog/P01-S01-T01$"))
            expect(panel.locator('[data-test="assistant-user"]')).to_have_count(1)
            expect(panel.locator('[data-test="assistant-context"]')).to_contain_text(
                "task P01-S01-T01"
            )
            run_link = answer.get_by_role("link", name="abcd1234")
            expect(run_link).to_have_attribute("href", f"#/r/{identifier}/runs/abcd1234")

            # a new thread offers the questions of the screen, the old one is in the list
            panel.locator('[data-test="assistant-new"]').click()
            expect(panel.locator('[data-test="assistant-suggestion"]').first).to_have_text(
                "Co má tenhle task udělat?"
            )
            panel.locator('[data-test="assistant-threads"]').click()
            items = panel.locator('[data-test="assistant-thread-item"]')
            expect(items).to_have_count(1)
            items.first.click()
            expect(panel.locator('[data-test="assistant-answer"]')).to_contain_text("selhal")
        finally:
            release.set()
            browser.close()
