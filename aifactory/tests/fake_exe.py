"""Make a test's fake program (a script with a shebang) runnable on every platform.

POSIX: ``chmod 0755``, as the tests did before. Windows runs no shebang scripts: the script
moves to ``<path>.script`` and ``<path>.exe`` takes its place, the distlib launcher from the
pip wheel that ``ensurepip`` ships followed by a zip whose ``__main__.py`` runs the script
(a Python script in this interpreter, any other with Git's ``sh``). ``CreateProcess`` adds
``.exe`` to a command without an extension that does not exist, so ``gh`` on PATH and the
path itself both reach the launcher.
"""

from __future__ import annotations

import contextlib
import functools
import io
import os
import shutil
import sys
import zipfile
from pathlib import Path

_RUNNER = """\
import os, runpy, subprocess, sys
script = {script!r}
if {python!r}:
    sys.argv[0] = script
    runpy.run_path(script, run_name="__main__")
else:
    sys.exit(subprocess.call([{sh!r}, script, *sys.argv[1:]]))
"""


@functools.cache
def _launcher() -> bytes:
    bundled = Path(sys.base_prefix) / "Lib" / "ensurepip" / "_bundled"
    wheel = next(bundled.glob("pip-*.whl"))
    with zipfile.ZipFile(wheel) as whl:
        return whl.read("pip/_vendor/distlib/t64.exe")


@functools.cache
def _sh() -> str:
    found = shutil.which("sh")
    if found and "system32" not in found.lower():
        return found
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("no git on PATH: Git for Windows brings the sh the fakes need")
    root = Path(git).resolve().parent.parent  # <Git>/cmd/git.exe or <Git>/bin/git.exe
    return str(root / "bin" / "sh.exe")


def _windows_exe(path: Path) -> Path:
    script = path.with_name(path.name + ".script")
    os.replace(path, script)
    first = script.read_text(encoding="utf-8").splitlines()[0] if script.stat().st_size else ""
    python = "python" in first.lower()
    runner = _RUNNER.format(script=str(script), python=python, sh="" if python else _sh())
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("__main__.py", runner)
    data = _launcher() + f'#!"{sys.executable}"\n'.encode() + archive.getvalue()
    exe = path.with_name(path.name + ".exe")
    if exe.is_file() and exe.read_bytes() == data:
        return exe
    tmp = exe.with_name(f".{exe.name}.{os.getpid()}")
    tmp.write_bytes(data)
    try:
        os.replace(tmp, exe)
    except PermissionError:  # another xdist worker runs the same launcher right now
        with contextlib.suppress(OSError):
            tmp.unlink()
    return exe


def make_executable(path: Path) -> Path:
    """Make the script `path` runnable; returns the file to run (Windows: ``<path>.exe``)."""
    path.chmod(0o755)
    if sys.platform == "win32":
        return _windows_exe(path)
    return path
