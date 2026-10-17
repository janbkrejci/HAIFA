"""From the empty overview to a merged run of the sample repository, in a browser.

``factory obs`` starts with an empty registry over the fake harness (``f3_repo``). The test
clicks "Vyzkoušet na ukázce": the dashboard creates the sample in ``$HAIFA_HOME/demo``, starts
``DEMO-S01-T01`` with the first tested harness (``harness-tests.json`` says claude passed) and
opens its backlog. The fake builder waits for a release file, so the run detail is seen while
the build runs; then the fake tester plans the sample's real unittest suite, the run commits
and publishes a local PR, the test approves it in Review and the run detail offers an own
repository. "Odebrat ukázku" removes the registry entry and the folder. No model and no
hosting is called.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from f3_repo import api_get, git, obs_server, run_state, runs_report, task_runs, tripwire, wait_for
from playwright.sync_api import Dialog, Route, expect, sync_playwright
from test_f3_browser import RUN_START_TIMEOUT_S, RUN_TIMEOUT_S, SERVER_TIMEOUT_MS, _launch

pytestmark = [pytest.mark.browser, pytest.mark.slow, pytest.mark.xdist_group("e2e")]

TASK = "DEMO-S01-T01"
ALL_BEFORE = '__all__ = ["line_count", "word_count", "words"]'
CHAR_COUNT = '''

def char_count(text: str, *, spaces: bool = True) -> int:
    """How many characters `text` has; with `spaces=False` whitespace does not count."""
    return len(text) if spaces else sum(1 for ch in text if not ch.isspace())
'''
TEST_ANCHOR = "class "
CHECK = {
    "name": "unittest",
    "argv": [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
}


def _script(path: Path, release: Path) -> Path:
    build = {
        "wait_for_file": str(release),
        "wait_timeout_s": RUN_TIMEOUT_S,
        "envelope": {
            "status": "success",
            "summary": "add char_count",
            "artifacts": [],
            "changed_files": ["textstats.py"],
            "commit_message": "Add char_count",
        },
        "edits": [
            {
                "path": "textstats.py",
                "replace": [ALL_BEFORE, ALL_BEFORE.replace('["', '["char_count", "')],
            },
            {"path": "textstats.py", "append": CHAR_COUNT},
        ],
    }
    plan = {
        "envelope": {
            "status": "success",
            "summary": "the sample's unittest suite covers char_count",
            "coverage": "full",
            "reason": "the sample has one small suite",
            "checks": [CHECK],
        },
        "edits": [],
    }
    approve = {
        "envelope": {
            "status": "success",
            "approved": True,
            "summary": "plan fits",
            "findings": [],
            "blocking": [],
        },
        "edits": [],
    }
    script = {"agents": {"builder": [build], "tester": [plan], "test-reviewer": [approve]}}
    path.write_text(json.dumps(script, indent=2), encoding="utf-8", newline="\n")
    return path


def _demo_id(url: str) -> str:
    repos = api_get(url, "/api/repos")["repos"]
    demo = [r for r in repos if r.get("demo")]
    assert len(demo) == 1, repos
    return str(demo[0]["id"])


def test_demo_from_empty_overview_to_merge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    credentials = tmp_path / "claude-home"
    credentials.mkdir()
    (credentials / ".credentials.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(credentials))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    release = tmp_path / "release-build"
    script = _script(tmp_path / "fake.json", release)
    wire, marker = tripwire(tmp_path / "wire")
    home, log = tmp_path / "haifa-home", tmp_path / "obs.log"
    home.mkdir()
    tests = {"claude": {"claude-opus-5-5": {"ok": True, "answer": "OK"}}}
    (home / "harness-tests.json").write_text(json.dumps(tests), encoding="utf-8")
    demo_dir = home / "demo"
    aborted: list[str] = []
    dialogs: list[str] = []
    with obs_server(None, script, wire, log, home) as obs:
        api: dict[str, str] = {}

        def report() -> str:
            base = api.get("base")
            runs = runs_report(base, TASK) if base else "(no sample yet)"
            return f"{runs}\n--- server log\n{log.read_text(encoding='utf-8')[-6000:]}"

        with sync_playwright() as playwright:
            browser = _launch(playwright)
            context = browser.new_context(base_url=obs.url, service_workers="block")
            context.set_default_timeout(SERVER_TIMEOUT_MS)
            expect.set_options(timeout=SERVER_TIMEOUT_MS)

            def local_only(route: Route) -> None:
                if route.request.url.startswith(obs.url + "/"):
                    route.continue_()
                else:
                    aborted.append(route.request.url)
                    route.abort()

            context.route("**/*", local_only)
            page = context.new_page()

            def no_dialog(dialog: Dialog) -> None:
                dialogs.append(f"{dialog.type}: {dialog.message}")
                dialog.dismiss()

            page.on("dialog", no_dialog)
            try:
                # the empty overview offers the sample next to adding a repository
                page.goto("/")
                empty = page.locator('[data-test="no-repos"]')
                expect(empty.locator('[data-test="add-repo-link"]')).to_be_visible()
                empty.locator('[data-test="try-demo"]').click()
                expect(page).to_have_url(re.compile(rf"#/r/[^/]+/backlog/{TASK}$"))
                repo_id = _demo_id(obs.url)
                api["base"] = f"{obs.url}/api/repos/{repo_id}"
                assert git(demo_dir, "branch", "--show-current") == "main"
                expect(page.locator('[data-test="task-id"]')).to_have_text(TASK)
                banner = page.locator('[data-test="demo-banner"]')
                expect(banner).to_contain_text("Ukázkové repo")

                def claimed() -> str | None:
                    runs = task_runs(api["base"], TASK)
                    return str(runs[0]["run_id"]) if runs else None

                run_id = wait_for(claimed, RUN_START_TIMEOUT_S, "sample run claimed", report)
                run = run_state(api["base"], run_id)
                assert run["state"] == "running", report()
                expect(banner.locator('[data-test="demo-started"]')).to_contain_text("claude")

                # while the builder works, the run detail explains where the run is
                page.goto(f"/#/r/{repo_id}/runs/{run_id}")
                steps = page.locator('[data-test="demo-steps"]')
                expect(steps.locator('[data-step="worktree"]')).to_have_attribute(
                    "data-state", "done"
                )
                expect(steps.locator('[data-step="build"]')).to_have_attribute(
                    "data-state", "current"
                )
                expect(steps.locator('[data-step="build"]')).to_contain_text("builder")
                release.write_text("go\n", encoding="utf-8")

                def finished() -> dict[str, Any] | None:
                    state = run_state(api["base"], run_id)
                    return state if state["state"] != "running" else None

                done = wait_for(finished, RUN_TIMEOUT_S, "sample run finished", report)
                assert done["state"] == "succeeded", report()
                assert done["pr"] and done["pr"]["state"] == "open", report()

                # the run is done and its PR waits: the explanation sends to Review
                expect(steps.locator('[data-step="merge"]')).to_have_attribute(
                    "data-state", "current"
                )
                for step in ("build", "test", "review", "pr"):
                    expect(steps.locator(f'[data-step="{step}"]')).to_have_attribute(
                        "data-state", "done"
                    )
                steps.locator('[data-test="demo-review-link"]').click()
                approve = page.locator('[data-test="approve"]')
                expect(approve).to_be_enabled()
                approve.click()
                modal = page.locator('[data-test="confirm-dialog"]')
                modal.locator('[data-test="confirm-ok"]').click()
                expect(page.locator('[data-test="notice"]')).to_contain_text("Sloučeno")
                assert "char_count" in git(demo_dir, "show", "main:textstats.py")

                # after the merge the run detail offers an own repository
                page.goto(f"/#/r/{repo_id}/runs/{run_id}")
                finished_box = page.locator('[data-test="demo-finished"]')
                expect(finished_box).to_contain_text("celým cyklem")
                expect(
                    finished_box.locator('[data-test="demo-finished-add-repo"]')
                ).to_have_attribute("href", "#/repos/add")

                # one button removes the sample with its folder
                finished_box.locator('[data-test="remove-demo"]').click()
                modal = page.locator('[data-test="confirm-dialog"]')
                expect(modal).to_contain_text(str(demo_dir.absolute()))
                modal.locator('[data-test="confirm-ok"]').click()
                expect(page.locator('[data-test="no-repos"]')).to_be_visible()
                assert not demo_dir.exists()
                assert api_get(obs.url, "/api/repos")["repos"] == []
            except Exception as exc:
                raise AssertionError(f"{exc}\n{report()}") from exc
            finally:
                context.close()
                browser.close()
    assert aborted == []
    assert dialogs == []
    assert not marker.exists(), marker.read_text(encoding="utf-8")
