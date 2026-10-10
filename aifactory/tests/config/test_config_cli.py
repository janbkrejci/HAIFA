"""`factory config status` and `factory config show`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from config_repo import AGENTS_YAML, commit_all, make_repo, write

from aifactory.cli import main
from cli_json import read_envelope

PLANNER_SYSTEM = ".factory/prompts/planner/system.md"


def _dirty(repo: Path) -> None:
    write(repo, PLANNER_SYSTEM, "edited\n")
    write(repo, ".factory/agents.yaml", AGENTS_YAML.replace("model: opus", "model: haiku"))


def _json(capsys: pytest.CaptureFixture[str]) -> Any:
    return read_envelope(capsys)


def test_status_json_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(make_repo(tmp_path / "repo"))
    assert main(["config", "status", "--json"]) == 0
    env = _json(capsys)
    assert env["ok"] is True
    assert env["data"]["clean"] is True
    assert env["warnings"] == []
    assert env["data"]["base"] == "main"


def test_status_json_with_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path / "repo")
    _dirty(repo)
    monkeypatch.chdir(repo)
    assert main(["config", "status", "--json"]) == 0
    env = _json(capsys)
    assert env["data"]["clean"] is False
    changes = env["data"]["changes"]
    assert isinstance(changes, list)
    assert {c["path"] for c in changes} == {".factory/agents.yaml", PLANNER_SYSTEM}
    warnings = "\n".join(env["warnings"])
    assert ".factory/agents.yaml" in warnings
    assert PLANNER_SYSTEM in warnings


def test_status_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path / "repo")
    monkeypatch.chdir(repo)
    assert main(["config", "status"]) == 0
    assert "config in sync with main" in capsys.readouterr().out
    _dirty(repo)
    assert main(["config", "status"]) == 0
    out = capsys.readouterr().out
    assert ".factory/agents.yaml" in out
    assert PLANNER_SYSTEM in out
    assert "runs use main" in out


def test_show_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, PLANNER_SYSTEM, "edited\n")
    monkeypatch.chdir(repo)
    assert main(["config", "show", "--json"]) == 0
    env = _json(capsys)
    assert env["ok"] is True
    data = env["data"]
    assert "warnings" not in data
    # tester and test-reviewer come from the seed
    assert data["agents"] == ["planner", "builder", "tester", "test-reviewer"]
    assert data["workflows"] == ["plan-build"]
    assert data["local"] == {"trace_db": ".factory/trace.db"}
    assert any(PLANNER_SYSTEM in w for w in env["warnings"])


def test_show_text_prints_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, PLANNER_SYSTEM, "edited\n")
    monkeypatch.chdir(repo)
    assert main(["config", "show"]) == 0
    captured = capsys.readouterr()
    assert "planner, builder" in captured.out
    assert f"warning: {PLANNER_SYSTEM}" in captured.err


def test_show_broken_committed_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path / "repo")
    write(repo, ".factory/agents.yaml", "agents: [\n")
    commit_all(repo, "broken agents")
    monkeypatch.chdir(repo)
    assert main(["config", "show", "--json"]) == 2
    data = _json(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "invalid_config"
    issues = data["error"]["issues"]
    assert isinstance(issues, list)
    assert "agents.yaml" in issues[0]["path"]
    assert main(["config", "status"]) == 0


def test_outside_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["config", "status", "--json"]) == 2
    assert _json(capsys)["ok"] is False
    assert main(["config", "show"]) == 2
    assert "factory config show" in capsys.readouterr().err


def test_config_without_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["config"]) == 0
    assert "status" in capsys.readouterr().out


def test_json_data_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(make_repo(tmp_path / "repo"))
    assert main(["config", "status", "--json"]) == 0
    assert set(_json(capsys)["data"]) == {"base", "commit", "clean", "changes"}
    assert main(["config", "show", "--json"]) == 0
    data = _json(capsys)["data"]
    assert {"base", "commit", "agents", "workflows"} <= set(data)
    assert "ok" not in data and "warnings" not in data
