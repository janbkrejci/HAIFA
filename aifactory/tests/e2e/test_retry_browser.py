"""Retry from both dashboard screens, through real processes and a fake harness."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from f3_repo import (
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
    RUN_TIMEOUT_S,
    SERVER_TIMEOUT_MS,
    Server,
    _calls,
    _create_task,
    _launch,
    _open_task,
    _start_run,
)

pytestmark = [pytest.mark.browser, pytest.mark.slow, pytest.mark.xdist_group("e2e")]


@pytest.mark.parametrize("screen", ["runs", "backlog"])
def test_retry_from_run_and_task_detail(tmp_path: Path, screen: str) -> None:
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
                "summary": "needs retry",
                "findings": [],
                "blocking": ["confirm the implementation"],
            }
        },
        {
            "envelope": {
                "status": "success",
                "approved": True,
                "summary": "approved",
                "findings": [],
                "blocking": [],
            }
        },
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
            task_id = _create_task(page, "Retry task", "Keep the existing implementation.")
            run_id = _start_run(page, server, task_id, commit_first=True)
            wait_for(
                lambda: (run_state(obs.api, run_id)["state"] == "failed") or None,
                RUN_TIMEOUT_S,
                "first attempt failed",
                lambda: server.report(task_id),
            )
            before = run_state(obs.api, run_id)
            if screen == "backlog":
                _open_task(page, task_id)
            else:
                page.reload()
            page.locator('[data-test="retry-run"]').click()
            note = f"Potvrzuji implementaci z obrazovky {screen}."
            page.locator('[data-test="retry-note"]').fill(note)
            with page.expect_response(
                lambda r: r.url.endswith(f"/runs/{run_id}/retry")
            ) as response:
                page.locator('[data-test="retry-submit"]').click()
            assert response.value.status == 202
            payload = response.value.json()["data"]
            assert payload["action"] == "retry"
            if payload["run"] is not None:
                assert payload["run"]["run_id"] == run_id
                assert payload["run"]["attempt"] == 2
            wait_for(
                lambda: (run_state(obs.api, run_id)["state"] == "succeeded") or None,
                RUN_TIMEOUT_S,
                "retry completed",
                lambda: server.report(task_id),
            )
            [after] = task_runs(obs.api, task_id)
            assert (after["run_id"], after["attempt"]) == (run_id, 2)
            assert after["branch"] == before["branch"]
            assert after["retries"][0]["note"] == note
            assert after["retries"][0]["from_phase"] == "review"
            page.goto(f"/#/r/{obs.repo_id}/runs/{run_id}")
            expect(page.locator('[data-test="run-retry"]')).to_contain_text(note)
            expect(page.locator('[data-test="run-attempt"]')).to_contain_text("2")
            calls = _calls(script)
            assert len([c for c in calls if c["agent"] == "planner"]) == 1
            reviews = [c for c in calls if c["agent"] == "reviewer"]
            assert len(reviews) == 2
            assert reviews[0]["session_id"] == reviews[1]["session_id"]
            assert reviews[0]["cwd"] == reviews[1]["cwd"]
            assert not blocked and not marker.exists()
        finally:
            context.close()
            browser.close()
