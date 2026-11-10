"""Bounded probe processes: the time budget, and stopping only the probe's own tree."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from aifactory import oscompat, procrun
from aifactory.check.machine import SystemMachine
from aifactory.providers import git

# A command that starts a helper keeping the inherited output open, then hangs: waiting for
# EOF on pipes would block until the helper ends.
_HELPER = "import time; time.sleep(60)"


def _hanging(pid_file: Path) -> list[str]:
    script = (
        "import subprocess, sys, time\n"
        f"helper = subprocess.Popen([sys.executable, '-c', {_HELPER!r}])\n"
        f"open({str(pid_file)!r}, 'w').write(str(helper.pid))\n"
        "print('started', flush=True)\n"
        "time.sleep(60)\n"
    )
    return [sys.executable, "-c", script]


def _gone(pid: int, seconds: float = 10) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not oscompat.alive(pid):
            return True
        time.sleep(0.05)
    return False


def test_run_returns_output_and_exit_code() -> None:
    done = procrun.run([sys.executable, "-c", "import sys; print('out'); sys.exit(3)"], 30)
    assert done.returncode == 3 and done.stdout.strip() == "out"


def test_timeout_stops_the_probe_tree_but_not_other_processes(tmp_path: Path) -> None:
    pid_file = tmp_path / "helper.pid"
    bystander = subprocess.Popen([sys.executable, "-c", _HELPER])  # a task or other app
    try:
        started = time.monotonic()
        with pytest.raises(subprocess.TimeoutExpired):
            procrun.run(_hanging(pid_file), 2)
        assert time.monotonic() - started < 15, "an inherited pipe must not block the timeout"
        helper = int(pid_file.read_text())
        assert _gone(helper), "the probe's helper process must be stopped with it"
        assert bystander.poll() is None, "a process outside the probe is never stopped"
    finally:
        bystander.kill()
        bystander.wait()


def test_budget_shortens_a_probe_and_refuses_one_after_it() -> None:
    with procrun.budget(0.5):
        shortened = procrun.limit(15)
        assert shortened is not None and shortened <= 0.5
        started = time.monotonic()
        with pytest.raises(subprocess.TimeoutExpired):
            procrun.run([sys.executable, "-c", _HELPER], 30)
        assert time.monotonic() - started < 10
        with pytest.raises(procrun.BudgetExceeded):
            procrun.limit(15, ["claude", "auth", "status"])
    # Outside the budget (and in other threads) nothing is limited.
    assert procrun.limit(15) == 15 and procrun.remaining() is None


def test_nested_budget_never_extends_the_outer_one() -> None:
    with procrun.budget(1.0), procrun.budget(100.0):
        left = procrun.remaining()
        assert left is not None and left <= 1.0


def test_system_machine_probe_times_out_to_none() -> None:
    started = time.monotonic()
    assert SystemMachine().run([sys.executable, "-c", _HELPER], timeout=0.5) is None
    assert time.monotonic() - started < 10


def test_git_respects_a_spent_budget(tmp_path: Path) -> None:
    with procrun.budget(0.0), pytest.raises(procrun.BudgetExceeded):
        git.run_bytes(tmp_path, ["--version"])
    assert git.run_bytes(tmp_path, ["--version"]).returncode == 0
