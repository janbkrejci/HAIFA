"""Git repos built once per test session (per xdist worker) and copied into each test.

Helpers used to rebuild the same small repo with a handful of git commands in every
test. `build(path, key, make)` runs `make` once into a template directory and then
copies it to `path`. Without the session fixture (`conftest._fast_test_env` calls
`enable`) every helper falls back to building in place, exactly as before.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

_root: Path | None = None


def enable(directory: Path) -> None:
    global _root
    directory.mkdir(parents=True, exist_ok=True)
    _root = directory


def build(path: Path, key: str, make: Callable[[Path], object]) -> None:
    """Make `path` the repo that `make(path)` would build, reusing a per-session template."""
    if _root is None:
        make(path)
        return
    template = _root / key
    if not template.is_dir():
        staging = _root / f".{key}.building"
        if staging.exists():
            shutil.rmtree(staging)
        make(staging)
        staging.rename(template)
    shutil.copytree(template, path, symlinks=True, dirs_exist_ok=True)
