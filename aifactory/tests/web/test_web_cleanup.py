"""Dashboard cleanup is detached from edits, serialized per repo and server-owned."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from backlog_fixture import B1, make_backlog_repo
from starlette.concurrency import run_in_threadpool
from starlette.testclient import TestClient

from aifactory import review
from aifactory.web import app as web_app
from aifactory.web import create_app, create_multi_app, monitoring
from aifactory.web.registry import Registry

BASE = "http://127.0.0.1:4700"


@pytest.mark.parametrize("multi", [False, True])
def test_cancel_returns_while_cleanup_runs_and_skips_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, multi: bool
) -> None:
    repo = make_backlog_repo(tmp_path / "repo")
    registry = Registry(tmp_path / "home")
    entry, _ = registry.add(repo)
    app = create_multi_app(home=registry.home) if multi else create_app(repo)
    prefix = f"/api/repos/{entry.id}" if multi else "/api"
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls: list[Path] = []

    def clean(root: Path) -> None:
        calls.append(root)
        started.set()
        try:
            assert release.wait(10), "test must release the cleanup worker"
        finally:
            finished.set()

    monkeypatch.setattr(review, "clean_worktrees", clean)
    with TestClient(app, base_url=BASE) as client:
        try:
            response = client.post(
                f"{prefix}/backlog/tasks/{B1}/edit", json={"status": "cancelled"}
            )
            assert response.status_code == 200
            assert response.json()["data"]["task"]["board_state"] == "cancelled"
            assert started.wait(5)
            assert not finished.is_set()
            assert not release.is_set()  # response arrived with the worker still blocked
            assert client.get(f"{prefix}/health" if not multi else "/api/health").status_code == 200
            assert client.portal is not None
            client.portal.call(run_in_threadpool, app.state.worktree_cleanup.registered, registry)
            assert calls == [repo]
        finally:
            release.set()


def test_cleanup_failure_is_logged_and_does_not_undo_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    repo = make_backlog_repo(tmp_path / "repo")
    calls: list[Path] = []

    def clean(root: Path) -> None:
        calls.append(root)
        raise RuntimeError("cleanup broke")

    monkeypatch.setattr(review, "clean_worktrees", clean)
    app = create_app(repo)
    with TestClient(app, base_url=BASE) as client:
        response = client.post(f"/api/backlog/tasks/{B1}/edit", json={"status": "cancelled"})
        assert response.status_code == 200
    assert calls == [repo]
    assert "cleanup broke" in caplog.text
    assert str(repo) in caplog.text
    # A failed worker must release exclusion so the next sweep can retry it.
    app.state.worktree_cleanup.clean(repo)
    assert calls == [repo, repo]
    with TestClient(app, base_url=BASE) as client:
        assert (
            client.get(f"/api/backlog/tasks/{B1}").json()["data"]["task"]["status"] == "cancelled"
        )


def test_other_edits_and_rejected_cancel_do_not_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_backlog_repo(tmp_path / "repo")
    calls: list[Path] = []
    monkeypatch.setattr(review, "clean_worktrees", calls.append)
    with TestClient(create_app(repo), base_url=BASE) as client:
        assert (
            client.post(f"/api/backlog/tasks/{B1}/edit", json={"title": "New"}).status_code == 200
        )
        assert (
            client.post("/api/backlog/tasks/missing/edit", json={"status": "cancelled"}).status_code
            != 200
        )
    assert calls == []


def test_periodic_cleanup_starts_without_requests_and_continues_after_repo_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    registry = Registry(tmp_path / "home")
    repos = [tmp_path / "first", tmp_path / "second"]
    for repo in repos:
        repo.mkdir()
        registry.add(repo)
    calls: list[Path] = []
    repeated = threading.Event()
    real_periodic = monitoring.periodic

    def clean(repo: Path) -> None:
        # A running event loop here would mean cleanup blocks the ASGI server.
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        calls.append(repo)
        if repo == repos[0]:
            raise RuntimeError("first repo failed")
        if calls.count(repos[1]) >= 2:
            repeated.set()

    async def periodic(check: Callable[[], object], interval: float) -> None:
        if interval == web_app.WORKTREE_CLEANUP_INTERVAL:
            await real_periodic(check, 0.01)

    async def once(check: Callable[[], object]) -> None:
        pass

    monkeypatch.setattr(review, "clean_worktrees", clean)
    monkeypatch.setattr(monitoring, "periodic", periodic)
    monkeypatch.setattr(monitoring, "once", once)
    with TestClient(create_multi_app(home=registry.home, background_checks=True), base_url=BASE):
        assert repeated.wait(5)
    assert calls[:4] == repos * 2
    assert "first repo failed" in caplog.text
