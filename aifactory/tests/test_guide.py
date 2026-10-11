"""The user and administrator guide: chapters, links between them and the bundle's INSTALL.md."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest
from bundle.build import install_guide

from aifactory import guide

ROOT = Path(__file__).resolve().parents[1]
SRC_GUIDE = ROOT / "src" / "aifactory" / "guide"


def _slug(title: str) -> str:
    """The same slug as ``slug`` in ``web/src/lib/guide.ts``."""
    folded = unicodedata.normalize("NFD", title.replace("`", ""))
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "-", folded).strip("-")


def _sections(markdown: str) -> set[str]:
    fence = False
    found: set[str] = set()
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        elif not fence and line.startswith("## "):
            found.add(_slug(line[3:].strip()))
    return found


def test_chapters_are_ordered_unique_and_titled() -> None:
    chapters = guide.chapters()
    assert len(chapters) >= 8
    ids = [c.id for c in chapters]
    assert len(set(ids)) == len(ids)
    assert ids[0] == "uvod"
    assert guide.INSTALL_CHAPTER in ids
    for chapter in chapters:
        assert chapter.markdown.startswith(f"# {chapter.title}\n")
    names = sorted(p.name for p in SRC_GUIDE.glob("*.md"))
    assert len(names) == len(chapters), "every .md of the guide must be named NN-<id>.md"


def test_chapter_lookup() -> None:
    assert guide.chapter(guide.INSTALL_CHAPTER).title
    with pytest.raises(KeyError):
        guide.chapter("neexistuje")


def test_chapters_from_a_directory(tmp_path: Path) -> None:
    (tmp_path / "10-b.md").write_text("# Béčko\n", encoding="utf-8")
    (tmp_path / "02-a.md").write_text("bez nadpisu\n", encoding="utf-8")
    (tmp_path / "poznamky.md").write_text("# Ignorováno\n", encoding="utf-8")
    chapters = guide.chapters(tmp_path)
    assert [(c.id, c.title) for c in chapters] == [("a", "a"), ("b", "Béčko")]


def test_guide_links_point_to_existing_chapters_and_sections() -> None:
    sections = {c.id: _sections(c.markdown) for c in guide.chapters()}
    broken: list[str] = []
    for chapter in guide.chapters():
        for target in re.findall(r"\]\((#/[^)\s]+)\)", chapter.markdown):
            parts = target.removeprefix("#/").split("/")
            if parts[0] != "guide":
                continue
            if len(parts) < 2 or parts[1] not in sections:
                broken.append(f"{chapter.id}: {target}")
            elif len(parts) == 3 and parts[2] not in sections[parts[1]]:
                broken.append(f"{chapter.id}: {target}")
    assert broken == []


def test_relative_markdown_links_are_not_used() -> None:
    """The dashboard renders only http(s) and #/ links; anything else would show as text."""
    for chapter in guide.chapters():
        links = re.findall(r"\]\(([^)\s]+)\)", chapter.markdown)
        assert [x for x in links if not x.startswith(("http://", "https://", "#/"))] == []


def test_bundle_install_guide_is_the_installation_chapter() -> None:
    text = install_guide("9.9.9")
    source = guide.chapter(guide.INSTALL_CHAPTER).markdown
    assert "](#/guide/" in source
    assert "](#/" not in text
    assert "[Řešení problémů]" not in text and "kapitole Řešení problémů" in text
    assert text.count("\n") == source.count("\n")
    assert "haifa-9.9.9.zip" in text
    assert "<verze>" not in text
    for needle in ("./install.sh", "factory check", "factory upgrade", "factory obs"):
        assert needle in text
