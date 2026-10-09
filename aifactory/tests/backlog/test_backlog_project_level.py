"""The top backlog level: default ``project``, ``--project`` and repos with ``module``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from backlog_repo import index_md, sample_repo, task_md, write

from aifactory.backlog import counts, load_backlog
from aifactory.cli import main
from cli_json import read_envelope

Capsys = pytest.CaptureFixture[str]


def _json(capsys: Capsys) -> Any:
    return read_envelope(capsys)


def project_repo(tmp_path: Path) -> Path:
    """A repo whose config has no ``levels`` (defaults) with projects P1 and P2."""
    root = tmp_path / "repo"
    write(root, ".factory/config.yaml", "backlog_dir: backlog\n")
    for project in ("P1", "P2"):
        base = f"backlog/{project}-core"
        write(root, f"{base}/index.md", index_md(project))
        write(root, f"{base}/S01-x/index.md", index_md(f"{project}-S01"))
        write(root, f"{base}/S01-x/{project}-S01-T01-a.md", task_md(f"{project}-S01-T01"))
    return root


def test_default_levels_are_project_step_task(tmp_path: Path) -> None:
    backlog = load_backlog(project_repo(tmp_path))
    assert backlog.settings.levels == ("project", "step", "task")
    assert [c.level for c in backlog.containers] == ["project", "project"]
    assert counts(backlog) == {"project": 2, "step": 2, "task": 2}


def test_backlog_list_project_filter(tmp_path: Path, capsys: Capsys) -> None:
    root = str(project_repo(tmp_path))
    assert main(["backlog", "list", "--json", "--repo", root, "--project", "P1"]) == 0
    data = _json(capsys)["data"]
    assert data["levels"] == ["project", "step", "task"]
    assert data["filters"] == {"status": None, "project": "P1"}
    assert [c["id"] for c in data["items"]] == ["P1"]


def test_backlog_list_unknown_project(tmp_path: Path, capsys: Capsys) -> None:
    root = str(project_repo(tmp_path))
    assert main(["backlog", "list", "--repo", root, "--project", "P9"]) == 2
    assert "unknown project 'P9'" in capsys.readouterr().err
    assert main(["backlog", "list", "--json", "--repo", root, "--project", "P9"]) == 2
    error = _json(capsys)["error"]
    assert error["code"] == "unknown_project"
    assert error["message"] == "unknown project 'P9'"


def test_task_list_project_filter(tmp_path: Path, capsys: Capsys) -> None:
    root = str(project_repo(tmp_path))
    assert main(["task", "list", "--json", "--repo", root, "--project", "P2"]) == 0
    data = _json(capsys)["data"]
    assert data["filters"]["project"] == "P2"
    assert [t["id"] for t in data["tasks"]] == ["P2-S01-T01"]
    assert main(["task", "list", "--json", "--repo", root, "--project", "P9"]) == 2
    error = _json(capsys)["error"]
    assert error["code"] == "unknown_project"
    assert error["message"] == "unknown project 'P9'"


def test_auto_continue_unknown_names_levels(tmp_path: Path, capsys: Capsys) -> None:
    root = str(project_repo(tmp_path))
    assert main(["backlog", "auto-continue", "NOPE", "--on", "--json", "--repo", root]) == 2
    error = _json(capsys)["error"]
    assert error["code"] == "unknown_container"
    assert error["message"] == "no project or step 'NOPE'"


def test_module_option_is_gone(tmp_path: Path, capsys: Capsys) -> None:
    root = str(project_repo(tmp_path))
    with pytest.raises(SystemExit) as info:
        main(["backlog", "list", "--repo", root, "--module", "P1"])
    assert info.value.code == 2
    with pytest.raises(SystemExit) as info:
        main(["task", "list", "--repo", root, "--module", "P1"])
    assert info.value.code == 2


# ── a repo with the old explicit ``levels: [module, step, task]`` ───────────


def test_old_module_levels_still_work(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    assert (root / ".factory/config.yaml").read_text().startswith("levels: [module, step, task]")
    repo = ["--repo", str(root)]
    assert main(["backlog", "check", *repo]) == 0
    assert capsys.readouterr().out == "OK: 2 module, 3 step, 6 task\n"
    assert main(["backlog", "list", "--json", "--project", "M01", *repo]) == 0
    data = _json(capsys)["data"]
    assert data["levels"] == ["module", "step", "task"]
    assert [c["id"] for c in data["items"]] == ["M01"]
    assert main(["task", "list", "--json", "--project", "M9", *repo]) == 2
    error = _json(capsys)["error"]
    assert error["code"] == "unknown_project"
    assert error["message"] == "unknown module 'M9'"
    assert main(["backlog", "list", "--json", "--project", "M9", *repo]) == 2
    error = _json(capsys)["error"]
    assert (error["code"], error["message"]) == ("unknown_project", "unknown module 'M9'")
    assert main(["backlog", "auto-continue", "X", "--on", "--json", *repo]) == 2
    assert _json(capsys)["error"]["message"] == "no module or step 'X'"
