"""Parts of the parallel chain: ``task_chains``, ``pr_changed_files``, member processes."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from run_repo import Script, commit_all, fake_env, git, make_run_repo, ok, write

from aifactory.cli import main
from aifactory.engine.utils import now_iso
from aifactory.run import TaskPrRow, TaskRunError, TaskRunRow, TaskRunStore
from aifactory.run.gitops import pr_changed_files
from aifactory.run.members import launch_error, member_result, parse_envelope
from aifactory.run.store import TaskChainRow
from cli_json import read_envelope

Capsys = pytest.CaptureFixture[str]
T01, T02 = "M01-S01-T01", "M01-S01-T02"


def _row(chain_id: str, pid: int | None, state: str = "running") -> TaskChainRow:
    now = str(now_iso())
    return TaskChainRow(chain_id, T01, pid, 3, state, now, now)


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


# ── task_chains ──────────────────────────────────────────────────────────────


def test_task_chains_crud_and_reap(tmp_path: Path) -> None:
    store = TaskRunStore(tmp_path / "trace.db")
    try:
        store.start_chain(_row("c1", os.getpid()))
        store.update_chain(
            "c1",
            run_ids=["r1", "r2"],
            skipped=[{"task_id": T02, "reason": "writes_overlap", "detail": "x", "waits_on": []}],
            exclusive=[T01],
        )
        got = store.get_chain("c1")
        assert got is not None
        assert got.run_id_list() == ["r1", "r2"]
        assert got.skipped_list()[0]["reason"] == "writes_overlap"
        assert got.exclusive_list() == [T01]
        assert got.to_json()["run_ids"] == ["r1", "r2"]
        store.update_chain("c1", state="finished", stop="exhausted")
        got = store.get_chain("c1")
        assert got is not None and got.ended_at is not None and got.stop == "exhausted"

        store.start_chain(_row("c2", _dead_pid()))
        chains = {c.chain_id: c for c in store.chains()}
        assert chains["c2"].state == "aborted"
        store.delete_chain("c1")
        assert [c.chain_id for c in store.chains()] == ["c2"]
    finally:
        store.close()


def test_task_chains_schema_is_added_to_an_existing_db(tmp_path: Path) -> None:
    db = tmp_path / "trace.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE task_runs (run_id TEXT PRIMARY KEY, task_id TEXT NOT NULL)")
    conn.close()
    for _ in range(2):  # idempotent
        store = TaskRunStore(db)
        try:
            assert store.chains() == []
        finally:
            store.close()


def test_a_single_run_without_auto_continue_is_not_listed(tmp_path: Path) -> None:
    store = TaskRunStore(tmp_path / "trace.db")
    try:
        for chain_id, stop, runs in (
            ("single", "disabled", ["r1"]),
            ("empty", "disabled", []),
            ("two", "disabled", ["r1", "r2"]),
            ("done", "exhausted", ["r1"]),
        ):
            store.start_chain(_row(chain_id, None, "finished"))
            store.update_chain(chain_id, run_ids=runs, stop=stop)
        store.start_chain(_row("aborted", None, "aborted"))
        assert sorted(c.chain_id for c in store.chains()) == ["aborted", "done", "two"]
    finally:
        store.close()


def test_dismiss_erases_an_ended_chain_only(tmp_path: Path) -> None:
    store = TaskRunStore(tmp_path / "trace.db")
    try:
        store.start_chain(_row("live", os.getpid()))
        store.start_chain(_row("gone", _dead_pid()))
        store.start_chain(_row("old", None, "finished"))
        with pytest.raises(TaskRunError) as info:
            store.dismiss_chain("live")
        assert info.value.code == "chain_running"
        assert store.dismiss_chain("old") is True
        assert store.dismiss_chain("gone") is True  # its process is gone: aborted, ended
        assert store.dismiss_chain("old") is False
        assert [c.chain_id for c in store.chains()] == ["live"]
    finally:
        store.close()


def test_running_chains_come_first(tmp_path: Path) -> None:
    store = TaskRunStore(tmp_path / "trace.db")
    try:
        store.start_chain(_row("old", None, "finished"))
        store.start_chain(_row("live", os.getpid()))
        assert [c.chain_id for c in store.chains(limit=1)] == ["live"]
        assert [c.chain_id for c in store.chains()] == ["live", "old"]
    finally:
        store.close()


# ── pr_changed_files ─────────────────────────────────────────────────────────


def test_pr_changed_files(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "T")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    write(repo, "a.txt", "a\n")
    base_sha = commit_all(repo, "init")
    git(repo, "checkout", "-q", "-b", "factory/X-1")
    write(repo, "src/one.py", "1\n")
    write(repo, "a.txt", "changed\n")
    commit_all(repo, "change")
    git(repo, "checkout", "-q", "main")
    write(repo, "later.txt", "main moves on\n")
    commit_all(repo, "main later")
    assert pr_changed_files(repo, "main", "factory/X-1") == ["a.txt", "src/one.py"]
    assert pr_changed_files(repo, "gone", "factory/X-1", base_sha) == ["a.txt", "src/one.py"]
    assert pr_changed_files(repo, "main", "factory/missing") is None
    assert pr_changed_files(repo, "gone", "factory/X-1") is None


# ── member processes ─────────────────────────────────────────────────────────


def test_parse_envelope_after_narration(tmp_path: Path) -> None:
    assert parse_envelope('{"ok": true}') == {"ok": True}
    assert parse_envelope('narration\n{\n  "ok": false\n}') == {"ok": False}
    assert parse_envelope("nothing") is None
    env = tmp_path / "e.json"
    env.write_text(
        '{"ok": false, "error": {"code": "no_writes", "message": "m"}}',
        encoding="utf-8",
        newline="\n",
    )
    error = launch_error(env, tmp_path / "log", 1, "run X")
    assert error is not None and (error.code, error.message) == ("no_writes", "m")
    env.write_text("garbage", encoding="utf-8", newline="\n")
    (tmp_path / "log").write_text("last words\n", encoding="utf-8", newline="\n")
    error = launch_error(env, tmp_path / "log", 2, "run X")
    assert error is not None and error.code == "internal_error"
    assert "last words" in error.message


def test_member_result_from_envelope_and_store(tmp_path: Path) -> None:
    repo = make_run_repo(tmp_path / "repo")
    store = TaskRunStore(repo / ".factory" / "trace.db")
    now = str(now_iso())
    row = TaskRunRow("r1", T01, "factory/T-1", "wt", "main", "0", None, "running", now, pid=1)
    try:
        store.claim(row)
        store.finish("r1", "succeeded", "abc", None)
        store.claim(TaskRunRow("r2", T01, "factory/T-1", "wt", "main", "0", None, "running", now))
        store.finish("r2", "failed", "abd", "rejected")
        pr = TaskPrRow(
            "factory/T-1", T01, "local", "1", "URL", "main", "0", "t", "", "open", now, now
        )
        store.save_pr(pr)
    finally:
        store.close()
    envelope = {
        "ok": True,
        "data": {
            "run": {"run_id": "r1"},
            "pr_error": None,
            "auto_merge": {"merged": False, "code": "no_review", "reason": "x", "pr_url": "URL"},
            "resolve_run": {"run_id": "r2"},
        },
        "warnings": ["w"],
    }
    result = member_result(repo, T01, row, envelope)
    assert result.ok
    assert result.run.state == "succeeded"
    assert result.pr is not None and result.pr.url == "URL"
    assert result.auto_merge is not None and result.auto_merge.code == "no_review"
    assert result.warnings == ("w",)
    resolved = result.resolve_run
    assert resolved is not None and resolved.run.run_id == "r2" and resolved.run.state == "failed"
    assert resolved.pr is not None and resolved.pr.url == "URL"

    lost = member_result(repo, T02, None, None, "tail", 1)
    assert not lost.ok and lost.run.state == "failed" and "tail" in (lost.run.error or "")


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


def test_member_runs_one_task_only(tmp_path: Path, script: Script, capsys: Capsys) -> None:
    repo = make_run_repo(tmp_path / "repo")
    write(
        repo,
        "backlog/M01-core/S01-model/index.md",
        "---\nid: M01-S01\ntitle: Model\nwrites: [src/app/]\nauto_continue: true\n"
        "auto_merge: true\n---\n",
    )
    write(
        repo,
        "backlog/M01-core/S01-model/M01-S01-T02-loader.md",
        f"---\nid: {T02}\ntitle: Loader\nstatus: todo\n---\n\nLoad.\n",
    )
    commit_all(repo, "auto")
    rel = "src/app/one.py"
    script.on("planner", lambda wt: write(wt, rel, "X = 1\n"))
    script.add("planner", ok(artifacts=[], changed_files=[rel], commit_message="Add"))
    argv = ["task", "run", T01, "--repo", str(repo), "--json", "--member"]
    code = main([*argv, "--started-by=auto-continue"])
    env = read_envelope(capsys)
    assert code == 0, env
    data = env["data"]
    assert data["run"]["task_id"] == T01
    assert data["run"]["started_by"] == "auto-continue"
    assert "chain" not in data
    # plan-commit has no review: the member tried auto-merge and left the PR open
    assert data["auto_merge"]["merged"] is False
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        assert store.for_task(T02) == []
        assert store.chains() == []
    finally:
        store.close()
