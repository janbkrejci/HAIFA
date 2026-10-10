"""`factory backlog add|edit`: projects and steps (index.md) created and edited through core."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from backlog_repo import M01_S01, sample_repo, write

from aifactory.backlog import (
    TaskEditError,
    add_container,
    check_backlog,
    edit_container,
    effective_sources,
    load_backlog,
    parse_frontmatter,
)
from aifactory.backlog.edit import compose_id
from aifactory.cli import main
from cli_json import run_json

Capsys = pytest.CaptureFixture[str]
M01_INDEX = "backlog/M01-core/index.md"
S01_INDEX = f"{M01_S01}/index.md"


def _snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _header(root: Path, rel: str) -> dict[str, object]:
    return parse_frontmatter((root / rel).read_text(encoding="utf-8"))[0]


# ── core ─────────────────────────────────────────────────────────────────────


def test_harness_choices_are_project_settings_not_step_settings(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    edit_container(root, "M01", values={"harness": "codex", "model": "gpt-5.5"})
    assert _header(root, M01_INDEX)["harness"] == "codex"
    with pytest.raises(TaskEditError, match="only allowed on a project"):
        edit_container(root, "M01-S01", values={"harness": "claude"})
    with pytest.raises(TaskEditError):
        edit_container(root, "M01", values={"harness": "unknown"})


def test_add_project_and_step(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    project = add_container(root, None, "M03", "Reporty a exporty", body="Popis modulu.")
    assert project.path == "backlog/M03-reporty-a-exporty/index.md"
    assert project.changed
    assert project.container.level == "module"
    assert _header(root, project.path) == {"id": "M03", "title": "Reporty a exporty"}
    assert "Popis modulu." in project.container.body
    step = add_container(root, "M03", "S01", "Export CSV")
    assert step.path == "backlog/M03-reporty-a-exporty/S01-export-csv/index.md"
    assert step.container.level == "step"
    assert step.container.parent is not None and step.container.parent.id == "M03"
    assert check_backlog(load_backlog(root)) == []


@pytest.mark.parametrize("code", ["", "-M01", "M 01", "M01/x", "Ž01"])
def test_add_rejects_an_invalid_code(tmp_path: Path, code: str) -> None:
    root = sample_repo(tmp_path)
    before = _snapshot(root)
    with pytest.raises(TaskEditError) as exc:
        add_container(root, None, code, "Název")
    assert exc.value.code == "invalid_id"
    assert _snapshot(root) == before


def test_add_rejects_a_duplicate_code(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    before = _snapshot(root)
    for parent, code in ((None, "M01"), ("M01", "S01"), ("M01", "M01-S01")):
        with pytest.raises(TaskEditError) as exc:
            add_container(root, parent, code, "Jiný název")
        assert exc.value.code == "backlog_invalid"
        assert exc.value.exit_code == 1
        assert [i.code for i in exc.value.issues] == ["duplicate_id"]
    assert _snapshot(root) == before


def test_add_rejects_a_step_outside_its_project(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    before = _snapshot(root)
    with pytest.raises(TaskEditError) as exc:
        add_container(root, "M01", "M02-S09", "Cizí step")
    assert exc.value.code == "invalid_id"  # another project's prefix is not stripped
    with pytest.raises(TaskEditError) as exc:
        add_container(root, "M09", "S01", "Bez projektu")
    assert exc.value.code == "unknown_container"
    with pytest.raises(TaskEditError) as exc:
        add_container(root, "M01-S01", "X01", "Pod stepem")
    assert exc.value.code == "invalid_value"
    assert _snapshot(root) == before


@pytest.mark.parametrize(
    ("parent", "code", "full"),
    [
        (None, "HAIFA", "HAIFA"),
        (None, " M03 ", "M03"),
        ("HAIFA", "S10", "HAIFA-S10"),
        ("HAIFA", "HAIFA-S10", "HAIFA-S10"),
        ("HAIFA-S10", "T05", "HAIFA-S10-T05"),
        ("HAIFA-S10", "HAIFA-S10-T05", "HAIFA-S10-T05"),
        ("HAIFA-S10", "t1.v2_b", "HAIFA-S10-t1.v2_b"),
    ],
)
def test_compose_id(parent: str | None, code: str, full: str) -> None:
    assert compose_id(parent, code) == full


@pytest.mark.parametrize(
    ("parent", "code"),
    [
        (None, "M-01"),
        (None, ""),
        ("HAIFA", "HAIFA-"),
        ("HAIFA", "OTHER-S10"),
        ("HAIFA", "S-10"),
        ("HAIFA", "_S10"),
        ("HAIFA-S10", "HAIFA-T05"),
        ("HAIFA-S10", "T 5"),
    ],
)
def test_compose_id_rejects_invalid_codes(parent: str | None, code: str) -> None:
    with pytest.raises(TaskEditError) as exc:
        compose_id(parent, code)
    assert exc.value.code == "invalid_id"
    assert exc.value.exit_code == 2


def test_add_step_by_short_code_or_full_id(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    short = add_container(root, "M01", "S07", "Krátký kód")
    assert short.container.id == "M01-S07"
    assert short.path == "backlog/M01-core/S07-kratky-kod/index.md"
    full = add_container(root, "M01", "M01-S08", "Plné id")
    assert full.container.id == "M01-S08"
    assert check_backlog(load_backlog(root)) == []


def test_add_rejects_an_empty_title(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    with pytest.raises(TaskEditError) as exc:
        add_container(root, None, "M03", "  ")
    assert exc.value.code == "invalid_value"


def test_edit_sets_and_clears_keys_and_keeps_unknown_ones(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    result = edit_container(
        root,
        "M01",
        title="Jádro",
        values={
            "workflow": "build-test",
            "writes": ["src/", "tests/"],
            "specs_dir": "docs/specs",
            "docs_dir": "docs/app",
            "auto_continue": True,
        },
        clear=["source", "target"],
    )
    assert result.changed
    header = _header(root, M01_INDEX)
    assert header["title"] == "Jádro"
    assert header["workflow"] == "build-test"
    assert header["writes"] == ["src/", "tests/"]
    assert header["specs_dir"] == "docs/specs"
    assert header["docs_dir"] == "docs/app"
    assert header["auto_continue"] is True
    assert "source" not in header and "target" not in header
    assert header["owner"] == "alice"  # unknown key stays
    text = (root / M01_INDEX).read_text(encoding="utf-8")
    assert text.endswith("Jádro: datový model a API.\n")
    assert result.container.extra == {"owner": "alice"}

    again = edit_container(root, "M01", values={"writes": ["lib/"]})
    assert _header(root, M01_INDEX)["writes"] == ["lib/"]
    assert again.changed
    same = edit_container(root, "M01", values={"writes": ["lib/"]})
    assert not same.changed
    edit_container(root, "M01", clear=["auto_continue", "workflow"])
    header = _header(root, M01_INDEX)
    assert "auto_continue" not in header and "workflow" not in header
    assert header["owner"] == "alice"


def test_edit_rejects_bad_input(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    before = _snapshot(root)
    cases: list[tuple[dict[str, Any], str]] = [
        ({}, "no_changes"),
        ({"values": {"owner": "x"}}, "invalid_value"),
        ({"clear": ["auto_merge"]}, "invalid_value"),
        ({"values": {"workflow": "x"}, "clear": ["workflow"]}, "conflicting_options"),
        ({"values": {"writes": "src/"}}, "invalid_value"),
        ({"values": {"auto_continue": "yes"}}, "invalid_value"),
        ({"values": {"test": ["just", "check"]}}, "invalid_value"),  # removed key
        ({"title": " "}, "invalid_value"),
    ]
    for kwargs, code in cases:
        with pytest.raises(TaskEditError) as exc:
            edit_container(root, "M01", **kwargs)
        assert exc.value.code == code, kwargs
    with pytest.raises(TaskEditError) as exc:
        edit_container(root, "M01", values={"specs_dir": "../outside"})
    assert exc.value.code == "backlog_invalid"
    assert {i.code for i in exc.value.issues} == {"invalid_field"}
    with pytest.raises(TaskEditError) as exc:
        edit_container(root, "M01-S01-T01", title="Task")
    assert exc.value.code == "unknown_container"
    assert _snapshot(root) == before


def test_effective_sources_name_the_origin(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    write(
        root,
        ".factory/config.yaml",
        "levels: [module, step, task]\nbacklog_dir: backlog\ndocs_dir: docs\n",
    )
    edit_container(root, "M01-S01", values={"workflow": "own-flow"})
    edit_container(root, "M01", values={"docs_dir": "docs/app"})
    backlog = load_backlog(root)
    step = backlog.by_id["M01-S01"]
    sources = effective_sources(step, backlog.settings)
    assert sources["workflow"] == {
        "value": "own-flow",
        "origin": {"source": "own", "level": "step", "id": "M01-S01", "path": S01_INDEX},
    }
    assert sources["docs_dir"] == {
        "value": "docs/app",
        "origin": {"source": "inherited", "level": "module", "id": "M01", "path": M01_INDEX},
    }
    assert sources["specs_dir"] == {
        "value": "specs",
        "origin": {"source": "config", "path": ".factory/config.yaml", "key": "specs_dir"},
    }
    assert sources["auto_continue"] == {"value": False, "origin": {"source": "default"}}
    edit_container(root, "M01", clear=["docs_dir"])
    backlog = load_backlog(root)
    sources = effective_sources(backlog.by_id["M01-S01"], backlog.settings)
    assert sources["docs_dir"] == {
        "value": "docs",
        "origin": {"source": "config", "path": ".factory/config.yaml", "key": "docs_dir"},
    }
    assert "test" not in sources


# ── CLI ──────────────────────────────────────────────────────────────────────


def test_cli_add_and_edit(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    repo = ["--repo", str(root)]
    assert main(["backlog", "add", "--id", "M03", "--title", "Reporty", *repo]) == 0
    assert capsys.readouterr().out == "added module M03 backlog/M03-reporty/index.md\n"
    rc, env = run_json(
        capsys,
        ["backlog", "add", "M03", "--id", "M03-S01", "--title", "Export", "--body", "B", "--json"]
        + repo,
    )
    assert rc == 0
    data = env["data"]
    assert data["action"] == "add"
    assert data["path"] == "backlog/M03-reporty/S01-export/index.md"
    assert data["container"]["id"] == "M03-S01"
    assert data["container"]["parent"] == "M03"
    assert data["container"]["body"].strip() == "B"
    assert data["issues"] == []

    edit = ["backlog", "edit", "M01", "--title", "Jádro", "--workflow", "wf"]
    edit += ["--writes", "a/", "b/", "--auto-continue", "on"]
    edit += ["--clear", "source", "target", "--json", *repo]
    rc, env = run_json(capsys, edit)
    assert rc == 0
    container = env["data"]["container"]
    assert container["title"] == "Jádro"
    assert container["own"]["workflow"] == "wf"
    assert container["own"]["writes"] == ["a/", "b/"]
    assert container["own"]["auto_continue"] is True
    assert "source" not in container["own"]
    assert container["extra"] == {"owner": "alice"}
    assert container["effective"]["workflow"]["origin"]["source"] == "own"
    header = _header(root, M01_INDEX)
    assert header["owner"] == "alice"
    assert "target" not in header

    step_edit = ["backlog", "edit", "M01-S01", "--specs-dir", "docs/specs", "--json"]
    rc, env = run_json(capsys, step_edit + repo)
    assert rc == 0
    effective = env["data"]["container"]["effective"]
    assert effective["specs_dir"]["value"] == "docs/specs"
    assert "test" not in effective
    assert effective["workflow"] == {
        "value": "wf",
        "origin": {"source": "inherited", "level": "module", "id": "M01", "path": M01_INDEX},
    }
    rc, env = run_json(capsys, ["backlog", "edit", "M01", "--clear", "workflow", "--json"] + repo)
    assert rc == 0
    assert "workflow" not in _header(root, M01_INDEX)


def test_cli_rejects_invalid_writes(tmp_path: Path, capsys: Capsys) -> None:
    root = sample_repo(tmp_path)
    repo = ["--repo", str(root)]
    before = _snapshot(root)
    rc, env = run_json(capsys, ["backlog", "add", "--id", "M 3", "--title", "X", "--json"] + repo)
    assert rc == 2
    assert env["error"]["code"] == "invalid_id"
    rc, env = run_json(capsys, ["backlog", "add", "--id", "M01", "--title", "X", "--json"] + repo)
    assert rc == 1
    assert env["error"]["code"] == "backlog_invalid"
    assert [i["code"] for i in env["error"]["issues"]] == ["duplicate_id"]
    add_outside = ["backlog", "add", "M01", "--id", "M02-S05", "--title", "X", "--json"]
    rc, env = run_json(capsys, add_outside + repo)
    assert rc == 2
    assert env["error"]["code"] == "invalid_id"
    rc, env = run_json(capsys, ["backlog", "edit", "M01", "--json"] + repo)
    assert rc == 2
    assert env["error"]["code"] == "no_changes"
    rc, env = run_json(capsys, ["backlog", "edit", "M01", "--clear", "owner", "--json"] + repo)
    assert rc == 2
    assert env["error"]["code"] == "usage_error"
    assert main(["backlog", "add", "--id", "M01", "--title", "X", *repo]) == 1
    assert "duplicate_id" in capsys.readouterr().err
    assert _snapshot(root) == before


def test_project_paths_inherit_clear_and_isolate(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    keys = ("specs_dir", "docs_dir", "workdir")
    edits: dict[str, object] = {key: f"projects/core/{key}" for key in keys}
    edit_container(root, "M01", values=edits)
    edit_container(root, "M02", values={key: f"projects/ui/{key}" for key in keys})
    backlog = load_backlog(root)
    for key in keys:
        core = effective_sources(backlog.by_id["M01"], backlog.settings)[key]
        assert core["value"] == edits[key]
        assert core["origin"] == {
            "source": "own",
            "level": "module",
            "id": "M01",
            "path": M01_INDEX,
        }
        assert (
            effective_sources(backlog.by_id["M02"], backlog.settings)[key]["value"]
            == f"projects/ui/{key}"
        )
    edit_container(root, "M01", clear=list(keys))
    backlog = load_backlog(root)
    for key in keys:
        entry = effective_sources(backlog.by_id["M01"], backlog.settings)[key]
        assert entry["value"] == getattr(backlog.settings, key)
        assert entry["origin"] == {"source": "config", "path": ".factory/config.yaml", "key": key}
        assert (
            effective_sources(backlog.by_id["M02"], backlog.settings)[key]["value"]
            == f"projects/ui/{key}"
        )


def test_workdir_is_project_only_and_paths_cannot_escape(tmp_path: Path) -> None:
    root = sample_repo(tmp_path)
    before = _snapshot(root)
    with pytest.raises(TaskEditError):
        edit_container(root, "M01-S01", values={"workdir": "src"})
    for value in ("../outside", "/abs", "C:/outside", "..\\outside"):
        with pytest.raises(TaskEditError):
            edit_container(root, "M01", values={"workdir": value})
    assert _snapshot(root) == before
    (root / "link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(TaskEditError):
        edit_container(root, "M01", values={"docs_dir": "link/docs"})
