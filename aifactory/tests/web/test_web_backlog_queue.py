"""The kanban's queue for auto-continue: order and exclusion (``task_queue`` in the trace DB)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backlog_fixture import A2, A3, B1, B2, B3, make_backlog_repo
from starlette.testclient import TestClient

from aifactory.run.store import TaskRunStore
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


def _prefs(root: Path) -> Any:
    store = TaskRunStore(root / ".factory" / "trace.db")
    try:
        return store.queue_prefs()
    finally:
        store.close()


def test_order_is_saved_and_returned_by_the_backlog(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    body = _check(client.post("/api/backlog/queue/order", json={"order": [B3, A2]}), 200)
    assert body["data"] == {"order": [B3, A2]}
    assert _prefs(root).order == (B3, A2)
    data = _check(client.get("/api/backlog"), 200)["data"]
    tasks = data["tasks"]
    assert [t["id"] for t in tasks[:2]] == [B3, A2]
    ranks = {t["id"]: t["queue_rank"] for t in tasks}
    assert ranks[B3] == 0 and ranks[A2] == 1 and ranks[A3] is None
    assert all(t["auto_excluded"] is False for t in tasks)


def test_exclusion_is_saved_and_returned(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    url = f"/api/backlog/tasks/{B2}/auto-exclude"
    body = _check(client.post(url, json={"excluded": True}), 200)
    assert body["data"] == {"task_id": B2, "excluded": True}
    data = _check(client.get("/api/backlog"), 200)["data"]
    excluded = {t["id"] for t in data["tasks"] if t["auto_excluded"]}
    assert excluded == {B2}
    _check(client.post(url, json={"excluded": False}), 200)
    assert _prefs(root).excluded == frozenset()


def test_bad_requests_are_rejected(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    order = "/api/backlog/queue/order"
    body = _check(client.post(order, json={"order": ["M09-S01-T01"]}), 404)
    assert body["error"]["code"] == "unknown_task"
    body = _check(client.post(order, json={"order": "x"}), 400)
    assert body["error"]["code"] == "invalid_value"
    body = _check(client.post(order, json={"order": [B1, B1]}), 400)
    assert body["error"]["code"] == "invalid_value"
    body = _check(client.post(order, json={"order": [], "x": 1}), 400)
    assert body["error"]["code"] == "usage_error"
    exclude = f"/api/backlog/tasks/{B1}/auto-exclude"
    body = _check(client.post(exclude, json={"excluded": "yes"}), 400)
    assert body["error"]["code"] == "invalid_value"
    body = _check(
        client.post("/api/backlog/tasks/M09-S01-T01/auto-exclude", json={"excluded": True}),
        404,
    )
    assert body["error"]["code"] == "unknown_task"


def test_writes_from_another_origin_are_refused(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    response = client.post(
        "/api/backlog/queue/order",
        json={"order": [B3]},
        headers={"Origin": "http://evil.test"},
    )
    assert response.status_code == 403
