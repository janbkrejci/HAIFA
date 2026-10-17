"""The Nový záměr API (``web.intent``) with a fake proposer harness."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from advice_fixture import git, make_repo
from aifactory.backlog import check_backlog, load_backlog
from aifactory.web import create_app
from intent_fixture import export_step, install_fake, task


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = make_repo(tmp_path / "repo")
    # CI has no global git identity; the backlog commit of Použít needs one
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.com")
    return root


@pytest.fixture
def client(repo: Path) -> Any:
    app = create_app(repo, static_dir=repo / "absent")
    with TestClient(app, base_url="http://127.0.0.1:4700") as test_client:
        yield test_client


def wait(client: TestClient, job: str) -> dict[str, Any]:
    for _ in range(500):
        data = client.get(f"/api/backlog/intent/{job}").json()["data"]
        if data["state"] not in {"queued", "running"}:
            return dict(data)
        time.sleep(0.02)
    raise AssertionError("the proposal did not finish")


def _head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()


def test_propose_refine_in_same_session_and_apply(
    repo: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    revised = export_step(task("T03", "Dokumentace exportu", depends_on=["T02"]))
    seen = install_fake(monkeypatch, [export_step(), revised])
    head = _head(repo)
    response = client.post(
        "/api/backlog/intent", json={"intent": "Export do CSV", "project": "P01"}
    )
    assert response.status_code == 202, response.text
    job = response.json()["data"]["job_id"]
    data = wait(client, job)
    assert data["state"] == "ready", data
    proposal = data["proposal"]
    assert proposal["step"]["id"] == "P01-S02" and proposal["step"]["new"] is True
    assert [t["id"] for t in proposal["tasks"]] == ["P01-S02-T01", "P01-S02-T02"]
    assert [t["code"] for t in proposal["tasks"]] == ["T01", "T02"]
    assert proposal["findings"] == []
    assert _head(repo) == head and git(repo, "status", "--porcelain") == ""

    # Upřesni: the edited proposal and the note go to the same agent session
    edits = [{"code": "T01", "title": "Model CSV", "body": proposal["tasks"][0]["body"]}]
    response = client.post(
        f"/api/backlog/intent/{job}/refine",
        json={"note": "Přidej dokumentaci.", "tasks": edits},
    )
    assert response.status_code == 202, response.text
    data = wait(client, job)
    assert data["state"] == "ready" and data["round"] == 2
    assert data["notes"] == ["Přidej dokumentaci."]
    assert len(seen) == 2
    assert seen[1].session_id == seen[0].session_id
    assert seen[1].cwd == seen[0].cwd
    assert "## Continuation" in seen[1].prompt
    assert "Přidej dokumentaci." in seen[1].prompt
    assert "Model CSV" in seen[1].prompt and "CLI exportu" not in seen[1].prompt
    assert [t["code"] for t in data["proposal"]["tasks"]] == ["T01", "T02", "T03"]

    # Použít: remove T03, rename T02, write and commit
    tasks = [
        {"code": "T01", "title": "Model", "body": data["proposal"]["tasks"][0]["body"]},
        {"code": "T02", "title": "CLI pro export", "body": "Jinak.\n\nHotovo znamená:\n- ok"},
    ]
    response = client.post(f"/api/backlog/intent/{job}/apply", json={"tasks": tasks})
    assert response.status_code == 200, response.text
    applied = response.json()["data"]
    assert applied["commit"] is not None, applied["warnings"]
    assert applied["commit"]["committed"] is True
    assert sorted(applied["files"]) == [
        "backlog/P01/S02-export/P01-S02-T01-model.md",
        "backlog/P01/S02-export/P01-S02-T02-cli-pro-export.md",
        "backlog/P01/S02-export/index.md",
    ]
    assert _head(repo) != head
    assert git(repo, "status", "--porcelain", "--untracked-files=all") == ""
    backlog = load_backlog(repo)
    assert check_backlog(backlog) == []
    assert backlog.by_id["P01-S02-T02"].title == "CLI pro export"
    assert "Jinak." in backlog.by_id["P01-S02-T02"].body
    assert "P01-S02-T03" not in backlog.by_id
    assert wait(client, job)["state"] == "applied"
    assert client.post(f"/api/backlog/intent/{job}/apply", json={}).status_code == 400


def test_removed_dependency_is_dropped(
    repo: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake(monkeypatch, [export_step()])
    job = client.post("/api/backlog/intent", json={"intent": "Export", "project": "P01"}).json()[
        "data"
    ]["job_id"]
    data = wait(client, job)
    body = data["proposal"]["tasks"][1]["body"]
    response = client.post(
        f"/api/backlog/intent/{job}/apply",
        json={"tasks": [{"code": "T02", "title": "CLI", "body": body}]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["tasks"][0]["depends_on"] == []
    assert load_backlog(repo).by_id["P01-S02-T02"].depends_on == []  # type: ignore[union-attr]


def test_failed_proposal_and_validation(
    repo: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake(monkeypatch, [export_step(task("T03", "Bez", workflow="missing"))])
    assert client.post("/api/backlog/intent", json={"intent": " "}).status_code == 400
    both = {"intent": "x", "project": "P01", "step": "P01-S01"}
    assert client.post("/api/backlog/intent", json=both).status_code == 400
    job = client.post("/api/backlog/intent", json={"intent": "Export", "project": "P01"}).json()[
        "data"
    ]["job_id"]
    data = wait(client, job)
    assert data["state"] == "failed"
    assert data["error"]
    assert {i["code"] for i in data["issues"]} == {"unknown_workflow"}
    assert client.post(f"/api/backlog/intent/{job}/refine", json={"note": "x"}).status_code == 400
    assert git(repo, "status", "--porcelain") == ""


def test_new_tasks_of_existing_step_and_discard(
    repo: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    answer = {**export_step(), "step": None}
    answer["tasks"] = [task("T02", "Druhý", depends_on=["P01-S01-T01"])]
    install_fake(monkeypatch, [answer])
    job = client.post("/api/backlog/intent", json={"intent": "Druhý", "step": "P01-S01"}).json()[
        "data"
    ]["job_id"]
    data = wait(client, job)
    assert data["proposal"]["step"]["new"] is False
    assert [t["id"] for t in data["proposal"]["tasks"]] == ["P01-S01-T02"]
    manager = cast(Starlette, client.app).state.intent
    workdir = manager.jobs[job].workdir
    assert workdir.is_dir()
    assert client.post(f"/api/backlog/intent/{job}/discard").status_code == 200
    assert not workdir.exists()
    assert client.get(f"/api/backlog/intent/{job}").status_code == 404
    assert git(repo, "status", "--porcelain") == ""
