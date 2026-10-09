"""Content versions: golden values, equal across layouts and names, sensitive to content."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
from library_tree import (
    SYSTEM,
    USER,
    WORKFLOW,
    extension_files,
    library_agent,
    put,
    repo_agent,
    skill_files,
    tree,
)

from aifactory.library import (
    ItemFile,
    agent_version,
    load_library_item,
    load_repo_item,
    tree_version,
    workflow_version,
)

NO_EXEC_BIT = pytest.mark.skipif(
    sys.platform == "win32", reason="Windows has no exec bit to derive the executable flag from"
)


def _ns(data: bytes) -> bytes:
    return str(len(data)).encode() + b":" + data + b","


GOLDEN_AGENT = "sha256:bcf4dcecf6df46547a2606b7630bb17eb1505e9c4dd2feee3df5690571e0fb79"
GOLDEN_WORKFLOW = "sha256:10a9e14c9e2667eb640db339b60d506114a15d19f7584c158b41c75ae183771f"
GOLDEN_SKILL = "sha256:3cbd80d16a84a39f62f769b35046de61e71d7420142cc405186758804e129ee0"
GOLDEN_EXTENSION = "sha256:80f84910d344501f050a74a4d89a039936d6f581021e38820832a4ee92e369ff"


def test_golden_agent_version() -> None:
    version = agent_version("Plan it.", b"sys\n", b"usr {{prompt}}\n")
    expected = hashlib.sha256(b"8:Plan it.," + b"4:sys\n," + b"15:usr {{prompt}}\n,").hexdigest()
    assert version == "sha256:" + expected
    assert version == GOLDEN_AGENT


def test_golden_workflow_version() -> None:
    data = b"name: plan\nsteps: [plan]\n"
    version = workflow_version(data)
    assert version == "sha256:" + hashlib.sha256(data).hexdigest()
    assert version == GOLDEN_WORKFLOW


def test_golden_skill_version() -> None:
    skill = b"---\nname: s\ndescription: d\n---\n"
    run = b"#!/bin/sh\n"
    files = [ItemFile("bin/run.sh", True, run), ItemFile("SKILL.md", False, skill)]
    expected = hashlib.sha256(
        _ns(b"SKILL.md") + b"0" + _ns(skill) + _ns(b"bin/run.sh") + b"1" + _ns(run)
    ).hexdigest()
    assert tree_version(files) == "sha256:" + expected
    assert tree_version(files) == GOLDEN_SKILL


def test_golden_extension_version() -> None:
    entry = b"export default {}\n"
    util = b"export {}\n"
    files = [ItemFile("x.ts", False, entry), ItemFile("lib/util.ts", False, util)]
    expected = hashlib.sha256(
        _ns(b"lib/util.ts") + b"0" + _ns(util) + _ns(b"x.ts") + b"0" + _ns(entry)
    ).hexdigest()
    assert tree_version(files) == "sha256:" + expected
    assert tree_version(files) == GOLDEN_EXTENSION


def test_agent_same_version_in_library_and_repo(tmp_path: Path) -> None:
    library_agent(tmp_path / "lib", "planner")
    repo_agent(tmp_path / "repo", "my-planner")
    lib = load_library_item(tmp_path / "lib", "agent", "planner")
    repo = load_repo_item(tmp_path / "repo", "agent", "my-planner")
    assert lib.version == repo.version == agent_version("Plan it.", SYSTEM, USER)


def test_workflow_same_version_in_library_and_repo_under_any_name(tmp_path: Path) -> None:
    put(tmp_path / "lib", "workflows/plan.yaml", WORKFLOW)
    put(tmp_path / "repo", ".factory/workflows/other.yaml", WORKFLOW)
    lib = load_library_item(tmp_path / "lib", "workflow", "plan")
    repo = load_repo_item(tmp_path / "repo", "workflow", "other")
    assert lib.version == repo.version == workflow_version(WORKFLOW)


@pytest.mark.parametrize(
    ("type", "library_dir", "repo_dir", "files"),
    [
        pytest.param(
            "skill", "skills/lint", ".claude/skills/lint", skill_files(), marks=NO_EXEC_BIT
        ),
        ("extension", "extensions/x", ".factory/extensions/x", extension_files()),
    ],
)
def test_tree_same_version_in_library_and_repo(
    tmp_path: Path,
    type: str,
    library_dir: str,
    repo_dir: str,
    files: dict[str, tuple[bytes, bool]],
) -> None:
    tree(tmp_path / "lib", library_dir, files)
    tree(tmp_path / "repo", repo_dir, files)
    name = library_dir.split("/")[1]
    lib = load_library_item(tmp_path / "lib", type, name)
    repo = load_repo_item(tmp_path / "repo", type, name)
    assert lib.version == repo.version
    assert lib.version == tree_version(
        ItemFile(path, executable, data) for path, (data, executable) in files.items()
    )


def test_tree_version_ignores_input_order() -> None:
    files = [ItemFile("x.ts", False, b"a")]
    assert tree_version(files) == tree_version(list(reversed(files)))


@pytest.mark.parametrize(
    ("purpose", "system", "user"),
    [
        ("Plan it!", SYSTEM, USER),
        ("Plan it.", b"sys\r\n", USER),
        ("Plan it.", SYSTEM, b"usr {{prompt}}!\n"),
    ],
)
def test_one_byte_changes_agent_version(purpose: str, system: bytes, user: bytes) -> None:
    assert agent_version(purpose, system, user) != agent_version("Plan it.", SYSTEM, USER)


def test_agent_parts_do_not_run_together() -> None:
    assert agent_version("a", b"b", b"") != agent_version("", b"ab", b"")


def test_one_byte_changes_workflow_version() -> None:
    assert workflow_version(WORKFLOW) != workflow_version(WORKFLOW + b" ")


def test_one_byte_changes_skill_version(tmp_path: Path) -> None:
    folder = tree(tmp_path, "skills/lint", skill_files())
    before = load_library_item(tmp_path, "skill", "lint").version
    (folder / "bin/run.sh").write_bytes(b"#!/bin/sh\nruff  .\n")
    assert load_library_item(tmp_path, "skill", "lint").version != before


@pytest.mark.parametrize(
    ("type", "rel", "files", "target"),
    [
        ("skill", "skills/lint", skill_files(), "SKILL.md"),
        ("extension", "extensions/x", extension_files(), "lib/util.ts"),
    ],
)
@NO_EXEC_BIT
def test_executable_bit_changes_tree_version(
    tmp_path: Path, type: str, rel: str, files: dict[str, tuple[bytes, bool]], target: str
) -> None:
    folder = tree(tmp_path, rel, files)
    name = rel.split("/")[1]
    before = load_library_item(tmp_path, type, name).version
    (folder / target).chmod(0o755)
    assert load_library_item(tmp_path, type, name).version != before


def test_executable_bit_does_not_change_agent_version(tmp_path: Path) -> None:
    folder = library_agent(tmp_path)
    before = load_library_item(tmp_path, "agent", "planner").version
    (folder / "system.md").chmod(0o755)
    assert load_library_item(tmp_path, "agent", "planner").version == before


def test_renaming_a_file_changes_skill_version(tmp_path: Path) -> None:
    folder = tree(tmp_path, "skills/lint", skill_files())
    before = load_library_item(tmp_path, "skill", "lint").version
    (folder / "bin/run.sh").rename(folder / "bin/go.sh")
    assert load_library_item(tmp_path, "skill", "lint").version != before


def test_defaults_do_not_change_agent_version(tmp_path: Path) -> None:
    library_agent(tmp_path / "a")
    library_agent(
        tmp_path / "b",
        agent_yaml=(
            "purpose: Plan it.\n"
            "defaults:\n"
            "  harness: pi\n"
            "  model: openai/gpt-5\n"
            "  thinking: high\n"
            "  writes: [$docs_dir/, src/]\n"
            "  color: red\n"
            "  skills: [lint]\n"
        ),
    )
    a = load_library_item(tmp_path / "a", "agent", "planner")
    b = load_library_item(tmp_path / "b", "agent", "planner")
    assert a.defaults != b.defaults
    assert a.version == b.version
