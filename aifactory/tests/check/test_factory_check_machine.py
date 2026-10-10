"""``factory check``: machine, login, library and environment findings (FakeMachine).

No test starts a harness, ``gh`` or ``az``; the library remote is a bare repo on disk.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml
from factory_check_repo import GIT_IDENTITY, FakeMachine, commit_all, make_check_repo, write

from aifactory.check import CheckReport, Finding, Probe, run_check
from aifactory.home import env_file
from aifactory.library.store import init_library, library_root

PI_ROSTER = """\
defaults:
  harness: claude
  model: sonnet
agents:
  - name: planner
    model: opus
  - name: builder
    harness: pi
    model: openai/gpt-5
"""
CODEX_ROSTER = PI_ROSTER.replace("harness: pi\n    model: openai/gpt-5", "harness: codex")
PI_AUTH = ("pi", "auth", "check", "--model", "openai/gpt-5", "--json", "--no-refresh")
PI_MODELS = ("pi", "--list-models")
CATALOG = "provider  model  context\nopenai  gpt-5  400K\nopenai  gpt-5-mini  400K\n"


def _codes(report: CheckReport) -> list[str]:
    return [f.code for f in report.findings]


def _one(report: CheckReport, code: str, scope: str, severity: str) -> Finding:
    found = [f for f in report.findings if f.code == code]
    assert found, (code, _codes(report))
    assert (found[0].scope, found[0].severity) == (scope, severity), found[0]
    return found[0]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_check_repo(tmp_path / "repo")


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    path = tmp_path / "plain"
    path.mkdir()
    return path


def _outside(path: Path, machine: FakeMachine, offline: bool = False) -> CheckReport:
    report = run_check(path, offline=offline, machine=machine, require_repo=False)
    assert report.in_repo is False and report.repo is None and report.state is None
    assert {f.scope for f in report.findings} <= {"machine", "library"}
    return report


def _roster(repo: Path, text: str) -> None:
    write(repo, ".factory/agents.yaml", text)
    commit_all(repo, "roster")


# -- platform and tools --


@pytest.mark.parametrize("name", ["darwin", "linux", "wsl"])
def test_supported_platforms(outside: Path, name: str) -> None:
    assert "unsupported_platform" not in _codes(_outside(outside, FakeMachine(platform_name=name)))


def test_unsupported_platform(outside: Path) -> None:
    report = _outside(outside, FakeMachine(platform_name="win32"))
    finding = _one(report, "unsupported_platform", "machine", "error")
    assert "WSL" in (finding.fix or "")
    assert not report.ok


def test_git_missing(outside: Path) -> None:
    machine = FakeMachine(present={"uv"})
    _one(_outside(outside, machine), "git_missing", "machine", "error")
    assert "git_identity_missing" not in _codes(_outside(outside, machine))
    assert "git_missing" not in _codes(_outside(outside, FakeMachine()))


def test_git_identity_missing(outside: Path, repo: Path) -> None:
    machine = FakeMachine(environ={})
    finding = _one(_outside(outside, machine), "git_identity_missing", "machine", "error")
    assert "user.name" in finding.message and "user.email" in finding.message
    assert ("git", "config", "--get", "user.name") in machine.calls

    machine = FakeMachine(environ={})
    machine.outputs[("git", "config", "--get", "user.name")] = Probe(0, "Ada\n", "")
    machine.outputs[("git", "config", "--get", "user.email")] = Probe(0, "ada@x\n", "")
    assert "git_identity_missing" not in _codes(run_check(repo, machine=machine))

    machine = FakeMachine(environ={})
    machine.outputs[("git", "config", "--get", "user.name")] = Probe(0, "Ada\n", "")
    machine.outputs[("git", "config", "--get", "user.email")] = Probe(1, "", "")
    finding = _one(run_check(repo, machine=machine), "git_identity_missing", "machine", "error")
    assert "user.email" in finding.message and "user.name" not in finding.message


def test_uv_missing(outside: Path) -> None:
    machine = FakeMachine(present={"git", "claude"})
    _one(_outside(outside, machine), "uv_missing", "machine", "warning")
    assert "uv_missing" not in _codes(_outside(outside, FakeMachine()))


def test_harness_missing_outside_is_info(outside: Path) -> None:
    report = _outside(outside, FakeMachine(present={"git", "uv"}))
    found = [f for f in report.findings if f.code == "harness_missing"]
    assert [f.severity for f in found] == ["info"] * 3
    assert [f.message.split()[1] for f in found] == ["claude", "codex", "pi"]
    assert all("optional" in f.message for f in found)
    assert report.ok


def test_node_missing(repo: Path) -> None:
    _roster(repo, PI_ROSTER)
    present = {"just", "claude", "pi", "git", "uv"}
    report = run_check(repo, offline=True, machine=FakeMachine(present=present))
    finding = _one(report, "node_missing", "machine", "error")
    assert "builder" in finding.message
    report = run_check(repo, offline=True, machine=FakeMachine(present=present | {"node"}))
    assert "node_missing" not in _codes(report)
    # a roster without pi does not need node
    _roster(repo, CODEX_ROSTER)
    assert "node_missing" not in _codes(run_check(repo, machine=FakeMachine(present=present)))


# -- logins --


def test_claude_login(repo: Path, outside: Path) -> None:
    machine = FakeMachine(logged_in=False)
    finding = _one(run_check(repo, machine=machine), "harness_login", "machine", "error")
    assert finding.message.startswith("claude is not logged in")
    assert finding.fix == "claude auth login"
    assert ("claude", "auth", "status") in machine.calls
    assert "harness_login" not in _codes(run_check(repo, machine=FakeMachine()))
    # outside a repo every installed harness is asked, as a warning
    _one(_outside(outside, FakeMachine(logged_in=False)), "harness_login", "machine", "warning")


def test_codex_login(repo: Path) -> None:
    _roster(repo, CODEX_ROSTER)
    machine = FakeMachine(present={"just", "claude", "codex", "git", "uv"})
    machine.outputs[("codex", "login", "status")] = Probe(1, "", "Not logged in")
    found = [f for f in run_check(repo, machine=machine).findings if f.code == "harness_login"]
    assert [f.message.split()[0] for f in found] == ["codex"]
    assert found[0].fix == "codex login" and "builder" in found[0].message


def test_pi_login(repo: Path) -> None:
    _roster(repo, PI_ROSTER)
    machine = FakeMachine(present={"just", "claude", "pi", "git", "uv", "node"})
    machine.outputs[PI_AUTH] = Probe(0, '{"ok": false}', "")
    machine.outputs[PI_MODELS] = Probe(0, CATALOG, "")
    found = [f for f in run_check(repo, machine=machine).findings if f.code == "harness_login"]
    assert len(found) == 1 and "openai/gpt-5" in found[0].message
    assert "pi auth login" in (found[0].fix or "")

    machine.outputs[PI_AUTH] = Probe(1, "", "")
    assert "harness_login" in _codes(run_check(repo, machine=machine))
    machine.outputs[PI_AUTH] = Probe(0, '{"ok": true}', "")
    assert "harness_login" not in _codes(run_check(repo, machine=machine))
    machine.outputs[PI_AUTH] = Probe(0, "not json", "")
    assert "harness_login" not in _codes(run_check(repo, machine=machine))


def test_pi_model_unknown(repo: Path) -> None:
    _roster(repo, PI_ROSTER)
    machine = FakeMachine(present={"just", "claude", "pi", "git", "uv", "node"})
    machine.outputs[PI_AUTH] = Probe(0, '{"ok": true}', "")
    machine.outputs[PI_MODELS] = Probe(0, CATALOG, "")
    assert "pi_model_unknown" not in _codes(run_check(repo, machine=machine))

    machine.outputs[PI_MODELS] = Probe(0, "provider model context\nanthropic opus 1M\n", "")
    finding = _one(run_check(repo, machine=machine), "pi_model_unknown", "machine", "error")
    assert "openai/gpt-5" in finding.message and "builder" in finding.message

    machine.outputs[PI_MODELS] = Probe(1, "", "boom")
    assert "pi_model_unknown" not in _codes(run_check(repo, machine=machine))


def test_match_pi_model() -> None:
    from aifactory.check.machine_rules import match_pi_model, pi_catalog

    catalog = pi_catalog(CATALOG)
    assert catalog == [("openai", "gpt-5"), ("openai", "gpt-5-mini")]
    assert match_pi_model(catalog, "openai/gpt-5") == "ok"
    assert match_pi_model(catalog, "gpt-5") == "ok"
    assert match_pi_model(catalog, "mini") == "ok"
    assert match_pi_model(catalog, "gpt") == "ambiguous"
    assert match_pi_model(catalog, "opus") == "missing"


def test_gh_and_az_login(repo: Path) -> None:
    write(repo, ".factory/config.yaml", "base: main\ngit_provider: github\n")
    commit_all(repo, "github")
    _one(run_check(repo, machine=FakeMachine(logged_in=False)), "gh_login", "machine", "error")
    assert "gh_login" not in _codes(run_check(repo, machine=FakeMachine()))
    write(
        repo,
        ".factory/config.yaml",
        "base: main\ngit_provider: azure\nazure:\n  organization: o\n  project: p\n"
        "  repository: r\n",
    )
    commit_all(repo, "azure")
    _one(run_check(repo, machine=FakeMachine(logged_in=False)), "az_login", "machine", "error")
    assert "az_login" not in _codes(run_check(repo, machine=FakeMachine()))


def test_offline_skips_every_login(repo: Path, outside: Path) -> None:
    _roster(repo, PI_ROSTER)
    write(repo, ".factory/config.yaml", "base: main\ngit_provider: github\n")
    commit_all(repo, "github")
    machine = FakeMachine(present={"just", "claude", "pi", "codex", "gh", "git", "uv", "node"})
    report = run_check(repo, offline=True, machine=machine)
    assert machine.calls == []
    finding = _one(report, "hosting_skipped", "machine", "info")
    assert "harnesses" in finding.message
    machine = FakeMachine(present={"claude", "pi", "codex", "git", "uv"}, logged_in=False)
    report = _outside(outside, machine, offline=True)
    assert machine.calls == [] and report.offline


# -- library --


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    return proc.stdout.strip()


@pytest.fixture
def lib(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A library in the test's HAIFA_HOME, pushed to a bare remote on disk."""
    for key, value in GIT_IDENTITY.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    bare = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", "--quiet", "-b", "main", str(bare))
    init_library(remote=str(bare))
    return library_root()


def _meta(lib: Path, **changes: object) -> None:
    path = lib / "library.yaml"
    meta = yaml.safe_load(path.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is None:
            meta.pop(key, None)
        else:
            meta[key] = value
    path.write_text(yaml.safe_dump(meta), encoding="utf-8")
    _git(lib, "commit", "-q", "-am", "meta")


def _library_codes(report: CheckReport) -> list[str]:
    return [f.code for f in report.findings if f.scope == "library" or f.code == "factory_outdated"]


def test_library_missing(outside: Path) -> None:
    report = _outside(outside, FakeMachine())
    finding = _one(report, "library_missing", "library", "warning")
    assert str(library_root()) in finding.message
    assert _library_codes(report) == ["library_missing"]


def test_healthy_library(outside: Path, lib: Path) -> None:
    assert _library_codes(_outside(outside, FakeMachine())) == []


def test_library_dirty(outside: Path, lib: Path) -> None:
    write(lib, "notes.txt", "draft\n")
    finding = _one(_outside(outside, FakeMachine()), "library_dirty", "library", "warning")
    assert "notes.txt" in finding.message and str(lib) in (finding.fix or "")


def test_library_unpushed(outside: Path, lib: Path) -> None:
    write(lib, "notes.txt", "draft\n")
    _git(lib, "add", "-A")
    _git(lib, "commit", "-q", "-m", "local")
    report = _outside(outside, FakeMachine())
    finding = _one(report, "library_unpushed", "library", "warning")
    assert "1 commit(s)" in finding.message and "as of the last fetch" in finding.message
    assert finding.fix == "factory library push"
    assert "library_behind" not in _codes(report)


def test_library_behind(outside: Path, lib: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", str(tmp_path / "remote.git"), str(other))
    write(other, "notes.txt", "remote\n")
    _git(other, "add", "-A")
    _git(other, "commit", "-q", "-m", "remote")
    _git(other, "push", "-q", "origin", "main")
    assert "library_behind" not in _codes(_outside(outside, FakeMachine()))  # no fetch yet
    _git(lib, "fetch", "-q", "origin")  # the test fetches; the check never does
    finding = _one(_outside(outside, FakeMachine()), "library_behind", "library", "warning")
    assert finding.fix == "factory library pull"


def test_factory_outdated(outside: Path, lib: Path) -> None:
    _meta(lib, min_factory_version="999.0")
    report = _outside(outside, FakeMachine())
    finding = _one(report, "factory_outdated", "machine", "error")
    assert "999.0" in finding.message and finding.fix == "factory upgrade"
    assert not report.ok


def test_seed_update_available(outside: Path, lib: Path) -> None:
    _meta(lib, seed={})
    finding = _one(_outside(outside, FakeMachine()), "seed_update_available", "library", "info")
    assert finding.fix == "factory library seed"


# -- environment --


def test_env_file_mode(outside: Path) -> None:
    path = env_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("X=1\n", encoding="utf-8")
    machine = FakeMachine(modes={path: 0o644})
    finding = _one(_outside(outside, machine), "env_file_mode", "machine", "warning")
    assert finding.fix == f"chmod 600 {path}"
    assert "env_file_mode" not in _codes(_outside(outside, FakeMachine(modes={path: 0o600})))
    if os.name == "posix":
        path.chmod(0o644)
        assert "env_file_mode" in _codes(_outside(outside, FakeMachine()))
        path.chmod(0o600)
        assert "env_file_mode" not in _codes(_outside(outside, FakeMachine()))


def test_no_env_file(outside: Path) -> None:
    assert "env_file_mode" not in _codes(_outside(outside, FakeMachine()))


@pytest.mark.parametrize(
    "name",
    [
        "CLAUDE_SAFE_MODE",
        "CLAUDE_MCP_CONFIG",
        "CLAUDE_PERMISSION_MODE",
        "CODEX_SAFE_MODE",
        "CODEX_SANDBOX",
        "PI_SAFE_MODE",
    ],
)
def test_env_override(outside: Path, name: str) -> None:
    machine = FakeMachine(environ={**GIT_IDENTITY, name: "/some/value"})
    found = [f for f in _outside(outside, machine).findings if f.code == "env_override"]
    assert len(found) == 1
    assert (found[0].scope, found[0].severity) == ("machine", "info")
    assert found[0].message.startswith(f"{name}=/some/value is set")
    empty = FakeMachine(environ={**GIT_IDENTITY, name: ""})
    assert "env_override" not in _codes(_outside(outside, empty))


def test_codex_not_isolated(repo: Path, tmp_path: Path) -> None:
    _roster(repo, CODEX_ROSTER)
    home = tmp_path / "home"
    write(home, ".codex/AGENTS.md", "global\n")
    present = {"just", "claude", "codex", "git", "uv"}
    report = run_check(repo, offline=True, machine=FakeMachine(present=present, home_dir=home))
    _one(report, "codex_not_isolated", "machine", "warning")
    safe = FakeMachine(
        present=present, home_dir=home, environ={**GIT_IDENTITY, "CODEX_SAFE_MODE": "1"}
    )
    assert "codex_not_isolated" not in _codes(run_check(repo, offline=True, machine=safe))
