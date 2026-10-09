from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from advice_fixture import make_repo
from aifactory import backlog as core
from aifactory.errors import UsageError
from aifactory.web import create_app
from aifactory.web.workflow_advice import AdviceManager
from aifactory.workflow.adaptive import context
from aifactory.workflow.task_advice import TaskRecommendationOutput, validate_task


def proposal(**overrides: Any) -> dict[str, Any]:
    return {
        "status": "success",
        "title": "Clearer task",
        "body": "Acceptance criteria",
        "writes": ["src/"],
        "depends_on": [],
        "related": [],
        "workflow": "plan",
        "reason": "Narrower scope",
        "parameters": {
            "test": ["uv", "run", "pytest"],
            "test_timeout": 120,
            "auto_merge": False,
            "source": "input.md",
        },
        **overrides,
    }


def test_repeat_select_cost_and_save(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    app = create_app(repo, static_dir=repo / "absent")
    app.state.task_advice.close()
    seen = []

    def runner(
        root: Path, ctx: dict[str, Any], identifier: str, event: threading.Event
    ) -> dict[str, Any]:
        seen.append(ctx)
        return proposal(usage={"tokens": 100, "cost_usd": 0.025})

    app.state.task_advice = AdviceManager(runner, task_parameters=True)
    task_path = repo / "backlog/P01/S01/P01-S01-T01-first.md"
    original = task_path.read_text()
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        options = client.get("/api/backlog/task-advice/options").json()["data"]["agents"]
        assert options[0] == {"name": "planner", "provider": "claude", "model": "sonnet"}
        payload = {
            "task_id": "P01-S01-T01",
            "agent": "planner",
            "draft": {"title": "Live title", "body": "Live body", "related": [], "depends_on": []},
        }
        ids = []
        for _ in range(2):
            response = client.post("/api/backlog/task-advice", json=payload)
            assert response.status_code == 202
            identifier = response.json()["data"]["job_id"]
            ids.append(identifier)
            for _ in range(200):
                data = client.get(f"/api/backlog/task-advice/{identifier}").json()["data"]
                if data["state"] in {"succeeded", "failed"}:
                    break
                time.sleep(0.01)
            assert data["state"] == "succeeded", data
            assert data["recommendation"]["usage"]["cost_usd"] == 0.025
            assert task_path.read_text() == original
        assert ids[0] != ids[1]
        assert seen[0]["draft"]["body"] == "Live body"
        assert seen[0]["agent"] == "planner"
        assert (
            client.post(
                "/api/backlog/task-advice", json={**payload, "agent": "invented"}
            ).status_code
            == 400
        )
        result = data["recommendation"]
        edit = {
            k: result[k]
            for k in ("title", "body", "writes", "depends_on", "related", "workflow", "parameters")
        }
        response = client.post("/api/backlog/tasks/P01-S01-T01/edit", json=edit)
        assert response.status_code == 200, response.text
        task = core.load_for_edit(repo).by_id["P01-S01-T01"]
        assert isinstance(task, core.Task)
        assert task.title == "Clearer task"
        assert task.own["auto_merge"] is False
        assert task.own["test_timeout"] == 120
        response = client.post("/api/backlog/tasks", json={"step": "P01-S01", **edit})
        assert response.status_code == 200, response.text
        task = core.load_for_edit(repo).by_id[response.json()["data"]["task"]["id"]]
        assert isinstance(task, core.Task)
        assert task.own["auto_merge"] is False
        assert task.own["source"] == "input.md"


@pytest.mark.parametrize(
    "changes",
    [
        {"depends_on": ["P01-S01-T01"]},
        {"related": ["invented"]},
        {"writes": ["../outside"]},
        {"workflow": "invented"},
    ],
)
def test_invalid_proposal(tmp_path: Path, changes: dict[str, Any]) -> None:
    repo = make_repo(tmp_path / "repo")
    with pytest.raises(UsageError):
        validate_task(
            repo,
            TaskRecommendationOutput.model_validate(proposal(**changes)),
            context(repo, "P01-S01-T01", {}, task_parameters=True),
        )


def test_atomic_relations_and_history(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    path = repo / "backlog/P01/S01/P01-S01-T01-first.md"
    path.write_text(path.read_text() + "\n## Běhy\n\n- previous run\n")
    original = path.read_text()
    with pytest.raises(core.TaskEditError):
        core.edit_task(repo, "P01-S01-T01", body="Updated", depends_on=["missing"])
    assert path.read_text() == original
    core.edit_task(repo, "P01-S01-T01", body="Updated\n## Běhy\nFake history", related=[])
    assert "Updated" in path.read_text()
    assert "- previous run" in path.read_text()
    assert "Fake history" not in path.read_text()


def test_selected_agent_uses_proposal_schema_and_reports_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    from concurrent.futures import ThreadPoolExecutor

    from aifactory.engine import agents
    from aifactory.engine.data_types import AgentResult
    from aifactory.harness.check import HarnessStatus
    from aifactory.workflow.adaptive import recommend

    repo = make_repo(tmp_path / "repo")
    seen = []
    monkeypatch.setattr(
        "aifactory.workflow.adaptive.check_harness",
        lambda name: HarnessStatus(name, "fake", "fake", "1"),
    )

    def run(request: Any, **kwargs: Any) -> AgentResult:
        seen.append(request)
        assert '"parameters"' in request.system_prompt
        assert "Original task" not in request.prompt
        assert Path(request.cwd) != repo
        return AgentResult(text=json.dumps(proposal()), returncode=0, tokens=200, cost=0.05)

    monkeypatch.setattr(agents.INTERFACES["claude"], "run", run)
    ctx = context(repo, "P01-S01-T01", {"body": "Live body"}, task_parameters=True)
    ctx.update(task_parameters=True, agent="builder", available_tasks=[])
    with ThreadPoolExecutor(1) as pool:
        result = pool.submit(recommend, repo, ctx, "task-proposal", threading.Event()).result()
    assert result["title"] == "Clearer task"
    assert result["usage"] == {"tokens": 200, "cost_usd": 0.05}
    assert seen[0].model == "sonnet"
    assert not Path(seen[0].cwd).exists()
