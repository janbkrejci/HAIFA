"""The Backlog API: dependency graph of a module or step and the auto-continue switch."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from backlog_fixture import A1, A2, A3, A4, B1, B2, B3, M01, S1, S2, git, make_backlog_repo
from starlette.testclient import TestClient

from aifactory.backlog import Container, iter_containers, load_backlog
from aifactory.cli import main
from aifactory.skill import envelope_problems
from aifactory.web import create_app

BASE = "http://127.0.0.1:4700"


def _client(root: Path, tmp_path: Path) -> TestClient:
    return TestClient(create_app(root, static_dir=tmp_path / "nostatic"), base_url=BASE)


def _check(response: Any, status: int) -> Any:
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    return body


def _get(client: TestClient, url: str, status: int = 200) -> Any:
    return _check(client.get(url), status)


def _post(client: TestClient, url: str, payload: Any, status: int = 200) -> Any:
    return _check(client.post(url, json=payload), status)


def _container(root: Path, container_id: str) -> Container:
    backlog = load_backlog(root)
    return next(c for c in iter_containers(backlog.containers) if c.id == container_id)


def _status_paths(root: Path) -> list[str]:
    return [line[3:] for line in git(root, "status", "--porcelain", "-uall").splitlines()]


def test_step_graph_nodes_and_edges(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo", with_trace=True)
    client = _client(root, tmp_path)
    data = _get(client, f"/api/backlog/containers/{S1}/graph")["data"]
    assert data["container"] == {
        "id": S1,
        "title": "Model",
        "level": "step",
        "path": "backlog/M01-core/S01-model",
        "auto_continue": None,
        "effective_auto_continue": False,
        "auto_merge": None,
        "effective_auto_merge": False,
        "can_toggle": True,
    }
    assert [n["id"] for n in data["nodes"]] == [A1, A2, A3, A4]
    assert data["edges"] == [{"from": A1, "to": A2}, {"from": A2, "to": A3}]
    states = {t["id"]: t["board_state"] for t in _get(client, "/api/backlog")["data"]["tasks"]}
    for node in data["nodes"]:
        assert node["board_state"] == states[node["id"]]
        assert node["external"] is False
        assert node["step"] == S1


def test_module_graph_and_external_dependency(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo", with_trace=True)
    client = _client(root, tmp_path)
    module = _get(client, f"/api/backlog/containers/{M01}/graph")["data"]
    assert [n["id"] for n in module["nodes"]] == [A1, A2, A3, A4]
    _post(client, f"/api/backlog/tasks/{B1}/link", {"depends_on": [A2, M01]})
    data = _get(client, f"/api/backlog/containers/{S2}/graph")["data"]
    by_id = {n["id"]: n for n in data["nodes"]}
    assert list(by_id) == [B1, B2, B3, M01, A2]
    assert by_id[B2]["board_state"] == "running"
    assert by_id[A2]["external"] is True
    assert by_id[A2]["kind"] == "task"
    assert by_id[A2]["board_state"] == "ready"
    assert by_id[M01]["kind"] == "container"
    assert by_id[M01]["board_state"] is None
    assert by_id[M01]["state"] == "1/3"
    assert {"from": A2, "to": B1} in data["edges"]


def test_unknown_container(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    body = _get(_client(root, tmp_path), "/api/backlog/containers/M09/graph", 404)
    assert body["error"]["code"] == "unknown_container"


def test_auto_continue_writes_like_the_cli(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    twin = tmp_path / "twin"
    shutil.copytree(root, twin)
    client = _client(root, tmp_path)
    url = f"/api/backlog/containers/{S1}/auto-continue"
    data = _post(client, url, {"mode": "on"})["data"]
    assert data["changed"] is True
    assert data["auto_continue"] is True
    assert data["effective_auto_continue"] is True
    assert data["id"] == S1 and data["level"] == "step"
    assert _container(root, S1).defaults.get("auto_continue") is True
    assert _status_paths(root) == ["backlog/M01-core/S01-model/index.md"]
    assert main(["backlog", "auto-continue", S1, "--on", "--repo", str(twin)]) == 0
    index = "backlog/M01-core/S01-model/index.md"
    assert (root / index).read_text() == (twin / index).read_text()

    assert _post(client, url, {"mode": "on"})["data"]["changed"] is False
    _post(client, url, {"mode": "off"})
    assert _container(root, S1).defaults.get("auto_continue") is False
    data = _post(client, url, {"mode": "inherit"})["data"]
    assert data["auto_continue"] is None
    assert "auto_continue" not in _container(root, S1).defaults
    assert _status_paths(root) == []

    tree = _get(client, "/api/backlog")["data"]["items"]
    assert all("auto_continue" in c for c in tree)
    _post(client, f"/api/backlog/containers/{M01}/auto-continue", {"mode": "on"})
    step = _get(client, f"/api/backlog/containers/{S1}/graph")["data"]["container"]
    assert step["auto_continue"] is None
    assert step["effective_auto_continue"] is True


def test_auto_merge_writes_like_the_cli(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    twin = tmp_path / "twin"
    shutil.copytree(root, twin)
    client = _client(root, tmp_path)
    url = f"/api/backlog/containers/{S1}/auto-merge"
    data = _post(client, url, {"mode": "on"})["data"]
    assert data["changed"] is True
    assert (data["auto_merge"], data["effective_auto_merge"]) == (True, True)
    assert data["id"] == S1 and data["level"] == "step"
    assert _container(root, S1).defaults.get("auto_merge") is True
    assert main(["backlog", "auto-merge", S1, "--on", "--repo", str(twin)]) == 0
    index = "backlog/M01-core/S01-model/index.md"
    assert (root / index).read_text() == (twin / index).read_text()

    tree = _get(client, "/api/backlog")["data"]["items"]
    assert all("auto_merge" in c for c in tree)
    task = _get(client, f"/api/backlog/tasks/{A1}")["data"]["task"]
    assert (task["own_auto_merge"], task["effective_auto_merge"]) == (None, True)

    edit = f"/api/backlog/tasks/{A1}/edit"
    _post(client, edit, {"auto_merge": False})
    task = _get(client, f"/api/backlog/tasks/{A1}")["data"]["task"]
    assert (task["own_auto_merge"], task["effective_auto_merge"]) == (False, False)
    _post(client, edit, {"clear_auto_merge": True})
    task = _get(client, f"/api/backlog/tasks/{A1}")["data"]["task"]
    assert (task["own_auto_merge"], task["effective_auto_merge"]) == (None, True)
    assert _post(client, edit, {"auto_merge": "yes"}, 400)["error"]["code"] == "invalid_value"

    data = _post(client, url, {"mode": "inherit"})["data"]
    assert data["auto_merge"] is None
    _post(client, f"/api/backlog/containers/{M01}/auto-merge", {"mode": "on"})
    step = _get(client, f"/api/backlog/containers/{S1}/graph")["data"]["container"]
    assert (step["auto_merge"], step["effective_auto_merge"]) == (None, True)
    assert step["auto_continue"] is None
    assert _post(client, url, {"mode": "maybe"}, 400)["error"]["code"] == "invalid_value"
    body = _post(client, "/api/backlog/containers/M09/auto-merge", {"mode": "on"}, 404)
    assert body["error"]["code"] == "unknown_container"


def test_auto_continue_rejects_bad_input(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    url = f"/api/backlog/containers/{S1}/auto-continue"
    assert _post(client, url, {"mode": "maybe"}, 400)["error"]["code"] == "invalid_value"
    assert _post(client, url, {"bogus": 1}, 400)["error"]["code"] == "usage_error"
    assert _post(client, url, {}, 400)["error"]["code"] == "usage_error"
    body = _post(client, "/api/backlog/containers/M09/auto-continue", {"mode": "on"}, 404)
    assert body["error"]["code"] == "unknown_container"
    assert _status_paths(root) == []
