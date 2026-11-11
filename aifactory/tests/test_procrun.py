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


@pytest.mark.parametrize("command", [["git", "rev-parse", "HEAD"], "git rev-parse HEAD"])
@pytest.mark.parametrize("left", [0.0, 0.27, 0.99])
def test_limit_refuses_git_with_insufficient_remaining_time(
    monkeypatch: pytest.MonkeyPatch, command: list[str] | str, left: float
) -> None:
    monkeypatch.setattr(procrun, "_clock", lambda: 100.0)
    with procrun.budget(left), pytest.raises(procrun.BudgetExceeded) as caught:
        procrun.limit(None, command)
    assert caught.value.cmd == command


def test_limit_allows_usable_git_budget_and_preserves_other_probe_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(procrun, "_clock", lambda: 100.0)
    with procrun.budget(1.0):
        assert procrun.limit(None, ["git", "status"]) == 1.0
        assert procrun.limit(0.5, ["git", "status"]) == 0.5
    with procrun.budget(0.27):
        assert procrun.limit(15, ["claude", "--version"]) == pytest.approx(0.27)
    assert procrun.limit(None, ["git", "status"]) is None


def test_git_budget_can_expire_between_commands_without_starting_another(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [100.0]
    calls: list[list[str]] = []
    monkeypatch.setattr(procrun, "_clock", lambda: clock[0])

    def finish(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(argv)
        clock[0] = 109.73
        return subprocess.CompletedProcess(argv, 0, b"head\n", b"")

    monkeypatch.setattr(subprocess, "run", finish)
    with procrun.budget(10.0):
        assert git.run_bytes(tmp_path, ["rev-parse", "HEAD"]).returncode == 0
        with pytest.raises(procrun.BudgetExceeded):
            git.run_bytes(tmp_path, ["ls-tree", "HEAD"])
    assert calls == [["git", "rev-parse", "HEAD"]]


def test_system_machine_probe_times_out_to_none() -> None:
    started = time.monotonic()
    assert SystemMachine().run([sys.executable, "-c", _HELPER], timeout=0.5) is None
    assert time.monotonic() - started < 10


def test_git_respects_a_spent_budget(tmp_path: Path) -> None:
    with procrun.budget(0.0), pytest.raises(procrun.BudgetExceeded):
        git.run_bytes(tmp_path, ["--version"])
    assert git.run_bytes(tmp_path, ["--version"]).returncode == 0
