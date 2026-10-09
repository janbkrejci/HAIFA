"""`workflow: null` on a project, step or task means "no workflow", even under a workflow."""

from __future__ import annotations

from pathlib import Path

import pytest
from backlog_repo import index_md, task_md, write

from aifactory.backlog import Task, effective_workflow, has_workflow, load_backlog

TASK = "M01-S01-T01"


def _key(value: str | None) -> str:
    """Frontmatter line for `workflow`: absent (""), `null` ("null") or a name."""
    return "" if value == "" else f"workflow: {value}\n"


@pytest.mark.parametrize(
    ("project", "step", "task", "expected"),
    [
        ("wf-a", "", "", "wf-a"),
        ("wf-a", "null", "", None),
        ("wf-a", "wf-b", "null", None),
        ("wf-a", "null", "wf-c", "wf-c"),
        ("null", "wf-b", "", "wf-b"),
        ("null", "", "", None),
        ("", "", "", None),
    ],
)
def test_nearest_workflow_wins(
    tmp_path: Path, project: str, step: str, task: str, expected: str | None
) -> None:
    write(tmp_path, "backlog/M01-core/index.md", index_md("M01", _key(project)))
    write(tmp_path, "backlog/M01-core/S01-model/index.md", index_md("M01-S01", _key(step)))
    write(
        tmp_path,
        f"backlog/M01-core/S01-model/{TASK}-x.md",
        task_md(TASK, extra=_key(task)),
    )
    node = load_backlog(tmp_path).by_id[TASK]
    assert isinstance(node, Task)
    assert effective_workflow(node) == expected
    assert has_workflow(node) is (expected is not None)
