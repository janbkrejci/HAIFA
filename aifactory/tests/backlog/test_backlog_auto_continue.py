"""`factory backlog auto-continue`: auto_continue in a module's or step's index.md."""

from __future__ import annotations

from pathlib import Path

import pytest
from backlog_repo import M01_S01, T02, rewrite, sample_repo

from aifactory.backlog import (
    Task,
    TaskEditError,
    effective,
    load_backlog,
    set_auto_continue,
)
from aifactory.backlog.taskfile import set_field
from aifactory.cli import main
from cli_json import read_envelope

Capsys = pytest.CaptureFixture[str]
INDEX = f"{M01_S01}/index.md"
TASK_ID = "M01-S01-T01"


def _effective(root: Path) -> object:
    task = load_backlog(root).by_id[TASK_ID]
    assert isinstance(task, Task)
    return effective(task).get("auto_continue")


def test_set_field_bool_unquoted() -> None:
    text = "---\nid: X\ntitle: X\n---\n\nbody\n"
    assert "auto_continue: true\n" in set_field(text, "auto_continue", True)
    assert "auto_continue: false\n" in set_field(text, "auto_continue", False)


def test_on_off_inherit(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    before = (root / INDEX).read_text(encoding="utf-8")

    result = set_auto_continue(root, "M01-S01", True)
    assert result.changed and result.path == INDEX
    text = (root / INDEX).read_text(encoding="utf-8")
    assert "auto_continue: true\n" in text
    assert text.replace("auto_continue: true\n", "") == before
    assert result.container.defaults["auto_continue"] is True
    assert _effective(root) is True

    assert set_auto_continue(root, "M01-S01", True).changed is False

    set_auto_continue(root, "M01-S01", False)
    assert "auto_continue: false\n" in (root / INDEX).read_text(encoding="utf-8")
    assert _effective(root) is False

    result = set_auto_continue(root, "M01-S01", None)
    assert result.changed
    assert (root / INDEX).read_text(encoding="utf-8") == before
    assert _effective(root) is None


def test_module_switch_is_inherited(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    set_auto_continue(root, "M01", True)
    assert _effective(root) is True


def test_unknown_container(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    with pytest.raises(TaskEditError) as info:
        set_auto_continue(root, "M09", True)
    assert info.value.code == "unknown_container" and info.value.exit_code == 2


def test_cli_text_and_json(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    code = main(["backlog", "auto-continue", "M01-S01", "--on", "--repo", str(root)])
    assert code == 0
    assert capsys.readouterr().out.strip() == f"auto_continue on for M01-S01 ({INDEX})"

    code = main(["backlog", "auto-continue", "M01-S01", "--on", "--repo", str(root)])
    assert code == 0
    assert capsys.readouterr().out.strip() == "unchanged M01-S01"

    code = main(["backlog", "auto-continue", "M01-S01", "--off", "--json", "--repo", str(root)])
    env = read_envelope(capsys)
    data = env["data"]
    assert code == 0
    assert env["ok"] is True and data["changed"] is True
    assert (data["id"], data["path"], data["auto_continue"]) == ("M01-S01", INDEX, False)
    assert data["level"] == "step"

    code = main(["backlog", "auto-continue", "M01-S01", "--inherit", "--json", "--repo", str(root)])
    data = read_envelope(capsys)["data"]
    assert code == 0 and data["auto_continue"] is None

    code = main(["backlog", "auto-continue", "M09", "--on", "--json", "--repo", str(root)])
    data = read_envelope(capsys)
    assert code == 2
    assert data["error"]["code"] == "unknown_container"


def test_cli_needs_a_mode(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    with pytest.raises(SystemExit):
        main(["backlog", "auto-continue", "M01-S01", "--repo", str(root)])


def test_loader_rejects_non_bool(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    rewrite(root / INDEX, "title: Model\n", "title: Model\nauto_continue: yes-please\n")
    rewrite(root / T02, "status: todo\n", "status: todo\nauto_continue: 1\n")
    backlog = load_backlog(root)
    bad = [i for i in backlog.issues if i.code == "invalid_field" and "auto_continue" in i.message]
    assert {i.path for i in bad} == {INDEX, T02}
    assert _effective(root) is None
