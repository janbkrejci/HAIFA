"""Temporary git repositories with a sample ``.factory/`` (helpers, not fixtures)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import repo_templates

AGENTS_YAML = """\
defaults:
  harness: claude
  model: sonnet
agents:
  - name: planner
    model: opus
    writes: [specs/]
  - name: builder
"""

FILES = {
    ".gitignore": ".factory/local.yaml\n",
    ".factory/config.yaml": "base: main\n",
    ".factory/agents.yaml": AGENTS_YAML,
    ".factory/prompts/planner/system.md": "You are the planner.\n",
    ".factory/prompts/planner/user.md": "Plan this: {{prompt}}\n",
    ".factory/prompts/builder/system.md": "You are the builder.\n",
    ".factory/prompts/builder/user.md": "Build this: {{prompt}}\n",
    ".factory/workflows/plan-build.yaml": "name: plan-build\nsteps: [plan, build]\n",
}


def git(repo: Path, *args: str) -> str:
    env = dict(os.environ)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    proc = subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=env,
        encoding="utf-8",
    )
    return proc.stdout


def write(repo: Path, rel: str, text: str) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD").strip()


def make_repo(path: Path) -> Path:
    """A git repo on ``main`` with the sample ``.factory/`` committed."""
    repo_templates.build(path, "config", _build_repo)
    return path


def _build_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    for rel, text in FILES.items():
        write(path, rel, text)
    commit_all(path, "factory config")
