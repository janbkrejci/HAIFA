"""Loading the tree: levels, inheritance, derived states, reverse links."""

from __future__ import annotations

from pathlib import Path

import pytest
from backlog_repo import (
    DOCS,
    ENDPOINT,
    FIXTURE,
    T02,
    index_md,
    rewrite,
    sample_repo,
    task_md,
    write,
)

from aifactory.backlog import (
    Container,
    Task,
    blocks,
    check_backlog,
    counts,
    derived_state,
    effective,
    effective_workflow,
    effective_writes,
    is_done,
    iter_tasks,
    load_backlog,
    load_settings,
    unmet,
)
from aifactory.config import ConfigError


def _task(backlog_id: str, root: Path = FIXTURE) -> Task:
    node = load_backlog(root).by_id[backlog_id]
    assert isinstance(node, Task)
    return node


def test_sample_counts_and_no_issues() -> None:
    backlog = load_backlog(FIXTURE)
    assert counts(backlog) == {"module": 2, "step": 3, "task": 6}
    assert check_backlog(backlog) == []
    assert [c.id for c in backlog.containers] == ["M01", "M02"]
    m01 = backlog.containers[0]
    assert m01.level == "module"
    assert m01.index_path == "backlog/M01-core/index.md"
    assert [c.level for c in m01.children] == ["step", "step"]
    assert {t.level for t in iter_tasks(backlog)} == {"task"}


def test_inheritance() -> None:
    backlog = load_backlog(FIXTURE)
    loader = backlog.by_id["M01-S01-T02"]
    assert isinstance(loader, Task)
    eff = effective(loader)
    # `owner` in the module index is a legacy field and is not inherited
    assert "owner" not in eff
    assert eff["source"] == "src/"
    assert eff["target"] == "src/"
    # the task's own workflow beats the module's
    assert effective_workflow(loader) == "plan-build-test-review"
    assert effective_writes(loader) == ["src/"]
    assert loader.writes == []

    endpoint = backlog.by_id["M01-S02-T01"]
    assert isinstance(endpoint, Task)
    # the step overrides the module
    assert effective_workflow(endpoint) == "plan-build-test"
    # own writes override inherited ones
    assert effective_writes(endpoint) == ["src/api/"]

    schema = backlog.by_id["M01-S01-T01"]
    assert isinstance(schema, Task)
    assert effective_workflow(schema) == "plan-build"

    view = backlog.by_id["M02-S01-T01"]
    assert isinstance(view, Task)
    assert "owner" not in effective(view)
    # no level sets writes: the default, the whole repo
    assert effective_writes(view) == ["**"]


def test_derived_states() -> None:
    backlog = load_backlog(FIXTURE)
    states = {t.id: derived_state(backlog, t) for t in iter_tasks(backlog)}
    assert states == {
        "M01-S01-T01": "done",
        "M01-S01-T02": "ready",
        "M01-S02-T01": "blocked",
        "M01-S02-T02": "cancelled",
        "M02-S01-T01": "ready",
        "M02-S01-T02": "blocked",
    }
    endpoint = backlog.by_id["M01-S02-T01"]
    assert isinstance(endpoint, Task)
    [reason] = unmet(backlog, endpoint)
    assert (reason.id, reason.reason, reason.missing) == ("M01-S01", "incomplete", ["M01-S01-T02"])


def test_step_done_when_all_tasks_done(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    assert not is_done(load_backlog(root).by_id["M01-S01"])
    rewrite(root / T02, "status: todo", "status: done")
    backlog = load_backlog(root)
    assert is_done(backlog.by_id["M01-S01"])
    endpoint = backlog.by_id["M01-S02-T01"]
    assert isinstance(endpoint, Task)
    assert derived_state(backlog, endpoint) == "ready"
    # M01-S02 has one active task (todo) and one cancelled one
    assert not is_done(backlog.by_id["M01-S02"])


def test_only_cancelled_container_is_not_done(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / ENDPOINT, "status: todo", "status: cancelled")
    rewrite(root / T02, "depends_on: [M01-S01-T01]", "depends_on: [M01-S02]")
    backlog = load_backlog(root)
    step = backlog.by_id["M01-S02"]
    assert isinstance(step, Container)
    assert not is_done(step)
    loader = backlog.by_id["M01-S01-T02"]
    assert isinstance(loader, Task)
    assert [u.reason for u in unmet(backlog, loader)] == ["empty"]
    assert derived_state(backlog, loader) == "blocked"
    assert (root / DOCS).exists()


def test_blocks_is_reverse_of_depends_on() -> None:
    assert blocks(load_backlog(FIXTURE)) == {
        "M01-S01": ["M01-S02-T01"],
        "M01-S01-T01": ["M01-S01-T02", "M02-S01-T01"],
        "M01-S02-T01": ["M02-S01-T02"],
        "M02-S01-T01": ["M02-S01-T02"],
    }


def test_two_levels(tmp_path: Path) -> None:
    write(tmp_path, ".factory/config.yaml", "levels: [epic, story]\n")
    write(tmp_path, "backlog/E1/index.md", index_md("E1", "owner: carol\n"))
    write(tmp_path, "backlog/E1/E1-a.md", task_md("E1-a"))
    write(tmp_path, "backlog/E1/E1-b.md", task_md("E1-b", extra="depends_on: [E1-a]\n"))
    backlog = load_backlog(tmp_path)
    assert check_backlog(backlog) == []
    assert counts(backlog) == {"epic": 1, "story": 2}
    [epic] = backlog.containers
    assert epic.level == "epic"
    assert [t.level for t in epic.tasks] == ["story", "story"]
    task = epic.tasks[1]
    assert "owner" not in effective(task)
    assert derived_state(backlog, task) == "blocked"


def test_owner_field_is_ignored(tmp_path: Path) -> None:
    """A legacy ``owner`` in an index or a task stays valid and is ignored."""
    write(tmp_path, "backlog/M01/index.md", index_md("M01", "owner: alice\n"))
    write(tmp_path, "backlog/M01/S01/index.md", index_md("M01-S01", "owner: carol\n"))
    write(tmp_path, "backlog/M01/S01/M01-S01-T01.md", task_md("M01-S01-T01", extra="owner: bob\n"))
    backlog = load_backlog(tmp_path)
    assert check_backlog(backlog) == []
    task = backlog.by_id["M01-S01-T01"]
    assert isinstance(task, Task)
    assert "owner" not in effective(task)
    assert "owner" not in task.own
    for container_id in ("M01", "M01-S01"):
        container = backlog.by_id[container_id]
        assert isinstance(container, Container)
        assert "owner" not in container.defaults


def test_four_levels(tmp_path: Path) -> None:
    write(tmp_path, ".factory/config.yaml", "levels: [area, module, step, task]\n")
    write(tmp_path, "backlog/A/index.md", index_md("A"))
    write(tmp_path, "backlog/A/M/index.md", index_md("A-M"))
    write(tmp_path, "backlog/A/M/S/index.md", index_md("A-M-S"))
    write(tmp_path, "backlog/A/M/S/t.md", task_md("A-M-S-T1", status="done"))
    backlog = load_backlog(tmp_path)
    assert check_backlog(backlog) == []
    assert counts(backlog) == {"area": 1, "module": 1, "step": 1, "task": 1}
    area = backlog.containers[0]
    step = area.children[0].children[0]
    assert (area.level, area.children[0].level, step.level) == ("area", "module", "step")
    assert step.tasks[0].level == "task"
    assert is_done(area)


def test_missing_config_uses_defaults(tmp_path: Path) -> None:
    assert load_settings(tmp_path).levels == ("project", "step", "task")


def test_invalid_config_raises(tmp_path: Path) -> None:
    write(tmp_path, ".factory/config.yaml", "levels: [x]\n")
    with pytest.raises(ConfigError):
        load_backlog(tmp_path)
