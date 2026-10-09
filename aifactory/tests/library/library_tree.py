"""Write library items and repo copies into a temporary directory (helpers, not fixtures)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import yaml

WORKFLOW = b"name: plan\ndescription: Plan the task.\nsteps: [plan]\n"
SKILL_MD = b"---\nname: lint\ndescription: Lint the code.\n---\nRun the linter.\n"
AGENT_YAML = (
    "purpose: Plan it.\ndefaults:\n  harness: claude\n  model: opus\n  writes:\n    - $specs_dir/\n"
)
SYSTEM = b"sys\n"
USER = b"usr {{prompt}}\n"


def put(base: Path, rel: str, data: bytes | str, *, executable: bool = False) -> Path:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)
    path.chmod(0o755 if executable else 0o644)
    return path


def symlink(target: Path, link: Path) -> None:
    """Create ``link`` -> ``target``; on Windows skip the test when symlinks need a privilege."""
    try:
        os.symlink(target, link)
    except OSError as error:
        if sys.platform == "win32":
            pytest.skip(f"cannot create symlinks here: {error}")
        raise


def library_agent(
    root: Path,
    name: str = "planner",
    *,
    agent_yaml: str = AGENT_YAML,
    system: bytes = SYSTEM,
    user: bytes = USER,
) -> Path:
    folder = f"agents/{name}"
    put(root, f"{folder}/agent.yaml", agent_yaml)
    put(root, f"{folder}/system.md", system)
    put(root, f"{folder}/user.md", user)
    return root / folder


def repo_agent(
    repo: Path,
    name: str = "planner",
    *,
    purpose: object = "Plan it.",
    system: bytes = SYSTEM,
    user: bytes = USER,
) -> None:
    entry: dict[str, object] = {"name": name, "purpose": purpose}
    put(repo, ".factory/agents.yaml", yaml.safe_dump({"agents": [entry]}))
    put(repo, f".factory/prompts/{name}/system.md", system)
    put(repo, f".factory/prompts/{name}/user.md", user)


def skill_files(name: str = "lint") -> dict[str, tuple[bytes, bool]]:
    text = f"---\nname: {name}\ndescription: Lint the code.\n---\nRun the linter.\n"
    return {"SKILL.md": (text.encode(), False), "bin/run.sh": (b"#!/bin/sh\nruff .\n", True)}


def extension_files(name: str = "x") -> dict[str, tuple[bytes, bool]]:
    return {f"{name}.ts": (b"export default {}\n", False), "lib/util.ts": (b"export {}\n", False)}


def tree(base: Path, rel: str, files: dict[str, tuple[bytes, bool]]) -> Path:
    for path, (data, executable) in files.items():
        put(base, f"{rel}/{path}", data, executable=executable)
    return base / rel
