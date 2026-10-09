"""SIGTERM ends the run and closes the trace rows of the run and its agent child."""

from __future__ import annotations

import os
import signal
import sys

import pytest
from engine_fakes import (  # noqa: F401
    FAKE_CHILD_PID,
    EngineEnv,
    agent_phase,
    engine_env_fixture,
    events_of,
    rows,
    start,
)


@pytest.mark.skipif(sys.platform == "win32", reason="Windows cannot send itself SIGTERM")
def test_sigterm_closes_agent_child_and_fails_run(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)
    env.fake.during = lambda: os.kill(os.getpid(), signal.SIGTERM)
    env.script.add_ok("builder")

    with pytest.raises(SystemExit) as exc:
        agent_phase(run, "builder")

    assert exc.value.code == 128 + signal.SIGTERM
    procs = rows(
        env.db_path,
        "SELECT kind, name, pid, ended_at FROM processes WHERE adw_id=? ORDER BY id",
        run.adw_id,
    )
    assert [(k, n, p) for k, n, p, _ in procs] == [
        ("adw", "", os.getpid()),
        ("agent", "builder", FAKE_CHILD_PID),
    ]
    assert all(ended is not None for *_, ended in procs)
    status = rows(env.db_path, "SELECT status FROM sessions WHERE adw_id=?", run.adw_id)
    assert status == [("fail",)]

    phase_id = f"{run.adw_id}_01_builder"
    assert rows(env.db_path, "SELECT status FROM phases WHERE phase_id=?", phase_id) == [("fail",)]
    events = events_of(env.db_path, phase_id)
    assert any(t == "error" for t, _, _ in events)
    assert events[-1][0] == "phase_end" and events[-1][2] == {"status": "fail"}


def test_ensure_installs_signal_handlers(engine_env: EngineEnv) -> None:
    before = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    start(engine_env)
    for sig, handler in before.items():
        assert signal.getsignal(sig) is not handler
