"""The Backlog API for projects and steps: detail with origins, add and edit through core."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from backlog_fixture import git, make_backlog_repo
from starlette.testclient import TestClient

from aifactory.skill import envelope_problems
from aifactory.web import create_app

BASE = "http://127.0.0.1:4700"
M01_INDEX = "backlog/M01-core/index.md"
S01_INDEX = "backlog/M01-core/S01-model/index.md"


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


def _header(root: Path, rel: str) -> dict[str, Any]:
    text = (root / rel).read_text(encoding="utf-8")
    loaded = yaml.safe_load(text.split("---\n")[1])
    assert isinstance(loaded, dict)
    return loaded


def _snapshot(root: Path) -> dict[str, bytes]:
    backlog = root / "backlog"
    return {
        p.relative_to(root).as_posix(): p.read_bytes() if p.is_file() else b"<dir>"
        for p in backlog.rglob("*")
    }


def test_detail_has_own_and_effective_values_with_origin(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    (root / ".factory/config.yaml").write_text(
        "base: main\nlevels: [module, step, task]\nbacklog_dir: backlog\ndocs_dir: docs\n",
        encoding="utf-8",
        newline="\n",
    )
    client = _client(root, tmp_path)
    data = _get(client, "/api/backlog/containers/M01-S01")["data"]
    container = data["container"]
    assert container["id"] == "M01-S01"
    assert container["title"] == "Model"
    assert container["level"] == "step"
    assert container["parent"] == "M01"
    assert container["own"] == {}
    assert "auto_continue" in data["editable_keys"]
    effective = container["effective"]
    assert effective["workflow"] == {
        "value": "plan-build",
        "origin": {"source": "inherited", "level": "module", "id": "M01", "path": M01_INDEX},
    }
    assert "test" not in effective
    assert effective["docs_dir"] == {
        "value": "docs",
        "origin": {"source": "config", "path": ".factory/config.yaml", "key": "docs_dir"},
    }
    assert effective["auto_continue"] == {"value": False, "origin": {"source": "default"}}
    assert effective["source"] == {"value": None, "origin": None}

    project = _get(client, "/api/backlog/containers/M01")["data"]["container"]
    assert project["own"] == {"workflow": "plan-build"}
    assert project["extra"] == {"owner": "alice"}
    assert project["effective"]["workflow"]["origin"]["source"] == "own"
    body = _get(client, "/api/backlog/containers/M09", 404)
    assert body["error"]["code"] == "unknown_container"


def test_add_project_and_step(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    data = _post(client, "/api/backlog/containers", {"id": "M03", "title": "Reporty"})["data"]
    assert data["action"] == "add"
    assert data["path"] == "backlog/M03-reporty/index.md"
    assert data["container"]["level"] == "module"
    payload = {"parent": "M03", "id": "M03-S01", "title": "Export", "body": "Popis."}
    data = _post(client, "/api/backlog/containers", payload)["data"]
    assert data["path"] == "backlog/M03-reporty/S01-export/index.md"
    assert data["container"]["body"].strip() == "Popis."
    assert _header(root, data["path"]) == {"id": "M03-S01", "title": "Export"}
    # nothing is committed
    status = git(root, "status", "--porcelain", "-uall")
    assert "backlog/M03-reporty/S01-export/index.md" in status
    assert git(root, "log", "--oneline").count("\n") == 1


def test_add_rejects_invalid_duplicate_and_foreign_codes(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    before = _snapshot(root)
    body = _post(client, "/api/backlog/containers", {"id": "M 1", "title": "X"}, 400)
    assert body["error"]["code"] == "invalid_id"
    body = _post(client, "/api/backlog/containers", {"id": "M01", "title": "X"}, 422)
    assert body["error"]["code"] == "backlog_invalid"
    assert [i["code"] for i in body["error"]["issues"]] == ["duplicate_id"]
    payload = {"parent": "M01", "id": "M02-S07", "title": "X"}
    assert _post(client, "/api/backlog/containers", payload, 400)["error"]["code"] == "invalid_id"
    payload = {"parent": "M01", "id": "S01", "title": "X"}
    body = _post(client, "/api/backlog/containers", payload, 422)
    assert [i["code"] for i in body["error"]["issues"]] == ["duplicate_id"]
    body = _post(client, "/api/backlog/containers", {"title": "X"}, 400)
    assert body["error"]["code"] == "usage_error"
    body = _post(client, "/api/backlog/containers", {"id": "M04", "title": "X", "x": 1}, 400)
    assert body["error"]["code"] == "usage_error"
    assert _snapshot(root) == before


def test_edit_sets_clears_and_keeps_unknown_keys(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    payload = {
        "title": "Jádro",
        "writes": ["src/"],
        "source": "src/",
        "target": "src/",
        "specs_dir": "specs/core",
        "docs_dir": "docs/core",
        "auto_continue": True,
    }
    data = _post(client, "/api/backlog/containers/M01/edit", payload)["data"]
    assert data["changed"] is True
    header = _header(root, M01_INDEX)
    assert header == {
        "id": "M01",
        "title": "Jádro",
        "owner": "alice",
        "workflow": "plan-build",
        "writes": ["src/"],
        "source": "src/",
        "target": "src/",
        "specs_dir": "specs/core",
        "docs_dir": "docs/core",
        "auto_continue": True,
    }
    assert data["container"]["effective"]["specs_dir"]["origin"]["source"] == "own"

    step = _post(client, "/api/backlog/containers/M01-S01/edit", {"workflow": "plan"})["data"]
    assert step["container"]["effective"]["workflow"]["origin"]["id"] == "M01-S01"
    assert step["container"]["effective"]["specs_dir"]["origin"] == {
        "source": "inherited",
        "level": "module",
        "id": "M01",
        "path": M01_INDEX,
    }

    payload2: dict[str, Any] = {"workflow": None, "clear": ["source", "target"]}
    _post(client, "/api/backlog/containers/M01/edit", payload2)
    header = _header(root, M01_INDEX)
    assert "workflow" not in header and "source" not in header and "target" not in header
    assert header["owner"] == "alice"
    assert _header(root, S01_INDEX)["workflow"] == "plan"


def test_edit_rejects_bad_input(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    before = _snapshot(root)
    body = _post(client, "/api/backlog/containers/M01/edit", {"owner": "x"}, 400)
    assert body["error"]["code"] == "usage_error"
    body = _post(client, "/api/backlog/containers/M01/edit", {}, 400)
    assert body["error"]["code"] == "no_changes"
    body = _post(client, "/api/backlog/containers/M01/edit", {"auto_continue": "on"}, 400)
    assert body["error"]["code"] == "invalid_value"
    body = _post(client, "/api/backlog/containers/M01/edit", {"docs_dir": "/abs"}, 422)
    assert body["error"]["code"] == "backlog_invalid"
    body = _post(client, "/api/backlog/containers/M09/edit", {"title": "X"}, 404)
    assert body["error"]["code"] == "unknown_container"
    assert _snapshot(root) == before
