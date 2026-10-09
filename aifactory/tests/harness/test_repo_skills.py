"""The skills mirror: .agents/skills as an exact copy of .claude/skills."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from aifactory.harness.repo_skills import (
    MIRROR,
    SOURCE,
    commit_snapshot,
    diff_snapshots,
    sync,
    worktree_snapshot,
)


def _write(path: Path, text: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _files(base: Path) -> dict[str, bytes]:
    files = (p for p in sorted(base.rglob("*")) if p.is_file())
    return {p.relative_to(base).as_posix(): p.read_bytes() for p in files}


def _layout(root: Path) -> None:
    _write(root / SOURCE / "a" / "SKILL.md", "skill a\n")
    _write(root / SOURCE / "b" / "SKILL.md", "skill b\n")
    _write(root / SOURCE / "b" / "run.sh", "#!/bin/sh\necho b\n", executable=True)
    _write(root / MIRROR / "b" / "SKILL.md", "stale b\n")
    _write(root / MIRROR / "old" / "SKILL.md", "old\n")


def test_sync_makes_an_exact_copy(tmp_path: Path) -> None:
    _layout(tmp_path)

    result = sync(tmp_path)

    assert result.added == ("a",)
    assert result.updated == ("b",)
    assert result.removed == ("old",)
    assert _files(tmp_path / SOURCE) == _files(tmp_path / MIRROR)
    assert os.access(tmp_path / MIRROR / "b" / "run.sh", os.X_OK)
    again = sync(tmp_path)
    assert (again.added, again.updated, again.removed) == ((), (), ())


@pytest.mark.skipif(sys.platform == "win32", reason="Windows files have no exec bit")
def test_exec_bit_alone_is_a_change(tmp_path: Path) -> None:
    _write(tmp_path / SOURCE / "a" / "run.sh", "x\n", executable=True)
    _write(tmp_path / MIRROR / "a" / "run.sh", "x\n")
    assert sync(tmp_path).updated == ("a",)
    assert os.access(tmp_path / MIRROR / "a" / "run.sh", os.X_OK)


def test_sync_without_source_removes_the_mirror_only(tmp_path: Path) -> None:
    _write(tmp_path / MIRROR / "old" / "SKILL.md", "old\n")
    _write(tmp_path / ".agents" / "other.txt", "keep\n")

    result = sync(tmp_path)

    assert result.removed == ("old",)
    assert not (tmp_path / MIRROR).exists()
    assert (tmp_path / ".agents" / "other.txt").read_text() == "keep\n"


def test_sync_without_source_drops_empty_agents_dir(tmp_path: Path) -> None:
    _write(tmp_path / MIRROR / "old" / "SKILL.md", "old\n")
    sync(tmp_path)
    assert not (tmp_path / ".agents").exists()


def test_sync_with_nothing_is_a_no_op(tmp_path: Path) -> None:
    result = sync(tmp_path)
    assert (result.added, result.updated, result.removed) == ((), (), ())
    assert not (tmp_path / ".agents").exists()


def test_diff_snapshots() -> None:
    source = {"a/SKILL.md": "1", "b/SKILL.md": "2", "b/x.py": "3", "top.md": "4"}
    mirror = {"b/SKILL.md": "2", "b/x.py": "9", "c/SKILL.md": "5", "top.md": "4"}
    diff = diff_snapshots(source, mirror)
    assert diff.missing == ("a",)
    assert diff.changed == ("b",)
    assert diff.extra == ("c",)
    assert not diff.clean
    assert diff_snapshots(source, source).clean


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def test_commit_snapshot_matches_the_worktree_answer(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _layout(tmp_path)
    _git(tmp_path, "add", "-A")
    if sys.platform == "win32":  # no exec bit in a Windows worktree: set it in the index
        _git(tmp_path, "update-index", "--chmod=+x", f"{SOURCE}/b/run.sh")
    _git(tmp_path, "commit", "-q", "-m", "skills")
    commit = _git(tmp_path, "rev-parse", "HEAD").strip()

    source = commit_snapshot(tmp_path, commit, SOURCE)
    mirror = commit_snapshot(tmp_path, commit, MIRROR)

    assert set(source) == {"a/SKILL.md", "b/SKILL.md", "b/run.sh"}
    assert source["b/run.sh"].startswith("100755 ")
    from_git = diff_snapshots(source, mirror)
    from_tree = diff_snapshots(
        worktree_snapshot(tmp_path, SOURCE), worktree_snapshot(tmp_path, MIRROR)
    )
    assert from_git == from_tree
    assert commit_snapshot(tmp_path, commit, "nope/skills") == {}
