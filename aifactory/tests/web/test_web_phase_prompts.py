"""The phase prompts API: one phase's system and user prompt from the run's session dir."""

from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest
from multi_repo import symlink
from starlette.testclient import TestClient
from trace_fixture import make_trace_db

from aifactory.run.errors import TaskRunError
from aifactory.run.task import session_dir_of
from aifactory.skill import envelope_problems
from aifactory.web import create_app, runs

BASE = "http://127.0.0.1:4700"


def _client(root: Path, tmp_path: Path) -> TestClient:
    return TestClient(create_app(root, static_dir=tmp_path / "nostatic"), base_url=BASE)


def _get(client: TestClient, url: str, status: int = 200) -> Any:
    response = client.get(url)
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    return body


def _commit(root: Path, *paths: str) -> None:
    """Commit ``paths`` on ``main``: the run config is read from base."""
    for args in (
        ("checkout", "-q", "-B", "main"),
        ("add", "--", *paths),
        ("-c", "user.name=t", "-c", "user.email=t@example.test", "commit", "-q", "-m", "c"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    root = make_trace_db(tmp_path / "repo", os.getpid())
    _commit(root, ".factory/config.yaml", "backlog")
    return root


def _add_phase(repo: Path, phase_id: str, name: str, owner: str, kind: str = "agent") -> None:
    conn = sqlite3.connect(str(repo / ".factory" / "trace.db"), isolation_level=None)
    try:
        conn.execute(
            "INSERT INTO phases (phase_id, adw_id, seq, name, kind, owner, status, attempt, "
            "retries, started_at) VALUES (?, 'r-ok', 9, ?, ?, ?, 'success', 1, 0, "
            "'2026-01-01T10:04:00+00:00')",
            (phase_id, name, kind, owner),
        )
    finally:
        conn.close()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _url(run_id: str, phase_id: str) -> str:
    return f"/api/runs/{run_id}/phases/{phase_id}/prompts"


def test_session_dir_defaults_to_factory_data(repo: Path) -> None:
    assert session_dir_of(repo, "r-ok") == repo.resolve() / ".factory/data/sessions/r-ok"


def test_build_and_revise_of_one_agent_differ(repo: Path, tmp_path: Path) -> None:
    _add_phase(repo, "pb", "build", "builder")
    _add_phase(repo, "pr", "revise_1", "builder")
    prompts = session_dir_of(repo, "r-ok") / "builder" / "prompts"
    _write(prompts / "phases/build/system.md", "build system")
    _write(prompts / "phases/build/user.md", "build it")
    _write(prompts / "phases/revise_1/system.md", "revise system")
    _write(prompts / "phases/revise_1/user.md", "fix it")
    _write(prompts / "system.md", "revise system")
    _write(prompts / "user.md", "fix it")
    client = _client(repo, tmp_path)

    build = _get(client, _url("r-ok", "pb"))["data"]
    revise = _get(client, _url("r-ok", "pr"))["data"]

    assert (build["system"], build["user"]) == ("build system", "build it")
    assert (revise["system"], revise["user"]) == ("revise system", "fix it")
    for data in (build, revise):
        assert data["source"] == "phase"
        assert data["legacy"] is False
        assert data["agent"] == "builder"
        assert data["truncated"] == {"system": False, "user": False}
    assert build["phase"] == "build" and revise["phase"] == "revise_1"


def test_legacy_run_falls_back_to_agent_prompts(repo: Path, tmp_path: Path) -> None:
    prompts = session_dir_of(repo, "r-ok") / "planner" / "prompts"
    _write(prompts / "system.md", "planner system")
    _write(prompts / "user.md", "plan it")

    body = _get(_client(repo, tmp_path), _url("r-ok", "p1"))

    data = body["data"]
    assert (data["system"], data["user"]) == ("planner system", "plan it")
    assert data["source"] == "agent"
    assert data["legacy"] is True
    assert any("per-phase" in w for w in body["warnings"])


def test_missing_files_are_null(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    nothing = _get(client, _url("r-ok", "p1"))["data"]
    assert (nothing["system"], nothing["user"], nothing["source"]) == (None, None, "none")
    code = _get(client, _url("r-ok", "p2"))["data"]
    assert (code["system"], code["user"], code["source"]) == (None, None, "none")

    _write(session_dir_of(repo, "r-ok") / "planner/prompts/phases/plan/system.md", "only system")
    partial = _get(client, _url("r-ok", "p1"))["data"]
    assert partial["system"] == "only system"
    assert partial["user"] is None
    assert partial["source"] == "phase"


def test_unknown_run_is_404(repo: Path, tmp_path: Path) -> None:
    body = _get(_client(repo, tmp_path), _url("nope", "p1"), 404)
    assert body["error"]["code"] == "unknown_run"


def test_unknown_phase_is_404(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    assert _get(client, _url("r-ok", "nope"), 404)["error"]["code"] == "unknown_phase"
    # p3 belongs to r-run, not r-ok.
    assert _get(client, _url("r-ok", "p3"), 404)["error"]["code"] == "unknown_phase"


def test_invalid_id_is_400(repo: Path, tmp_path: Path) -> None:
    client = _client(repo, tmp_path)
    for url in (_url("r-ok", "bad%20id"), _url("r-ok", "a..b"), _url("r..ok", "p1")):
        assert _get(client, url, 400)["error"]["code"] == "invalid_value"
    for run_id, phase_id in (("r-ok", "../etc"), ("../x", "p1"), ("r-ok", "")):
        with pytest.raises(TaskRunError) as exc:
            runs.phase_prompts(repo, run_id, phase_id)
        assert exc.value.code == "invalid_value"


def test_path_cannot_escape_session_dir(repo: Path, tmp_path: Path) -> None:
    session = session_dir_of(repo, "r-ok")
    session.mkdir(parents=True)
    outside = session.parent.parent / "outside"
    _write(outside / "prompts/phases/x/system.md", "escaped")
    _write(outside / "prompts/system.md", "escaped")
    _add_phase(repo, "pe", "x", "../../outside")
    client = _client(repo, tmp_path)

    escaped = _get(client, _url("r-ok", "pe"))
    assert (escaped["data"]["system"], escaped["data"]["user"]) == (None, None)
    assert escaped["data"]["source"] == "none"

    secret = tmp_path / "secret.md"
    secret.write_text("secret", encoding="utf-8", newline="\n")
    link = session / "planner/prompts/phases/plan/user.md"
    link.parent.mkdir(parents=True)
    symlink(link, secret)
    _write(link.parent / "system.md", "plan system")
    linked = _get(client, _url("r-ok", "p1"))["data"]
    assert linked["system"] == "plan system"
    assert linked["user"] is None


def test_large_prompt_is_truncated(repo: Path, tmp_path: Path) -> None:
    phase = session_dir_of(repo, "r-ok") / "planner/prompts/phases/plan"
    _write(phase / "system.md", "small")
    _write(phase / "user.md", "x" * (runs.MAX_PROMPT_BYTES + 100))

    data = _get(_client(repo, tmp_path), _url("r-ok", "p1"))["data"]

    assert len(data["user"].encode()) <= runs.MAX_PROMPT_BYTES
    assert data["truncated"] == {"system": False, "user": True}
    assert data["max_bytes"] == runs.MAX_PROMPT_BYTES


def test_session_dir_follows_data_dir(repo: Path, tmp_path: Path) -> None:
    _write(repo / ".factory/agents.yaml", "defaults:\n  data_dir: custom-data\nagents: []\n")
    _commit(repo, ".factory/agents.yaml")
    assert session_dir_of(repo, "r-ok") == repo.resolve() / "custom-data/sessions/r-ok"
    beside_db = repo / ".factory/data/sessions/r-ok/planner/prompts/phases/plan"
    _write(beside_db / "user.md", "next to the trace db")
    client = _client(repo, tmp_path)

    assert _get(client, _url("r-ok", "p1"))["data"]["user"] is None

    _write(repo / "custom-data/sessions/r-ok/planner/prompts/phases/plan/user.md", "custom")
    assert _get(client, _url("r-ok", "p1"))["data"]["user"] == "custom"
