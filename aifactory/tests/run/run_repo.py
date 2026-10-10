"""A git repo with ``.factory/`` and a backlog for ``factory task run`` tests (not fixtures).

Runs go through the real engine with the fake harnesses of ``workflow_fakes``;
no test calls a model.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import repo_templates

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workflow"))

from workflow_fakes import (  # noqa: E402
    FakeHarness,
    Script,
    install_fake_harnesses,
    ok,
    plan_envelope,
    triage_envelope,
)

__all__ = [
    "SPEC",
    "DOC",
    "T01",
    "T02",
    "FakeHarness",
    "Script",
    "commit_all",
    "fake_env",
    "git",
    "make_run_repo",
    "ok",
    "PLAN_APPROVED",
    "plan_envelope",
    "scripted_plan",
    "triage_envelope",
    "write",
]

# the test-reviewer's approval of a test plan (seed agent, added to every roster)
PLAN_APPROVED: dict[str, Any] = {
    "status": "success",
    "approved": True,
    "summary": "plan fits",
    "findings": [],
    "blocking": [],
}

T01 = "M01-S01-T01"
T02 = "M01-S01-T02"
SPEC = "specs/M01-S01-T01-schema.md"
DOC = "app_docs/M01-S01-T01-schema.md"

USER_PROMPT = (
    "{{prompt}}\nctx={{context_handoff_dir}}\nspec={{spec_path}}\ndoc={{doc_path}}\n"
    "PREV<<{{previous_envelope}}>>PREV\n"
)


def agents_yaml(harness: str) -> str:
    return (
        f"defaults:\n  harness: {harness}\n  model: sonnet\n"
        "agents:\n  - name: planner\n  - name: builder\n  - name: tester\n  - name: documenter\n"
    )


def files(harness: str) -> dict[str, str]:
    result = {
        ".gitignore": ".factory/local.yaml\n",
        ".factory/config.yaml": "base: main\n",
        ".factory/agents.yaml": agents_yaml(harness),
        ".factory/workflows/plan-commit.yaml": (
            "name: plan-commit\ndescription: Plan the task and commit the plan\n"
            "steps: [plan, commit]\n"
        ),
        "backlog/M01-core/index.md": (
            "---\nid: M01\ntitle: Core\nworkflow: plan-commit\n---\n\nJádro.\n"
        ),
        "backlog/M01-core/S01-model/index.md": (
            "---\nid: M01-S01\ntitle: Model\nwrites: [src/app/]\n---\n\nModel.\n"
        ),
        "backlog/M01-core/S01-model/M01-S01-T01-schema.md": (
            f"---\nid: {T01}\ntitle: Schema\nstatus: todo\n---\n\n## Zadání\nNavrhnout schéma.\n"
        ),
        "backlog/M01-core/S01-model/M01-S01-T02-loader.md": (
            f"---\nid: {T02}\ntitle: Loader\nstatus: todo\ndepends_on: [{T01}]\n---\n\n"
            "## Zadání\nNačíst data.\n"
        ),
        "README.md": "readme\n",
        "src/app/__init__.py": "",
    }
    for agent in ("planner", "builder", "tester", "documenter"):
        result[f".factory/prompts/{agent}/system.md"] = f"You are the {agent}.\n"
        result[f".factory/prompts/{agent}/user.md"] = USER_PROMPT
    return result


def scripted_plan(script: Script, *argv: str) -> None:
    """A tester plan with the single check `argv` and the test-reviewer's approval of it."""
    script.add("tester", plan_envelope(*argv))
    script.add("test-reviewer", dict(PLAN_APPROVED))


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return proc.stdout.strip()


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def make_run_repo(path: Path, harness: str = "claude") -> Path:
    """A git repo on ``main`` with ``.factory/`` and a two-task backlog, all committed."""
    repo_templates.build(path, f"run-{harness}", lambda p: _build_run_repo(p, harness))
    return path.resolve()


def _build_run_repo(path: Path, harness: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "commit.gpgsign", "false")
    for rel, text in files(harness).items():
        write(path, rel, text)
    commit_all(path, "init")


def fake_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    """Fake harnesses, a fixed engineer name, and the signal handlers restored afterwards."""
    monkeypatch.setenv("ENGINEER_NAME", "tester")
    for key in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(key, "Test")
    for key in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(key, "test@example.com")
    script, _ = install_fake_harnesses(monkeypatch)
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    cwd = os.getcwd()
    try:
        yield script
    finally:
        os.chdir(cwd)
        for sig, handler in saved.items():
            signal.signal(sig, handler)
