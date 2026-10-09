"""Scenario F2 of `just validate` without running it: the sample backlog and the fake scripts.

The backlog the scenario creates with ``factory task add`` is valid, the fake
builders' edits keep the sandbox suite green in the merge order of the
scenario, and the ``--auto`` script chains the queues of both tasks.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import repo_templates
from cli_json import run_json
from validation import f2_backlog, fake, fake_scripts, sandbox

Capsys = pytest.CaptureFixture[str]
MERGE_ORDER = ("M03-S01-T01", "M04-S01-T01", "M04-S01-T02", "M04-S01-T03", "M03-S01-T02")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    repo_templates.build(path, "validation-sandbox", _build_sandbox)
    return path


def _build_sandbox(path: Path) -> None:
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.name", "Test")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "commit.gpgsign", "false")
    sandbox.materialize(path, "main", "local")
    sandbox.commit_all(path, "sandbox")


def _cli_json(capsys: Capsys, *argv: str) -> tuple[int, dict[str, Any]]:
    capsys.readouterr()
    code, data = run_json(capsys, [*argv, "--json"])
    assert isinstance(data, dict)
    return code, data


def _walk(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        out.append(item)
        out.extend(_walk(item.get("children", [])))
    return out


def _builder_edits(task_id: str) -> list[dict[str, Any]]:
    script = fake_scripts.script_for(task_id, "happy")
    return [e for entry in script["agents"]["builder"] for e in entry["edits"]]


def _suite(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-q"],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_f2_backlog_is_valid(repo: Path, capsys: Capsys) -> None:
    for rel, text in f2_backlog.CONTAINERS.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8", newline="\n")
    for task in f2_backlog.TASKS:
        code, data = _cli_json(capsys, *f2_backlog.add_argv(task), "--repo", str(repo))
        assert code == 0, data
        assert (repo / task.path).is_file(), task.path
    assert set(f2_backlog.TASK_PATHS.values()) == {t.path for t in f2_backlog.TASKS}

    code, data = _cli_json(capsys, "backlog", "check", "--repo", str(repo))
    assert code == 0, data
    assert data["warnings"] == []

    code, data = _cli_json(capsys, "backlog", "list", "--repo", str(repo))
    assert code == 0
    nodes = _walk(data["data"]["items"])
    projects = [n["id"] for n in nodes if n["kind"] == "container" and n["level"] == "project"]
    assert {"M03", "M04"} <= set(projects)
    tasks = {n["id"]: n for n in nodes if n["kind"] == "task" and n["id"] in f2_backlog.ALL}
    assert set(tasks) == set(f2_backlog.ALL)
    for task in f2_backlog.TASKS:
        node = tasks[task.id]
        assert node["status"] == "todo"
        assert node["path"] == task.path
        assert list(node["depends_on"]) == list(task.depends_on)
        assert list(node["writes"]) == list(task.writes)


def test_f2_fake_edits_keep_the_suite_green(repo: Path, tmp_path: Path) -> None:
    branch = tmp_path / "report-branch"
    for task_id in MERGE_ORDER:
        if task_id == "M04-S01-T03":
            # the --auto chain branches T03 off a base without median
            shutil.copytree(repo, branch)
        fake.apply_edits(repo, _builder_edits(task_id))
        proc = _suite(repo)
        assert proc.returncode == 0, (task_id, proc.stderr[-2000:])
    fake.apply_edits(branch, _builder_edits("M04-S01-T03"))
    proc = _suite(branch)
    assert proc.returncode == 0, proc.stderr[-2000:]


def test_f2_auto_script_chains_two_tasks() -> None:
    script = fake_scripts.script_for(f2_backlog.AUTO_START, "auto")
    agents = script["agents"]
    assert script["task"] == f2_backlog.AUTO_START
    assert len(agents["planner"]) == 2
    assert len(agents["documenter"]) == 2
    assert [e["envelope"]["approved"] for e in agents["reviewer"]] == [False, True, False, True]
    builders = agents["builder"]
    assert len(builders) == 4
    for i, task_id in enumerate(f2_backlog.AUTO_CHAIN):
        writes = f2_backlog.BY_ID[task_id].writes
        assert builders[2 * i + 1]["edits"] == [fake_scripts.revise_edit(writes[0])]
        # the fake planner writes where the rendered prompt says (`{{spec_path}}`)
        assert agents["planner"][i]["edits"][0]["path"] == fake.OUTPUT
        assert fake_scripts.TASK_STEMS[task_id] == f"{task_id}-" + f2_backlog.BY_ID[task_id].slug


def test_f2_scripts_revise_the_first_written_file() -> None:
    for task in f2_backlog.TASKS:
        agents = fake_scripts.script_for(task.id, "happy")["agents"]
        assert [e["envelope"]["approved"] for e in agents["reviewer"]] == [False, True]
        assert agents["builder"][-1]["edits"] == [fake_scripts.revise_edit(task.writes[0])]
        assert fake_scripts.TASK_STEMS[task.id] == task.stem
