"""Worktree cleanup stops only its own processes, on Windows and POSIX alike."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import psutil
import pytest

from aifactory import worktree_processes as cleanup


def process(pid: int, exe: Path, cwd: Path) -> Mock:
    return Mock(pid=pid, exe=Mock(return_value=str(exe)), cwd=Mock(return_value=str(cwd)))


@pytest.mark.parametrize("attribute", ["exe", "cwd"])
def test_cleanup_matches_exact_directory_and_preserves_self_and_parents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, attribute: str
) -> None:
    root = tmp_path / "worktree"
    root.mkdir()
    outside = tmp_path / "worktree-other"
    selected = process(100001, outside / "python", outside)
    getattr(selected, attribute).return_value = str(root / "engine" / "RtDaemon.exe")
    unrelated = process(100002, outside / "RtDaemon.exe", outside)
    own = process(os.getpid(), root / "factory", root)
    ancestor = process(100003, root / "factory", root)
    monkeypatch.setattr(psutil, "Process", lambda: Mock(parents=lambda: [ancestor]))
    monkeypatch.setattr(psutil, "process_iter", lambda: [own, ancestor, unrelated, selected])
    wait = Mock(return_value=([selected], []))
    monkeypatch.setattr(psutil, "wait_procs", wait)

    cleanup.stop_directory_processes(root)

    selected.terminate.assert_called_once()
    selected.kill.assert_not_called()
    for kept in (own, ancestor, unrelated):
        kept.terminate.assert_not_called()
    assert wait.call_args_list[0].args[0] == [selected]


@pytest.mark.parametrize("failure", ["stubborn", "denied", "survives"])
def test_cleanup_escalates_and_reports_processes_it_cannot_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    selected = process(100001, tmp_path / "app.exe", tmp_path)
    monkeypatch.setattr(psutil, "process_iter", lambda: [selected])
    if failure == "denied":
        selected.terminate.side_effect = psutil.AccessDenied(selected.pid)
    wait = Mock(side_effect=[([], [selected]), ([], [selected] if failure == "survives" else [])])
    monkeypatch.setattr(psutil, "wait_procs", wait)
    if failure == "stubborn":
        cleanup.stop_directory_processes(tmp_path)
        selected.kill.assert_called_once()
    else:
        with pytest.raises(OSError, match="100001"):
            cleanup.stop_directory_processes(tmp_path)


def test_cleanup_handles_exited_and_inaccessible_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gone = process(100001, tmp_path, tmp_path)
    gone.exe.side_effect = psutil.NoSuchProcess(gone.pid)
    inaccessible = process(100002, tmp_path, tmp_path)
    inaccessible.exe.side_effect = psutil.AccessDenied(inaccessible.pid)
    inaccessible.cwd.side_effect = psutil.AccessDenied(inaccessible.pid)
    # An inaccessible executable must not hide a matching cwd.
    selected = process(100003, tmp_path, tmp_path)
    selected.exe.side_effect = psutil.AccessDenied(selected.pid)
    monkeypatch.setattr(psutil, "process_iter", lambda: [gone, inaccessible, selected])
    monkeypatch.setattr(psutil, "wait_procs", lambda *_args, **_kwargs: ([], []))
    cleanup.stop_directory_processes(tmp_path)
    gone.terminate.assert_not_called()
    inaccessible.terminate.assert_not_called()
    selected.terminate.assert_called_once()


def test_cleanup_stops_real_process_in_worktree(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    with subprocess.Popen(
        [sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(60)"],
        cwd=worktree,
        stdout=subprocess.PIPE,
        text=True,
    ) as child:
        try:
            assert child.stdout is not None and child.stdout.readline().strip() == "ready"
            cleanup.stop_directory_processes(worktree)
            assert child.wait(timeout=5) is not None
            worktree.rmdir()
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
