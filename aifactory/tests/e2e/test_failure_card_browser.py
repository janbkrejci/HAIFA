"""The failure card of a failed run, the failure kind on Přehled and Běhy, and Zrušit task.

A real run through the fake harness: the reviewer never approves, so the run fails
``accept_not_met`` with the reviewer's objection in its ``failure_detail``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from f3_repo import (
    api_get,
    fake_script,
    git,
    make_f3_repo,
    obs_server,
    run_state,
    tripwire,
    wait_for,
)
from playwright.sync_api import Route, expect, sync_playwright
from test_f3_browser import (
    RUN_TIMEOUT_S,
    SERVER_TIMEOUT_MS,
    Server,
    _create_task,
    _launch,
    _no_native_tooltips,
    _start_run,
)

pytestmark = [pytest.mark.browser, pytest.mark.slow, pytest.mark.xdist_group("e2e")]

OBJECTION = "add a test for the empty input"


def test_failure_card_of_a_failed_run(tmp_path: Path) -> None:
    repo = make_f3_repo(tmp_path / "repo")
    agents = repo / ".factory/agents.yaml"
    agents.write_text(agents.read_text(encoding="utf-8") + "  - name: reviewer\n", encoding="utf-8")
    prompts = repo / ".factory/prompts/reviewer"
    prompts.mkdir(parents=True)
    (prompts / "system.md").write_text("Review the implementation.\n", encoding="utf-8")
    (prompts / "user.md").write_text("{{prompt}}\n{{previous_envelope}}\n", encoding="utf-8")
    (repo / ".factory/workflows/plan-commit.yaml").write_text(
        "name: plan-commit\ndescription: Plan and review\nsteps:\n"
        "  - plan\n  - review:\n      when: plan.ran\n      input: [plan]\n  - commit\n"
        "accept: review.approved\n",
        encoding="utf-8",
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "configure review")
    script = fake_script(tmp_path / "script.json")
    data = json.loads(script.read_text(encoding="utf-8"))
    data["agents"]["reviewer"] = [
        {
            "envelope": {
                "status": "success",
                "approved": False,
                "summary": "needs work",
                "findings": [],
                "blocking": [OBJECTION],
            }
        }
    ]
    script.write_text(json.dumps(data), encoding="utf-8")
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
            page.goto(f"/#/r/{obs.repo_id}/backlog")
            task_id = _create_task(page, "Failing task", "Keep the existing implementation.")
            run_id = _start_run(page, server, task_id, commit_first=True)
            wait_for(
                lambda: (run_state(obs.api, run_id)["state"] == "failed") or None,
                RUN_TIMEOUT_S,
                "run failed",
                lambda: server.report(task_id),
            )
            run = run_state(obs.api, run_id)
            assert run["failure_kind"] == "accept_not_met"
            assert run["failure_detail"]["review"]["objections"] == [OBJECTION]

            # Přehled: the kind, not the start of the error
            page.goto("/#/overview")
            row = page.locator(f'[data-test="row-failed"][data-run="{run_id}"]')
            expect(row.locator('[data-test="row-error"]')).to_have_text("Nesplněná podmínka accept")

            # Běhy: the kind under the state of the run
            page.goto(f"/#/r/{obs.repo_id}/runs")
            kind = page.locator(f'tr[data-run="{run_id}"] [data-col="failure-kind"]')
            expect(kind).to_have_text("Nesplněná podmínka accept")

            # the run detail opens with the card: kind, sentence and objection from the run
            page.goto(f"/#/r/{obs.repo_id}/runs/{run_id}")
            card = page.locator('[data-test="failure-card"]')
            expect(card).to_have_attribute("data-kind", "accept_not_met")
            expect(card.locator('[data-test="failure-kind"]')).to_have_text(
                "Nesplněná podmínka accept"
            )
            expect(card.locator('[data-test="failure-sentence"]')).to_contain_text(
                "Review neschválilo"
            )
            expect(card.locator('[data-fact="objections"]')).to_contain_text(OBJECTION)
            expect(card.locator('[data-fact="accept"]')).to_contain_text("review.approved")
            expect(card.locator('[data-test="retry-run"]')).to_have_text("Pokračovat")
            expect(page.locator('[data-test="retry-run"]')).to_have_count(1)
            _no_native_tooltips(page)

            # Zrušit task: confirmed in the dashboard's modal, the task is cancelled
            card.locator('[data-test="cancel-task"]').click()
            dialog = page.locator('[data-test="confirm-dialog"]')
            expect(dialog).to_contain_text(f"Zrušit task {task_id}?")
            dialog.locator('[data-test="confirm-ok"]').click()
            expect(page.locator('[data-test="cancel-done"]')).to_contain_text(task_id)
            task = api_get(obs.api, f"/backlog/tasks/{task_id}")["task"]
            assert task["board_state"] == "cancelled"
            # a cancelled task leaves the Selhalo section of Přehled
            page.goto("/#/overview")
            expect(page.locator(f'[data-test="row-failed"][data-run="{run_id}"]')).to_have_count(0)
            assert not blocked and not marker.exists()
        finally:
            context.close()
            browser.close()
