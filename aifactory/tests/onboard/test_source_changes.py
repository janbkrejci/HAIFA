"""Source blockers compare Git content, including Windows clean filters."""

from pathlib import Path

import pytest
from onboard_repo import commit_all, git, init_repo, write

from aifactory.library.config_edit import read_state
from aifactory.library.tree import tree_files
from aifactory.onboard.onboard import _source_changes, _sssf_changes


@pytest.mark.parametrize("kind", ["factory", "sssf"])
@pytest.mark.parametrize("autocrlf", ["true", "false"])
def test_source_changes_respect_git_filters(tmp_path: Path, kind: str, autocrlf: str) -> None:
    repo = init_repo(tmp_path / "repo")
    git(repo, "config", "core.autocrlf", autocrlf)
    git(repo, "config", "core.safecrlf", "false")
    if kind == "factory":
        path = ".factory/config.yaml"
        content = b"base: main\r\ngit_provider: local\r\n"
    else:
        path = "adws/adw_modules/utils.py"
        content = b"# committed source\r\n"
    disk = write(repo, path, content)
    commit_all(repo)
    index = repo / ".git/index"
    before = index.read_bytes()

    if kind == "factory":
        state = read_state(repo, "base")

        def changes() -> list[str]:
            return _source_changes(repo, state.files, state.executable)
    else:
        files = {f.path: f for f in tree_files(repo, "HEAD", ["adws"])}

        def changes() -> list[str]:
            return _sssf_changes(repo, files)

    assert changes() == []
    assert index.read_bytes() == before
    disk.write_bytes(content.replace(b"\r\n", b"\n"))
    assert changes() == ([] if autocrlf == "true" else [path])
    assert index.read_bytes() == before
    disk.write_bytes(content + b"# local edit\r\n")
    assert changes() == [path]
    assert index.read_bytes() == before
    disk.unlink()
    assert changes() == [path]
    assert index.read_bytes() == before
