"""Empty obs → add/install repos → switch screens → run/review → safe removal."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from f3_repo import (
    T01,
    _kill_running_runs,
    api_get,
    fake_script,
    git,
    make_f3_repo,
    obs_server,
    registered_id,
    run_state,
    wait_for,
)
from multi_repo_e2e import diagnostic_tripwire, fresh_repo, repo_snapshot
from playwright.sync_api import Dialog, Page, Route, expect, sync_playwright
from test_f3_browser import (
    RUN_TIMEOUT_S,
    Net,
    Server,
    _calls,
    _check_report,
    _create_task,
    _launch,
    _nav,
    _start_run,
)
from validation.fake import REAL_HARNESS_MESSAGE

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


def _menu(page: Page, action: str) -> None:
    page.locator('[data-test="switcher-button"]').click()
    page.locator(f'[data-test="{action}"]').click()


def _inspect(page: Page, repo: Path) -> None:
    field = page.locator('[data-test="add-path"]')
    field.fill(str(repo))
    field.press("Escape")
    page.locator('[data-test="add-inspect"]').click()
    expect(page.locator('[data-test="inspect-root"]')).to_have_text(str(repo))


def test_multi_repo_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    credentials = tmp_path / "claude-home"
    credentials.mkdir()
    (credentials / ".credentials.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(credentials))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    repo_a = make_f3_repo(tmp_path / "repo-a")
    repo_b, bare = fresh_repo(tmp_path)
    before_install = git(repo_b, "rev-parse", "HEAD")
    script = fake_script(tmp_path / "fake.json")
    release = tmp_path / "release-plan"
    data = json.loads(script.read_text(encoding="utf-8"))
    planner = data["agents"]["planner"][0]
    planner.update(wait_for_file=str(release), wait_timeout_s=RUN_TIMEOUT_S)
    script.write_text(json.dumps({"agents": {"planner": [planner]}}), encoding="utf-8")
    wire, marker = diagnostic_tripwire(tmp_path)
    home, log = tmp_path / "haifa-home", tmp_path / "obs.log"
    assert not home.exists()
    net = Net()
    choosers: list[str] = []
    try:
        with obs_server(None, script, wire, log, home) as obs:
            assert obs.repo_id == ""
            with pytest.raises(ValueError, match="empty dashboard"):
                _ = obs.api
            assert api_get(obs.url, "/api/repos")["repos"] == []
            with sync_playwright() as playwright:
                browser = _launch(playwright)
                context = browser.new_context(base_url=obs.url, service_workers="block")
                context.set_default_timeout(60_000)
                expect.set_options(timeout=60_000)

                def local_only(route: Route) -> None:
                    if not route.request.url.startswith(obs.url + "/"):
                        net.aborted.append(route.request.url)
                        route.abort()
                    elif re.search(r"/api/repos/[^/]+/factory/check(?:\?|$)", route.request.url):
                        route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps({"ok": True, "data": _check_report()}),
                        )
                    else:
                        route.continue_()

                context.route("**/*", local_only)
                page = context.new_page()

                def no_dialog(dialog: Dialog) -> None:
                    net.dialogs.append(f"{dialog.type}: {dialog.message}")
                    dialog.dismiss()

                page.on("dialog", no_dialog)
                page.on("filechooser", lambda _: choosers.append("filechooser"))
                server: Server | None = None
                try:
                    page.goto("/")
                    expect(page).to_have_url(f"{obs.url}/#/overview")
                    warning = page.locator('[data-test="readiness-warning"]')
                    warning.click()
                    expect(page).to_have_url(f"{obs.url}/#/problems")
                    warning = page.locator(
                        '[data-test="system-problems"] [data-test="readiness-warning"]'
                    )
                    expect(warning).to_contain_text("Přidej repozitář")
                    warning.locator('a[href="#/repos/add"]').first.click()
                    _inspect(page, repo_a)
                    page.locator('[data-test="inspect-add"]').click()
                    expect(page.locator('[data-test="repo-added"]')).to_be_visible()
                    page.locator('[data-test="repo-added-open"]').click()
                    expect(page).to_have_url(re.compile(r"#/r/[^/]+/factory$"))
                    id_a = registered_id(home, repo_a)
                    expect(page).to_have_url(f"{obs.url}/#/r/{id_a}/factory")
                    server = Server(
                        repo_a,
                        obs.url,
                        log,
                        script,
                        marker,
                        git(repo_a, "rev-parse", "HEAD"),
                        home,
                        id_a,
                    )

                    _menu(page, "switch-add")
                    _inspect(page, repo_b)
                    page.locator('[data-test="inspect-init"]').click()
                    expect(page.locator('[data-test="factory-plan"]')).to_be_visible()
                    id_b = registered_id(home, repo_b)
                    expect(page.locator('[data-test="install-provider"]')).to_have_attribute(
                        "data-value", "local"
                    )
                    registered = api_get(obs.url, "/api/repos")["repos"]
                    assert {r["id"]: r["path"] for r in registered} == {
                        id_a: str(repo_a),
                        id_b: str(repo_b),
                    }
                    subject = "HAIFA-S01-T22: install repo B from browser"
                    page.locator('[data-test="factory-message"]').fill(subject)
                    assert git(repo_b, "rev-parse", "HEAD") == before_install
                    assert git(bare, "rev-parse", "main") == before_install
                    assert not (repo_b / ".factory").exists()
                    page.locator('[data-test="factory-perform"]').click()
                    expect(page.locator('[data-test="confirm-dialog"]')).to_contain_text(
                        "pushnout na origin"
                    )
                    page.locator('[data-test="confirm-ok"]').click()
                    page.locator('[data-test="repo-added-open"]').click()
                    expect(page.locator('[data-test="factory-verdict"]')).to_be_visible()
                    installed = git(repo_b, "rev-parse", "main")
                    assert installed != before_install
                    assert git(bare, "rev-parse", "main") == installed
                    for repo in (repo_b, bare):
                        assert git(repo, "log", "--format=%s", f"{before_install}..main") == subject
                        assert git(repo, "rev-list", "--count", f"{before_install}..main") == "1"
                    assert (repo_b / ".factory/manifest.yaml").is_file()

                    _nav(page, "runs")
                    for repo, repo_id in ((repo_a, id_a), (repo_b, id_b), (repo_a, id_a)):
                        _menu(page, f"switch-repo-{repo_id}")
                        expect(page).to_have_url(f"{obs.url}/#/r/{repo_id}/runs")
                        expect(page.locator("h1")).to_have_text("Běhy")
                        expect(page.locator('[data-test="switcher-current"]')).to_have_text(
                            repo.name
                        )

                    _nav(page, "backlog")
                    task = _create_task(page, "Multi-repo feature", "Implementace v repozitáři A.")
                    assert task == T01
                    run_id = _start_run(page, server, task, commit_first=True)
                    _menu(page, "switch-overview")
                    card = page.locator(f'[data-test="overview-card"][data-repo="{id_a}"]')
                    running = card.locator(f'[data-test="row-running"][data-run="{run_id}"]')
                    expect(running).to_contain_text(task)
                    expect(running.locator('[data-test="row-phase"]')).to_contain_text("plan")
                    expect(running).to_have_attribute("href", f"#/r/{id_a}/runs/{run_id}")
                    expect(
                        page.locator('[data-test="total-running"] [data-test="total-count"]')
                    ).to_have_text("1")
                    expect(
                        page.locator(f'[data-repo="{id_b}"] [data-test="row-running"]')
                    ).to_have_count(0)
                    expect(
                        page.locator(
                            f'[data-test="overview-card"][data-repo="{id_b}"] '
                            '[data-test="card-warnings"]'
                        )
                    ).to_contain_text("backlog directory 'backlog' does not exist")
                    release.touch()

                    def finished() -> str | None:
                        state = str(run_state(server.api, run_id)["state"])
                        return state if state != "running" else None

                    state = wait_for(finished, RUN_TIMEOUT_S, "run finished", server.report)
                    assert state == "succeeded", server.report(task)
                    review = card.locator(f'[data-test="row-review"][data-task="{task}"]')
                    expect(review).to_be_visible()
                    expect(review).to_have_attribute("href", f"#/r/{id_a}/review/{task}")
                    pr = run_state(server.api, run_id)["pr"]
                    assert pr and pr["url"].startswith("local:") and pr["state"] == "open", pr
                    assert git(repo_a, "rev-parse", pr["pr_id"])
                    overview = api_get(obs.url, "/api/overview")["repos"]
                    overview_a = next(r for r in overview if r["id"] == id_a)
                    assert any(
                        item["task_id"] == task
                        and item["pr_id"] == pr["pr_id"]
                        and item["url"] == pr["url"]
                        for item in overview_a["review"]
                    ), overview_a
                    expect(review).to_contain_text(f"PR #{pr['pr_id']}")
                    expect(running).to_have_count(0)
                    expect(
                        page.locator('[data-test="total-review"] [data-test="total-count"]')
                    ).to_have_text("1")

                    _menu(page, "switch-overview")
                    row = page.locator(f'[data-repo="{id_b}"]')
                    expect(row).to_be_visible()
                    before_remove = repo_snapshot(repo_b, bare)
                    row.locator('[data-test="card-remove"], [data-test="calm-remove"]').click()
                    modal = page.locator('[data-test="confirm-dialog"]')
                    expect(modal).to_contain_text(f"Odebrat {repo_b.name} z dashboardu?")
                    expect(modal).to_contain_text("Ve složce")
                    modal.locator('[data-test="confirm-ok"]').click()
                    expect(row).to_have_count(0)
                    expect(page.locator(f'[data-repo="{id_a}"]')).to_be_visible()
                    assert [r["id"] for r in api_get(obs.url, "/api/repos")["repos"]] == [id_a]
                    assert registered_id(home, repo_a) == id_a
                    with pytest.raises(AssertionError, match="not in the registry"):
                        registered_id(home, repo_b)
                    page.locator('[data-test="switcher-button"]').click()
                    expect(page.locator(f'[data-test="switch-repo-{id_b}"]')).to_have_count(0)
                    expect(page.locator(f'[data-test="switch-repo-{id_a}"]')).to_be_visible()
                    assert repo_snapshot(repo_b, bare) == before_remove
                except Exception as exc:
                    report = server.report(T01) if server else log.read_text(encoding="utf-8")
                    raise AssertionError(
                        f"{exc}\n{report}\nexternal={net.aborted} dialogs={net.dialogs}"
                    ) from exc
                finally:
                    release.touch()
                    context.close()
                    browser.close()
            assert net.aborted == []
            assert net.dialogs == []
            assert choosers == []
            assert not marker.exists(), marker.read_text(encoding="utf-8")
            calls = _calls(script)
            assert [c["agent"] for c in calls] == ["planner"], calls
            assert Path(calls[0]["cwd"]).is_relative_to(repo_a / ".factory/worktrees"), calls
            for output in [log, *(home / "logs").glob("*.log")]:
                assert REAL_HARNESS_MESSAGE not in output.read_text(encoding="utf-8")
    finally:
        release.touch()
        _kill_running_runs(repo_a)
