"""The ``rebase`` code step on a plain git repo: clean rebase, no-op, conflict, markers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aifactory.workflow import EngineCodeRunner, conflict_markers, rebase_onto, unmerged_files


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return proc.stdout.strip()


def commit(repo: Path, rel: str, text: str, message: str) -> str:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for key in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(key, "Test")
    for key in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(key, "test@example.com")
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "commit.gpgsign", "false")
    commit(repo, "x.txt", "VALUE = 0\n", "init")
    return repo


def test_clean_rebase_keeps_history(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "topic")
    commit(repo, "a.txt", "a\n", "a")
    before = commit(repo, "b.txt", "b\n", "b")
    git(repo, "checkout", "-q", "main")
    onto = commit(repo, "c.txt", "c\n", "c")
    git(repo, "checkout", "-q", "topic")

    result = rebase_onto(repo, "main")

    assert (result.clean, result.conflict, result.squashed) == (True, False, False)
    assert result.onto == onto and result.before == before
    assert result.files == []
    git(repo, "merge-base", "--is-ancestor", onto, "HEAD")
    assert git(repo, "rev-list", "--count", "main..HEAD") == "2"
    assert "cleanly" in result.summary


def test_already_on_onto_is_noop(repo: Path) -> None:
    onto = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "topic")
    head = commit(repo, "a.txt", "a\n", "a")

    result = rebase_onto(repo, onto)

    assert result.clean and not result.conflict
    assert git(repo, "rev-parse", "HEAD") == head


def test_conflict_leaves_markers_on_onto(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "topic")
    before = commit(repo, "x.txt", "VALUE = 2\n", "two")
    git(repo, "checkout", "-q", "main")
    onto = commit(repo, "x.txt", "VALUE = 1\n", "one")
    git(repo, "checkout", "-q", "topic")

    result = rebase_onto(repo, "main")

    assert (result.clean, result.conflict, result.squashed) == (False, True, True)
    assert result.files == ["x.txt"]
    assert result.before == before
    assert git(repo, "rev-parse", "HEAD") == onto
    assert git(repo, "symbolic-ref", "HEAD") == "refs/heads/topic"
    assert unmerged_files(repo) == ["x.txt"]
    assert conflict_markers(repo, ["x.txt"]) == ["x.txt"]
    assert "x.txt" in git(repo, "diff", "HEAD", "--numstat")
    assert "conflicts in x.txt" in result.summary


def test_unknown_onto_raises(repo: Path) -> None:
    with pytest.raises(RuntimeError):
        rebase_onto(repo, "nope")


def test_markers_ignore_rule_and_missing_file(repo: Path) -> None:
    (repo / "doc.md").write_text("Title\n=======\n\ntext\n", encoding="utf-8", newline="\n")
    (repo / "bad.txt").write_text(
        "<<<<<<< HEAD\na\n=======\nb\n>>>>>>> x\n", encoding="utf-8", newline="\n"
    )
    assert conflict_markers(repo, ["doc.md", "gone.txt", "bad.txt"]) == ["bad.txt"]


def test_engine_rebase_needs_target(repo: Path) -> None:
    run = SimpleNamespace(prompt_variables={}, repo_root=str(repo))
    with pytest.raises(RuntimeError, match="factory task resolve"):
        EngineCodeRunner().rebase(run)
