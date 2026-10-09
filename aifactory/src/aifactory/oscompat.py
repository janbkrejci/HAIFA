"""The few OS calls that differ between POSIX and Windows.

On POSIX every function is the call the code used before (``fcntl.flock``,
``os.kill(pid, 0)``, ``os.kill``, ``os.killpg``, ``os.fchmod``). On Windows: ``lock`` is
``msvcrt.locking`` on byte 0 of the lock file, ``alive`` asks ``OpenProcess`` (there
``os.kill(pid, 0)`` would terminate the process), ``kill`` and ``kill_group`` are
``taskkill /T /F`` (the process with its children), ``fchmod`` does nothing and
``image_path`` (Windows only) stands in for ``ps -o command`` and ``utf8_stdio`` switches
stdout and stderr to UTF-8 (POSIX: nothing).
``NEW_GROUP`` goes to ``Popen(creationflags=...)`` next to ``start_new_session=True``,
which Windows ignores: the child gets its own process group and a hidden console of its
own, so neither Ctrl+C nor closing the parent's console window stops it.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

if sys.platform == "win32":
    import ctypes
    import msvcrt

    NEW_GROUP = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _STILL_ACTIVE = 259
    _ERROR_ACCESS_DENIED = 5

    def lock(fd: int, *, blocking: bool) -> None:
        """Lock `fd` exclusively; without `blocking` a held lock raises ``OSError``."""
        while True:
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if not blocking:
                    raise
                time.sleep(0.05)

    def unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

    def alive(pid: int) -> bool:
        """The process `pid` exists (a process of another user counts as alive)."""
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return bool(kernel32.GetLastError() == _ERROR_ACCESS_DENIED)
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)

    def image_path(pid: int) -> str | None:
        """The executable of the process `pid` (Windows only), None when it is gone."""
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            size = ctypes.c_ulong(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return None
            return buffer.value
        finally:
            kernel32.CloseHandle(handle)

    def _taskkill(pid: int) -> None:
        if not alive(pid):
            raise ProcessLookupError(pid)
        done = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
        # A parent that exits by itself once taskkill ended its child (a venv's python.exe
        # launcher does) makes taskkill fail, though the process is gone as asked.
        if done.returncode != 0 and alive(pid):
            raise ProcessLookupError(pid)

    def kill(pid: int, *, force: bool) -> None:
        """Stop `pid` (Windows: always forced, with its children)."""
        _taskkill(pid)

    def kill_group(pid: int, *, force: bool) -> None:
        """Stop the process group led by `pid` (Windows: the process tree, forced)."""
        _taskkill(pid)

    def fchmod(fd: int, mode: int) -> None:
        """Windows has no POSIX modes: the user's profile directory keeps the file private."""

    def utf8_stdio() -> None:
        """stdout and stderr in UTF-8: a pipe would otherwise get the ANSI code page."""
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is not None:
                reconfigure(encoding="utf-8")

else:
    import fcntl
    import signal

    NEW_GROUP = 0

    def lock(fd: int, *, blocking: bool) -> None:
        """Lock `fd` exclusively; without `blocking` a held lock raises ``OSError``."""
        fcntl.flock(fd, fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB)

    def unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)

    def alive(pid: int) -> bool:
        """The process `pid` exists (a process of another user counts as alive)."""
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def kill(pid: int, *, force: bool) -> None:
        """SIGKILL with `force`, else SIGTERM."""
        os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)

    def kill_group(pid: int, *, force: bool) -> None:
        """SIGKILL with `force`, else SIGTERM, to the process group `pid`."""
        os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)

    def fchmod(fd: int, mode: int) -> None:
        os.fchmod(fd, mode)

    def utf8_stdio() -> None:
        """POSIX: the locale decides, as before."""
