"""``factory task pause|resume``: a run waits at a phase boundary and goes on afterwards."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from run_repo import SPEC, T01, Script, fake_env, make_run_repo, ok, write

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))

from trace_fixture import T1, T2, make_trace_db  # noqa: E402

from aifactory.run import TaskRunError, TaskRunStore, pause_run, resume_run, run_task  # noqa: E402
from aifactory.run import pause as pause_mod  # noqa: E402
from aifactory.run.stop import running_run, stop_run  # noqa: E402
from aifactory.run.store import PAUSED, PAUSING, RUNNING, STOPPED  # noqa: E402
from aifactory.workflow.interpreter import EngineCodeRunner  # noqa: E402
from cli_json import run_json  # noqa: E402

Capsys = pytest.CaptureFixture[str]


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def _db(repo: Path) -> Path:
    return repo / ".factory" / "trace.db"


def _phases(repo: Path, run_id: str) -> list[tuple[str, str]]:
    conn = sqlite3.connect(str(_db(repo)))
    try:
        rows = conn.execute(
            "SELECT name, status FROM phases WHERE adw_id = ? ORDER BY seq, rowid", (run_id,)
        ).fetchall()
    finally:
        conn.close()
    return [(str(n), str(s)) for n, s in rows]


def _pause(repo: Path, run_id: str) -> tuple[str, str | None]:
    store = TaskRunStore(_db(repo))
    try:
        current = store.pause_of(run_id)
        assert current is not None
        return current
    finally:
        store.close()


def _fake_sleep(monkeypatch: pytest.MonkeyPatch, on_sleep: Any) -> list[float]:
    """Replace the gate's sleep (only in ``run.pause``) with `on_sleep`."""
    calls: list[float] = []

    def sleep(seconds: float) -> None:
        calls.append(seconds)
        on_sleep()

    monkeypatch.setattr(pause_mod, "time", SimpleNamespace(sleep=sleep))
    return calls


def _request_pause_in_planner(repo: Path, script: Script, run_ids: list[str]) -> None:
    def plan(wt: Path) -> None:
        write(wt, SPEC, "# spec\n")
        row = running_run(repo, T01)
        assert row is not None
        run_ids.append(row.run_id)
        assert pause_run(repo, row.run_id).pause == PAUSING
        # The phase in progress goes on: still pausing, not paused.
        assert _pause(repo, row.run_id) == (RUNNING, PAUSING)

    script.on("planner", plan)
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add schema spec"))


def test_pause_at_phase_boundary_then_resume_finishes(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_ids: list[str] = []
    seen: list[dict[str, Any]] = []
    _request_pause_in_planner(repo, script, run_ids)

    def while_paused() -> None:
        run_id = run_ids[0]
        store = TaskRunStore(_db(repo))
        try:
            live = [r.run_id for r in store.live_runs()]
            row = store.get(run_id)
        finally:
            store.close()
        assert row is not None
        seen.append(
            {
                "pause": _pause(repo, run_id),
                "phases": _phases(repo, run_id),
                "live": live,
                "shown": row.shown_state,
            }
        )
        resume_run(repo, run_id)

    sleeps = _fake_sleep(monkeypatch, while_paused)

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert len(sleeps) == 1
    paused = seen[0]
    assert paused["pause"] == (RUNNING, PAUSED)
    assert paused["shown"] == PAUSED
    # The plan phase ended, the commit phase did not start yet.
    names = [name for name, _ in paused["phases"]]
    assert "plan" in names and "commit" not in names
    assert all(status != "running" for _, status in paused["phases"])
    # A paused run keeps its place among the live runs (limit and chains).
    assert paused["live"] == run_ids
    assert "commit" in [name for name, _ in _phases(repo, run_ids[0])]
    assert _pause(repo, run_ids[0]) == ("succeeded", None)


class _PauseInCommit(EngineCodeRunner):
    def __init__(self, repo: Path) -> None:
        self.repo = repo

    def commit(self, run: Any, message: str) -> str:
        row = running_run(self.repo, T01)
        assert row is not None
        pause_run(self.repo, row.run_id)
        return super().commit(run, message)


def test_pause_in_last_phase_lets_the_run_finish(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC]))

    def never() -> None:
        raise AssertionError("no phase follows the last one: nothing to wait for")

    _fake_sleep(monkeypatch, never)

    result = run_task(repo, T01, code=_PauseInCommit(repo))

    assert result.run.state == "succeeded", result.run.error
    assert result.run.pause is None


def test_stop_while_paused_ends_the_run_stopped(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_ids: list[str] = []
    _request_pause_in_planner(repo, script, run_ids)

    def stop() -> None:
        # stop_run would signal this very process; mark the run as it does.
        store = TaskRunStore(_db(repo))
        try:
            assert store.mark_stopped(run_ids[0], "stopped by user")
        finally:
            store.close()

    _fake_sleep(monkeypatch, stop)

    result = run_task(repo, T01)

    assert result.run.state == STOPPED
    assert result.run.pause is None
    assert "commit" not in [name for name, _ in _phases(repo, run_ids[0])]


# -- pause_run / resume_run / stop_run over a trace DB fixture ------------------------


@pytest.fixture(name="sleeper")
def sleeper_fixture() -> Iterator[subprocess.Popen[bytes]]:
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    yield proc
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=10)


def _trace_repo(tmp_path: Path, pid: int) -> Path:
    repo = make_trace_db(tmp_path / "trace-repo", os.getpid())
    store = TaskRunStore(_db(repo))
    store.conn.execute("UPDATE task_runs SET pid = ? WHERE run_id = 'r-run'", (pid,))
    store.close()
    return repo


def test_stop_a_paused_run(tmp_path: Path, sleeper: subprocess.Popen[bytes]) -> None:
    repo = _trace_repo(tmp_path, sleeper.pid)
    pause_run(repo, "r-run")
    store = TaskRunStore(_db(repo))
    assert store.enter_pause("r-run") is True
    store.close()

    result = stop_run(repo, "r-run", timeout=5)

    assert result.run.state == STOPPED
    assert result.run.pause is None
    assert result.signalled == [sleeper.pid]
    assert sleeper.wait(timeout=10) is not None


def test_pause_and_resume_errors_change_nothing(tmp_path: Path) -> None:
    repo = _trace_repo(tmp_path, os.getpid())
    with pytest.raises(TaskRunError) as err:
        pause_run(repo, "r-ok")
    assert err.value.code == "run_not_running"
    with pytest.raises(TaskRunError) as err:
        resume_run(repo, "r-run")
    assert err.value.code == "run_not_paused"
    assert _pause(repo, "r-run") == (RUNNING, None)

    pause_run(repo, "r-run")
    with pytest.raises(TaskRunError) as err:
        pause_run(repo, "r-run")
    assert err.value.code == "run_already_paused"
    assert _pause(repo, "r-run") == (RUNNING, PAUSING)
    # A pending pause can be dropped before it takes effect.
    assert resume_run(repo, "r-run").pause is None
    with pytest.raises(TaskRunError) as err:
        resume_run(repo, "nope")
    assert err.value.code == "unknown_run"


def test_cli_pause_resume(tmp_path: Path, capsys: Capsys) -> None:
    repo = _trace_repo(tmp_path, os.getpid())
    capsys.readouterr()
    args = ["--json", "--repo", str(repo)]

    rc, env = run_json(capsys, ["task", "resume", T2, *args])
    assert rc == 2
    assert env["error"]["code"] == "run_not_paused"

    rc, env = run_json(capsys, ["task", "pause", T2, *args])
    assert rc == 0
    assert env["data"]["run"]["pause"] == PAUSING
    assert env["data"]["run"]["state"] == RUNNING

    rc, env = run_json(capsys, ["task", "pause", T2, *args])
    assert rc == 2
    assert env["error"]["code"] == "run_already_paused"

    store = TaskRunStore(_db(repo))
    store.enter_pause("r-run")
    store.close()
    rc, env = run_json(capsys, ["task", "resume", T2, *args])
    assert rc == 0
    assert env["data"]["run"]["pause"] is None

    rc, env = run_json(capsys, ["task", "pause", T1, *args])
    assert rc == 2
    assert env["error"]["code"] == "run_not_running"
    rc, env = run_json(capsys, ["task", "resume", T1, *args])
    assert rc == 2
    assert env["error"]["code"] == "run_not_running"
