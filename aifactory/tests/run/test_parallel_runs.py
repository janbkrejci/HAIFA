"""Parallel runs: different tasks at once, the same task once, trace DB in WAL (task 1.12)."""

from __future__ import annotations

import multiprocessing
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from run_repo import Script, fake_env, git, make_run_repo, ok, write
from test_auto_continue import T01, T03, open_pr, runs_of, setup_chain

from aifactory.engine.tracer import Tracer
from aifactory.run import TaskRunError, TaskRunStore, run_task


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    repo = make_run_repo(tmp_path / "repo")
    setup_chain(repo)
    return repo


def trace_db(repo: Path) -> Path:
    return repo / ".factory" / "trace.db"


def _fork() -> Any:
    if "fork" not in multiprocessing.get_all_start_methods():
        pytest.skip("needs the fork start method")
    return multiprocessing.get_context("fork")


def _child(
    script: Script,
    repo: Path,
    tid: str,
    name: str,
    before: Callable[[], object],
    inside: Callable[[Path], object],
    out: Any,
) -> None:
    """Runs in a forked process: scripts its own planner call, reports the outcome."""
    rel = f"src/app/{name}.py"
    script.add("planner", ok(artifacts=[], changed_files=[rel], commit_message=f"Add {name}"))

    def effect(cwd: Path) -> None:
        inside(cwd)
        write(cwd, rel, f"NAME = {name!r}\n")

    script.on("planner", effect)
    try:
        before()
        result = run_task(repo, tid)
        out.put((tid, "ok" if result.ok else f"failed: {result.run.error}", result.run.branch))
    except TaskRunError as exc:
        out.put((tid, "error", exc.code))
    except BaseException as exc:  # pragma: no cover - reported to the parent
        out.put((tid, "crash", repr(exc)))


def _collect(procs: list[Any], out: Any) -> list[tuple[str, str, str]]:
    results = [out.get(timeout=120) for _ in procs]
    for p in procs:
        p.join(timeout=60)
        assert p.exitcode is not None
    return results


def _nothing() -> None:
    return None


def test_parallel_runs_of_different_tasks(repo: Path, script: Script) -> None:
    ctx = _fork()
    barrier = ctx.Barrier(2)
    out = ctx.Queue()

    def both_inside(cwd: Path) -> None:
        barrier.wait(timeout=60)  # both runs are inside their workflow at the same time

    procs = [
        ctx.Process(target=_child, args=(script, repo, tid, name, _nothing, both_inside, out))
        for tid, name in ((T01, "one"), (T03, "three"))
    ]
    for p in procs:
        p.start()
    results = sorted(_collect(procs, out))
    assert results == [(T01, "ok", f"factory/{T01}-1"), (T03, "ok", f"factory/{T03}-1")]
    worktrees = set()
    for tid in (T01, T03):
        rows = runs_of(repo, tid)
        assert [r.state for r in rows] == ["succeeded"]
        assert open_pr(repo, tid) is not None
        worktrees.add(rows[0].worktree)
    assert len(worktrees) == 2


def test_parallel_runs_on_fresh_trace_db(repo: Path, script: Script) -> None:
    """Two runs start together on a trace DB that does not exist yet; neither is locked out."""
    assert not trace_db(repo).exists()
    ctx = _fork()
    start = ctx.Barrier(2)
    inside = ctx.Barrier(2)
    out = ctx.Queue()

    def before() -> None:
        start.wait(timeout=60)

    def both_inside(cwd: Path) -> None:
        inside.wait(timeout=60)

    procs = [
        ctx.Process(target=_child, args=(script, repo, tid, name, before, both_inside, out))
        for tid, name in ((T01, "one"), (T03, "three"))
    ]
    for p in procs:
        p.start()
    results = sorted(_collect(procs, out))
    assert results == [(T01, "ok", f"factory/{T01}-1"), (T03, "ok", f"factory/{T03}-1")]
    for tid in (T01, T03):
        assert [r.state for r in runs_of(repo, tid)] == ["succeeded"]
    conn = sqlite3.connect(str(trace_db(repo)))
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        conn.close()


class _Out:
    """Forwards results; a refused start releases the winner."""

    def __init__(self, out: Any, loser_done: Any) -> None:
        self.out = out
        self.loser_done = loser_done

    def put(self, item: tuple[str, str, str]) -> None:
        self.out.put(item)
        if item[1] == "error":
            self.loser_done.set()


def test_concurrent_start_of_same_task_one_refused(repo: Path, script: Script) -> None:
    ctx = _fork()
    barrier = ctx.Barrier(2)
    loser_done = ctx.Event()
    out = ctx.Queue()

    def start() -> None:
        barrier.wait(timeout=60)

    def winner_waits(cwd: Path) -> None:
        # Keep the run going until the other process has been refused.
        assert loser_done.wait(timeout=60)

    procs = [
        ctx.Process(
            target=_child,
            args=(script, repo, T01, "one", start, winner_waits, _Out(out, loser_done)),
        )
        for _ in range(2)
    ]
    for p in procs:
        p.start()
    results = _collect(procs, out)
    outcomes = sorted(r[1:] for r in results)
    assert outcomes == [("error", "already_running"), ("ok", f"factory/{T01}-1")]
    assert [r.state for r in runs_of(repo, T01)] == ["succeeded"]
    branches = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/factory/")
    assert branches == f"factory/{T01}-1"


def test_tracer_opens_fresh_trace_db_while_store_holds_lock(tmp_path: Path) -> None:
    """The engine's Tracer asks for WAL before busy_timeout; the store must switch first."""
    db = tmp_path / "trace.db"
    assert not db.exists()
    store = TaskRunStore(db)
    outcome: list[BaseException | None] = []

    def open_tracer() -> None:
        try:
            tracer = Tracer(db, tmp_path / "events.jsonl")
            tracer.conn.close()  # sqlite connections stay in their own thread
            outcome.append(None)
        except BaseException as exc:
            outcome.append(exc)

    try:
        with store.serialized():
            thread = threading.Thread(target=open_tracer)
            thread.start()
            time.sleep(0.5)  # the Tracer starts while the write lock is held
        thread.join(timeout=10)
        assert not thread.is_alive()
        assert outcome == [None]
    finally:
        store.close()
    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        conn.close()
