"""The fingerprint of the package on disk and the watch that notices a change."""

from __future__ import annotations

from pathlib import Path

from aifactory.codeprint import CodeWatch, fingerprint


def test_fingerprint_follows_the_files(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    first = fingerprint(tmp_path)
    assert fingerprint(tmp_path) == first
    (tmp_path / "mod.py").write_text("x = 22\n", encoding="utf-8", newline="\n")
    assert fingerprint(tmp_path) != first


def test_fingerprint_skips_pycache(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    first = fingerprint(tmp_path)
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "mod.cpython-311.pyc").write_bytes(b"\0")
    assert fingerprint(tmp_path) == first


def test_watch_turns_stale_when_a_file_appears(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    watch = CodeWatch(tmp_path, ttl=0.0)
    assert not watch.stale()
    (tmp_path / "defaults.yaml").write_text("a: 1\n", encoding="utf-8", newline="\n")
    assert watch.stale()
    assert watch.current() != watch.started


def test_watch_rereads_at_most_once_per_ttl(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    watch = CodeWatch(tmp_path, ttl=3600.0)
    (tmp_path / "mod.py").write_text("x = 22\n", encoding="utf-8", newline="\n")
    assert not watch.stale()
