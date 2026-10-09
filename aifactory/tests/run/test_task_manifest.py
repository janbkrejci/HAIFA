"""Runs in a repo with ``.factory/manifest.yaml``: format gate and workflows only from the repo."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from run_repo import T01, Script, commit_all, fake_env, git, make_run_repo, write

from aifactory.config import MANIFEST_FILE, WorktreeSource, load_config
from aifactory.run import TaskRunError, run_task
from aifactory.run.task import named_workflow
from aifactory.workflow import DEFAULT_WORKFLOWS_DIR, load_workflow

MANIFEST = "format: 1\nwritten_by: 0.2.0\nlibrary: null\n"


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def _nothing_created(repo: Path) -> None:
    worktrees = repo / ".factory" / "worktrees"
    assert not worktrees.exists() or not any(worktrees.iterdir())
    assert git(repo, "for-each-ref", "refs/heads/factory/") == ""


def test_newer_format_stops_the_run_before_start(repo: Path, script: Script) -> None:
    write(repo, MANIFEST_FILE, "format: 2\nwritten_by: 9.0.0\n")
    commit_all(repo, "future manifest")
    with pytest.raises(TaskRunError) as exc:
        run_task(repo, T01)
    assert exc.value.code == "format_unsupported"
    assert "factory upgrade" in exc.value.message
    _nothing_created(repo)
    assert script.calls == []


def test_without_manifest_packaged_workflows_still_resolve(repo: Path) -> None:
    config = load_config(WorktreeSource(repo))
    assert config.manifest is None
    assert named_workflow("plan-commit", config, T01).name == "plan-commit"
    assert named_workflow("plan", config, T01).name == "plan"


def test_with_manifest_workflows_come_only_from_the_repo(repo: Path) -> None:
    write(repo, MANIFEST_FILE, MANIFEST)
    config = load_config(WorktreeSource(repo))
    assert config.manifest is not None
    assert named_workflow("plan-commit", config, T01).name == "plan-commit"
    with pytest.raises(TaskRunError) as exc:
        named_workflow("plan", config, T01)
    assert exc.value.code == "unknown_workflow"
    assert "factory config add workflow plan" in exc.value.message


def test_with_manifest_resolve_comes_from_the_package(repo: Path) -> None:
    write(repo, MANIFEST_FILE, MANIFEST)
    write(repo, ".factory/workflows/resolve.yaml", "name: resolve\nsteps: [plan]\n")
    config = load_config(WorktreeSource(repo))
    for name in ("resolve", "resolve-reviewed"):
        packaged = load_workflow(DEFAULT_WORKFLOWS_DIR / f"{name}.yaml", config.roles)
        assert named_workflow(name, config, T01) == packaged


def test_run_with_workflow_missing_in_repo_fails_before_start(repo: Path, script: Script) -> None:
    write(repo, MANIFEST_FILE, MANIFEST)
    write(
        repo,
        "backlog/M01-core/S01-model/M01-S01-T04-odd.md",
        "---\nid: M01-S01-T04\ntitle: Odd\nstatus: todo\nworkflow: plan\n---\n",
    )
    commit_all(repo, "manifest and a task with a packaged workflow")
    with pytest.raises(TaskRunError) as exc:
        run_task(repo, "M01-S01-T04")
    assert exc.value.code == "unknown_workflow"
    _nothing_created(repo)
    assert script.calls == []
