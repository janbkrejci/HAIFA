"""The Backlog API: tree, kanban states, filters, task detail and writes through core."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from backlog_fixture import (
    A1,
    A2,
    A3,
    A4,
    B1,
    B2,
    B3,
    S1,
    S2,
    git,
    make_backlog_repo,
)
from starlette.testclient import TestClient

import aifactory.backlog
from aifactory.run.store import TaskRunStore
from aifactory.skill import envelope_problems
from aifactory.web import create_app
from aifactory.web.backlog import BOARD_STATES

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


def _states(data: Any) -> dict[str, str]:
    return {t["id"]: t["board_state"] for t in data["tasks"]}


def _file(root: Path, task_id: str) -> Path:
    [path] = list((root / "backlog").rglob(f"{task_id}-*.md"))
    return path


def _status_paths(root: Path) -> list[str]:
    return [line[3:] for line in git(root, "status", "--porcelain", "-uall").splitlines()]


def test_tree_follows_levels_and_board_states(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo", with_trace=True)
    data = _get(_client(root, tmp_path), "/api/backlog")["data"]
    assert data["levels"] == ["module", "step", "task"]
    module = data["items"][0]
    assert module["level"] == "module"
    assert "owner" not in module
    step = module["children"][0]
    assert step["level"] == "step"
    assert [t["id"] for t in step["children"]] == [A1, A2, A3, A4]
    m01_counts = {state: 0 for state in BOARD_STATES} | {
        "done": 1,
        "ready": 1,
        "blocked": 1,
        "cancelled": 1,
    }
    assert module["state_counts"] == m01_counts
    assert step["state_counts"] == m01_counts
    assert _states(data) == {
        A1: "done",
        A2: "ready",
        A3: "blocked",
        A4: "cancelled",
        B1: "todo",
        B2: "running",
        B3: "in review",
    }
    assert data["states"] == list(BOARD_STATES)
    assert data["state_counts"] == {state: 1 for state in BOARD_STATES} | {
        "awaiting merge": 0,
        "human": 0,
    }
    assert "owners" not in data
    assert {"custom-flow", "plan-build"} <= set(data["workflows"])
    assert [s["id"] for s in data["steps"]] == [S1, S2]
    assert data["steps"][0]["project"] == "M01"
    assert "module" not in data["steps"][0]
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id[A2]["blocks"] == [A3]
    assert by_id[B3]["last_run"] == "succeeded"
    assert "owner" not in by_id[B1]


def test_tree_gives_own_and_inherited_switches(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    module = _get(client, "/api/backlog")["data"]["items"][0]
    step = module["children"][0]
    assert (step["auto_continue"], step["effective_auto_continue"], step["can_toggle"]) == (
        None,
        False,
        True,
    )
    _post(client, "/api/backlog/containers/M01/auto-continue", {"mode": "on"})
    _post(client, f"/api/backlog/containers/{S1}/auto-merge", {"mode": "off"})
    module = _get(client, "/api/backlog")["data"]["items"][0]
    step = module["children"][0]
    assert (module["auto_continue"], module["effective_auto_continue"]) == (True, True)
    assert (step["auto_continue"], step["effective_auto_continue"]) == (None, True)
    assert (step["auto_merge"], step["effective_auto_merge"]) == (False, False)


def test_custom_levels(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo", levels=["area", "task"])
    data = _get(_client(root, tmp_path), "/api/backlog")["data"]
    assert data["levels"] == ["area", "task"]
    assert data["items"][0]["level"] == "area"
    assert [t["id"] for t in data["items"][0]["children"]] == ["A1-T01", "A1-T02"]
    assert [s["id"] for s in data["steps"]] == ["A1"]
    assert _states(data) == {"A1-T01": "ready", "A1-T02": "blocked"}


def test_names_give_title_and_level_of_every_code(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    data = _get(client, "/api/backlog/names")["data"]
    assert data["levels"] == ["module", "step", "task"]
    names = data["names"]
    assert names["M01"] == {"title": "Core", "level": "module"}
    assert names[S1] == {"title": "Model", "level": "step"}
    assert names[A1] == {"title": "Schema", "level": "task"}
    assert names[B3] == {"title": "Kanban", "level": "task"}
    assert set(names) == {"M01", "M02", S1, S2, A1, A2, A3, A4, B1, B2, B3}

    # a renamed task shows up at once (the backlog of the checkout, no commit needed)
    _post(client, f"/api/backlog/tasks/{A1}/edit", {"title": "Schema v2"})
    names = _get(client, "/api/backlog/names")["data"]["names"]
    assert names[A1] == {"title": "Schema v2", "level": "task"}


def test_names_follow_custom_levels(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo", levels=["area", "task"])
    data = _get(_client(root, tmp_path), "/api/backlog/names")["data"]
    assert data["levels"] == ["area", "task"]
    assert data["names"]["A1"] == {"title": "Area one", "level": "area"}
    assert data["names"]["A1-T01"]["level"] == "task"


def test_filters(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo", with_trace=True)
    client = _client(root, tmp_path)
    data = _get(client, "/api/backlog?status=ready")["data"]
    assert [t["id"] for t in data["tasks"]] == [A2]
    assert [m["id"] for m in data["items"]] == ["M01"]
    assert [c["id"] for c in data["items"][0]["children"]] == [S1]
    assert data["filters"] == {"status": "ready"}
    # the state counts ignore the status filter
    assert data["state_counts"]["todo"] == 1
    step_counts = data["items"][0]["children"][0]["state_counts"]
    assert (step_counts["ready"], step_counts["done"], step_counts["blocked"]) == (1, 1, 1)
    assert "owners" not in data

    # `?owner=` is ignored
    everything = _get(client, "/api/backlog")["data"]
    data = _get(client, "/api/backlog?owner=bob")["data"]
    assert [t["id"] for t in data["tasks"]] == [t["id"] for t in everything["tasks"]]
    assert [m["id"] for m in data["items"]] == ["M01", "M02"]
    assert data["filters"] == {"status": None}
    data = _get(client, "/api/backlog?owner=alice&status=todo")["data"]
    assert [t["id"] for t in data["tasks"]] == [B1]

    data = _get(client, "/api/backlog?status=running")["data"]
    assert [t["id"] for t in data["tasks"]] == [B2]
    data = _get(client, "/api/backlog?status=in%20review")["data"]
    assert [t["id"] for t in data["tasks"]] == [B3]

    body = _get(client, "/api/backlog?status=bogus", 400)
    assert body["error"]["code"] == "invalid_status"


def test_open_pr_waits_for_review_without_auto_merge(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo", with_trace=True)
    client = _client(root, tmp_path)
    _post(client, f"/api/backlog/containers/{S2}/auto-merge", {"mode": "off"})
    data = _get(client, "/api/backlog")["data"]
    assert _states(data)[B3] == "in review"
    assert data["state_counts"]["awaiting merge"] == 0


def test_open_pr_waits_for_automerge_with_inherited_auto_merge(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo", with_trace=True)
    client = _client(root, tmp_path)
    _post(client, "/api/backlog/containers/M02/auto-merge", {"mode": "on"})
    data = _get(client, "/api/backlog")["data"]
    assert _states(data)[B3] == "awaiting merge"
    assert (data["state_counts"]["in review"], data["state_counts"]["awaiting merge"]) == (0, 1)
    module = next(m for m in data["items"] if m["id"] == "M02")
    assert module["state_counts"]["awaiting merge"] == 1
    data = _get(client, "/api/backlog?status=awaiting%20merge")["data"]
    assert [t["id"] for t in data["tasks"]] == [B3]
    assert _get(client, "/api/backlog?status=in%20review")["data"]["tasks"] == []
    detail = _get(client, f"/api/backlog/tasks/{B3}")["data"]
    assert detail["task"]["board_state"] == "awaiting merge"

    # the task's own switch wins over the inherited one
    _post(client, f"/api/backlog/tasks/{B3}/edit", {"auto_merge": False})
    assert _states(_get(client, "/api/backlog")["data"])[B3] == "in review"


def test_failed_auto_merge_puts_the_pr_back_to_review(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo", with_trace=True)
    client = _client(root, tmp_path)
    _post(client, f"/api/backlog/containers/{S2}/auto-merge", {"mode": "on"})
    assert _states(_get(client, "/api/backlog")["data"])[B3] == "awaiting merge"
    store = TaskRunStore(root / ".factory" / "trace.db")
    try:
        store.update_pr(f"factory/{B3}-1", auto_merge_error="checks_failing: ci")
    finally:
        store.close()
    assert _states(_get(client, "/api/backlog")["data"])[B3] == "in review"


def test_no_trace_db_means_no_runtime_states(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    data = _get(_client(root, tmp_path), "/api/backlog")["data"]
    assert _states(data)[B2] == "ready"
    assert _states(data)[B3] == "ready"
    assert not (root / ".factory" / "trace.db").exists()


@pytest.mark.parametrize(
    ("state", "pr_error", "expected"),
    [
        ("succeeded", None, "running"),
        ("succeeded", "push failed", "ready"),
        ("failed", None, "ready"),
        ("aborted", None, "ready"),
    ],
)
def test_run_to_publication_handoff(
    tmp_path: Path, state: str, pr_error: str | None, expected: str
) -> None:
    from aifactory.web.backlog import backlog_view

    root = make_backlog_repo(tmp_path / "repo", with_trace=True)
    store = TaskRunStore(root / ".factory/trace.db")
    try:
        store.finish("r-b2", state, None, None)
        store.set_pr_error("r-b2", pr_error)
    finally:
        store.close()
    data, warnings = backlog_view(root)
    assert warnings == []
    assert _states(data)[B2] == expected


@pytest.mark.parametrize("same_branch", [True, False])
def test_success_with_closed_pr_is_ready(tmp_path: Path, same_branch: bool) -> None:
    from aifactory.web.backlog import backlog_view

    root = make_backlog_repo(tmp_path / "repo", with_trace=True)
    store = TaskRunStore(root / ".factory/trace.db")
    try:
        store.update_pr(f"factory/{B3}-1", state="closed")
        if not same_branch:
            store.conn.execute(
                "UPDATE task_prs SET branch = 'factory/older-branch' WHERE task_id = ?", (B3,)
            )
    finally:
        store.close()
    data, warnings = backlog_view(root)
    assert warnings == []
    assert _states(data)[B3] == ("ready" if same_branch else "running")
    assert data["state_counts"]["running"] == 1 + (not same_branch)
    assert data["state_counts"]["in review"] == data["state_counts"]["awaiting merge"] == 0


def test_merge_handoff_and_reopening(tmp_path: Path) -> None:
    from aifactory.web.backlog import backlog_view

    root = make_backlog_repo(tmp_path / "repo", with_trace=True)
    store = TaskRunStore(root / ".factory/trace.db")
    try:
        store.update_pr(f"factory/{B3}-1", state="merged")
    finally:
        store.close()
    assert _states(backlog_view(root)[0])[B3] == "done"
    path = _file(root, B3)
    path.write_text(
        path.read_text(encoding="utf-8") + "\n## Běhy\n- PR https://example.test/pr/3 merged\n",
        encoding="utf-8",
    )
    assert _states(backlog_view(root)[0])[B3] == "ready"


@pytest.mark.parametrize("missing", [("branch",), ("branch", "pr_error")])
@pytest.mark.parametrize("run_state", ["succeeded", "running"])
def test_legacy_merge_handoff_and_reopening(
    tmp_path: Path, missing: tuple[str, ...], run_state: str
) -> None:
    from aifactory.web.backlog import backlog_view

    root = make_backlog_repo(tmp_path / "repo", with_trace=True)
    with sqlite3.connect(root / ".factory/trace.db") as conn:
        conn.execute(
            "UPDATE task_runs SET state = ?, pid = ? WHERE run_id = 'r-b3'",
            (run_state, os.getpid()),
        )
        conn.execute("UPDATE task_prs SET state = 'merged' WHERE task_id = ?", (B3,))
        for column in missing:
            conn.execute(f"ALTER TABLE task_runs DROP COLUMN {column}")
    data, warnings = backlog_view(root)
    assert warnings == []
    assert _states(data)[B3] == ("done" if run_state == "succeeded" else "running")
    path = _file(root, B3)
    path.write_text(
        path.read_text(encoding="utf-8") + "\n## Běhy\n- PR https://example.test/pr/3 merged\n",
        encoding="utf-8",
    )
    reopened, warnings = backlog_view(root)
    assert warnings == []
    assert _states(reopened)[B3] == ("ready" if run_state == "succeeded" else "running")


def test_ended_process_stays_running_until_reaped(tmp_path: Path) -> None:
    from overview_fixture import dead_pid

    from aifactory.web.backlog import backlog_view

    root = make_backlog_repo(tmp_path / "repo", with_trace=True)
    with dead_pid() as pid:
        store = TaskRunStore(root / ".factory/trace.db")
        try:
            store.conn.execute("UPDATE task_runs SET pid = ? WHERE run_id = 'r-b2'", (pid,))
        finally:
            store.close()
        assert _states(backlog_view(root)[0])[B2] == "running"
        store = TaskRunStore(root / ".factory/trace.db")
        try:
            assert store.get("r-b2").state == "running"  # type: ignore[union-attr]
        finally:
            store.close()


def test_task_detail(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo", with_trace=True)
    client = _client(root, tmp_path)
    data = _get(client, f"/api/backlog/tasks/{A3}")["data"]
    assert data["task"]["id"] == A3
    assert "owner" not in data["task"]
    assert "Zadání Writer." in data["body"]
    assert data["depends"] == [{"id": A2, "kind": "task", "title": "Loader", "state": "ready"}]
    assert data["blocks"] == []

    data = _get(client, f"/api/backlog/tasks/{A2}")["data"]
    assert data["blocks"] == [{"id": A3, "title": "Writer", "board_state": "blocked"}]

    data = _get(client, f"/api/backlog/tasks/{B3}")["data"]
    assert len(data["runs"]) == 1
    assert data["runs"][0]["state"] == "succeeded"
    assert len(data["prs"]) == 1
    assert data["prs"][0]["url"] == "https://example.test/pr/3"

    body = _get(client, "/api/backlog/tasks/NOPE", 404)
    assert body["error"]["code"] == "unknown_task"


def test_add_task_writes_only_backlog_and_does_not_commit(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    payload = {
        "step": S1,
        "title": "Nový task",
        "workflow": "plan",
        "depends_on": [A1],
        "body": "Text",
    }
    data = _post(_client(root, tmp_path), "/api/backlog/tasks", payload)["data"]
    assert data["action"] == "add"
    assert data["changed"] is True
    assert data["task"]["id"] == "M01-S01-T05"
    assert data["task"]["board_state"] == "ready"
    text = (root / data["path"]).read_text(encoding="utf-8")
    assert "status: todo" in text
    assert "workflow: plan" in text
    paths = _status_paths(root)
    assert paths and all(p.startswith("backlog/") for p in paths)
    assert git(root, "rev-list", "--count", "HEAD").strip() == "1"


def test_add_rejects_broken_backlog(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    payload = {"step": S1, "title": "Broken", "depends_on": ["NOPE"]}
    body = _post(_client(root, tmp_path), "/api/backlog/tasks", payload, 422)
    assert body["error"]["code"] == "backlog_invalid"
    assert body["error"]["issues"][0]["code"] == "unknown_ref"
    assert _status_paths(root) == []

    body = _post(_client(root, tmp_path), "/api/backlog/tasks", {"step": "X", "title": "a"}, 404)
    assert body["error"]["code"] == "unknown_step"


def test_commit_backlog_to_base(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    git(root, "branch", "-M", "main")
    client = _client(root, tmp_path)
    added = _post(client, "/api/backlog/tasks", {"step": S1, "title": "Nový task"})["data"]
    data = _post(client, "/api/backlog/commit", {})["data"]
    assert data["committed"] is True
    assert data["paths"] == [added["path"]]
    assert _status_paths(root) == []
    assert git(root, "rev-list", "--count", "HEAD").strip() == "2"
    assert _post(client, "/api/backlog/commit", {"message": "x"})["data"]["committed"] is False
    body = _post(client, "/api/backlog/commit", {"nope": 1}, 400)
    assert body["error"]["code"] == "usage_error"

    git(root, "switch", "-q", "-c", "feature")
    _post(client, "/api/backlog/tasks", {"step": S1, "title": "Další"})
    body = _post(client, "/api/backlog/commit", {}, 409)
    assert body["error"]["code"] == "not_on_base"


def test_status_lists_backlog_files_not_committed(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    git(root, "branch", "-M", "main")
    client = _client(root, tmp_path)
    data = _get(client, "/api/backlog/status")["data"]
    assert (data["base"], data["clean"], data["changes"]) == ("main", True, [])
    assert data["commit"] == git(root, "rev-parse", "HEAD").strip()

    _post(client, f"/api/backlog/containers/{S1}/auto-continue", {"mode": "on"})
    added = _post(client, "/api/backlog/tasks", {"step": S1, "title": "Nový task"})["data"]
    (root / "README.md").write_text("outside the backlog\n", encoding="utf-8", newline="\n")
    data = _get(client, "/api/backlog/status")["data"]
    assert data["clean"] is False
    assert data["changes"] == [  # sorted by path; README.md is outside the backlog
        {"path": added["path"], "status": "untracked"},
        {"path": "backlog/M01-core/S01-model/index.md", "status": "modified"},
    ]

    _post(client, "/api/backlog/commit", {})
    data = _get(client, "/api/backlog/status")["data"]
    assert (data["clean"], data["changes"]) == (True, [])
    assert data["commit"] == git(root, "rev-parse", "HEAD").strip()


def test_edit_and_assign_workflow(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    url = f"/api/backlog/tasks/{B1}/edit"
    data = _post(client, url, {"title": "Rozvržení", "workflow": "custom-flow"})["data"]
    assert data["task"]["workflow"] == "custom-flow"
    assert data["task"]["own_workflow"] == "custom-flow"
    assert data["task"]["board_state"] == "ready"
    text = _file(root, B1).read_text(encoding="utf-8")
    assert "title: Rozvržení" in text
    assert "workflow: custom-flow" in text

    data = _post(client, url, {"clear_workflow": True})["data"]
    assert "workflow:" not in _file(root, B1).read_text(encoding="utf-8")
    assert data["task"]["board_state"] == "ready"  # no workflow key: the default workflow

    data = _post(client, url, {"status": "cancelled"})["data"]
    assert data["task"]["board_state"] == "cancelled"

    assert _post(client, url, {"status": "done"}, 400)["error"]["code"] == "invalid_status"
    assert _post(client, url, {}, 400)["error"]["code"] == "no_changes"
    assert git(root, "rev-list", "--count", "HEAD").strip() == "1"


def test_link_add_remove_and_cycle(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    before = _file(root, A1).read_bytes()
    body = _post(client, f"/api/backlog/tasks/{A1}/link", {"depends_on": [A3]}, 422)
    assert body["error"]["code"] == "backlog_invalid"
    assert "cycle" in [i["code"] for i in body["error"]["issues"]]
    assert _file(root, A1).read_bytes() == before

    _post(client, f"/api/backlog/tasks/{B1}/link", {"depends_on": [A2]})
    detail = _get(client, f"/api/backlog/tasks/{A2}")["data"]
    assert B1 in [b["id"] for b in detail["blocks"]]

    _post(client, f"/api/backlog/tasks/{B1}/link", {"depends_on": [A2], "remove": True})
    detail = _get(client, f"/api/backlog/tasks/{A2}")["data"]
    assert B1 not in [b["id"] for b in detail["blocks"]]


def test_bad_bodies(tmp_path: Path) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    client = _client(root, tmp_path)
    url = "/api/backlog/tasks"
    response = client.post(url, content=b"not json", headers={"Content-Type": "application/json"})
    assert _check(response, 400)["error"]["code"] == "usage_error"
    assert _post(client, url, [1, 2], 400)["error"]["code"] == "usage_error"
    assert _post(client, url, {"step": S1, "title": 5}, 400)["error"]["code"] == "invalid_value"
    body = _post(client, url, {"step": S1, "title": "a", "color": "red"}, 400)
    assert body["error"]["code"] == "usage_error"
    assert "color" in body["error"]["message"]
    assert _post(client, url, {"title": "a"}, 400)["error"]["code"] == "usage_error"
    edit = f"/api/backlog/tasks/{B1}/edit"
    assert _post(client, edit, {"writes": "a"}, 400)["error"]["code"] == "invalid_value"
    assert _post(client, edit, {"clear_workflow": 1}, 400)["error"]["code"] == "invalid_value"
    assert _status_paths(root) == []


def test_api_calls_core_functions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_backlog_repo(tmp_path / "repo")
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def spy(name: str) -> Any:
        original = getattr(aifactory.backlog, name)

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            calls.append((name, args, kwargs))
            return original(*args, **kwargs)

        return wrapper

    for name in ("add_task", "edit_task", "link_task"):
        monkeypatch.setattr(f"aifactory.backlog.{name}", spy(name))
    client = _client(root, tmp_path)
    _post(client, "/api/backlog/tasks", {"step": S2, "title": "Filtr", "writes": ["web/"]})
    _post(client, f"/api/backlog/tasks/{B1}/edit", {"workflow": "plan"})
    _post(client, f"/api/backlog/tasks/{B1}/link", {"related": [B2]})
    assert [c[0] for c in calls] == ["add_task", "edit_task", "link_task"]
    assert calls[0][1] == (root, S2, "Filtr")
    assert calls[0][2] == {
        "task_id": None,
        "slug": None,
        "workflow": None,
        "writes": ["web/"],
        "depends_on": None,
        "related": None,
        "body": "",
        "parameters": None,
        "assignee": None,
    }
    assert calls[1][1] == (root, B1)
    assert calls[1][2] == {
        "title": None,
        "status": None,
        "workflow": "plan",
        "clear_workflow": False,
        "writes": None,
        "clear_writes": False,
        "auto_merge": None,
        "clear_auto_merge": False,
        "parameters": None,
        "body": None,
        "depends_on": None,
        "related": None,
        "assignee": None,
        "clear_assignee": False,
    }
    assert calls[2][1] == (root, B1)
    assert calls[2][2] == {"depends_on": None, "related": [B2], "remove": False}
