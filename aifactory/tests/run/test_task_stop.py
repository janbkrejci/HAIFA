"""``stop_run`` and ``factory task stop``: SIGTERM to agents and the run, state ``stopped``."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import psutil
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))

from trace_fixture import T1, T2, make_trace_db  # noqa: E402

from aifactory import oscompat  # noqa: E402
from aifactory.run import STOPPED, TaskRunError, TaskRunStore, stop_run  # noqa: E402
from aifactory.run.store import FAILED  # noqa: E402
from cli_json import run_json  # noqa: E402

Capsys = pytest.CaptureFixture[str]
Spawn = list[subprocess.Popen[bytes]]


@pytest.fixture(name="procs")
def procs_fixture() -> Iterator[Spawn]:
    spawned: Spawn = []
    yield spawned
    for proc in spawned:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)


def _sleeper(procs: Spawn) -> subprocess.Popen[bytes]:
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    procs.append(proc)
    return proc


def _db(repo: Path) -> Path:
    return repo / ".factory" / "trace.db"


def _repo(tmp_path: Path, pid: int) -> Path:
    repo = make_trace_db(tmp_path / "repo", os.getpid())
    store = TaskRunStore(_db(repo))
    store.conn.execute(
        "UPDATE task_runs SET pid = ?, pid_created_at = ? WHERE run_id = 'r-run'",
        (pid, oscompat.process_created_at(pid)),
    )
    store.close()
    return repo


def _add_process(repo: Path, kind: str, pid: int, command: str) -> None:
    conn = sqlite3.connect(str(_db(repo)))
    columns = {r[1] for r in conn.execute("PRAGMA table_info(processes)")}
    if "pid_created_at" not in columns:
        conn.execute("ALTER TABLE processes ADD COLUMN pid_created_at REAL")
    conn.execute(
        "INSERT INTO processes (adw_id, kind, name, pid, command, started_at, pid_created_at) "
        "VALUES ('r-run', ?, 'planner', ?, ?, '2026-01-03T10:00:00+00:00', ?)",
        (kind, pid, command, oscompat.process_created_at(pid)),
    )
    conn.commit()
    conn.close()


def _state(repo: Path, run_id: str) -> str:
    store = TaskRunStore(_db(repo))
    row = store.get(run_id)
    store.close()
    assert row is not None
    return row.state


def test_stop_signals_agents_then_run(tmp_path: Path, procs: Spawn) -> None:
    run = _sleeper(procs)
    agent = _sleeper(procs)
    recycled = _sleeper(procs)
    repo = _repo(tmp_path, run.pid)
    exe = Path(sys.executable).name
    _add_process(repo, "adw", run.pid, "factory task run")
    _add_process(repo, "agent", agent.pid, f"{exe} planner model")
    _add_process(repo, "agent", recycled.pid, "claude planner opus")

    result = stop_run(repo, "r-run", timeout=5)

    assert result.run.state == STOPPED
    assert result.signalled == [agent.pid, run.pid]
    assert result.killed == []
    assert run.wait(timeout=10) is not None
    assert agent.wait(timeout=10) is not None
    assert recycled.poll() is None  # its command is not what the trace recorded
    conn = sqlite3.connect(str(_db(repo)))
    live = conn.execute(
        "SELECT COUNT(*) FROM processes WHERE adw_id = 'r-run' AND ended_at IS NULL"
    ).fetchone()
    status = conn.execute("SELECT status FROM sessions WHERE adw_id = 'r-run'").fetchone()
    conn.close()
    assert live == (0,)
    assert status == ("fail",)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows has no SIGTERM: the first stop is already a forced kill",
)
def test_stop_kills_what_ignores_sigterm(tmp_path: Path, procs: Spawn) -> None:
    code = (
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print(1, flush=True); time.sleep(60)"
    )
    stubborn = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE)
    procs.append(stubborn)
    assert stubborn.stdout is not None
    stubborn.stdout.readline()  # the handler is installed
    repo = _repo(tmp_path, stubborn.pid)

    result = stop_run(repo, "r-run", timeout=0.5)

    assert result.killed == [stubborn.pid]
    assert stubborn.wait(timeout=10) is not None


def test_finish_does_not_overwrite_stopped(tmp_path: Path) -> None:
    repo = _repo(tmp_path, os.getpid())
    store = TaskRunStore(_db(repo))
    assert store.mark_stopped("r-run", "stopped by user") is True
    store.finish("r-run", FAILED, None, "interrupted")
    assert store.mark_stopped("r-run", "again") is False
    store.close()
    assert _state(repo, "r-run") == STOPPED


def test_stop_own_process_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path, os.getpid())
    with pytest.raises(TaskRunError) as err:
        stop_run(repo, "r-run")
    assert err.value.code == "run_not_running"
    assert _state(repo, "r-run") == "running"


def test_dead_or_unknown_run(tmp_path: Path, procs: Spawn) -> None:
    dead = _sleeper(procs)
    dead.kill()
    dead.wait(timeout=10)
    repo = _repo(tmp_path, dead.pid)
    with pytest.raises(TaskRunError) as err:
        stop_run(repo, "r-run")
    assert err.value.code == "run_not_running"
    assert _state(repo, "r-run") == "aborted"
    with pytest.raises(TaskRunError) as unknown:
        stop_run(repo, "nope")
    assert unknown.value.code == "unknown_run"


def test_cli_stop(tmp_path: Path, procs: Spawn, capsys: Capsys) -> None:
    run = _sleeper(procs)
    repo = _repo(tmp_path, run.pid)
    capsys.readouterr()

    rc, env = run_json(capsys, ["task", "stop", T2, "--json", "--repo", str(repo)])
    assert rc == 0
    assert env["data"]["run"]["state"] == "stopped"
    assert env["data"]["signalled"] == [run.pid]
    assert run.wait(timeout=10) is not None

    rc, env = run_json(capsys, ["task", "stop", T2, "--json", "--repo", str(repo)])
    assert rc == 2
    assert env["error"]["code"] == "run_not_running"

    rc, env = run_json(capsys, ["task", "stop", T2, "--run", "r-ok", "--json", "--repo", str(repo)])
    assert rc == 2
    assert env["error"]["code"] == "invalid_value"

    rc, env = run_json(capsys, ["task", "stop", T1, "--run", "r-ok", "--json", "--repo", str(repo)])
    assert rc == 2
    assert env["error"]["code"] == "run_not_running"


def test_stop_never_signals_recycled_parent(tmp_path: Path, procs: Spawn) -> None:
    unrelated = _sleeper(procs)
    repo = _repo(tmp_path, unrelated.pid)
    with sqlite3.connect(_db(repo)) as conn:
        conn.execute(
            "UPDATE task_runs SET pid_created_at = pid_created_at - 100 WHERE run_id = 'r-run'"
        )
    with pytest.raises(TaskRunError, match="run_not_running"):
        stop_run(repo, "r-run", timeout=0)
    assert unrelated.poll() is None
    assert _state(repo, "r-run") == "aborted"


def test_stop_refuses_legacy_parent_without_identity(tmp_path: Path, procs: Spawn) -> None:
    unrelated = _sleeper(procs)
    repo = _repo(tmp_path, unrelated.pid)
    with sqlite3.connect(_db(repo)) as conn:
        conn.execute("UPDATE task_runs SET pid_created_at = NULL WHERE run_id = 'r-run'")
    with pytest.raises(TaskRunError, match="process_identity_unconfirmed"):
        stop_run(repo, "r-run", timeout=0)
    assert unrelated.poll() is None
    assert _state(repo, "r-run") == "running"


@pytest.mark.parametrize("created_at", [None, 1.0])
def test_stop_skips_recycled_or_legacy_child_with_same_command(
    tmp_path: Path, procs: Spawn, created_at: float | None
) -> None:
    run = _sleeper(procs)
    unrelated = _sleeper(procs)
    repo = _repo(tmp_path, run.pid)
    _add_process(repo, "agent", unrelated.pid, Path(sys.executable).name)
    with sqlite3.connect(_db(repo)) as conn:
        conn.execute(
            "UPDATE processes SET pid_created_at = ? WHERE pid = ?", (created_at, unrelated.pid)
        )
    result = stop_run(repo, "r-run", timeout=1)
    assert result.signalled == [run.pid]
    assert result.unverified == [unrelated.pid]
    assert unrelated.poll() is None


def test_force_escalation_rechecks_identity(
    tmp_path: Path, procs: Spawn, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.run import stop

    run = _sleeper(procs)
    repo = _repo(tmp_path, run.pid)
    calls: list[tuple[int, bool]] = []

    def signal(pid: int, *, force: bool, created_at: float | None) -> bool:
        calls.append((pid, force))
        # Simulate reuse after TERM without signalling any real process.
        monkeypatch.setattr(oscompat, "process_matches", lambda pid, created_at: False)
        return True

    monkeypatch.setattr(stop, "_signal", signal)
    result = stop_run(repo, "r-run", timeout=0)
    assert calls == [(run.pid, False)]
    assert result.killed == []
    assert run.poll() is None


def test_windows_descendants_are_captured_child_first(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from aifactory.run import stop

    child = SimpleNamespace(pid=12, create_time=lambda: 2.0)
    grandchild = SimpleNamespace(pid=13, create_time=lambda: 3.0)

    def children(*, recursive: bool) -> list[object]:
        assert recursive
        return [child, grandchild]

    parent = SimpleNamespace(create_time=lambda: 1.0, children=children)
    monkeypatch.setattr(psutil, "Process", lambda pid: parent)
    assert stop._descendants(11, 1.0) == [(13, 3.0), (12, 2.0)]
    assert stop._descendants(11, 9.0) == []
    assert stop._descendants(11, None) == []


def test_windows_stop_keeps_descendant_identity_for_escalation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from aifactory.run import stop

    parent = 2_000_000_000
    repo = _repo(tmp_path, parent)
    with sqlite3.connect(_db(repo)) as conn:
        conn.execute("UPDATE task_runs SET pid_created_at = 1 WHERE run_id = 'r-run'")
    monkeypatch.setattr(stop, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(stop, "_alive", lambda pid: True)
    monkeypatch.setattr(stop, "_running", lambda pid: True)
    monkeypatch.setattr(stop, "_descendants", lambda pid, created_at: [(13, 3.0), (12, 2.0)])
    calls: list[tuple[int, bool, float | None]] = []

    def signal(pid: int, *, force: bool, created_at: float | None) -> bool:
        calls.append((pid, force, created_at))
        return True

    monkeypatch.setattr(stop, "_signal", signal)
    # Child 12's PID is reused between TERM and KILL. No real PID is signalled.
    monkeypatch.setattr(
        oscompat, "process_matches", lambda pid, created_at: not (pid == 12 and len(calls) >= 3)
    )
    result = stop_run(repo, "r-run", timeout=0)
    assert calls == [
        (13, False, 3.0),
        (12, False, 2.0),
        (parent, False, 1.0),
        (13, True, 3.0),
        (parent, True, 1.0),
    ]
    assert result.signalled == [13, 12, parent]
    assert result.killed == [13, parent]
