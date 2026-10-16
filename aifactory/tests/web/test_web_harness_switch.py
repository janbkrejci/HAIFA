"""„Pokračovat s jiným harnessem“: the harnesses offered and the retry on the chosen one."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from trace_fixture import T1, make_trace_db

from aifactory.home import haifa_home
from aifactory.skill import envelope_problems
from aifactory.web import create_app

BASE = "http://127.0.0.1"


class _Launcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str] | None]] = []

    def start_retry(
        self,
        repo: Path,
        task_id: str,
        run_id: str,
        *,
        note: str | None = None,
        from_phase: str | None = None,
        timeout: float = 30.0,
        agents_override: dict[str, str] | None = None,
    ) -> object:
        self.calls.append((task_id, run_id, agents_override))
        return object()


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    repo = make_trace_db(tmp_path / "repo", os.getpid())
    conn = sqlite3.connect(repo / ".factory" / "trace.db")
    with conn:
        conn.execute(
            "UPDATE task_runs SET failure_kind = 'quota', failure_detail = ? WHERE run_id = ?",
            (
                json.dumps({"harness": "codex", "model": "gpt-6.1-sol", "agent": "builder"}),
                "r-fail",
            ),
        )
    conn.close()
    home = haifa_home()
    home.mkdir(parents=True, exist_ok=True)
    choices = {
        "claude": {"enabled": True, "model": "claude-opus-5-5", "thinking": "high"},
        "codex": {"enabled": True, "model": "gpt-6.1-sol", "thinking": None},
        "pi": {"enabled": True, "model": "x/y", "thinking": None},
    }
    (home / "harnesses.json").write_text(
        json.dumps({"version": 1, "default_harness": "codex", "harnesses": choices}),
        encoding="utf-8",
    )
    tests = {
        "claude": {"claude-opus-5-5": {"ok": True}},
        "codex": {"gpt-6.1-sol": {"ok": True}},
        "pi": {"x/y": {"ok": False}},
    }
    (home / "harness-tests.json").write_text(json.dumps(tests), encoding="utf-8")
    return repo


def _client(repo: Path, tmp_path: Path, launcher: _Launcher) -> TestClient:
    app = create_app(repo, static_dir=tmp_path / "nostatic", launcher=launcher)  # type: ignore[arg-type]
    return TestClient(app, base_url=BASE)


def test_choices_are_enabled_tested_and_not_exhausted(repo: Path, tmp_path: Path) -> None:
    response = _client(repo, tmp_path, _Launcher()).get("/api/runs/r-fail/harness-choices")
    body = response.json()
    assert response.status_code == 200, body
    assert envelope_problems(body) == []
    data = body["data"]
    assert data["exhausted"] == {"harness": "codex", "model": "gpt-6.1-sol"}
    # codex ran out, pi failed its test
    assert data["choices"] == [
        {"harness": "claude", "model": "claude-opus-5-5", "thinking": "high"}
    ]


def test_retry_with_a_harness_passes_its_model(repo: Path, tmp_path: Path) -> None:
    launcher = _Launcher()
    client = _client(repo, tmp_path, launcher)

    response = client.post("/api/runs/r-fail/retry", json={"harness": "claude"})
    assert response.status_code == 202, response.json()
    assert launcher.calls == [
        (T1, "r-fail", {"harness": "claude", "model": "claude-opus-5-5", "thinking": "high"})
    ]

    for refused in ("pi", "codex", "nope"):
        bad = client.post("/api/runs/r-fail/retry", json={"harness": refused})
        assert bad.status_code == 400, bad.json()
        assert bad.json()["error"]["code"] == "invalid_value"
    assert len(launcher.calls) == 1
