from copy import deepcopy

import pytest

from aifactory.backlog.derived import harness_values
from aifactory.backlog.model import Container, Task
from aifactory.run.task import task_harness_values


@pytest.mark.parametrize(
    ("nearer", "expected"),
    [
        ({}, {"harness": "codex", "model": "project-model", "thinking": "high"}),
        ({"harness": "claude"}, {"harness": "claude", "thinking": "high"}),
        (
            {"harness": "claude", "model": "sonnet"},
            {"harness": "claude", "model": "sonnet", "thinking": "high"},
        ),
        ({"harness": "codex"}, {"harness": "codex", "model": "project-model", "thinking": "high"}),
        (
            {"model": "nearer-model", "thinking": "low"},
            {"harness": "codex", "model": "nearer-model", "thinking": "low"},
        ),
        (
            {"harness": None, "model": "", "thinking": None},
            {"harness": "codex", "model": "project-model", "thinking": "high"},
        ),
    ],
)
def test_container_and_task_inherit_the_same_binding(
    nearer: dict[str, object], expected: dict[str, object]
) -> None:
    original = {"harness": "codex", "model": "project-model", "thinking": "high"}
    root = Container("root", "Root", "root", "root", defaults=dict(original))
    project = Container("P", "Project", "project", "P", defaults=nearer, parent=root)
    step = Container("S", "Step", "step", "P/S", parent=project)
    task = Task("T", "Task", "todo", "task", "P/S/T.md", step)
    before = deepcopy([root.defaults, project.defaults, step.defaults, task.own])
    for node in (project, step, task):
        assert harness_values(node) == expected
    assert task_harness_values(task) == expected
    assert [root.defaults, project.defaults, step.defaults, task.own] == before
    step.defaults = {"harness": "pi", "model": "provider/model"}
    task.own = {"harness": "codex"}
    assert harness_values(step) == {
        "harness": "pi",
        "model": "provider/model",
        "thinking": expected["thinking"],
    }
    assert task_harness_values(task) == {"harness": "codex", "thinking": expected["thinking"]}
