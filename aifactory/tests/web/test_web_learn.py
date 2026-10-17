"""The Lekce API (``web.learn``): list, scan in the background, accept, dismiss."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from aifactory.learn.store import ACCEPTED, PROPOSED, REJECTED
from aifactory.web import create_app
from aifactory.web.learn import LearnManager
from learn_fixture import fake_learner, make_learn_repo

RULE = "Add a test for every new CLI command."
LESSON = {"rule": RULE, "target": "AGENTS.md", "complaints": ["c1", "c2"]}
OTHER = {"rule": "Run ruff before reporting.", "target": "AGENTS.md", "complaints": ["c1", "c3"]}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_learn_repo(tmp_path)


@pytest.fixture
def client(repo: Path) -> Any:
    app = create_app(repo, static_dir=repo / "absent")
    with TestClient(app, base_url="http://127.0.0.1:4700") as test_client:
        yield test_client


def _answer(*lessons: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "summary": "lessons", "lessons": list(lessons)}


def _wait(client: TestClient) -> dict[str, Any]:
    for _ in range(500):
        data = client.get("/api/learn").json()["data"]
        if data["scan"] and data["scan"]["state"] != "running":
            return dict(data)
        time.sleep(0.02)
    raise AssertionError("the scan did not finish")


def test_scan_accept_dismiss(
    repo: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, answers = fake_learner(monkeypatch)
    answers.append(_answer(LESSON, OTHER))
    assert client.get("/api/learn").json()["data"] == {"lessons": [], "scan": None}

    response = client.post("/api/learn/scan", json={})
    assert response.status_code == 202, response.text
    assert response.json()["data"]["state"] == "running"
    data = _wait(client)
    assert data["scan"]["state"] == "done", data
    assert data["scan"]["result"] == {"objections": 3, "runs": 2, "lessons": 2, "repeats": 0}
    assert [lesson["state"] for lesson in data["lessons"]] == [PROPOSED, PROPOSED]
    first = next(lesson for lesson in data["lessons"] if lesson["rule"] == RULE)
    assert [r["run_id"] for r in first["runs"]] == ["run-a", "run-b"]
    assert first["complaints"][0]["text"] == "The new CLI command has no test."

    accepted = client.post(f"/api/learn/lessons/{first['id']}/accept", json={})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["task"]["id"] == "P01-LEARN-T01"
    other = next(lesson for lesson in data["lessons"] if lesson["id"] != first["id"])
    dismissed = client.post(f"/api/learn/lessons/{other['id']}/dismiss", json={"reason": "no"})
    assert dismissed.json()["data"]["state"] == REJECTED

    lessons = client.get("/api/learn").json()["data"]["lessons"]
    assert [(lesson["id"], lesson["state"]) for lesson in lessons] == [
        (first["id"], ACCEPTED),
        (other["id"], REJECTED),
    ]
    assert lessons[0]["task_id"] == "P01-LEARN-T01"


def test_errors(client: TestClient) -> None:
    missing = client.post("/api/learn/lessons/Lnope/accept", json={})
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "unknown_lesson"
    assert client.post("/api/learn/lessons/Lnope/dismiss", json={}).status_code == 404
    assert client.post("/api/learn/scan", json={"other": 1}).status_code == 400
    assert client.post("/api/learn/lessons/L1/accept", json={"project": 3}).status_code == 400


def test_one_scan_at_a_time_and_failure_is_reported(repo: Path) -> None:
    release = threading.Event()

    def slow(root: Path, since: str | None) -> dict[str, Any]:
        assert release.wait(10)
        raise RuntimeError("boom")

    manager = LearnManager(slow)
    try:
        assert manager.start(repo, {"since": "2026-10-01"})["since"] == "2026-10-01"
        with pytest.raises(Exception, match="already"):
            manager.start(repo, {})
        release.set()
        for _ in range(500):
            scan = manager.state(repo)["scan"]
            if scan["state"] != "running":
                break
            time.sleep(0.01)
        assert scan["state"] == "failed" and "boom" in scan["error"]
    finally:
        manager.close()
