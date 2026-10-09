"""`add_task`, `edit_task` and `link_task`: validated writes of task files."""

from __future__ import annotations

from pathlib import Path

import pytest
from backlog_repo import ENDPOINT, M01_S01, T02, VIEW, rewrite, sample_repo

from aifactory.backlog import (
    TaskEditError,
    add_task,
    check_backlog,
    derived_state,
    edit_task,
    effective_workflow,
    link_task,
    load_backlog,
    parse_frontmatter,
)


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _header(root: Path, rel: str) -> dict[str, object]:
    return parse_frontmatter((root / rel).read_text(encoding="utf-8"))[0]


def test_add_task(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    before = {k: v for k, v in snapshot(root).items() if not k.startswith("backlog/")}
    result = add_task(root, "M01-S01", "Nový task")
    rel = f"{M01_S01}/M01-S01-T03-novy-task.md"
    assert result.path == rel
    assert result.changed
    assert result.task.id == "M01-S01-T03"
    header = _header(root, rel)
    assert header["status"] == "todo"
    assert header["depends_on"] == []
    assert derived_state(result.backlog, result.task) == "ready"
    assert check_backlog(load_backlog(root)) == []
    assert result.issues == []
    after = {k: v for k, v in snapshot(root).items() if not k.startswith("backlog/")}
    assert after == before


def test_add_task_with_fields(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    result = add_task(
        root,
        "M01-S01",
        "Další",
        depends_on=["M01-S01-T02"],
        writes=["src/x/"],
        workflow="wf",
        body="Zadání tasku.",
    )
    header = _header(root, result.path)
    assert header["workflow"] == "wf"
    assert header["writes"] == ["src/x/"]
    assert header["depends_on"] == ["M01-S01-T02"]
    assert derived_state(result.backlog, result.task) == "blocked"
    assert "Zadání tasku." in result.task.body


def test_add_task_with_own_test_command(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    result = add_task(root, "M01-S01", "Celá sada", test=["just", "check"])
    header = _header(root, result.path)
    assert header["test"] == ["just", "check"]
    assert check_backlog(load_backlog(root)) == []


def test_add_task_rejects_an_empty_test_command(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    with pytest.raises(TaskEditError) as exc:
        add_task(root, "M01-S01", "Bez testu", test=[])
    assert exc.value.code == "invalid_value"


def _expect(exc: pytest.ExceptionInfo[TaskEditError], code: str, exit_code: int) -> None:
    assert exc.value.exit_code == exit_code
    assert exc.value.errors()[0]["code"] == code


def test_add_rejected_keeps_tree(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    before = snapshot(root)
    with pytest.raises(TaskEditError) as exc:
        add_task(root, "M01-S01", "X", depends_on=["NOPE"])
    _expect(exc, "unknown_ref", 1)
    assert exc.value.code == "backlog_invalid"
    with pytest.raises(TaskEditError) as exc:
        add_task(root, "M01-S01", "X", task_id="X-1")
    _expect(exc, "id_prefix", 1)
    with pytest.raises(TaskEditError) as exc:
        add_task(root, "M01-S01", "X", task_id="M01-S01-T01")
    _expect(exc, "duplicate_id", 1)
    assert snapshot(root) == before


@pytest.mark.parametrize(
    ("step", "title", "kwargs", "code"),
    [
        ("M09-S01", "X", {}, "unknown_step"),
        ("M01", "X", {}, "unknown_step"),
        ("M01-S01", "  ", {}, "invalid_value"),
        ("M01-S01", "X", {"task_id": "M01-S01/T9"}, "invalid_id"),
        ("M01-S01", "X", {"slug": "Bad Slug"}, "invalid_value"),
        ("M01-S01", "X", {"task_id": "M01-S01-T09", "related": ["M01-S01-T09"]}, "self_ref"),
        ("M01-S01", "X", {"task_id": "M01-S01-T01", "slug": "schema"}, "file_exists"),
    ],
)
def test_add_input_errors(
    tmp_path: Path, step: str, title: str, kwargs: dict[str, str | list[str]], code: str
) -> None:
    root = sample_repo(tmp_path)
    before = snapshot(root)
    with pytest.raises(TaskEditError) as exc:
        add_task(root, step, title, **kwargs)  # type: ignore[arg-type]
    _expect(exc, code, 2)
    assert snapshot(root) == before


def test_edit_title_changes_only_that_line(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    old = (root / T02).read_text(encoding="utf-8")
    result = edit_task(root, "M01-S01-T02", title="Loader: v2")
    new = (root / T02).read_text(encoding="utf-8")
    assert result.changed
    assert result.task.title == "Loader: v2"
    assert new.replace('title: "Loader: v2"', "title: Loader") == old


def test_edit_status(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    result = edit_task(root, "M01-S02-T02", status="todo")
    assert result.task.status == "todo"
    result = edit_task(root, "M01-S02-T02", status="cancelled")
    assert result.task.status == "cancelled"
    before = snapshot(root)
    with pytest.raises(TaskEditError) as exc:
        edit_task(root, "M01-S01-T02", status="done")
    _expect(exc, "invalid_status", 2)
    with pytest.raises(TaskEditError) as exc:
        edit_task(root, "M01-S01-T01", status="cancelled")
    _expect(exc, "invalid_status", 2)
    assert snapshot(root) == before


def test_edit_workflow_and_writes(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    result = edit_task(root, "M01-S01-T02", clear_workflow=True)
    assert "workflow" not in _header(root, T02)
    assert effective_workflow(result.task) == "plan-build"
    result = edit_task(root, "M01-S01-T02", workflow="custom", writes=[])
    header = _header(root, T02)
    assert header["workflow"] == "custom"
    assert header["writes"] == []
    result = edit_task(root, "M01-S01-T02", clear_writes=True)
    assert "writes" not in _header(root, T02)


def test_edit_errors_and_noop(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    with pytest.raises(TaskEditError) as exc:
        edit_task(root, "M01-S01-T02")
    _expect(exc, "no_changes", 2)
    with pytest.raises(TaskEditError) as exc:
        edit_task(root, "M01-S01-T02", workflow="x", clear_workflow=True)
    _expect(exc, "conflicting_options", 2)
    with pytest.raises(TaskEditError) as exc:
        edit_task(root, "M01-S01-T99", title="x")
    _expect(exc, "unknown_task", 2)
    with pytest.raises(TaskEditError) as exc:
        edit_task(root, "M01-S01", title="x")
    _expect(exc, "unknown_task", 2)
    before = snapshot(root)
    mtime = (root / T02).stat().st_mtime_ns
    result = edit_task(root, "M01-S01-T02", title="Loader")
    assert not result.changed
    assert snapshot(root) == before
    assert (root / T02).stat().st_mtime_ns == mtime


def test_edit_duplicate_target(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / T02, "id: M01-S01-T02", "id: M01-S01-T01")
    with pytest.raises(TaskEditError) as exc:
        edit_task(root, "M01-S01-T01", title="x")
    _expect(exc, "duplicate_id", 2)


def test_link_add_and_remove(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    result = link_task(root, "M01-S01-T02", related=["M02-S01-T01"])
    assert result.changed
    assert _header(root, T02)["related"] == ["M02-S01-T01"]
    again = link_task(root, "M01-S01-T02", related=["M02-S01-T01"])
    assert not again.changed
    link_task(root, "M01-S01-T02", related=["M02-S01-T01"], remove=True)
    assert "related" not in _header(root, T02)
    link_task(root, "M01-S01-T02", depends_on=["M01-S01-T01"], remove=True)
    assert _header(root, T02)["depends_on"] == []
    result = link_task(root, "M01-S02-T01", depends_on=["M01-S01-T02"])
    assert result.task.depends_on == ["M01-S01", "M01-S01-T02"]
    assert _header(root, ENDPOINT)["depends_on"] == ["M01-S01", "M01-S01-T02"]


@pytest.mark.parametrize(
    ("task_id", "kwargs", "code", "exit_code"),
    [
        ("M01-S01-T01", {"depends_on": ["M01-S01-T02"]}, "cycle", 1),
        ("M01-S01-T01", {"depends_on": ["M01-S01"]}, "cycle", 1),
        ("M01-S01-T02", {"depends_on": ["NOPE"]}, "unknown_ref", 1),
        ("M01-S01-T02", {"related": ["NOPE"]}, "unknown_ref", 1),
        ("M01-S01-T02", {"related": ["M01-S01-T02"]}, "self_ref", 2),
        ("M01-S01-T02", {}, "no_changes", 2),
    ],
)
def test_link_errors(
    tmp_path: Path, task_id: str, kwargs: dict[str, list[str]], code: str, exit_code: int
) -> None:
    root = sample_repo(tmp_path)
    before = snapshot(root)
    with pytest.raises(TaskEditError) as exc:
        link_task(root, task_id, depends_on=kwargs.get("depends_on"), related=kwargs.get("related"))
    _expect(exc, code, exit_code)
    assert snapshot(root) == before


def test_existing_problem_does_not_block(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / VIEW, "depends_on: [M01-S01-T01]", "depends_on: [GONE]")
    result = edit_task(root, "M01-S01-T02", title="Jinak")
    assert result.changed
    assert [i.code for i in result.issues] == ["unknown_ref"]


def test_missing_backlog_dir(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    with pytest.raises(TaskEditError) as exc:
        add_task(root, "M01-S01", "X")
    _expect(exc, "missing_backlog_dir", 2)
