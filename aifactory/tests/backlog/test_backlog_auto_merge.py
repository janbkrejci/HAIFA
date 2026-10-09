"""`auto_merge`: inherited like auto_continue; `factory backlog auto-merge`, `task edit`."""

from __future__ import annotations

from pathlib import Path

import pytest
from backlog_repo import M01_S01, T01, T02, rewrite, sample_repo

from aifactory.backlog import (
    Task,
    TaskEditError,
    edit_task,
    effective,
    load_backlog,
    set_auto_merge,
)
from aifactory.cli import main
from cli_json import read_envelope

Capsys = pytest.CaptureFixture[str]
INDEX = f"{M01_S01}/index.md"
TASK_ID = "M01-S01-T01"


def _effective(root: Path, task_id: str = TASK_ID) -> object:
    task = load_backlog(root).by_id[task_id]
    assert isinstance(task, Task)
    return effective(task).get("auto_merge")


def test_on_off_inherit(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    before = (root / INDEX).read_text(encoding="utf-8")

    result = set_auto_merge(root, "M01-S01", True)
    assert result.changed and result.path == INDEX and result.action == "auto_merge"
    assert "auto_merge: true\n" in (root / INDEX).read_text(encoding="utf-8")
    assert result.container.defaults["auto_merge"] is True
    assert _effective(root) is True
    assert set_auto_merge(root, "M01-S01", True).changed is False

    set_auto_merge(root, "M01-S01", False)
    assert "auto_merge: false\n" in (root / INDEX).read_text(encoding="utf-8")
    assert _effective(root) is False

    assert set_auto_merge(root, "M01-S01", None).changed
    assert (root / INDEX).read_text(encoding="utf-8") == before
    assert _effective(root) is None


def test_project_step_task_inheritance(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    set_auto_merge(root, "M01", True)
    assert _effective(root) is True
    set_auto_merge(root, "M01-S01", False)
    assert _effective(root) is False
    edit_task(root, TASK_ID, auto_merge=True)
    assert _effective(root) is True
    assert _effective(root, "M01-S01-T02") is False


def test_task_edit_switches_off_and_back_to_inherited(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    set_auto_merge(root, "M01-S01", True)
    before = (root / T01).read_text(encoding="utf-8")

    edit_task(root, TASK_ID, auto_merge=False)
    assert "auto_merge: false\n" in (root / T01).read_text(encoding="utf-8")
    assert _effective(root) is False

    edit_task(root, TASK_ID, clear_auto_merge=True)
    assert (root / T01).read_text(encoding="utf-8") == before
    assert _effective(root) is True


def test_task_edit_conflicting_options(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    with pytest.raises(TaskEditError) as info:
        edit_task(root, TASK_ID, auto_merge=True, clear_auto_merge=True)
    assert info.value.code == "conflicting_options"


def test_cli_backlog_auto_merge(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    code = main(["backlog", "auto-merge", "M01-S01", "--on", "--repo", str(root)])
    assert code == 0
    assert capsys.readouterr().out.strip() == f"auto_merge on for M01-S01 ({INDEX})"

    code = main(["backlog", "auto-merge", "M01-S01", "--off", "--json", "--repo", str(root)])
    env = read_envelope(capsys)
    data = env["data"]
    assert code == 0 and env["ok"] is True and data["changed"] is True
    assert (data["id"], data["path"], data["auto_merge"], data["level"]) == (
        "M01-S01",
        INDEX,
        False,
        "step",
    )

    code = main(["backlog", "auto-merge", "M01", "--inherit", "--repo", str(root)])
    assert code == 0 and capsys.readouterr().out.strip() == "unchanged M01"

    code = main(["backlog", "auto-merge", "M09", "--on", "--json", "--repo", str(root)])
    assert code == 2
    assert read_envelope(capsys)["error"]["code"] == "unknown_container"


def test_cli_task_edit_auto_merge(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    assert main(["task", "edit", TASK_ID, "--auto-merge", "off", "--repo", str(root)]) == 0
    assert "auto_merge: false\n" in (root / T01).read_text(encoding="utf-8")
    assert main(["task", "edit", TASK_ID, "--auto-merge", "on", "--repo", str(root)]) == 0
    assert "auto_merge: true\n" in (root / T01).read_text(encoding="utf-8")
    assert main(["task", "edit", TASK_ID, "--auto-merge", "inherit", "--repo", str(root)]) == 0
    assert "auto_merge" not in (root / T01).read_text(encoding="utf-8")
    capsys.readouterr()
    with pytest.raises(SystemExit):
        main(["task", "edit", TASK_ID, "--auto-merge", "maybe", "--repo", str(root)])


def test_loader_rejects_non_bool(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / INDEX, "title: Model\n", "title: Model\nauto_merge: yes-please\n")
    rewrite(root / T02, "status: todo\n", "status: todo\nauto_merge: 1\n")
    backlog = load_backlog(root)
    bad = [i for i in backlog.issues if i.code == "invalid_field" and "'auto_merge'" in i.message]
    assert {i.path for i in bad} == {INDEX, T02}
    assert _effective(root) is None
    assert _effective(root, "M01-S01-T02") is None
