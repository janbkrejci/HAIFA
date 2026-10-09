"""The ``specs_dir``/``docs_dir`` fields: directories inside the repo, validated and inherited."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from backlog_repo import M01_S01, T01, rewrite, sample_repo

from aifactory.backlog import (
    Task,
    effective_docs_dir,
    effective_specs_dir,
    load_backlog,
)
from aifactory.cli import main
from aifactory.config import check_relative_dir

Capsys = pytest.CaptureFixture[str]
PROJECT_INDEX = "backlog/M01-core/index.md"
STEP_INDEX = f"{M01_S01}/index.md"
TASK_ID = "M01-S01-T01"


def _task(root: Path) -> Task:
    task = load_backlog(root).by_id[TASK_ID]
    assert isinstance(task, Task)
    return task


def _project(root: Path, extra: str) -> None:
    rewrite(root / PROJECT_INDEX, "title: Core\n", f"title: Core\n{extra}")


def _check(root: Path, capsys: Capsys) -> tuple[int, dict[str, Any]]:
    code = main(["backlog", "check", "--json", "--repo", str(root)])
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("value", ["docs/M07/specs", "specs", " docs/x ", "."])
def test_check_relative_dir_accepts(value: str) -> None:
    assert check_relative_dir(value) == value.strip()


@pytest.mark.parametrize("value", ["../x", "a/../../b", "/abs", "", "  ", 5, None, ["specs"]])
def test_check_relative_dir_rejects(value: object) -> None:
    with pytest.raises(ValueError):
        check_relative_dir(value)


def test_valid_values_pass_check(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    _project(root, "specs_dir: docs/M07/specs\ndocs_dir: docs/M07/app\n")
    rewrite(root / T01, "status: done\n", "status: done\nspecs_dir: docs/T\n")
    code, data = _check(root, capsys)
    assert code == 0
    assert data["data"]["issues"] == []


def test_project_dir_outside_repo_is_reported(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    _project(root, "specs_dir: ../x\n")
    code, data = _check(root, capsys)
    assert code == 1
    assert data["ok"] is False
    [issue] = data["data"]["issues"]
    assert issue["code"] == "invalid_field"
    assert issue["path"] == PROJECT_INDEX
    assert "'specs_dir'" in issue["message"]
    # kept, so a run fails instead of falling back to the config
    assert effective_specs_dir(_task(root)) == "../x"


@pytest.mark.parametrize("value", ["/abs", "5", "''", "[docs]"])
def test_invalid_task_dir_is_reported(tmp_path: Path, capsys: Capsys, value: str) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / T01, "status: done\n", f"status: done\ndocs_dir: {value}\n")
    code, data = _check(root, capsys)
    assert code == 1
    [issue] = data["data"]["issues"]
    assert issue["code"] == "invalid_field"
    assert issue["path"] == T01
    assert "'docs_dir'" in issue["message"]
    assert _task(root).own["docs_dir"] is not None


def test_nearest_dir_wins(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    assert effective_specs_dir(_task(root)) is None
    assert effective_docs_dir(_task(root)) is None

    _project(root, "specs_dir: docs/M07/specs\ndocs_dir: docs/M07/app\n")
    assert effective_specs_dir(_task(root)) == "docs/M07/specs"
    assert effective_docs_dir(_task(root)) == "docs/M07/app"

    rewrite(root / STEP_INDEX, "title: Model\n", "title: Model\nspecs_dir: docs/S01\n")
    assert effective_specs_dir(_task(root)) == "docs/S01"
    assert effective_docs_dir(_task(root)) == "docs/M07/app"

    rewrite(root / T01, "status: done\n", "status: done\nspecs_dir: docs/T\ndocs_dir: null\n")
    assert effective_specs_dir(_task(root)) == "docs/T"
    assert effective_docs_dir(_task(root)) == "docs/M07/app"
