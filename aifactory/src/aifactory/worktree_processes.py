"""Stop processes whose executable or working directory belongs to a removed worktree."""

from __future__ import annotations

import os
from pathlib import Path

import psutil

STOP_WAIT = 3.0


def stop_directory_processes(path: Path) -> None:
    """Stop only processes rooted in `path`, then wait for Windows file handles to close.

    psutil checks PID reuse before signalling. Never signal this process or its parents.
    Processes we cannot inspect (e.g. another user's system processes) are left alone.
    A matched process that cannot be stopped prevents deletion of the directory.
    """
    root = path.resolve()
    protected = {os.getpid(), *(p.pid for p in psutil.Process().parents())}
    matched: list[psutil.Process] = []
    for process in psutil.process_iter():
        if process.pid in protected:
            continue
        try:
            belongs = False
            for attribute in (process.exe, process.cwd):
                try:
                    value = attribute()
                except psutil.AccessDenied:
                    continue
                if value and Path(value).resolve().is_relative_to(root):
                    belongs = True
                    break
            if belongs:
                process.terminate()
                matched.append(process)
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as exc:
            raise OSError(f"cannot stop process {process.pid} in {root}") from exc
    _, alive = psutil.wait_procs(matched, timeout=STOP_WAIT)
    for process in alive:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as exc:
            raise OSError(f"cannot kill process {process.pid} in {root}") from exc
    _, alive = psutil.wait_procs(alive, timeout=STOP_WAIT)
    if alive:
        raise OSError(f"processes still running in {root}: {', '.join(str(p.pid) for p in alive)}")
