"""The base-move journal (``run/basemoves.py``) and the factory commands that write it."""

from __future__ import annotations

from pathlib import Path

import pytest
from run_repo import commit_all, git, make_run_repo, write

from aifactory.backlog.commit import commit_backlog
from aifactory.providers import git as pgit
from aifactory.run import basemoves
from aifactory.run.basemoves import BaseMove, factory_chain

REF = "refs/heads/main"


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def _move(old: str, new: str, run: str | None = None, ref: str = REF) -> BaseMove:
    return BaseMove(ref=ref, old=old, new=new, run=run, index_tree=None, command="advance")


def test_journal_lives_in_the_common_git_dir(repo: Path) -> None:
    path = basemoves.journal(repo)
    assert path == (repo / ".git" / "haifa" / "base-moves.jsonl").resolve()
    assert basemoves.offset(repo) == 0
    assert basemoves.moves_since(repo, 0) == []


def test_record_and_read_from_offset(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(basemoves.RUN_ENV, raising=False)
    basemoves.record(repo, REF, "a", "b", checkout=None, command="task approve")
    start = basemoves.offset(repo)
    assert start > 0
    monkeypatch.setenv(basemoves.RUN_ENV, "run42")
    basemoves.record(repo, REF, "b", "c", checkout=repo, command="backlog commit")

    every = basemoves.moves_since(repo, 0)
    assert [(m.old, m.new, m.run) for m in every] == [("a", "b", None), ("b", "c", "run42")]
    later = basemoves.moves_since(repo, start)
    assert len(later) == 1
    assert later[0].command == "backlog commit"
    assert later[0].index_tree == git(repo, "write-tree")


def test_broken_lines_are_skipped(repo: Path) -> None:
    basemoves.record(repo, REF, "a", "b", checkout=None, command="advance")
    path = basemoves.journal(repo)
    assert path is not None
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write('{"ref": "refs/heads/main", "old": 1}\nnot json\n[]\n{"ref": "x"')
    basemoves.record(repo, REF, "b", "c", checkout=None, command="advance")
    moves = basemoves.moves_since(repo, 0)
    assert [(m.old, m.new) for m in moves] == [("a", "b")]


def test_record_never_raises(tmp_path: Path) -> None:
    basemoves.record(tmp_path, REF, "a", "b", checkout=None, command="advance")
    assert basemoves.offset(tmp_path) == 0


def test_chain_of_foreign_moves() -> None:
    moves = [_move("x", "y", ref="refs/heads/other"), _move("a", "b", "B"), _move("b", "c")]
    last = factory_chain(moves, REF, "a", "c", "A")
    assert last is not None and last.new == "c"


def test_chain_with_own_link_is_not_foreign() -> None:
    moves = [_move("a", "b", "B"), _move("b", "c", "A")]
    assert factory_chain(moves, REF, "a", "c", "A") is None
    assert factory_chain(moves, REF, "a", "c", None) is not None


def test_chain_with_missing_link_is_not_foreign() -> None:
    assert factory_chain([_move("a", "b")], REF, "a", "c", "A") is None
    assert factory_chain([_move("b", "c")], REF, "a", "c", "A") is None
    assert factory_chain([_move("a", "c", ref="refs/heads/dev")], REF, "a", "c", "A") is None


def test_wait_for_chain_stops_at_own_run(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(basemoves.RUN_ENV, "A")
    basemoves.record(repo, REF, "a", "b", checkout=None, command="advance")
    assert basemoves.wait_for_chain(repo, 0, REF, "a", "b", "A", tries=50, delay=1) is None
    assert basemoves.wait_for_chain(repo, 0, REF, "a", "b", "B") is not None


def test_backlog_commit_records_the_move(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(basemoves.RUN_ENV, raising=False)
    old = git(repo, "rev-parse", "main")
    task = repo / "backlog/M01-core/S01-model/M01-S01-T01-schema.md"
    task.write_text(
        task.read_text(encoding="utf-8") + "\nVíc textu.\n", encoding="utf-8", newline="\n"
    )

    result = commit_backlog(repo)

    assert result.committed and result.commit is not None
    moves = basemoves.moves_since(repo, 0)
    assert len(moves) == 1
    move = moves[0]
    assert (move.ref, move.old, move.new) == (REF, old, result.commit)
    assert move.command == "backlog commit" and move.run is None
    assert move.index_tree == git(repo, "write-tree")


def test_advance_branch_records_the_move(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(basemoves.RUN_ENV, "runB")
    old = git(repo, "rev-parse", "main")
    git(repo, "checkout", "-q", "-b", "side")
    write(repo, "notes.txt", "side\n")
    new = commit_all(repo, "side")
    git(repo, "checkout", "-q", "main")

    pgit.advance_branch(repo, "main", new, old, command="task approve")

    assert git(repo, "rev-parse", "main") == new
    [move] = basemoves.moves_since(repo, 0)
    assert (move.old, move.new, move.run, move.command) == (old, new, "runB", "task approve")
    assert move.index_tree == git(repo, "write-tree")
