"""Live updates: the file/trace watcher, the rowid-cursor run tail and the SSE stream."""

from __future__ import annotations

import http.client
import json
import os
import socket
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from starlette.testclient import TestClient
from trace_fixture import T1, T2, make_repo, make_trace_db

from aifactory.skill import envelope_problems
from aifactory.web import create_app
from aifactory.web.live import LiveWatcher

BASE = "http://127.0.0.1:4700"
TASK_FILE = "backlog/M01-core/S01-model/M01-S01-T01-schema.md"


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_trace_db(tmp_path / "repo", os.getpid())


def _append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _db(repo: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(repo / ".factory" / "trace.db"), isolation_level=None)


def _insert_event(repo: Path, event_id: str, run_id: str, phase_id: str, **extra: Any) -> None:
    conn = _db(repo)
    conn.execute(
        "INSERT INTO events (event_id, adw_id, phase_id, type, name, payload_json, tokens, "
        "started_at) VALUES (?, ?, ?, ?, ?, ?, ?, '2026-01-01T10:06:00+00:00')",
        (
            event_id,
            run_id,
            phase_id,
            extra.get("type", "tool_call"),
            extra.get("name", "Read"),
            json.dumps(extra.get("payload", {})),
            extra.get("tokens"),
        ),
    )
    conn.close()


# -- watcher -------------------------------------------------------------------------


def test_file_change_is_an_event(repo: Path) -> None:
    watcher = LiveWatcher(repo)
    try:
        assert watcher.poll() == []
        _append(repo / TASK_FILE, "\nZměna.\n")
        [event] = watcher.poll()
        assert event.kind == "files"
        assert event.data["areas"] == ["backlog"]
        assert event.data["paths"] == [TASK_FILE]
        assert event.data["truncated"] is False
        assert watcher.poll() == []
        _append(repo / ".factory" / "config.yaml", "# note\n")
        [event] = watcher.poll()
        assert event.data == {
            "areas": ["factory"],
            "paths": [".factory/config.yaml"],
            "truncated": False,
        }
        (repo / TASK_FILE).unlink()
        [event] = watcher.poll()
        assert event.data["paths"] == [TASK_FILE]
    finally:
        watcher.close()


def test_worktrees_data_and_trace_db_are_not_file_events(repo: Path) -> None:
    watcher = LiveWatcher(repo)
    try:
        assert watcher.poll() == []
        _append(repo / ".factory" / "worktrees" / "x" / "foo.py", "x = 1\n")
        _append(repo / ".factory" / "data" / "x.jsonl", "{}\n")
        _append(repo / "backlog" / "M01-core" / "index.md~", "backup")
        assert watcher.poll() == []
        _insert_event(repo, "e-new", "r-run", "p3")
        events = watcher.poll()
        assert [e.kind for e in events] == ["trace"]
    finally:
        watcher.close()


def test_new_trace_rows_are_an_event(repo: Path) -> None:
    watcher = LiveWatcher(repo)
    try:
        assert watcher.poll() == []
        _insert_event(repo, "e-new", "r-run", "p3")
        [event] = watcher.poll()
        assert event.kind == "trace"
        assert event.data["run_ids"] == ["r-run"]
        assert T2 in event.data["task_ids"]
        assert event.data["runs_changed"] is False
        conn = _db(repo)
        (max_rowid,) = conn.execute("SELECT MAX(rowid) FROM events").fetchone()
        assert event.data["events"] == max_rowid
        assert watcher.poll() == []
        conn.execute("UPDATE task_runs SET state = 'stopped' WHERE run_id = 'r-run'")
        conn.close()
        [event] = watcher.poll()
        assert event.data["runs_changed"] is True
        assert event.data["task_ids"] == [T2]
    finally:
        watcher.close()


def test_phase_leaving_running_is_an_event(repo: Path) -> None:
    watcher = LiveWatcher(repo)
    try:
        assert watcher.poll() == []
        conn = _db(repo)
        conn.execute("UPDATE phases SET status = 'success' WHERE phase_id = 'p3'")
        conn.close()
        [event] = watcher.poll()
        assert event.data["run_ids"] == ["r-run"]
    finally:
        watcher.close()


def test_trace_db_created_later(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "repo")
    watcher = LiveWatcher(root)
    try:
        assert watcher.poll() == []
        assert watcher.poll() == []
        make_trace_db(tmp_path / "repo", os.getpid())
        kinds = {e.kind: e for e in watcher.poll()}
        assert "trace" in kinds
        assert T1 in kinds["trace"].data["task_ids"]
    finally:
        watcher.close()


# -- run tail ------------------------------------------------------------------------


def _client(root: Path, tmp_path: Path) -> TestClient:
    return TestClient(create_app(root, static_dir=tmp_path / "nostatic"), base_url=BASE)


def _get(client: TestClient, url: str, status: int = 200) -> Any:
    response = client.get(url)
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    return body["data"] if status == 200 else body


def _tail_url(run_id: str, cursors: dict[str, int], open_phases: str = "") -> str:
    query = "&".join(f"{k}={v}" for k, v in cursors.items())
    return f"/api/runs/{run_id}/tail?{query}" + (f"&open={open_phases}" if open_phases else "")


def test_detail_has_cursors(repo: Path, tmp_path: Path) -> None:
    data = _get(_client(repo, tmp_path), "/api/runs/r-ok")
    conn = _db(repo)
    (max_event,) = conn.execute("SELECT MAX(rowid) FROM events WHERE adw_id = 'r-ok'").fetchone()
    (max_phase,) = conn.execute("SELECT MAX(rowid) FROM phases WHERE adw_id = 'r-ok'").fetchone()
    conn.close()
    assert data["cursors"] == {
        "events": max_event,
        "phases": max_phase,
        "gates": 2,
        "envelopes": 1,
    }


def test_tail_returns_new_rows_with_cursors(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    cursors = _get(client, "/api/runs/r-ok")["cursors"]
    empty = _get(client, _tail_url("r-ok", cursors))
    assert empty["events"] == []
    assert empty["phases"] == []
    assert empty["gates"] == []
    assert empty["envelopes"] == []
    assert empty["cursors"] == cursors
    assert empty["has_more"] is False
    assert empty["run"]["run_id"] == "r-ok"

    conn = _db(repo)
    conn.execute(
        "INSERT INTO phases (phase_id, adw_id, seq, name, kind, owner, status, attempt, "
        "retries, started_at) VALUES ('p9', 'r-ok', 3, 'review', 'agent', 'reviewer', "
        "'running', 1, 0, '2026-01-01T10:06:00+00:00')"
    )
    conn.close()
    _insert_event(
        repo,
        "e9",
        "r-ok",
        "p9",
        type="agent_end",
        name="reviewer",
        payload={"cost": 0.5, "usage": {"input_tokens": 10, "output_tokens": 4}},
        tokens=14,
    )
    tail = _get(client, _tail_url("r-ok", cursors))
    assert [e["event_id"] for e in tail["events"]] == ["e9"]
    assert tail["events"][0]["payload"]["cost"] == 0.5
    assert [p["phase_id"] for p in tail["phases"]] == ["p9"]
    assert (tail["phases"][0]["tokens"], tail["phases"][0]["cost"]) == (14, 0.5)
    assert tail["usage_delta"] == {"read": 10, "written": 4}
    assert tail["cursors"]["events"] == tail["events"][0]["rowid"] > cursors["events"]
    assert tail["cursors"]["phases"] > cursors["phases"]

    # the running phase stays in the tail; once it ends, `open=` still brings it
    again = _get(client, _tail_url("r-ok", tail["cursors"]))
    assert again["events"] == []
    assert [p["phase_id"] for p in again["phases"]] == ["p9"]
    conn = _db(repo)
    conn.execute("UPDATE phases SET status = 'success' WHERE phase_id = 'p9'")
    conn.close()
    closed = _get(client, _tail_url("r-ok", tail["cursors"]))
    assert closed["phases"] == []
    reopened = _get(client, _tail_url("r-ok", tail["cursors"], "p9"))
    assert [(p["phase_id"], p["status"]) for p in reopened["phases"]] == [("p9", "success")]
    assert reopened["cursors"] == tail["cursors"]


def test_tail_pages_events(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    first = _get(client, "/api/runs/r-ok/tail?limit=3")
    assert [e["event_id"] for e in first["events"]] == ["e1", "e2", "e3"]
    assert first["has_more"] is True
    rest = _get(client, f"/api/runs/r-ok/tail?events={first['cursors']['events']}")
    assert [e["event_id"] for e in rest["events"]] == ["e4", "e5", "e6", "e7", "e8"]
    assert rest["has_more"] is False


def test_tail_errors(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    assert _get(client, "/api/runs/nope/tail", 404)["error"]["code"] == "unknown_run"
    assert _get(client, "/api/runs/r-ok/tail?events=x", 400)["error"]["code"] == "usage_error"


# -- SSE end to end ------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


def _read_event(response: http.client.HTTPResponse, kind: str, deadline: float) -> Any:
    current: str | None = None
    while time.monotonic() < deadline:
        line = response.fp.readline().decode("utf-8").rstrip("\r\n")
        if line.startswith("event: "):
            current = line[len("event: ") :]
        elif line.startswith("data: ") and current == kind:
            return json.loads(line[len("data: ") :])
        elif line == "":
            current = None
    raise AssertionError(f"no {kind} event in time")


@pytest.mark.xdist_group("live")
def test_sse_stream_reports_file_change(repo: Path, tmp_path: Path) -> None:
    port = _free_port()
    app = create_app(repo, static_dir=tmp_path / "nostatic", live_interval=0.1)
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="warning", timeout_graceful_shutdown=1
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert time.monotonic() < deadline, "server did not start"
            time.sleep(0.02)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/live", headers={"Host": "127.0.0.1"})
        response = conn.getresponse()
        assert response.status == 200
        assert response.getheader("content-type", "").startswith("text/event-stream")
        hello = _read_event(response, "hello", time.monotonic() + 5)
        assert hello["interval"] == 0.1
        # the watcher takes its baseline; on Windows its git call alone can take 0.3 s
        time.sleep(2.0 if sys.platform == "win32" else 0.3)
        written = time.monotonic()
        _append(repo / TASK_FILE, "\nŽivě.\n")
        event = _read_event(response, "files", written + 5)
        assert time.monotonic() - written < 2
        assert TASK_FILE in event["paths"]
        assert isinstance(event["seq"], int)
        conn.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    assert not thread.is_alive()
