"""Dependencies between separate project roots in one repository."""

from __future__ import annotations

from pathlib import Path

import pytest
from backlog_repo import index_md, rewrite, task_md, write

from aifactory.backlog import Task, Unmet, check_backlog, link_task, load_backlog, unmet
from aifactory.run.queue import select_ready
from aifactory.run.store import QueuePrefs
from aifactory.web.backlog import container_graph

A_TASK = "A-S01-T01"
B_TASK = "B-S01-T01"
A_PATH = f"backlog/A/S01/{A_TASK}.md"
B_PATH = f"backlog/B/S01/{B_TASK}.md"


@pytest.fixture
def cross_project_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    write(root, ".factory/config.yaml", "docs_root: .\n")
    for project in ("A", "B"):
        base = f"backlog/{project}"
        write(root, f"{base}/index.md", index_md(project))
        write(root, f"{base}/S01/index.md", index_md(f"{project}-S01"))
        extra = f"depends_on: [{A_TASK}]\n" if project == "B" else ""
        task_id = f"{project}-S01-T01"
        write(root, f"{base}/S01/{task_id}.md", task_md(task_id, extra=extra))
    return root


def test_check_accepts_cross_project_reference(cross_project_repo: Path) -> None:
    backlog = load_backlog(cross_project_repo)
    assert [project.id for project in backlog.containers] == ["A", "B"]
    issues = check_backlog(backlog)
    assert not [issue for issue in issues if issue.code == "unknown_ref"]
    assert issues == []


def test_unmet_tracks_cross_project_completion(cross_project_repo: Path) -> None:
    backlog = load_backlog(cross_project_repo)
    task = backlog.by_id[B_TASK]
    assert isinstance(task, Task)
    assert unmet(backlog, task) == [Unmet(A_TASK, "not_done", [A_TASK])]

    rewrite(cross_project_repo / A_PATH, "status: todo", "status: done")
    backlog = load_backlog(cross_project_repo)
    task = backlog.by_id[B_TASK]
    assert isinstance(task, Task)
    assert unmet(backlog, task) == []


def test_select_ready_waits_for_other_project(cross_project_repo: Path) -> None:
    # Put B first so backlog ordering cannot mask a missing dependency check.
    prefs = QueuePrefs(order=(B_TASK, A_TASK))
    selection = select_ready(
        load_backlog(cross_project_repo),
        open_pr=lambda _: None,
        running=lambda _: None,
        prefs=prefs,
    )
    assert selection.next is not None
    assert selection.next.id == A_TASK
    assert [(s.task_id, s.reason, s.waits_on) for s in selection.skipped] == [
        (B_TASK, "blocked", [A_TASK])
    ]

    rewrite(cross_project_repo / A_PATH, "status: todo", "status: done")
    selection = select_ready(
        load_backlog(cross_project_repo),
        open_pr=lambda _: None,
        running=lambda _: None,
        prefs=prefs,
    )
    assert selection.next is not None
    assert selection.next.id == B_TASK
    assert selection.skipped == []


def test_link_task_adds_cross_project_dependency(cross_project_repo: Path) -> None:
    rewrite(cross_project_repo / B_PATH, f"depends_on: [{A_TASK}]\n", "")
    before = load_backlog(cross_project_repo).by_id[B_TASK]
    assert isinstance(before, Task)
    assert before.depends_on == []

    result = link_task(cross_project_repo, B_TASK, depends_on=[A_TASK])
    assert result.changed
    backlog = load_backlog(cross_project_repo)
    task = backlog.by_id[B_TASK]
    assert isinstance(task, Task)
    assert task.depends_on == [A_TASK]
    assert check_backlog(backlog) == []


def test_container_graph_shows_other_project_as_external(cross_project_repo: Path) -> None:
    graph, warnings = container_graph(cross_project_repo, "B")
    assert warnings == []
    assert graph["container"]["id"] == "B"
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert set(nodes) == {A_TASK, B_TASK}
    assert nodes[A_TASK]["external"] is True
    assert nodes[A_TASK]["kind"] == "task"
    assert nodes[A_TASK]["step"] == "A-S01"
    assert nodes[B_TASK]["external"] is False
    assert graph["edges"] == [{"from": A_TASK, "to": B_TASK}]
