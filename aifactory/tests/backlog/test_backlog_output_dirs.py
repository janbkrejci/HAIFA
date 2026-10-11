"""``docs_root``: one folder setting; old folder keys in config and backlog are ignored."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from backlog_repo import M01_S01, T01, rewrite, sample_repo

from aifactory.backlog import Task, load_backlog
from aifactory.cli import main
from aifactory.config import ProjectSettings, check_relative_dir
from aifactory.run.scope import output_paths

Capsys = pytest.CaptureFixture[str]
PROJECT_INDEX = "backlog/M01-core/index.md"
STEP_INDEX = f"{M01_S01}/index.md"
TASK_ID = "M01-S01-T01"


def _task(root: Path) -> Task:
    task = load_backlog(root).by_id[TASK_ID]
    assert isinstance(task, Task)
    return task


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


def test_folders_derive_from_docs_root() -> None:
    default = ProjectSettings()
    assert default.docs_root == "factory"
    assert (default.backlog_dir, default.specs_dir, default.docs_dir) == (
        "factory/backlog",
        "factory/specs",
        "factory/docs",
    )
    nested = ProjectSettings(docs_root="./work/factory/")
    assert nested.docs_root == "work/factory"
    assert nested.backlog_dir == "work/factory/backlog"
    top = ProjectSettings(docs_root=".")
    assert (top.backlog_dir, top.specs_dir, top.docs_dir) == ("backlog", "specs", "docs")


@pytest.mark.parametrize("value", ["../x", "/abs", ""])
def test_docs_root_must_stay_in_the_repo(value: str) -> None:
    with pytest.raises(ValueError):
        ProjectSettings(docs_root=value)


def test_old_config_keys_are_dropped() -> None:
    settings = ProjectSettings.model_validate(
        {"backlog_dir": "x", "backlog_dirs": ["a/*"], "specs_dir": "s", "docs_dir": "d"}
    )
    assert settings.backlog_dir == "factory/backlog"
    assert settings.specs_dir == "factory/specs"


def test_old_backlog_keys_are_ignored(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / PROJECT_INDEX, "title: Core\n", "title: Core\nspecs_dir: ../x\nworkdir: /a\n")
    rewrite(root / STEP_INDEX, "title: Model\n", "title: Model\nworkdir: sub\n")
    rewrite(root / T01, "status: done\n", "status: done\ndocs_dir: 5\nworkdir: x\n")
    code, data = _check(root, capsys)
    assert code == 0
    assert data["data"]["issues"] == []
    task = _task(root)
    assert "docs_dir" not in task.own
    settings = ProjectSettings(docs_root=".")
    paths = output_paths(task, settings)
    assert paths.spec == "specs/M01-core/S01-model/M01-S01-T01-schema.md"
    assert paths.doc == "docs/M01-core/S01-model/M01-S01-T01-schema.md"
