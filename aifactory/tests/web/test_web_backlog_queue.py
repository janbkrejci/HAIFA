"""The kanban's queue for auto-continue: order and exclusion (``task_queue`` in the trace DB)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from backlog_fixture import A1, A2, A3, A4, B1, B2, B3, make_backlog_repo
from starlette.testclient import TestClient

from aifactory.backlog import parse_frontmatter
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


def _set_priority(root: Path, task_id: str, blockers: list[str]) -> None:
    store = TaskRunStore(root / ".factory" / "trace.db")
    try:
        store.set_priority(task_id, blockers, "run-1")
    finally:
        store.close()


def test_priority_goes_first_and_can_be_cleared(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    _check(client.post("/api/backlog/queue/order", json={"order": [A2]}), 200)
    _set_priority(root, B3, [B2])  # B3 blocked during a run on B2
    _set_priority(root, A4, [B1])  # a cancelled task has no priority
    data = _check(client.get("/api/backlog"), 200)["data"]
    tasks = data["tasks"]
    assert [t["id"] for t in tasks[:3]] == [B2, B3, A2]
    by_id = {t["id"]: t for t in tasks}
    assert by_id[B2]["priority_rank"] == 0 and by_id[B2]["priority_of"] == [B3]
    assert by_id[B3]["priority_blockers"] == [B2] and by_id[B3]["priority_rank"] == 1
    assert by_id[A2]["priority_rank"] is None and by_id[A2]["priority_of"] == []
    assert [p["task_id"] for p in data["priority"]] == [B3]
    assert data["priority_order"] == [B2, B3]
    # clearing the blocker's priority clears the record that gives it
    body = _check(client.delete(f"/api/backlog/tasks/{B2}/priority"), 200)
    assert body["data"] == {"task_id": B2, "cleared": [B3]}
    data = _check(client.get("/api/backlog"), 200)["data"]
    assert data["tasks"][0]["id"] == A2 and data["priority_order"] == []
    body = _check(client.delete("/api/backlog/tasks/M09-S01-T01/priority"), 404)
    assert body["error"]["code"] == "unknown_task"


def test_task_list_prints_the_priority(tmp_path: Path, capsys: Any) -> None:
    from aifactory.cli import main

    root = make_backlog_repo(tmp_path / "repo")
    _set_priority(root, B3, [B2])
    assert main(["task", "list", "--repo", str(root)]) == 0
    lines = {line.split()[0]: line for line in capsys.readouterr().out.splitlines()}
    assert "[přednostně #1]" in lines[B2]
    assert "[přednostně #2]" in lines[B3]
    assert "přednostně" not in lines[A2]
    assert main(["task", "list", "--json", "--repo", str(root)]) == 0
    tasks = {t["id"]: t for t in json.loads(capsys.readouterr().out)["data"]["tasks"]}
    assert tasks[B2]["priority"] == {"rank": 0, "of": [B3], "blockers": None}
    assert tasks[B3]["priority"] == {"rank": 1, "of": [B3], "blockers": [B2]}
    assert tasks[A2]["priority"] is None


def test_cancelling_a_task_drops_its_priority(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    _set_priority(root, B3, [B2])
    _set_priority(root, B2, [B1])
    url = f"/api/backlog/tasks/{B3}/edit"
    data = _check(client.post(url, json={"status": "cancelled"}), 200)["data"]
    assert data["task"]["board_state"] == "cancelled"
    assert [p.task_id for p in _prefs(root).priority] == [B2]


@pytest.mark.parametrize("task_id", [A1, A4])
def test_archive_round_trip_in_frontmatter(tmp_path: Path, task_id: str) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    before = {p: p.read_bytes() for p in (root / "backlog").rglob("*.md")}
    data = _check(client.get("/api/backlog"), 200)["data"]
    tasks = {t["id"]: t for t in data["tasks"]}
    assert tasks[A1]["archived"] is False
    assert tasks[A4]["archived"] is True
    assert tasks[B1]["archived"] is False
    path = root / tasks[task_id]["path"]
    default = task_id == A4
    for archived in (not default, default):
        body = _check(
            client.post(f"/api/backlog/tasks/{task_id}/archive", json={"archived": archived}), 200
        )
        assert body["data"] == {"task_id": task_id, "archived": archived}
        header, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        if archived == default:
            assert "archived" not in header
        else:
            assert header["archived"] is archived
        # A new app reads the file, with no trace database.
        fresh = _client(root, tmp_path)
        data = _check(fresh.get("/api/backlog"), 200)["data"]
        tasks = {t["id"]: t for t in data["tasks"]}
        assert tasks[task_id]["archived"] is archived
        detail = _check(fresh.get(f"/api/backlog/tasks/{task_id}"), 200)["data"]
        assert detail["task"]["archived"] is archived
        assert not (root / ".factory" / "trace.db").exists()
    assert {p: p.read_bytes() for p in (root / "backlog").rglob("*.md")} == before


def test_legacy_database_archive_does_not_override_frontmatter(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    store = TaskRunStore(root / ".factory" / "trace.db")
    try:
        store.set_archived(A1, True)
    finally:
        store.close()
    data = _check(_client(root, tmp_path).get("/api/backlog"), 200)["data"]
    assert next(t for t in data["tasks"] if t["id"] == A1)["archived"] is False


@pytest.mark.parametrize("task_id", [B1, "M09-S01-T01", "M01-S01"])
@pytest.mark.parametrize("archived", [True, False])
def test_archive_rejects_unknown_and_unfinished_tasks(
    tmp_path: Path, task_id: str, archived: bool
) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    status, code = (400, "invalid_value") if task_id == B1 else (404, "unknown_task")
    body = _check(
        client.post(f"/api/backlog/tasks/{task_id}/archive", json={"archived": archived}), status
    )
    assert body["error"]["code"] == code
    assert not (root / ".factory" / "trace.db").exists()


@pytest.mark.parametrize(
    "payload,code",
    [
        ({}, "invalid_value"),
        ({"archived": None}, "invalid_value"),
        ({"archived": 1}, "invalid_value"),
        ({"archived": "true"}, "invalid_value"),
        ({"archived": True, "extra": True}, "usage_error"),
    ],
)
def test_archive_validates_body(tmp_path: Path, payload: dict[str, Any], code: str) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    body = _check(client.post(f"/api/backlog/tasks/{A1}/archive", json=payload), 400)
    assert body["error"]["code"] == code
    assert not (root / ".factory" / "trace.db").exists()


@pytest.mark.parametrize(
    "kwargs,status,code",
    [
        (
            {"json": {"archived": True}, "headers": {"Origin": "http://evil.test"}},
            403,
            "cross_origin",
        ),
        (
            {"json": {"archived": True}, "headers": {"Sec-Fetch-Site": "cross-site"}},
            403,
            "cross_origin",
        ),
        ({"content": '{"archived": true}'}, 415, "unsupported_media_type"),
    ],
)
def test_archive_uses_write_guard(
    tmp_path: Path, kwargs: dict[str, Any], status: int, code: str
) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    body = _check(client.post(f"/api/backlog/tasks/{A1}/archive", **kwargs), status)
    assert body["error"]["code"] == code
    assert not (root / ".factory" / "trace.db").exists()
