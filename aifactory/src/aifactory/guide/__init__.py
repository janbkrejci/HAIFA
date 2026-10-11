"""The user and administrator guide: Czech markdown chapters shipped in the package.

Each chapter is ``<NN>-<id>.md`` in this directory; ``NN`` orders the chapters and the
first ``# `` heading is its title. The dashboard serves them on ``/api/guide`` and renders
them on ``#/guide``. The installation chapter is also the bundle's standalone
``INSTALL.md`` (``bundle/build.py``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

GUIDE_DIR = Path(__file__).resolve().parent
INSTALL_CHAPTER = "instalace"
_NAME = re.compile(r"^(\d+)-([a-z0-9-]+)\.md$")


@dataclass(frozen=True)
class Chapter:
    id: str
    title: str
    markdown: str

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "title": self.title, "markdown": self.markdown}


def _title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def chapters(directory: Path = GUIDE_DIR) -> list[Chapter]:
    """The chapters in order of their number prefix."""
    found: list[tuple[int, Chapter]] = []
    for path in directory.glob("*.md"):
        match = _NAME.match(path.name)
        if match is None:
            continue
        text = path.read_text(encoding="utf-8")
        chapter_id = match.group(2)
        found.append((int(match.group(1)), Chapter(chapter_id, _title(text, chapter_id), text)))
    return [chapter for _, chapter in sorted(found, key=lambda item: (item[0], item[1].id))]


def chapter(chapter_id: str, directory: Path = GUIDE_DIR) -> Chapter:
    """The chapter ``chapter_id``; ``KeyError`` when there is none."""
    for item in chapters(directory):
        if item.id == chapter_id:
            return item
    raise KeyError(chapter_id)
