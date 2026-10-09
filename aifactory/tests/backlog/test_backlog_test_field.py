"""The ``test`` field: a command string or a list of strings, validated and inherited."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from backlog_repo import M01_S01, T01, rewrite, sample_repo

from aifactory.backlog import Task, effective_test, load_backlog
from aifactory.cli import main
from aifactory.config import split_command

Capsys = pytest.CaptureFixture[str]
MODULE_INDEX = "backlog/M01-core/index.md"
STEP_INDEX = f"{M01_S01}/index.md"
TASK_ID = "M01-S01-T01"


def _task(root: Path) -> Task:
    task = load_backlog(root).by_id[TASK_ID]
    assert isinstance(task, Task)
    return task


def _check(root: Path, capsys: Capsys) -> tuple[int, dict[str, Any]]:
    code = main(["backlog", "check", "--json", "--repo", str(root)])
    return code, json.loads(capsys.readouterr().out)


def test_split_command_string_like_a_shell() -> None:
    assert split_command("uv run 'a b'") == ("uv", "run", "a b")
    assert split_command(["just", "check"]) == ("just", "check")


@pytest.mark.parametrize("value", ["", "   ", [], [""], ["just", " "], [1], 5, None, "a 'b"])
def test_split_command_rejects(value: object) -> None:
    with pytest.raises(ValueError):
        split_command(value)


def test_valid_values_pass_check(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / STEP_INDEX, "title: Model\n", "title: Model\ntest: [just, check]\n")
    rewrite(root / T01, "status: done\n", 'status: done\ntest: "uv run pytest -q"\n')
    code, data = _check(root, capsys)
    assert code == 0
    assert data["ok"] is True
    assert data["data"]["issues"] == []


def test_invalid_task_test_is_reported(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / T01, "status: done\n", "status: done\ntest: 5\n")
    code, data = _check(root, capsys)
    assert code == 1
    assert data["ok"] is False
    [issue] = data["data"]["issues"]
    assert issue["code"] == "invalid_field"
    assert issue["path"] == T01
    assert "'test'" in issue["message"]
    assert _task(root).own["test"] == 5  # kept, so a run fails instead of falling back


def test_invalid_index_test_is_reported(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / STEP_INDEX, "title: Model\n", "title: Model\ntest: []\n")
    code, data = _check(root, capsys)
    assert code == 1
    [issue] = data["data"]["issues"]
    assert issue["code"] == "invalid_field"
    assert issue["path"] == STEP_INDEX
    assert "'test'" in issue["message"]
    assert effective_test(_task(root)) == []


def test_effective_test_nearest_wins(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    assert effective_test(_task(root)) == "uv run pytest"  # from the module

    rewrite(root / STEP_INDEX, "title: Model\n", "title: Model\ntest: [just, check]\n")
    assert effective_test(_task(root)) == ["just", "check"]

    rewrite(root / T01, "status: done\n", 'status: done\ntest: "pytest -q"\n')
    assert effective_test(_task(root)) == "pytest -q"


def test_effective_test_skips_null(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / STEP_INDEX, "title: Model\n", "title: Model\ntest: null\n")
    rewrite(root / T01, "status: done\n", "status: done\ntest:\n")
    assert effective_test(_task(root)) == "uv run pytest"


def test_effective_test_none_when_unset(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / MODULE_INDEX, 'test: "uv run pytest"\n', "")
    assert effective_test(_task(root)) is None
