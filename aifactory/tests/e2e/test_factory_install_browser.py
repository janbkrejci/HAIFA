"""Install from the dashboard into a fresh local repo and verify its bare origin."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from f3_repo import git, make_f3_repo, obs_server, registered_id
from playwright.sync_api import Dialog, Route, expect, sync_playwright
from test_f3_browser import _choose, _launch

from fake_exe import make_executable

pytestmark = [pytest.mark.browser, pytest.mark.xdist_group("e2e")]


def test_factory_install_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    credentials = tmp_path / "claude-home"
    credentials.mkdir()
    (credentials / ".credentials.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(credentials))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    control = make_f3_repo(tmp_path / "control")
    repo = tmp_path / "fresh"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("fresh repository\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "initial")
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "-u", "origin", "main")
    git(repo, "remote", "set-head", "origin", "main")
    legacy = repo / "adws/adw_sssf_config/sssf.config.yaml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("name: legacy\n", encoding="utf-8")
    git(repo, "add", "adws")
    git(repo, "commit", "-q", "-m", "legacy sssf")
    git(repo, "push", "-q", "origin", "main")
    before = git(repo, "rev-parse", "HEAD")
    script = tmp_path / "fake.json"
    script.write_text(json.dumps({"agents": {}}), encoding="utf-8")
    marker = tmp_path / "model-called"
    probe = tmp_path / "probe"
    probe.write_text(
        "#!/usr/bin/env python\nimport sys\nfrom pathlib import Path\n"
        "if sys.argv[1:] in (['--version'], ['auth', 'status'], ['login', 'status'], "
        "['--list-models']):\n"
        "    print('test CLI 1.0')\n"
        "elif sys.argv[1:] == ['app-server', '--stdio', '-c', 'mcp_servers={}', "
        "'-c', 'analytics.enabled=false']:\n"
        "    sys.exit(0)\n"
        f"else:\n    Path({str(marker)!r}).write_text('called')\n    sys.exit(97)\n",
        encoding="utf-8",
    )
    wire = make_executable(probe)
    home = tmp_path / "home"
    with obs_server(control, script, wire, tmp_path / "obs.log", home) as server:
        with sync_playwright() as playwright:
            browser = _launch(playwright)
            context = browser.new_context(base_url=server.url)
            context.set_default_timeout(60_000)
            expect.set_options(timeout=60_000)
            external: list[str] = []
            dialogs: list[str] = []

            def local_only(route: Route) -> None:
                if route.request.url.startswith(server.url + "/"):
                    route.continue_()
                else:
                    external.append(route.request.url)
                    route.abort()

            context.route("**/*", local_only)
            page = context.new_page()

            def dismiss_dialog(dialog: Dialog) -> None:
                dialogs.append(dialog.message)
                dialog.dismiss()

            page.on("dialog", dismiss_dialog)
            try:
                page.goto("/#/repos/add")
                page.locator('[data-test="add-path"]').fill(str(repo))
                page.locator('[data-test="add-inspect"]').click()
                expect(page.locator('[data-test="inspect-sssf-warning"]')).to_contain_text(
                    "smazána"
                )
                expect(page.locator('[data-test="inspect-onboard"]')).to_have_count(0)
                page.locator('[data-test="inspect-init"]').click()
                expect(page.locator('[data-test="factory-plan"]')).to_be_visible()
                temp_id = registered_id(home, repo)
                assert not (repo / "adws").exists()
                assert git(repo, "log", "-1", "--format=%s") == (
                    "Remove legacy sssf installation before adding HAIFA"
                )
                assert git(repo, "rev-parse", "HEAD~1") == before
                before = git(repo, "rev-parse", "HEAD")
                assert not (repo / ".factory").exists()
                page.locator('[data-test="cancel-install"]').click()
                expect(page.locator('[data-test="add-path"]')).to_be_visible()
                # Wait for the install action to return after temporary repo removal.
                expect(page.locator('[data-test="inspect-init"]')).to_be_visible()
                registry = context.request.get("/api/repos").json()["data"]["repos"]
                assert temp_id not in [r["id"] for r in registry]
                assert not (repo / ".factory").exists()
                page.locator('[data-test="inspect-init"]').click()
                expect(page.locator('[data-test="install-provider"]')).to_have_attribute(
                    "data-value", "local"
                )
                _choose(page, '[data-test="harness-builder"]', "codex")
                page.locator('[data-test="model-builder"]').fill("gpt-6.1-sol")
                page.locator('[data-test="thinking-builder"]').fill("medium")
                page.locator('[data-test="factory-message"]').fill("factory from dashboard")
                expect(page.locator('[data-test="factory-perform"]')).to_be_enabled()
                assert git(repo, "rev-parse", "HEAD") == before
                assert git(bare, "rev-parse", "main") == git(repo, "rev-parse", "HEAD~1")
                assert not (repo / ".factory").exists()
                page.locator('[data-test="factory-perform"]').click()
                expect(page.locator('[data-test="confirm-dialog"]')).to_contain_text(
                    "pushnout na origin"
                )
                page.locator('[data-test="confirm-ok"]').click()
                page.locator('[data-test="repo-added-open"]').click()
                expect(page.locator('[data-test="factory-verdict"]')).to_be_visible()
                after = git(repo, "rev-parse", "main")
                assert after != before
                assert git(bare, "rev-parse", "main") == after
                assert git(repo, "log", "-1", "--format=%s") == "factory from dashboard"
                assert git(repo, "rev-list", "--count", f"{before}..main") == "1"
                assert (repo / ".factory/manifest.yaml").is_file()
                roster = yaml.safe_load((repo / ".factory/agents.yaml").read_text(encoding="utf-8"))
                agents = {a["name"]: a for a in roster["agents"]}
                assert agents["builder"]["harness"] == "codex"
                assert agents["builder"]["model"] == "gpt-6.1-sol"
                assert agents["builder"]["thinking"] == "medium"
                assert (
                    agents["planner"].get("harness", roster.get("defaults", {}).get("harness"))
                    != "codex"
                )
            finally:
                context.close()
                browser.close()
            assert external == []
            assert dialogs == []
            assert not marker.exists()
