"""The Runs API: list, totals, detail, events and stop, over a trace DB fixture."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from trace_fixture import T1, T2, make_repo, make_trace_db

from aifactory.run import TaskRunStore
from aifactory.run.stop import StopResult
from aifactory.skill import envelope_problems
from aifactory.web import create_app

BASE = "http://127.0.0.1:4700"


def _client(root: Path, tmp_path: Path) -> TestClient:
    return TestClient(create_app(root, static_dir=tmp_path / "nostatic"), base_url=BASE)


def _get(client: TestClient, url: str, status: int = 200) -> Any:
    response = client.get(url)
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    return body


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_trace_db(tmp_path / "repo", os.getpid())


@pytest.fixture(name="sleeper")
def sleeper_fixture() -> Iterator[subprocess.Popen[bytes]]:
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    yield proc
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=10)


def test_list_has_every_column_newest_first(repo: Path, tmp_path: Path) -> None:
    body = _get(_client(repo, tmp_path), "/api/runs")
    runs = body["data"]["runs"]
    assert [r["run_id"] for r in runs] == ["r-run", "r-fail", "r-ok"]
    ok = runs[2]
    assert ok["task_id"] == T1
    assert ok["task_title"] == "Schema"
    assert ok["workflow"] == "plan-commit"
    assert ok["state"] == "succeeded"
    assert ok["started_at"] == "2026-01-01T10:00:00+00:00"
    assert ok["duration_s"] == 300.0
    assert ok["tokens"] == 1180
    assert ok["cost"] == 0.25
    assert ok["pr"] == {
        "url": "https://example.test/pr/7",
        "pr_id": "7",
        "state": "open",
        "merged_by": None,
        "auto_merge_error": None,
    }
    assert [p["name"] for p in ok["phases"]] == ["plan", "test"]
    assert runs[1]["pr"] is None
    assert runs[1]["error"] == "accept not met"
    assert runs[0]["state"] == "running"
    assert runs[0]["duration_s"] > 0
    assert (runs[0]["started_by"], ok["started_by"]) == ("auto-continue", None)
    assert body["data"]["tasks"] == [T1, T2]


def test_filters_by_state_and_task(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    failed = _get(client, "/api/runs?state=failed")["data"]
    assert [r["run_id"] for r in failed["runs"]] == ["r-fail"]
    by_task = _get(client, f"/api/runs?task={T1}")["data"]
    assert [r["run_id"] for r in by_task["runs"]] == ["r-fail", "r-ok"]
    both = _get(client, f"/api/runs?task={T2}&state=failed")["data"]
    assert both["runs"] == []
    # The task list ignores the filters; the totals are not part of the list.
    assert "totals" not in both
    assert both["tasks"] == [T1, T2]


def test_unknown_state_is_400(repo: Path, tmp_path: Path) -> None:
    body = _get(_client(repo, tmp_path), "/api/runs?state=bogus", 400)
    assert body["error"]["code"] == "invalid_status"


def test_cost_totals_per_task_and_backlog(repo: Path, tmp_path: Path) -> None:
    totals = _get(_client(repo, tmp_path), "/api/runs/totals")["data"]
    assert totals["backlog"] == {"cost": 0.31, "tokens": 1780, "runs": 3}
    assert totals["tasks"] == [
        {"task_id": T1, "task_title": "Schema", "cost": 0.3, "tokens": 1680, "runs": 2},
        {"task_id": T2, "task_title": "Loader", "cost": 0.01, "tokens": 100, "runs": 1},
    ]


def test_repo_without_trace_db_is_empty(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "repo")
    data = _get(_client(root, tmp_path), "/api/runs")["data"]
    assert data["runs"] == [] and data["tasks"] == []
    totals = _get(_client(root, tmp_path), "/api/runs/totals")["data"]
    assert totals["backlog"] == {"cost": 0.0, "tokens": 0, "runs": 0}
    assert not (root / ".factory" / "trace.db").exists()
    body = _get(_client(root, tmp_path), "/api/runs/r-ok", 404)
    assert body["error"]["code"] == "unknown_run"


def test_detail_phases_gates_envelopes(repo: Path, tmp_path: Path) -> None:
    data = _get(_client(repo, tmp_path), "/api/runs/r-ok")["data"]
    assert data["run"]["run_id"] == "r-ok"
    assert data["session"]["total_tokens"] == 1180
    assert data["usage"] == {"read": 150, "written": 30}
    phases = data["phases"]
    assert [(p["seq"], p["name"], p["status"]) for p in phases] == [
        (1, "plan", "success"),
        (2, "test", "fail"),
    ]
    plan, test = phases
    assert (plan["harness"], plan["model"]) == ("claude", "claude-opus")
    assert (plan["tokens"], plan["cost"]) == (1180, 0.25)
    assert plan["usage"]["output_tokens"] == 30
    assert plan["duration_s"] == 180.0
    assert (test["harness"], test["model"], test["tokens"]) == (None, None, 0)
    gates = data["gates"]
    assert [(g["gate"], g["passed"]) for g in gates] == [
        ("artifacts_exist", True),
        ("tests_pass", False),
    ]
    assert gates[0]["checks"] == [{"item": "specs/x.md", "ok": True, "note": "exists"}]
    assert gates[1]["violations"] == ["tests failed"]
    assert gates[1]["checks"] is None
    [envelope] = data["envelopes"]
    assert envelope["payload"] == {"status": "success", "summary": "a plan"}
    assert envelope["valid"] is True


def test_detail_harness_falls_back_to_agent_sessions(repo: Path, tmp_path: Path) -> None:
    phases = _get(_client(repo, tmp_path), "/api/runs/r-run")["data"]["phases"]
    assert (phases[0]["harness"], phases[0]["model"]) == ("codex", "gpt-5")


def test_unknown_run_is_404(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    assert _get(client, "/api/runs/nope", 404)["error"]["code"] == "unknown_run"
    assert _get(client, "/api/runs/nope/events", 404)["error"]["code"] == "unknown_run"


def test_events_paginate(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    first = _get(client, "/api/runs/r-ok/events?limit=3")["data"]
    assert [e["event_id"] for e in first["events"]] == ["e1", "e2", "e3"]
    assert first["has_more"] is True
    tool = first["events"][2]
    assert tool["type"] == "tool_call"
    assert tool["payload"]["args"] == {"file_path": "src/app/x.py"}
    rest = _get(client, f"/api/runs/r-ok/events?after={first['cursor']}")["data"]
    assert [e["event_id"] for e in rest["events"]] == ["e4", "e5", "e6", "e7", "e8"]
    assert rest["has_more"] is False
    body = _get(client, "/api/runs/r-ok/events?after=x", 400)
    assert body["error"]["code"] == "usage_error"


def _set_pid(repo: Path, run_id: str, pid: int) -> None:
    store = TaskRunStore(repo / ".factory" / "trace.db")
    store.conn.execute("UPDATE task_runs SET pid = ? WHERE run_id = ?", (pid, run_id))
    store.close()


def test_stop_terminates_and_marks_stopped(
    repo: Path, tmp_path: Path, sleeper: subprocess.Popen[bytes]
) -> None:
    _set_pid(repo, "r-run", sleeper.pid)
    client = _client(repo, tmp_path)
    response = client.post("/api/runs/r-run/stop")
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == 200, body
    assert body["data"]["run"]["state"] == "stopped"
    assert body["data"]["signalled"] == [sleeper.pid]
    assert sleeper.wait(timeout=10) is not None
    listed = _get(client, "/api/runs?state=stopped")["data"]["runs"]
    assert [r["run_id"] for r in listed] == ["r-run"]

    again = client.post("/api/runs/r-run/stop")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "run_not_running"


def test_stop_finished_run_is_409(repo: Path, tmp_path: Path) -> None:
    response = _client(repo, tmp_path).post("/api/runs/r-ok/stop")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "run_not_running"
    missing = _client(repo, tmp_path).post("/api/runs/nope/stop")
    assert missing.status_code == 404


def test_web_calls_the_cli_stop_function(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, str]] = []

    def spy(root: Path, run_id: str) -> StopResult:
        calls.append((root, run_id))
        store = TaskRunStore(root / ".factory" / "trace.db")
        store.mark_stopped(run_id, "spy")
        row = store.get(run_id)
        store.close()
        assert row is not None
        return StopResult(row, [], [])

    monkeypatch.setattr("aifactory.run.stop.stop_run", spy)
    response = _client(repo, tmp_path).post("/api/runs/r-run/stop")
    assert response.status_code == 200
    assert calls == [(repo, "r-run")]
    assert response.json()["data"]["run"]["state"] == "stopped"


def _slot_event(repo: Path, event_id: str, payload: dict[str, object]) -> None:
    conn = sqlite3.connect(str(repo / ".factory" / "trace.db"), isolation_level=None)
    try:
        conn.execute(
            "INSERT INTO events (event_id, adw_id, phase_id, type, name, payload_json, "
            "started_at) VALUES (?, 'r-run', 'p3', 'log', 'test_slot', ?, "
            "'2026-01-03T10:01:00+00:00')",
            (event_id, json.dumps(payload)),
        )
    finally:
        conn.close()


def test_phase_waiting_for_a_test_slot(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    run = _get(client, "/api/runs/r-run")["data"]
    assert run["phases"][0]["slot_wait"] is None
    _slot_event(repo, "s1", {"state": "waiting", "ahead": 3, "slots": 1})
    _slot_event(repo, "s2", {"state": "waiting", "ahead": 2, "slots": 1})
    listed = _get(client, "/api/runs")["data"]["runs"][0]
    assert listed["phases"][0]["slot_wait"] == {"ahead": 2, "slots": 1}
    detail = _get(client, "/api/runs/r-run")["data"]["phases"][0]
    assert detail["slot_wait"] == {"ahead": 2, "slots": 1}
    _slot_event(repo, "s3", {"state": "acquired", "slot": 0, "slots": 1})
    assert _get(client, "/api/runs/r-run")["data"]["phases"][0]["slot_wait"] is None
    ok = _get(client, "/api/runs/r-ok")["data"]["phases"]
    assert all(p["slot_wait"] is None for p in ok)


LONG_REQUEST = (
    "# Zadání\n\n" + " ".join(f"slovo{i}" for i in range(200)) + "\n\nkeep what this says."
)


def _request_phase(repo: Path, run_id: str, request: str) -> None:
    """A request (engineer) phase of ``run_id`` that logged ``request`` as its input."""
    conn = sqlite3.connect(str(repo / ".factory" / "trace.db"), isolation_level=None)
    try:
        conn.execute(
            "INSERT INTO phases (phase_id, adw_id, seq, name, kind, owner, status, attempt, "
            "retries, started_at) VALUES (?, ?, 0, 'request', 'engineer', 'tester', "
            "'success', 1, 0, '2026-01-02T10:00:00+00:00')",
            (f"{run_id}-req", run_id),
        )
        conn.execute(
            "INSERT INTO events (event_id, adw_id, phase_id, type, name, payload_json, "
            "started_at) VALUES (?, ?, ?, 'log', 'request', ?, '2026-01-02T10:00:00+00:00')",
            (f"{run_id}-ev", run_id, f"{run_id}-req", json.dumps({"input": request})),
        )
    finally:
        conn.close()


def test_detail_has_the_whole_request(repo: Path, tmp_path: Path) -> None:
    from aifactory.engine.tracer import Tracer

    assert len(LONG_REQUEST) > 500
    tracer = Tracer(repo / ".factory" / "trace.db", tmp_path / "events.jsonl")
    tracer.session_request("r-fail", LONG_REQUEST)
    tracer.conn.close()
    session = _get(_client(repo, tmp_path), "/api/runs/r-fail")["data"]["session"]
    assert session["request"] == LONG_REQUEST


def test_detail_takes_the_request_from_the_trace_for_an_old_run(repo: Path, tmp_path: Path) -> None:
    # An older run kept only the first 500 characters in sessions.request.
    conn = sqlite3.connect(str(repo / ".factory" / "trace.db"), isolation_level=None)
    try:
        conn.execute(
            "UPDATE sessions SET request = ? WHERE adw_id = 'r-fail'", (LONG_REQUEST[:500],)
        )
    finally:
        conn.close()
    _request_phase(repo, "r-fail", LONG_REQUEST)
    session = _get(_client(repo, tmp_path), "/api/runs/r-fail")["data"]["session"]
    assert session["request"] == LONG_REQUEST


def _post(client: TestClient, url: str, status: int = 200) -> Any:
    response = client.post(url)
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    return body


def _ids(client: TestClient, url: str) -> list[str]:
    return [r["run_id"] for r in _get(client, url)["data"]["runs"]]


def test_archive_finished_moves_runs_to_the_archived_list(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    assert _ids(client, "/api/runs?archived=1") == []
    body = _post(client, "/api/runs/archive-finished")
    assert sorted(body["data"]["archived"]) == ["r-fail", "r-ok"]
    assert _ids(client, "/api/runs") == ["r-run"]
    archived = _get(client, "/api/runs?archived=1")["data"]
    assert [r["run_id"] for r in archived["runs"]] == ["r-fail", "r-ok"]
    assert all(r["archived"] for r in archived["runs"])
    # Totals keep every run, archived or not.
    assert _get(client, "/api/runs/totals")["data"]["backlog"]["runs"] == 3
    assert _post(client, "/api/runs/archive-finished")["data"]["archived"] == []


def test_archive_and_unarchive_one_run(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    run = _post(client, "/api/runs/r-fail/archive")["data"]["run"]
    assert run["run_id"] == "r-fail" and run["archived"] is True
    assert _ids(client, "/api/runs") == ["r-run", "r-ok"]
    assert _ids(client, "/api/runs?archived=1") == ["r-fail"]
    run = _post(client, "/api/runs/r-fail/unarchive")["data"]["run"]
    assert run["archived"] is False
    assert _ids(client, "/api/runs?archived=1") == []
    # The detail of an archived run still opens.
    _post(client, "/api/runs/r-ok/archive")
    assert _get(client, "/api/runs/r-ok")["data"]["run"]["archived"] is True


def test_running_run_is_not_archived(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    body = _post(client, "/api/runs/r-run/archive", 409)
    assert body["error"]["code"] == "run_running"
    assert _post(client, "/api/runs/nope/archive", 404)["error"]["code"] == "unknown_run"
    assert _post(client, "/api/runs/nope/unarchive", 404)["error"]["code"] == "unknown_run"


def _trace_rows(repo: Path, run_id: str) -> int:
    conn = sqlite3.connect(repo / ".factory" / "trace.db")
    try:
        return sum(
            conn.execute(f"SELECT COUNT(*) FROM {t} WHERE adw_id = ?", (run_id,)).fetchone()[0]
            for t in ("sessions", "phases", "events", "envelopes", "gate_results")
        )
    finally:
        conn.close()


def test_delete_one_archived_run_with_its_trace(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    body = _post(client, "/api/runs/r-ok/delete", 409)
    assert body["error"]["code"] == "run_not_archived"
    assert _trace_rows(repo, "r-ok") > 0
    _post(client, "/api/runs/r-ok/archive")
    assert _post(client, "/api/runs/r-ok/delete")["data"] == {"deleted": ["r-ok"]}
    assert _trace_rows(repo, "r-ok") == 0
    assert _get(client, "/api/runs/r-ok", 404)["error"]["code"] == "unknown_run"
    assert _ids(client, "/api/runs?archived=1") == []
    assert _post(client, "/api/runs/r-ok/delete", 404)["error"]["code"] == "unknown_run"


def test_delete_archived_erases_only_archived_runs(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    _post(client, "/api/runs/r-fail/archive")
    assert _post(client, "/api/runs/delete-archived")["data"] == {"deleted": ["r-fail"]}
    assert _ids(client, "/api/runs") == ["r-run", "r-ok"]
    assert _trace_rows(repo, "r-fail") == 0
    assert _trace_rows(repo, "r-ok") > 0
    assert _post(client, "/api/runs/delete-archived")["data"] == {"deleted": []}


def test_old_trace_db_gets_the_archived_column(tmp_path: Path) -> None:
    db = tmp_path / "trace.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE task_runs (run_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, "
        "branch TEXT NOT NULL, worktree TEXT NOT NULL, base TEXT NOT NULL, "
        "base_sha TEXT NOT NULL, head_sha TEXT, state TEXT NOT NULL, started_at TEXT NOT NULL, "
        "ended_at TEXT, pid INTEGER, workflow TEXT, note TEXT, error TEXT)"
    )
    conn.execute(
        "INSERT INTO task_runs VALUES ('r1', 'T', 'b', 'w', 'main', 'sha', NULL, 'failed', "
        "'2026-01-01T00:00:00+00:00', NULL, NULL, NULL, NULL, NULL)"
    )
    conn.commit()
    conn.close()
    store = TaskRunStore(db)
    try:
        row = store.get("r1")
        assert row is not None and row.archived == 0
        assert store.archive_finished() == ["r1"]
    finally:
        store.close()


def test_pause_and_resume_a_running_run(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    response = client.post("/api/runs/r-run/pause")
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == 200, body
    assert body["data"]["run"]["state"] == "running"
    assert body["data"]["run"]["pause"] == "pausing"

    again = client.post("/api/runs/r-run/pause")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "run_already_paused"

    store = TaskRunStore(repo / ".factory" / "trace.db")
    store.enter_pause("r-run")
    store.close()
    listed = _get(client, "/api/runs?state=paused")["data"]["runs"]
    assert [(r["run_id"], r["pause"]) for r in listed] == [("r-run", "paused")]

    resumed = client.post("/api/runs/r-run/resume")
    assert resumed.status_code == 200
    assert resumed.json()["data"]["run"]["pause"] is None
    not_paused = client.post("/api/runs/r-run/resume")
    assert not_paused.status_code == 409
    assert not_paused.json()["error"]["code"] == "run_not_paused"


def test_pause_finished_run_is_409(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    for action in ("pause", "resume"):
        response = client.post(f"/api/runs/r-ok/{action}")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "run_not_running"
    assert client.post("/api/runs/nope/pause").status_code == 404
