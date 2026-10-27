"""Best-effort cleanup of Claude's cwd-specific project directories."""

from __future__ import annotations

import os
import re
import shutil
import stat
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def _encode(path: str | Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def _projects() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"


def claude_project_dirs(cwd: str | Path) -> set[Path]:
    """Include both the supplied spelling (including Windows 8.3) and resolved cwd."""
    return {_projects() / _encode(cwd), _projects() / _encode(Path(cwd).resolve())}


def _remove(path: Path) -> None:
    def writable(func: Any, name: str, *_: Any) -> None:
        os.chmod(name, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
        func(name)

    try:
        # Do not follow links out of Claude's projects directory.
        if path.is_symlink():
            path.unlink()
        else:
            shutil.rmtree(path, onerror=writable)
    except Exception:
        pass


def remove_agent_dirs(cwd: str | Path) -> None:
    """Never let transcript cleanup break the operation that owns the cwd."""
    try:
        for path in claude_project_dirs(cwd):
            _remove(path)
    except Exception:
        pass


def sweep_orphans(prefixes: Iterable[str | Path], alive: Iterable[str | Path]) -> None:
    """Remove only scoped project names, preserving live and existing cwd spellings.

    Encoding is lossy, so never try to decode a project name into a filesystem path.
    Instead walk matching existing paths, pruning branches without candidate names.
    """
    try:
        prefixes = list(prefixes)
        live = {p.name for cwd in alive for p in claude_project_dirs(cwd)}
        protected: set[str] = set()
        candidates = {
            p
            for p in _projects().iterdir()
            if p.is_dir()
            and any(
                p.name.startswith(encoded.name + ("" if str(prefix).endswith("-") else "-"))
                for prefix in prefixes
                for encoded in claude_project_dirs(prefix)
            )
        }
        names = {p.name for p in candidates}
        for prefix in prefixes:

            def failed(error: OSError) -> None:
                raise error

            for root, dirs, _ in os.walk(Path(prefix).parent, onerror=failed):
                path = Path(root)
                encoded = {p.name for p in claude_project_dirs(path)}
                protected.update(encoded)
                # os.walk does not visit directory symlinks; keep their cwd and
                # descendants without following a link out of the owned tree.
                for directory in dirs:
                    child = path / directory
                    if child.is_symlink():
                        for variant in claude_project_dirs(child):
                            protected.update(
                                name
                                for name in names
                                if name == variant.name or name.startswith(variant.name + "-")
                            )
                dirs[:] = [
                    d
                    for d in dirs
                    if any(
                        name == variant.name or name.startswith(variant.name + "-")
                        for variant in claude_project_dirs(path / d)
                        for name in names
                    )
                ]
        for path in candidates:
            if path.name not in protected and not any(
                path.name == name or path.name.startswith(name + "-") for name in live
            ):
                _remove(path)
    except Exception:
        # An unreadable source directory is not evidence that its cwd disappeared.
        pass
