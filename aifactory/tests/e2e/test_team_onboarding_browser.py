"""One offline team journey: seed, extract, run with a skill, adopt, export and pull."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml
from f3_repo import api_get, log_tail, obs_server, registered_id, run_logs_tail
from multi_repo_e2e import diagnostic_tripwire, repo_snapshot
from playwright.sync_api import Browser, Dialog, Page, Route, expect, sync_playwright
from team_flow_e2e import (
    EXPORT_MARKER,
    SKILL_DESCRIPTION,
    TASK,
    commit_all,
    git,
    publication_hook,
    team_repo,
    team_script,
    write,
)
from test_f3_browser import Server, _calls, _choose, _launch, _start_run, _watch_run
from validation.fake import REAL_HARNESS_MESSAGE

from aifactory.config.manifest import read_manifest
from aifactory.run.task import session_dir_of

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


@contextmanager
def guarded_page(browser: Browser, url: str, violations: list[str]) -> Iterator[Page]:
    context = browser.new_context(base_url=url, service_workers="block")
    context.set_default_timeout(60_000)
    expect.set_options(timeout=60_000)

    def local_only(route: Route) -> None:
        request = route.request.url
        if not request.startswith(url + "/"):
            violations.append(request)
            route.abort()
        elif "/factory/check" in request or "/machine/check" in request:
            route.continue_(url=request + ("&" if "?" in request else "?") + "offline=1")
        else:
            route.continue_()

    def dismiss(dialog: Dialog) -> None:
        violations.append("dialog: " + dialog.message)
        dialog.dismiss()

    context.route("**/*", local_only)
    page = context.new_page()
    page.on("dialog", dismiss)
    page.on("filechooser", lambda _: violations.append("filechooser"))
    try:
        yield page
    finally:
        context.close()


def inspect_repo(page: Page, repo: Path) -> None:
    page.goto("/#/repos/add")
    page.locator('[data-test="add-path"]').fill(str(repo))
    page.locator('[data-test="add-inspect"]').click()
    expect(page.locator('[data-test="inspect-card"]')).to_be_visible()


def settle_operation(page: Page) -> None:
    page.locator('[data-test="item-operation"]').scroll_into_view_if_needed()
    page.evaluate(
        "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )


def apply_item(page: Page, repo: Path) -> None:
    settle_operation(page)
    before = git(repo, "rev-parse", "HEAD")
    _choose(page, '[data-test="item-target"]', "base")
    page.locator('[data-test="item-preview"]').click()
    expect(page.locator('[data-test="item-apply"]')).to_be_enabled()
    assert git(repo, "rev-parse", "HEAD") == before
    page.locator('[data-test="item-apply"]').click()
    assert git(repo, "rev-parse", "HEAD") == before
    page.locator('[data-test="confirm-ok"]').click()
    expect(page.locator('[data-test="item-result"]')).to_have_text(re.compile(r"[0-9a-f]{40}"))
    assert git(repo, "rev-parse", "HEAD") != before
    assert git(repo, "status", "--porcelain") == ""


def test_team_onboarding_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")
    git_config = write(
        tmp_path, "isolated-gitconfig", "[maintenance]\n\tauto = false\n[gc]\n\tauto = 0\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(git_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    home_a, home_b = tmp_path / "machine-a", tmp_path / "machine-b"
    assert not home_a.exists() and not home_b.exists()
    repo = team_repo(tmp_path)
    remote, library_remote = tmp_path / "legacy.git", tmp_path / "library.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(library_remote))
    adws_before = repo_snapshot(repo, remote)["files"]
    script = team_script(tmp_path / "fake.json")
    wire, marker = diagnostic_tripwire(tmp_path)
    proof = tmp_path / "publication.json"
    violations: list[str] = []
    logs = [tmp_path / f"{name}.log" for name in ("a", "a-onboard", "b", "b-adopt", "a-pull")]
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        try:
            with obs_server(None, script, wire, logs[0], home_a) as obs:
                with guarded_page(browser, obs.url, violations) as page:
                    page.goto("/")
                    expect(page).to_have_url(obs.url + "/#/overview")
                    page.locator('[data-test="readiness-warning"]').click()
                    expect(page).to_have_url(obs.url + "/#/problems")
                    page.locator('[data-test="readiness-warning"] a[href="#/setup"]').first.click()
                    expect(page).to_have_url(obs.url + "/#/setup")
                    expect(page.locator("h1")).to_have_text("Tento počítač")
                    assert api_get(obs.url, "/api/repos")["repos"] == []
                    page.locator('[data-test="library-init"]').click()
                    expect(page.locator('[data-test="confirm-dialog"]')).to_contain_text(
                        "agent/builder"
                    )
                    library = home_a / "library"
                    assert not library.exists()
                    page.locator('[data-test="confirm-ok"]').click()
                    expect(page.locator('[data-test="library-path"]')).to_have_text(str(library))
                    assert git(library, "rev-list", "--count", "HEAD") == "1"
                    # UI seeds locally; the fixture connects the team's local bare remote.
                    git(library, "remote", "add", "origin", str(library_remote))
                    write(
                        library,
                        "skills/team-check/SKILL.md",
                        "---\nname: team-check\n"
                        f"description: {SKILL_DESCRIPTION}\n---\nCheck shared contracts.\n",
                    )
                    commit_all(library, "Share team skill")
                    git(library, "push", "-u", "origin", "main")
                    assert git(library, "rev-parse", "HEAD") == git(
                        library_remote, "rev-parse", "main"
                    )
            hook = publication_hook(remote, library_remote, proof)
            preview_repo = repo_snapshot(repo, remote)
            preview_library = repo_snapshot(library, library_remote)
            # `factory obs --repo` registers without installing (the dashboard's Add would
            # install factory from the library); the sssf repo is onboarded from Factory.
            with obs_server(repo, script, wire, logs[1], home_a) as obs:
                with guarded_page(browser, obs.url, violations) as page:
                    page.goto(f"/#/r/{obs.repo_id}/factory")
                    plan = page.locator('[data-test="onboarding-plan"]')
                    expect(plan).to_contain_text("builder")
                    expect(plan).to_contain_text("simple-sdlc")
                    expect(plan).to_contain_text("manifest.yaml")
                    for path, bare, baseline_preview in (
                        (repo, remote, preview_repo),
                        (library, library_remote, preview_library),
                    ):
                        preview_after = repo_snapshot(path, bare)
                        for key in ("files", "head", "status", "remote_refs"):
                            assert preview_after[key] == baseline_preview[key]
                    before = git(repo, "rev-parse", "HEAD")
                    lib_before = git(library, "rev-parse", "HEAD")
                    page.locator('[data-test="onboarding-perform"]').click()
                    expect(page.locator('[data-test="confirm-dialog"]')).to_contain_text(
                        "adws/ zůstane beze změny"
                    )
                    assert git(repo, "rev-parse", "HEAD") == before
                    assert git(library, "rev-parse", "HEAD") == lib_before
                    page.locator('[data-test="confirm-ok"]').click()
                    expect(page.locator('[data-test="factory-state"]')).to_have_text("Onboardováno")
                    page.locator('[data-test="factory-recheck"]').click()
                    evidence = json.loads(proof.read_text())
                    assert (
                        evidence["repo"]
                        == git(remote, "rev-parse", "main")
                        == git(repo, "rev-parse", "HEAD")
                    )
                    assert evidence["library"] == git(library_remote, "rev-parse", "main")
                    hook.unlink()
                    manifest = read_manifest(repo)
                    assert manifest is not None and manifest.onboarding is not None
                    assert manifest.onboarding.source == "sssf"
                    builder_item = manifest.items.agents["builder"].item
                    old_version = manifest.items.agents["builder"].version
                    assert (
                        git(remote, "show", "main:.factory/manifest.yaml")
                        == (repo / ".factory/manifest.yaml").read_text().strip()
                    )
                    after_files = repo_snapshot(repo, remote)["files"]
                    assert {k: v for k, v in after_files.items() if k.startswith("adws/")} == {
                        k: v for k, v in adws_before.items() if k.startswith("adws/")
                    }
                    page.locator('[data-test="item-add"]').click()
                    settle_operation(page)
                    _choose(page, '[data-test="item-type"]', "skill")
                    _choose(page, '[data-test="item-name"]', "team-check")
                    _choose(page, '[data-test="item-agent"]', "builder")
                    apply_item(page, repo)
                    expect(
                        page.locator('[data-test="item-skill-team-check"] [data-state]')
                    ).to_have_attribute("data-state", "synced")
                    roster = yaml.safe_load((repo / ".factory/agents.yaml").read_text())
                    assert (
                        "team-check"
                        in next(a for a in roster["agents"] if a["name"] == "builder")["skills"]
                    )
                    skill_manifest = read_manifest(repo)
                    assert skill_manifest is not None
                    assert "team-check" in skill_manifest.items.skills
                    for folder in (".claude", ".agents"):
                        assert (repo / folder / "skills/team-check/SKILL.md").read_bytes() == (
                            library / "skills/team-check/SKILL.md"
                        ).read_bytes()
                    server = Server(
                        repo,
                        obs.url,
                        logs[1],
                        script,
                        marker,
                        before,
                        home_a,
                        registered_id(home_a, repo),
                    )
                    run_id = _start_run(page, server, TASK, commit_first=False)
                    _watch_run(page, server, run_id, TASK)
                    detail = api_get(server.api, f"/runs/{run_id}")
                    assert any(
                        p["name"] == "build" and p["status"] == "success" for p in detail["phases"]
                    )
                    system = (
                        session_dir_of(repo, run_id) / "builder/prompts/phases/build/system.md"
                    ).read_text()
                    assert "## Available skills" in system
                    assert "team-check" in system and SKILL_DESCRIPTION in system
                    assert ".claude/skills/team-check/SKILL.md" in system
                    assert [c["agent"] for c in _calls(script)] == [
                        "planner",
                        "builder",
                        "tester",
                        "test-reviewer",
                        "reviewer",
                        "documenter",
                    ]
                    page.screenshot(path=str(tmp_path / "a-run.png"))
            # Publish the skill commit on main for the second machine; task PR stays separate.
            git(repo, "push", "origin", "main")
            repo_b = tmp_path / "clone-b"
            git(tmp_path, "clone", str(remote), str(repo_b))
            git(repo_b, "status", "--porcelain")
            baseline = repo_snapshot(repo_b, remote)
            with obs_server(None, script, wire, logs[2], home_b) as obs:
                with guarded_page(browser, obs.url, violations) as page:
                    # first visit: the overview's guide leads to this machine's setup
                    page.goto("/")
                    expect(page.locator('[data-test="readiness-warning"]')).to_be_visible()
                    page.goto("/#/setup")
                    expect(page.locator("h1")).to_have_text("Tento počítač")
                    page.locator('[data-test="library-url"]').fill(str(library_remote))
                    page.locator('[data-test="library-clone"]').click()
                    expect(page.locator('[data-test="confirm-dialog"]')).to_contain_text(
                        str(home_b / "library")
                    )
                    assert not (home_b / "library").exists()
                    page.locator('[data-test="confirm-ok"]').click()
                    expect(page.locator('[data-test="library-path"]')).to_have_text(
                        str(home_b / "library")
                    )
                    assert git(home_b / "library", "rev-parse", "HEAD") == git(
                        library_remote, "rev-parse", "main"
                    )
            # registered without installing: the clone is already onboarded
            with obs_server(repo_b, script, wire, logs[3], home_b) as obs:
                with guarded_page(browser, obs.url, violations) as page:
                    page.goto(f"/#/r/{obs.repo_id}/factory")
                    expect(page.locator('[data-test="factory-state"]')).to_have_text("Onboardováno")
                    expect(page.locator('[data-test="onboarding-panel"]')).not_to_contain_text(
                        "Onboarding — jednou"
                    )
                    expect(page.locator('[data-test="onboarding-plan"]')).to_be_visible()
                    assert repo_snapshot(repo_b, remote) == baseline
                    prompt = repo_b / ".factory/prompts/builder/system.md"
                    prompt.write_text(prompt.read_text() + "\n" + EXPORT_MARKER + "\n")
                    commit_all(repo_b, "Revise team builder on machine B")
                    page.goto(f"/#/r/{registered_id(home_b, repo_b)}/factory")
                    page.locator(
                        '[data-test="item-agent-builder"] [data-test="item-export"]'
                    ).click()
                    expect(page.locator('[data-test="item-slot"]')).to_have_value("")
                    apply_item(page, repo_b)
                    new_manifest = read_manifest(repo_b)
                    assert new_manifest is not None
                    new_version = new_manifest.items.agents["builder"].version
                    assert new_version != old_version
                    assert git(home_b / "library", "rev-parse", "HEAD") == git(
                        library_remote, "rev-parse", "main"
                    )
                    assert EXPORT_MARKER in git(
                        library_remote, "show", f"main:agents/{builder_item}/system.md"
                    )
                    page.screenshot(path=str(tmp_path / "b-export.png"))
            # A already has a run trace; reopening obs can update its runtime database.
            # Pull must leave the repository's installed prompt, manifest and HEAD alone.
            unchanged_a = {
                rel: (repo / rel).read_bytes()
                for rel in (".factory/prompts/builder/system.md", ".factory/manifest.yaml")
            }
            head_a = git(repo, "rev-parse", "HEAD")
            with obs_server(None, script, wire, logs[4], home_a) as obs:
                with guarded_page(browser, obs.url, violations) as page:
                    page.goto("/#/setup")
                    page.get_by_role("button", name="Stáhnout", exact=True).click()
                    expect(page.get_by_role("status")).to_contain_text("Stažení dokončeno")
                    page.goto("/#/library")
                    row = page.locator('[data-test="library-item"]').filter(
                        has=page.get_by_role("button", name=builder_item, exact=True)
                    )
                    expect(row).to_contain_text("zastaralé")
                    row.get_by_role("button", name=builder_item, exact=True).click()
                    expect(page.locator('[data-test="item-history"]')).to_contain_text("v2")
                    expect(page.locator('[data-test="library-detail"]')).to_contain_text(
                        EXPORT_MARKER
                    )
                    repo_id = registered_id(home_a, repo)
                    page.goto(f"/#/r/{repo_id}/factory")
                    expect(
                        page.locator('[data-test="item-agent-builder"] [data-state]')
                    ).to_have_attribute("data-state", "outdated")
                    items = api_get(obs.url, f"/api/repos/{repo_id}/factory/items")["items"]
                    assert any(i["name"] == "builder" and i["state"] == "outdated" for i in items)
                    assert git(repo, "rev-parse", "HEAD") == head_a
                    assert all(
                        (repo / rel).read_bytes() == data for rel, data in unchanged_a.items()
                    )
                    page.screenshot(path=str(tmp_path / "a-pull.png"))
            assert violations == []
            assert not marker.exists()
            assert all(REAL_HARNESS_MESSAGE not in log.read_text() for log in logs)
            assert REAL_HARNESS_MESSAGE not in run_logs_tail(home_a)
        except Exception:
            print("\n".join(log_tail(log) for log in logs))
            print(run_logs_tail(home_a))
            print(_calls(script))
            print(proof.read_text() if proof.exists() else "No publication proof")
            raise
        finally:
            browser.close()
