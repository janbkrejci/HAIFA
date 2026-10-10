"""Start a task run from the API: a real ``factory task run`` process over the fake harness.

The launcher's command prefix is ``python -m validation.worker``; with
``HAIFA_VALIDATE_FAKE`` the worker installs the scripted fake harness of
``validation.fake`` in the run process. ``claude``, ``codex``, ``pi`` and ``gh`` point at a
tripwire, so no test calls a model or the network. The launcher itself (stop,
concurrency, errors, cleanup) is covered with a stub process in ``test_web_launcher``.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from aifactory.run import TaskRunRow, TaskRunStore
from aifactory.skill import envelope_problems
from aifactory.web import create_app
from aifactory.web.launcher import RunLauncher

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))

from run_repo import T01, T02, commit_all, git, make_run_repo, write  # noqa: E402

from fake_exe import make_executable

BASE = "http://127.0.0.1:4700"
AIFACTORY = Path(__file__).resolve().parents[2]
WORKER = [sys.executable, "-m", "validation.worker"]
TRIPWIRE_ENV = ("AIFACTORY_GH", "CODEX_PATH", "CLAUDE_CODE_PATH", "PI_PATH")


@dataclass
class Worker:
    script: Path
    marker: Path

    def calls(self) -> list[dict[str, Any]]:
        log = self.script.with_name(self.script.name + ".calls.jsonl")
        if not log.is_file():
            return []
        lines = log.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line]


def _planner_call(name: str) -> dict[str, Any]:
    rel = f"src/app/{name}.py"
    return {
        "envelope": {
            "status": "success",
            "summary": f"add {rel}",
            "artifacts": [],
            "changed_files": [rel],
            "commit_message": f"Add {name}",
        },
        "edits": [{"path": rel, "write": f"NAME = {name!r}\n"}],
    }


@pytest.fixture(name="worker")
def worker_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Worker]:
    script = tmp_path / "script.json"
    planner = [_planner_call("model"), _planner_call("loader")]
    script.write_text(json.dumps({"agents": {"planner": planner}}), encoding="utf-8", newline="\n")
    wire_dir = tmp_path / "wire"
    wire_dir.mkdir()
    marker = wire_dir / "real-harness-reached"
    wire = wire_dir / "tripwire"
    wire.write_text(
        f'#!/bin/sh\necho "$0 $*" >> "{marker}"\nexit 97\n', encoding="utf-8", newline="\n"
    )
    wire = make_executable(wire)
    monkeypatch.setenv("HAIFA_VALIDATE_FAKE", str(script))
    old = os.environ.get("PYTHONPATH")
    monkeypatch.setenv("PYTHONPATH", str(AIFACTORY) + (os.pathsep + old if old else ""))
    monkeypatch.setenv("UV_NO_SYNC", "1")
    monkeypatch.setenv("ENGINEER_NAME", "tester")
    for key in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(key, "Test")
    for key in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(key, "test@example.com")
    for key in TRIPWIRE_ENV:
        monkeypatch.setenv(key, str(wire))
    for key in ("HAIFA_VALIDATE_HIDDEN", "HAIFA_SANDBOX_REPO"):
        monkeypatch.delenv(key, raising=False)
    worker = Worker(script, marker)
    yield worker
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


@pytest.fixture(name="app")
def app_fixture(repo: Path, tmp_path: Path, worker: Worker) -> Iterator[Starlette]:
    app = create_app(repo, static_dir=tmp_path / "nostatic", launcher=RunLauncher(command=WORKER))
    try:
        yield app
    finally:
        wait(app)


@pytest.fixture(name="client")
def client_fixture(app: Starlette) -> TestClient:
    return TestClient(app, base_url=BASE)


def wait(app: Starlette) -> None:
    """Wait until every run process of the dashboard exited and was cleaned up."""
    launcher: RunLauncher = app.state.launcher
    launcher.wait(timeout=120)
    assert launcher.running() == []


def runs_of(repo: Path, task_id: str) -> list[TaskRunRow]:
    db = repo / ".factory" / "trace.db"
    if not db.is_file():
        return []
    store = TaskRunStore(db)
    try:
        return store.for_task(task_id)
    finally:
        store.close()


def _check(response: Any, status: int) -> Any:
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    return body


def _run(client: TestClient, task_id: str, payload: Any, status: int = 202) -> Any:
    return _check(client.post(f"/api/backlog/tasks/{task_id}/run", json=payload), status)


def test_run_from_api_creates_task_run(
    app: Starlette, client: TestClient, repo: Path, worker: Worker
) -> None:
    data = _run(client, T01, {"note": "z UI"})["data"]
    assert data["task_id"] == T01
    assert data["pending"] is False
    assert data["force"] is False
    assert data["run"]["task_id"] == T01
    assert data["run"]["pid"] != os.getpid()
    wait(app)
    [row] = runs_of(repo, T01)
    assert row.run_id == data["run"]["run_id"]
    assert row.note == "z UI"
    assert row.state == "succeeded", row.error
    assert [c["agent"] for c in worker.calls()] == ["planner"]

    # a second process with the same script gets the script's second entry
    _run(client, T02, {"force": True})
    wait(app)
    [row2] = runs_of(repo, T02)
    assert row2.state == "succeeded", row2.error
    assert [c["agent"] for c in worker.calls()] == ["planner", "planner"]
    assert git(repo, "show", f"{row2.branch}:src/app/loader.py") == "NAME = 'loader'"


def test_unmet_dependencies_and_force(
    app: Starlette, client: TestClient, repo: Path, worker: Worker
) -> None:
    check = _check(client.get(f"/api/backlog/tasks/{T02}/run-check"), 200)["data"]
    assert [u["id"] for u in check["unmet"]] == [T01]
    assert check["in_base"] is True
    assert check["config"]["clean"] is True
    assert check["running"] is None
    assert check["launcher_busy"] is False
    body = _run(client, T02, {}, 409)
    assert body["error"]["code"] == "unmet_dependencies"
    wait(app)
    assert runs_of(repo, T02) == []
    assert worker.calls() == []
    data = _run(client, T02, {"force": True})["data"]
    assert data["force"] is True
    wait(app)
    assert [r.state for r in runs_of(repo, T02)] == ["succeeded"]


def test_task_without_workflow_does_not_start(
    app: Starlette, client: TestClient, repo: Path, worker: Worker
) -> None:
    write(
        repo,
        "backlog/M01-core/S01-model/M01-S01-T02-loader.md",
        f"---\nid: {T02}\ntitle: Loader\nstatus: todo\nworkflow: null\n"
        f"depends_on: [{T01}]\n---\n\nNačíst.\n",
    )
    commit_all(repo, "task without workflow")
    for payload in ({}, {"force": True}):
        body = _run(client, T02, payload, 422)
        assert body["error"]["code"] == "no_workflow"
        wait(app)
    assert runs_of(repo, T02) == []
    assert worker.calls() == []
    assert git(repo, "branch", "--list", "factory/*").strip() == ""
    assert not (repo / ".factory" / "worktrees").exists() or not any(
        (repo / ".factory" / "worktrees").iterdir()
    )


def test_run_check_reports_uncommitted_config(client: TestClient, repo: Path) -> None:
    write(repo, ".factory/workflows/x.yaml", "name: x\nsteps: [plan]\n")
    body = _check(client.get(f"/api/backlog/tasks/{T01}/run-check"), 200)
    config = body["data"]["config"]
    assert config["clean"] is False
    assert config["changes"] == [{"path": ".factory/workflows/x.yaml", "status": "untracked"}]
    assert any(".factory/workflows/x.yaml" in w for w in body["warnings"])
    assert body["data"]["launcher_busy"] is False


def test_run_rejects_bad_input(client: TestClient, repo: Path) -> None:
    assert _run(client, T01, {"bogus": 1}, 400)["error"]["code"] == "usage_error"
    assert _run(client, T01, {"force": "yes"}, 400)["error"]["code"] == "invalid_value"
    assert _run(client, "M01-S01-T09", {}, 404)["error"]["code"] == "unknown_task"
    body = _check(client.get("/api/backlog/tasks/M01-S01-T09/run-check"), 404)
    assert body["error"]["code"] == "unknown_task"
    assert runs_of(repo, T01) == []


def test_excluded_task_still_runs_by_hand(
    app: Starlette, client: TestClient, repo: Path, worker: Worker
) -> None:
    body = _check(
        client.post(f"/api/backlog/tasks/{T01}/auto-exclude", json={"excluded": True}), 200
    )
    assert body["data"] == {"task_id": T01, "excluded": True}
    data = _run(client, T01, {})["data"]
    assert data["run"]["task_id"] == T01
    wait(app)
    [row] = runs_of(repo, T01)
    assert row.state == "succeeded", row.error


def test_run_override_is_validated(client: TestClient, repo: Path) -> None:
    body = _run(client, T01, {"harness": "nope"}, 400)
    assert body["error"]["code"] == "invalid_value"
    body = _run(client, T01, {"thinking": "loud"}, 400)
    assert body["error"]["code"] == "invalid_value"
    assert _run(client, T01, {"auto": "yes"}, 400)["error"]["code"] == "invalid_value"
    assert runs_of(repo, T01) == []


def test_run_check_reports_the_effective_run(client: TestClient, repo: Path) -> None:
    check = _check(client.get(f"/api/backlog/tasks/{T01}/run-check"), 200)["data"]
    assert check["workflow"]
    assert check["writes"]
    assert "test" not in check
