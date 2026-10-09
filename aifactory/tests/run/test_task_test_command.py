"""The ``test`` step of a task run: task ``test``, ``index.md`` ``test``, ``test_command``.

The test steps run a real subprocess (no fake ``CodeRunner``); the command that ran
is read from the ``quality:test`` events in ``.factory/trace.db``.
"""

from __future__ import annotations

import json
import shlex
import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from run_repo import T01, Script, commit_all, fake_env, git, make_run_repo, ok, write

from aifactory.run import TaskRunError, run_task

STEP_INDEX = "backlog/M01-core/S01-model/index.md"
TASK_FILE = "backlog/M01-core/S01-model/M01-S01-T01-schema.md"


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def py(code: str) -> list[str]:
    """A command that runs ``code`` in this Python."""
    return [sys.executable, "-c", code]


TASK_CMD = py("print('task')")
INDEX_CMD = py("print('index')")
CONFIG_CMD = py("print('config')")


def setup(
    repo: Path,
    *,
    task_test: object = None,
    step_test: object = None,
    config_test: object = None,
    steps: str = "[plan, test]",
) -> None:
    """Workflow ``plan-test`` for T01 with the given ``test`` values, all committed."""
    write(
        repo,
        ".factory/workflows/plan-test.yaml",
        f"name: plan-test\ndescription: Plan the task, then run the suite\n"
        f"steps: {steps}\naccept: test.passed\n",
    )
    config = "base: main\n"
    if config_test is not None:
        config += f"test_command: {json.dumps(config_test)}\n"
    write(repo, ".factory/config.yaml", config)
    step = "---\nid: M01-S01\ntitle: Model\nwrites: [src/app/]\n"
    if step_test is not None:
        step += f"test: {json.dumps(step_test)}\n"
    write(repo, STEP_INDEX, step + "---\n\nModel.\n")
    task = f"---\nid: {T01}\ntitle: Schema\nstatus: todo\nworkflow: plan-test\n"
    if task_test is not None:
        task += f"test: {json.dumps(task_test)}\n"
    write(repo, TASK_FILE, task + "---\n\n## Zadání\nNavrhnout schéma.\n")
    commit_all(repo, "test setup")


def ran_commands(repo: Path, run_id: str) -> list[str]:
    """Commands of the ``quality:test`` events of run ``run_id``, in order."""
    conn = sqlite3.connect(str(repo / ".factory" / "trace.db"))
    try:
        rows = conn.execute(
            "SELECT payload_json FROM events WHERE adw_id = ? AND name = 'quality:test' "
            "ORDER BY rowid",
            (run_id,),
        ).fetchall()
    finally:
        conn.close()
    return [json.loads(row[0])["command"] for row in rows]


def test_task_test_beats_index_and_config(repo: Path, script: Script) -> None:
    setup(
        repo,
        task_test=shlex.join(TASK_CMD),
        step_test=INDEX_CMD,
        config_test=CONFIG_CMD,
    )
    script.add("planner", ok())

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert ran_commands(repo, result.run.run_id) == [shlex.join(TASK_CMD)]


def test_index_test_beats_config(repo: Path, script: Script) -> None:
    setup(repo, step_test=INDEX_CMD, config_test=shlex.join(CONFIG_CMD))
    script.add("planner", ok())

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert ran_commands(repo, result.run.run_id) == [shlex.join(INDEX_CMD)]


def test_module_index_test_is_inherited(repo: Path, script: Script) -> None:
    setup(repo, config_test=CONFIG_CMD)
    write(
        repo,
        "backlog/M01-core/index.md",
        f"---\nid: M01\ntitle: Core\nworkflow: plan-commit\ntest: {json.dumps(INDEX_CMD)}\n"
        "---\n\nJádro.\n",
    )
    commit_all(repo, "module test")
    script.add("planner", ok())

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert ran_commands(repo, result.run.run_id) == [shlex.join(INDEX_CMD)]


def test_config_test_command_beats_default(repo: Path, script: Script) -> None:
    setup(repo, config_test=CONFIG_CMD)
    script.add("planner", ok())

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert ran_commands(repo, result.run.run_id) == [shlex.join(CONFIG_CMD)]


def test_default_is_just_test(repo: Path, script: Script) -> None:
    setup(repo)
    script.add("planner", ok())

    result = run_task(repo, T01)

    assert ran_commands(repo, result.run.run_id) == ["just test"]


def test_nonzero_exit_fails_the_step(repo: Path, script: Script) -> None:
    failing = py("raise SystemExit(3)")
    setup(repo, task_test=failing, config_test=CONFIG_CMD)
    script.add("planner", ok())

    result = run_task(repo, T01)

    assert result.run.state == "failed"
    assert result.run.error == "accept not met"
    wf = result.workflow_run
    assert wf is not None and wf.accepted is False
    assert ran_commands(repo, result.run.run_id) == [shlex.join(failing)]


def test_retest_runs_the_same_command(repo: Path, script: Script) -> None:
    setup(repo, task_test=TASK_CMD, steps="[plan, test, {test: {id: retest}}]")
    script.add("planner", ok())

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert ran_commands(repo, result.run.run_id) == [shlex.join(TASK_CMD)] * 2


@pytest.mark.parametrize("where", ["task", "step"])
def test_invalid_test_stops_before_start(repo: Path, script: Script, where: str) -> None:
    if where == "task":
        setup(repo, task_test=5, config_test=CONFIG_CMD)
    else:
        setup(repo, step_test=[], config_test=CONFIG_CMD)

    with pytest.raises(TaskRunError) as exc:
        run_task(repo, T01)

    assert exc.value.code == "invalid_test"
    worktrees = repo / ".factory" / "worktrees"
    assert not worktrees.exists() or not any(worktrees.iterdir())
    branches = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/factory/")
    assert branches == ""
    assert script.calls == []
