"""Every `--json` command prints the one envelope; generated from the parser, so new
commands are covered without touching this file."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from aifactory.cli import build_parser, main
from aifactory.skill import (
    ERROR_CODES,
    CommandSpec,
    envelope_fail,
    envelope_ok,
    envelope_problems,
    iter_commands,
    strip_payload,
)
from cli_json import run_json

Capsys = pytest.CaptureFixture[str]

LEAVES = [spec for spec in iter_commands(build_parser()) if spec.has_json]
DUMMIES = {"ID": "X-T01", "STEP": "X", "TITLE": "t"}
SAMPLE = Path(__file__).parent / "backlog" / "fixtures" / "sample"


def _argv(spec: CommandSpec, tmp_path: Path) -> list[str]:
    argv = list(spec.path)
    for arg in spec.arguments:
        if arg.positional:
            name = arg.names[0]
            argv.append(
                str(tmp_path / "missing.yaml") if name == "FILE" else DUMMIES.get(name, "x")
            )
    groups: set[str] = set()
    for arg in spec.arguments:
        if arg.positional or not arg.required:
            continue
        if arg.group is not None:
            if arg.group in groups:
                continue
            groups.add(arg.group)
        argv.append(arg.names[0])
        if arg.takes_value:
            argv.append("n")
    argv.append("--json")
    if spec.has_repo:
        argv += ["--repo", str(tmp_path)]
    return argv


def test_every_leaf_has_json() -> None:
    specs = iter_commands(build_parser())
    assert specs and all(spec.has_json for spec in specs)


@pytest.mark.parametrize("spec", LEAVES, ids=lambda s: " ".join(s.path))
def test_command_prints_envelope(
    spec: CommandSpec, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    if spec.path == ("harness", "check"):
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    argv = _argv(spec, tmp_path)
    rc = main(argv)
    out = capsys.readouterr().out
    obj = json.loads(out)  # exactly one JSON document
    assert envelope_problems(obj) == [], (argv, obj)
    assert obj["ok"] == (rc == 0)
    if not obj["ok"]:
        assert obj["error"]["code"] in ERROR_CODES
        assert obj["error"]["code"] != "internal_error", obj


def test_usage_error_json(capsys: Capsys) -> None:
    rc, obj = run_json(capsys, ["task", "return", "X", "--json"])
    assert rc == 2
    assert obj["error"]["code"] == "usage_error"
    assert "--note" in obj["error"]["message"]


def test_usage_error_without_json_exits(capsys: Capsys) -> None:
    with pytest.raises(SystemExit) as info:
        main(["task", "return", "X"])
    assert info.value.code == 2
    assert "required: --note" in capsys.readouterr().err


def test_group_with_json_is_usage_error(capsys: Capsys) -> None:
    rc, obj = run_json(capsys, ["task", "--json"])
    assert rc == 2 and obj["error"]["code"] == "usage_error"


def test_internal_error_json(capsys: Capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    import aifactory.cli as cli

    def boom(args: argparse.Namespace) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "_task", boom)
    rc, obj = run_json(capsys, ["task", "list", "--json"])
    assert rc == 2
    assert obj["error"]["code"] == "internal_error"
    assert "boom" in obj["error"]["message"]
    with pytest.raises(RuntimeError):
        main(["task", "list"])


# ── success paths ────────────────────────────────────────────────────────────


def _ok(capsys: Capsys, argv: list[str]) -> dict[str, Any]:
    rc, obj = run_json(capsys, argv)
    assert rc == 0 and obj["ok"] is True, obj
    data = obj["data"]
    assert isinstance(data, dict)
    assert "ok" not in data and "warnings" not in data
    return data


def test_backlog_and_task_success(tmp_path: Path, capsys: Capsys) -> None:
    root = tmp_path / "repo"
    shutil.copytree(SAMPLE, root)
    repo = ["--repo", str(root)]
    assert set(_ok(capsys, ["backlog", "check", "--json", *repo])) == {"counts", "issues"}
    assert {"items", "filters", "issues"} <= set(_ok(capsys, ["backlog", "list", "--json", *repo]))
    assert set(_ok(capsys, ["task", "list", "--json", *repo])) == {"filters", "tasks", "issues"}
    shown = _ok(capsys, ["task", "show", "M01-S01-T02", "--json", *repo])
    assert set(shown) == {"task", "body", "issues", "runs", "prs"}
    added = _ok(capsys, ["task", "add", "M01-S01", "Nový", "--json", *repo])
    assert set(added) == {"action", "changed", "path", "task", "issues"}


def test_workflow_check_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Capsys
) -> None:
    from aifactory.workflow import DEFAULT_WORKFLOWS_DIR

    monkeypatch.chdir(tmp_path)
    data = _ok(capsys, ["workflow", "check", str(DEFAULT_WORKFLOWS_DIR / "plan.yaml"), "--json"])
    assert data["issues"] == [] and data["workflow"] == "plan"


# ── the envelope helpers ─────────────────────────────────────────────────────


def test_envelope_helpers() -> None:
    assert envelope_problems(envelope_ok({"a": 1}, ["w"])) == []
    fail = envelope_fail("unknown_task", "no task", id="X", issues=[{"code": "c", "message": "m"}])
    assert envelope_problems(fail) == []
    assert envelope_problems(envelope_fail("made_up", "x")) != []
    assert envelope_problems({"ok": True, "data": {}, "error": None}) != []
    assert envelope_problems({"ok": True, "data": {}, "error": None, "warnings": [1]}) != []
    assert envelope_problems([]) != []
    data, warnings = strip_payload({"ok": True, "x": 1, "warnings": ["w"]})
    assert data == {"x": 1} and warnings == ["w"]
