"""The dashboard's background refresh of open task PRs (``web/pr_refresh.py``); no network."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from multi_repo import git, rmtree
from overview_fixture import (
    T_FAIL,
    T_REV,
    dead_pid,
    make_installed_repo,
    make_overview_repo,
    register,
)

from aifactory.repo_settings import RepositorySettings
from aifactory.review import ReviewError, SyncResult
from aifactory.review import sync as review_sync
from aifactory.run.store import TaskChainRow, TaskRunStore
from aifactory.web.backlog import _runtime
from aifactory.web.launcher import Launcher
from aifactory.web.overview import Overview
from aifactory.web.pr_refresh import refresh_registered

REV_BRANCH = f"factory/{T_REV}-r-rev"  # the fixture's open PR of T_REV


@pytest.fixture(name="repo_a")
def repo_a_fixture(tmp_path: Path) -> Iterator[Path]:
    with dead_pid() as pid:
        yield make_overview_repo(tmp_path / "alpha", live_pid=os.getpid(), dead_pid=pid)


@pytest.fixture(name="repo_b")
def repo_b_fixture(tmp_path: Path) -> Iterator[Path]:
    with dead_pid() as pid:
        yield make_overview_repo(tmp_path / "beta", live_pid=os.getpid(), dead_pid=pid, prefix="b-")


def _db(root: Path) -> Path:
    return root / ".factory" / "trace.db"


def test_refreshes_repos_with_a_trace_db_only(
    repo_a: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = make_installed_repo(tmp_path / "plain")
    gone = make_installed_repo(tmp_path / "gone")
    registry = register(tmp_path / "home", repo_a, plain, gone)
    rmtree(gone)
    seen: list[Path] = []

    def fake(root: Path) -> SyncResult:
        seen.append(root)
        return SyncResult(pr=None, created=False, updated=False, warnings=["PR x: gh_failed: y"])

    monkeypatch.setattr(review_sync, "refresh_prs", fake)
    warnings = refresh_registered(registry)

    assert [p.resolve() for p in seen] == [repo_a.resolve()]
    assert warnings == ["alpha: PR x: gh_failed: y"]
    assert not _db(plain).exists()


def test_one_broken_repo_does_not_stop_the_others(
    repo_a: Path, repo_b: Path, tmp_path: Path
) -> None:
    registry = register(tmp_path / "home", repo_a, repo_b)
    seen: list[str] = []

    def fake(root: Path) -> SyncResult:
        if root.name == "alpha":
            raise ReviewError("invalid_config", "broken")
        seen.append(root.name)
        return SyncResult(pr=None, created=False, updated=False)

    warnings = refresh_registered(registry, refresh=fake)

    assert seen == ["beta"]
    assert warnings == ["alpha: invalid_config: broken"]


def test_pr_merged_outside_leaves_review_and_kanban(repo_a: Path, tmp_path: Path) -> None:
    registry = register(tmp_path / "home", repo_a)
    entry = registry.snapshot()[0].repos[0]
    assert [r["task_id"] for r in Overview(registry).repo(entry)["review"]] == [T_REV]
    # provider local: a PR branch contained in base is merged
    git(repo_a, "branch", REV_BRANCH, "main")

    assert refresh_registered(registry) == []

    item = Overview(registry).repo(entry)
    assert item["review"] == []
    assert item["tasks"]["in review"] == 0
    assert [m["task_id"] for m in item["merged_outside"]] == [T_REV]
    assert item["sync_pr"] is None
    assert T_REV not in _runtime(repo_a)[0].in_review


@pytest.mark.parametrize("stop", ["not_merged", "disabled", "failed", "exhausted"])
@pytest.mark.parametrize("auto", [False, True])
@pytest.mark.parametrize("local_on", [False, True])
@pytest.mark.parametrize("merge_on", [False, True])
def test_refresh_resumes_only_a_not_merged_chain_once_via_launcher(
    repo_a: Path, tmp_path: Path, stop: str, auto: bool, local_on: bool, merge_on: bool
) -> None:
    RepositorySettings(repo_a).update({"auto_continue": local_on, "auto_merge": merge_on})
    store = TaskRunStore(_db(repo_a))
    try:
        for run_id in ("r-run", "r-dead"):
            store.finish(run_id, "aborted", None, "stopped")
        store.set_queue_order([T_FAIL])
        store.start_chain(
            TaskChainRow(
                "stopped",
                T_REV,
                None,
                1,
                "finished",
                "0",
                "0",
                stop=stop,
                run_ids='["r-rev"]',
                auto=int(auto),
            )
        )
    finally:
        store.close()
    registry = register(tmp_path / "home", repo_a)
    launcher = Mock(spec=Launcher)
    launcher.start.return_value = None  # claim pending: process continues independently

    def refresh(root: Path) -> SyncResult:
        store = TaskRunStore(_db(root))
        try:
            store.update_pr(REV_BRANCH, state="merged")
        finally:
            store.close()
        # Return the event twice as well: the claim must prevent a duplicate launch.
        return SyncResult(
            pr=None,
            created=False,
            updated=False,
            states=[{"task_id": T_REV, "state": "merged"}],
        )

    assert refresh_registered(registry, refresh=refresh, launcher=launcher) == []
    assert refresh_registered(registry, refresh=refresh, launcher=launcher) == []
    if stop == "not_merged" and local_on:
        launcher.start.assert_called_once_with(
            repo_a, T_FAIL, note=None, force=False, auto=auto, automatic=True
        )
    else:
        launcher.start.assert_not_called()
