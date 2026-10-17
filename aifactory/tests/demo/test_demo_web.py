"""The sample repository in the dashboard: ``POST`` and ``DELETE /api/demo``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from aifactory.demo import default_dir, remove_demo
from aifactory.skill import envelope_problems
from aifactory.web import create_multi_app
from aifactory.web.registry import Registry, RepoError

BASE = "http://127.0.0.1:4700"


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    for kind in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{kind}_NAME", "Ada Tester")
        monkeypatch.setenv(f"GIT_{kind}_EMAIL", "ada@example.com")


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


@pytest.fixture
def client(home: Path, tmp_path: Path) -> TestClient:
    app = create_multi_app(home=home, static_dir=tmp_path / "nostatic")
    return TestClient(app, base_url=BASE)


def _body(response: Any, status: int) -> Any:
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    return body


def test_create_registers_the_sample_and_marks_it_in_the_repo_list(
    client: TestClient, home: Path
) -> None:
    data = _body(client.post("/api/demo"), 201)["data"]

    assert Path(data["path"]) == default_dir(home).absolute()
    assert data["created"] and data["registered"] and data["provider"] == "local"
    repos = _body(client.get("/api/repos"), 200)["data"]["repos"]
    assert [(r["id"], r["demo"], r["status"]) for r in repos] == [(data["repo_id"], True, "ok")]
    backlog = _body(client.get(f"/api/repos/{data['repo_id']}/backlog"), 200)["data"]
    assert [item["id"] for item in backlog["items"]] == ["DEMO"]

    again = _body(client.post("/api/demo"), 200)["data"]
    assert not again["created"] and again["repo_id"] == data["repo_id"]


def test_create_takes_no_options(client: TestClient) -> None:
    body = _body(client.post("/api/demo", json={"path": "/tmp/x"}), 400)
    assert body["error"]["code"] == "usage_error"


def test_a_folder_that_is_not_a_repo_is_not_registered(client: TestClient, home: Path) -> None:
    folder = default_dir(home)
    folder.mkdir(parents=True)
    (folder / "notes.txt").write_text("mine\n", encoding="utf-8")

    body = _body(client.post("/api/demo"), 422)

    assert body["error"]["code"] == "not_git"
    assert [p.name for p in folder.iterdir()] == ["notes.txt"]


def test_remove_drops_the_entry_and_the_folder(client: TestClient, home: Path) -> None:
    data = _body(client.post("/api/demo"), 201)["data"]

    removed = _body(client.delete("/api/demo"), 200)["data"]

    assert removed == {"path": data["path"], "repo_id": data["repo_id"], "deleted": True}
    assert not default_dir(home).exists()
    assert _body(client.get("/api/repos"), 200)["data"]["repos"] == []
    # nothing left: removing again changes nothing and still succeeds
    assert _body(client.delete("/api/demo"), 200)["data"]["deleted"] is False


def test_other_repos_are_not_the_demo_and_stay(
    client: TestClient, home: Path, tmp_path: Path
) -> None:
    from aifactory.demo import create_demo

    mine = create_demo(tmp_path / "mine", home=home)
    _body(client.post("/api/demo"), 201)

    repos = _body(client.get("/api/repos"), 200)["data"]["repos"]
    assert sorted(r["demo"] for r in repos) == [False, True]
    _body(client.delete("/api/demo"), 200)

    state, _warnings = Registry(home).snapshot()
    assert [e.id for e in state.repos] == [mine.repo_id]
    assert (tmp_path / "mine" / "textstats.py").is_file()


def test_a_live_run_keeps_the_sample(
    client: TestClient, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aifactory.demo as demo

    _body(client.post("/api/demo"), 201)
    monkeypatch.setattr(demo, "_live_runs", lambda _root: ["r1"])

    body = _body(client.delete("/api/demo"), 409)

    assert body["error"]["code"] == "run_in_progress"
    assert default_dir(home).is_dir()
    with pytest.raises(RepoError):
        remove_demo(home)
    assert len(Registry(home).snapshot()[0].repos) == 1
