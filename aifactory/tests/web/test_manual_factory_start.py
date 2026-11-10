"""Overview Play through the real launcher, CLI and claim; scripted harness only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from aifactory.repo_settings import RepositorySettings
from aifactory.web.control import FactoryControl
from aifactory.web.launcher import RunLauncher

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))

from run_repo import commit_all, make_run_repo, write  # noqa: E402
from test_auto_continue import T01, T02, T03, runs_of, setup_chain  # noqa: E402
from test_web_task_run import WORKER, Worker  # noqa: E402
from test_web_task_run import worker_fixture as worker_fixture  # noqa: E402


@pytest.mark.parametrize("auto_continue,failed", [(False, False), (False, True), (True, False)])
def test_play_accepts_manual_batch_and_obeys_continuation_policy(
    tmp_path: Path, worker: Worker, auto_continue: bool, failed: bool
) -> None:
    repo = make_run_repo(tmp_path / "repo")
    setup_chain(repo)
    # Keep T01 and T02 ready and independent; only one initial slot is available.
    write(
        repo,
        "backlog/M01-core/S01-model/M01-S01-T03.md",
        f"---\nid: {T03}\ntitle: Done\nstatus: done\n---\n",
    )
    commit_all(repo, "two ready tasks")
    settings = RepositorySettings(repo)
    settings.update({"auto_continue": auto_continue})
    if failed:
        worker.script.write_text(
            json.dumps(
                {
                    "agents": {
                        "planner": [
                            {
                                "envelope": {
                                    "status": "fail",
                                    "summary": "Scripted failure",
                                }
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
    launcher = RunLauncher(command=WORKER)
    try:
        result = FactoryControl().start(repo, launcher)
        assert [row["task_id"] for row in result["started"]] == [T01], result
        assert result["started"][0]["run_id"] is not None
        assert settings.read().auto_continue is auto_continue
    finally:
        launcher.wait(120)
    assert launcher.running() == []
    (first,) = runs_of(repo, T01)
    assert (first.started_by, first.state, first.attempt) == (
        "manual",
        "failed" if failed else "succeeded",
        1,
    )
    next_runs = runs_of(repo, T02)
    if auto_continue:
        assert [(row.started_by, row.state) for row in next_runs] == [
            ("auto-continue", "succeeded")
        ]
    else:
        assert next_runs == []
        # No slot refill, retry or heal after the initial batch, even on failure.
        assert len(worker.calls()) == 1
    assert settings.read().auto_continue is auto_continue
