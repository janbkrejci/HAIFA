"""A succeeded run that changed nothing: the task is done in base without a PR."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from run_repo import T01, Script, fake_env, git, make_run_repo, ok

from aifactory.backlog import Task, load_backlog
from aifactory.run import TaskRunStore, run_task


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


def test_run_without_changes_marks_task_done(repo: Path, script: Script) -> None:
    script.add("planner", ok(summary="already in base"))
    result = run_task(repo, T01)

    assert result.ok, (result.run.error, result.pr_error)
    assert result.done_without_pr and result.pr is None
    task = load_backlog(repo).by_id[T01]
    assert isinstance(task, Task) and task.status == "done"
    assert f"bez změn, běh {result.run.run_id}" in task.body
    subject = git(repo, "log", "-1", "--format=%s")
    assert subject == f"{T01}: hotovo bez změn (běh {result.run.run_id})"
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        assert store.prs_for_task(T01) == []
        row = store.get(result.run.run_id)
        assert row is not None and row.pr_error is None
    finally:
        store.close()
