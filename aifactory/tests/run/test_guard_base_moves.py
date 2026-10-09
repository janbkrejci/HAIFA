"""The run guard and base moves made by factory commands during an agent phase.

The fake harness runs agent effects in-process, where ``HAIFA_RUN_ID`` is the id
of the run under test. ``foreign()`` drops it to stand for a factory command in
another process (the operator's terminal, the dashboard, another run).
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from run_repo import SPEC, T01, Script, commit_all, fake_env, git, make_run_repo, ok, write
from test_auto_continue import T03, build, open_pr, setup_chain

from aifactory.providers import git as pgit
from aifactory.review import approve_task
from aifactory.run import TaskRunRow, TaskRunStore, run_task
from aifactory.run.basemoves import RUN_ENV


@contextlib.contextmanager
def foreign() -> Iterator[None]:
    saved = os.environ.pop(RUN_ENV, None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ[RUN_ENV] = saved


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def _side_commit(repo: Path) -> tuple[str, str]:
    """(main, a descendant of main) — the main checkout stays clean on ``main``."""
    old = git(repo, "rev-parse", "main")
    git(repo, "checkout", "-q", "-b", "side")
    write(repo, "README.md", "readme v2\n")
    write(repo, "docs/news.md", "news\n")
    new = commit_all(repo, "side")
    git(repo, "checkout", "-q", "main")
    return old, new


def _backups(repo: Path, run_id: str) -> list[Path]:
    """Guard backups kept in the session of `run_id` (one per breached phase)."""
    root = repo / ".factory" / "data" / "sessions" / run_id / "guard_backup"
    return sorted(root.iterdir()) if root.is_dir() else []


def _plan(script: Script, effect: Callable[[Path], None]) -> None:
    def plan(wt: Path) -> None:
        effect(wt)
        write(wt, SPEC, "# spec\n")

    script.on("planner", plan)
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add spec"))


def test_factory_move_of_base_is_not_a_breach(repo: Path, script: Script) -> None:
    old, new = _side_commit(repo)

    def move(wt: Path) -> None:
        with foreign():
            pgit.advance_branch(repo, "main", new, old, command="task approve")

    _plan(script, move)
    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert git(repo, "rev-parse", "main") == new
    assert git(repo, "status", "--porcelain") == ""
    assert git(repo, "symbolic-ref", "HEAD") == "refs/heads/main"
    assert _backups(repo, result.run.run_id) == []


def test_agent_move_of_base_is_a_breach(repo: Path, script: Script) -> None:
    old, new = _side_commit(repo)

    def move(wt: Path) -> None:
        pgit.advance_branch(repo, "main", new, old, command="task approve")

    _plan(script, move)
    result = run_task(repo, T01)

    assert result.run.state == "failed"
    assert "main checkout: HEAD" in (result.run.error or "")
    assert _backups(repo, result.run.run_id) != []


def test_factory_move_and_agent_commit_is_a_breach(repo: Path, script: Script) -> None:
    old, new = _side_commit(repo)

    def move(wt: Path) -> None:
        with foreign():
            pgit.advance_branch(repo, "main", new, old)
        git(repo, "commit", "--allow-empty", "-q", "-m", "agent")

    _plan(script, move)
    result = run_task(repo, T01)

    assert result.run.state == "failed"
    assert "main checkout: HEAD" in (result.run.error or "")


def test_factory_move_and_agent_branch_switch_is_a_breach(repo: Path, script: Script) -> None:
    old, new = _side_commit(repo)

    def move(wt: Path) -> None:
        with foreign():
            pgit.advance_branch(repo, "main", new, old)
        git(repo, "checkout", "-q", "-b", "other")

    _plan(script, move)
    result = run_task(repo, T01)

    assert result.run.state == "failed"
    assert "main checkout: HEAD — moved to refs/heads/other" in (result.run.error or "")


def test_files_are_restored_against_the_new_head(repo: Path, script: Script) -> None:
    old, new = _side_commit(repo)

    def move(wt: Path) -> None:
        with foreign():
            pgit.advance_branch(repo, "main", new, old)
        write(repo, "README.md", "hijacked\n")

    _plan(script, move)
    result = run_task(repo, T01)

    assert result.run.state == "failed"
    error = result.run.error or ""
    assert "main checkout: README.md" in error
    assert "main checkout: HEAD" not in error
    assert (repo / "README.md").read_text(encoding="utf-8") == "readme v2\n"
    assert git(repo, "status", "--porcelain") == ""


def _two_runs(repo: Path, script: Script, *, from_agent: bool) -> tuple[TaskRunRow, str]:
    setup_chain(repo)
    build(script, "b")
    run_b = run_task(repo, T03)
    assert run_b.run.state == "succeeded", run_b.run.error
    assert open_pr(repo, T03) is not None

    def approve_b(wt: Path) -> None:
        if from_agent:
            approve_task(repo, T03)
        else:
            with foreign():
                approve_task(repo, T03)
        write(wt, "src/app/a.py", "NAME = 'a'\n")

    script.on("planner", approve_b)
    script.add("planner", ok(artifacts=[], changed_files=["src/app/a.py"], commit_message="Add a"))
    run_a = run_task(repo, T01)
    return run_a.run, run_b.run.branch


def test_approving_another_run_during_a_phase(repo: Path, script: Script) -> None:
    run_a, branch_b = _two_runs(repo, script, from_agent=False)

    assert run_a.state == "succeeded", run_a.error
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        pr_b = store.pr_for_branch(branch_b)
    finally:
        store.close()
    assert pr_b is not None and pr_b.state == "merged"
    assert git(repo, "rev-parse", "main") == pr_b.merge_sha
    assert git(repo, "status", "--porcelain") == ""
    assert git(repo, "symbolic-ref", "HEAD") == "refs/heads/main"
    assert open_pr(repo, T01) is not None


def test_approve_started_by_the_agent_is_a_breach(repo: Path, script: Script) -> None:
    run_a, _ = _two_runs(repo, script, from_agent=True)

    assert run_a.state == "failed"
    assert "main checkout: HEAD" in (run_a.error or "")
