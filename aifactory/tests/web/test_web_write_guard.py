"""The write guard: Origin, Sec-Fetch-Site and Content-Type checks on /api/ writes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from web_repo import git_repo

from aifactory.run.errors import TaskRunError
from aifactory.skill import envelope_problems
from aifactory.skill.codes import ERROR_CODES
from aifactory.web import create_app

BASE = "http://127.0.0.1:4700"
EVIL = "http://evil.example"


@pytest.fixture(name="calls")
def calls_fixture(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def spy_add(repo: Path, body: Any) -> tuple[dict[str, Any], list[str]]:
        calls.append("add")
        return {"spy": True}, []

    def spy_edit(repo: Path, task_id: str, body: Any) -> tuple[dict[str, Any], list[str]]:
        calls.append("edit")
        return {"spy": True}, []

    def spy_stop(repo: Path, run_id: str) -> Any:
        calls.append("stop")
        raise TaskRunError("unknown_run", f"no run {run_id}")

    monkeypatch.setattr("aifactory.web.backlog.add", spy_add)
    monkeypatch.setattr("aifactory.web.backlog.edit", spy_edit)
    monkeypatch.setattr("aifactory.run.stop.stop_run", spy_stop)
    return calls


@pytest.fixture(name="client")
def client_fixture(tmp_path: Path) -> TestClient:
    root = git_repo(tmp_path / "repo")
    return TestClient(create_app(root, static_dir=tmp_path / "nostatic"), base_url=BASE)


def _rejected(response: Any, status: int, code: str) -> None:
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    assert body["ok"] is False
    assert body["error"]["code"] == code


PASSING: dict[str, dict[str, Any]] = {
    "no headers (CLI)": {"json": {"title": "x"}},
    "same origin": {"json": {"title": "x"}, "headers": {"Origin": BASE}},
    "same origin, same-origin fetch": {
        "json": {"title": "x"},
        "headers": {"Origin": BASE, "Sec-Fetch-Site": "same-origin"},
    },
    "json with charset": {
        "content": b'{"title":"x"}',
        "headers": {"Content-Type": "application/json; charset=utf-8"},
    },
}

REJECTED: dict[str, tuple[dict[str, Any], int, str]] = {
    "foreign origin": ({"json": {"title": "x"}, "headers": {"Origin": EVIL}}, 403, "cross_origin"),
    "localhost vs 127.0.0.1": (
        {"json": {"title": "x"}, "headers": {"Origin": "http://localhost:4700"}},
        403,
        "cross_origin",
    ),
    "other port": (
        {"json": {"title": "x"}, "headers": {"Origin": "http://127.0.0.1:4701"}},
        403,
        "cross_origin",
    ),
    "null origin": ({"json": {"title": "x"}, "headers": {"Origin": "null"}}, 403, "cross_origin"),
    "cross-site": (
        {"json": {"title": "x"}, "headers": {"Sec-Fetch-Site": "cross-site"}},
        403,
        "cross_origin",
    ),
    "same-site": (
        {"json": {"title": "x"}, "headers": {"Sec-Fetch-Site": "same-site"}},
        403,
        "cross_origin",
    ),
    "same origin but cross-site": (
        {"json": {"title": "x"}, "headers": {"Origin": BASE, "Sec-Fetch-Site": "cross-site"}},
        403,
        "cross_origin",
    ),
    "form body": ({"data": {"title": "x"}}, 415, "unsupported_media_type"),
    "text/plain body": (
        {"content": b'{"title":"x"}', "headers": {"Content-Type": "text/plain"}},
        415,
        "unsupported_media_type",
    ),
    "multipart body": (
        {"files": {"f": ("a.txt", b"x", "text/plain")}},
        415,
        "unsupported_media_type",
    ),
    "body without content type": ({"content": b'{"title":"x"}'}, 415, "unsupported_media_type"),
}


@pytest.mark.parametrize("case", list(PASSING))
def test_write_passes(client: TestClient, calls: list[str], case: str) -> None:
    response = client.post("/api/backlog/tasks", **PASSING[case])
    assert response.status_code == 200, response.json()
    assert calls == ["add"]


@pytest.mark.parametrize("case", list(PASSING))
def test_edit_passes(client: TestClient, calls: list[str], case: str) -> None:
    response = client.post("/api/backlog/tasks/T01/edit", **PASSING[case])
    assert response.status_code == 200, response.json()
    assert calls == ["edit"]


@pytest.mark.parametrize("case", list(REJECTED))
def test_write_rejected(client: TestClient, calls: list[str], case: str) -> None:
    kwargs, status, code = REJECTED[case]
    _rejected(client.post("/api/backlog/tasks", **kwargs), status, code)
    assert calls == []


def test_empty_post_without_headers_passes(client: TestClient, calls: list[str]) -> None:
    response = client.post("/api/runs/r1/stop")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_run"
    assert calls == ["stop"]


def test_empty_post_from_the_dashboard_passes(client: TestClient, calls: list[str]) -> None:
    headers = {"Origin": BASE, "Sec-Fetch-Site": "same-origin"}
    response = client.post("/api/runs/r1/stop", headers=headers)
    assert response.status_code not in (403, 415)
    assert calls == ["stop"]


def test_empty_post_from_foreign_origin_is_rejected(client: TestClient, calls: list[str]) -> None:
    _rejected(client.post("/api/runs/r1/stop", headers={"Origin": EVIL}), 403, "cross_origin")
    assert calls == []


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_other_write_methods_are_checked(client: TestClient, method: str) -> None:
    response = client.request(method, "/api/backlog/tasks", headers={"Origin": EVIL})
    _rejected(response, 403, "cross_origin")


def test_get_is_not_checked(client: TestClient) -> None:
    headers = {"Origin": EVIL, "Sec-Fetch-Site": "cross-site"}
    assert client.get("/api/health", headers=headers).status_code == 200


def test_writes_outside_api_are_not_checked(client: TestClient) -> None:
    response = client.post("/", headers={"Origin": EVIL})
    assert response.status_code != 403


def test_host_check_stays(tmp_path: Path) -> None:
    root = git_repo(tmp_path / "repo")
    client = TestClient(create_app(root, static_dir=tmp_path / "nostatic"), base_url=EVIL)
    assert client.post("/api/runs/x/stop", headers={"Origin": EVIL}).status_code == 400


def test_codes_are_registered() -> None:
    assert "cross_origin" in ERROR_CODES
    assert "unsupported_media_type" in ERROR_CODES
