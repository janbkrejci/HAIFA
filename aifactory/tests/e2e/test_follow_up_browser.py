"""Otevřít navazující task from the detail of a done task, run at once on a fake harness."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from f3_repo import (
    T01,
    fake_script,
    git,
    make_f3_repo,
    obs_server,
    run_state,
    task_runs,
    tripwire,
    wait_for,
)
from playwright.sync_api import Route, expect, sync_playwright
from test_f3_browser import (
    RUN_START_TIMEOUT_S,
    RUN_TIMEOUT_S,
    SERVER_TIMEOUT_MS,
    Server,
    _calls,
    _launch,
)

from aifactory.backlog import load_backlog

pytestmark = [pytest.mark.browser, pytest.mark.slow, pytest.mark.xdist_group("e2e")]

DONE_TASK = f"---\nid: {T01}\ntitle: Schema\nstatus: done\n---\n\n## Zadání\nNavrhnout schéma.\n"


def test_follow_up_from_done_task(tmp_path: Path) -> None:
    repo = make_f3_repo(tmp_path / "repo")
    path = repo / "backlog/M01-core/S01-model/M01-S01-T01-schema.md"
    path.write_text(DONE_TASK, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "done task")
    script = fake_script(tmp_path / "script.json")
    wire, marker = tripwire(tmp_path / "wire")
    log, home = tmp_path / "obs.log", tmp_path / "haifa-home"
    with obs_server(repo, script, wire, log, home) as obs, sync_playwright() as p:
        server = Server(
            repo, obs.url, log, script, marker, git(repo, "rev-parse", "HEAD"), home, obs.repo_id
        )
        browser = _launch(p)
        context = browser.new_context(base_url=obs.url)
        context.set_default_timeout(SERVER_TIMEOUT_MS)
        blocked: list[str] = []

        def only_local(route: Route) -> None:
            if route.request.url.startswith(obs.url + "/"):
                route.continue_()
            else:
                blocked.append(route.request.url)
                route.abort()

        context.route("**/*", only_local)
        page = context.new_page()
        try:
            page.goto(f"/#/r/{obs.repo_id}/backlog/{T01}")
            expect(page.locator('[data-test="task-id"]')).to_have_text(T01)
            # a done task is not run, edited or improved again
            for test_id in ("run", "edit", "improve"):
                expect(page.locator(f'[data-test="{test_id}"]')).to_have_count(0)
            page.locator('[data-test="follow-up"]').click()
            dialog = page.locator('[data-test="follow-up-dialog"]')
            expect(dialog).to_contain_text("Co změnit, předělat nebo dodělat")
            expect(dialog.locator('[data-test="follow-up-run"]')).to_be_checked()
            dialog.locator('[data-test="follow-up-body"]').fill("Doplnit schéma o verzi.")
            with page.expect_response(lambda r: r.url.endswith(f"/{T01}/follow-up")) as response:
                dialog.locator('[data-test="follow-up-submit"]').click()
            assert response.value.status == 202
            new_id = response.value.json()["data"]["task"]["id"]
            assert new_id != T01

            # the detail of the new task opens and links the original one
            page.wait_for_url(re.compile(rf"#/r/[^/]+/backlog/{new_id}$"))
            expect(page.locator('[data-test="task-id"]')).to_have_text(new_id)
            follows = page.locator('[data-test="follows"]')
            expect(follows).to_contain_text(f"Navazuje na {T01}")

            run_id = wait_for(
                lambda: next((r["run_id"] for r in task_runs(obs.api, new_id)), None),
                RUN_START_TIMEOUT_S,
                f"run of {new_id} claimed",
                lambda: server.report(new_id),
            )
            wait_for(
                lambda: (run_state(obs.api, run_id)["state"] == "succeeded") or None,
                RUN_TIMEOUT_S,
                "follow-up run succeeded",
                lambda: server.report(new_id),
            )

            # the original task lists the task that follows it
            follows.locator("a").click()
            expect(page.locator('[data-test="task-id"]')).to_have_text(T01)
            expect(
                page.locator(f'[data-test="followed-by"] [data-follower="{new_id}"]')
            ).to_be_visible()
            assert not blocked and not marker.exists()
        finally:
            context.close()
            browser.close()

    # the backlog was committed to base before the run
    assert f"follows {T01}" in git(repo, "log", "--format=%s", "main")
    assert load_backlog(repo).by_id[new_id].follows == T01  # type: ignore[union-attr]
    assert [c.get("agent") for c in _calls(script)] == ["planner"]
