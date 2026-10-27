"""Automatic cleanup uses real worktrees and offline workflow/provider fixtures."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from run_repo import T01, T02, Script, fake_env, git, make_run_repo, ok, write

from aifactory.backlog import Task, load_backlog
from aifactory.providers import git as pgit
from aifactory.review import clean_worktrees, flow
from aifactory.run import TaskRunStore, run_task


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def build(script: Script, path: str) -> None:
    script.on("planner", lambda wt: write(wt, path, "content\n"))
    script.add("planner", ok(artifacts=[path], commit_message="Add content"))


def set_status(repo: Path, status: str) -> None:
    task = load_backlog(repo).by_id[T01]
    assert isinstance(task, Task)
    path = repo / task.path
    path.write_text(
        path.read_text(encoding="utf-8").replace("status: todo", f"status: {status}"),
        encoding="utf-8",
    )


def forget_pr(repo: Path, *, running: bool = False, pid: int | None = None) -> None:
    store = TaskRunStore(repo / ".factory/trace.db")
    try:
        store.conn.execute("DELETE FROM task_prs")
        store.conn.execute(
            "UPDATE task_runs SET state = ?, pid = ?",
            ("running" if running else "failed", pid or os.getpid()),
        )
        store.conn.commit()
    finally:
        store.close()


@pytest.mark.parametrize("status", ["cancelled", "done"])
def test_next_run_cleans_terminal_task(repo: Path, script: Script, status: str) -> None:
    build(script, "src/app/first.py")
    first = run_task(repo, T01)
    forget_pr(repo)
    set_status(repo, status)  # main checkout is authoritative, even before commit
    write(Path(first.run.worktree), "uncommitted.txt", "discard terminal task changes")
    orphan = repo / ".factory/worktrees/sync-crashed"
    orphan.mkdir()
    (orphan / "leftover").write_text("partial checkout", encoding="utf-8")

    def before_workflow(wt: Path) -> None:
        assert not Path(first.run.worktree).exists()
        assert not orphan.exists()
        if status == "cancelled":
            assert pgit.rev_parse(repo, f"refs/heads/{first.run.branch}") is None
        write(wt, "src/app/second.py", "second\n")

    script.on("planner", before_workflow)
    script.add("planner", ok(artifacts=["src/app/second.py"], commit_message="Add second"))
    second = run_task(repo, T02, force=True)
    assert second.ok, (second.run.error, second.pr_error)


@pytest.mark.parametrize("kind", ["running", "open", "failed", "stopped"])
def test_next_run_preserves_live_pr_and_retry_worktrees(
    repo: Path, script: Script, kind: str
) -> None:
    build(script, "src/app/first.py")
    first = run_task(repo, T01)
    if kind != "open":
        forget_pr(repo, running=kind == "running")
    if kind == "stopped":
        store = TaskRunStore(repo / ".factory/trace.db")
        store.conn.execute("UPDATE task_runs SET failure_kind = 'stopped'")
        store.conn.commit()
        store.close()
    build(script, "src/app/second.py")
    second = run_task(repo, T02, force=True)
    assert second.ok, (second.run.error, second.pr_error)
    assert Path(first.run.worktree).is_dir()
    assert pgit.rev_parse(repo, f"refs/heads/{first.run.branch}")


def test_running_in_another_process_is_preserved(repo: Path, script: Script) -> None:
    build(script, "src/app/first.py")
    first = run_task(repo, T01)
    with subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE
    ) as process:
        try:
            forget_pr(repo, running=True, pid=process.pid)
            set_status(repo, "cancelled")
            build(script, "src/app/second.py")
            assert run_task(repo, T02, force=True).ok
            assert Path(first.run.worktree).is_dir()
            assert pgit.rev_parse(repo, f"refs/heads/{first.run.branch}")
        finally:
            assert process.stdin is not None
            process.stdin.close()
            process.wait(timeout=10)


def test_cancelled_task_with_open_pr_is_preserved(repo: Path, script: Script) -> None:
    build(script, "src/app/first.py")
    first = run_task(repo, T01)
    set_status(repo, "cancelled")
    assert clean_worktrees(repo).removed == []
    assert Path(first.run.worktree).is_dir()
    assert pgit.rev_parse(repo, f"refs/heads/{first.run.branch}")


def test_latest_failed_return_protects_shared_worktree(repo: Path, script: Script) -> None:
    build(script, "src/app/first.py")
    first = run_task(repo, T01)
    store = TaskRunStore(repo / ".factory/trace.db")
    try:
        store.claim(
            replace(
                first.run, run_id="failed-return", state="running", ended_at=None, pid=os.getpid()
            )
        )
        store.finish("failed-return", "failed", first.run.head_sha, "returned build failed")
        store.update_pr(first.run.branch, state="closed")
    finally:
        store.close()
    cleaned = clean_worktrees(repo)
    assert not cleaned.removed
    assert not cleaned.deleted_branches
    assert Path(first.run.worktree).is_dir()


def test_cleanup_failure_is_warning_and_execution_continues(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    orphan = repo / ".factory/worktrees/sync-locked"
    orphan.mkdir(parents=True)
    original = shutil.rmtree

    def locked(path: str | os.PathLike[str], *args: Any, **kwargs: Any) -> None:
        if Path(path) == orphan:
            raise PermissionError("file locked")
        original(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", locked)
    build(script, "src/app/app.py")
    result = run_task(repo, T01)
    assert result.ok
    assert any("file locked" in warning for warning in result.warnings)
    assert orphan.is_dir()


def test_dirty_older_attempt_is_kept_with_warning(repo: Path, script: Script) -> None:
    build(script, "src/app/first.py")
    first = run_task(repo, T01)
    forget_pr(repo)
    write(Path(first.run.worktree), "uncommitted.txt", "keep me")
    build(script, "src/app/second.py")
    second = run_task(repo, T01)
    assert second.ok
    assert Path(first.run.worktree).is_dir()
    assert any("uncommitted changes" in warning for warning in second.warnings)


def test_closed_pr_branch_cleanup_has_reasons(repo: Path, script: Script) -> None:
    build(script, "src/app/first.py")
    first = run_task(repo, T01)
    store = TaskRunStore(repo / ".factory/trace.db")
    store.update_pr(first.run.branch, state="closed")
    store.close()
    cleaned = clean_worktrees(repo)
    assert cleaned.branch_reasons == {first.run.branch: "closed"}
    assert cleaned.to_json()["branch_reasons"] == cleaned.branch_reasons
    assert cleaned.removed[0]["reason"] == "closed"
    assert not Path(first.run.worktree).exists()
    assert pgit.rev_parse(repo, f"refs/heads/{first.run.branch}") is None


@pytest.mark.parametrize("interruption", [False, True])
def test_post_run_cleanup_after_failure_and_interrupt(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch, interruption: bool
) -> None:
    from aifactory.run import task as task_module

    def interrupted(*args: object, **kwargs: object) -> None:
        set_status(repo, "cancelled")
        if interruption:
            raise KeyboardInterrupt()
        raise RuntimeError("workflow failed")

    monkeypatch.setattr(task_module, "run_workflow", interrupted)
    if interruption:
        with pytest.raises(KeyboardInterrupt):
            run_task(repo, T01)
    else:
        assert not run_task(repo, T01).ok
    store = TaskRunStore(repo / ".factory/trace.db")
    row = store.for_task(T01)[0]
    store.close()
    assert row.state == "failed"
    assert not Path(row.worktree).exists()
    assert pgit.rev_parse(repo, f"refs/heads/{row.branch}") is None


def test_orphan_cleanup_prunes_stale_git_registration(repo: Path) -> None:
    path = repo / ".factory/worktrees/stale"
    git(repo, "worktree", "add", "--detach", str(path))
    shutil.rmtree(path)
    cleaned = clean_worktrees(repo)
    assert not cleaned.warnings
    assert str(path).replace("\\", "/") not in git(repo, "worktree", "list", "--porcelain")


def test_orphan_cleanup_refuses_main_checkout_as_root(repo: Path) -> None:
    ctx = flow._context(repo, None)
    try:
        settings = ctx.rc.config.settings.model_copy(update={"worktrees_dir": "."})
        ctx.rc = replace(ctx.rc, config=replace(ctx.rc.config, settings=settings))
        cleaned = flow._clean(ctx)
        assert any("unsafe worktrees directory" in warning for warning in cleaned.warnings)
        assert (repo / "src/app/__init__.py").is_file()
        assert (repo / ".git").is_dir()
    finally:
        ctx.store.close()
