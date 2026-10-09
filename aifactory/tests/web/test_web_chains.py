"""``GET /api/chains``: auto-continue chains with their runs, free slots and skips."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from starlette.testclient import TestClient
from trace_fixture import T1, make_repo, make_trace_db

from aifactory.engine.utils import now_iso
from aifactory.run import TaskRunStore
from aifactory.run.store import TaskChainRow
from aifactory.skill import envelope_problems
from aifactory.web import create_app

BASE = "http://127.0.0.1:4700"


def _get(root: Path, tmp_path: Path) -> Any:
    client = TestClient(create_app(root, static_dir=tmp_path / "nostatic"), base_url=BASE)
    response = client.get("/api/chains")
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == 200, body
    return body["data"]


def test_no_trace_db_no_chains(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "repo")
    data = _get(root, tmp_path)
    assert data["chains"] == []
    assert not (root / ".factory" / "trace.db").exists()


def test_chain_with_runs_slots_and_skips(tmp_path: Path) -> None:
    root = make_trace_db(tmp_path / "repo", os.getpid())
    store = TaskRunStore(root / ".factory" / "trace.db")
    try:
        runs = [r for r in store.all_runs() if r.state in ("running", "succeeded")][:2]
        running = [r for r in store.all_runs() if r.state == "running"]
        assert running, "the fixture has a running run"
        chosen = [running[0], *[r for r in runs if r.run_id != running[0].run_id][:1]]
        now = str(now_iso())
        store.start_chain(TaskChainRow("c1", T1, os.getpid(), 3, "running", now, now))
        skip = {"task_id": "X", "reason": "writes_overlap", "detail": "PR u: a", "waits_on": []}
        store.update_chain(
            "c1", run_ids=[r.run_id for r in chosen], skipped=[skip], exclusive=["W"]
        )
    finally:
        store.close()
    data = _get(root, tmp_path)
    assert data["max_parallel_runs"] == 1
    (chain,) = data["chains"]
    assert chain["chain_id"] == "c1" and chain["state"] == "running"
    assert [r["run_id"] for r in chain["runs"]] == [r.run_id for r in chosen]
    assert chain["running"] == sum(1 for r in chosen if r.state == "running")
    assert chain["free_slots"] == 3 - chain["running"]
    assert chain["skipped"] == [skip]
    assert chain["exclusive"] == ["W"]


def _client(root: Path, tmp_path: Path) -> TestClient:
    return TestClient(create_app(root, static_dir=tmp_path / "nostatic"), base_url=BASE)


def _chain(root: Path, row: TaskChainRow, run_ids: list[str], **fields: Any) -> None:
    store = TaskRunStore(root / ".factory" / "trace.db")
    try:
        store.start_chain(row)
        store.update_chain(row.chain_id, run_ids=run_ids, **fields)
    finally:
        store.close()


def test_every_run_shows_its_result(tmp_path: Path) -> None:
    root = make_trace_db(tmp_path / "repo", os.getpid())
    now = str(now_iso())
    _chain(
        root,
        TaskChainRow("c1", T1, None, 1, "running", now, now),
        ["r-ok", "r-fail"],
        state="finished",
        stop="failed",
    )
    (chain,) = _get(root, tmp_path)["chains"]
    ok, failed = chain["runs"]
    assert (ok["run_id"], ok["state"], ok["workflow"], ok["error"]) == (
        "r-ok",
        "succeeded",
        "plan-commit",
        None,
    )
    assert ok["pr"] == {
        "url": "https://example.test/pr/7",
        "pr_id": "7",
        "state": "open",
        "merged_by": None,
        "auto_merge_error": None,
    }
    assert (failed["state"], failed["error"], failed["pr"]) == ("failed", "accept not met", None)


def test_a_sequential_chain_shows_the_run_going_on_in_its_process(tmp_path: Path) -> None:
    root = make_trace_db(tmp_path / "repo", os.getpid())
    now = str(now_iso())
    # the chain records r-ok when it ended; r-run (same process) is not recorded yet
    _chain(root, TaskChainRow("c1", T1, os.getpid(), 1, "running", now, now), ["r-ok"])
    (chain,) = _get(root, tmp_path)["chains"]
    assert [(r["run_id"], r["state"]) for r in chain["runs"]] == [
        ("r-ok", "succeeded"),
        ("r-run", "running"),
    ]
    assert (chain["running"], chain["free_slots"]) == (1, 0)


def test_dismiss_erases_an_ended_chain(tmp_path: Path) -> None:
    root = make_trace_db(tmp_path / "repo", os.getpid())
    now = str(now_iso())
    _chain(root, TaskChainRow("live", T1, os.getpid(), 1, "running", now, now), [])
    _chain(
        root,
        TaskChainRow("old", T1, None, 1, "running", now, now),
        ["r-ok", "r-fail"],
        state="finished",
        stop="failed",
    )
    client = _client(root, tmp_path)
    response = client.post("/api/chains/live/dismiss")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "chain_running"
    response = client.post("/api/chains/old/dismiss")
    assert response.status_code == 200, response.json()
    assert response.json()["data"] == {"dismissed": "old"}
    assert [c["chain_id"] for c in _get(root, tmp_path)["chains"]] == ["live"]
    response = client.post("/api/chains/old/dismiss")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_chain"
    # its runs stay
    store = TaskRunStore(root / ".factory" / "trace.db")
    try:
        assert store.get("r-ok") is not None and store.get("r-fail") is not None
    finally:
        store.close()
