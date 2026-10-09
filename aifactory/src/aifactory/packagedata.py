"""Packaged data files of aifactory, read once per process.

HAIFA builds itself: merging a task replaces files of this package under running processes.
Code already in memory must keep the data it came with; otherwise a run that started before
the merge meets a new ``roles.yaml`` with a code step it does not know. The default roles and
workflows (``defaults/`` and ``engine/defaults/``) are read when this module is first imported
and served from memory for the life of the process. Any other path is read from disk.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIRS = (PACKAGE_DIR / "defaults", PACKAGE_DIR / "engine" / "defaults")
DATA_SUFFIXES = frozenset({".yaml", ".yml"})


class PackageData:
    """The text files under ``dirs`` as they were when the object was created."""

    def __init__(self, dirs: Iterable[Path]) -> None:
        self.dirs = tuple(d.resolve() for d in dirs)
        self._files: dict[Path, str] = {}
        for base in self.dirs:
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*")):
                if path.is_file() and path.suffix in DATA_SUFFIXES:
                    self._files[path.resolve()] = path.read_text(encoding="utf-8")

    def covers(self, path: Path) -> bool:
        """True when ``path`` is a data file kind this snapshot is responsible for."""
        resolved = path.resolve()
        return resolved.suffix in DATA_SUFFIXES and any(
            resolved.is_relative_to(base) for base in self.dirs
        )

    def read_text(self, path: Path) -> str:
        """The text of ``path``; a covered data file comes from the snapshot.

        A covered file that did not exist when the snapshot was taken raises
        ``FileNotFoundError`` like a missing file, even when it exists on disk now.
        """
        if not self.covers(path):
            return path.read_text(encoding="utf-8")
        try:
            return self._files[path.resolve()]
        except KeyError:
            missing = f"{path}: not part of the package when the process started"
            raise FileNotFoundError(missing) from None

    def names(self, directory: Path, suffix: str = ".yaml") -> list[str]:
        """Stems of the snapshot files directly in ``directory`` (sorted)."""
        resolved = directory.resolve()
        return sorted(p.stem for p in self._files if p.parent == resolved and p.suffix == suffix)


DATA = PackageData(DATA_DIRS)


def read_text(path: Path) -> str:
    """``DATA.read_text``: packaged roles and workflows as of the start of the process."""
    return DATA.read_text(path)
