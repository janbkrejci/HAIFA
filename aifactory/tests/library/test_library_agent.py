"""``writes`` variables and roster entries of library agents."""

from __future__ import annotations

from pathlib import Path

import pytest
from library_tree import library_agent, put

from aifactory.config.settings import ProjectSettings
from aifactory.library import Item, expand_writes, load_library_item, roster_entry

SETTINGS = ProjectSettings()


def test_expand_specs_dir() -> None:
    assert expand_writes(["$specs_dir/"], SETTINGS) == ["specs/"]


def test_expand_docs_dir_with_subpath() -> None:
    settings = ProjectSettings(docs_dir="docs")
    assert expand_writes(["$docs_dir/sub/"], settings) == ["docs/sub/"]


def test_expand_strips_trailing_slash_of_setting() -> None:
    settings = ProjectSettings(specs_dir="plans/")
    assert expand_writes(["$specs_dir/a.md"], settings) == ["plans/a.md"]


def test_expand_none_empty_and_plain() -> None:
    assert expand_writes(None, SETTINGS) is None
    assert expand_writes([], SETTINGS) == []
    assert expand_writes(["src/", "README.md"], SETTINGS) == ["src/", "README.md"]


def test_expand_rejects_unknown_variable() -> None:
    with pytest.raises(ValueError):
        expand_writes(["$foo/"], SETTINGS)


def test_roster_entry_skips_unset_and_library_only_keys(tmp_path: Path) -> None:
    library_agent(
        tmp_path,
        agent_yaml=(
            "purpose: Plan it.\n"
            "defaults:\n"
            "  model: opus\n"
            "  tools: [Read, Grep]\n"
            "  writes: [$specs_dir/]\n"
            "  skills: [lint]\n"
            "  extensions: [x]\n"
        ),
    )
    item = load_library_item(tmp_path, "agent", "planner")
    assert roster_entry(item, ProjectSettings(specs_dir="plans")) == {
        "name": "planner",
        "purpose": "Plan it.",
        "model": "opus",
        "tools": ["Read", "Grep"],
        "writes": ["plans/"],
    }


def test_roster_entry_full(tmp_path: Path) -> None:
    library_agent(
        tmp_path,
        agent_yaml=(
            "purpose: p\n"
            "defaults: {harness: claude, model: opus, thinking: low, writes: [], color: red}\n"
        ),
    )
    item = load_library_item(tmp_path, "agent", "planner")
    assert roster_entry(item, SETTINGS) == {
        "name": "planner",
        "purpose": "p",
        "harness": "claude",
        "model": "opus",
        "thinking": "low",
        "writes": [],
        "color": "red",
    }


def test_roster_entry_needs_library_agent(tmp_path: Path) -> None:
    put(tmp_path, "workflows/plan.yaml", b"name: plan\ndescription: d\nsteps: [plan]\n")
    workflow = load_library_item(tmp_path, "workflow", "plan")
    with pytest.raises(ValueError):
        roster_entry(workflow, SETTINGS)
    with pytest.raises(ValueError):
        roster_entry(Item(type="agent", name="a", files=()), SETTINGS)
