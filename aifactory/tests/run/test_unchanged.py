"""A run that changed nothing: the task is done in base without a PR.

A succeeded run without commits, a builder that reports ``already_done`` with evidence,
and the dashboard's „Hotovo“ of a ``nothing_to_do`` run (only the backlog must change).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError
from run_repo import T01, Script, commit_all, fake_env, git, make_run_repo, ok, write
from starlette.testclient import TestClient

from aifactory import failure
from aifactory.backlog import Task, load_backlog
from aifactory.engine.data_types import BuildOutput
from aifactory.run import TaskRunError, TaskRunStore, run_task
from aifactory.run.store import FAILED, SUCCEEDED
from aifactory.run.unchanged import finish_nothing_to_do
from aifactory.web import create_app

BASE = "http://127.0.0.1:4700"


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


# -- the builder reports the work done already, or that only the backlog must change --

BUILD_TEST = (
    "name: build-test\ndescription: Build the task, test it and commit green code\n"
    "steps: [build, test_plan, test, commit]\naccept: test.passed\n"
)
BUILD_FIX = (
    "name: build-fix\ndescription: Build the task, fix it once and commit the code\n"
    "steps: [build, fix, commit]\n"
)
ALREADY_DONE = {"evidence": ["abc1234 Add schema", "src/app/schema.py"], "reason": "in base"}


def _use_workflow(repo: Path, name: str, text: str) -> None:
    write(repo, f".factory/workflows/{name}.yaml", text)
    index = repo / "backlog/M01-core/index.md"
    index.write_text(
        index.read_text(encoding="utf-8").replace("workflow: plan-commit", f"workflow: {name}"),
        encoding="utf-8",
    )
    commit_all(repo, f"tasks run {name}")


def _task(repo: Path) -> Task:
    task = load_backlog(repo).by_id[T01]
    assert isinstance(task, Task)
    return task


def test_builder_already_done_ends_the_run_done_without_changes(repo: Path, script: Script) -> None:
    _use_workflow(repo, "build-test", BUILD_TEST)
    script.add("builder", ok(summary="schema is in base", already_done=ALREADY_DONE))
    result = run_task(repo, T01)

    assert result.ok, (result.run.error, result.pr_error)
    assert result.run.state == SUCCEEDED
    assert result.done_without_pr and result.pr is None
    assert result.workflow_run is not None and result.workflow_run.already_done is not None
    # the workflow ended at the build: no tester, no test, no commit
    assert [c.agent for c in script.calls] == ["builder"]
    assert [r.step for r in result.workflow_run.records] == ["build"]
    task = _task(repo)
    assert task.status == "done"
    assert f"bez změn, běh {result.run.run_id}" in task.body
    assert "už hotovo: abc1234 Add schema, src/app/schema.py" in task.body
    subject = git(repo, "log", "-1", "--format=%s")
    assert subject == f"{T01}: hotovo bez změn (běh {result.run.run_id})"


def test_already_done_of_a_later_build_does_not_end_the_run(repo: Path, script: Script) -> None:
    _use_workflow(repo, "build-fix", BUILD_FIX)
    script.on("builder", lambda wt: write(wt, "src/app/schema.py", "SCHEMA = 1\n"))
    script.add(
        "builder",
        ok(changed_files=["src/app/schema.py"], commit_message="Add schema"),
        ok(summary="nothing to fix", already_done=ALREADY_DONE),
    )
    result = run_task(repo, T01)

    assert result.ok, (result.run.error, result.pr_error)
    assert not result.done_without_pr and result.pr is not None
    assert result.workflow_run is not None and result.workflow_run.already_done is None
    assert [r.step for r in result.workflow_run.records][-1] == "commit"
    assert _task(repo).status == "todo"


def test_already_done_needs_evidence_and_success() -> None:
    with pytest.raises(ValidationError):
        BuildOutput.model_validate({"status": "success", "already_done": {"evidence": []}})
    with pytest.raises(ValidationError):
        BuildOutput.model_validate({"status": "success", "already_done": {"evidence": [" "]}})
    with pytest.raises(ValidationError):
        BuildOutput.model_validate({"status": "fail", "already_done": {"evidence": ["abc1234"]}})
    out = BuildOutput.model_validate(
        {"status": "success", "already_done": {"evidence": [" abc1234 "]}}
    )
    assert out.already_done is not None and out.already_done.evidence == ["abc1234"]


def _backlog_only_run(repo: Path, script: Script) -> str:
    _use_workflow(repo, "build-test", BUILD_TEST)
    script.add(
        "builder",
        {
            "status": "fail",
            "summary": "only the front matter of the task must change",
            "fail_kind": "nothing_to_do",
        },
    )
    result = run_task(repo, T01)
    assert result.run.state == FAILED
    assert result.run.failure_kind == failure.NOTHING_TO_DO
    return result.run.run_id


def test_backlog_only_run_fails_nothing_to_do_and_is_marked_done(
    repo: Path, script: Script
) -> None:
    run_id = _backlog_only_run(repo, script)
    assert _task(repo).status == "todo"

    row, commit = finish_nothing_to_do(repo, run_id)
    assert row.run_id == run_id and commit.committed
    task = _task(repo)
    assert task.status == "done"
    assert f"bez změn, běh {run_id}" in task.body
    assert "důvod: builder: only the front matter of the task must change" in task.body
    assert git(repo, "log", "-1", "--format=%s") == f"{T01}: hotovo bez změn (běh {run_id})"


def test_only_a_nothing_to_do_run_is_marked_done(repo: Path, script: Script) -> None:
    script.add("planner", {"status": "fail", "summary": "gave up"})
    run_id = run_task(repo, T01).run.run_id
    with pytest.raises(TaskRunError) as caught:
        finish_nothing_to_do(repo, run_id)
    assert caught.value.code == "not_nothing_to_do"
    with pytest.raises(TaskRunError) as unknown:
        finish_nothing_to_do(repo, "nope")
    assert unknown.value.code == "unknown_run"
    assert _task(repo).status == "todo"


def test_dashboard_marks_a_nothing_to_do_run_done(
    repo: Path, script: Script, tmp_path: Path
) -> None:
    run_id = _backlog_only_run(repo, script)
    client = TestClient(create_app(repo, static_dir=tmp_path / "nostatic"), base_url=BASE)

    response = client.post(f"/api/runs/{run_id}/done", json={})
    body = response.json()
    assert response.status_code == 200, body
    assert body["data"]["task_id"] == T01
    assert body["data"]["commit"]["committed"] is True
    assert body["data"]["run"]["run_id"] == run_id
    assert _task(repo).status == "done"

    missing = client.post("/api/runs/nope/done", json={})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "unknown_run"
