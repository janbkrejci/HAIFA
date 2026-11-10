"""A timed-out check stops its whole process tree, real processes, no mocks of the kill.

Every command here is a bounded Python script: workers sleep at most WORKER_LIFE seconds
and record their pid, so the tests can check that nothing they started survives, while
a process started outside the command stays alive.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aifactory import oscompat
from aifactory.engine import quality
from aifactory.engine.data_types import QualityCheckResult, QualityCheckSpec

WORKER_LIFE = 60  # a leaked worker still ends by itself


def _run(tmp_path: Path, argv: list[str], timeout: float) -> QualityCheckResult:
    run = SimpleNamespace(
        phases=[SimpleNamespace(seq=1, phase_id="p1")],
        context_handoff_dir=tmp_path / "handoff",
        console=SimpleNamespace(note=lambda message: None),
        repo_root=tmp_path,
        tracer=SimpleNamespace(event=lambda event: None),
        adw_id="t0000001",
    )
    spec = QualityCheckSpec(name="check", area="backend", operation="build", argv=argv)
    spec.timeout_seconds = timeout  # type: ignore[assignment]
    return quality._run(spec, run)


def _worker(pids: Path) -> str:
    """A worker that records its pid in `pids`, then sleeps."""
    return (
        "import os, pathlib, time; "
        f"pathlib.Path({str(pids)!r}, str(os.getpid())).touch(); "
        f"time.sleep({WORKER_LIFE})"
    )


def _recorded(pids: Path) -> list[int]:
    return [int(path.name) for path in pids.iterdir()]


def _wait_dead(pids: list[int], seconds: float = 5) -> list[int]:
    deadline = time.monotonic() + seconds
    alive = [pid for pid in pids if oscompat.alive(pid)]
    while alive and time.monotonic() < deadline:
        time.sleep(0.05)
        alive = [pid for pid in alive if oscompat.alive(pid)]
    return alive


@pytest.fixture
def bystander() -> Any:
    """A process outside the command; a timeout must not touch it."""
    process = subprocess.Popen(
        [sys.executable, "-c", f"import time; time.sleep({WORKER_LIFE})"],
        creationflags=oscompat.NEW_GROUP,
        start_new_session=True,
    )
    yield process
    process.kill()
    process.wait()


def test_timeout_stops_the_tree_and_keeps_output(tmp_path: Path, bystander: Any) -> None:
    pids = tmp_path / "pids"
    pids.mkdir()
    script = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {_worker(pids)!r}])\n"
        "print('before the limit', flush=True)\n"
        "print('stderr before the limit', file=sys.stderr, flush=True)\n"
        f"time.sleep({WORKER_LIFE})\n"
    )
    clock = time.monotonic()
    result = _run(tmp_path, [sys.executable, "-c", script], timeout=3)
    assert time.monotonic() - clock < 3 + oscompat.KILL_WAIT + 5
    assert result.returncode == 124
    assert result.passed is False
    log = Path(result.output_artifact).read_text(encoding="utf-8")
    assert "exit: 124" in log
    assert "before the limit" in log
    assert "stderr before the limit" in log
    assert "Timed out: exceeded the time limit of 3s." in log
    assert "stopped" in log
    assert len(_recorded(pids)) == 1
    assert _wait_dead(_recorded(pids)) == []
    assert oscompat.alive(bystander.pid)
    assert bystander.poll() is None


def test_timeout_stops_children_started_during_the_kill(tmp_path: Path, bystander: Any) -> None:
    """Like xdist replacing a crashed worker: a dying worker is respawned at once."""
    pids = tmp_path / "pids"
    pids.mkdir()
    controller = (
        "import subprocess, sys\n"
        f"argv = [sys.executable, '-c', {_worker(pids)!r}]\n"
        "workers = [subprocess.Popen(argv) for _ in range(4)]\n"
        "print('controller up', flush=True)\n"
        "while True:\n"
        "    for index, worker in enumerate(workers):\n"
        "        if worker.poll() is not None:\n"
        "            print('node down, respawning', flush=True)\n"
        "            workers[index] = subprocess.Popen(argv)\n"
    )
    result = _run(tmp_path, [sys.executable, "-c", controller], timeout=4)
    assert result.returncode == 124
    assert "controller up" in Path(result.output_artifact).read_text(encoding="utf-8")
    assert len(_recorded(pids)) >= 4
    time.sleep(0.5)  # a child that escaped would record its pid by now
    assert _wait_dead(_recorded(pids)) == []
    assert bystander.poll() is None


def test_timeout_stops_a_child_whose_parent_already_exited(tmp_path: Path) -> None:
    """taskkill /T walks parent links and misses a grandchild of an exited parent."""
    pids = tmp_path / "pids"
    pids.mkdir()
    middle = (
        f"import subprocess, sys\nsubprocess.Popen([sys.executable, '-c', {_worker(pids)!r}])\n"
    )
    root = (
        "import pathlib, subprocess, sys, time\n"
        f"subprocess.run([sys.executable, '-c', {middle!r}], check=True)\n"
        f"while not any(pathlib.Path({str(pids)!r}).iterdir()): time.sleep(0.02)\n"
        "print('orphan running', flush=True)\n"
        f"time.sleep({WORKER_LIFE})\n"
    )
    result = _run(tmp_path, [sys.executable, "-c", root], timeout=4)
    assert result.returncode == 124
    assert "orphan running" in Path(result.output_artifact).read_text(encoding="utf-8")
    assert len(_recorded(pids)) == 1
    assert _wait_dead(_recorded(pids)) == []


def test_normal_completion_keeps_exit_code_output_and_background_helper(tmp_path: Path) -> None:
    pids = tmp_path / "pids"
    pids.mkdir()
    helper = (
        "import os, pathlib, time; "
        f"pathlib.Path({str(pids)!r}, str(os.getpid())).touch(); time.sleep(3)"
    )
    script = (
        "import pathlib, subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {helper!r}])\n"
        f"while not any(pathlib.Path({str(pids)!r}).iterdir()): time.sleep(0.02)\n"
        "print('done', flush=True)\n"
        "raise SystemExit(3)\n"
    )
    result = _run(tmp_path, [sys.executable, "-c", script], timeout=30)
    assert result.returncode == 3
    log = Path(result.output_artifact).read_text(encoding="utf-8")
    assert "done" in log
    assert "Timed out" not in log
    # Only a timeout stops the tree: a helper of a finished command runs on.
    assert all(oscompat.alive(pid) for pid in _recorded(pids))
    assert _wait_dead(_recorded(pids), seconds=15) == []


def test_kill_of_an_already_exited_command(tmp_path: Path) -> None:
    with oscompat.ProcessTree() as tree:
        process = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            creationflags=oscompat.NEW_GROUP | tree.creationflags,
            start_new_session=True,
        )
        tree.adopt(process)
        assert process.wait(timeout=30) == 0
        assert "stopped" in tree.kill(process)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows job object")
def test_without_a_job_object_the_kill_falls_back_to_taskkill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oscompat._kernel32, "CreateJobObjectW", lambda *args: None)
    pids = tmp_path / "pids"
    pids.mkdir()
    script = (
        "import pathlib, subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {_worker(pids)!r}])\n"
        f"while not any(pathlib.Path({str(pids)!r}).iterdir()): time.sleep(0.02)\n"
        f"time.sleep({WORKER_LIFE})\n"
    )
    result = _run(tmp_path, [sys.executable, "-c", script], timeout=3)
    assert result.returncode == 124
    assert "taskkill /T /F (no job object)" in Path(result.output_artifact).read_text(
        encoding="utf-8"
    )
    assert _wait_dead(_recorded(pids)) == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows job object")
def test_a_command_in_the_job_starts_and_runs_normally(tmp_path: Path) -> None:
    """The command starts suspended; adopt must resume it, children included."""
    script = (
        "import subprocess, sys\n"
        "child = subprocess.run([sys.executable, '-c', 'print(42)'],\n"
        "                       capture_output=True, text=True)\n"
        "print('child said', child.stdout.strip(), 'exit', child.returncode, flush=True)\n"
    )
    result = _run(tmp_path, [sys.executable, "-c", script], timeout=30)
    assert result.returncode == 0
    assert "child said 42 exit 0" in Path(result.output_artifact).read_text(encoding="utf-8")
