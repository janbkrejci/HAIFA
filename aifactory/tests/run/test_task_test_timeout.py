"""The time limit of the ``test`` step: task, ``index.md``, ``config.yaml``, 600 s.

The test steps run a real subprocess (no fake ``CodeRunner``); the limit is read from
the ``timeout_seconds`` of the ``quality:check`` events (the check of ``plan_envelope``)
in ``.factory/trace.db``.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from run_repo import T01, Script, commit_all, fake_env, git, make_run_repo, ok, plan_envelope, write

from aifactory.config import ConfigError
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


OK_CMD = py("print('ok')")


def setup(
    repo: Path,
    *,
    task_timeout: object = None,
    step_timeout: object = None,
    config_timeout: object = None,
    steps: str = "[plan, test_plan, test]",
) -> None:
    """Workflow ``plan-test`` for T01 with the given ``test_timeout`` values, all committed."""
    write(
        repo,
        ".factory/workflows/plan-test.yaml",
        f"name: plan-test\ndescription: Plan the task, then run the suite\n"
        f"steps: {steps}\naccept: test.passed\n",
    )
    config = "base: main\n"
    if config_timeout is not None:
        config += f"test_timeout: {json.dumps(config_timeout)}\n"
    write(repo, ".factory/config.yaml", config)
    step = "---\nid: M01-S01\ntitle: Model\nwrites: [src/app/]\n"
    if step_timeout is not None:
        step += f"test_timeout: {json.dumps(step_timeout)}\n"
    write(repo, STEP_INDEX, step + "---\n\nModel.\n")
    task = f"---\nid: {T01}\ntitle: Schema\nstatus: todo\nworkflow: plan-test\n"
    if task_timeout is not None:
        task += f"test_timeout: {json.dumps(task_timeout)}\n"
    write(repo, TASK_FILE, task + "---\n\n## Zadání\nNavrhnout schéma.\n")
    commit_all(repo, "test setup")


def scripted(script: Script, argv: list[str] = OK_CMD) -> None:
    """The planner's envelope, then a tester plan with the single check ``argv``."""
    script.add("planner", ok())
    script.add("tester", plan_envelope(*argv))


def ran_timeouts(repo: Path, run_id: str) -> list[int]:
    """Rounded ``timeout_seconds`` of the ``quality:check`` events of run ``run_id``, in order."""
    conn = sqlite3.connect(str(repo / ".factory" / "trace.db"))
    try:
        rows = conn.execute(
            "SELECT payload_json FROM events WHERE adw_id = ? AND name = 'quality:check' "
            "ORDER BY rowid",
            (run_id,),
        ).fetchall()
    finally:
        conn.close()
    # the executor passes the remaining share of the limit, a float just under it
    return [round(json.loads(row[0])["timeout_seconds"]) for row in rows]


def test_task_timeout_beats_index_and_config(repo: Path, script: Script) -> None:
    setup(repo, task_timeout=41, step_timeout=42, config_timeout=43)
    scripted(script)

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert ran_timeouts(repo, result.run.run_id) == [41]


def test_index_timeout_beats_config(repo: Path, script: Script) -> None:
    setup(repo, step_timeout=42, config_timeout=43)
    scripted(script)

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert ran_timeouts(repo, result.run.run_id) == [42]


def test_project_index_timeout_is_inherited(repo: Path, script: Script) -> None:
    setup(repo, config_timeout=43)
    write(
        repo,
        "backlog/M01-core/index.md",
        "---\nid: M01\ntitle: Core\nworkflow: plan-commit\ntest_timeout: 44\n---\n\nJádro.\n",
    )
    commit_all(repo, "module timeout")
    scripted(script)

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert ran_timeouts(repo, result.run.run_id) == [44]


def test_config_timeout_beats_default(repo: Path, script: Script) -> None:
    setup(repo, config_timeout=43)
    scripted(script)

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert ran_timeouts(repo, result.run.run_id) == [43]


def test_default_timeout_is_600(repo: Path, script: Script) -> None:
    setup(repo)
    scripted(script)

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert ran_timeouts(repo, result.run.run_id) == [600]


def test_retest_uses_the_same_timeout(repo: Path, script: Script) -> None:
    setup(repo, task_timeout=41, steps="[plan, test_plan, test, {test: {id: retest}}]")
    scripted(script)

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert ran_timeouts(repo, result.run.run_id) == [41, 41]


@pytest.mark.parametrize(
    "code",
    [
        "import time; time.sleep(30)",
        # partial output: TimeoutExpired.stdout is bytes even with text=True
        "import sys, time; print('started', flush=True); "
        "sys.stderr.write('warming up\\n'); sys.stderr.flush(); time.sleep(30)",
    ],
)
def test_exceeded_timeout_fails_the_step(repo: Path, script: Script, code: str) -> None:
    setup(repo, task_timeout=1, step_timeout=600)
    scripted(script, py(code))

    clock = time.monotonic()
    result = run_task(repo, T01)

    assert time.monotonic() - clock < 25
    assert result.run.state == "failed", result.run.error
    assert result.run.error == "accept not met"
    wf = result.workflow_run
    assert wf is not None and wf.accepted is False
    assert wf.results["test"]["passed"] is False
    failure = wf.results["test"]["failures"][0]
    # the executor passes the remaining share of the limit, so the message may say 0.99...s
    assert re.search(r"exceeded the time limit of (1|0\.9\d*)s", failure), failure
    assert "TypeError" not in failure
    if "started" in code:
        assert "started" in failure and "warming up" in failure
    assert ran_timeouts(repo, result.run.run_id) == [1]


@pytest.mark.parametrize(
    ("where", "value"),
    [("task", 0), ("task", "600"), ("task", True), ("step", -5), ("step", 1.5)],
)
def test_invalid_timeout_stops_before_start(
    repo: Path, script: Script, where: str, value: object
) -> None:
    if where == "task":
        setup(repo, task_timeout=value, config_timeout=43)
    else:
        setup(repo, step_timeout=value, config_timeout=43)

    with pytest.raises(TaskRunError) as exc:
        run_task(repo, T01)

    assert exc.value.code == "invalid_test_timeout"
    _assert_not_started(repo, script)


def test_invalid_config_timeout_stops_before_start(repo: Path, script: Script) -> None:
    setup(repo, config_timeout="1800")

    with pytest.raises((TaskRunError, ConfigError)) as exc:
        run_task(repo, T01)

    assert "test_timeout" in str(exc.value)
    _assert_not_started(repo, script)


def _assert_not_started(repo: Path, script: Script) -> None:
    worktrees = repo / ".factory" / "worktrees"
    assert not worktrees.exists() or not any(worktrees.iterdir())
    branches = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/factory/")
    assert branches == ""
    assert script.calls == []


def test_task_run_takes_a_machine_wide_test_slot(
    repo: Path, script: Script, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A task run's test step holds a slot in ``<HAIFA home>/test_slots`` (``test_slots``)."""
    monkeypatch.setenv("HAIFA_HOME", str(tmp_path / "home"))
    setup(repo, config_timeout=43)
    scripted(script)

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    conn = sqlite3.connect(str(repo / ".factory" / "trace.db"))
    try:
        rows = conn.execute(
            "SELECT payload_json FROM events WHERE adw_id = ? AND name = 'test_slot'",
            (result.run.run_id,),
        ).fetchall()
    finally:
        conn.close()
    [acquired] = [json.loads(row[0]) for row in rows]
    assert acquired["state"] == "acquired"
    assert acquired["slot"] == 0
    assert (tmp_path / "home" / "test_slots" / "slot-0.lock").is_file()
