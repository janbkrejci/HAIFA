"""The few OS calls that differ between POSIX and Windows.

On POSIX every function is the call the code used before (``fcntl.flock``,
``os.kill(pid, 0)``, ``os.kill``, ``os.killpg``, ``os.fchmod``). On Windows: ``lock`` is
``msvcrt.locking`` on byte 0 of the lock file, ``alive`` asks ``OpenProcess`` (there
``os.kill(pid, 0)`` would terminate the process), ``kill`` and ``kill_group`` are
``taskkill /T /F`` (the process with its children), ``fchmod`` does nothing and
``image_path`` (Windows only) stands in for ``ps -o command`` and ``utf8_stdio`` switches
stdout and stderr to UTF-8 (POSIX: nothing).
``ProcessTree`` stops a command with everything it started: the process group on POSIX,
a job object on Windows.
``NEW_GROUP`` goes to ``Popen(creationflags=...)`` next to ``start_new_session=True``,
which Windows ignores: the child gets its own process group and a hidden console of its
own, so neither Ctrl+C nor closing the parent's console window stops it.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from contextlib import suppress
from typing import Any

# Seconds ProcessTree.kill waits for the stopped processes to be gone.
KILL_WAIT = 10.0

if sys.platform == "win32":
    import ctypes
    import msvcrt
    from ctypes import wintypes

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

    _PROCESS_TERMINATE = 0x0001
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_SUSPEND_RESUME = 0x0800
    _JOB_BASIC_ACCOUNTING = 1
    _JOB_KILLED_EXIT = 1

    class _JobAccounting(ctypes.Structure):
        _fields_ = [  # noqa: RUF012 - ctypes reads the class attribute
            ("total_user_time", ctypes.c_int64),
            ("total_kernel_time", ctypes.c_int64),
            ("period_user_time", ctypes.c_int64),
            ("period_kernel_time", ctypes.c_int64),
            ("page_faults", wintypes.DWORD),
            ("total_processes", wintypes.DWORD),
            ("active_processes", wintypes.DWORD),
            ("terminated_processes", wintypes.DWORD),
        ]

    # Own library instances: the argtypes below must not change ctypes.windll for others.
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ntdll = ctypes.WinDLL("ntdll")
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.TerminateJobObject.restype = wintypes.BOOL
    _kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    _kernel32.QueryInformationJobObject.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    _ntdll.NtResumeProcess.restype = ctypes.c_long

    class ProcessTree:
        """A command with every process it starts, in one Windows job object.

        ``taskkill /T`` follows parent links one process at a time. A child started while
        it runs (an xdist worker replacing a killed one) escapes, a child whose parent
        already exited is not found, and once taskkill has ended the tree's hidden console
        host (conhost.exe, a child of the root), a python.exe started next fails with
        0xc0000142 behind a modal "unable to start correctly" dialog. A job holds every
        descendant from its first instruction (the command starts suspended and runs only
        once it is in the job), and ``TerminateJobObject`` stops all members at once.
        Without a job (creating or joining it failed) ``kill`` falls back to taskkill.
        """

        creationflags = 0x00000004  # CREATE_SUSPENDED

        def __init__(self) -> None:
            self._job: int | None = None

        def __enter__(self) -> ProcessTree:
            return self

        def __exit__(self, *exc: object) -> None:
            if self._job is not None:
                _kernel32.CloseHandle(self._job)
                self._job = None

        def adopt(self, process: subprocess.Popen[Any]) -> None:
            """Put `process`, started with ``creationflags``, in a new job and resume it."""
            access = _PROCESS_TERMINATE | _PROCESS_SET_QUOTA | _PROCESS_SUSPEND_RESUME
            handle = _kernel32.OpenProcess(access, False, process.pid)
            if not handle:
                error = ctypes.get_last_error()
                process.kill()  # suspended forever otherwise
                raise ctypes.WinError(error)
            try:
                job = _kernel32.CreateJobObjectW(None, None)
                if job and _kernel32.AssignProcessToJobObject(job, handle):
                    self._job = job
                elif job:
                    _kernel32.CloseHandle(job)
            finally:
                status = _ntdll.NtResumeProcess(handle)
                _kernel32.CloseHandle(handle)
            if status < 0:
                process.kill()
                code = status & 0xFFFFFFFF
                raise OSError(f"cannot resume process {process.pid}: NTSTATUS {code:#x}")

        def _active(self) -> int:
            info = _JobAccounting()
            if not _kernel32.QueryInformationJobObject(
                self._job, _JOB_BASIC_ACCOUNTING, ctypes.byref(info), ctypes.sizeof(info), None
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            return int(info.active_processes)

        def kill(self, process: subprocess.Popen[Any]) -> str:
            """Stop the command and every process it started; return a line for the log."""
            if self._job is None:
                with suppress(ProcessLookupError):
                    _taskkill(process.pid)
                return "stopped the process tree with taskkill /T /F (no job object)"
            found = self._active()
            deadline = time.monotonic() + KILL_WAIT
            while True:
                # Terminate again while members remain: covers a child created in between.
                _kernel32.TerminateJobObject(self._job, _JOB_KILLED_EXIT)
                left = self._active()
                if left == 0 or time.monotonic() >= deadline:
                    break
                time.sleep(0.05)
            note = f"stopped {found} process(es) of the command's job object"
            if left:
                note += f"; {left} still running after {KILL_WAIT:g}s"
            return note

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

    class ProcessTree:
        """A command with every process it starts: its own process group on POSIX."""

        creationflags = 0

        def __enter__(self) -> ProcessTree:
            return self

        def __exit__(self, *exc: object) -> None:
            pass

        def adopt(self, process: subprocess.Popen[Any]) -> None:
            """``start_new_session=True`` already made `process` a group leader."""

        def kill(self, process: subprocess.Popen[Any]) -> str:
            """SIGKILL to the command's process group; return a line for the log."""
            with suppress(ProcessLookupError):
                kill_group(process.pid, force=True)
            return "stopped the command's process group"

    def fchmod(fd: int, mode: int) -> None:
        os.fchmod(fd, mode)

    def utf8_stdio() -> None:
        """POSIX: the locale decides, as before."""
