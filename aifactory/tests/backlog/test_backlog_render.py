"""Filters, JSON and the text tree."""

from __future__ import annotations

import json
from typing import Any

import pytest
from backlog_repo import FIXTURE

from aifactory.backlog import backlog_to_json, format_tree, load_backlog, select_projects


def test_tree() -> None:
    lines = format_tree(load_backlog(FIXTURE))
    assert lines[0] == "M01 Core  [1/3]"
    assert "  M01-S01 Model  [1/2]  (blocks: M01-S02-T01)" in lines
    assert "    M01-S01-T01 Schema  done  (blocks: M01-S01-T02, M02-S01-T01)" in lines
    assert "    M01-S01-T02 Loader  ready" in lines
    assert (
        "    M01-S02-T01 Endpoint  blocked (waits for: M01-S01 [M01-S01-T02])"
        "  (blocks: M02-S01-T02)"
    ) in lines
    assert "    M01-S02-T02 Docs  cancelled" in lines
    assert "    M02-S01-T02 Filter  blocked (waits for: M02-S01-T01, M01-S02-T01)" in lines


def test_done_container_is_marked(tmp_path: Any) -> None:
    from backlog_repo import T02, rewrite, sample_repo

    root = sample_repo(tmp_path)
    rewrite(root / T02, "status: todo", "status: done")
    assert "  M01-S01 Model  [2/2]  done  (blocks: M01-S02-T01)" in format_tree(load_backlog(root))


def test_status_ready_filter() -> None:
    lines = [line.strip() for line in format_tree(load_backlog(FIXTURE), status="ready")]
    assert lines == [
        "M01 Core  [1/3]",
        "M01-S01 Model  [1/2]  (blocks: M01-S02-T01)",
        "M01-S01-T02 Loader  ready",
        "M02 UI  [0/2]",
        "M02-S01 List  [0/2]",
        "M02-S01-T01 View  ready  (blocks: M02-S01-T02)",
    ]


def test_status_todo_takes_ready_and_blocked() -> None:
    text = "\n".join(format_tree(load_backlog(FIXTURE), status="todo"))
    for task_id in ("M01-S01-T02", "M01-S02-T01", "M02-S01-T01", "M02-S01-T02"):
        assert task_id in text
    assert "M01-S01-T01" not in text.replace("(blocks: M01-S01-T02", "")
    assert "Schema" not in text
    assert "Docs" not in text


def test_status_done_hides_containers_without_match() -> None:
    lines = format_tree(load_backlog(FIXTURE), status="done")
    assert [line.split()[0] for line in lines] == ["M01", "M01-S01", "M01-S01-T01"]


@pytest.mark.parametrize("project", ["M02", "M02-ui"])
def test_project_filter(project: str) -> None:
    backlog = load_backlog(FIXTURE)
    assert [c.id for c in select_projects(backlog, project)] == ["M02"]
    lines = format_tree(backlog, project=project)
    assert lines[0] == "M02 UI  [0/2]"
    assert not any("M01" in line.split()[0] for line in lines)


def test_unknown_project() -> None:
    backlog = load_backlog(FIXTURE)
    with pytest.raises(LookupError):
        format_tree(backlog, project="M9")
    with pytest.raises(LookupError):
        backlog_to_json(backlog, [], project="M9")


def test_json() -> None:
    backlog = load_backlog(FIXTURE)
    data: dict[str, Any] = json.loads(json.dumps(backlog_to_json(backlog, [])))
    assert data["ok"] is True
    assert data["levels"] == ["module", "step", "task"]
    assert data["backlog_dir"] == "backlog"
    assert data["filters"] == {"status": None, "project": None}
    m01 = data["items"][0]
    assert m01["progress"] == {"done": 1, "total": 3}
    assert m01["done"] is False
    assert "owner" not in m01["defaults"]
    step = m01["children"][0]
    assert (step["id"], step["done"], step["blocks"]) == ("M01-S01", False, ["M01-S02-T01"])
    loader = step["children"][1]
    assert loader["state"] == "ready"
    assert loader["writes"] == ["src/"]
    assert loader["own_writes"] == []
    assert loader["workflow"] == "plan-build-test-review"
    endpoint = m01["children"][1]["children"][0]
    assert endpoint["state"] == "blocked"
    assert endpoint["writes"] == ["src/api/"]
    assert endpoint["blocked_by"] == [
        {"id": "M01-S01", "reason": "incomplete", "missing": ["M01-S01-T02"]}
    ]
    assert endpoint["blocks"] == ["M02-S01-T02"]


def test_json_filters() -> None:
    data: dict[str, Any] = backlog_to_json(
        load_backlog(FIXTURE), [], status="blocked", project="M02"
    )
    assert data["filters"] == {"status": "blocked", "project": "M02"}
    [m02] = data["items"]
    [step] = m02["children"]
    assert [t["id"] for t in step["children"]] == ["M02-S01-T02"]
    assert step["progress"] == {"done": 0, "total": 2}
