"""F3 acceptance test in a browser: a task is created, linked, run, watched, approved and
merged from the dashboard alone, with no terminal.

``factory obs`` runs over a temporary repo (provider ``local``, fake harness, see
``f3_repo``); Playwright drives the system Google Chrome (``HAIFA_E2E_CHANNEL``
overrides it, an empty value uses Playwright's bundled chromium, ``just e2e-install``).
Once the server is up the test never changes the repo itself: it only reads git for
the final checks, so every change on ``main`` comes from the dashboard. Requests to
anything but the server are aborted and counted, and no model or hosting is called.

Since HAIFA-S01-T09 every run is a separate ``factory task`` process whose start takes a
while under load: the start request waits at most 30 s for the process to claim its row
and then answers ``pending`` (the dialog shows no link then). So the test waits for the
run process through the API (``/api/runs``), not through fixed pauses, with limits
``RUN_START_TIMEOUT_S`` and ``RUN_TIMEOUT_S``; steps where the server works with git get
``SERVER_TIMEOUT_MS``. On failure it prints the runs' state from the API, the server's
log and the run processes' output.
"""

from __future__ import annotations

import json
import os
import re
import stat
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml
from f3_repo import (
    T01,
    T02,
    fake_script,
    git,
    log_tail,
    make_f3_repo,
    obs_server,
    registered_id,
    run_logs_tail,
    run_state,
    runs_report,
    task_runs,
    tripwire,
    wait_for,
)
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Dialog,
    Page,
    Playwright,
    Route,
    expect,
    sync_playwright,
)
from playwright.sync_api import Error as PlaywrightError

pytestmark = pytest.mark.xdist_group("e2e")

CHANNEL_ENV = "HAIFA_E2E_CHANNEL"
# pure UI: navigation, forms, dropdowns
DEFAULT_TIMEOUT_MS = 15_000
# the UI waits for the server's work with git (backlog commit, run check, merge, lists)
SERVER_TIMEOUT_MS = 60_000
# a run is a separate `factory task` process (HAIFA-S01-T09); the start request waits for it
# to claim its row at most 30 s and then answers `pending`, so the start gets its real time
RUN_START_TIMEOUT_S = 90.0
# the whole fake-harness run process under load
RUN_TIMEOUT_S = 240.0


@dataclass
class Server:
    repo: Path
    url: str
    log: Path
    script: Path
    marker: Path
    init: str
    home: Path
    repo_id: str

    @property
    def api(self) -> str:
        """The base URL of the repo's API (``/api/repos/<id>``)."""
        return f"{self.url}/api/repos/{self.repo_id}"

    def report(self, task_id: str | None = None) -> str:
        """The runs from the API, the server's output and the newest outputs of its runs."""
        return (
            f"{runs_report(self.api, task_id)}\n--- server log\n{log_tail(self.log)}\n"
            f"{run_logs_tail(self.home)}"
        )


@dataclass
class Net:
    aborted: list[str] = field(default_factory=list)
    # system dialogs (confirm/alert/prompt) the page opened; the dashboard must use its own modal
    dialogs: list[str] = field(default_factory=list)


def _launch(p: Playwright) -> Browser:
    """System Chrome first (bundled browsers do not run on every macOS), then bundled chromium."""
    requested = os.environ.get(CHANNEL_ENV)
    channels: list[str | None] = [requested or None] if requested is not None else ["chrome", None]
    errors: list[str] = []
    for channel in channels:
        try:
            if channel is None:
                return p.chromium.launch(headless=True)
            return p.chromium.launch(channel=channel, headless=True)
        except PlaywrightError as exc:
            errors.append(f"{channel or 'bundled chromium'}: {exc.message.splitlines()[0]}")
    pytest.fail(
        "no browser for the F3 test: install Google Chrome or run `just e2e-install`\n"
        + "\n".join(errors)
    )


@pytest.fixture(name="server")
def server_fixture(tmp_path: Path) -> Iterator[Server]:
    repo = make_f3_repo(tmp_path / "repo")
    script = fake_script(tmp_path / "script.json")
    wire, marker = tripwire(tmp_path / "wire")
    log = tmp_path / "obs.log"
    home = tmp_path / "haifa-home"
    init = git(repo, "rev-parse", "HEAD")
    with obs_server(repo, script, wire, log, home) as obs:
        yield Server(repo, obs.url, log, script, marker, init, home, obs.repo_id)


@pytest.fixture(name="net")
def net_fixture() -> Net:
    return Net()


@pytest.fixture(name="page")
def page_fixture(server: Server, net: Net) -> Iterator[Page]:
    with sync_playwright() as p:
        browser = _launch(p)
        context: BrowserContext = browser.new_context(base_url=server.url)
        context.set_default_timeout(DEFAULT_TIMEOUT_MS)
        expect.set_options(timeout=DEFAULT_TIMEOUT_MS)

        def only_local(route: Route) -> None:
            if route.request.url.startswith(server.url + "/"):
                route.continue_()
            else:
                net.aborted.append(route.request.url)
                route.abort()

        context.route("**/*", only_local)
        page = context.new_page()

        def no_system_dialog(dialog: Dialog) -> None:
            net.dialogs.append(f"{dialog.type}: {dialog.message}")
            dialog.dismiss()

        page.on("dialog", no_system_dialog)
        try:
            yield page
        finally:
            context.close()
            browser.close()
        assert net.dialogs == [], f"system dialogs appeared: {net.dialogs}"


def _nav(page: Page, screen: str) -> None:
    page.locator(f'a[data-screen="{screen}"]').click()
    expect(page).to_have_url(re.compile(rf"#/r/[^/]+/{screen}"))
    _no_native_tooltips(page)


def _no_native_tooltips(page: Page) -> None:
    """No element carries a native `title` tooltip; the dashboard has its own."""
    expect(page.locator("[title]")).to_have_count(0)


def _choose(page: Page, selector: str, value: str) -> None:
    """Pick `value` from the dashboard's own dropdown (no native <select> is left)."""
    trigger = page.locator(selector)
    trigger.click()
    listbox = page.get_by_role("listbox")
    expect(listbox).to_be_visible()
    expect(trigger).to_have_attribute("aria-expanded", "true")
    listbox.locator(f'[role="option"][data-value="{value}"]').click()
    expect(listbox).to_have_count(0)
    expect(trigger).to_have_attribute("data-value", value)


def _create_task(page: Page, title: str, body: str) -> str:
    page.locator('[data-test="new-task"]').click()
    _choose(page, '[data-test="step"]', "M01-S01")
    page.locator('[data-test="title"]').fill(title)
    page.locator('textarea[data-test="body"]').fill(body)
    page.locator('[data-test="save"]').click()
    page.wait_for_url(re.compile(r"#/r/[^/]+/backlog/M01-S01-T\d+$"))
    task_id = page.url.rsplit("/", 1)[-1]
    expect(page.locator('[data-test="task-id"]')).to_have_text(task_id)
    return task_id


def _unfold(page: Page, task_id: str) -> None:
    """Unfold the project and step of a task: the tree starts folded (the browser remembers)."""
    parts = task_id.split("-")
    for depth in range(1, len(parts)):
        node = "-".join(parts[:depth])
        toggle = page.locator(f'li.container[data-node="{node}"] > .row [data-test="toggle"]')
        expect(toggle).to_be_visible(timeout=SERVER_TIMEOUT_MS)
        if toggle.get_attribute("aria-expanded") == "false":
            toggle.click()
        expect(toggle).to_have_attribute("aria-expanded", "true")


def _open_task(page: Page, task_id: str) -> None:
    _nav(page, "backlog")
    _unfold(page, task_id)
    page.locator(f'li.task[data-task="{task_id}"] a.task-link').click()
    expect(page.locator('[data-test="task-id"]')).to_have_text(task_id)


def _start_run(page: Page, server: Server, task_id: str, *, commit_first: bool) -> str:
    _open_task(page, task_id)
    page.locator('[data-test="run"]').click()
    dialog = page.locator('[data-test="run-dialog"]')
    expect(dialog).to_be_visible()
    # the run check reads git on the server
    expect(dialog.locator('[data-test="run-loading"]')).to_have_count(0, timeout=SERVER_TIMEOUT_MS)
    not_in_base = dialog.locator('[data-test="not-in-base"]')
    if commit_first:
        expect(not_in_base).to_be_visible()
        dialog.locator('[data-test="commit-backlog"]').click()
        expect(not_in_base).to_have_count(0, timeout=SERVER_TIMEOUT_MS)
    else:
        expect(not_in_base).to_have_count(0)
    expect(dialog.locator('[data-test="unmet-warning"]')).to_have_count(0)
    start = dialog.locator('[data-test="run-start"]')
    expect(start).to_be_enabled(timeout=SERVER_TIMEOUT_MS)
    known = {r["run_id"] for r in task_runs(server.api, task_id)}
    start.click()

    def new_run() -> str | None:
        fresh = [r["run_id"] for r in task_runs(server.api, task_id) if r["run_id"] not in known]
        return str(fresh[0]) if fresh else None

    run_id = wait_for(
        new_run,
        RUN_START_TIMEOUT_S,
        f"run of {task_id} claimed",
        lambda: server.report(task_id),
    )
    # a claimed start opens the run's detail; a `pending` one offers "Otevřít běh" once
    # live updates bring the run
    detail = f"#/r/{server.repo_id}/runs/{run_id}"

    def opened() -> bool | None:
        if page.url.endswith(detail):
            return True
        link = dialog.locator('[data-test="run-result"] a')
        if link.count() and (link.first.get_attribute("href") or "").endswith(detail):
            link.first.click()
            return True
        return None

    wait_for(
        opened,
        SERVER_TIMEOUT_MS / 1000,
        f"run {run_id} opened",
        lambda: f"url={page.url}\n{server.report(task_id)}",
    )
    expect(page.locator('[data-test="task-link"]')).to_have_text(task_id, timeout=SERVER_TIMEOUT_MS)
    return run_id


def _watch_run(page: Page, server: Server, run_id: str, task_id: str) -> None:
    def finished() -> str | None:
        state = str(run_state(server.api, run_id)["state"])
        return state if state != "running" else None

    state = wait_for(
        finished, RUN_TIMEOUT_S, f"run {run_id} finished", lambda: server.report(task_id)
    )
    assert state == "succeeded", f"run {run_id} ended {state}:\n{server.report(task_id)}"
    _nav(page, "runs")
    page.locator('[data-test="refresh"]').click()
    chip = page.locator(f'tr[data-run="{run_id}"] .chip[data-status]')
    try:
        expect(chip).to_have_attribute("data-status", "succeeded", timeout=SERVER_TIMEOUT_MS)
    except AssertionError as exc:
        raise AssertionError(f"{exc}\n{server.report(task_id)}") from exc


def _check_run_detail(page: Page, server: Server, run_id: str, task_id: str) -> None:
    """The run detail opens with no phase panel; the plan phase shows its compiled prompt."""
    page.locator(f'tr[data-run="{run_id}"] a.task-link').click()
    expect(page).to_have_url(re.compile(rf"#/r/[^/]+/runs/{re.escape(run_id)}$"))
    panel = page.locator(".phase-detail")
    expect(panel).to_have_count(0)
    waterfall = page.locator('[data-test="waterfall"]')
    expect(waterfall).to_be_visible()
    expect(page.locator("table.phases")).to_have_count(0)
    expect(waterfall.locator('[data-lane="engineer"]')).to_have_count(1)
    expect(waterfall.locator('[data-lane="agent:planner"]')).to_have_count(1)
    expect(waterfall.locator("button.block").first).to_be_visible()
    block = waterfall.locator('button.block[data-name="plan"]')
    block.click()
    expect(panel).to_be_visible()
    expect(block).to_have_class(re.compile(r"\bselected\b"))
    expect(page).to_have_url(re.compile(rf"#/r/[^/]+/runs/{re.escape(run_id)}/[^/]+$"))
    expect(panel.locator(".dsec-body")).to_have_count(0)
    for section in ("prompts", "gates", "outputs"):
        expect(panel.locator(f'[data-section="{section}"]')).to_have_count(1)
    _no_native_tooltips(page)
    panel.locator('[data-section="prompts"] [data-test="dsec-toggle"]').click()
    prompt_panels = panel.locator('[data-test="prompt-panel"]')
    try:
        expect(prompt_panels.first).to_be_visible(timeout=SERVER_TIMEOUT_MS)
    except AssertionError as exc:
        raise AssertionError(f"{exc}\n{server.report(task_id)}") from exc
    expect(panel.locator(".prompt-body")).to_have_count(0)
    panel.locator('[data-prompt="system"] [data-test="prompt-toggle"]').click()
    expect(panel.locator('[data-prompt="system"] .prompt-body')).to_contain_text(
        "You are the planner."
    )
    _no_native_tooltips(page)
    panel.locator('[data-test="phase-close"]').click()
    expect(panel).to_have_count(0)
    expect(page).to_have_url(re.compile(rf"#/r/[^/]+/runs/{re.escape(run_id)}$"))
    # a click on the block selects the phase, a second click deselects it
    block.click()
    expect(panel).to_be_visible()
    block.click()
    expect(panel).to_have_count(0)
    expect(page).to_have_url(re.compile(rf"#/r/[^/]+/runs/{re.escape(run_id)}$"))


def _approve(page: Page, server: Server, net: Net, task_id: str) -> None:
    _nav(page, "review")
    row = page.locator(f'tr[data-pr="{task_id}"] a.task-link')
    try:
        expect(row).to_be_visible(timeout=SERVER_TIMEOUT_MS)
    except AssertionError as exc:
        raise AssertionError(f"{exc}\n{server.report(task_id)}") from exc
    row.click()
    # the PR opens with every section collapsed; the actions sit above them
    expect(page.locator('[data-test="actions"]')).to_be_visible(timeout=SERVER_TIMEOUT_MS)
    expect(page.locator(".dsec-body")).to_have_count(0)
    expect(page.locator('[data-test="pr-body"]')).to_have_count(0)
    approve = page.locator('[data-test="approve"]')
    expect(approve).to_be_enabled(timeout=SERVER_TIMEOUT_MS)
    _no_native_tooltips(page)
    approve.click()
    modal = page.locator('[data-test="confirm-dialog"]')
    expect(modal).to_be_visible()
    expect(modal).to_contain_text("Schválit a mergovat")
    expect(modal.locator('[data-test="confirm-ok"]')).to_be_focused()
    modal.locator('[data-test="confirm-ok"]').click()
    expect(modal).to_have_count(0)
    assert net.dialogs == [], f"system dialogs appeared: {net.dialogs}"
    notice = page.locator('[data-test="notice"]')
    try:
        expect(notice).to_contain_text("Sloučeno", timeout=SERVER_TIMEOUT_MS)
    except AssertionError as exc:
        raise AssertionError(f"{exc}\n{server.report(task_id)}") from exc


def _task_file(repo: Path, task_id: str) -> str:
    names = git(repo, "ls-tree", "-r", "--name-only", "main", "backlog/").splitlines()
    [path] = [n for n in names if Path(n).name.startswith(f"{task_id}-")]
    return path


def _frontmatter(text: str) -> dict[str, Any]:
    _, head, _ = text.split("---\n", 2)
    data = yaml.safe_load(head)
    assert isinstance(data, dict)
    return data


def _calls(script: Path) -> list[dict[str, Any]]:
    log = script.with_name(script.name + ".calls.jsonl")
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def test_f3_task_lifecycle_in_browser(page: Page, server: Server, net: Net) -> None:
    page.goto(f"/#/r/{server.repo_id}/backlog")
    expect(page.locator("h1")).to_have_text("Backlog")

    # create two tasks and link them
    first = _create_task(page, "First feature", "Zadání prvního tasku.")
    second = _create_task(page, "Second feature", "Zadání druhého tasku.")
    assert (first, second) == (T01, T02)
    page.locator('[data-test="link-input"]').fill(first)
    page.locator('[data-test="link-add"]').click()
    expect(page.locator(f'li[data-dep="{first}"]')).to_be_visible()
    _open_task(page, first)
    expect(page.locator(f'li[data-block="{second}"]')).to_be_visible()

    # run the first task (the backlog is committed from the run dialog), watch it, approve it
    run1 = _start_run(page, server, first, commit_first=True)
    _watch_run(page, server, run1, first)
    _check_run_detail(page, server, run1, first)
    _approve(page, server, net, first)

    # the second task depends on the first one, which is now done in base
    run2 = _start_run(page, server, second, commit_first=False)
    _watch_run(page, server, run2, second)
    _approve(page, server, net, second)

    # the Backlog screen shows both tasks done, in the tree and in the kanban
    _nav(page, "backlog")
    page.locator('[data-test="refresh"]').click()
    for task_id in (first, second):
        _unfold(page, task_id)
        chip = page.locator(f'li.task[data-task="{task_id}"] .chip')
        expect(chip).to_have_attribute("data-state", "done", timeout=SERVER_TIMEOUT_MS)
    page.locator('[data-test="mode-kanban"]').click()
    done = page.locator('section.column[data-column="done"]')
    for task_id in (first, second):
        expect(done.locator(f'a.card[data-card="{task_id}"]')).to_be_visible()

    # base: both tasks are done with a PR line under ## Běhy, and their code is merged
    repo = server.repo
    for task_id in (first, second):
        text = git(repo, "show", f"main:{_task_file(repo, task_id)}")
        assert _frontmatter(text)["status"] == "done", text
        assert "## Běhy" in text and "PR local:" in text, text
    assert git(repo, "show", "main:src/app/first.py") == "FIRST = 1"
    assert git(repo, "show", "main:src/app/second.py") == "SECOND = 2"

    # no terminal: after init, main has only the dashboard's backlog commit and two merges
    subjects = git(repo, "log", "--first-parent", "--format=%s", f"{server.init}..main")
    lines = subjects.splitlines()
    assert len(lines) == 3, subjects
    assert lines[-1].startswith("backlog: "), subjects
    assert all(first in s or second in s for s in lines[:2]), subjects
    assert git(repo, "status", "--porcelain", "--untracked-files=no") == ""

    # no model, no hosting, no network
    calls = _calls(server.script)
    assert [c.get("agent") for c in calls] == ["planner", "planner"], calls
    assert not server.marker.exists(), server.marker.read_text(encoding="utf-8")
    assert net.aborted == [], net.aborted
    assert net.dialogs == []

    # both runs were separate processes; their envelopes and output are private files in
    # the server's HAIFA home, none in the repo
    envelopes = sorted((server.home / "logs").glob("*.json"))
    assert len(envelopes) == 2, envelopes
    if sys.platform != "win32":  # Windows has no POSIX file modes
        for path in [*envelopes, *(server.home / "logs").glob("*.log")]:
            assert stat.S_IMODE(path.stat().st_mode) == 0o600, path
    for path in envelopes:
        assert json.loads(path.read_text(encoding="utf-8"))["ok"] is True, path.read_text()
    tracked = git(repo, "ls-files", "--others", "--cached").splitlines()
    assert not any(Path(name).name in {p.name for p in envelopes} for name in tracked)


def _index(repo: Path, container_id: str) -> Path:
    """The working-tree ``index.md`` of a project or step."""
    for path in (repo / "backlog").rglob("index.md"):
        if _frontmatter(path.read_text(encoding="utf-8")).get("id") == container_id:
            return path
    raise AssertionError(f"no index.md of {container_id}")


def test_project_and_step_from_dashboard(page: Page, server: Server, net: Net) -> None:
    """A project and a step are created on the Backlog screen, the step's workflow is set in
    its Nastavení panel and a task is created in it; nothing is committed."""
    repo = server.repo
    page.goto(f"/#/r/{server.repo_id}/backlog")
    expect(page.locator("h1")).to_have_text("Backlog")

    # a duplicate code is rejected at the form and nothing is written
    page.locator('[data-test="new-project"]').click()
    form = page.locator('[data-test="container-form"]')
    expect(form).to_be_visible()
    form.locator('[data-test="container-id"]').fill("M01")
    form.locator('[data-test="container-title"]').fill("Duplicate")
    form.locator('[data-test="container-save"]').click()
    expect(form.locator('[data-issue="duplicate_id"]')).to_be_visible(timeout=SERVER_TIMEOUT_MS)
    assert git(repo, "status", "--porcelain") == ""

    # the project: its graph opens with the description in Náhled and Zdroj
    form.locator('[data-test="container-id"]').fill("M02")
    form.locator('[data-test="container-title"]').fill("Export")
    form.locator('[data-test="container-body-input"]').fill("Export **dat**.")
    form.locator('[data-test="container-save"]').click()
    page.wait_for_url(re.compile(r"#/r/[^/]+/backlog/graph/M02$"), timeout=SERVER_TIMEOUT_MS)
    expect(page.locator('[data-test="graph-title"]')).to_have_text("Export")
    settings = page.locator('[data-test="container-settings"]')
    expect(settings.locator('[data-test="commit-note"]')).to_contain_text("až po commitu backlogu")
    body = settings.locator('[data-test="container-body"]')
    expect(body.locator('[data-test="md-preview"] strong')).to_have_text("dat")
    body.locator('[data-test="md-tab-source"]').click()
    expect(body.locator('[data-test="md-source"]')).to_contain_text("Export **dat**.")
    _no_native_tooltips(page)

    # the step
    page.locator('[data-test="new-step"]').click()
    page.wait_for_url(re.compile(r"#/r/[^/]+/backlog/new-container/M02$"))
    form.locator('[data-test="container-id"]').fill("M02-S01")
    form.locator('[data-test="container-title"]').fill("Formats")
    form.locator('[data-test="container-save"]').click()
    page.wait_for_url(re.compile(r"#/r/[^/]+/backlog/graph/M02-S01$"), timeout=SERVER_TIMEOUT_MS)
    expect(page.locator('[data-test="graph-title"]')).to_have_text("Formats")
    expect(page.locator('[data-test="new-step"]')).to_have_count(0)

    # the step's workflow: inherited (none), then its own
    row = settings.locator('[data-setting="workflow"]')
    expect(row).to_have_attribute("data-source", "none")
    settings.locator('[data-test="inherit-workflow"]').uncheck()
    _choose(page, '[data-test="edit-workflow"]', "plan-commit")
    settings.locator('[data-test="settings-save"]').click()
    expect(row).to_have_attribute("data-source", "own", timeout=SERVER_TIMEOUT_MS)
    expect(row.locator('[data-test="value-workflow"]')).to_contain_text("plan-commit")
    step_index = _index(repo, "M02-S01")
    assert _frontmatter(step_index.read_text(encoding="utf-8"))["workflow"] == "plan-commit"

    # a task in the new step inherits the workflow
    page.locator('[data-test="new-task"]').click()
    _choose(page, '[data-test="step"]', "M02-S01")
    page.locator('[data-test="title"]').fill("CSV export")
    page.locator('[data-test="save"]').click()
    page.wait_for_url(re.compile(r"#/r/[^/]+/backlog/M02-S01-T01$"), timeout=SERVER_TIMEOUT_MS)
    expect(page.locator('[data-test="task-id"]')).to_have_text("M02-S01-T01")
    assert any(p.name.startswith("M02-S01-T01-") for p in step_index.parent.glob("*.md"))

    # written to the working tree only: no commit, no model, no network
    assert git(repo, "rev-parse", "HEAD") == server.init
    assert _calls(server.script) == []
    assert not server.marker.exists()
    assert net.aborted == [], net.aborted
    assert net.dialogs == []


def _check_report() -> dict[str, Any]:
    """A canned ``factory check`` report: the real online check would call claude and gh."""
    return {
        "in_repo": True,
        "repo": None,
        "state": "pre_library",
        "action": None,
        "sssf_leftover": False,
        "alternate_rosters": False,
        "onboarding": None,
        "base": "main",
        "commit": None,
        "remote": None,
        "ahead": None,
        "behind": None,
        "offline": False,
        "ok": True,
        "counts": {"error": 0, "warning": 1, "info": 0},
        "groups": {},
        "backlog": None,
        "findings": [
            {
                "code": "harness_missing",
                "scope": "machine",
                "severity": "warning",
                "message": "canned finding of the browser test",
                "fix": None,
                "action": None,
            }
        ],
        "checked_at": "2026-10-01T10:00:00+00:00",
        "cached": False,
        "manifest": None,
        "manifest_error": None,
        "version": "0.0.0-test",
    }


def test_add_and_remove_repo_in_browser(
    page: Page, server: Server, net: Net, tmp_path: Path
) -> None:
    """A second repo is added by typing its path (factory from the library is committed on
    its base), its Factory tab checks it on its own, and it is removed again: the removal
    commits the deletion of ``.factory/`` and keeps the backlog."""
    second = make_f3_repo(tmp_path / "second-repo")
    checks: list[str] = []

    def canned_check(route: Route) -> None:
        checks.append(route.request.url)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": True, "data": _check_report(), "error": None, "warnings": []}),
        )

    page.route("**/api/repos/*/factory/check*", canned_check)

    # the folder step: type the path, inspect, add
    page.goto("/#/repos/add")
    field = page.locator('[data-test="add-path"]')
    expect(field).to_have_value("~/")
    field.fill(str(second))
    field.press("Escape")
    page.locator('[data-test="add-inspect"]').click()
    card = page.locator('[data-test="inspect-card"]')
    expect(card).to_be_visible(timeout=SERVER_TIMEOUT_MS)
    expect(card).not_to_have_attribute("data-state", "problem")
    expect(card.locator('[data-test="inspect-root"]')).to_have_text(str(second))
    expect(card.locator('[data-test="inspect-install-note"]')).to_contain_text(
        "commitne to do main"
    )
    page.locator('[data-test="inspect-add"]').click(timeout=SERVER_TIMEOUT_MS)
    expect(page.locator('[data-test="repo-added-install"]')).to_be_visible(
        timeout=SERVER_TIMEOUT_MS
    )
    page.locator('[data-test="repo-added-open"]').click(timeout=SERVER_TIMEOUT_MS)

    # the Factory tab of the new repo runs the check by itself
    expect(page).to_have_url(re.compile(r"#/r/[^/]+/factory$"), timeout=SERVER_TIMEOUT_MS)
    second_id = registered_id(server.home, second)
    assert page.url.endswith(f"#/r/{second_id}/factory")
    expect(page.locator('[data-test="findings-local"]')).to_be_visible(timeout=SERVER_TIMEOUT_MS)
    expect(page.locator('[data-test="findings-local"]')).to_contain_text("canned finding")
    assert checks and all(f"/api/repos/{second_id}/factory/check" in url for url in checks)
    _no_native_tooltips(page)

    assert git(second, "status", "--porcelain") == ""
    installed = git(second, "rev-parse", "HEAD")

    # remove it with the dashboard's own modal: the removal plan, then a commit on base
    page.goto("/#/overview")
    row = page.locator(f'[data-repo="{second_id}"]')
    expect(row).to_be_visible(timeout=SERVER_TIMEOUT_MS)
    row.locator('[data-test="card-remove"], [data-test="calm-remove"]').click()
    dialog = page.locator('[data-test="confirm-dialog"]')
    expect(dialog).to_contain_text(f"Odebrat repozitář {second.name}?")
    expect(dialog).to_contain_text("commitne to do main", timeout=SERVER_TIMEOUT_MS)
    expect(dialog).to_contain_text("Backlog, specifikace a dokumentace v repu zůstanou.")
    expect(dialog.locator('[data-test="removal-blockers"]')).to_have_count(0)
    dialog.locator('[data-test="confirm-ok"]').click()
    expect(row).to_have_count(0, timeout=SERVER_TIMEOUT_MS)
    original = page.locator(f'[data-repo="{server.repo_id}"]')
    expect(original).to_be_visible()

    # unregistered; one more commit deleted .factory/, the backlog stays
    entries = yaml.safe_load((server.home / "dashboard.yaml").read_text(encoding="utf-8"))
    paths = [Path(e["path"]).resolve() for e in entries.get("repos") or []]
    assert second.resolve() not in paths
    assert git(second, "status", "--porcelain") == ""
    assert git(second, "rev-parse", "HEAD~1") == installed
    assert git(second, "ls-tree", "-r", "--name-only", "HEAD", ".factory") == ""
    assert git(second, "ls-tree", "-r", "--name-only", "HEAD", "backlog") != ""
    assert not (second / ".factory").exists()
    assert net.aborted == []
