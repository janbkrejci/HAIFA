"""Merged PR cleanup uses real local refs and a bare remote; hosting is offline."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from aifactory.backlog import Task, load_backlog
from aifactory.cli import main
from aifactory.config import load_run_config
from aifactory.providers import git as pgit
from aifactory.providers.github import GitHubProvider
from aifactory.review import approve_task, clean_worktrees, flow
from aifactory.review.automerge import _hosting_and_merge
from aifactory.run import TaskPrRow, TaskRunStore, run_task
from aifactory.run.store import RUNNING, _now

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "providers"))

from run_repo import (  # noqa: E402,I001
    T01,
    T02,
    Script,
    commit_all,
    fake_env,
    git,
    make_run_repo,
    ok,
    scripted_plan,
    write,
)
from gh_fake import install_fake_gh, reply  # noqa: E402


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = make_run_repo(tmp_path / "repo")
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(tmp_path / "origin.git"))
    git(root, "remote", "add", "origin", str(tmp_path / "origin.git"))
    git(root, "push", "-q", "-u", "origin", "main")
    return root


def build(script: Script, path: str) -> None:
    script.on("planner", lambda wt: write(wt, path, f"# {path}\n"))
    script.add("planner", ok(artifacts=[path], commit_message=f"Add {path}"))


def assert_gone(repo: Path, branch: str) -> None:
    assert pgit.rev_parse(repo, f"refs/heads/{branch}") is None
    assert pgit.remote_branch_exists(repo, "origin", branch) is False


@pytest.mark.parametrize("hosting", ["local", "github"])
@pytest.mark.parametrize("merged_by", ["operator", "auto-merge"])
def test_approve_deletes_after_restack(
    repo: Path,
    script: Script,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hosting: str,
    merged_by: str,
) -> None:
    provider = None
    if hosting == "github":
        install_fake_gh(
            tmp_path,
            monkeypatch,
            {
                "pr create": reply("https://github.com/o/r/pull/7\n"),
                "pr view": reply({"state": "OPEN", "mergeable": "MERGEABLE"}),
                "pr checks": reply(exit=1, stderr="no checks reported"),
            },
        )
        provider = GitHubProvider(repo, load_run_config(repo).config.settings)
    build(script, "src/app/a.py")
    run = run_task(repo, T01, provider=provider)
    assert run.ok, (run.run.error, run.pr_error)
    branch = run.run.branch
    from aifactory.review import stack

    def restack(*args: object, **kwargs: object) -> list[str]:
        assert pgit.rev_parse(repo, f"refs/heads/{branch}")
        assert pgit.remote_branch_exists(repo, "origin", branch)
        return []

    monkeypatch.setattr(stack, "restack_dependents", restack)
    if merged_by == "auto-merge":
        rc = load_run_config(repo)
        task = load_backlog(repo, rc.config.settings).by_id[T01]
        assert isinstance(task, Task) and run.pr is not None
        outcome = _hosting_and_merge(repo, run.pr, task, provider, rc, repo)
        assert outcome.merged, outcome.reason
        assert outcome.approve is not None
        result = outcome.approve
    else:
        result = approve_task(repo, T01, provider=provider)
    assert result.merged_by == merged_by
    assert result.pr.state == "merged"
    assert result.deleted_branches == [branch, f"origin/{branch}"]
    assert result.to_json()["deleted_branches"] == result.deleted_branches
    assert not result.warnings
    assert_gone(repo, branch)


def test_remote_failure_is_warning_and_clean_retries(
    repo: Path,
    script: Script,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build(script, "src/app/a.py")
    run = run_task(repo, T01)
    real_git = pgit.git

    def rejected(root: Path, *args: str, input: str | None = None) -> str:
        if "--delete" in args:
            raise RuntimeError("protected branch: deletion rejected")
        return real_git(root, *args, input=input)

    with monkeypatch.context() as patch:
        patch.setattr(pgit, "git", rejected)
        result = approve_task(repo, T01)
    assert result.pr.state == "merged"
    assert result.deleted_branches == [run.run.branch]
    assert any("deletion rejected" in warning for warning in result.warnings)
    cleaned = clean_worktrees(repo)
    assert cleaned.deleted_branches == [f"origin/{run.run.branch}"]
    assert not cleaned.warnings
    assert_gone(repo, run.run.branch)


def test_clean_historical_merge_and_idempotence(
    repo: Path,
    script: Script,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build(script, "src/app/a.py")
    run = run_task(repo, T01)
    with monkeypatch.context() as patch:
        patch.setattr(flow, "_delete_merged_branch", lambda *args: None)
        approve_task(repo, T01)
    cleaned = clean_worktrees(repo)
    assert cleaned.deleted_branches == [run.run.branch, f"origin/{run.run.branch}"]
    assert cleaned.to_json()["deleted_branches"] == cleaned.deleted_branches
    assert_gone(repo, run.run.branch)
    assert clean_worktrees(repo).deleted_branches == []


@pytest.mark.parametrize("state", ["open", "closed", "abandoned"])
def test_clean_keeps_other_branches(repo: Path, script: Script, state: str) -> None:
    build(script, "src/app/a.py")
    run = run_task(repo, T01)
    store = TaskRunStore(repo / ".factory/trace.db")
    try:
        if state == "abandoned":
            store.conn.execute("DELETE FROM task_prs")
            store.conn.commit()
        elif state == "closed":
            store.update_pr(run.run.branch, state=state)
    finally:
        store.close()
    assert clean_worktrees(repo).deleted_branches == []
    assert pgit.rev_parse(repo, f"refs/heads/{run.run.branch}")
    assert pgit.remote_branch_exists(repo, "origin", run.run.branch)


def test_successful_restack_releases_parent_before_child_merges(repo: Path, script: Script) -> None:
    write(repo, ".factory/config.yaml", "base: main\ndocs_root: .\nstacked_prs: true\n")
    commit_all(repo, "Enable stacking")
    git(repo, "push", "origin", "main")
    build(script, "src/app/a.py")
    first = run_task(repo, T01)
    build(script, "src/app/b.py")
    second = run_task(repo, T02)
    assert second.run.stacked_on == first.run.branch
    scripted_plan(script)
    merged = approve_task(repo, T01)
    assert not merged.warnings
    assert merged.deleted_branches == [first.run.branch, f"origin/{first.run.branch}"]
    assert_gone(repo, first.run.branch)
    assert clean_worktrees(repo).deleted_branches == []
    approve_task(repo, T02)
    assert_gone(repo, second.run.branch)
    clean_worktrees(repo)
    assert_gone(repo, first.run.branch)
    assert git(repo, "show", "main:src/app/b.py") == "# src/app/b.py"


@pytest.mark.parametrize("checkout", ["main", "worktree", "running"])
def test_clean_preserves_checkout_and_running_branch(
    repo: Path,
    script: Script,
    monkeypatch: pytest.MonkeyPatch,
    checkout: str,
) -> None:
    build(script, "src/app/a.py")
    run = run_task(repo, T01)
    with monkeypatch.context() as patch:
        patch.setattr(flow, "_delete_merged_branch", lambda *args: None)
        approve_task(repo, T01)
    branch = run.run.branch
    if checkout == "main":
        git(repo, "checkout", branch)
    else:
        git(repo, "worktree", "add", run.run.worktree, branch)
    if checkout == "running":
        # Keep the record alive in this process when the store reaps runs.
        import os

        store = TaskRunStore(repo / ".factory/trace.db")
        try:
            store.conn.execute(
                "UPDATE task_runs SET state = 'running', pid = ? WHERE run_id = ?",
                (os.getpid(), run.run.run_id),
            )
            store.conn.commit()
        finally:
            store.close()
    cleaned = clean_worktrees(repo)
    if checkout == "worktree":
        # A completed run's worktree may be removed before deleting its branch.
        assert_gone(repo, branch)
    else:
        assert cleaned.deleted_branches == []
        assert pgit.rev_parse(repo, f"refs/heads/{branch}")
        assert pgit.remote_branch_exists(repo, "origin", branch)
        if checkout == "running":
            assert Path(run.run.worktree).exists()


def test_clean_keeps_unregistered_checkout(
    repo: Path,
    script: Script,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    build(script, "src/app/a.py")
    run = run_task(repo, T01)
    with monkeypatch.context() as patch:
        patch.setattr(flow, "_delete_merged_branch", lambda *args: None)
        approve_task(repo, T01)
    git(repo, "worktree", "add", str(tmp_path / "operator"), run.run.branch)
    assert clean_worktrees(repo).deleted_branches == []
    assert pgit.rev_parse(repo, f"refs/heads/{run.run.branch}")
    assert pgit.remote_branch_exists(repo, "origin", run.run.branch)


@pytest.mark.parametrize("remote", ["absent", "already-deleted", "unreachable"])
def test_cleanup_remote_states(
    repo: Path,
    script: Script,
    monkeypatch: pytest.MonkeyPatch,
    remote: str,
) -> None:
    build(script, "src/app/a.py")
    run = run_task(repo, T01)
    with monkeypatch.context() as patch:
        patch.setattr(flow, "_delete_merged_branch", lambda *args: None)
        approve_task(repo, T01)
    if remote == "absent":
        git(repo, "remote", "remove", "origin")
    elif remote == "already-deleted":
        git(repo, "push", "origin", "--delete", run.run.branch)
    else:
        monkeypatch.setattr(pgit, "remote_branch_exists", lambda *args: None)
    result = clean_worktrees(repo)
    assert result.deleted_branches == [run.run.branch]
    assert bool(result.warnings) == (remote == "unreachable")


def test_failed_restack_preserves_parent(
    repo: Path,
    script: Script,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aifactory.review.errors import ReviewError

    write(repo, ".factory/config.yaml", "base: main\ndocs_root: .\nstacked_prs: true\n")
    commit_all(repo, "Enable stacking")
    git(repo, "push", "origin", "main")
    build(script, "src/app/a.py")
    first = run_task(repo, T01)
    build(script, "src/app/b.py")
    assert run_task(repo, T02).ok

    def cannot_resolve(*args: object, **kwargs: object) -> None:
        raise ReviewError("worktree_failed", "restack refused")

    monkeypatch.setattr(flow, "resolve_task", cannot_resolve)
    # The real restacker records the failure and keeps the dependent PR open.
    result = approve_task(repo, T01)
    assert result.pr.state == "merged"
    assert result.deleted_branches == []
    assert any("restack refused" in warning for warning in result.warnings)
    assert clean_worktrees(repo).deleted_branches == []
    assert pgit.rev_parse(repo, f"refs/heads/{first.run.branch}")
    assert pgit.remote_branch_exists(repo, "origin", first.run.branch)


def test_approve_and_clean_preserve_shared_active_worktree(
    repo: Path,
    script: Script,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build(script, "src/app/a.py")
    completed = run_task(repo, T01)
    assert completed.ok and completed.run.state == "succeeded"
    path = Path(completed.run.worktree)
    original_remove = flow._remove_run_worktrees

    def start_live_run_before_cleanup(ctx: flow._Ctx, branch: str) -> tuple[list[str], list[str]]:
        # Approval already passed its busy check; another run now shares the path.
        ctx.store.claim(
            replace(
                completed.run,
                run_id="live-shared",
                state=RUNNING,
                pid=os.getpid(),
                started_at=_now(),
                ended_at=None,
            )
        )
        rows = ctx.store.runs_on_branch(branch)
        assert len(rows) == 2
        assert {row.state for row in rows} == {"succeeded", RUNNING}
        assert {Path(row.worktree) for row in rows} == {path}
        return original_remove(ctx, branch)

    monkeypatch.setattr(flow, "_remove_run_worktrees", start_live_run_before_cleanup)
    approved = approve_task(repo, T01)
    assert approved.pr.state == "merged"
    assert str(path) not in approved.removed_worktrees
    assert approved.deleted_branches == []
    assert not approved.warnings
    assert path.is_dir()
    assert pgit.rev_parse(repo, f"refs/heads/{completed.run.branch}")
    assert pgit.remote_branch_exists(repo, "origin", completed.run.branch)

    cleaned = clean_worktrees(repo)
    assert not any(Path(item["worktree"]) == path for item in cleaned.removed)
    assert cleaned.deleted_branches == []
    assert not cleaned.warnings
    assert path.is_dir()
    assert pgit.rev_parse(repo, f"refs/heads/{completed.run.branch}")
    assert pgit.remote_branch_exists(repo, "origin", completed.run.branch)


def test_local_failure_is_warning_remote_deletes_and_clean_retries(
    repo: Path,
    script: Script,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build(script, "src/app/a.py")
    run = run_task(repo, T01)
    original_git = pgit.git

    def reject_local(root: Path, *args: str, input: str | None = None) -> str:
        if args[:2] == ("branch", "-D"):
            raise RuntimeError("local deletion refused")
        return original_git(root, *args, input=input)

    with monkeypatch.context() as patch:
        patch.setattr(pgit, "git", reject_local)
        approved = approve_task(repo, T01)
    assert approved.pr.state == "merged"
    assert approved.merge_sha == git(repo, "rev-parse", "main")
    assert approved.deleted_branches == [f"origin/{run.run.branch}"]
    assert any(
        run.run.branch in warning and "local deletion refused" in warning
        for warning in approved.warnings
    )
    assert pgit.rev_parse(repo, f"refs/heads/{run.run.branch}")
    assert pgit.remote_branch_exists(repo, "origin", run.run.branch) is False
    cleaned = clean_worktrees(repo)
    assert cleaned.deleted_branches == [run.run.branch]
    assert not cleaned.warnings
    assert_gone(repo, run.run.branch)


@pytest.mark.parametrize("command", ["approve", "clean"])
@pytest.mark.parametrize("as_json", [False, True], ids=["text", "json"])
@pytest.mark.parametrize("partial", [False, True], ids=["complete", "partial"])
def test_cli_reports_deletions_and_nonfatal_warnings(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    as_json: bool,
    partial: bool,
) -> None:
    import aifactory.review as review

    branch = f"factory/{T01}-1"
    deleted = [branch] if partial else [branch, f"origin/{branch}"]
    warnings = [f"remote branch origin/{branch} not deleted: push rejected"] if partial else []
    pr = TaskPrRow(
        branch=branch,
        task_id=T01,
        provider="local",
        pr_id=branch,
        url=f"local:{branch}",
        base="main",
        base_sha="a" * 40,
        title="Task",
        body="",
        state="merged",
        created_at=_now(),
        updated_at=_now(),
        merge_sha="b" * 40,
    )
    approved = flow.ApproveResult(
        task_id=T01,
        pr=pr,
        merge_sha=pr.merge_sha,
        strategy="squash",
        reviewed=False,
        base_sha=pr.merge_sha,
        deleted_branches=deleted,
        warnings=warnings,
    )
    cleaned = flow.CleanResult(deleted_branches=deleted, warnings=warnings)
    monkeypatch.setattr(review, "approve_task", lambda *args, **kwargs: approved)
    monkeypatch.setattr(review, "clean_worktrees", lambda *args, **kwargs: cleaned)
    argv = ["task", command, *([T01] if command == "approve" else []), "--repo", str(repo)]
    if as_json:
        argv.append("--json")
    assert main(argv) == 0
    output = capsys.readouterr()
    if as_json:
        envelope = json.loads(output.out)
        assert envelope["ok"] is True and envelope["error"] is None
        assert envelope["data"]["deleted_branches"] == deleted
        assert envelope["warnings"] == warnings
        assert "warnings" not in envelope["data"]
        assert output.err == ""
    else:
        for name in deleted:
            assert f"deleted branch {name}" in output.out.splitlines()
        if partial:
            assert f"deleted branch origin/{branch}" not in output.out.splitlines()
        assert output.err.splitlines() == [f"warning: {warning}" for warning in warnings]


def test_rendered_skill_describes_branch_cleanup_and_safety(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--skill"]) == 0
    skill = capsys.readouterr().out
    approve = skill.split("### factory task approve\n", 1)[1].split("\n### ", 1)[0]
    clean = skill.split("### factory task clean\n", 1)[1].split("\n### ", 1)[0]
    assert "After restacking dependents" in approve
    assert "delete the merged branch locally and on the remote" in approve
    for section in (approve, clean):
        for rule in ("open stacked PR", "running run", "checkout", "warnings", "deleted_branches"):
            assert rule in section
    assert "local and remote branches" in clean
    assert "including older merges" in clean
    assert "Keep closed and abandoned branches" in clean
