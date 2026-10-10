"""`factory backlog check` and `factory backlog list`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from backlog_repo import T01, T02, rewrite, sample_repo, write

from aifactory.cli import main
from cli_json import read_envelope

Capsys = pytest.CaptureFixture[str]


def _json(capsys: Capsys) -> Any:
    return read_envelope(capsys)


def test_bare_backlog_prints_help(capsys: Capsys) -> None:
    assert main(["backlog"]) == 0
    assert "check" in capsys.readouterr().out


def test_check_ok(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    assert main(["backlog", "check", "--repo", str(root)]) == 0
    assert capsys.readouterr().out == "OK: 2 module, 3 step, 6 task\n"
    assert main(["backlog", "check", "--json", "--repo", str(root)]) == 0
    data = _json(capsys)
    assert data == {
        "ok": True,
        "data": {"counts": {"module": 2, "step": 3, "task": 6}, "issues": []},
        "error": None,
        "warnings": [],
    }


def test_check_accepts_legacy_owner(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    assert "owner: alice" in (root / "backlog/M01-core/index.md").read_text(encoding="utf-8")
    rewrite(root / T02, "status: todo", "status: todo\nowner: bob")
    assert main(["backlog", "check", "--json", "--repo", str(root)]) == 0
    data = _json(capsys)
    assert data["ok"] is True
    assert data["data"]["issues"] == []
    assert data["warnings"] == []


def test_check_errors(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / T02, "id: M01-S01-T02", "id: M01-S01-T01")
    assert main(["backlog", "check", "--repo", str(root)]) == 1
    out = capsys.readouterr().out
    assert f"{T02}: duplicate_id: " in out
    assert out.rstrip().endswith("error(s)")
    assert main(["backlog", "check", "--json", "--repo", str(root)]) == 1
    data = _json(capsys)
    assert data["ok"] is False
    assert data["error"]["code"] == "backlog_invalid"
    assert [e["path"] for e in data["data"]["issues"]] == [T02]
    assert all(e["path"].endswith(".md") for e in data["data"]["issues"])
    assert data["error"]["issues"] == data["data"]["issues"]
    assert T01 != T02


def test_invalid_config(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    write(root, ".factory/config.yaml", "levels: [x]\n")
    for command in ("check", "list"):
        assert main(["backlog", command, "--repo", str(root)]) == 2
        assert f"factory backlog {command}: " in capsys.readouterr().err
        assert main(["backlog", command, "--json", "--repo", str(root)]) == 2
        data = _json(capsys)
        assert data["ok"] is False
        assert data["error"]["code"] == "invalid_config"
        assert data["error"]["issues"][0]["path"].endswith("config.yaml")


def test_list(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    assert main(["backlog", "list", "--repo", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "M01-S01-T02 Loader  ready" in captured.out
    assert "M02-S01-T02 Filter  blocked" in captured.out


def test_list_filters(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    assert main(["backlog", "list", "--repo", str(root), "--status", "blocked"]) == 0
    out = capsys.readouterr().out
    assert "M01-S02-T01" in out and "M02-S01-T02" in out
    assert "Loader" not in out and "View" not in out

    assert main(["backlog", "list", "--repo", str(root), "--project", "M01"]) == 0
    out = capsys.readouterr().out
    assert "M01 Core" in out
    assert "M02 UI" not in out and "M02-S01 List" not in out

    args = ["backlog", "list", "--repo", str(root), "--project", "M02-ui", "--status", "ready"]
    assert main(args) == 0
    lines = [line.strip() for line in capsys.readouterr().out.splitlines()]
    assert lines == [
        "M02 UI  [0/2]",
        "M02-S01 List  [0/2]",
        "M02-S01-T01 View  ready  (blocks: M02-S01-T02)",
    ]


def test_list_json(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    args = ["backlog", "list", "--json", "--repo", str(root), "--status", "ready"]
    assert main([*args, "--project", "M01"]) == 0
    env = _json(capsys)
    assert env["ok"] is True
    data = env["data"]
    assert data["filters"] == {"status": "ready", "project": "M01"}
    [m01] = data["items"]
    assert [c["id"] for c in m01["children"]] == ["M01-S01"]


def test_list_unknown_project(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    assert main(["backlog", "list", "--repo", str(root), "--project", "M9"]) == 2
    assert "unknown module 'M9'" in capsys.readouterr().err
    assert main(["backlog", "list", "--json", "--repo", str(root), "--project", "M9"]) == 2
    assert _json(capsys)["error"]["code"] == "unknown_project"


def test_list_missing_backlog_dir_is_created(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    write(root, ".factory/config.yaml", "backlog_dir: nowhere\n")
    assert main(["backlog", "list", "--repo", str(root)]) == 0
    assert "not found" not in capsys.readouterr().err
    assert (root / "nowhere").is_dir()
    assert main(["backlog", "list", "--json", "--repo", str(root)]) == 0
    assert _json(capsys)["ok"] is True


def test_list_with_problems_warns(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / T02, "status: todo", "status: running")
    assert main(["backlog", "list", "--repo", str(root)]) == 0
    captured = capsys.readouterr()
    assert "M01-S01-T02 Loader  invalid (status: 'running')" in captured.out
    assert "1 problem(s), run 'factory backlog check'" in captured.err


def test_without_repo_uses_cwd(
    tmp_path: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = sample_repo(tmp_path)
    monkeypatch.chdir(root)
    assert main(["backlog", "check"]) == 0
    assert "OK: 2 module" in capsys.readouterr().out
