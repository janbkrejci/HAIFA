"""The dashboard notices a changed package: /api/code, blocked writes and the restart."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient
from web_repo import git_repo

from aifactory.codeprint import CodeWatch
from aifactory.web import create_app

BASE = "http://127.0.0.1:4700"


def _client(tmp_path: Path, restarts: list[str]) -> tuple[TestClient, Path]:
    root = git_repo(tmp_path / "repo")
    package = tmp_path / "package"
    package.mkdir()
    (package / "mod.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    app = create_app(
        root,
        static_dir=tmp_path / "nostatic",
        code_watch=CodeWatch(package, ttl=0.0),
        restart=lambda: restarts.append("restart"),
    )
    return TestClient(app, base_url=BASE), package


def test_fresh_dashboard_is_not_stale(tmp_path: Path) -> None:
    client, _ = _client(tmp_path, [])
    body = client.get("/api/code").json()
    assert body["ok"] is True
    assert body["data"]["stale"] is False
    assert body["data"]["started"] == body["data"]["current"]


def test_changed_package_blocks_writes_but_not_reads(tmp_path: Path) -> None:
    client, package = _client(tmp_path, [])
    (package / "mod.py").write_text("x = 22\n", encoding="utf-8", newline="\n")
    assert client.get("/api/code").json()["data"]["stale"] is True
    response = client.post("/api/backlog/commit", json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_code"
    assert "restartuj" in response.json()["error"]["message"].lower()
    assert client.get("/api/health").status_code == 200


def test_restart_answers_and_then_restarts(tmp_path: Path) -> None:
    restarts: list[str] = []
    client, package = _client(tmp_path, restarts)
    (package / "mod.py").write_text("x = 22\n", encoding="utf-8", newline="\n")
    response = client.post("/api/restart")
    assert response.status_code == 200
    assert response.json()["data"] == {"restarting": True}
    assert restarts == ["restart"]
