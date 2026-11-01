"""The Lekce API (``web.learn``): list, scan in the background, accept, dismiss."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from aifactory.home import haifa_home
from aifactory.learn.sources import FACTORY_REPO_ENV
from aifactory.learn.store import ACCEPTED, PROPOSED, REJECTED
from aifactory.learn.view import lessons as view_lessons
from aifactory.web import create_app
from aifactory.web.learn import LearnManager
from aifactory.web.registry import Registry
from learn_fixture import fake_learner, make_learn_repo, register_learn_repos

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
    assert client.post("/api/learn/scan", json={"all": True, "other": 1}).status_code == 400
    not_bool = client.post("/api/learn/scan", json={"all": "yes"})
    assert not_bool.status_code == 400 and "boolean" in not_bool.json()["error"]["message"]
    assert client.post("/api/learn/scan", json={"all": 1}).status_code == 400
    assert client.post("/api/learn/lessons/L1/accept", json={"project": 3}).status_code == 400


def test_one_scan_at_a_time_and_failure_is_reported(repo: Path) -> None:
    release = threading.Event()

    def slow(root: Path, since: str | None, all_repos: bool) -> dict[str, Any]:
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


def _finished(manager: LearnManager, repo: Path) -> dict[str, Any]:
    for _ in range(500):
        scan = manager.state(repo)["scan"]
        if scan["state"] != "running":
            return dict(scan)
        time.sleep(0.01)
    raise AssertionError("the scan did not finish")


def test_scan_body_all_is_passed_to_the_scanner(client: TestClient, repo: Path) -> None:
    own, _created = Registry(haifa_home()).add(repo)
    calls: list[tuple[str | None, bool]] = []

    def scanner(root: Path, since: str | None, all_repos: bool) -> dict[str, Any]:
        calls.append((since, all_repos))
        found = [{"repo": own.id}, {"repo": "beta"}, {"repo": "beta"}, {"repo": "gamma"}]
        return {
            "objections": 5,
            "runs": 4,
            "repos": 3,
            "lessons": found if all_repos else found[:1],
            "repeats": [{"id": "L1", "added": 2, "repo": "beta"}],
            "warnings": ["gamma: cannot read the lessons"],
        }

    app = cast(Starlette, client.app)
    app.state.learn.close()
    app.state.learn = LearnManager(scanner)

    started = client.post("/api/learn/scan", json={"all": True, "since": "2026-10-01"})
    assert started.status_code == 202, started.text
    assert started.json()["data"]["all"] is True
    done = _wait(client)["scan"]
    assert done["state"] == "done" and done["all"] is True
    assert done["result"] == {
        "objections": 5,
        "runs": 4,
        "lessons": 4,
        "repeats": 2,
        "repos": 3,
        "elsewhere": {"beta": 2, "gamma": 1},
        "warnings": ["gamma: cannot read the lessons"],
    }

    # without ``all`` (and with ``all: false``) the scan stays in the repo, as before
    for body in ({}, {"all": False}):
        assert client.post("/api/learn/scan", json=body).status_code == 202
        single = _wait(client)["scan"]
        assert single["all"] is False
        assert single["result"] == {"objections": 5, "runs": 4, "lessons": 1, "repeats": 2}
    assert calls == [("2026-10-01", True), (None, False), (None, False)]


def test_scan_all_of_an_unregistered_repo(repo: Path) -> None:
    manager = LearnManager(lambda root, since, all_repos: {"lessons": [{"repo": 3}], "repos": 1})
    try:
        manager.start(repo, {"all": True})
        scan = _finished(manager, repo)
        # an unregistered repo has no id: every lesson with a repo counts as elsewhere
        assert scan["state"] == "done" and scan["result"]["elsewhere"] == {"3": 1}
    finally:
        manager.close()


def test_scan_all_through_the_api_shows_origin_and_repos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(FACTORY_REPO_ENV, "haifa")
    repos = register_learn_repos(tmp_path, "haifa", "app")
    _, answers = fake_learner(monkeypatch)
    answers.append(
        _answer(
            {**OTHER, "repo": "haifa", "complaints": ["c1", "c4"]},
            {**LESSON, "repo": "app", "complaints": ["c4", "c5"]},
        )
    )
    app = create_app(repos["haifa"], static_dir=repos["haifa"] / "absent")
    with TestClient(app, base_url="http://127.0.0.1:4700") as client:
        assert client.post("/api/learn/scan", json={"all": True}).status_code == 202
        data = _wait(client)
        assert data["scan"]["state"] == "done", data
        result = data["scan"]["result"]
        assert (result["repos"], result["lessons"], result["elsewhere"]) == (2, 2, {"app": 1})
        [here] = data["lessons"]
        assert here["rule"] == OTHER["rule"]
        assert here["origin"] == ["haifa", "app"]
        assert [c["repo"] for c in here["complaints"]] == ["haifa", "app"]

    [there] = view_lessons(repos["app"])
    assert there["rule"] == RULE and there["origin"] == ["app"]
    assert {c["repo"] for c in there["complaints"]} == {"app"}
