"""GIRO's machine home, with explicit HAIFA aliases and guarded legacy discovery.

Defaults use XDG_CONFIG_HOME/giro or ~/.config/giro (Path.home on Windows).
Legacy-only defaults require confirmed migration; ambiguous directories fail closed.
Environment files cannot redirect the already selected home.
"""

from __future__ import annotations

import os
import stat
import sys
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import BinaryIO, TextIO

from dotenv import dotenv_values

from aifactory import oscompat

HOME_ENV = "HAIFA_HOME"
XDG_ENV = "XDG_CONFIG_HOME"
ENV_FILE = "env"


def _env(environ: Mapping[str, str], name: str) -> str | None:
    value = environ.get(name)
    return value if value else None


def haifa_home(environ: Mapping[str, str] | None = None) -> Path:
    """Explicit GIRO_HOME/HAIFA_HOME, otherwise the guarded GIRO default."""
    env = os.environ if environ is None else environ
    from aifactory.environment import value
    from aifactory.upgrade import UpgradeError

    explicit = value("HOME", env)
    if explicit is not None:
        return Path(explicit).expanduser()
    xdg = _env(env, XDG_ENV)
    home = _env(env, "HOME")
    base = Path(home) if home is not None else Path.home()
    parent = Path(xdg).expanduser() if xdg is not None else base / ".config"
    target, legacy = parent / "giro", parent / "haifa"
    if legacy.exists() and target.resolve() != legacy.resolve():
        if target.exists():
            from aifactory.migration_guard import MARKER, check_home

            if (target / MARKER).exists():
                check_home(target, expected_source=legacy)
                return target
            raise UpgradeError(
                "migration_collision",
                f"Both {legacy} and {target} exist without a completed migration. "
                "Stop writers, back up both and inspect them; select GIRO_HOME explicitly.",
            )
        raise UpgradeError(
            "migration_required",
            f"Legacy data found at {legacy}. Stop HAIFA and use its transition button, "
            "or run giro migrate --confirm --haifa-bundle PATH to the verified last HAIFA ZIP. "
            "Nothing has been written.",
        )
    return target


def logs_dir(environ: Mapping[str, str] | None = None) -> Path:
    """``<home>/logs``; created (mode 0700) when missing."""
    path = haifa_home(environ) / "logs"
    if not path.is_dir():
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    return path


def create_private(path: Path) -> BinaryIO:
    """A new file at `path` with mode 0600, open for binary writing; an existing file fails."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        oscompat.fchmod(fd, 0o600)
    except OSError:
        os.close(fd)
        raise
    return os.fdopen(fd, "wb")


def env_file(environ: Mapping[str, str] | None = None) -> Path:
    """``<home>/env``: KEY=VALUE lines loaded into the environment at ``factory`` start."""
    return haifa_home(environ) / ENV_FILE


def load_env_file(
    environ: MutableMapping[str, str] | None = None, stderr: TextIO | None = None
) -> list[str]:
    """Load ``<home>/env`` into `environ` (default ``os.environ``) if the file exists.

    Variables `environ` already has are kept. A file whose mode is not 0600 is still
    loaded, with an ``env_file_mode`` warning on `stderr` (not on Windows: no modes there).
    Returns the names it set.
    """
    env: MutableMapping[str, str] = os.environ if environ is None else environ
    path = env_file(env)
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return []
    if not path.is_file():
        return []
    if mode != 0o600 and sys.platform != "win32":  # Windows has no POSIX modes to check
        out = sys.stderr if stderr is None else stderr
        print(
            f"factory: warning: env_file_mode: {path} has mode {mode:04o}, expected 0600",
            file=out,
        )
    from aifactory.environment import resolve

    before = dict(env)
    settings = dotenv_values(path)
    resolved = resolve(before, settings, stderr=stderr)
    env.update(resolved)
    return [key for key in settings if key not in before and key in resolved]
