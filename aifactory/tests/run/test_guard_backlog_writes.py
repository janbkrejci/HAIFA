"""The run guard and backlog writes made through the factory during an agent phase.

Like ``test_guard_base_moves``: the fake harness runs agent effects in-process with
``HAIFA_RUN_ID`` of the run under test; ``foreign()`` stands for a factory command
of another process (the operator's terminal, the dashboard).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from run_repo import SPEC, T01, T02, Script, fake_env, git, make_run_repo, ok, write
from starlette.testclient import TestClient
from test_guard_base_moves import foreign

from aifactory.backlog import add_task, commit_backlog, edit_task, set_auto_continue
from aifactory.cli import main
from aifactory.run import run_task
from aifactory.web import create_app

STEP = "M01-S01"
T02_PATH = "backlog/M01-core/S01-model/M01-S01-T02-loader.md"
NEW_PATH = "backlog/M01-core/S01-model/M01-S01-T03-novy-task.md"
STEP_INDEX = "backlog/M01-core/S01-model/index.md"


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def _plan(script: Script, effect: Callable[[Path], None]) -> None:
    def plan(wt: Path) -> None:
        effect(wt)
        write(wt, SPEC, "# spec\n")

    script.on("planner", plan)
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add spec"))


def _operator_edits(repo: Path) -> None:
    add_task(repo, STEP, "Nový task")
    edit_task(repo, T02, title="Loader v2")


def test_factory_backlog_write_is_not_a_breach(repo: Path, script: Script) -> None:
    def effect(wt: Path) -> None:
        with foreign():
            _operator_edits(repo)

    _plan(script, effect)
    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert "title: Nový task" in (repo / NEW_PATH).read_text(encoding="utf-8")
    assert "title: Loader v2" in (repo / T02_PATH).read_text(encoding="utf-8")
    status = git(repo, "status", "--porcelain", "--", "backlog")
    assert NEW_PATH in status and T02_PATH in status


def test_factory_write_started_by_the_agent_is_a_breach(repo: Path, script: Script) -> None:
    _plan(script, lambda wt: _operator_edits(repo))
    result = run_task(repo, T01)

    assert result.run.state == "failed"
    error = result.run.error or ""
    assert f"main checkout: {NEW_PATH}" in error
    assert f"main checkout: {T02_PATH}" in error
    assert not (repo / NEW_PATH).exists()
    assert "title: Loader\n" in (repo / T02_PATH).read_text(encoding="utf-8")
    assert git(repo, "status", "--porcelain") == ""


def test_agent_write_after_factory_write_keeps_factory_content(repo: Path, script: Script) -> None:
    def effect(wt: Path) -> None:
        with foreign():
            edit_task(repo, T02, title="Loader v2")
        write(repo, T02_PATH, "hijacked\n")

    _plan(script, effect)
    result = run_task(repo, T01)

    assert result.run.state == "failed"
    error = result.run.error or ""
    assert f"main checkout: {T02_PATH} — restored to the factory write" in error
    assert "title: Loader v2" in (repo / T02_PATH).read_text(encoding="utf-8")


def test_agent_write_before_factory_write_is_reported(repo: Path, script: Script) -> None:
    def effect(wt: Path) -> None:
        text = (repo / T02_PATH).read_text(encoding="utf-8").replace("Načíst data.", "Agent.")
        write(repo, T02_PATH, text)
        with foreign():
            edit_task(repo, T02, title="Loader v2")

    _plan(script, effect)
    result = run_task(repo, T01)

    assert result.run.state == "failed"
    error = result.run.error or ""
    assert f"{T02_PATH} — changed by the agent before a factory write" in error
    text = (repo / T02_PATH).read_text(encoding="utf-8")
    assert "title: Loader v2" in text and "Agent." in text


def test_other_main_checkout_change_is_still_a_breach(repo: Path, script: Script) -> None:
    def effect(wt: Path) -> None:
        with foreign():
            add_task(repo, STEP, "Nový task")
        write(repo, "README.md", "hijacked\n")

    _plan(script, effect)
    result = run_task(repo, T01)

    assert result.run.state == "failed"
    error = result.run.error or ""
    assert "main checkout: README.md — rolled back" in error
    assert NEW_PATH not in error
    assert (repo / "README.md").read_text(encoding="utf-8") == "readme\n"
    assert (repo / NEW_PATH).is_file()


def test_add_and_commit_backlog_during_phase(repo: Path, script: Script) -> None:
    def effect(wt: Path) -> None:
        with foreign():
            add_task(repo, STEP, "Nový task")
            assert commit_backlog(repo).committed

    _plan(script, effect)
    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert git(repo, "cat-file", "-t", f"main:{NEW_PATH}") == "blob"
    assert git(repo, "status", "--porcelain") == ""
    assert git(repo, "symbolic-ref", "HEAD") == "refs/heads/main"


def test_auto_continue_during_phase(repo: Path, script: Script) -> None:
    def effect(wt: Path) -> None:
        with foreign():
            set_auto_continue(repo, STEP, True)

    _plan(script, effect)
    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert "auto_continue: true" in (repo / STEP_INDEX).read_text(encoding="utf-8")


def test_cli_and_dashboard_writes_during_phase(repo: Path, script: Script, tmp_path: Path) -> None:
    def effect(wt: Path) -> None:
        with foreign():
            assert main(["task", "add", STEP, "Nový task", "--repo", str(repo)]) == 0
            assert main(["task", "link", T02, "--related", T01, "--repo", str(repo)]) == 0
            app = create_app(repo, static_dir=tmp_path / "nostatic")
            client = TestClient(app, base_url="http://127.0.0.1:4700")
            url = f"/api/backlog/containers/{STEP}/auto-continue"
            assert client.post(url, json={"mode": "on"}).status_code == 200
            url = f"/api/backlog/tasks/{T02}/edit"
            assert client.post(url, json={"title": "Loader v2"}).status_code == 200

    _plan(script, effect)
    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert (repo / NEW_PATH).is_file()
    text = (repo / T02_PATH).read_text(encoding="utf-8")
    assert "title: Loader v2" in text and T01 in text.split("related")[1]
    assert "auto_continue: true" in (repo / STEP_INDEX).read_text(encoding="utf-8")
