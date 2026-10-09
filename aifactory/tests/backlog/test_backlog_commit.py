"""``factory backlog commit``: commit only the backlog's working-tree changes to ``base``."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from aifactory.backlog import TaskEditError, add_task, commit_backlog, link_task
from cli_json import run_json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))

from run_repo import T01, git, make_run_repo, write  # noqa: E402


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def committed_files(repo: Path, ref: str = "HEAD") -> list[str]:
    return git(repo, "show", "--name-only", "--format=", ref).splitlines()


def test_commits_only_the_backlog(repo: Path) -> None:
    before = git(repo, "rev-parse", "HEAD")
    added = add_task(repo, "M01-S01", "Třetí")
    write(repo, "README.md", "changed\n")
    write(repo, "notes.txt", "draft\n")
    result = commit_backlog(repo)
    assert result.committed and not result.pushed
    assert result.base == "main"
    assert result.paths == [added.path]
    assert result.commit == git(repo, "rev-parse", "HEAD")
    assert git(repo, "rev-parse", "HEAD~1") == before
    assert committed_files(repo) == [added.path]
    assert git(repo, "log", "-1", "--format=%s") == "backlog: 1 file(s) from factory"
    status = git(repo, "status", "--porcelain").splitlines()
    assert sorted(line.split()[-1] for line in status) == ["README.md", "notes.txt"]


def test_an_edited_file_alone_keeps_its_path_and_nothing_else_is_committed(repo: Path) -> None:
    """``git status`` lists it first as `` M <path>``: the path must not lose a character,
    else no backlog root owns it and ``git add -A`` would stage the whole checkout."""
    rel = "backlog/M01-core/S01-model/index.md"
    path = repo / rel
    path.write_text(
        path.read_text().replace("---\n", "---\nauto_continue: true\n", 1),
        encoding="utf-8",
        newline="\n",
    )
    write(repo, "README.md", "changed\n")  # tracked, outside the backlog
    result = commit_backlog(repo)
    assert result.committed and result.paths == [rel]
    assert committed_files(repo) == [rel]
    assert git(repo, "status", "--porcelain").split() == ["M", "README.md"]


def test_nothing_to_commit(repo: Path) -> None:
    before = git(repo, "rev-parse", "HEAD")
    result = commit_backlog(repo)
    assert not result.committed and result.commit is None and result.paths == []
    assert git(repo, "rev-parse", "HEAD") == before


def test_custom_message_and_edits(repo: Path) -> None:
    added = add_task(repo, "M01-S01", "Třetí")
    link_task(repo, added.task.id, depends_on=[T01])
    result = commit_backlog(repo, "backlog: nový task")
    assert result.committed
    assert git(repo, "log", "-1", "--format=%s") == "backlog: nový task"


def test_invalid_backlog_is_refused(repo: Path) -> None:
    path = repo / "backlog/M01-core/S01-model/M01-S01-T01-schema.md"
    path.write_text(
        path.read_text().replace("status: todo", "status: todo\ndepends_on: [NOPE]"),
        encoding="utf-8",
        newline="\n",
    )
    before = git(repo, "rev-parse", "HEAD")
    with pytest.raises(TaskEditError) as info:
        commit_backlog(repo)
    assert info.value.code == "backlog_invalid" and info.value.exit_code == 1
    assert any(i.code == "unknown_ref" for i in info.value.issues)
    assert git(repo, "rev-parse", "HEAD") == before


def test_not_on_base(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "feature")
    add_task(repo, "M01-S01", "Třetí")
    with pytest.raises(TaskEditError) as info:
        commit_backlog(repo)
    assert info.value.code == "not_on_base"
    assert "feature" in info.value.message


def test_pushes_to_the_remote(repo: Path, tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "main")
    add_task(repo, "M01-S01", "Třetí")
    result = commit_backlog(repo)
    assert result.pushed
    assert git(remote, "rev-parse", "main") == result.commit


def test_cli_json(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    added = add_task(repo, "M01-S01", "Třetí")
    rc, env = run_json(capsys, ["backlog", "commit", "--json", "--repo", str(repo)])
    assert rc == 0
    assert env["data"]["committed"] is True
    assert env["data"]["paths"] == [added.path]
    rc, env = run_json(capsys, ["backlog", "commit", "--json", "--repo", str(repo)])
    assert rc == 0 and env["data"]["committed"] is False
    git(repo, "switch", "-q", "-c", "feature")
    rc, env = run_json(capsys, ["backlog", "commit", "--json", "--repo", str(repo)])
    assert rc == 2 and env["error"]["code"] == "not_on_base"
