"""The onboarding state of a repo (AR30, O1) and how `factory check` reports it."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from onboard_repo import (
    HAIFA_FACTORY,
    SSSF_TEMPLATES,
    commit_all,
    copy_haifa_factory,
    git,
    git_state,
    init_repo,
    stamp_sssf,
    write,
)

from aifactory.check import run_check
from aifactory.config.manifest import (
    MANIFEST_FILE,
    LibraryRef,
    Manifest,
    Onboarding,
    dump_manifest,
)
from aifactory.onboard import repo_state

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "check"))

from factory_check_repo import FakeMachine  # noqa: E402

CONFIG = "base: main\n"
AGENTS = "defaults:\n  harness: claude\nagents:\n  - name: builder\n    purpose: Build.\n"
ONBOARDING = Onboarding(
    source="sssf",
    source_commit="a" * 40,
    at="2026-10-02T10:00:00Z",
    by="Ada Tester",
    factory="0.1.0",
    library_commit="b" * 40,
)
MANIFEST = Manifest(
    written_by="0.1.0",
    library=LibraryRef(id="lib-1", name="team", remote="https://example.com/lib.git"),
    onboarding=ONBOARDING,
)

needs_haifa = pytest.mark.skipif(
    not (HAIFA_FACTORY / "config.yaml").is_file(), reason="HAIFA's .factory/ is not here"
)
needs_sssf = pytest.mark.skipif(
    not (SSSF_TEMPLATES / "sssf.config.yaml").is_file(), reason="vendor/sssf is not here"
)


def _onboarded(repo: Path) -> None:
    write(repo, ".factory/config.yaml", CONFIG)
    write(repo, ".factory/agents.yaml", AGENTS)
    write(repo, MANIFEST_FILE, dump_manifest(MANIFEST))


# ── states ────────────────────────────────────────────────────────────────────


def test_onboarded(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    _onboarded(repo)
    sha = commit_all(repo, "onboard")
    state = repo_state(repo)
    assert (state.state, state.action, state.commit, state.base) == (
        "onboarded",
        "adopt",
        sha,
        "main",
    )
    assert state.onboarding == ONBOARDING.model_dump(mode="json")
    assert state.library == {"id": "lib-1", "name": "team", "remote": "https://example.com/lib.git"}
    assert not state.sssf_leftover and not state.alternate_rosters
    data = state.to_json()
    assert data["state"] == "onboarded" and data["action"] == "adopt"
    assert data["onboarding"]["by"] == "Ada Tester"


@needs_haifa
def test_haifa_copy_is_pre_library_with_leftover(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "haifa")
    copy_haifa_factory(repo)
    commit_all(repo, "haifa")
    state = repo_state(repo)
    assert (state.state, state.action) == ("pre_library", "onboard")
    assert state.sssf_leftover is True
    assert state.alternate_rosters is False
    assert state.rosters == ("adws/adw_sssf_config/sssf.config.yaml",)
    assert state.onboarding is None


@needs_haifa
def test_haifa_copy_onboarded_keeps_leftover(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "haifa")
    copy_haifa_factory(repo)
    write(repo, MANIFEST_FILE, dump_manifest(MANIFEST))
    commit_all(repo, "haifa onboarded")
    state = repo_state(repo)
    assert (state.state, state.sssf_leftover) == ("onboarded", True)


def test_agents_yaml_alone_is_pre_library(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    write(repo, ".factory/agents.yaml", AGENTS)
    commit_all(repo, "roster")
    assert repo_state(repo).state == "pre_library"


@needs_sssf
def test_sssf_fixture(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "sssf")
    stamp_sssf(repo)
    commit_all(repo, "sssf")
    state = repo_state(repo)
    assert (state.state, state.action) == ("sssf", "onboard")
    assert state.sssf_leftover is False  # no .factory/ next to adws/
    assert state.alternate_rosters is False
    assert state.rosters == ("adws/adw_sssf_config/sssf.config.yaml",)


@needs_sssf
def test_sssf_alternate_rosters(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "sssf")
    stamp_sssf(repo)
    src = repo / "adws" / "adw_sssf_config" / "sssf.config.yaml"
    write(repo, "adws/adw_sssf_config/validation.yaml", src.read_text(encoding="utf-8"))
    write(repo, "adws/adw_sssf_config/notes.txt", "not a roster\n")
    commit_all(repo, "two rosters")
    state = repo_state(repo)
    assert state.state == "sssf" and state.alternate_rosters is True
    assert len(state.rosters) == 2


def test_config_only_in_working_tree(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    write(repo, ".factory/config.yaml", CONFIG)
    state = repo_state(repo)
    assert (state.state, state.action) == ("working_tree", "config_commit")


@needs_sssf
def test_sssf_only_in_working_tree(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    stamp_sssf(repo)
    assert repo_state(repo).state == "working_tree"


def test_manifest_only_in_working_tree_stays_pre_library(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    write(repo, ".factory/config.yaml", CONFIG)
    commit_all(repo, "config")
    write(repo, MANIFEST_FILE, dump_manifest(MANIFEST))
    assert repo_state(repo).state == "pre_library"  # base decides, not the working tree


def test_none(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    state = repo_state(repo)
    assert (state.state, state.action) == ("none", "init")
    assert state.commit == git(repo, "rev-parse", "HEAD")


def test_none_without_commit(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "empty", readme=False)
    state = repo_state(repo)
    assert (state.state, state.commit) == ("none", None)


def test_other_base(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    git(repo, "switch", "-q", "-c", "dev")
    _onboarded(repo)
    commit_all(repo, "onboard on dev")
    git(repo, "switch", "-q", "main")
    assert repo_state(repo, "main").state == "none"
    assert repo_state(repo, "dev").state == "onboarded"


def test_invalid_manifest_is_onboarded_with_error(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    write(repo, ".factory/config.yaml", CONFIG)
    write(repo, MANIFEST_FILE, "format: 99\nwritten_by: x\n")
    commit_all(repo, "future manifest")
    state = repo_state(repo)
    assert state.state == "onboarded" and state.onboarding is None
    assert state.manifest_error is not None and "newer" in state.manifest_error


# ── reading only ──────────────────────────────────────────────────────────────


def test_state_changes_no_index_or_ref(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    _onboarded(repo)
    commit_all(repo, "onboard")
    # stale stat data: a command that refreshes the index would rewrite it
    os.utime(repo / ".factory" / "agents.yaml", ns=(1, 1))
    os.utime(repo / "README.md", ns=(1, 1))
    before = git_state(repo)
    assert repo_state(repo).state == "onboarded"
    assert git_state(repo) == before


def test_state_runs_only_read_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = init_repo(tmp_path / "repo")
    _onboarded(repo)
    commit_all(repo, "onboard")
    calls: list[tuple[list[str], dict[str, str]]] = []
    real = subprocess.run

    def spy(argv: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(argv, list) and argv and argv[0] == "git":
            calls.append((list(argv), dict(kwargs.get("env") or {})))
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    repo_state(repo)
    assert calls
    assert {argv[1] for argv, _ in calls} <= {"rev-parse", "ls-tree", "cat-file"}
    assert all(env.get("GIT_OPTIONAL_LOCKS") == "0" for _, env in calls)
    assert not any("fetch" in argv for argv, _ in calls)


# ── factory check ─────────────────────────────────────────────────────────────


def _codes(report: Any) -> list[str]:
    return [f.code for f in report.findings]


def test_check_onboarded(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    _onboarded(repo)
    write(repo, "adws/adw_sssf_config/sssf.config.yaml", "agents: []\n")
    commit_all(repo, "onboard")
    report = run_check(repo, machine=FakeMachine())
    assert (report.state, report.action) == ("onboarded", "adopt")
    assert report.onboarding == ONBOARDING.model_dump(mode="json")
    assert report.sssf_leftover is True
    found = {f.code: f for f in report.findings}
    onboarded = found["repo_onboarded"]
    assert (onboarded.severity, onboarded.action) == ("info", "adopt")
    assert "Ada Tester" in onboarded.message and "team" in onboarded.message
    assert found["sssf_leftover"].severity == "info"
    data = report.to_json()
    assert data["state"] == "onboarded" and data["action"] == "adopt"
    assert data["onboarding"]["source"] == "sssf"


@needs_sssf
def test_check_sssf(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "sssf")
    stamp_sssf(repo)
    write(repo, "adws/adw_sssf_config/other.yaml", "agents: []\n")
    commit_all(repo, "sssf")
    report = run_check(repo, machine=FakeMachine())
    assert (report.state, report.action, report.alternate_rosters) == ("sssf", "onboard", True)
    repo_codes = [f.code for f in report.findings if f.scope == "repo"]
    assert repo_codes == ["sssf_not_onboarded", "alternate_rosters"]
    finding = report.findings[0]
    assert (finding.severity, finding.action) == ("error", "onboard")
    assert not report.ok


@needs_haifa
def test_check_haifa_copy(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "haifa")
    copy_haifa_factory(repo)
    commit_all(repo, "haifa")
    report = run_check(repo, machine=FakeMachine())
    assert (report.state, report.action) == ("pre_library", "onboard")
    assert "pre_library_config" in _codes(report) and "sssf_leftover" in _codes(report)
