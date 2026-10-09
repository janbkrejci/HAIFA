"""Validation of library items: every problem is reported, all at once."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from library_tree import (
    AGENT_YAML,
    WORKFLOW,
    extension_files,
    library_agent,
    put,
    repo_agent,
    skill_files,
    symlink,
    tree,
)

from aifactory.engine.role_registry import Issue
from aifactory.library import (
    MAX_ITEM_BYTES,
    MAX_ITEM_FILES,
    LibraryError,
    check_library_item,
    check_repo_item,
    load_library_item,
    load_repo_item,
)


def codes(issues: list[Issue]) -> list[str]:
    return [issue.code for issue in issues]


def library_codes(root: Path, type: str, name: str) -> list[str]:
    return codes(check_library_item(root, type, name)[1])


# ── valid items ───────────────────────────────────────────────────────────────


def test_valid_items_pass(tmp_path: Path) -> None:
    library_agent(tmp_path)
    put(tmp_path, "workflows/plan.yaml", WORKFLOW)
    tree(tmp_path, "skills/lint", skill_files())
    tree(tmp_path, "extensions/x", extension_files())
    for type, name in [
        ("agent", "planner"),
        ("workflow", "plan"),
        ("skill", "lint"),
        ("extension", "x"),
    ]:
        item = load_library_item(tmp_path, type, name)
        assert (item.type, item.name) == (type, name)
        assert item.version.startswith("sha256:")


def test_library_agent_reads_purpose_and_defaults(tmp_path: Path) -> None:
    library_agent(tmp_path)
    item = load_library_item(tmp_path, "agent", "planner")
    assert item.purpose == "Plan it."
    assert item.defaults is not None
    assert item.defaults.harness == "claude"
    assert item.defaults.writes == ("$specs_dir/",)
    assert [f.path for f in item.files] == ["system.md", "user.md"]


def test_repo_agent_has_no_defaults_and_may_lack_purpose(tmp_path: Path) -> None:
    repo_agent(tmp_path, purpose=None)
    item = load_repo_item(tmp_path, "agent", "planner")
    assert item.defaults is None
    assert item.purpose == ""


# ── type and name ─────────────────────────────────────────────────────────────


def test_invalid_type(tmp_path: Path) -> None:
    assert library_codes(tmp_path, "prompt", "x") == ["invalid_type"]


@pytest.mark.parametrize("name", ["a" * 49, "Planner", "-x", "", "a_b", "a/b", "a.b"])
def test_invalid_name(tmp_path: Path, name: str) -> None:
    assert library_codes(tmp_path, "skill", name) == ["invalid_name"]
    assert codes(check_repo_item(tmp_path, "agent", name)[1]) == ["invalid_name"]


def test_longest_name_is_valid(tmp_path: Path) -> None:
    name = "a" * 48
    tree(tmp_path, f"extensions/{name}", {f"{name}.ts": (b"", False)})
    assert library_codes(tmp_path, "extension", name) == []


# ── reading ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("type", ["agent", "workflow", "skill", "extension"])
def test_missing_item(tmp_path: Path, type: str) -> None:
    assert library_codes(tmp_path, type, "nope") == ["missing_item"]


def test_workflow_directory_is_missing_item(tmp_path: Path) -> None:
    (tmp_path / "workflows/plan.yaml").mkdir(parents=True)
    assert library_codes(tmp_path, "workflow", "plan") == ["missing_item"]


def test_missing_agent_files_each_reported(tmp_path: Path) -> None:
    (tmp_path / "agents/planner").mkdir(parents=True)
    item, issues = check_library_item(tmp_path, "agent", "planner")
    assert item is None
    assert codes(issues) == ["missing_file"] * 3
    assert [i.path for i in issues] == [
        "agents/planner/agent.yaml",
        "agents/planner/system.md",
        "agents/planner/user.md",
    ]


def test_missing_repo_prompt(tmp_path: Path) -> None:
    repo_agent(tmp_path)
    (tmp_path / ".factory/prompts/planner/user.md").unlink()
    assert codes(check_repo_item(tmp_path, "agent", "planner")[1]) == ["missing_file"]


def test_symlinked_file(tmp_path: Path) -> None:
    folder = tree(tmp_path, "skills/lint", skill_files())
    put(tmp_path, "outside.txt", b"x")
    symlink(tmp_path / "outside.txt", folder / "link.txt")
    item, issues = check_library_item(tmp_path, "skill", "lint")
    assert codes(issues) == ["symlink"]
    assert issues[0].path == "skills/lint/link.txt"
    assert item is not None
    assert "link.txt" not in [f.path for f in item.files]


def test_symlinked_directory(tmp_path: Path) -> None:
    folder = tree(tmp_path, "extensions/x", extension_files())
    (tmp_path / "elsewhere").mkdir()
    put(tmp_path, "elsewhere/a.ts", b"x")
    symlink(tmp_path / "elsewhere", folder / "more")
    issues = check_library_item(tmp_path, "extension", "x")[1]
    assert codes(issues) == ["symlink"]
    assert issues[0].path == "extensions/x/more"


def test_symlinked_item_root(tmp_path: Path) -> None:
    tree(tmp_path, "real", skill_files())
    (tmp_path / "skills").mkdir()
    symlink(tmp_path / "real", tmp_path / "skills/lint")
    assert library_codes(tmp_path, "skill", "lint") == ["symlink"]


def test_symlinked_agent_prompt(tmp_path: Path) -> None:
    folder = library_agent(tmp_path)
    (folder / "user.md").unlink()
    put(tmp_path, "u.md", b"x")
    symlink(tmp_path / "u.md", folder / "user.md")
    assert library_codes(tmp_path, "agent", "planner") == ["symlink"]


def test_symlinked_workflow(tmp_path: Path) -> None:
    put(tmp_path, "real.yaml", WORKFLOW)
    (tmp_path / "workflows").mkdir()
    symlink(tmp_path / "real.yaml", tmp_path / "workflows/plan.yaml")
    assert library_codes(tmp_path, "workflow", "plan") == ["symlink"]


def test_special_file_is_not_a_file(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("no named pipes (os.mkfifo) on Windows")
    folder = tree(tmp_path, "skills/lint", skill_files())
    os.mkfifo(folder / "pipe")
    assert library_codes(tmp_path, "skill", "lint") == ["not_a_file"]


def test_too_many_files(tmp_path: Path) -> None:
    folder = tree(tmp_path, "skills/lint", skill_files())
    for index in range(MAX_ITEM_FILES - 1):
        put(folder, f"data/{index}.txt", b"x")
    assert library_codes(tmp_path, "skill", "lint") == ["too_many_files"]
    assert check_library_item(tmp_path, "skill", "lint")[0] is None


def test_at_most_max_files_is_fine(tmp_path: Path) -> None:
    folder = tree(tmp_path, "skills/lint", skill_files())
    for index in range(MAX_ITEM_FILES - 2):
        put(folder, f"data/{index}.txt", b"x")
    assert library_codes(tmp_path, "skill", "lint") == []


def test_too_large(tmp_path: Path) -> None:
    folder = tree(tmp_path, "extensions/x", {"x.ts": (b"", False)})
    put(folder, "big.bin", b"\0" * (MAX_ITEM_BYTES + 1))
    item, issues = check_library_item(tmp_path, "extension", "x")
    assert codes(issues) == ["too_large"]
    assert item is None


def test_empty_directories_are_ignored(tmp_path: Path) -> None:
    folder = tree(tmp_path, "extensions/x", extension_files())
    before = load_library_item(tmp_path, "extension", "x").version
    (folder / "empty").mkdir()
    assert load_library_item(tmp_path, "extension", "x").version == before


# ── agent.yaml ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("agent_yaml", "expected"),
    [
        ("purpose: [unclosed\n", ["invalid_yaml"]),
        ("- a\n- b\n", ["not_a_mapping"]),
        (AGENT_YAML + "color: red\n", ["unknown_key"]),
        ("defaults: {}\n", ["missing_purpose"]),
        ("purpose: '  '\n", ["missing_purpose"]),
        ("purpose: p\ndefaults: [a]\n", ["invalid_defaults"]),
        ("purpose: p\ndefaults: {harness: nope}\n", ["invalid_defaults"]),
        ("purpose: p\ndefaults: {thinking: huge}\n", ["invalid_defaults"]),
        ("purpose: p\ndefaults: {writes: [$foo/]}\n", ["invalid_defaults"]),
        ("purpose: p\ndefaults: {writes: [$specs_dir/$docs_dir/]}\n", ["invalid_defaults"]),
        ("purpose: p\ndefaults: {sandbox: true}\n", ["invalid_defaults"]),
        ("purpose: p\ndefaults: {skills: [Bad_Name]}\n", ["invalid_defaults"]),
        ("purpose: p\ndefaults: {harness: nope, thinking: huge}\n", ["invalid_defaults"] * 2),
    ],
)
def test_agent_yaml_problems(tmp_path: Path, agent_yaml: str, expected: list[str]) -> None:
    library_agent(tmp_path, agent_yaml=agent_yaml)
    item, issues = check_library_item(tmp_path, "agent", "planner")
    assert codes(issues) == expected
    assert {i.path for i in issues} == {"agents/planner/agent.yaml"}
    assert item is not None


def test_agent_yaml_not_utf8(tmp_path: Path) -> None:
    library_agent(tmp_path)
    put(tmp_path, "agents/planner/agent.yaml", b"purpose: \xff\n")
    assert library_codes(tmp_path, "agent", "planner") == ["not_utf8"]


def test_defaults_harness_alias_is_canonical(tmp_path: Path) -> None:
    library_agent(tmp_path, agent_yaml="purpose: p\ndefaults: {harness: claude, thinking: low}\n")
    item = load_library_item(tmp_path, "agent", "planner")
    assert item.defaults is not None
    assert item.defaults.thinking == "low"


# ── repo roster ───────────────────────────────────────────────────────────────


def test_unknown_agent_without_roster(tmp_path: Path) -> None:
    put(tmp_path, ".factory/prompts/planner/system.md", b"s")
    put(tmp_path, ".factory/prompts/planner/user.md", b"u")
    assert codes(check_repo_item(tmp_path, "agent", "planner")[1]) == ["unknown_agent"]


def test_unknown_agent_not_in_roster(tmp_path: Path) -> None:
    repo_agent(tmp_path, "builder")
    put(tmp_path, ".factory/prompts/planner/system.md", b"s")
    put(tmp_path, ".factory/prompts/planner/user.md", b"u")
    assert codes(check_repo_item(tmp_path, "agent", "planner")[1]) == ["unknown_agent"]


def test_unknown_agent_invalid_roster(tmp_path: Path) -> None:
    repo_agent(tmp_path)
    put(tmp_path, ".factory/agents.yaml", "agents: [unclosed\n")
    assert codes(check_repo_item(tmp_path, "agent", "planner")[1]) == ["unknown_agent"]


def test_invalid_purpose_in_roster(tmp_path: Path) -> None:
    repo_agent(tmp_path, purpose=["a"])
    assert codes(check_repo_item(tmp_path, "agent", "planner")[1]) == ["invalid_purpose"]


# ── workflow ──────────────────────────────────────────────────────────────────


def test_workflow_not_utf8(tmp_path: Path) -> None:
    put(tmp_path, "workflows/plan.yaml", b"name: \xff\n")
    assert library_codes(tmp_path, "workflow", "plan") == ["not_utf8"]


def test_workflow_invalid_yaml(tmp_path: Path) -> None:
    put(tmp_path, "workflows/plan.yaml", b"steps: [plan\n")
    assert library_codes(tmp_path, "workflow", "plan") == ["invalid_yaml"]


def test_workflow_not_a_mapping(tmp_path: Path) -> None:
    put(tmp_path, ".factory/workflows/plan.yaml", b"- plan\n")
    assert codes(check_repo_item(tmp_path, "workflow", "plan")[1]) == ["not_a_mapping"]


def test_workflow_unknown_step_uses_parser_codes(tmp_path: Path) -> None:
    put(tmp_path, "workflows/plan.yaml", b"name: plan\ndescription: d\nsteps: [nope]\n")
    issues = check_library_item(tmp_path, "workflow", "plan")[1]
    assert codes(issues) == ["unknown_step"]
    assert issues[0].path == "workflows/plan.yaml:steps[0]"


# ── skill and extension ───────────────────────────────────────────────────────


def test_missing_skill_md(tmp_path: Path) -> None:
    tree(tmp_path, "skills/lint", {"README.md": (b"x", False)})
    assert library_codes(tmp_path, "skill", "lint") == ["missing_skill_md"]


def test_skill_md_in_subfolder_does_not_count(tmp_path: Path) -> None:
    tree(tmp_path, "skills/lint", {"docs/SKILL.md": skill_files()["SKILL.md"]})
    assert library_codes(tmp_path, "skill", "lint") == ["missing_skill_md"]


@pytest.mark.parametrize(
    "text",
    [b"no header\n", b"---\nname: lint\n", b"---\n- a\n---\n", b"---\nname: [x\n---\n"],
)
def test_invalid_front_matter(tmp_path: Path, text: bytes) -> None:
    tree(tmp_path, "skills/lint", {"SKILL.md": (text, False)})
    assert library_codes(tmp_path, "skill", "lint") == ["invalid_front_matter"]


@pytest.mark.parametrize(
    "header",
    [b"name: other\ndescription: d\n", b"description: d\n"],
)
def test_name_mismatch(tmp_path: Path, header: bytes) -> None:
    tree(tmp_path, "skills/lint", {"SKILL.md": (b"---\n" + header + b"---\n", False)})
    assert library_codes(tmp_path, "skill", "lint") == ["name_mismatch"]


@pytest.mark.parametrize(
    "header",
    [b"name: lint\n", b"name: lint\ndescription: '  '\n", b"name: lint\ndescription: [a]\n"],
)
def test_missing_description(tmp_path: Path, header: bytes) -> None:
    tree(tmp_path, "skills/lint", {"SKILL.md": (b"---\n" + header + b"---\n", False)})
    assert library_codes(tmp_path, "skill", "lint") == ["missing_description"]


def test_skill_md_not_utf8(tmp_path: Path) -> None:
    tree(tmp_path, "skills/lint", {"SKILL.md": (b"---\nname: \xff\n---\n", False)})
    assert library_codes(tmp_path, "skill", "lint") == ["not_utf8"]


def test_missing_entry(tmp_path: Path) -> None:
    tree(tmp_path, ".factory/extensions/x", {"index.ts": (b"", False)})
    issues = check_repo_item(tmp_path, "extension", "x")[1]
    assert codes(issues) == ["missing_entry"]
    assert issues[0].path == ".factory/extensions/x/x.ts"


# ── all at once ───────────────────────────────────────────────────────────────


def test_every_problem_in_one_error(tmp_path: Path) -> None:
    folder = tree(tmp_path, "skills/lint", {"SKILL.md": (b"---\nname: other\n---\n", False)})
    put(tmp_path, "outside", b"x")
    symlink(tmp_path / "outside", folder / "link")
    with pytest.raises(LibraryError) as error:
        load_library_item(tmp_path, "skill", "lint")
    assert sorted(codes(error.value.issues)) == [
        "missing_description",
        "name_mismatch",
        "symlink",
    ]
    assert "skills/lint/SKILL.md: name_mismatch" in str(error.value)


def test_repo_errors_all_at_once(tmp_path: Path) -> None:
    (tmp_path / ".factory/prompts/planner").mkdir(parents=True)
    with pytest.raises(LibraryError) as error:
        load_repo_item(tmp_path, "agent", "planner")
    assert codes(error.value.issues) == ["unknown_agent", "missing_file", "missing_file"]
