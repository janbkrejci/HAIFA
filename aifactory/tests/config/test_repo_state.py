"""``aifactory.config.repo_state``: the state of a repo read from base, nothing written."""

from __future__ import annotations

from pathlib import Path

from config_repo import commit_all, git, write

from aifactory.config.repo_state import repo_state

CONFIG = ".factory/config.yaml"
JSON_KEYS = ["repo", "base", "commit", "state", "action"]


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    write(path, "README.md", "readme\n")
    commit_all(path, "readme")
    return path


def test_installed(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    write(repo, CONFIG, "base: main\n")
    commit_all(repo, "install")
    state = repo_state(repo)
    assert (state.state, state.action, state.config_in_base) == ("installed", None, True)
    assert list(state.to_json()) == JSON_KEYS


def test_installed_wins_over_adws(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    write(repo, CONFIG, "base: main\n")
    write(repo, "adws/adw_sssf_config/sssf.config.yaml", "agents: []\n")
    commit_all(repo, "both")
    assert repo_state(repo).state == "installed"


def test_old_manifest_is_ignored(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    write(repo, ".factory/manifest.yaml", "format: 1\n")
    commit_all(repo, "manifest without config")
    assert repo_state(repo).state == "none"


def test_uncommitted(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    write(repo, CONFIG, "base: main\n")
    state = repo_state(repo)
    assert (state.state, state.action) == ("uncommitted", "config_commit")
    assert not state.config_in_base


def test_none(tmp_path: Path) -> None:
    state = repo_state(_repo(tmp_path / "repo"))
    assert (state.state, state.action, state.config_in_base) == ("none", "init", False)


def test_unsupported_sssf(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    write(repo, "adws/adw_sssf_config/sssf.config.yaml", "agents: []\n")
    commit_all(repo, "sssf")
    state = repo_state(repo)
    assert (state.state, state.action, state.config_in_base) == ("unsupported", None, False)


def test_nothing_is_written(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    write(repo, CONFIG, "base: main\n")
    commit_all(repo, "install")
    git(repo, "status", "--porcelain")  # settle the index before measuring it
    index = repo / ".git" / "index"
    before = (index.stat().st_mtime_ns, git(repo, "rev-parse", "HEAD"))
    repo_state(repo)
    # the index first: git status itself may refresh it
    assert (index.stat().st_mtime_ns, git(repo, "rev-parse", "HEAD")) == before
    assert git(repo, "status", "--porcelain") == ""
