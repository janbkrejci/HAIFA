"""The Overview's factory controls: ``POST /api/repos/{id}/control/start|pause|resume|stop``.

A fake launcher claims a `running` row with a live pid in the real trace DB; a fake stop
blocks on an event, so the stop's progress can be seen in ``GET /api/overview``.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from multi_repo import BASE, commit_all, write
from overview_fixture import make_installed_repo, register
from starlette.testclient import TestClient
from thread_launcher import ThreadLauncher

from aifactory.engine.utils import now_iso
from aifactory.run.errors import TaskRunError
from aifactory.run.store import TaskChainRow, TaskRunRow, TaskRunStore
from aifactory.skill import envelope_problems
from aifactory.web import create_app, create_multi_app
from aifactory.web.control import KEEP_SECONDS, FactoryControl

STEP = "backlog/M01-core/S01-model"
T1, T2, T3 = "M01-S01-T01", "M01-S01-T02", "M01-S01-T03"


def _db(root: Path) -> Path:
    return root / ".factory" / "trace.db"


def _row(task_id: str) -> TaskRunRow:
    return TaskRunRow(
        run_id=f"r-{task_id}",
        task_id=task_id,
        branch=f"factory/{task_id}-1",
        worktree="wt",
        base="main",
        base_sha="0",
        head_sha=None,
        state="running",
        started_at=str(now_iso()),
        pid=os.getpid(),
    )


def claim(root: Path, task_id: str) -> TaskRunRow:
    row = _row(task_id)
    store = TaskRunStore(_db(root))
    try:
        store.claim(row)
    finally:
        store.close()
    return row


class FakeLauncher(ThreadLauncher):
    """Claims a running row for every started task; records the calls."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str | None, bool, bool]] = []

    def start(
        self,
        repo: Path,
        task_id: str,
        *,
        note: str | None,
        force: bool,
        harness: str | None = None,
        model: str | None = None,
        thinking: str | None = None,
        auto: bool = False,
        timeout: float = 30.0,
    ) -> TaskRunRow | None:
        self.calls.append((task_id, note, force, auto))
        return claim(repo, task_id)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    """Three ready tasks with separate writes, two parallel slots."""
    root = make_installed_repo(
        tmp_path / "alpha", config="base: main\ndocs_root: .\nmax_parallel_runs: 2\n"
    )
    shutil.rmtree(root / STEP)
    write(root, f"{STEP}/index.md", "---\nid: M01-S01\ntitle: Model\n---\n")
    for task_id, writes in ((T1, "src/a/"), (T2, "src/b/"), (T3, "src/c/")):
        write(
            root,
            f"{STEP}/{task_id}.md",
            f"---\nid: {task_id}\ntitle: Task {task_id}\nstatus: todo\nwrites: [{writes}]\n---\n",
        )
    commit_all(root, "three tasks")
    return root


def _app(
    tmp_path: Path, repo: Path, launcher: FakeLauncher, control: FactoryControl | None = None
) -> TestClient:
    home = tmp_path / "home"
    register(home, repo)
    app = create_multi_app(home=home, static_dir=tmp_path / "nostatic", launcher=launcher)
    if control is not None:
        app.state.control = control
        app.state.overview.control = control
    return TestClient(app, base_url=BASE)


def _post(client: TestClient, path: str, status: int = 200) -> dict[str, Any]:
    response = client.post(f"/api/repos/alpha/control/{path}", json={})
    body: dict[str, Any] = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    return body


def _factory(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/overview")
    assert response.status_code == 200
    factory: dict[str, Any] = response.json()["data"]["repos"][0]["factory"]
    return factory


def _pauses(root: Path) -> dict[str, str | None]:
    store = TaskRunStore(_db(root))
    try:
        return {r.task_id: r.pause for r in store.live_runs()}
    finally:
        store.close()


def test_start_fills_the_free_slots_in_queue_order(repo: Path, tmp_path: Path) -> None:
    launcher = FakeLauncher()
    client = _app(tmp_path, repo, launcher)
    assert _factory(client)["can_start"] is True
    data = _post(client, "start")["data"]
    assert launcher.calls == [(T1, None, False, False), (T2, None, False, False)]
    assert data["started"] == [
        {"task_id": T1, "run_id": f"r-{T1}"},
        {"task_id": T2, "run_id": f"r-{T2}"},
    ]
    assert (data["max_parallel_runs"], data["running"], data["free_slots"]) == (2, 0, 2)
    factory = _factory(client)
    assert (factory["running"], factory["free_slots"], factory["can_start"]) == (2, 0, False)

    again = _post(client, "start")["data"]
    assert again["started"] == [] and again["free_slots"] == 0
    assert len(launcher.calls) == 2


def test_start_rejects_unknown_fields(repo: Path, tmp_path: Path) -> None:
    client = _app(tmp_path, repo, FakeLauncher())
    response = client.post("/api/repos/alpha/control/start", json={"auto": True})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "usage_error"


def test_start_with_an_invalid_config_is_an_error(repo: Path, tmp_path: Path) -> None:
    write(repo, ".factory/config.yaml", "base: main\nmax_parallel_runs: nope\n")
    commit_all(repo, "broken")
    launcher = FakeLauncher()
    client = _app(tmp_path, repo, launcher)
    body = _post(client, "start", 500)
    assert body["error"]["code"] == "invalid_config"
    assert launcher.calls == []


def test_pause_and_resume_every_running_run(repo: Path, tmp_path: Path) -> None:
    claim(repo, T1)
    claim(repo, T2)
    claim(repo, T3)
    store = TaskRunStore(_db(repo))
    try:
        store.request_pause(f"r-{T3}")
        store.enter_pause(f"r-{T3}")
    finally:
        store.close()
    client = _app(tmp_path, repo, FakeLauncher())
    data = _post(client, "pause")["data"]
    assert sorted(data["run_ids"]) == [f"r-{T1}", f"r-{T2}"]
    assert data["errors"] == []
    assert _pauses(repo) == {T1: "pausing", T2: "pausing", T3: "paused"}
    factory = _factory(client)
    assert (factory["pausing"], factory["paused"]) == (2, 1)
    control = factory["control"]
    assert control["action"] == "pause"
    assert sorted(control["run_ids"]) == [f"r-{T1}", f"r-{T2}", f"r-{T3}"]

    resumed = _post(client, "resume")["data"]
    assert sorted(resumed["run_ids"]) == [f"r-{T1}", f"r-{T2}", f"r-{T3}"]
    assert _pauses(repo) == {T1: None, T2: None, T3: None}
    assert _factory(client)["control"] is None


def _finish(root: Path, task_id: str) -> None:
    store = TaskRunStore(_db(root))
    try:
        store.finish(f"r-{task_id}", "succeeded", None, None)
    finally:
        store.close()


def _chain(root: Path, state: str = "running") -> None:
    now = str(now_iso())
    store = TaskRunStore(_db(root))
    try:
        store.start_chain(TaskChainRow("c1", T1, os.getpid(), 2, state, now, now))
    finally:
        store.close()


def test_pause_holds_a_run_a_chain_starts_after_it(repo: Path, tmp_path: Path) -> None:
    """A run paused in its last phase ends; the run its chain starts next is paused too."""
    claim(repo, T1)
    _chain(repo)
    control = FactoryControl(hold_poll=None)
    client = _app(tmp_path, repo, FakeLauncher(), control)
    assert _post(client, "pause")["data"]["run_ids"] == [f"r-{T1}"]

    _finish(repo, T1)  # the last phase ended: the pause had nothing to hold
    assert _factory(client)["control"] is None  # no run of the pause runs
    claim(repo, T2)  # the chain goes on
    assert control.hold(repo) == [f"r-{T2}"]
    assert _pauses(repo) == {T2: "pausing"}
    factory = _factory(client)
    assert factory["pausing"] == 1
    assert factory["control"]["run_ids"] == [f"r-{T1}", f"r-{T2}"]
    assert control.hold(repo) == []  # already pausing: asked once

    _post(client, "resume")
    assert _pauses(repo) == {T2: None}
    claim(repo, T3)
    assert control.hold(repo) == []  # no pause any more
    assert _pauses(repo) == {T2: None, T3: None}


def test_pause_ends_when_its_runs_and_the_chains_ended(repo: Path, tmp_path: Path) -> None:
    claim(repo, T1)
    control = FactoryControl(hold_poll=None)
    client = _app(tmp_path, repo, FakeLauncher(), control)
    _post(client, "pause")
    _finish(repo, T1)
    assert control.hold(repo) == []  # no chain runs: the pause is over
    claim(repo, T2)
    assert control.hold(repo) == []
    assert _pauses(repo) == {T2: None}


def test_pause_watcher_pauses_late_runs(repo: Path, tmp_path: Path) -> None:
    claim(repo, T1)
    control = FactoryControl(hold_poll=0.02)
    client = _app(tmp_path, repo, FakeLauncher(), control)
    _post(client, "pause")
    claim(repo, T2)
    deadline = time.monotonic() + 10
    while _pauses(repo)[T2] is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert _pauses(repo) == {T1: "pausing", T2: "pausing"}
    _post(client, "stop", 202)
    control.wait(10)


def test_stop_progress_is_shown_until_every_run_ended(repo: Path, tmp_path: Path) -> None:
    claim(repo, T1)
    claim(repo, T2)
    release = threading.Event()
    stopped: list[str] = []

    def fake_stop(root: Path, run_id: str) -> None:
        assert release.wait(10)
        if run_id == f"r-{T2}":
            raise TaskRunError("remote_run", "stop this run on the machine that started it")
        store = TaskRunStore(_db(root))
        try:
            store.mark_stopped(run_id, "stopped by user")
        finally:
            store.close()
        stopped.append(run_id)

    clock = Clock()
    control = FactoryControl(stop=fake_stop, clock=clock)
    client = _app(tmp_path, repo, FakeLauncher(), control)
    data = _post(client, "stop", 202)["data"]
    assert data["pending"] == [f"r-{T1}", f"r-{T2}"]
    progress = _factory(client)["control"]
    assert progress["action"] == "stop"
    assert progress["pending"] == [f"r-{T1}", f"r-{T2}"]
    assert progress["finished_at"] is None

    release.set()
    control.wait(10)
    progress = _factory(client)["control"]
    assert progress["pending"] == []
    assert progress["finished_at"] is not None
    assert stopped == [f"r-{T1}"]
    assert [(e["run_id"], e["code"]) for e in progress["errors"]] == [(f"r-{T2}", "remote_run")]

    clock.now += KEEP_SECONDS + 1
    assert _factory(client)["control"] is None


def test_stop_with_nothing_running_is_finished_at_once(repo: Path, tmp_path: Path) -> None:
    client = _app(tmp_path, repo, FakeLauncher())
    data = _post(client, "stop", 202)["data"]
    assert (data["run_ids"], data["pending"]) == ([], [])


def test_single_repo_app_serves_the_controls(repo: Path, tmp_path: Path) -> None:
    launcher = FakeLauncher()
    app = create_app(repo, static_dir=tmp_path / "nostatic", launcher=launcher)
    client = TestClient(app, base_url=BASE)
    response = client.post("/api/control/start")
    assert response.status_code == 200, response.json()
    assert [s["task_id"] for s in response.json()["data"]["started"]] == [T1, T2]
