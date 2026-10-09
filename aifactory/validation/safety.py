"""Deletion guard: the validation deletes only inside directories it created itself."""

from __future__ import annotations

import os
import shutil
import stat
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


class UnsafeDelete(RuntimeError):
    """A delete outside a directory this run owns was refused."""


class Owned:
    """Registry of the directories this run created and may delete in."""

    def __init__(self) -> None:
        self._roots: list[Path] = []

    def add(self, root: Path) -> Path:
        resolved = root.resolve()
        if resolved not in self._roots:
            self._roots.append(resolved)
        return resolved

    def owns(self, root: Path) -> bool:
        return root.resolve() in self._roots

    @property
    def roots(self) -> list[Path]:
        return list(self._roots)


def _clear_readonly(func: Callable[[str], Any], path: str, _exc: object) -> None:
    """Windows refuses to delete a read-only file (git objects are); clear the bit, retry."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def check_inside(path: Path, root: Path, owned: Owned) -> Path:
    """`path` resolved, if it lies inside the owned `root`; else raise ``UnsafeDelete``."""
    target = path.resolve()
    base = root.resolve()
    if not owned.owns(base):
        raise UnsafeDelete(f"refusing to delete in {base}: not created by this run")
    if target == base.parent or target in base.parents:
        raise UnsafeDelete(f"refusing to delete {target}: it contains {base}")
    if target != base and base not in target.parents:
        raise UnsafeDelete(f"refusing to delete {target}: outside {base}")
    return target


def safe_rmtree(path: Path, root: Path, owned: Owned) -> bool:
    """Delete `path` (a file or tree) inside the owned `root`; return whether it existed."""
    target = check_inside(path, root, owned)
    if not target.exists() and not target.is_symlink():
        return False
    if target.is_dir() and not target.is_symlink():
        if sys.platform == "win32":
            shutil.rmtree(target, onerror=_clear_readonly)
        else:
            shutil.rmtree(target)
    else:
        target.unlink()
    return True
