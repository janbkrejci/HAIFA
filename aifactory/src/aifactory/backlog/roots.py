"""Backlog roots: the directories ``backlog_dir`` or ``backlog_dirs`` name.

A pattern is a relative path; a part may hold the wildcards ``*``, ``?`` and ``[...]``
(``moduly/*/backlog``), which never cross a ``/``. Nothing here writes a file.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path

from aifactory.config import ProjectSettings

_WILDCARDS = frozenset("*?[")


def is_glob(pattern: str) -> bool:
    """True when ``pattern`` has a wildcard."""
    return any(ch in _WILDCARDS for ch in pattern)


def _parts(path: str) -> list[str]:
    return [p for p in path.strip("/").split("/") if p and p != "."]


def _expand(root: Path, pattern: str) -> list[str]:
    found = [""]
    for part in _parts(pattern):
        nxt: list[str] = []
        for prefix in found:
            base = root / prefix if prefix else root
            if not is_glob(part):
                if (base / part).is_dir():
                    nxt.append(f"{prefix}/{part}" if prefix else part)
                continue
            try:
                entries = sorted(base.iterdir(), key=lambda p: p.name)
            except OSError:
                continue
            for entry in entries:
                if entry.name.startswith(".") and not part.startswith("."):
                    continue
                if entry.is_dir() and fnmatchcase(entry.name, part):
                    nxt.append(f"{prefix}/{entry.name}" if prefix else entry.name)
        found = nxt
    return found


def backlog_roots(root: Path, settings: ProjectSettings) -> list[str]:
    """Existing backlog root directories under ``root``, relative, in pattern order.

    A pattern without a wildcard is listed even when the directory is missing, so the
    loader can report it; a wildcard pattern lists only the directories it matches.
    """
    result: list[str] = []
    for pattern in settings.backlog_patterns:
        if is_glob(pattern):
            matches = _expand(root, pattern)
        else:
            matches = ["/".join(_parts(pattern))]
        for match in matches:
            if match not in result:
                result.append(match)
    return result


def matches_pattern(directory: str, settings: ProjectSettings) -> bool:
    """True when the relative ``directory`` is one of the configured backlog roots."""
    parts = _parts(directory)
    for pattern in settings.backlog_patterns:
        want = _parts(pattern)
        if len(want) == len(parts) and all(
            fnmatchcase(p, w) for p, w in zip(parts, want, strict=True)
        ):
            return True
    return False


def owning_root(rel: str, settings: ProjectSettings) -> str | None:
    """The backlog root that holds the relative path ``rel`` (strictly inside it), or None."""
    parts = _parts(rel)
    for pattern in settings.backlog_patterns:
        want = _parts(pattern)
        if len(parts) > len(want) and all(
            fnmatchcase(p, w) for p, w in zip(parts, want, strict=False)
        ):
            return "/".join(parts[: len(want)])
    return None
