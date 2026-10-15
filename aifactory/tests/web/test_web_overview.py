"""``GET /api/overview``: what runs, waits for review and failed in every repo; reads only."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from multi_repo import BASE, commit_all, rmtree, write
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

from aifactory.run.store import SyncPrRow, TaskPrRow, TaskRunStore
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
def repo_a_fixture(tmp_path: Path) -> Iterator[Path]:
    with dead_pid() as pid:
        yield make_overview_repo(tmp_path / "alpha", live_pid=os.getpid(), dead_pid=pid)


@pytest.fixture(name="repo_b")
def repo_b_fixture(tmp_path: Path) -> Iterator[Path]:
    with dead_pid() as pid:
        yield make_overview_repo(tmp_path / "beta", live_pid=os.getpid(), dead_pid=pid, prefix="b-")


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
        "merged_outside": 0,
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


def test_config_cache_invalidated_before_ttl(tmp_path: Path) -> None:
    root = make_installed_repo(tmp_path / "cached")
    home = tmp_path / "home"
    register(home, root)
    client = _client(home, tmp_path)
    assert _get(client)["repos"][0]["config"]["clean"] is True
    write(root, ".factory/config.yaml", "base: main\nmax_parallel_runs: 3\n")
    assert _get(client)["repos"][0]["config"]["clean"] is False
    commit_all(root)
    assert _get(client)["repos"][0]["config"]["clean"] is True


# ── task summary and factory controls ────────────────────────────────────────


def _repo_item(repo: Path, tmp_path: Path) -> dict[str, Any]:
    home = tmp_path / "home"
    register(home, repo)
    item: dict[str, Any] = _get(_client(home, tmp_path))["repos"][0]
    return item


def test_task_summary_counts_tasks_per_board_state(repo_a: Path, tmp_path: Path) -> None:
    a = _repo_item(repo_a, tmp_path)
    # T_DEAD's process ended: its board state comes from the backlog (ready)
    assert a["tasks"] == {
        "todo": 0,
        "ready": 2,
        "blocked": 0,
        "running": 1,
        "in review": 1,
        "done": 1,
        "cancelled": 1,
    }


def test_factory_block_with_the_default_limit(repo_a: Path, tmp_path: Path) -> None:
    a = _repo_item(repo_a, tmp_path)
    assert a["factory"] == {
        "max_parallel_runs": 1,
        "running": 1,
        "in_review": 1,
        "free_slots": 0,
        "ready": 2,
        "can_start": False,
        "paused": 0,
        "pausing": 0,
        "control": None,
    }
    assert {r["task_id"]: r["pause"] for r in a["running"]} == {T_RUN: None, T_DEAD: None}


def test_factory_can_start_with_a_free_slot_and_excluded_tasks_are_not_ready(
    repo_a: Path, tmp_path: Path
) -> None:
    write(repo_a, ".factory/config.yaml", "base: main\ndocs_root: .\nmax_parallel_runs: 3\n")
    commit_all(repo_a, "three slots")
    store = TaskRunStore(_db(repo_a))
    try:
        store.set_excluded(T_FAIL, True)
        store.request_pause("r-run")
    finally:
        store.close()
    a = _repo_item(repo_a, tmp_path)
    factory = a["factory"]
    # T_RUN runs and T_REV's PR waits for review: both take a slot
    assert (factory["max_parallel_runs"], factory["running"], factory["free_slots"]) == (3, 1, 1)
    assert factory["in_review"] == 1
    assert factory["ready"] == 1
    assert factory["can_start"] is True
    assert (factory["pausing"], factory["paused"]) == (1, 0)
    assert a["tasks"]["ready"] == 2  # the summary is the kanban's, exclusion aside
    assert next(r for r in a["running"] if r["task_id"] == T_RUN)["pause"] == "pausing"


def test_a_pr_waiting_for_review_takes_the_last_free_slot(repo_a: Path, tmp_path: Path) -> None:
    write(repo_a, ".factory/config.yaml", "base: main\ndocs_root: .\nmax_parallel_runs: 2\n")
    commit_all(repo_a, "two slots")
    factory = _repo_item(repo_a, tmp_path)["factory"]
    assert (factory["running"], factory["in_review"], factory["free_slots"]) == (1, 1, 0)
    assert factory["can_start"] is False
    _save_pr(repo_a, T_RUN, "factory/run-1", "open", 1)  # a running task with a PR: once
    factory = _repo_item(repo_a, tmp_path)["factory"]
    assert (factory["running"], factory["in_review"], factory["free_slots"]) == (1, 1, 0)


def test_trace_db_without_the_pause_column(repo_a: Path, tmp_path: Path) -> None:
    conn = sqlite3.connect(str(_db(repo_a)), isolation_level=None)
    try:
        conn.execute("ALTER TABLE task_runs DROP COLUMN pause")
    finally:
        conn.close()
    a = _repo_item(repo_a, tmp_path)
    assert a["warnings"] == []
    assert {r["task_id"]: r["pause"] for r in a["running"]} == {T_RUN: None, T_DEAD: None}
    assert a["factory"]["running"] == 1


def test_missing_repo_has_no_tasks_nor_factory(tmp_path: Path) -> None:
    gone = make_installed_repo(tmp_path / "gone")
    home = tmp_path / "home"
    register(home, gone)
    rmtree(gone)
    g = _get(_client(home, tmp_path))["repos"][0]
    assert g["state"] == "missing"
    assert (g["tasks"], g["factory"]) == (None, None)


# ── PRs merged outside factory and closed tasks ──────────────────────────────


def _save_pr(
    root: Path, task_id: str, branch: str, state: str, day: int, merged_at: str | None = None
) -> str:
    """A PR row created on 2026-02-<day> (day 0: 2025-12-31, before the fixture's open PR)."""
    created = f"2026-02-{day:02d}T10:00:00+00:00" if day else "2025-12-31T10:00:00+00:00"
    url = f"https://example.test/pr/{branch}"
    store = TaskRunStore(_db(root))
    try:
        store.save_pr(
            TaskPrRow(
                branch=branch,
                task_id=task_id,
                provider="local",
                pr_id=branch,
                url=url,
                base="main",
                base_sha="0" * 40,
                title=task_id,
                body="",
                state=state,
                created_at=created,
                updated_at=created,
                merged_at=merged_at,
            )
        )
    finally:
        store.close()
    return url


def test_review_leaves_out_done_and_cancelled_tasks(repo_a: Path, tmp_path: Path) -> None:
    _save_pr(repo_a, T_DONE, "factory/done-1", "open", 1)
    _save_pr(repo_a, T_CANC, "factory/canc-1", "open", 2)
    a = _repo_item(repo_a, tmp_path)
    assert [r["task_id"] for r in a["review"]] == [T_REV]
    assert a["tasks"]["in review"] == 1


def test_merged_outside_lists_tasks_not_done_in_base(repo_a: Path, tmp_path: Path) -> None:
    url = _save_pr(repo_a, T_FAIL, "factory/fail-1", "merged", 1, "2026-02-01T12:00:00+00:00")
    _save_pr(repo_a, T_DONE, "factory/done-1", "merged", 2, "2026-02-02T12:00:00+00:00")
    _save_pr(repo_a, T_REV, "factory/rev-0", "merged", 0, "2025-12-31T12:00:00+00:00")
    a = _repo_item(repo_a, tmp_path)
    assert a["merged_outside"] == [
        {
            "task_id": T_FAIL,
            "task_title": "Failing",
            "pr_id": "factory/fail-1",
            "url": url,
            "branch": "factory/fail-1",
            "merged_at": "2026-02-01T12:00:00+00:00",
        }
    ]
    assert a["sync_pr"] is None


def test_merged_outside_skips_a_newer_open_pr_and_a_reopened_task(
    repo_a: Path, tmp_path: Path
) -> None:
    _save_pr(repo_a, T_FAIL, "factory/fail-1", "merged", 1)
    _save_pr(repo_a, T_FAIL, "factory/fail-2", "open", 2)
    url = _save_pr(repo_a, T_DEAD, "factory/dead-1", "merged", 3)
    path = repo_a / "backlog/M01-core/S01-model/M01-S01-T06-orphan.md"
    path.write_text(
        path.read_text(encoding="utf-8") + f"\n## Běhy\n- 2026-02-03: PR {url} merged\n",
        encoding="utf-8",
    )
    commit_all(repo_a, "reopened")
    a = _repo_item(repo_a, tmp_path)
    assert a["merged_outside"] == []


def test_open_sync_pr_is_shown(repo_a: Path, tmp_path: Path) -> None:
    _save_pr(repo_a, T_FAIL, "factory/fail-1", "merged", 1)
    store = TaskRunStore(_db(repo_a))
    try:
        store.save_sync_pr(
            SyncPrRow(
                branch="factory-sync/1",
                provider="local",
                pr_id="factory-sync/1",
                url="local:factory-sync/1",
                base="main",
                base_sha="0" * 40,
                title="backlog sync",
                body="",
                state="open",
                tasks=f'["{T_FAIL}"]',
                created_at="2026-02-02T10:00:00+00:00",
                updated_at="2026-02-02T10:00:00+00:00",
            )
        )
    finally:
        store.close()
    a = _repo_item(repo_a, tmp_path)
    assert [m["task_id"] for m in a["merged_outside"]] == [T_FAIL]
    assert a["sync_pr"] == {
        "url": "local:factory-sync/1",
        "branch": "factory-sync/1",
        "tasks": [T_FAIL],
    }


def test_new_keys_in_stub_and_totals(repo_a: Path, tmp_path: Path) -> None:
    _save_pr(repo_a, T_FAIL, "factory/fail-1", "merged", 1)
    gone = make_installed_repo(tmp_path / "gone")
    home = tmp_path / "home"
    register(home, repo_a, gone)
    rmtree(gone)
    data = _get(_client(home, tmp_path))
    g = _by_id(data)["gone"]
    assert (g["merged_outside"], g["sync_pr"]) == ([], None)
    assert data["totals"]["merged_outside"] == 1
