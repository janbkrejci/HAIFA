"""``factory check``: envelope, exit codes 0/1/2 and the text output."""

from __future__ import annotations

from pathlib import Path

import pytest
from factory_check_repo import FakeMachine, commit_all, make_check_repo, write

from aifactory import check
from aifactory.cli import main
from cli_json import run_json

Capsys = pytest.CaptureFixture[str]
KEYS = {"code", "scope", "severity", "message", "fix", "action"}


@pytest.fixture
def machine(monkeypatch: pytest.MonkeyPatch) -> FakeMachine:
    fake = FakeMachine()
    monkeypatch.setattr(check, "default_machine", lambda: fake)
    return fake


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_check_repo(tmp_path / "repo")


def test_ok(repo: Path, machine: FakeMachine, capsys: Capsys) -> None:
    write(repo, ".factory/prompts/builder/user.md", "Changed: {{prompt}}\n")
    rc, obj = run_json(capsys, ["check", "--repo", str(repo), "--json"])
    assert rc == 0
    data = obj["data"]
    assert data["ok"] is True and data["state"] == "pre_library"
    assert data["counts"] == {"error": 0, "warning": 2, "info": 1}
    assert data["in_repo"] is True
    assert [set(f) for f in data["findings"]] == [KEYS, KEYS, KEYS]
    assert obj["warnings"] == []


def test_cwd(
    repo: Path, machine: FakeMachine, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo / ".factory")
    rc, obj = run_json(capsys, ["check", "--json"])
    assert rc == 0 and obj["data"]["repo"] == str(repo)


def test_errors(repo: Path, machine: FakeMachine, capsys: Capsys) -> None:
    machine.present.discard("claude")
    write(repo, "justfile", "lint:\n    ruff\n")
    commit_all(repo, "no test recipe")
    rc, obj = run_json(capsys, ["check", "--repo", str(repo), "--json"])
    assert rc == 1
    assert obj["error"]["code"] == "checks_failed"
    assert "test_recipe_missing" in obj["error"]["message"]
    codes = {f["code"]: f for f in obj["data"]["findings"]}
    assert codes["harness_missing"]["scope"] == "machine"
    assert codes["test_recipe_missing"]["scope"] == "repo"
    assert obj["data"]["ok"] is False


def test_offline(repo: Path, machine: FakeMachine, capsys: Capsys) -> None:
    write(repo, ".factory/config.yaml", "base: main\ngit_provider: github\n")
    commit_all(repo, "github")
    machine.logged_in = False
    rc, obj = run_json(capsys, ["check", "--repo", str(repo), "--offline", "--json"])
    assert machine.calls == []
    assert obj["data"]["offline"] is True
    assert "hosting_skipped" in {f["code"] for f in obj["data"]["findings"]}
    assert rc == 0


def test_not_a_repository(tmp_path: Path, machine: FakeMachine, capsys: Capsys) -> None:
    rc, obj = run_json(capsys, ["check", "--repo", str(tmp_path), "--json"])
    assert rc == 2
    assert obj["error"]["code"] == "not_a_repository"
    assert main(["check", "--repo", str(tmp_path)]) == 2
    assert "not a git repository" in capsys.readouterr().err


def test_text_output(repo: Path, machine: FakeMachine, capsys: Capsys) -> None:
    assert main(["check", "--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("state:   pre_library (main @ ")
    assert "next: onboard" in out
    assert "0 error(s), 1 warning(s), 1 info" in out
    assert "warning library library_missing:" in out
    machine.present.discard("just")
    assert main(["check", "--repo", str(repo)]) == 1
    out = capsys.readouterr().out
    assert "error   machine just_missing:" in out
    assert "fix: install just" in out


def test_outside_a_repository(
    tmp_path: Path, machine: FakeMachine, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "plain"
    outside.mkdir()
    monkeypatch.chdir(outside)
    rc, obj = run_json(capsys, ["check", "--json"])
    assert rc == 0
    data = obj["data"]
    assert data["in_repo"] is False
    assert (data["repo"], data["state"], data["action"], data["base"]) == (None,) * 4
    assert data["findings"]
    assert {f["scope"] for f in data["findings"]} <= {"machine", "library"}
    assert "library_missing" in {f["code"] for f in data["findings"]}

    machine.platform_name = "win32"
    rc, obj = run_json(capsys, ["check", "--json"])
    assert rc == 1 and obj["error"]["code"] == "checks_failed"
    assert "unsupported_platform" in obj["error"]["message"]

    machine.platform_name = "linux"
    assert main(["check"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("state:   outside a git repository (machine and library only)")
    assert "remote:" not in out


def test_explicit_repo_outside_a_repository_still_exits_2(
    tmp_path: Path, machine: FakeMachine, capsys: Capsys
) -> None:
    rc, obj = run_json(capsys, ["check", "--repo", str(tmp_path), "--offline", "--json"])
    assert rc == 2 and obj["error"]["code"] == "not_a_repository"


def test_factory_without_a_command_prints_the_first_run_hint(capsys: Capsys) -> None:
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "usage:" in out
    assert out.rstrip().endswith("První spuštění: factory check")
