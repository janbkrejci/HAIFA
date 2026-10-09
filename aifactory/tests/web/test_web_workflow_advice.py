from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from advice_fixture import make_repo, output
from aifactory.web import create_app
from aifactory.web.workflow_advice import AdviceManager


def wait(client: TestClient, identifier: str) -> dict[str, Any]:
    for _ in range(200):
        data = client.get(f"/api/backlog/workflow-advice/{identifier}").json()["data"]
        if data["state"] in {"succeeded", "failed"}:
            return dict(data)
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def client_for(repo: Path, runner: Any) -> TestClient:
    app = create_app(repo, static_dir=repo / "absent")
    app.state.workflow_advice.close()
    app.state.workflow_advice = AdviceManager(runner)
    return TestClient(app, base_url="http://127.0.0.1:4700")


def test_async_duplicate_poll_scope_and_expiry(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    release = threading.Event()

    def runner(*args: Any) -> dict[str, object]:
        assert release.wait(5)
        return output()

    with client_for(repo, runner) as client:
        payload = {"task_id": "P01-S01-T01", "draft": {"title": "Draft"}}
        response = client.post("/api/backlog/workflow-advice", json=payload)
        assert response.status_code == 202
        identifier = response.json()["data"]["job_id"]
        assert (
            client.post("/api/backlog/workflow-advice", json=payload).json()["data"]["job_id"]
            == identifier
        )
        assert client.get(f"/api/backlog/workflow-advice/{identifier}").json()["data"]["state"] in {
            "queued",
            "running",
        }
        with pytest.raises(Exception, match="expired or not found"):
            cast(Starlette, client.app).state.workflow_advice.get(tmp_path / "foreign", identifier)
        release.set()
        assert wait(client, identifier)["state"] == "succeeded"
        job = cast(Starlette, client.app).state.workflow_advice.get(repo, identifier)
        job.completed -= 1801
        assert client.get(f"/api/backlog/workflow-advice/{identifier}").status_code == 404


@pytest.mark.parametrize("new", [False, True])
def test_add_and_edit_save(tmp_path: Path, new: bool) -> None:
    repo = make_repo(tmp_path / "repo")
    name = "research" if new else "plan"
    with client_for(repo, lambda *args: output(name, new=new)) as client:
        draft = {"step": "P01-S01", "title": "Unsaved", "body": "Task details"}
        identifier = client.post("/api/backlog/workflow-advice", json={"draft": draft}).json()[
            "data"
        ]["job_id"]
        assert wait(client, identifier)["state"] == "succeeded"
        assert not (repo / ".factory/workflows/research.yaml").exists()
        response = client.post(
            "/api/backlog/tasks", json={**draft, "workflow": name, "workflow_advice_id": identifier}
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"].get("requires_config_commit", False) == new
        if new:
            assert (repo / ".factory/workflows/research.yaml").read_text() == output(
                name, new=True
            )["workflow_yaml"]
        # Existing task, currently without workflow.
        identifier = client.post(
            "/api/backlog/workflow-advice",
            json={"task_id": "P01-S01-T01", "draft": {"title": "Edited"}},
        ).json()["data"]["job_id"]
        assert wait(client, identifier)["state"] == "succeeded"
        response = client.post(
            "/api/backlog/tasks/P01-S01-T01/edit",
            json={"title": "Edited", "workflow": name, "workflow_advice_id": identifier},
        )
        # A new recommendation with a name already on disk must never overwrite it.
        assert response.status_code == (400 if new else 200), response.text


@pytest.mark.parametrize("mutation", ["draft", "collision", "symlink", "invalid-task"])
def test_reject_without_partial_write(tmp_path: Path, mutation: str) -> None:
    repo = make_repo(tmp_path / "repo")
    with client_for(repo, lambda *args: output("research", new=True)) as client:
        draft = {"step": "P01-S01", "title": "Draft"}
        identifier = client.post("/api/backlog/workflow-advice", json={"draft": draft}).json()[
            "data"
        ]["job_id"]
        assert wait(client, identifier)["state"] == "succeeded"
        target = repo / ".factory/workflows/research.yaml"
        payload = {**draft, "workflow": "research", "workflow_advice_id": identifier}
        if mutation == "draft":
            payload["title"] = "Changed"
        elif mutation == "collision":
            target.write_text("foreign")
        elif mutation == "symlink":
            target.symlink_to(repo / ".factory/config.yaml")
        else:
            payload["id"] = "invalid id"
        response = client.post("/api/backlog/tasks", json=payload)
        assert response.status_code in {400, 422}, response.text
        assert len(list((repo / "backlog").rglob("*T*.md"))) == 1
        if mutation == "collision":
            assert target.read_text() == "foreign"
        elif mutation != "symlink":
            assert not target.exists()


def test_invalid_body_and_failure(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    with client_for(repo, lambda *args: {**output(), "workflow_name": "missing"}) as client:
        assert (
            client.post(
                "/api/backlog/workflow-advice", json={"draft": {"title": "Draft"}}
            ).status_code
            == 400
        )
        response = client.post(
            "/api/backlog/workflow-advice", json={"draft": {"step": "P01-S01", "title": "Draft"}}
        )
        result = wait(client, response.json()["data"]["job_id"])
        assert result["state"] == "failed"
        assert "catalog" in result["error"]


def test_idempotent_save_and_foreign_edit(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    with client_for(repo, lambda *args: output("research", new=True)) as client:
        payload = {"task_id": "P01-S01-T01", "draft": {}}
        identifier = client.post("/api/backlog/workflow-advice", json=payload).json()["data"][
            "job_id"
        ]
        assert wait(client, identifier)["state"] == "succeeded"
        save = {"workflow": "research", "workflow_advice_id": identifier}
        url = "/api/backlog/tasks/P01-S01-T01/edit"
        first = client.post(url, json=save)
        assert first.status_code == 200
        assert client.post(url, json=save).json() == first.json()
        (repo / ".factory/workflows/research.yaml").write_text("foreign content")
        assert client.post(url, json=save).status_code == 400
        assert (repo / ".factory/workflows/research.yaml").read_text() == "foreign content"


def test_rollback_and_journal_then_base_resolution(tmp_path: Path) -> None:
    from advice_fixture import git
    from aifactory.config import load_run_config
    from aifactory.run import backup, mainwrites
    from aifactory.run.task import named_workflow
    from aifactory.web import backlog
    from aifactory.web.backlog import UsageError

    repo = make_repo(tmp_path / "repo")
    with client_for(repo, lambda *args: output("research", new=True)) as client:
        identifier = client.post(
            "/api/backlog/workflow-advice", json={"task_id": "P01-S01-T01", "draft": {}}
        ).json()["data"]["job_id"]
        assert wait(client, identifier)["state"] == "succeeded"
        manager = cast(Starlette, client.app).state.workflow_advice
        target = repo / ".factory/workflows/research.yaml"

        def fail_live(root: Path, values: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
            if root == repo:
                raise UsageError("injected save failure")
            return backlog.edit(root, "P01-S01-T01", values)

        save = {"workflow": "research", "workflow_advice_id": identifier}
        with pytest.raises(UsageError, match="injected"):
            manager.save(repo, "P01-S01-T01", save, fail_live)
        assert not target.exists()
        offset = mainwrites.offset(repo)
        assert client.post("/api/backlog/tasks/P01-S01-T01/edit", json=save).status_code == 200
        writes = mainwrites.writes_since(repo, offset)
        accepted = mainwrites.accept(repo, writes, lambda path: backup.ABSENT, "foreign-run")
        assert ".factory/workflows/research.yaml" in accepted.states
        assert accepted.states[".factory/workflows/research.yaml"][0] == target.read_bytes()
        # Publishing the exact product changes makes the standard base resolver see the workflow.
        git(repo, "add", ".factory/workflows/research.yaml", "backlog")
        git(repo, "commit", "-qm", "publish fixture")
        assert (
            named_workflow("research", load_run_config(repo).config, "P01-S01-T01").name
            == "research"
        )


def test_two_repos_with_identical_task_ids_are_isolated(tmp_path: Path) -> None:
    from aifactory.web.app import create_multi_app
    from aifactory.web.registry import Registry

    first = make_repo(tmp_path / "first")
    second = make_repo(tmp_path / "second")
    home = tmp_path / "home"
    entry1, _ = Registry(home).add(first)
    entry2, _ = Registry(home).add(second)
    app = create_multi_app(home=home)
    app.state.workflow_advice.close()
    app.state.workflow_advice = AdviceManager(lambda *args: output())
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        payload = {"task_id": "P01-S01-T01", "draft": {}}
        path1 = f"/api/repos/{entry1.id}/backlog/workflow-advice"
        path2 = f"/api/repos/{entry2.id}/backlog/workflow-advice"
        job1 = client.post(path1, json=payload).json()["data"]["job_id"]
        job2 = client.post(path2, json=payload).json()["data"]["job_id"]
        assert job1 != job2
        assert client.get(f"{path1}/{job2}").status_code == 404
        assert client.get(f"{path2}/{job1}").status_code == 404


def test_busy_queue_and_task_state_are_rejected(tmp_path: Path) -> None:
    from aifactory.web.backlog import UsageError
    from aifactory.web.workflow_advice import Cancellation
    from aifactory.workflow.adaptive import context

    repo = make_repo(tmp_path / "repo")
    release = threading.Event()

    def runner(*args: Any) -> dict[str, object]:
        release.wait(5)
        return output()

    manager = AdviceManager(runner)
    try:
        for n in range(4):
            manager.start(repo, {"task_id": "P01-S01-T01", "draft": {"title": f"Draft {n}"}})
        from aifactory.backlog import TaskEditError, edit_task

        with pytest.raises(TaskEditError, match="busy"):
            manager.start(repo, {"task_id": "P01-S01-T01", "draft": {"title": "Fifth"}})
        with pytest.raises(UsageError, match="100 KB"):
            context(repo, None, {"step": "P01-S01", "title": "Draft", "body": "x" * 100_001})
        edit_task(repo, "P01-S01-T01", status="cancelled")
        with pytest.raises(UsageError, match="task state"):
            context(repo, "P01-S01-T01", {})
        cancellation = Cancellation()
        cancellation.set()
        assert cancellation.is_set()
    finally:
        release.set()
        manager.close()


def test_omitted_draft_fields_and_concurrent_task_edits_are_stale(tmp_path: Path) -> None:
    from aifactory.backlog import edit_task

    repo = make_repo(tmp_path / "repo")
    with client_for(repo, lambda *args: output("research", new=True)) as client:
        draft = {
            "step": "P01-S01",
            "title": "Draft",
            "body": "Original instructions",
            "writes": ["src/"],
        }
        identifier = client.post("/api/backlog/workflow-advice", json={"draft": draft}).json()[
            "data"
        ]["job_id"]
        assert wait(client, identifier)["state"] == "succeeded"
        assert (
            client.post(
                "/api/backlog/tasks",
                json={
                    "step": "P01-S01",
                    "title": "Draft",
                    "workflow": "research",
                    "workflow_advice_id": identifier,
                },
            ).status_code
            == 400
        )
        identifier = client.post(
            "/api/backlog/workflow-advice", json={"task_id": "P01-S01-T01", "draft": {}}
        ).json()["data"]["job_id"]
        assert wait(client, identifier)["state"] == "succeeded"
        edit_task(repo, "P01-S01-T01", workflow="plan")
        assert (
            client.post(
                "/api/backlog/tasks/P01-S01-T01/edit",
                json={"workflow": "research", "workflow_advice_id": identifier},
            ).status_code
            == 400
        )
        assert not (repo / ".factory/workflows/research.yaml").exists()


def test_advice_save_survives_concurrent_guard_restoration(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from aifactory.config import load_run_config
    from aifactory.engine import agents
    from aifactory.engine.permissions import PermissionBreach
    from aifactory.run.guard import TaskWriteGuard
    from aifactory.run.scope import TaskScope
    from aifactory.run.task import prepare_cfg

    repo = make_repo(tmp_path / "repo")
    worktree = make_repo(tmp_path / "foreign-worktree")
    runtime = repo / ".factory/data/foreign-run"
    cfg = prepare_cfg(repo, load_run_config(repo), runtime / "prompts")
    agent = agents.resolve(cfg, "planner")
    run = SimpleNamespace(
        repo_root=worktree,
        cfg=cfg,
        adw_id="foreign-run",
        session_dir=runtime,
        current_agent=agent,
    )
    guard = TaskWriteGuard(repo, worktree, TaskScope("foreign-run", (), ()), (".factory/data/",))
    with client_for(repo, lambda *args: output("research", new=True)) as client:
        identifier = client.post(
            "/api/backlog/workflow-advice", json={"task_id": "P01-S01-T01", "draft": {}}
        ).json()["data"]["job_id"]
        assert wait(client, identifier)["state"] == "succeeded"
        # The foreign agent phase starts before the operator saves the recommendation.
        before = guard.snapshot(run)
        before_restore = guard.snapshot(run)
        response = client.post(
            "/api/backlog/tasks/P01-S01-T01/edit",
            json={"workflow": "research", "workflow_advice_id": identifier},
        )
        assert response.status_code == 200, response.text
        task_path = repo / "backlog/P01/S01/P01-S01-T01-first.md"
        workflow_path = repo / ".factory/workflows/research.yaml"
        saved_task = task_path.read_bytes()
        saved_workflow = workflow_path.read_bytes()
        # A clean phase accepts both factory writes without restoring its stale snapshot.
        assert guard.enforce(run, None, agent, before) == []
        assert task_path.read_bytes() == saved_task
        assert workflow_path.read_bytes() == saved_workflow

        # A second concurrent phase has the same older snapshot and overwrites both paths.
        # Its restore must use journaled content rather than the pre-save content.
        task_path.write_text("agent overwrite")
        workflow_path.write_text("agent overwrite")
        with pytest.raises(PermissionBreach, match="restored to the factory write"):
            guard.enforce(run, None, agent, before_restore)
        assert task_path.read_bytes() == saved_task
        assert workflow_path.read_bytes() == saved_workflow
