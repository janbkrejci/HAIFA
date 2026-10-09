"""``GET /api/overview``: what runs, waits for review and failed in every repo; reads only."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from multi_repo import BASE, rmtree, write
from overview_fixture import (
    PR_URL,
    T_CANC,
    T_DEAD,
    T_DONE,
    T_FAIL,
    T_REV,
    T_RUN,
    dead_pid,
    make_installed_repo,
    make_overview_repo,
    register,
)
from starlette.testclient import TestClient

from aifactory.skill import envelope_problems
from aifactory.web import create_multi_app, overview
from aifactory.web.overview import CONFIG_TTL, PROCESS_ENDED, TASKS_TTL, Overview
from aifactory.web.registry import Registry, RepoEntry

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))

from test_trace_db_lock import hold_write_lock  # noqa: E402


def _client(home: Path, tmp_path: Path) -> TestClient:
    app = create_multi_app(home=home, static_dir=tmp_path / "nostatic")
    return TestClient(app, base_url=BASE)


def _get(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/overview")
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == 200, body
    assert body["ok"] is True
    data: dict[str, Any] = body["data"]
    return data


def _by_id(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in data["repos"]}


def _db(root: Path) -> Path:
    return root / ".factory" / "trace.db"


def _db_files(root: Path) -> set[str]:
    return {p.name for p in (root / ".factory").iterdir() if p.name.startswith("trace.db")}


def _run_row(db: Path, run_id: str) -> tuple[Any, ...]:
    # immutable: a plain mode=ro open of a closed WAL DB would create -wal/-shm itself
    conn = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    try:
        row = conn.execute("SELECT * FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
    finally:
        conn.close()
    assert row is not None
    return tuple(row)


@pytest.fixture(name="repo_a")
def repo_a_fixture(tmp_path: Path) -> Path:
    return make_overview_repo(tmp_path / "alpha", live_pid=os.getpid(), dead_pid=dead_pid())


@pytest.fixture(name="repo_b")
def repo_b_fixture(tmp_path: Path) -> Path:
    return make_overview_repo(
        tmp_path / "beta", live_pid=os.getpid(), dead_pid=dead_pid(), prefix="b-"
    )


def test_overview_of_repos_with_and_without_trace_and_a_missing_folder(
    repo_a: Path, repo_b: Path, tmp_path: Path
) -> None:
    plain = make_installed_repo(tmp_path / "plain")
    gone = make_installed_repo(tmp_path / "gone")
    home = tmp_path / "home"
    register(home, repo_a, repo_b, plain, gone)
    rmtree(gone)

    data = _get(_client(home, tmp_path))
    repos = _by_id(data)
    assert [r["id"] for r in data["repos"]] == ["alpha", "beta", "plain", "gone"]

    a = repos["alpha"]
    assert a["state"] == "ok"
    assert a["has_trace"] is True
    assert a["warnings"] == []
    running = {r["task_id"]: r for r in a["running"]}
    assert set(running) == {T_RUN, T_DEAD}
    run = running[T_RUN]
    assert run["run_id"] == "r-run"
    assert run["task_title"] == "Runner"
    assert run["workflow"] == "build-test-review"
    assert run["started_at"] == "2026-01-07T10:00:00+00:00"
    assert run["phase"] == {
        "name": "build",
        "attempt": 2,
        "started_at": "2026-01-07T10:02:00+00:00",
    }
    assert run["cost"] == 0.42
    assert run["process"] == "alive"
    assert run["status_label"] is None
    assert running[T_DEAD]["process"] == "ended"

    assert [r["task_id"] for r in a["review"]] == [T_REV]
    review = a["review"][0]
    assert review["url"] == PR_URL
    assert review["task_title"] == "Reviewed"
    assert review["age_s"] > 0
    assert review["source"] == "trace"

    assert [f["task_id"] for f in a["failed"]] == [T_FAIL]
    assert a["failed"][0]["error"] == "accept not met"
    assert a["failed"][0]["run_id"] == "r-fail"
    listed = {x["task_id"] for key in ("running", "review", "failed") for x in a[key]}
    assert not listed & {T_DONE, T_CANC}

    config = a["config"]
    assert config["installed"] is True
    assert config["invalid"] is False
    assert config["clean"] is True
    assert a["last_activity"] == "2026-01-07T10:00:00+00:00"

    b = repos["beta"]
    assert b["state"] == "ok"
    assert {r["run_id"] for r in b["running"]} == {"b-r-run", "b-r-dead"}
    assert [f["run_id"] for f in b["failed"]] == ["b-r-fail"]

    p = repos["plain"]
    assert p["has_trace"] is False
    assert p["running"] == p["review"] == p["failed"] == []
    assert p["config"] is not None and p["config"]["installed"] is True
    assert p["state"] == "ok"
    assert not _db(plain).exists()
    assert _db_files(plain) == set()

    g = repos["gone"]
    assert g["state"] == "missing"
    assert g["warnings"]

    assert data["totals"] == {
        "repos": 4,
        "running": 4,
        "review": 2,
        "failed": 2,
        "process_ended": 2,
        "with_warnings": 1,
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_dead_process_is_shown_without_any_write(repo_a: Path, tmp_path: Path) -> None:
    home = tmp_path / "home"
    registry = register(home, repo_a)
    db = _db(repo_a)
    wal = Path(f"{db}-wal")
    before = (
        _sha(db),
        db.stat().st_mtime_ns,
        wal.read_bytes() if wal.exists() else None,
        _db_files(repo_a),
        _run_row(db, "r-dead"),
        registry.path.read_bytes(),
    )

    data = _get(_client(home, tmp_path))

    dead = next(r for r in data["repos"][0]["running"] if r["task_id"] == T_DEAD)
    assert dead["process"] == "ended"
    assert dead["status_label"] == PROCESS_ENDED == "proces skončil"
    after = (
        _sha(db),
        db.stat().st_mtime_ns,
        wal.read_bytes() if wal.exists() else None,
        _db_files(repo_a),
        _run_row(db, "r-dead"),
        registry.path.read_bytes(),
    )
    assert after == before
    row = _run_row(db, "r-dead")
    assert "running" in row
    conn = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    try:
        state, ended = conn.execute(
            "SELECT state, ended_at FROM task_runs WHERE run_id = 'r-dead'"
        ).fetchone()
    finally:
        conn.close()
    assert (state, ended) == ("running", None)


def test_overview_never_uses_task_run_store(
    repo_a: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    register(home, repo_a)

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the overview must not open TaskRunStore")

    monkeypatch.setattr("aifactory.run.store.TaskRunStore.__init__", refuse)
    a = _get(_client(home, tmp_path))["repos"][0]
    assert a["state"] == "ok"
    assert {r["task_id"] for r in a["running"]} == {T_RUN, T_DEAD}
    assert [r["task_id"] for r in a["review"]] == [T_REV]
    assert [r["task_id"] for r in a["failed"]] == [T_FAIL]


def test_git_reads_without_optional_locks_and_no_fetch(
    repo_a: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    register(home, repo_a)
    calls: list[tuple[list[str], dict[str, str] | None]] = []
    real_run = subprocess.run

    def record(args: Any, *rest: Any, **kwargs: Any) -> Any:
        if isinstance(args, list | tuple) and args and args[0] == "git":
            calls.append(([str(a) for a in args], kwargs.get("env")))
        return real_run(args, *rest, **kwargs)

    monkeypatch.setattr(subprocess, "run", record)
    _get(_client(home, tmp_path))
    assert calls
    for args, env in calls:
        assert env is not None and env.get("GIT_OPTIONAL_LOCKS") == "0", args
        assert "fetch" not in args, args


def test_busy_trace_db_answers_within_a_second(repo_a: Path, tmp_path: Path) -> None:
    home = tmp_path / "home"
    register(home, repo_a)
    client = _client(home, tmp_path)
    _get(client)  # warm up: config and task caches
    holder = hold_write_lock(_db(repo_a), 3.0)
    try:
        start = time.monotonic()
        data = _get(client)
        took = time.monotonic() - start
    finally:
        holder.wait(timeout=30)
    assert took < 1.0
    assert T_RUN in {r["task_id"] for r in data["repos"][0]["running"]}


def _app_with(home: Path, tmp_path: Path, ov: Overview) -> TestClient:
    app = create_multi_app(home=home, static_dir=tmp_path / "nostatic")
    app.state.overview = ov
    return TestClient(app, base_url=BASE)


# limit, sleep of the slow repo and response bound; on Windows the other repo alone needs
# ~8 git processes of 0.15-0.3 s each, and a loaded full suite (xdist) slows them elsewhere too
LIMIT, SLOW, BOUND = (4.0, 8.0, 7.0) if sys.platform == "win32" else (1.0, 3.0, 2.5)


def test_slow_repo_times_out_and_the_others_answer(
    repo_a: Path, repo_b: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    registry = register(home, repo_a, repo_b)
    real = overview._trace_view

    def slow(db: Path) -> Any:
        if "alpha" in str(db):
            time.sleep(SLOW)
        return real(db)

    monkeypatch.setattr(overview, "_trace_view", slow)
    client = _app_with(home, tmp_path, Overview(registry, timeout=LIMIT))
    start = time.monotonic()
    data = _get(client)
    took = time.monotonic() - start
    repos = _by_id(data)
    assert repos["alpha"]["state"] == "timeout"
    assert "did not answer" in repos["alpha"]["warnings"][0]
    assert repos["beta"]["state"] == "ok"
    assert {r["run_id"] for r in repos["beta"]["running"]} == {"b-r-run", "b-r-dead"}
    assert took < BOUND


def test_broken_repo_gives_an_error_and_the_others_answer(
    repo_a: Path, repo_b: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    register(home, repo_a, repo_b)
    real = overview._trace_view

    def broken(db: Path) -> Any:
        if "alpha" in str(db):
            raise RuntimeError("kaputt")
        return real(db)

    monkeypatch.setattr(overview, "_trace_view", broken)
    repos = _by_id(_get(_client(home, tmp_path)))
    assert repos["alpha"]["state"] == "error"
    assert repos["alpha"]["warnings"] == ["RuntimeError: kaputt"]
    assert repos["beta"]["state"] == "ok"
    assert repos["beta"]["failed"]


def test_config_and_task_caches_per_repo(
    repo_a: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    counts = {"config": 0, "tasks": 0}
    real_state = getattr(overview, "repo_state")  # noqa: B009
    real_load = getattr(overview, "load_for_edit")  # noqa: B009

    def count_state(*args: Any, **kwargs: Any) -> Any:
        counts["config"] += 1
        return real_state(*args, **kwargs)

    def count_load(*args: Any, **kwargs: Any) -> Any:
        counts["tasks"] += 1
        return real_load(*args, **kwargs)

    monkeypatch.setattr(overview, "repo_state", count_state)
    monkeypatch.setattr(overview, "load_for_edit", count_load)
    now = [1000.0]
    ov = Overview(Registry(tmp_path / "home"), clock=lambda: now[0])
    entry = RepoEntry(id="alpha", name="alpha", path=str(repo_a), added_at="2026-01-01")

    ov.repo(entry)
    now[0] += CONFIG_TTL - 1
    ov.repo(entry)
    assert counts == {"config": 1, "tasks": 1}
    now[0] += 2  # 16 s after the first
    ov.repo(entry)
    assert counts == {"config": 2, "tasks": 1}
    now[0] += TASKS_TTL - 16 + 1  # 61 s after the first
    ov.repo(entry)
    assert counts == {"config": 3, "tasks": 2}


def test_invalid_config_in_base_and_uncommitted_config(tmp_path: Path) -> None:
    bad = make_installed_repo(tmp_path / "bad", config="base: main\nmerge_strategy: bogus\n")
    dirty = make_installed_repo(tmp_path / "dirty")
    write(dirty, ".factory/config.yaml", "base: main\nmax_parallel_runs: 3\n")
    home = tmp_path / "home"
    register(home, bad, dirty)

    repos = _by_id(_get(_client(home, tmp_path)))
    assert repos["bad"]["state"] == "invalid_config"
    assert repos["bad"]["config"]["invalid"] is True
    assert any("merge_strategy" in i for i in repos["bad"]["config"]["issues"])
    assert repos["dirty"]["state"] == "uncommitted"
    assert repos["dirty"]["config"]["uncommitted"] == [
        {"path": ".factory/config.yaml", "status": "modified"}
    ]
    assert repos["dirty"]["config"]["clean"] is False
