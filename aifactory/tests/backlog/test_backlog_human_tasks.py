"""`assignee: human`: a person's task never runs, shows as `human` and only a person marks
it done; a task waiting for it says so."""

from __future__ import annotations

from pathlib import Path

import pytest
from backlog_repo import index_md, task_md, write

from aifactory.backlog import (
    Task,
    TaskEditError,
    check_backlog,
    derived_state,
    edit_task,
    is_human,
    load_backlog,
    task_to_json,
    waits_for,
    waits_for_human,
)

STEP = "backlog/M01-core/S01-model"
T01, T02 = "M01-S01-T01", "M01-S01-T02"


def make(root: Path, *, step_extra: str = "", t01_extra: str = "assignee: human\n") -> Path:
    write(root, ".factory/config.yaml", "docs_root: .\n")
    write(root, "backlog/M01-core/index.md", index_md("M01"))
    write(root, f"{STEP}/index.md", index_md("M01-S01", step_extra))
    write(root, f"{STEP}/{T01}-a.md", task_md(T01, extra=t01_extra))
    write(root, f"{STEP}/{T02}-b.md", task_md(T02, extra=f"depends_on: [{T01}]\n"))
    return root


def task(root: Path, task_id: str) -> Task:
    node = load_backlog(root).by_id[task_id]
    assert isinstance(node, Task)
    return node


def test_human_task_state_and_its_dependent(tmp_path: Path) -> None:
    root = make(tmp_path)
    backlog = load_backlog(root)
    human, dependent = task(root, T01), task(root, T02)

    assert is_human(human) and not is_human(dependent)
    assert derived_state(backlog, human) == "human"
    assert derived_state(backlog, dependent) == "blocked"
    assert waits_for_human(backlog, dependent) == [T01]
    assert "for a person: M01-S01-T01" in waits_for(backlog, dependent)
    data = task_to_json(backlog, dependent, {})
    assert data["assignee"] == "agent" and data["waits_for_human"] == [T01]


def test_assignee_is_inherited_and_validated(tmp_path: Path) -> None:
    root = make(tmp_path, step_extra="assignee: human\n", t01_extra="assignee: robot\n")
    issues = [i for i in check_backlog(load_backlog(root)) if i.code == "invalid_field"]
    assert [i.id for i in issues] == [T01]
    # the invalid own value is dropped: T01 inherits `human` from the step, like T02
    assert is_human(task(root, T01)) and is_human(task(root, T02))


def test_only_a_persons_task_is_marked_done(tmp_path: Path) -> None:
    root = make(tmp_path)
    with pytest.raises(TaskEditError) as caught:
        edit_task(root, T02, status="done")
    assert caught.value.code == "invalid_status"

    edit_task(root, T01, status="done")
    done = task(root, T01)
    assert done.status == "done" and "hotovo ručně" in done.body
    assert derived_state(load_backlog(root), task(root, T02)) == "ready"


def test_edit_sets_and_clears_assignee(tmp_path: Path) -> None:
    root = make(tmp_path, t01_extra="")
    edit_task(root, T02, assignee="human")
    assert is_human(task(root, T02))
    edit_task(root, T02, clear_assignee=True)
    assert not is_human(task(root, T02))
    with pytest.raises(TaskEditError):
        edit_task(root, T02, assignee="robot")
