"""``add_batch``: tasks of an existing step, a new step, or a new project with its step."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from backlog_repo import M01_S01, sample_repo, task_md, write

from aifactory.backlog import NewTask, Task, TaskEditError, add_batch, load_backlog


def _tasks() -> list[NewTask]:
    return [
        NewTask("T01", "Schema"),
        NewTask("T02", "Loader", body="Načíst.", depends_on=["T01"]),
    ]


def _codes(exc: pytest.ExceptionInfo[TaskEditError]) -> list[str]:
    return [i.code for i in exc.value.issues]


def test_new_project_preview_writes_nothing(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    result = add_batch(
        root,
        _tasks(),
        project_code="M03",
        project_title="Reports",
        project_body="Přehledy.",
        step_code="S01",
        step_title="Export",
    )
    assert result.new_project and result.new_step and not result.written
    assert result.project_id == "M03"
    assert result.project_title == "Reports"
    assert result.project_body == "Přehledy."
    assert result.project_path == "backlog/M03-reports"
    assert result.step_id == "M03-S01"
    assert result.step_path == "backlog/M03-reports/S01-export"
    assert [t.id for t in result.tasks] == ["M03-S01-T01", "M03-S01-T02"]
    assert result.tasks[1].depends_on == ["M03-S01-T01"]
    assert result.files == [
        "backlog/M03-reports/index.md",
        "backlog/M03-reports/S01-export/index.md",
        "backlog/M03-reports/S01-export/M03-S01-T01-schema.md",
        "backlog/M03-reports/S01-export/M03-S01-T02-loader.md",
    ]
    assert not (root / "backlog/M03-reports").exists()


def test_new_project_write(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    result = add_batch(
        root,
        _tasks(),
        project_code="M03",
        project_title="Reports",
        project_body="Přehledy.",
        step_code="S01",
        step_title="Export",
        write=True,
    )
    assert result.written
    for rel in result.files:
        assert (root / rel).is_file()
    backlog = load_backlog(root)
    project = backlog.by_id["M03"]
    step = backlog.by_id["M03-S01"]
    assert project.title == "Reports" and project.body.strip() == "Přehledy."
    assert step.title == "Export"
    task = backlog.by_id["M03-S01-T02"]
    assert isinstance(task, Task) and task.depends_on == ["M03-S01-T01"]


def test_new_project_duplicate_id_and_directory(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    write(root, "backlog/M09-ui/readme.md", "x\n")
    with pytest.raises(TaskEditError) as exc:
        add_batch(
            root,
            _tasks(),
            project_code="M01",
            project_title="Core",
            step_code="S09",
            step_title="New",
        )
    assert exc.value.code == "backlog_invalid"
    assert "duplicate_id" in _codes(exc)
    assert "file_exists" in _codes(exc)
    with pytest.raises(TaskEditError) as exc:
        add_batch(
            root,
            _tasks(),
            project_code="M09",
            project_title="UI",
            step_code="S01",
            step_title="New",
        )
    assert _codes(exc) == ["file_exists"]


def test_new_project_empty_title(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    with pytest.raises(TaskEditError) as exc:
        add_batch(
            root,
            [NewTask("T01", "")],
            project_code="M03",
            project_title="  ",
            step_code="S01",
            step_title="",
        )
    assert exc.value.code == "backlog_invalid"
    assert _codes(exc).count("invalid_value") == 3
    assert not (root / "backlog/M03").exists()


@pytest.mark.parametrize(
    "options", [{"project": "M01"}, {"step": "M01-S01"}, {"project": "M01", "step": "M01-S01"}]
)
def test_new_project_conflicting_options(tmp_path: Path, options: dict[str, Any]) -> None:
    root = sample_repo(tmp_path)
    with pytest.raises(TaskEditError) as exc:
        add_batch(
            root,
            _tasks(),
            project_code="M03",
            project_title="R",
            step_code="S01",
            step_title="E",
            **options,
        )
    assert exc.value.code == "conflicting_options"


def test_new_project_without_project_level(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    write(root, ".factory/config.yaml", "levels: [step, task]\ndocs_root: .\n")
    write(root, "backlog/S01-a/index.md", "---\nid: S01\ntitle: A\n---\n")
    write(root, "backlog/S01-a/S01-T01-a.md", task_md("S01-T01"))
    with pytest.raises(TaskEditError) as exc:
        add_batch(
            root, _tasks(), project_code="P1", project_title="P", step_code="S02", step_title="B"
        )
    assert exc.value.code == "invalid_value"
    result = add_batch(root, [NewTask("T02", "Next")], step="S01")
    assert (result.project_id, result.project_title, result.project_path) == ("", "", "")
    assert result.project_body == "" and not result.new_project


def test_existing_step_and_project_fill_project_fields(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    by_step = add_batch(root, [NewTask("T09", "Extra")], step="M01-S01")
    by_project = add_batch(
        root, [NewTask("T01", "Extra")], project="M01", step_code="S09", step_title="New"
    )
    for result in (by_step, by_project):
        assert result.project_id == "M01"
        assert result.project_title == "Core"
        assert result.project_body == "Jádro: datový model a API."
        assert result.project_path == "backlog/M01-core"
        assert not result.new_project
    assert by_step.step_path == M01_S01 and not by_step.new_step
    assert by_project.step_path == "backlog/M01-core/S09-new" and by_project.new_step
