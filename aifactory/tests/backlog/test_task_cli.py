"""`factory task add|edit|link|show|list`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from backlog_repo import M01_S01, T01, sample_repo, write

from aifactory.cli import main
from cli_json import read_envelope

Capsys = pytest.CaptureFixture[str]


def _json(capsys: Capsys) -> Any:
    return read_envelope(capsys)


def _snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_bare_task_prints_help(capsys: Capsys) -> None:
    assert main(["task"]) == 0
    out = capsys.readouterr().out
    assert "add" in out
    assert "error codes" in out


def test_add_text_and_json(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    repo = ["--repo", str(root)]
    assert main(["task", "add", "M01-S01", "Nový task", *repo]) == 0
    rel = f"{M01_S01}/M01-S01-T03-novy-task.md"
    assert capsys.readouterr().out == f"added M01-S01-T03 {rel}\n"
    second = ["task", "add", "M01-S01", "Druhý", "--depends-on", "M01-S01-T03", "--json"]
    assert main([*second, *repo]) == 0
    env = _json(capsys)
    assert env["ok"] is True
    data = env["data"]
    assert data["action"] == "add"
    assert data["changed"] is True
    assert data["task"]["id"] == "M01-S01-T04"
    assert data["task"]["state"] == "blocked"
    assert data["path"] == f"{M01_S01}/M01-S01-T04-druhy.md"


def test_edit_and_link(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    repo = ["--repo", str(root)]
    assert main(["task", "edit", "M01-S01-T02", "--title", "Nový", "--writes", *repo]) == 0
    assert capsys.readouterr().out.startswith("updated M01-S01-T02 ")
    assert main(["task", "edit", "M01-S01-T02", "--title", "Nový", "--json", *repo]) == 0
    data = _json(capsys)["data"]
    assert data["changed"] is False
    assert data["task"]["writes"] == []
    assert main(["task", "link", "M01-S01-T02", "--related", "M02-S01-T01", "--json", *repo]) == 0
    data = _json(capsys)["data"]
    assert data["action"] == "link"
    assert data["task"]["related"] == ["M02-S01-T01"]
    assert data["task"]["state"] == "ready"
    assert main(["task", "link", "M01-S01-T02", "--related", "M02-S01-T01", *repo]) == 0
    assert capsys.readouterr().out == "unchanged M01-S01-T02\n"


def test_errors(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    repo = ["--repo", str(root)]
    before = _snapshot(root)
    cycle = ["task", "link", "M01-S01-T01", "--depends-on", "M01-S01-T02", *repo]
    assert main([*cycle, "--json"]) == 1
    data = _json(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "backlog_invalid"
    assert data["error"]["issues"][0]["code"] == "cycle"
    assert data["error"]["issues"][0]["path"] == T01
    assert main(cycle) == 1
    err = capsys.readouterr().err
    assert err.startswith("factory task link: ")
    assert ": cycle: " in err
    assert main(["task", "show", "NOPE", "--json", *repo]) == 2
    assert _json(capsys)["error"]["code"] == "unknown_task"
    assert main(["task", "edit", "M01-S01-T02", "--status", "done", "--json", *repo]) == 2
    assert _json(capsys)["error"]["code"] == "invalid_status"
    edit = ["task", "edit", "M01-S01-T02", "--workflow", "a", "--clear-workflow", "--json"]
    assert main([*edit, *repo]) == 2
    assert _json(capsys)["error"]["code"] == "conflicting_options"
    assert main(["task", "add", "M09-S01", "X", "--json", *repo]) == 2
    assert _json(capsys)["error"]["code"] == "unknown_step"
    assert _snapshot(root) == before


def test_show(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    repo = ["--repo", str(root)]
    assert main(["task", "show", "M01-S01-T02", *repo]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "state     ready" in lines
    assert "depends   M01-S01-T01 (done)" in lines
    assert "## Zadání" in lines
    assert main(["task", "show", "M01-S02-T01", *repo]) == 0
    out = capsys.readouterr().out
    assert "depends   M01-S01 (1/2)" in out
    assert "waits for M01-S01 [M01-S01-T02]" in out
    assert main(["task", "show", "M01-S01-T02", "--json", *repo]) == 0
    env = _json(capsys)
    assert env["ok"] is True
    assert env["data"]["task"]["state"] == "ready"
    assert "Načíst data" in env["data"]["body"]


def _ids(capsys: Capsys) -> list[str]:
    return [line.split()[0] for line in capsys.readouterr().out.splitlines()]


def test_list(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    repo = ["--repo", str(root)]
    assert main(["task", "list", *repo]) == 0
    assert len(_ids(capsys)) == 6
    assert main(["task", "list", "--status", "ready", *repo]) == 0
    assert _ids(capsys) == ["M01-S01-T02", "M02-S01-T01"]
    assert main(["task", "list", "--step", "M02-S01", *repo]) == 0
    assert _ids(capsys) == ["M02-S01-T01", "M02-S01-T02"]
    assert main(["task", "list", "--project", "M02", *repo]) == 0
    assert _ids(capsys) == ["M02-S01-T01", "M02-S01-T02"]
    assert main(["task", "list", "--status", "blocked", "--json", *repo]) == 0
    env = _json(capsys)
    assert env["ok"] is True
    assert [t["id"] for t in env["data"]["tasks"]] == ["M01-S02-T01", "M02-S01-T02"]
    for args, code in (
        (["--status", "bogus"], "invalid_status"),
        (["--project", "nope"], "unknown_project"),
        (["--step", "M01"], "unknown_step"),
    ):
        assert main(["task", "list", *args, "--json", *repo]) == 2
        assert _json(capsys)["error"]["code"] == code


def test_invalid_config(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    write(root, ".factory/config.yaml", "levels: [x]\n")
    assert main(["task", "list", "--json", "--repo", str(root)]) == 2
    data = _json(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "invalid_config"
    assert main(["task", "add", "M01-S01", "X", "--repo", str(root)]) == 2
    assert "factory task add: " in capsys.readouterr().err
