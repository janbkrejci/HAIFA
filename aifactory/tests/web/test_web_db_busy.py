"""The dashboard API over a busy trace DB: it waits, then says ``trace_db_locked``."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from trace_fixture import make_trace_db

from aifactory.skill import envelope_problems
from aifactory.web import create_app

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))

from test_trace_db_lock import HOLD_SECONDS, hold_write_lock  # noqa: E402

BASE = "http://127.0.0.1:4700"


def _get(client: TestClient, url: str) -> tuple[int, Any]:
    response = client.get(url)
    body = response.json()
    assert envelope_problems(body) == []
    return response.status_code, body


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_trace_db(tmp_path / "repo", os.getpid())


def _db(repo: Path) -> Path:
    return repo / ".factory" / "trace.db"


def test_api_waits_for_a_lock_held_longer_than_5s(repo: Path, tmp_path: Path) -> None:
    client = TestClient(create_app(repo, static_dir=tmp_path / "nostatic"), base_url=BASE)
    holder: subprocess.Popen[str] = hold_write_lock(_db(repo), HOLD_SECONDS)
    try:
        start = time.monotonic()
        status, body = _get(client, "/api/runs")  # all_runs() writes (reaps dead runs)
        waited = time.monotonic() - start
    finally:
        holder.wait(timeout=30)
    assert status == 200, body
    assert body["ok"] is True
    assert {r["run_id"] for r in body["data"]["runs"]} == {"r-ok", "r-fail", "r-run"}
    assert waited > 5.0


def test_api_says_trace_db_locked_when_the_wait_runs_out(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("aifactory.run.store.BUSY_TIMEOUT", 0.2)
    client = TestClient(create_app(repo, static_dir=tmp_path / "nostatic"), base_url=BASE)
    holder = hold_write_lock(_db(repo), 2.0)
    try:
        status, body = _get(client, "/api/runs")
    finally:
        holder.wait(timeout=30)
    assert status == 503
    assert body["error"]["code"] == "trace_db_locked"
    assert "database is locked" not in body["error"]["message"]
