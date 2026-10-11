"""Runs inherit agents, workflows and skills from the library; the repo's copy wins."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from run_repo import SPEC, T01, Script, commit_all, fake_env, git, make_run_repo, ok, write

from aifactory.library import store
from aifactory.run import TaskRunStore, run_task

LIBRARY_PLANNER = "You are the LIBRARY planner.\n"
SKILL_MD = "---\nname: lint\ndescription: Lint the code.\n---\nRun the linter.\n"
PLAN_COMMIT = "name: plan-commit\ndescription: Plan and commit\nsteps: [plan, commit]\n"


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="library")
def library_fixture(script: Script) -> str:
    """The library from the seed plus its own planner prompt, a workflow and a skill."""
    store.init_library("team")
    root = store.library_root()
    write(root, "agents/planner/system.md", LIBRARY_PLANNER)
    write(root, "workflows/plan-commit.yaml", PLAN_COMMIT)
    write(root, "skills/lint/SKILL.md", SKILL_MD)
    return commit_all(root, "team planner, plan-commit and lint")


def _plan(script: Script) -> None:
    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add the spec"))


def _system_prompt(repo: Path, run_id: str) -> str:
    path = repo / ".factory/data/sessions" / run_id / "planner/prompts/system.md"
    return path.read_text(encoding="utf-8")


def test_repo_without_agents_and_workflows_runs_with_the_library(
    tmp_path: Path, script: Script, library: str
) -> None:
    repo = make_run_repo(tmp_path / "repo")
    for rel in (".factory/agents.yaml", ".factory/prompts", ".factory/workflows"):
        path = repo / rel
        shutil.rmtree(path) if path.is_dir() else path.unlink()
    commit_all(repo, "only config.yaml")
    _plan(script)

    row = run_task(repo, T01).run

    assert row.state == "succeeded", row.error
    assert row.workflow == "plan-commit"
    assert row.library_commit == library
    assert _system_prompt(repo, row.run_id).startswith(LIBRARY_PLANNER)
    runs = TaskRunStore(repo / ".factory/trace.db")
    try:
        stored = runs.get(row.run_id)
    finally:
        runs.close()
    assert stored is not None and stored.library_commit == library
    # the library skill is in the worktree for claude and codex, but never committed
    worktree = Path(row.worktree)
    for top in (".claude/skills", ".agents/skills"):
        assert (worktree / top / "lint/SKILL.md").read_text(encoding="utf-8") == SKILL_MD
    assert git(worktree, "status", "--porcelain") == ""
    assert ".claude/" not in git(repo, "ls-tree", "-r", "--name-only", row.branch)


def test_the_repo_copy_wins_over_the_library(tmp_path: Path, script: Script, library: str) -> None:
    repo = make_run_repo(tmp_path / "repo")
    write(repo, ".claude/skills/lint/SKILL.md", SKILL_MD.replace("linter", "repo linter"))
    commit_all(repo, "own lint skill")
    _plan(script)

    row = run_task(repo, T01).run

    assert row.state == "succeeded", row.error
    assert row.library_commit == library
    assert _system_prompt(repo, row.run_id).startswith("You are the planner.\n")
    worktree = Path(row.worktree)
    assert "repo linter" in (worktree / ".claude/skills/lint/SKILL.md").read_text()
    assert not (worktree / ".agents/skills/lint").exists()


def test_without_a_library_the_run_reads_the_seed(tmp_path: Path, script: Script) -> None:
    repo = make_run_repo(tmp_path / "repo")
    _plan(script)

    row = run_task(repo, T01).run

    assert row.state == "succeeded", row.error
    assert row.library_commit is None
