"""Committed local repository for recommendation tests; no live model is used."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=test", "-c", "user.email=test@test", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def make_repo(root: Path) -> Path:
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    files = {
        ".factory/config.yaml": "base: main\nlevels: [project, step, task]\nbacklog_dir: backlog\n",
        ".factory/agents.yaml": (
            "defaults:\n"
            "  harness: claude\n"
            "  model: sonnet\n"
            "agents:\n"
            "  - name: planner\n"
            "  - name: builder\n"
        ),
        ".factory/workflows/plan.yaml": (
            "name: plan\n"
            "description: Analyze requirements before choosing an implementation approach\n"
            "steps: [plan]\n"
        ),
        ".gitignore": ".factory/data/\n",
        "backlog/P01/index.md": (
            "---\nid: P01\ntitle: Project\nwrites: [src/]\n---\nParent context\n"
        ),
        "backlog/P01/S01/index.md": "---\nid: P01-S01\ntitle: Step\n---\nStep context\n",
        "backlog/P01/S01/P01-S01-T01-first.md": (
            "---\nid: P01-S01-T01\ntitle: First\nstatus: todo\n---\nFull task body\n"
        ),
    }
    for agent in ("planner", "builder"):
        files[f".factory/prompts/{agent}/system.md"] = "Original system prompt"
        files[f".factory/prompts/{agent}/user.md"] = "Original task {{prompt}}"
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(root, "add", ".")
    git(root, "commit", "-qm", "fixture")
    return root


def output(name: str = "plan", *, new: bool = False) -> dict[str, object]:
    return {
        "status": "success",
        "decision": "new" if new else "existing",
        "workflow_name": name,
        "reason": "The task benefits from an initial analysis.",
        "workflow_yaml": (
            f"name: {name}\n"
            "description: Analyze requirements before choosing an implementation approach\n"
            "steps: [plan]\n"
        )
        if new
        else None,
    }
