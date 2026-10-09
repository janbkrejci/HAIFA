"""The journal of factory writes (``run/mainwrites.py``) and ``backup.supersede``."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from run_repo import git, make_run_repo, write

from aifactory.backlog import edit_task
from aifactory.run import backup, basemoves, mainwrites
from aifactory.run.mainwrites import MainWrite

PATH = "backlog/M01-core/S01-model/M01-S01-T02-loader.md"


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _absent(_: str) -> backup.FileState:
    return backup.ABSENT


def _record(repo: Path, path: str, old: bytes | None, new: bytes) -> None:
    mainwrites.record(repo, path, old, new, mode=0o644, command="task edit")


def _write(
    repo: Path, path: str, old: bytes | None, new: bytes, run: str | None = None
) -> MainWrite:
    return MainWrite(
        checkout=str(repo.resolve()),
        path=path,
        old=_sha(old) if old is not None else None,
        new=_sha(new),
        mode=0o644,
        run=run,
        command="task edit",
    )


def test_record_and_read_from_offset(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert mainwrites.journal(repo) == (repo / ".git" / "haifa" / "main-writes.jsonl").resolve()
    assert mainwrites.offset(repo) == 0
    monkeypatch.delenv(basemoves.RUN_ENV, raising=False)
    _record(repo, "backlog/a.md", None, b"a\n")
    start = mainwrites.offset(repo)
    assert start > 0
    monkeypatch.setenv(basemoves.RUN_ENV, "run42")
    _record(repo, "backlog/a.md", b"a\n", b"b\n")

    every = mainwrites.writes_since(repo, 0)
    assert [(w.old, w.new, w.run) for w in every] == [
        (None, _sha(b"a\n"), None),
        (_sha(b"a\n"), _sha(b"b\n"), "run42"),
    ]
    later = mainwrites.writes_since(repo, start)
    assert [w.run for w in later] == ["run42"]
    assert later[0].checkout == str(repo.resolve())
    assert mainwrites.content(repo, _sha(b"b\n")) == b"b\n"
    assert mainwrites.content(repo, _sha(b"missing")) is None


def test_broken_lines_are_skipped(repo: Path) -> None:
    path = mainwrites.journal(repo)
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('nonsense\n[1]\n{"path": "x"}\n', encoding="utf-8", newline="\n")
    _record(repo, "backlog/a.md", None, b"a\n")
    assert [w.path for w in mainwrites.writes_since(repo, 0)] == ["backlog/a.md"]


def test_record_outside_a_repo_is_a_no_op(tmp_path: Path) -> None:
    _record(tmp_path, "backlog/a.md", None, b"a\n")
    assert mainwrites.offset(tmp_path) == 0
    assert mainwrites.writes_since(tmp_path, 0) == []


def test_task_edit_records_its_write(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(basemoves.RUN_ENV, raising=False)
    old = (repo / PATH).read_bytes()
    edit_task(repo, "M01-S01-T02", title="Nový název")
    (entry,) = mainwrites.writes_since(repo, 0)
    new = (repo / PATH).read_bytes()
    assert (entry.path, entry.old, entry.new) == (PATH, _sha(old), _sha(new))
    assert entry.command == "task edit"
    assert entry.run is None
    assert mainwrites.content(repo, entry.new) == new


def test_accept_foreign_write_of_a_new_file(repo: Path) -> None:
    _record(repo, "backlog/a.md", None, b"a\n")
    found = mainwrites.accept(repo, mainwrites.writes_since(repo, 0), _absent, "own")
    assert found.states == {"backlog/a.md": (b"a\n", 0o644)}
    assert found.agent_first == []


def test_accept_ignores_writes_of_the_own_run(repo: Path) -> None:
    _record(repo, "backlog/a.md", None, b"a\n")
    writes = [_write(repo, "backlog/a.md", None, b"a\n", run="own")]
    found = mainwrites.accept(repo, writes, _absent, "own")
    assert found.states == {}
    assert found.agent_first == []


def test_accept_chains_writes_of_one_path(repo: Path) -> None:
    _record(repo, "backlog/a.md", None, b"a\n")
    _record(repo, "backlog/a.md", b"a\n", b"b\n")
    found = mainwrites.accept(repo, mainwrites.writes_since(repo, 0), _absent, "own")
    assert found.states == {"backlog/a.md": (b"b\n", 0o644)}
    assert found.agent_first == []


def test_accept_reports_a_change_before_the_factory_write(repo: Path) -> None:
    _record(repo, "backlog/a.md", b"agent\n", b"b\n")
    found = mainwrites.accept(repo, mainwrites.writes_since(repo, 0), _absent, "own")
    assert found.states == {"backlog/a.md": (b"b\n", 0o644)}
    assert found.agent_first == ["backlog/a.md"]


def test_accept_skips_a_write_the_backup_caught(repo: Path) -> None:
    _record(repo, "backlog/a.md", None, b"a\n")
    caught = backup.FileState("file", _sha(b"a\n"), 0o644)
    found = mainwrites.accept(repo, mainwrites.writes_since(repo, 0), lambda _: caught, "own")
    assert found.states == {}
    assert found.agent_first == []


def test_accept_ignores_another_checkout(repo: Path, tmp_path: Path) -> None:
    _record(repo, "backlog/a.md", None, b"a\n")
    other = tmp_path / "other"
    other.mkdir()
    found = mainwrites.accept(other, mainwrites.writes_since(repo, 0), _absent, "own")
    assert found.states == {}


def test_supersede_sets_the_factory_content(repo: Path, tmp_path: Path) -> None:
    write(repo, PATH, "operator draft\n")
    saved = backup.capture(repo, tmp_path / "backup")
    write(repo, PATH, "factory\n")
    assert backup.verify(saved) == [PATH]

    backup.supersede(saved, PATH, b"factory\n", 0o644)
    assert backup.verify(saved) == []

    write(repo, PATH, "agent\n")
    assert backup.restore(saved, (), [PATH]) == {PATH: "restored from backup"}
    assert (repo / PATH).read_text(encoding="utf-8") == "factory\n"
    assert (saved.dir / "superseded" / PATH).read_text(encoding="utf-8") == "operator draft\n"
    assert git(repo, "status", "--porcelain").strip() == f"M {PATH}"
