"""``aifactory.config.repo_state``: the state of a repo read from base, nothing written."""

from __future__ import annotations

from pathlib import Path

from config_repo import commit_all, git, write

from aifactory.config.manifest import (
    MANIFEST_FILE,
    LibraryRef,
    Manifest,
    Onboarding,
    dump_manifest,
)
from aifactory.config.repo_state import repo_state

MANIFEST = Manifest(
    written_by="0.1.0",
    library=LibraryRef(id="lib-1", name="team", remote=None),
    onboarding=Onboarding(source="init", at="2026-10-02T10:00:00Z", by="Ada", factory="0.1.0"),
)
JSON_KEYS = ["repo", "base", "commit", "state", "action", "onboarding", "library", "manifest_error"]


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    write(path, "README.md", "readme\n")
    commit_all(path, "readme")
    return path


def test_installed(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    write(repo, ".factory/config.yaml", "base: main\n")
    write(repo, MANIFEST_FILE, dump_manifest(MANIFEST))
    commit_all(repo, "install")
    state = repo_state(repo)
    assert (state.state, state.action, state.config_in_base) == ("installed", None, True)
    data = state.to_json()
    assert list(data) == JSON_KEYS
    assert data["onboarding"]["by"] == "Ada" and data["library"]["name"] == "team"
    assert data["manifest_error"] is None


def test_installed_with_broken_manifest(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    write(repo, MANIFEST_FILE, "format: 1\nwritten_by: x\nonboarding: {source: other}\n")
    commit_all(repo, "broken")
    state = repo_state(repo)
    assert state.state == "installed"
    assert state.manifest is None and state.manifest_error


def test_installed_wins_over_adws(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    write(repo, MANIFEST_FILE, dump_manifest(MANIFEST))
    write(repo, "adws/adw_sssf_config/sssf.config.yaml", "agents: []\n")
    commit_all(repo, "both")
    assert repo_state(repo).state == "installed"


def test_uncommitted(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    write(repo, ".factory/config.yaml", "base: main\n")
    state = repo_state(repo)
    assert (state.state, state.action) == ("uncommitted", "config_commit")
    assert not state.config_in_base


def test_none(tmp_path: Path) -> None:
    state = repo_state(_repo(tmp_path / "repo"))
    assert (state.state, state.action, state.config_in_base) == ("none", "init", False)
    assert state.onboarding is None and state.library is None


def test_unsupported_factory_without_manifest(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    write(repo, ".factory/config.yaml", "base: main\n")
    commit_all(repo, "old factory")
    state = repo_state(repo)
    assert (state.state, state.action, state.config_in_base) == ("unsupported", None, True)


def test_unsupported_sssf(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    write(repo, "adws/adw_sssf_config/sssf.config.yaml", "agents: []\n")
    commit_all(repo, "sssf")
    state = repo_state(repo)
    assert (state.state, state.action, state.config_in_base) == ("unsupported", None, False)
    assert list(state.to_json()) == JSON_KEYS


def test_nothing_is_written(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    write(repo, ".factory/config.yaml", "base: main\n")
    write(repo, MANIFEST_FILE, dump_manifest(MANIFEST))
    commit_all(repo, "install")
    git(repo, "status", "--porcelain")  # settle the index before measuring it
    index = repo / ".git" / "index"
    before = (index.stat().st_mtime_ns, git(repo, "rev-parse", "HEAD"))
    repo_state(repo)
    # the index first: git status itself may refresh it
    assert (index.stat().st_mtime_ns, git(repo, "rev-parse", "HEAD")) == before
    assert git(repo, "status", "--porcelain") == ""
