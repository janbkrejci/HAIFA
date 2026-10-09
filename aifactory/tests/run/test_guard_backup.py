"""``backup``: save the uncommitted state of a checkout and restore it exactly."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from aifactory.run import backup


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True, encoding="utf-8"
    ).stdout


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    (root / "a.txt").write_text("a\n", encoding="utf-8", newline="\n")
    (root / "b.txt").write_text("b\n", encoding="utf-8", newline="\n")
    (root / "exec.sh").write_text("#!/bin/sh\n", encoding="utf-8", newline="\n")
    os.chmod(root / "exec.sh", 0o755)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    return root


@pytest.fixture(name="dest")
def dest_fixture(tmp_path: Path) -> Path:
    return tmp_path / "backup"


def test_tracked_edit_and_untracked_file_survive_checkout_and_clean(repo: Path, dest: Path) -> None:
    (repo / "a.txt").write_text("engineer wip\n", encoding="utf-8", newline="\n")
    (repo / "new").mkdir()
    (repo / "new" / "wip.txt").write_text("draft\n", encoding="utf-8", newline="\n")
    saved = backup.capture(repo, dest)

    git(repo, "checkout", "--", ".")
    git(repo, "clean", "-fdq")

    assert backup.verify(saved) == ["a.txt", "new/wip.txt"]
    outcomes = backup.restore(saved, (), backup.verify(saved))
    assert outcomes == {"a.txt": "restored from backup", "new/wip.txt": "restored from backup"}
    assert (repo / "a.txt").read_text(encoding="utf-8") == "engineer wip\n"
    assert (repo / "new" / "wip.txt").read_text(encoding="utf-8") == "draft\n"
    assert backup.verify(saved) == []


def test_staged_change_is_restored_in_tree_and_index(repo: Path, dest: Path) -> None:
    (repo / "b.txt").write_text("staged\n", encoding="utf-8", newline="\n")
    git(repo, "add", "b.txt")
    cached = git(repo, "diff", "--cached")
    saved = backup.capture(repo, dest)

    git(repo, "reset", "-q")
    git(repo, "checkout", "--", "b.txt")

    off = backup.verify(saved)
    assert "b.txt" in off
    backup.restore(saved, (), off)
    assert (repo / "b.txt").read_text(encoding="utf-8") == "staged\n"
    assert git(repo, "diff", "--cached") == cached
    assert backup.verify(saved) == []


def test_deleted_tracked_file_stays_deleted(repo: Path, dest: Path) -> None:
    (repo / "a.txt").unlink()
    saved = backup.capture(repo, dest)

    git(repo, "checkout", "--", "a.txt")

    assert backup.verify(saved) == ["a.txt"]
    backup.restore(saved, (), ["a.txt"])
    assert not (repo / "a.txt").exists()
    assert (dest / "replaced" / "a.txt").read_text(encoding="utf-8") == "a\n"


def test_agent_changes_on_clean_paths_are_undone_and_kept(repo: Path, dest: Path) -> None:
    saved = backup.capture(repo, dest)

    (repo / "b.txt").write_text("agent\n", encoding="utf-8", newline="\n")
    (repo / "x.txt").write_text("agent new\n", encoding="utf-8", newline="\n")

    off = backup.verify(saved)
    assert off == ["b.txt", "x.txt"]
    outcomes = backup.restore(saved, (), off)
    assert outcomes == {"b.txt": "rolled back", "x.txt": "deleted"}
    assert (repo / "b.txt").read_text(encoding="utf-8") == "b\n"
    assert not (repo / "x.txt").exists()
    assert (dest / "replaced" / "b.txt").read_text(encoding="utf-8") == "agent\n"
    assert (dest / "replaced" / "x.txt").read_text(encoding="utf-8") == "agent new\n"
    assert git(repo, "status", "--porcelain") == ""


def test_same_numstat_edit_of_pre_dirty_file_is_caught(repo: Path, dest: Path) -> None:
    (repo / "a.txt").write_text("one\n", encoding="utf-8", newline="\n")
    saved = backup.capture(repo, dest)

    (repo / "a.txt").write_text("two\n", encoding="utf-8", newline="\n")

    assert backup.verify(saved) == ["a.txt"]
    backup.restore(saved, (), ["a.txt"])
    assert (repo / "a.txt").read_text(encoding="utf-8") == "one\n"


def test_executable_bit_is_kept(repo: Path, dest: Path) -> None:
    saved = backup.capture(repo, dest)
    (repo / "exec.sh").write_text("#!/bin/sh\necho agent\n", encoding="utf-8", newline="\n")

    backup.restore(saved, (), backup.verify(saved))
    assert (repo / "exec.sh").read_text(encoding="utf-8") == "#!/bin/sh\n"
    assert os.access(repo / "exec.sh", os.X_OK)


def test_ignored_prefixes_are_never_captured_or_restored(repo: Path, dest: Path) -> None:
    ignored = (".factory/data/",)
    (repo / ".factory" / "data").mkdir(parents=True)
    (repo / ".factory" / "data" / "x").write_text("before\n", encoding="utf-8", newline="\n")
    saved = backup.capture(repo, dest, ignored)
    assert ".factory/data/x" not in saved.files

    (repo / ".factory" / "data" / "x").write_text("after\n", encoding="utf-8", newline="\n")
    (repo / ".factory" / "data" / "y").write_text("new\n", encoding="utf-8", newline="\n")

    assert backup.verify(saved, ignored) == []
    assert (repo / ".factory" / "data" / "y").exists()


def test_agent_git_add_is_undone_in_index(repo: Path, dest: Path) -> None:
    (repo / "a.txt").write_text("unstaged wip\n", encoding="utf-8", newline="\n")
    saved = backup.capture(repo, dest)

    git(repo, "add", "a.txt")

    assert backup.verify(saved) == [backup.INDEX]
    outcomes = backup.restore(saved, (), [backup.INDEX])
    assert outcomes == {backup.INDEX: "restored"}
    assert git(repo, "diff", "--cached") == ""
    assert (repo / "a.txt").read_text(encoding="utf-8") == "unstaged wip\n"
