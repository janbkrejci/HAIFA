"""``factory backlog sync``, provider ``local``: tasks whose PR was merged outside factory."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from run_repo import SPEC, T01, Script, fake_env, git, make_run_repo, ok, write

from aifactory.cli import main
from aifactory.run import SyncPrRow, TaskPrRow, TaskRunStore, run_task
from cli_json import run_json

Capsys = pytest.CaptureFixture[str]
TASK_FILE = "backlog/M01-core/S01-model/M01-S01-T01-schema.md"
BRANCH = f"factory/{T01}-1"
SYNC = "factory-sync/1"


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def trace_db(repo: Path) -> Path:
    return repo / ".factory" / "trace.db"


def succeed(script: Script, text: str = "# spec\n") -> None:
    script.on("planner", lambda wt: write(wt, SPEC, text))
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add schema spec"))


def stored_pr(repo: Path, branch: str = BRANCH) -> TaskPrRow | None:
    store = TaskRunStore(trace_db(repo))
    try:
        return store.pr_for_branch(branch)
    finally:
        store.close()


def stored_sync(repo: Path, branch: str = SYNC) -> SyncPrRow | None:
    store = TaskRunStore(trace_db(repo))
    try:
        return store.sync_pr_for_branch(branch)
    finally:
        store.close()


def cli_json(capsys: Capsys, *argv: str) -> tuple[int, Any]:
    capsys.readouterr()
    return run_json(capsys, argv)


def sync(capsys: Capsys, repo: Path) -> tuple[int, dict[str, object]]:
    """``backlog sync --json``: the exit code and the envelope's ``data``."""
    code, env = cli_json(capsys, "backlog", "sync", "--json", "--repo", str(repo))
    assert env["ok"] is True, env
    data = env["data"]
    assert isinstance(data, dict) and "ok" not in data and "warnings" not in data
    return code, data


def close_pr(worktree: Path, branch: str = BRANCH) -> None:
    """Provider local: a PR whose branch is gone is closed."""
    git(worktree, "checkout", "-q", "--detach")
    git(worktree, "branch", "-D", branch)


def merge_outside(repo: Path, branch: str = BRANCH) -> None:
    """A merge nobody told factory about (a hosting UI, a manual ``git merge``)."""
    git(repo, "merge", "-q", "--no-ff", "-m", "outside", branch)


def branch_exists(repo: Path, branch: str) -> bool:
    return git(repo, "branch", "--list", branch) != ""


def run_and_merge_outside(repo: Path, script: Script) -> None:
    succeed(script)
    result = run_task(repo, T01)
    assert result.ok, (result.run.error, result.pr_error)
    merge_outside(repo)


def task_ids(data: dict[str, object]) -> list[object]:
    tasks = data["tasks"]
    assert isinstance(tasks, list)
    return [t["task_id"] for t in tasks]


def test_sync_opens_pr_for_outside_merge(repo: Path, script: Script, capsys: Capsys) -> None:
    run_and_merge_outside(repo, script)
    before = git(repo, "rev-parse", "main")

    code, data = sync(capsys, repo)

    assert code == 0, data
    assert data["created"] is True
    assert data["url"] == f"local:{SYNC}"
    assert task_ids(data) == [T01]
    assert git(repo, "rev-parse", "main") == before
    assert "status: done" not in git(repo, "show", f"main:{TASK_FILE}")
    assert git(repo, "status", "--porcelain") == ""
    assert branch_exists(repo, SYNC)
    synced = git(repo, "show", f"{SYNC}:{TASK_FILE}")
    assert "status: done" in synced
    assert f"PR local:{BRANCH}" in synced.split("## Běhy", 1)[1]
    saved = stored_pr(repo)
    assert saved is not None and saved.state == "merged"
    assert git(repo, "log", "-1", "--format=%s", SYNC).startswith("backlog sync:")
    states = data["states"]
    assert isinstance(states, list) and states[0]["state"] == "merged"
    row = stored_sync(repo)
    assert row is not None and row.state == "open" and row.task_ids() == [T01]
    assert f"- {T01} ({TASK_FILE}): PR local:{BRANCH}" in row.body
    assert "sync-check" not in git(repo, "worktree", "list")


def test_sync_skips_branch_that_exists_on_remote(
    repo: Path, script: Script, capsys: Capsys, tmp_path: Path
) -> None:
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, capture_output=True
    )
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "-u", "origin", "main")
    # factory-sync/1 left on the remote by an earlier run: unknown locally and to the DB,
    # on a commit that is not an ancestor of what sync will push
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(origin), str(clone))
    git(clone, "config", "user.email", "t@example.com")
    git(clone, "config", "user.name", "t")
    write(clone, "stale.txt", "old\n")
    git(clone, "add", "stale.txt")
    git(clone, "commit", "-q", "-m", "old sync")
    git(clone, "push", "-q", "origin", "HEAD:refs/heads/factory-sync/1")
    stale = git(origin, "rev-parse", "refs/heads/factory-sync/1")

    run_and_merge_outside(repo, script)
    git(repo, "push", "-q", "origin", "main")
    # only ls-remote can know about factory-sync/1
    assert git(repo, "for-each-ref", "refs/heads/factory-sync/") == ""
    assert git(repo, "for-each-ref", "refs/remotes/origin/factory-sync/") == ""

    code, data = sync(capsys, repo)

    assert code == 0, data
    assert data["created"] is True
    assert branch_exists(repo, "factory-sync/2")
    assert not branch_exists(repo, SYNC)
    assert git(origin, "rev-parse", "refs/heads/factory-sync/1") == stale
    assert git(origin, "rev-parse", "refs/heads/factory-sync/2") == git(
        repo, "rev-parse", "factory-sync/2"
    )
    assert "status: done" in git(repo, "show", f"factory-sync/2:{TASK_FILE}")


def test_sync_pr_merged_then_second_sync_is_noop(
    repo: Path, script: Script, capsys: Capsys
) -> None:
    run_and_merge_outside(repo, script)
    code, data = sync(capsys, repo)
    assert code == 0 and data["created"] is True

    merge_outside(repo, SYNC)
    assert "status: done" in git(repo, "show", f"main:{TASK_FILE}")

    code, data = sync(capsys, repo)
    assert code == 0, data
    assert data["pr"] is None
    assert data["tasks"] == []
    assert data["skipped"] == []
    assert not branch_exists(repo, "factory-sync/2")
    row = stored_sync(repo)
    assert row is not None and row.state == "merged"


def test_sync_closed_pr_does_not_change_task(repo: Path, script: Script, capsys: Capsys) -> None:
    succeed(script)
    run = run_task(repo, T01)
    close_pr(Path(run.run.worktree))

    code, data = sync(capsys, repo)

    assert code == 0, data
    assert data["pr"] is None
    states = data["states"]
    assert isinstance(states, list)
    assert {"task_id": T01, "branch": BRANCH, "url": f"local:{BRANCH}", "state": "closed"} in (
        states
    )
    saved = stored_pr(repo)
    assert saved is not None and saved.state == "closed"
    assert "status: done" not in git(repo, "show", f"main:{TASK_FILE}")
    assert git(repo, "branch", "--list", "factory-sync/*") == ""


def test_sync_nothing_to_do(repo: Path, capsys: Capsys) -> None:
    code, data = sync(capsys, repo)
    assert code == 0
    assert data["pr"] is None and data["url"] is None

    capsys.readouterr()
    assert main(["backlog", "sync", "--repo", str(repo)]) == 0
    assert "nothing to sync" in capsys.readouterr().out
    assert git(repo, "branch", "--list", "factory-sync/*") == ""


def test_sync_reuses_open_sync_pr(repo: Path, script: Script, capsys: Capsys) -> None:
    run_and_merge_outside(repo, script)
    code, data = sync(capsys, repo)
    assert code == 0 and data["created"] is True
    tip = git(repo, "rev-parse", SYNC)

    code, data = sync(capsys, repo)

    assert code == 0, data
    assert data["created"] is False
    assert data["updated"] is False
    pr = data["pr"]
    assert isinstance(pr, dict) and pr["branch"] == SYNC
    assert task_ids(data) == [T01]
    assert not branch_exists(repo, "factory-sync/2")
    assert git(repo, "rev-parse", SYNC) == tip

    capsys.readouterr()
    assert main(["backlog", "sync", "--repo", str(repo)]) == 0
    assert f"sync PR local:{SYNC} already open" in capsys.readouterr().out


def test_sync_text_output(repo: Path, script: Script, capsys: Capsys) -> None:
    run_and_merge_outside(repo, script)
    capsys.readouterr()
    assert main(["backlog", "sync", "--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert f"opened local:{SYNC}: done for {T01}" in out
    assert f"PR local:{BRANCH} of {T01} is merged" in out


def test_sync_after_approve_is_noop(repo: Path, script: Script, capsys: Capsys) -> None:
    from aifactory.review import approve_task

    succeed(script)
    run_task(repo, T01)
    approve_task(repo, T01)

    code, data = sync(capsys, repo)
    assert code == 0, data
    assert data["pr"] is None
    assert data["tasks"] == []


def test_store_sync_prs(tmp_path: Path) -> None:
    store = TaskRunStore(tmp_path / "trace.db")
    try:
        row = SyncPrRow(
            branch=SYNC,
            provider="local",
            pr_id=SYNC,
            url=f"local:{SYNC}",
            base="main",
            base_sha="a" * 40,
            title="backlog sync: done for 1 task(s)",
            body="body",
            state="open",
            tasks=json.dumps([T01]),
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
        )
        store.save_sync_pr(row)
        assert store.sync_pr_for_branch(SYNC) == row
        assert store.open_sync_prs() == [row]
        assert store.sync_branches() == [SYNC]
        assert row.task_ids() == [T01]
        assert row.to_json()["tasks"] == [T01]
        assert store.open_prs() == []  # a sync PR is not a task PR

        store.update_sync_pr(SYNC, state="merged")
        merged = store.sync_pr_for_branch(SYNC)
        assert merged is not None and merged.state == "merged"
        assert merged.updated_at != row.updated_at
        assert store.open_sync_prs() == []
        with pytest.raises(ValueError):
            store.update_sync_pr(SYNC, nope=1)
    finally:
        store.close()


def test_sync_help(capsys: Capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["backlog", "sync", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "base" in out
    assert "factory-sync" in out
