"""`factory workflow check <file> [--json]`: validation against roles and agents, no run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from workflow_fakes import make_factory_repo

from aifactory.cli import main
from cli_json import read_envelope

HEADER = "name: demo\ndescription: A workflow written only to exercise the check command\n"
PLAN_BUILD = (
    HEADER + "steps:\n  - plan\n  - build: {model: opus}\naccept: build.status == 'success'\n"
)


def _json(capsys: pytest.CaptureFixture[str]) -> Any:
    return read_envelope(capsys)


def _repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> Path:
    repo = make_factory_repo(tmp_path / "repo")
    path = repo / "wf.yaml"
    path.write_text(text, encoding="utf-8", newline="\n")
    monkeypatch.chdir(repo)
    return path


def test_valid_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _repo(tmp_path, monkeypatch, PLAN_BUILD)
    assert main(["workflow", "check", str(path)]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("OK: demo (2 steps)")
    assert "warning" not in captured.err


def test_valid_workflow_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _repo(tmp_path, monkeypatch, PLAN_BUILD)
    assert main(["workflow", "check", str(path), "--json"]) == 0
    env = _json(capsys)
    assert env["ok"] is True
    assert env["warnings"] == []
    data = env["data"]
    assert data["workflow"] == "demo"
    assert data["issues"] == []
    assert [s["step"] for s in data["steps"]] == ["plan", "build"]
    assert data["steps"][1]["model"] == "opus"
    assert data["roles"] == "packaged defaults"
    assert data["agents"] == ".factory/agents.yaml"


def test_roles_from_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _repo(tmp_path, monkeypatch, PLAN_BUILD)
    from aifactory.engine.role_registry import DEFAULT_ROLES_PATH

    roles = DEFAULT_ROLES_PATH.read_text(encoding="utf-8").replace("  build:", "  construct:")
    (path.parent / ".factory" / "roles.yaml").write_text(roles, encoding="utf-8", newline="\n")
    assert main(["workflow", "check", str(path), "--json"]) == 1
    env = _json(capsys)
    assert env["error"]["code"] == "workflow_invalid"
    data = env["data"]
    assert data["roles"] == ".factory/roles.yaml"
    # the project registry renamed `build`, so the workflow no longer knows it
    errors = [(e["code"], e["path"]) for e in data["issues"]]
    assert ("unknown_step", "steps[1].build") in errors


def test_agent_missing_from_roster(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _repo(tmp_path, monkeypatch, HEADER + "steps: [plan, build, review]\n")
    assert main(["workflow", "check", str(path)]) == 1
    out = capsys.readouterr().out
    assert "unknown_agent" in out
    assert "'reviewer'" in out
    assert "1 error(s)" in out


def test_invalid_override_for_the_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _repo(tmp_path, monkeypatch, HEADER + "steps:\n  - build: {model: gpt-5.5}\n")
    assert main(["workflow", "check", str(path), "--json"]) == 1
    errors = _json(capsys)["error"]["issues"]
    assert [(e["code"], e["path"]) for e in errors] == [("invalid_agent", "steps[0].build")]


def test_every_problem_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    text = HEADER + (
        "steps:\n  - deploy\n  - repeat: {until: test.approved}\n    steps: [test, fix]\n"
    )
    path = _repo(tmp_path, monkeypatch, text)
    assert main(["workflow", "check", str(path), "--json"]) == 1
    data = _json(capsys)
    assert data["ok"] is False
    codes = {e["code"] for e in data["data"]["issues"]}
    assert {"unknown_step", "unknown_field", "missing_max"} <= codes


def test_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo(tmp_path, monkeypatch, PLAN_BUILD)
    assert main(["workflow", "check", "nope.yaml", "--json"]) == 1
    assert [e["code"] for e in _json(capsys)["data"]["issues"]] == ["missing_file"]


def test_outside_a_factory_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "wf.yaml"
    path.write_text(HEADER + "steps: [plan, build, review]\n", encoding="utf-8", newline="\n")
    monkeypatch.chdir(tmp_path)
    assert main(["workflow", "check", str(path)]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("OK: demo")
    assert "warning: agents not checked" in captured.err


def test_agents_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "wf.yaml"
    path.write_text(HEADER + "steps: [plan, review]\n", encoding="utf-8", newline="\n")
    roster = tmp_path / "agents.yaml"
    roster.write_text(
        "defaults: {harness: claude, model: sonnet}\n"
        "agents:\n"
        "  - name: planner\n"
        "    prompt_engineering: {system: s.md, user: u.md}\n",
        encoding="utf-8",
        newline="\n",
    )
    monkeypatch.chdir(tmp_path)
    assert main(["workflow", "check", str(path), "--agents", str(roster), "--json"]) == 1
    data = _json(capsys)["data"]
    assert data["agents"] == str(roster)
    assert [e["code"] for e in data["issues"]] == ["unknown_agent"]


def test_invalid_roles_file_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "wf.yaml"
    path.write_text(PLAN_BUILD, encoding="utf-8", newline="\n")
    roles = tmp_path / "roles.yaml"
    roles.write_text("roles: [\n", encoding="utf-8", newline="\n")
    monkeypatch.chdir(tmp_path)
    assert main(["workflow", "check", str(path), "--roles", str(roles), "--json"]) == 2
    data = _json(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "invalid_roles"
    assert [i["code"] for i in data["error"]["issues"]] == ["invalid_yaml"]
    assert main(["workflow", "check", str(path), "--roles", str(roles)]) == 2
    assert "factory workflow check:" in capsys.readouterr().err


def test_no_subcommand_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["workflow"]) == 0
    assert "check" in capsys.readouterr().out


def test_unknown_step_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    text = HEADER + "steps:\n  - plan\n  - build: {agent: ghost}\n"
    path = _repo(tmp_path, monkeypatch, text)
    assert main(["workflow", "check", str(path), "--json"]) == 1
    errors = _json(capsys)["error"]["issues"]
    assert [(e["code"], e["path"]) for e in errors] == [("unknown_agent", "steps[1].build.agent")]


OVERLAY = """\
roles:
  audit:
    agent: planner
    output_type: GenericOutput
    gates: []
    description: Audit the change against the security checklist
"""


def test_roles_overlay_and_step_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    text = HEADER + "steps:\n  - plan\n  - audit\n  - build: {agent: planner}\n"
    path = _repo(tmp_path, monkeypatch, text)
    (path.parent / ".factory" / "roles.yaml").write_text(OVERLAY, encoding="utf-8", newline="\n")
    assert main(["workflow", "check", str(path), "--json"]) == 0
    data = _json(capsys)["data"]
    assert data["roles"] == ".factory/roles.yaml"
    assert [(s["step"], s["agent"]) for s in data["steps"]] == [
        ("plan", "planner"),
        ("audit", "planner"),
        ("build", "planner"),
    ]
