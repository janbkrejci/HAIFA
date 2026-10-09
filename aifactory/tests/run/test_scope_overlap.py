"""Overlap of write paths for parallel auto-continue (``scope.py``): pure functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from aifactory.run.scope import is_wide, literal_prefix, overlaps, paths_overlap


@pytest.mark.parametrize(
    ("pattern", "prefix"),
    [
        ("src/app/", "src/app"),
        ("./src/app", "src/app"),
        ("src/**/x.py", "src"),
        ("src/*/x.py", "src"),
        ("src/a?b/", "src"),
        ("**", ""),
        ("*.py", ""),
        (".", ""),
        ("justfile", "justfile"),
    ],
)
def test_literal_prefix(pattern: str, prefix: str) -> None:
    assert literal_prefix(pattern) == prefix


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("src/app/", "src/app/x.py", True),
        ("src/app/", "src/app/sub/", True),
        ("src/app/sub/", "src/app/", True),
        ("src/app", "src/application", False),
        ("src/app/", "src/application/x.py", False),
        ("src/app/", "src/app/", True),
        ("**", "anything/at/all.py", True),
        ("README.md", "**", True),
        ("src/*/x.py", "src/other/", True),
        ("src/*/x.py", "lib/other/", False),
        ("justfile", "justfile", True),
        ("justfile", "justfile.bak", False),
    ],
)
def test_paths_overlap(a: str, b: str, expected: bool) -> None:
    assert paths_overlap(a, b) is expected
    assert paths_overlap(b, a) is expected


def test_overlaps_lists_the_hit_paths_sorted() -> None:
    writes = ["src/app/", "justfile"]
    paths = ["src/other/x.py", "src/app/z.py", "justfile", "src/app/a.py"]
    assert overlaps(writes, paths) == ["justfile", "src/app/a.py", "src/app/z.py"]
    assert overlaps(["docs/"], paths) == []


def test_is_wide(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    assert is_wide(["aifactory/"]) == ["aifactory/"]
    assert is_wide(["src/"]) == ["src/"]
    assert is_wide(["src/*"]) == ["src/*"]
    assert is_wide(["**"]) == ["**"]
    assert is_wide(["."]) == ["."]
    assert is_wide(["justfile"]) == []
    assert is_wide(["src/app/"]) == []
    assert is_wide(["pkg"]) == []  # unknown without root
    assert is_wide(["pkg"], tmp_path) == ["pkg"]
    assert is_wide(["justfile"], tmp_path) == []
    assert is_wide(["aifactory/", "justfile"], tmp_path) == ["aifactory/"]
