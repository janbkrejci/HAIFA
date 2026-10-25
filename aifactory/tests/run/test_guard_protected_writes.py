"""Explicit task writes unlock protected paths without widening an agent's writes."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from run_repo import T01, Script, commit_all, fake_env, git, make_run_repo, ok, write

from aifactory import failure
from aifactory.run import run_task

DIRECTORY = ".factory/prompts/reviewer/"
FILES = [DIRECTORY + "system.md", DIRECTORY + "user.md"]
TASK = "backlog/M01-core/S01-model/M01-S01-T01-schema.md"


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    repo = make_run_repo(tmp_path / "repo", "codex")
    task = (repo / TASK).read_text(encoding="utf-8")
    write(repo, TASK, task.replace("status: todo", f"status: todo\nwrites: [{DIRECTORY}]"))
    write(
        repo,
        ".factory/workflows/plan-commit.yaml",
        "name: plan-commit\ndescription: Build and commit\nsteps: [build, commit]\n",
    )
    commit_all(repo, "Allow reviewer prompts in the task")
    return repo


def create_prompts(wt: Path) -> None:
    assert not (wt / DIRECTORY).exists()
    for path in FILES:
        write(wt, path, "review prompt\n")
    assert "?? .factory/prompts/reviewer/" in git(wt, "status", "--short")


def test_new_protected_files_explicitly_allowed_by_task_survive(repo: Path, script: Script) -> None:
    script.on("builder", create_prompts)
    script.add("builder", ok(changed_files=FILES, commit_message="Add reviewer prompts"))

    result = run_task(repo, T01)

    assert result.run.state == "succeeded", result.run.error
    assert result.run.failure_kind is None
    for path in FILES:
        assert git(repo, "show", f"{result.run.branch}:{path}") == "review prompt"


@pytest.mark.parametrize("declaration", [None, "task", "step", "project"])
def test_implicit_writes_keep_protection_but_declared_wildcard_unlocks_it(
    repo: Path, script: Script, declaration: str | None
) -> None:
    levels = {
        "task": TASK,
        "step": "backlog/M01-core/S01-model/index.md",
        "project": "backlog/M01-core/index.md",
    }
    for level, path in levels.items():
        text = (repo / path).read_text(encoding="utf-8")
        text = "\n".join(line for line in text.splitlines() if not line.startswith("writes:"))
        if level == declaration:
            text = text.replace("---\n", "---\nwrites: ['**']\n", 1)
        write(repo, path, text + "\n")
    commit_all(repo, "Set writes declaration provenance")
    ordinary = "docs/endpoint.md"

    def build(wt: Path) -> None:
        create_prompts(wt)
        write(wt, ordinary, "ordinary file\n")

    script.on("builder", build)
    script.add("builder", ok(changed_files=[*FILES, ordinary]))

    result = run_task(repo, T01)

    if declaration is None:
        assert result.run.state == "failed"
        assert result.run.failure_kind == failure.WRITES_VIOLATION
        detail = result.run.failure_detail_dict()
        assert detail is not None and detail["paths"] == FILES
        assert all(not (Path(result.run.worktree) / path).exists() for path in FILES)
        assert all(path in (result.run.error or "") for path in FILES)
    else:
        assert result.run.state == "succeeded", result.run.error
        for path in FILES:
            assert git(repo, "show", f"{result.run.branch}:{path}") == "review prompt"
    assert (Path(result.run.worktree) / ordinary).read_text(encoding="utf-8") == "ordinary file\n"


def test_protected_sibling_outside_task_writes_is_still_rejected(
    repo: Path, script: Script
) -> None:
    outside = ".factory/prompts/reviewer-other/system.md"

    def build(wt: Path) -> None:
        create_prompts(wt)
        write(wt, outside, "unauthorized\n")

    script.on("builder", build)
    script.add("builder", ok(changed_files=[*FILES, outside]))

    result = run_task(repo, T01)

    assert result.run.state == "failed"
    assert result.run.failure_kind == failure.WRITES_VIOLATION
    detail = result.run.failure_detail_dict()
    assert detail is not None and detail["paths"] == [outside]
    assert not (Path(result.run.worktree) / outside).exists()
    for path in FILES:
        assert (Path(result.run.worktree) / path).read_text(encoding="utf-8") == "review prompt\n"
        assert path not in (result.run.error or "")


@pytest.mark.parametrize("writes", ["[]", "[src/]", f"[{DIRECTORY}]"])
def test_task_writes_preserve_agent_restrictions(repo: Path, script: Script, writes: str) -> None:
    roster = repo / ".factory/agents.yaml"
    write(
        repo,
        ".factory/agents.yaml",
        roster.read_text(encoding="utf-8").replace(
            "- name: builder", f"- name: builder\n    writes: {writes}"
        ),
    )
    commit_all(repo, "Set builder writes")
    script.on("builder", create_prompts)
    script.add("builder", ok(changed_files=FILES))

    result = run_task(repo, T01)

    if writes == f"[{DIRECTORY}]":
        assert result.run.state == "succeeded", result.run.error
    else:
        assert result.run.state == "failed"
        assert result.run.failure_kind == failure.WRITES_VIOLATION
        detail = result.run.failure_detail_dict()
        assert detail is not None and detail["paths"] == FILES
        assert all(not (Path(result.run.worktree) / path).exists() for path in FILES)
