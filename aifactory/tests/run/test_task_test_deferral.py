"""Aggregate test targets are checked before agents run."""

from __future__ import annotations

from pathlib import Path

import pytest
from run_repo import T01, T02, make_run_repo, write

from aifactory.backlog import Task, load_backlog
from aifactory.config import WorktreeSource, load_config
from aifactory.run import TaskRunError
from aifactory.run.task import resolve_workflow, validate_test_deferrals


def setup(tmp_path: Path, target: str = T02) -> tuple[Path, Task]:
    root = make_run_repo(tmp_path / "repo")
    write(
        root,
        ".factory/workflows/adaptive.yaml",
        f"""name: adaptive
description: Select focused checks for development
steps:
  - test:
      selector: [selector]
      full_argv: [just, check]
      defer_to: {target}
""",
    )
    write(
        root,
        ".factory/workflows/aggregate.yaml",
        "name: aggregate\ndescription: Verify the entire module\nsteps: [test]\n",
    )
    write(
        root,
        "backlog/M01-core/S01-model/M01-S01-T01-schema.md",
        f"""---
id: {T01}
title: Dev
status: todo
workflow: adaptive
---
""",
    )
    write(
        root,
        "backlog/M01-core/S01-model/M01-S01-T02-loader.md",
        f"""---
id: {T02}
title: Aggregate
status: todo
workflow: aggregate
test: just check
---
""",
    )
    cfg = load_config(WorktreeSource(root))
    backlog = load_backlog(root, cfg.settings)
    task = backlog.by_id[T01]
    assert isinstance(task, Task)
    return root, task


def test_valid_aggregate(tmp_path: Path) -> None:
    root, task = setup(tmp_path)
    cfg = load_config(WorktreeSource(root))
    backlog = load_backlog(root, cfg.settings)
    assert validate_test_deferrals(resolve_workflow(task, cfg), task, backlog, cfg) == (T02,)


@pytest.mark.parametrize("problem", ["missing", "self", "done", "command", "nested", "project"])
def test_invalid_target(tmp_path: Path, problem: str) -> None:
    target = "MISSING" if problem == "missing" else T01 if problem == "self" else T02
    root, task = setup(tmp_path, target)
    cfg = load_config(WorktreeSource(root))
    backlog = load_backlog(root, cfg.settings)
    other = backlog.by_id[T02]
    assert isinstance(other, Task)
    if problem == "done":
        other.status = "done"
    elif problem == "command":
        other.own["test"] = "just test"
    elif problem == "nested":
        other.own["workflow"] = "adaptive"
    elif problem == "project":
        from aifactory.backlog.model import Container

        other.parent = Container("M02", "Other", "project", "backlog/M02")
    with pytest.raises(TaskRunError, match="invalid_test_deferral"):
        validate_test_deferrals(resolve_workflow(task, cfg), task, backlog, cfg)
