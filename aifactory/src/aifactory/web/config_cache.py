"""Short-lived dashboard reads, invalidated by configuration edits in any process.

Only stat shared configuration and Git metadata; never scan the repository or runtime
worktrees, run Git, refresh its index, or write an invalidation marker.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from aifactory.config.status import SHARED_DIRS, SHARED_FILES

CONFIG_TTL = 15.0
T = TypeVar("T")


def _fingerprint(root: Path) -> tuple[tuple[str, int, int, int], ...]:
    paths = [root / p for p in (*SHARED_FILES, ".factory/local.yaml", ".gitignore", ".git")]
    trees = [root / p for p in SHARED_DIRS]
    git_dir = root / ".git"
    try:
        if git_dir.is_file():
            pointer = git_dir.read_text(encoding="utf-8").strip()
            if pointer.startswith("gitdir: "):
                git_dir = root / pointer[8:]
        common = git_dir
        common_file = git_dir / "commondir"
        if common_file.is_file():
            common = git_dir / common_file.read_text(encoding="utf-8").strip()
        paths.extend([git_dir / "HEAD", git_dir / "index", common / "packed-refs"])
        trees.append(common / "refs")
    except OSError:
        pass  # A missing/broken repo is still cached briefly and checked again on expiry.
    for tree in trees:
        paths.append(tree)
        for directory, dirs, files in os.walk(tree, followlinks=False):
            paths.extend(Path(directory) / name for name in (*dirs, *files))
    result = []
    for path in sorted(set(paths)):
        try:
            stat = path.lstat()
            result.append((str(path), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size))
        except OSError:
            result.append((str(path), -1, -1, -1))
    return tuple(result)


@dataclass
class _Entry:
    lock: threading.Lock = field(default_factory=threading.Lock)
    checked: float = 0.0
    signature: object = None
    value: Any = None


class ConfigCache:
    """Per-app cache; serialize reads so concurrent navigation also computes only once."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._items: dict[object, _Entry] = {}

    def get(self, key: object, root: Path, compute: Callable[[], T]) -> T:
        with self._lock:
            entry = self._items.setdefault(key, _Entry())
        with entry.lock:
            signature = _fingerprint(root)
            if self._clock() - entry.checked < CONFIG_TTL and entry.signature == signature:
                value: T = entry.value
                return value
            value = compute()
            entry.checked, entry.signature, entry.value = self._clock(), signature, value
            return value

    def prune(self, keep: set[object]) -> None:
        with self._lock:
            for key in list(self._items):
                if key not in keep:
                    del self._items[key]
