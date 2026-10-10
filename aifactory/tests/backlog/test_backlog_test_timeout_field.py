"""The ``test_timeout`` field: whole seconds greater than 0, validated and inherited."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from backlog_repo import M01_S01, T01, rewrite, sample_repo

from aifactory.backlog import Task, effective_test_timeout, load_backlog
from aifactory.cli import main
from aifactory.config import check_timeout

Capsys = pytest.CaptureFixture[str]
MODULE_INDEX = "backlog/M01-core/index.md"
STEP_INDEX = f"{M01_S01}/index.md"
TASK_ID = "M01-S01-T01"


def _task(root: Path) -> Task:
    task = load_backlog(root).by_id[TASK_ID]
    assert isinstance(task, Task)
    return task


def _module_timeout(root: Path, value: int) -> None:
    old = "workflow: plan-build\n"
    rewrite(root / MODULE_INDEX, old, f"{old}test_timeout: {value}\n")


def _check(root: Path, capsys: Capsys) -> tuple[int, dict[str, Any]]:
    code = main(["backlog", "check", "--json", "--repo", str(root)])
    return code, json.loads(capsys.readouterr().out)


def test_check_timeout_accepts_positive_ints() -> None:
    assert check_timeout(1) == 1
    assert check_timeout(1800) == 1800


@pytest.mark.parametrize("value", [0, -1, "600", True, False, 1.5, None, [600]])
def test_check_timeout_rejects(value: object) -> None:
    with pytest.raises(ValueError):
        check_timeout(value)


def test_valid_values_pass_check(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / STEP_INDEX, "title: Model\n", "title: Model\ntest_timeout: 1800\n")
    rewrite(root / T01, "status: done\n", "status: done\ntest_timeout: 30\n")
    code, data = _check(root, capsys)
    assert code == 0
    assert data["ok"] is True
    assert data["data"]["issues"] == []


@pytest.mark.parametrize("value", ["0", "-1", '"600"', "true", "1.5"])
def test_invalid_task_timeout_is_reported(tmp_path: Path, capsys: Capsys, value: str) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / T01, "status: done\n", f"status: done\ntest_timeout: {value}\n")
    code, data = _check(root, capsys)
    assert code == 1
    assert data["ok"] is False
    [issue] = data["data"]["issues"]
    assert issue["code"] == "invalid_field"
    assert issue["path"] == T01
    assert "'test_timeout'" in issue["message"]
    # kept, so a run fails instead of falling back
    assert _task(root).own["test_timeout"] is not None


def test_invalid_index_timeout_is_reported(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / STEP_INDEX, "title: Model\n", "title: Model\ntest_timeout: 0\n")
    code, data = _check(root, capsys)
    assert code == 1
    [issue] = data["data"]["issues"]
    assert issue["code"] == "invalid_field"
    assert issue["path"] == STEP_INDEX
    assert "'test_timeout'" in issue["message"]
    assert effective_test_timeout(_task(root)) == 0


def test_effective_test_timeout_nearest_wins(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    assert effective_test_timeout(_task(root)) is None

    _module_timeout(root, 900)
    assert effective_test_timeout(_task(root)) == 900

    rewrite(root / STEP_INDEX, "title: Model\n", "title: Model\ntest_timeout: 1200\n")
    assert effective_test_timeout(_task(root)) == 1200

    rewrite(root / T01, "status: done\n", "status: done\ntest_timeout: 30\n")
    assert effective_test_timeout(_task(root)) == 30


def test_effective_test_timeout_skips_null(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    _module_timeout(root, 900)
    rewrite(root / STEP_INDEX, "title: Model\n", "title: Model\ntest_timeout: null\n")
    rewrite(root / T01, "status: done\n", "status: done\ntest_timeout:\n")
    assert effective_test_timeout(_task(root)) == 900
