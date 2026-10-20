"""Dashboard guards use real trace rows and base dependencies, without live services."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from backlog_fixture import A1, A2, A3, B2, B3, git, make_backlog_repo
from starlette.applications import Starlette
from starlette.testclient import TestClient
from test_web_backlog_follow_up import RecordingLauncher
from test_web_workflow_advice import client_for, wait
from trace_fixture import _run

from advice_fixture import make_repo, output
from aifactory.run import TaskRunStore
from aifactory.run.errors import TaskRunError
from aifactory.web import create_app
from aifactory.web.workflow_advice import AdviceManager


@pytest.mark.parametrize(
    ("action", "payload"),
    [
        ("edit", {"title": "Changed"}),
        ("edit", {"status": "cancelled"}),
        ("edit", {"workflow": "custom-flow"}),
        ("edit", {"writes": ["src/"]}),
        ("edit", {"body": "Changed body"}),
        ("edit", {"depends_on": [A1], "related": [A2]}),
        ("edit", {"workflow_advice_id": "unused", "workflow": "plan"}),
        ("link", {"depends_on": [A1]}),
        ("link", {"related": [A2]}),
        ("link", {"related": [A2], "remove": True}),
    ],
)
def test_running_task_cannot_be_written(
    tmp_path: Path, action: str, payload: dict[str, Any]
) -> None:
    repo = make_backlog_repo(tmp_path / "repo", with_trace=True)
    path = next((repo / "backlog").rglob(f"{B2}-*.md"))
    before = path.read_bytes()
    with TestClient(create_app(repo), base_url="http://127.0.0.1:4700") as client:
        response = client.post(f"/api/backlog/tasks/{B2}/{action}", json=payload)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "task_running"
    assert B2 in response.json()["error"]["message"]
    assert "r-b2" in response.json()["error"]["message"]
    assert path.read_bytes() == before


@pytest.mark.parametrize("endpoint", ["task-advice", "workflow-advice"])
def test_running_task_cannot_start_advice(tmp_path: Path, endpoint: str) -> None:
    repo = make_backlog_repo(tmp_path / "repo", with_trace=True)
    path = next((repo / "backlog").rglob(f"{B2}-*.md"))
    before = path.read_bytes()
    app = create_app(repo)
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        response = client.post(
            f"/api/backlog/{endpoint}", json={"task_id": B2, "draft": {"title": "Changed"}}
        )
        assert app.state.task_advice.jobs == {}
        assert app.state.workflow_advice.jobs == {}
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "task_running"
    assert path.read_bytes() == before


def test_advice_save_rechecks_run_before_creating_workflow(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    task_id = "P01-S01-T01"
    path = repo / "backlog/P01/S01/P01-S01-T01-first.md"
    before = path.read_bytes()
    with client_for(repo, lambda *args: output("research", new=True)) as client:
        response = client.post(
            "/api/backlog/workflow-advice", json={"task_id": task_id, "draft": {}}
        )
        assert response.status_code == 202
        identifier = response.json()["data"]["job_id"]
        assert wait(client, identifier)["state"] == "succeeded"
        store = TaskRunStore(repo / ".factory/trace.db")
        try:
            store.claim(_run("live", task_id, 1, "running", 1, pid=os.getpid()))
        finally:
            store.close()
        response = client.post(
            f"/api/backlog/tasks/{task_id}/edit",
            json={"workflow": "research", "workflow_advice_id": identifier},
        )
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "task_running"
    assert path.read_bytes() == before
    assert not (repo / ".factory/workflows/research.yaml").exists()


def test_advice_save_rechecks_running_under_lock(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    task_id = "P01-S01-T01"
    path = repo / "backlog/P01/S01/P01-S01-T01-first.md"
    before = path.read_bytes()

    def writer(root: Path, body: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        pytest.fail("AdviceManager.save must reject the running task before calling its writer")

    with client_for(repo, lambda *args: output("research", new=True)) as client:
        response = client.post(
            "/api/backlog/workflow-advice", json={"task_id": task_id, "draft": {}}
        )
        assert response.status_code == 202
        identifier = response.json()["data"]["job_id"]
        assert wait(client, identifier)["state"] == "succeeded"
        store = TaskRunStore(repo / ".factory/trace.db")
        try:
            store.claim(_run("live", task_id, 1, "running", 1, pid=os.getpid()))
        finally:
            store.close()
        manager: AdviceManager = cast(Starlette, client.app).state.workflow_advice
        # Call save directly so backlog.edit's earlier guard cannot hide a regression.
        with pytest.raises(TaskRunError) as rejected:
            manager.save(
                repo,
                task_id,
                {"workflow": "research", "workflow_advice_id": identifier},
                writer,
            )
        assert rejected.value.code == "task_running"
        assert "live" in rejected.value.message
    assert path.read_bytes() == before
    assert not (repo / ".factory/workflows/research.yaml").exists()


@pytest.mark.parametrize("force", [False, True])
def test_running_blocked_task_run_keeps_already_running(tmp_path: Path, force: bool) -> None:
    repo = make_backlog_repo(tmp_path / "repo")
    git(repo, "branch", "-M", "main")
    store = TaskRunStore(repo / ".factory/trace.db")
    try:
        store.claim(_run("live-blocked", A3, 1, "running", 1, pid=os.getpid()))
        before = store.for_task(A3)
    finally:
        store.close()
    attempts: list[str] = []

    class DuplicateRunLauncher(RecordingLauncher):
        def start(self, repo: Path, task_id: str, **kwargs: Any) -> None:
            attempts.append(task_id)
            raise TaskRunError("already_running", f"Task {task_id} already has a running run")

    launcher = DuplicateRunLauncher()
    app = create_app(repo, launcher=launcher)  # type: ignore[arg-type]
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        check = client.get(f"/api/backlog/tasks/{A3}/run-check").json()["data"]
        assert check["unmet"]
        assert check["stack"] is None
        assert check["running"]["run_id"] == "live-blocked"
        response = client.post(f"/api/backlog/tasks/{A3}/run", json={"force": force})
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "already_running"
    assert attempts == [A3]
    assert launcher.started == []
    store = TaskRunStore(repo / ".factory/trace.db")
    try:
        assert store.for_task(A3) == before
    finally:
        store.close()


@pytest.mark.parametrize("task_id", [A2, B3])
def test_idle_and_review_tasks_still_allow_writes(tmp_path: Path, task_id: str) -> None:
    repo = make_backlog_repo(tmp_path / "repo", with_trace=True)
    with TestClient(create_app(repo), base_url="http://127.0.0.1:4700") as client:
        response = client.post(f"/api/backlog/tasks/{task_id}/edit", json={"body": "Changed"})
        assert response.status_code == 200, response.text
        response = client.post(f"/api/backlog/tasks/{task_id}/link", json={"related": [A1]})
        assert response.status_code == 200, response.text


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("draft_unblocked", [False, True])
def test_blocked_run_never_reaches_launcher(
    tmp_path: Path, force: bool, draft_unblocked: bool
) -> None:
    repo = make_backlog_repo(tmp_path / "repo")
    git(repo, "branch", "-M", "main")
    if draft_unblocked:
        path = next((repo / "backlog").rglob(f"{A3}-*.md"))
        path.write_text(path.read_text().replace(f"depends_on: [{A2}]", "depends_on: []"))
    launcher = RecordingLauncher()
    app = create_app(repo, launcher=launcher)  # type: ignore[arg-type]
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        response = client.post(f"/api/backlog/tasks/{A3}/run", json={"force": force})
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "unmet_dependencies"
        assert launcher.started == []
        # The same force value still works for an unblocked task.
        response = client.post(f"/api/backlog/tasks/{A2}/run", json={"force": force})
        assert response.status_code == 202, response.text
        assert launcher.started == [A2]


def test_stacked_run_still_starts_without_force(tmp_path: Path) -> None:
    repo = make_backlog_repo(tmp_path / "repo", with_trace=True)
    git(repo, "branch", "-M", "main")
    config = repo / ".factory/config.yaml"
    config.write_text(config.read_text() + "stacked_prs: true\n")
    git(repo, "add", ".factory/config.yaml")
    git(repo, "commit", "-qm", "enable stacked runs")
    store = TaskRunStore(repo / ".factory/trace.db")
    try:
        pr = store.open_pr(B3)
        assert pr is not None
        # An open dependency PR whose tip is available locally.
        store.save_pr(replace(pr, task_id=A2, branch="main", pr_id="4"))
    finally:
        store.close()
    launcher = RecordingLauncher()
    app = create_app(repo, launcher=launcher)  # type: ignore[arg-type]
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        check = client.get(f"/api/backlog/tasks/{A3}/run-check").json()["data"]
        assert check["unmet"]
        assert check["stack"]["prs"][0]["task_id"] == A2
        response = client.post(f"/api/backlog/tasks/{A3}/run", json={})
        assert response.status_code == 202, response.text
        assert response.json()["data"]["force"] is False
    assert launcher.started == [A3]
