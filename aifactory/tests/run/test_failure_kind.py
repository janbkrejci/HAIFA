"""A failed run records a typed ``failure_kind`` and ``failure_detail`` in ``task_runs``.

Each kind is produced where it arises: the fake harness (quota, invalid envelope, an
agent's ``status: fail``), the write guard, the workflow's ``accept``, ``task stop`` and
the reaping of a dead run. ``task runs``, ``task show`` and the run API return them.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from run_repo import T01, Script, commit_all, fake_env, make_run_repo, ok, write

from aifactory import failure
from aifactory.cli import main
from aifactory.run import TaskRunRow, TaskRunStore, run_task
from aifactory.run.store import ABORTED, FAILED, STOPPED, SUCCEEDED
from aifactory.web.runs import run_detail
from cli_json import read_envelope

Capsys = pytest.CaptureFixture[str]


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def _store(repo: Path) -> TaskRunStore:
    return TaskRunStore(repo / ".factory" / "trace.db")


def _row(run_id: str, pid: int | None, state: str = "running") -> TaskRunRow:
    return TaskRunRow(
        run_id=run_id,
        task_id=T01,
        branch=f"factory/{T01}-9",
        worktree="/nowhere",
        base="main",
        base_sha="0" * 40,
        head_sha=None,
        state=state,
        started_at="2026-01-01T00:00:00+00:00",
        pid=pid,
    )


def _failed(repo: Path) -> dict[str, Any]:
    result = run_task(repo, T01)
    assert result.run.state == FAILED
    return result.run.to_json()


# -- kinds decided by the fake harness, the envelope and the guard --


def test_quota_from_the_harness(repo: Path, script: Script) -> None:
    def exhausted(wt: Path) -> None:
        raise failure.QuotaExhausted("claude", "You've hit your limit")

    script.on("planner", exhausted)
    script.add("planner", ok())
    data = _failed(repo)
    assert data["failure_kind"] == failure.QUOTA
    detail = data["failure_detail"]
    assert isinstance(detail, dict)
    assert (detail["harness"], detail["message"]) == ("claude", "You've hit your limit")
    # the engine adds the agent and its model (the failure card shows them)
    assert detail["agent"] == "planner"
    assert detail["model"]


def test_invalid_envelope(repo: Path, script: Script) -> None:
    script.add("planner", *([{"status": "maybe"}] * 3))
    data = _failed(repo)
    assert data["failure_kind"] == failure.INVALID_OUTPUT
    detail = data["failure_detail"]
    assert isinstance(detail, dict) and detail["cause"] == "json"


def test_nothing_to_do(repo: Path, script: Script) -> None:
    script.add(
        "planner", {"status": "fail", "summary": "already done", "fail_kind": "nothing_to_do"}
    )
    data = _failed(repo)
    assert data["failure_kind"] == failure.NOTHING_TO_DO
    assert data["failure_detail"] == {
        "agent": "planner",
        "summary": "already done",
        "fail_kind": "nothing_to_do",
    }


def test_agent_fail_without_kind_is_other(repo: Path, script: Script) -> None:
    script.add("planner", {"status": "fail", "summary": "gave up"})
    assert _failed(repo)["failure_kind"] == failure.OTHER


def test_writes_violation_from_the_guard(repo: Path, script: Script) -> None:
    script.on("planner", lambda wt: write(repo, "README.md", "hijacked\n"))
    script.add("planner", ok())
    data = _failed(repo)
    assert data["failure_kind"] == failure.WRITES_VIOLATION
    detail = data["failure_detail"]
    assert isinstance(detail, dict)
    assert detail["agent"] == "planner"
    assert any("README.md" in p for p in detail["problems"])


def test_unexpected_error_is_other(repo: Path, script: Script) -> None:
    def boom(wt: Path) -> None:
        raise RuntimeError("boom")

    script.on("planner", boom)
    script.add("planner", ok())
    data = _failed(repo)
    assert data["failure_kind"] == failure.OTHER
    assert data["failure_detail"] == {"error_type": "RuntimeError"}


def test_accept_not_met(repo: Path, script: Script) -> None:
    write(
        repo,
        ".factory/workflows/plan-commit.yaml",
        "name: plan-commit\ndescription: Plan the task and commit the plan\n"
        "steps: [plan, commit]\naccept: plan.summary == 'approved'\n",
    )
    commit_all(repo, "accept the plan only when approved")
    script.add("planner", ok())
    data = _failed(repo)
    assert data["error"] == (
        "Podmínka accept `plan.summary == 'approved'` nesplněna: plan.summary='done'"
    )
    assert data["failure_kind"] == failure.ACCEPT_NOT_MET
    detail = data["failure_detail"]
    assert isinstance(detail, dict) and detail["accept"] == "plan.summary == 'approved'"
    assert detail["values"] == {"plan.summary": "done"} and detail["rounds"] == []


def test_succeeded_run_has_no_failure(repo: Path, script: Script) -> None:
    script.add("planner", ok())
    data = run_task(repo, T01).run.to_json()
    assert data["state"] == SUCCEEDED
    assert data["failure_kind"] is None and data["failure_detail"] is None


# -- kinds decided by the store: stop, a dead process, a retry, old rows --


def test_stopped_run(repo: Path) -> None:
    store = _store(repo)
    try:
        store.claim(_row("stop0001", None))
        assert store.mark_stopped("stop0001", "stopped by the operator")
        # the dying process does not overwrite the kind
        store.finish("stop0001", FAILED, None, "interrupted", failure.OTHER, {})
        row = store.get("stop0001")
    finally:
        store.close()
    assert row is not None and row.state == STOPPED
    assert row.shown_failure_kind == failure.STOPPED
    assert row.failure_detail_dict() == {"note": "stopped by the operator"}


def test_dead_process_is_process_gone(repo: Path) -> None:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    store = _store(repo)
    try:
        store.claim(_row("dead0001", child.pid))
        assert store.running(T01) is None
        row = store.get("dead0001")
    finally:
        store.close()
    assert row is not None and row.state == ABORTED
    assert row.shown_failure_kind == failure.PROCESS_GONE
    assert row.failure_detail_dict() == {"pid": child.pid}


def test_retry_clears_the_failure(repo: Path) -> None:
    store = _store(repo)
    try:
        store.claim(_row("retr0001", None))
        store.finish("retr0001", FAILED, None, "accept not met", failure.ACCEPT_NOT_MET, {})
        row = store.reclaim("retr0001", 1, {"from": "test"})
    finally:
        store.close()
    assert row.failure_kind is None and row.shown_failure_kind is None


def test_old_failed_run_reads_as_other(repo: Path) -> None:
    store = _store(repo)
    try:
        store.claim(_row("old00001", None))
        store.finish("old00001", FAILED, None, "something")
        store.conn.execute(
            "UPDATE task_runs SET failure_kind = NULL, failure_detail = NULL WHERE run_id = ?",
            ("old00001",),
        )
        row = store.get("old00001")
    finally:
        store.close()
    assert row is not None
    assert row.to_json()["failure_kind"] == failure.OTHER
    assert row.to_json()["failure_detail"] == {}


def test_old_trace_db_gets_the_columns(tmp_path: Path) -> None:
    db = tmp_path / "trace.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE task_runs (run_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, "
        "branch TEXT NOT NULL, worktree TEXT NOT NULL, base TEXT NOT NULL, "
        "base_sha TEXT NOT NULL, head_sha TEXT, state TEXT NOT NULL, started_at TEXT NOT NULL, "
        "ended_at TEXT, pid INTEGER, workflow TEXT, note TEXT, error TEXT)"
    )
    conn.execute(
        "INSERT INTO task_runs (run_id, task_id, branch, worktree, base, base_sha, state, "
        "started_at, error) VALUES ('old1', ?, 'b', '/w', 'main', 'x', 'failed', 't', 'e')",
        (T01,),
    )
    conn.commit()
    conn.close()
    store = TaskRunStore(db)
    try:
        row = store.get("old1")
    finally:
        store.close()
    assert row is not None and row.shown_failure_kind == failure.OTHER


# -- the kind leaves the store through the CLI and the API --


def test_cli_and_api_return_the_kind(repo: Path, script: Script, capsys: Capsys) -> None:
    script.add("planner", {"status": "fail", "summary": "done", "fail_kind": "nothing_to_do"})
    run_id = run_task(repo, T01).run.run_id
    capsys.readouterr()

    assert main(["task", "runs", T01, "--json", "--repo", str(repo)]) == 0
    runs = read_envelope(capsys)["data"]["runs"]
    assert [(r["run_id"], r["failure_kind"]) for r in runs] == [(run_id, "nothing_to_do")]
    assert runs[0]["failure_detail"]["agent"] == "planner"

    assert main(["task", "show", T01, "--json", "--repo", str(repo)]) == 0
    shown = read_envelope(capsys)["data"]["runs"]
    assert shown[0]["failure_kind"] == "nothing_to_do"

    assert main(["task", "runs", T01, "--repo", str(repo)]) == 0
    assert "nothing_to_do" in capsys.readouterr().out

    detail, _ = run_detail(repo, run_id)
    assert detail["run"]["failure_kind"] == "nothing_to_do"
    assert detail["run"]["failure_detail"]["summary"] == "done"
    json.dumps(detail)  # JSON-ready


def test_cli_lists_a_blocked_run_with_its_blockers(repo: Path, capsys: Capsys) -> None:
    store = _store(repo)
    try:
        store.claim(_row("blk", None))
        error = failure.blocked_error(T01, ["M01-TODO-T01"])
        store.finish("blk", FAILED, None, error, failure.BLOCKED, {"blockers": ["M01-TODO-T01"]})
    finally:
        store.close()
    capsys.readouterr()
    assert main(["task", "runs", T01, "--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "blocked" in out and "waits for M01-TODO-T01" in out
    assert main(["task", "show", T01, "--repo", str(repo)]) == 0
    assert "blocked: waits for M01-TODO-T01" in capsys.readouterr().out
