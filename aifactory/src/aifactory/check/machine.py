"""What ``factory check`` asks the machine: programs on PATH, commands, environment.

Every machine query of the check goes through ``Machine`` so tests can replace it
(``FakeMachine``) and never start ``gh``, ``az`` or a harness. Git is not asked
through it; git reads go through ``aifactory.config.source.git``.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from aifactory.engine.utils import operator_env
from aifactory.harness.check import HarnessStatus, check_harness


@dataclass(frozen=True)
class Probe:
    """The result of one command."""

    returncode: int
    stdout: str
    stderr: str


class Machine(Protocol):
    def which(self, program: str) -> str | None:
        """The program's path, or None when it is not found / not executable."""
        ...

    def run(
        self, argv: Sequence[str], timeout: float = 15, cwd: Path | None = None
    ) -> Probe | None:
        """Run a read-only command (in ``cwd``); None when it cannot start or times out."""
        ...

    def env(self, name: str) -> str | None:
        """An environment variable, or None."""
        ...

    def harness(self, name: str, agents: Iterable[str]) -> HarnessStatus:
        """Locate a harness CLI and ask it for its version."""
        ...

    def home(self) -> Path:
        """The operator's home directory (only read, never written)."""
        ...

    def platform(self) -> str:
        """``darwin``, ``linux``, ``wsl`` or another ``sys.platform`` value."""
        ...

    def environment(self) -> Mapping[str, str]:
        """The whole environment, passed as ``environ`` to the library and home lookups."""
        ...

    def file_mode(self, path: Path) -> int | None:
        """The permission bits of an existing file, or None."""
        ...


class SystemMachine:
    """The real machine."""

    def which(self, program: str) -> str | None:
        return shutil.which(program)

    def run(
        self, argv: Sequence[str], timeout: float = 15, cwd: Path | None = None
    ) -> Probe | None:
        try:
            proc = subprocess.run(
                list(argv),
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=operator_env(),
                stdin=subprocess.DEVNULL,
                check=False,
                encoding="utf-8",
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return Probe(proc.returncode, proc.stdout or "", proc.stderr or "")

    def env(self, name: str) -> str | None:
        return os.environ.get(name)

    def harness(self, name: str, agents: Iterable[str]) -> HarnessStatus:
        return check_harness(name, agents)

    def home(self) -> Path:
        return Path.home()

    def platform(self) -> str:
        if sys.platform != "linux":
            return sys.platform
        if os.environ.get("WSL_DISTRO_NAME"):
            return "wsl"
        try:
            release = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8")
        except OSError:
            return "linux"
        return "wsl" if "microsoft" in release.lower() else "linux"

    def environment(self) -> Mapping[str, str]:
        return dict(os.environ)

    def file_mode(self, path: Path) -> int | None:
        try:
            if not path.is_file():
                return None
            return stat.S_IMODE(path.stat().st_mode)
        except OSError:
            return None
