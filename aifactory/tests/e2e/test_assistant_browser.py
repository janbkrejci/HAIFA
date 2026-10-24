"""The AI guide panel in the built dashboard: a conversation with a fake harness, no model."""

from __future__ import annotations

import json
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

from advice_fixture import git, make_repo
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
            with page.expect_response(
                lambda response: (
                    response.request.method == "POST"
                    and response.url.endswith("/api/assistant/threads")
                )
            ) as created:
                panel.locator('[data-test="assistant-send"]').click()
            assert created.value.request.post_data_json == {"screen": {"repo": identifier}}
            binding = created.value.json()["data"]
            expected_binding = " · ".join(
                value
                for value in (binding["harness"], binding["model"], binding.get("thinking"))
                if value
            )
            # the first part streams in while the agent still works
            streaming = panel.locator('[data-test="assistant-streaming"]')
            expect(streaming.locator("strong")).to_have_text("trace DB")
            expect(panel.locator('[data-test="assistant-harness"]')).to_have_text(expected_binding)
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

            # Reload restores the selected thread; reopening from the topbar starts fresh.
            page.reload()
            expect(panel.locator('[data-test="assistant-answer"]')).to_contain_text("selhal")
            panel.locator('[data-test="assistant-close"]').click()
            expect(panel).to_have_count(0)
            page.locator('[data-test="assistant-toggle"]').click()
            expect(panel.locator('[data-test="assistant-user"]')).to_have_count(0)
            expect(panel.locator('[data-test="assistant-answer"]')).to_have_count(0)
            expect(panel.locator('[data-test="assistant-suggestion"]').first).to_have_text(
                "Co má tenhle task udělat?"
            )
            panel.locator('[data-test="assistant-threads"]').click()
            items = panel.locator('[data-test="assistant-thread-item"]')
            expect(items).to_have_count(1)
            items.first.click()
            expect(panel.locator('[data-test="assistant-answer"]')).to_contain_text("selhal")
            panel.locator('[data-test="assistant-new"]').click()
            with page.expect_request(
                lambda request: (
                    request.method == "POST" and request.url.endswith("/api/assistant/threads")
                )
            ) as task_created:
                panel.locator('[data-test="assistant-suggestion"]').first.click()
            assert task_created.value.post_data_json == {
                "screen": {"repo": identifier, "task": "P01-S01-T01"}
            }
            expect(panel.locator('[data-test="assistant-answer"]')).to_contain_text("selhal")
            panel.locator('[data-test="assistant-threads"]').click()
            expect(items).to_have_count(2)
        finally:
            release.set()
            browser.close()


def test_assistant_proposed_action_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A proposal is a card; the task changes only after Provést, and the outcome is shown."""
    repo = make_repo(tmp_path / "repo")
    task_file = repo / "backlog/P01/S01/P01-S01-T01-first.md"
    before = task_file.read_text(encoding="utf-8")
    seen: list[Any] = []
    repo_id: list[str] = []

    def run(request: Any, **kwargs: Any) -> AgentResult:
        seen.append(request)
        proposal = json.dumps(
            {
                "kind": "edit_task",
                "repo": repo_id[0],
                "task": "P01-S01-T01",
                "writes": ["src/", "docs/"],
                "reason": "Task mění i dokumentaci.",
            }
        )
        text = f"Navrhuji rozšířit writes.\n\n```haifa-action\n{proposal}\n```\n"
        return AgentResult(text=text, returncode=0, tokens=10, cost=0.01)

    monkeypatch.setattr(agent_cc, "run", run)
    with dashboard(repo, tmp_path / "home") as (url, identifier), sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page()
        page.set_default_timeout(15000)
        try:
            repo_id.append(identifier)
            page.goto(f"{url}/#/r/{identifier}/backlog/P01-S01-T01")
            page.locator('[data-test="assistant-toggle"]').click()
            panel = page.locator('[data-test="assistant-panel"]')
            panel.locator('[data-test="assistant-input"]').fill("Přidej docs do writes")
            panel.locator('[data-test="assistant-send"]').click()

            card = panel.locator('[data-test="assistant-action"]')
            expect(card.locator('[data-test="assistant-action-title"]')).to_have_text(
                "Upravit task P01-S01-T01"
            )
            preview = card.locator('[data-test="assistant-action-preview"]')
            expect(preview).to_contain_text("src/, docs/")
            # the current value of the task is in the preview
            expect(preview.locator(".before")).to_have_text("src/")
            assert task_file.read_text(encoding="utf-8") == before
            page.screenshot(path=str(tmp_path / "assistant-action.png"))

            card.locator('[data-test="assistant-action-run"]').click()
            expect(card.locator('[data-test="assistant-action-state"]')).to_have_text(
                "Provedeno: Task upraven."
            )
            expect(panel.locator('[data-test="assistant-outcome"]')).to_contain_text("provedeno")
            assert "docs/" in task_file.read_text(encoding="utf-8")
            assert len(seen) == 1
        finally:
            browser.close()


def test_assistant_follow_up_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A follow_up proposal previews what it takes over; the task appears only after Provést."""
    repo = make_repo(tmp_path / "repo")
    task_file = repo / "backlog/P01/S01/P01-S01-T01-first.md"
    task_file.write_text(
        "---\nid: P01-S01-T01\ntitle: First\nstatus: done\nworkflow: plan\n"
        "writes: [src/x/]\n---\nFull task body\n",
        encoding="utf-8",
        newline="\n",
    )
    git(repo, "commit", "-qam", "done")
    step = task_file.parent
    before = sorted(p.name for p in step.glob("*.md"))
    repo_id: list[str] = []

    def run(request: Any, **kwargs: Any) -> AgentResult:
        proposal = json.dumps(
            {
                "kind": "follow_up",
                "repo": repo_id[0],
                "task": "P01-S01-T01",
                "body": "Doplnit dokumentaci.",
                "reason": "Task je hotový, chybí docs.",
            }
        )
        text = f"Navrhuji navázat.\n\n```haifa-action\n{proposal}\n```\n"
        return AgentResult(text=text, returncode=0, tokens=10, cost=0.01)

    monkeypatch.setattr(agent_cc, "run", run)
    with dashboard(repo, tmp_path / "home") as (url, identifier), sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page()
        page.set_default_timeout(15000)
        try:
            repo_id.append(identifier)
            page.goto(f"{url}/#/r/{identifier}/backlog/P01-S01-T01")
            page.locator('[data-test="assistant-toggle"]').click()
            panel = page.locator('[data-test="assistant-panel"]')
            panel.locator('[data-test="assistant-input"]').fill("Naváž dokumentací")
            panel.locator('[data-test="assistant-send"]').click()

            card = panel.locator('[data-test="assistant-action"]')
            expect(card.locator('[data-test="assistant-action-title"]')).to_have_text(
                "Navázat follow-upem na P01-S01-T01"
            )
            preview = card.locator('[data-test="assistant-action-preview"]')
            expect(preview).to_contain_text("Navazuje na P01-S01-T01: First")
            expect(preview).to_contain_text("src/x/")
            expect(preview).to_contain_text("plan")
            assert sorted(p.name for p in step.glob("*.md")) == before

            card.locator('[data-test="assistant-action-run"]').click()
            expect(card.locator('[data-test="assistant-action-state"]')).to_have_text(
                "Provedeno: Task P01-S01-T02 založen."
            )
            [new] = list(step.glob("P01-S01-T02-*.md"))
            text = new.read_text(encoding="utf-8")
            assert "follows: P01-S01-T01\n" in text and "Doplnit dokumentaci." in text
        finally:
            browser.close()
