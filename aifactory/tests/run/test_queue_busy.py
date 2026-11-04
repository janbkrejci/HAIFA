"""Contention is shared infrastructure trouble, not an unstartable queue item."""

import json
from pathlib import Path
from typing import Any

import pytest
from run_repo import make_run_repo
from test_factory_start import FakeStart
from test_parallel_chain import T01, T02, T03, FakeRunner, no_files, setup_tasks, started

from aifactory import cli
from aifactory.run import STOP_FAILED, TaskRunError, TaskRunRow, run_chain, start_factory


@pytest.mark.parametrize("persistent", [False, True])
def test_factory_start_keeps_locked_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, persistent: bool
) -> None:
    repo = make_run_repo(tmp_path / "repo")
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/")])
    launch = FakeStart(repo)
    attempts: list[str] = []

    def start(task_id: str) -> TaskRunRow | None:
        attempts.append(task_id)
        if persistent or len(attempts) == 1:
            raise TaskRunError("trace_db_locked", "held by another process")
        return launch(task_id)

    monkeypatch.setattr("aifactory.run.queue.time.sleep", lambda _: None)
    result = start_factory(repo, start, max_parallel=1, pr_files=no_files)
    assert attempts == [T01] * (3 if persistent else 2)
    assert launch.calls == ([] if persistent else [T01])
    assert bool(result.skipped) == persistent


@pytest.mark.parametrize("persistent", [False, True])
def test_parallel_chain_waits_for_same_candidate_and_drains_active_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    persistent: bool,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_run_repo(tmp_path / "repo")
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/"), (T03, "src/c/")])
    attempts: list[str] = []

    class BusyRunner(FakeRunner):
        def start(self, task_id: str, **kwargs: Any) -> TaskRunRow:
            attempts.append(task_id)
            if task_id == T02 and (persistent or attempts.count(T02) == 1):
                raise TaskRunError("trace_db_locked", "held by another process")
            return super().start(task_id, **kwargs)

    monkeypatch.setattr("aifactory.run.queue.time.sleep", lambda _: None)
    runner = BusyRunner(repo)
    result = run_chain(repo, T01, max_parallel=3, runner=runner, pr_files=no_files)
    assert not runner.active()
    if persistent:
        assert attempts == [T01, T02, T02, T02]
        assert started(runner) == [T01]
        assert result.stop == STOP_FAILED and not result.ok
        assert [(s.task_id, s.reason) for s in result.waiting] == [(T02, "cannot_start")]
        assert [r.run.task_id for r in result.runs] == [T01]
        monkeypatch.setattr("aifactory.run.run_chain", lambda *args, **kwargs: result)
        capsys.readouterr()
        assert cli.main(["task", "run", T01, "--repo", str(repo), "--json"]) == 2
        envelope = json.loads(capsys.readouterr().out)
        assert not envelope["ok"] and envelope["error"]["code"] == "trace_db_locked"
        assert envelope["data"]["chain"]["stop"] == "failed"
        cli._print_chain(result)
        assert "trace_db_locked" in capsys.readouterr().out
    else:
        assert attempts == [T01, T02, T02, T03]
        assert started(runner) == [T01, T02, T03]
        assert result.ok and result.waiting == []
