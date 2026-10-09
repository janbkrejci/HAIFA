"""Fingerprint of the aifactory package on disk, so a long-running process notices an update.

HAIFA builds itself: merging a task replaces files of this package under a running dashboard.
``CodeWatch`` takes the fingerprint when it is created and compares it with the files on disk.
The fingerprint covers every file of the package (relative path, size and modification time,
no contents) except ``__pycache__``.
"""

from __future__ import annotations

import hashlib
import stat
import time
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def fingerprint(root: Path = PACKAGE_DIR) -> str:
    """A short hash of every file under ``root``: relative path, size and mtime."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        try:
            info = path.stat()
        except OSError:
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        rel = path.relative_to(root).as_posix()
        digest.update(f"{rel}\0{info.st_size}\0{info.st_mtime_ns}\n".encode())
    return digest.hexdigest()[:16]


class CodeWatch:
    """The fingerprint of ``root`` when the watch started, compared with the disk on demand.

    ``current()`` reads the files at most once per ``ttl`` seconds.
    """

    def __init__(self, root: Path = PACKAGE_DIR, *, ttl: float = 2.0) -> None:
        self.root = root
        self.ttl = ttl
        self.started = fingerprint(root)
        self._current = self.started
        self._checked = time.monotonic()

    def current(self) -> str:
        now = time.monotonic()
        if now - self._checked >= self.ttl:
            self._current = fingerprint(self.root)
            self._checked = now
        return self._current

    def stale(self) -> bool:
        """True when the package on disk is not the one this process started with."""
        return self.current() != self.started
