"""The dashboard ASGI app: the /api/ envelope, the static build and the host check."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient
from web_repo import git_repo

from aifactory import __version__
from aifactory.skill import envelope_problems
from aifactory.web import STATIC_DIR, create_app

BASE = "http://127.0.0.1:4700"


def _client(root: Path, static_dir: Path | None = None) -> TestClient:
    return TestClient(create_app(root, static_dir=static_dir), base_url=BASE)


def test_health_returns_version_and_repo(tmp_path: Path) -> None:
    root = git_repo(tmp_path / "repo")
    response = _client(root, tmp_path / "nostatic").get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert envelope_problems(body) == []
    assert body["ok"] is True
    assert body["data"] == {"version": __version__, "repo": str(root)}


def test_unknown_endpoint_is_not_found_envelope(tmp_path: Path) -> None:
    response = _client(tmp_path, tmp_path / "nostatic").get("/api/nope")
    assert response.status_code == 404
    body = response.json()
    assert envelope_problems(body) == []
    assert body["error"]["code"] == "not_found"


def test_wrong_method_is_envelope(tmp_path: Path) -> None:
    response = _client(tmp_path, tmp_path / "nostatic").post("/api/health")
    assert response.status_code == 405
    body = response.json()
    assert envelope_problems(body) == []
    assert body["ok"] is False


def test_serves_static_index(tmp_path: Path) -> None:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<p>hello dashboard</p>", encoding="utf-8", newline="\n")
    response = _client(tmp_path, static).get("/")
    assert response.status_code == 200
    assert "hello dashboard" in response.text


def test_missing_build_says_how_to_build(tmp_path: Path) -> None:
    response = _client(tmp_path, tmp_path / "nostatic").get("/")
    assert response.status_code == 503
    assert "just web-build" in response.text


def test_foreign_host_is_rejected(tmp_path: Path) -> None:
    app = create_app(tmp_path, static_dir=tmp_path / "nostatic")
    client = TestClient(app, base_url="http://evil.example")
    assert client.get("/api/health").status_code == 400


def test_network_address_accepts_any_host(tmp_path: Path) -> None:
    # factory obs --host 0.0.0.0: the dashboard is reached by the machine's LAN name or IP
    app = create_app(tmp_path, static_dir=tmp_path / "nostatic", allowed_hosts=["*"])
    client = TestClient(app, base_url="http://192.168.1.5:4700")
    assert client.get("/api/health").status_code == 200


def test_packaged_build_is_served(tmp_path: Path) -> None:
    assert (STATIC_DIR / "index.html").is_file()
    response = TestClient(create_app(tmp_path), base_url=BASE).get("/")
    assert response.status_code == 200
    assert '<div id="app">' in response.text
