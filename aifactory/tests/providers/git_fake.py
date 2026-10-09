"""A fake `git` on PATH: ``git push`` fails as scripted, everything else is the real git.

The n-th ``git push`` (counted in ``$AIFACTORY_FAKE_GIT_STATE/count``) fails with exit 1
and the content of ``fail_<n>`` on stderr when that file exists; otherwise, and for every
other command, the real git (``$AIFACTORY_REAL_GIT``) runs. No network is involved: the
remote of the tests is a bare repository on disk.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from fake_exe import make_executable

_SCRIPT = """\
#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path

state = os.environ.get("AIFACTORY_FAKE_GIT_STATE")
if sys.argv[1:2] == ["push"] and state:
    count = Path(state) / "count"
    n = int(count.read_text()) + 1 if count.exists() else 1
    count.write_text(str(n))
    failure = Path(state) / f"fail_{n}"
    if failure.exists():
        sys.stderr.write(failure.read_text())
        sys.exit(1)
# Pass argv directly: Git Bash/MSYS rewrites some revision expressions on Windows.
sys.exit(subprocess.call([os.environ["AIFACTORY_REAL_GIT"], *sys.argv[1:]]))
"""

HTTP2 = (
    "error: RPC failed; curl 16 Error in the HTTP2 framing layer\n"
    "send-pack: unexpected disconnect while reading sideband packet\n"
    "fatal: the remote end hung up unexpectedly\n"
)
REJECTED = (
    "To /tmp/origin.git\n"
    " ! [rejected]        factory/x -> factory/x (non-fast-forward)\n"
    "error: failed to push some refs to '/tmp/origin.git'\n"
)


def _user() -> str:
    return str(os.getuid()) if hasattr(os, "getuid") else os.environ.get("USERNAME", "user")


def _bin_dir() -> Path:
    """A stable per-user directory keyed by the script (macOS checks a new file's first exec)."""
    key = hashlib.sha256(_SCRIPT.encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"aifactory-fake-git-{_user()}-{key}"


def _write_script() -> Path:
    bin_dir = _bin_dir()
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / "git"
    script = bin_dir / "git.script" if sys.platform == "win32" else path
    if not script.is_file() or script.read_text(encoding="utf-8") != _SCRIPT:
        tmp = bin_dir / f".git.{os.getpid()}"
        tmp.write_text(_SCRIPT, encoding="utf-8", newline="\n")
        tmp.chmod(0o755)
        os.replace(tmp, path)  # atomic: xdist workers may race on the shared path
        make_executable(path)
    return bin_dir


@dataclass
class FakeGit:
    state_dir: Path

    def fail_push(self, n: int, stderr: str) -> None:
        """The `n`-th push from now on fails with `stderr`."""
        (self.state_dir / f"fail_{self.pushes() + n}").write_text(
            stderr, encoding="utf-8", newline="\n"
        )

    def pushes(self) -> int:
        count = self.state_dir / "count"
        return int(count.read_text(encoding="utf-8").strip()) if count.is_file() else 0


def install_fake_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeGit:
    real = shutil.which("git")
    assert real is not None, "the tests need git on PATH"
    bin_dir = _write_script()
    state = tmp_path / "git_state"
    state.mkdir(exist_ok=True)
    monkeypatch.setenv("AIFACTORY_REAL_GIT", real)
    monkeypatch.setenv("AIFACTORY_FAKE_GIT_STATE", str(state))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return FakeGit(state)
