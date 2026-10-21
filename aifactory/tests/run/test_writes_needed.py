"""An agent that needs paths outside the task's writes: ``writes_needed`` and its retry."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from run_repo import T01, Script, fake_env, git, make_run_repo, write
from starlette.testclient import TestClient

from aifactory import failure
from aifactory.backlog import find_task, load_for_edit
from aifactory.run import TaskRunError, TaskRunStore, run_task
from aifactory.run.allow_writes import plan_allow_writes
from aifactory.run.store import FAILED, SUCCEEDED
from aifactory.web import create_app
from cli_json import run_json

Capsys = pytest.CaptureFixture[str]
TASK_FILE = "backlog/M01-core/S01-model/M01-S01-T01-schema.md"
BASE = "http://127.0.0.1:4700"


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def _needs(*paths: str) -> dict[str, Any]:
    return {
        "status": "fail",
        "summary": "the change breaks tests outside writes",
        "fail_kind": "needs_writes",
        "needs_writes": [{"path": p, "reason": f"{p} must change with this task"} for p in paths],
    }


def _failed(repo: Path, script: Script, *paths: str) -> str:
    script.add("planner", _needs(*paths))
    result = run_task(repo, T01)
    assert result.run.state == FAILED
    assert result.run.failure_kind == failure.WRITES_NEEDED
    return result.run.run_id


def test_needs_writes_ends_the_run_as_writes_needed_without_follow_ups(
    repo: Path, script: Script
) -> None:
    script.add("planner", _needs("./README.md", "README.md", "tests/test_x.py"))
    result = run_task(repo, T01)

    assert result.run.state == FAILED
    assert result.run.failure_kind == failure.WRITES_NEEDED
    detail = result.run.failure_detail_dict()
    assert detail is not None
    assert detail["agent"] == "planner"
    assert detail["fail_kind"] == "needs_writes"
    assert detail["paths"] == ["README.md", "tests/test_x.py"]
    assert detail["needs_writes"][0] == {
        "path": "README.md",
        "reason": "./README.md must change with this task",
    }
    assert "needs writes: README.md, tests/test_x.py" in (result.run.error or "")
    assert result.follow_ups is None
    task = find_task(load_for_edit(repo), T01)
    assert task.depends_on == []
    assert git(repo, "status", "--porcelain", "--", "backlog") == ""


def test_needs_writes_without_paths_is_not_a_valid_envelope(repo: Path, script: Script) -> None:
    bare = {"status": "fail", "summary": "x", "fail_kind": "needs_writes"}
    script.add("planner", bare, bare, bare, bare, bare)
    result = run_task(repo, T01)
    assert result.run.state == FAILED
    assert result.run.failure_kind == failure.INVALID_OUTPUT


def test_retry_allow_writes_adds_the_needed_paths_and_finishes(
    repo: Path, script: Script, capsys: Capsys
) -> None:
    run_id = _failed(repo, script, "README.md")

    script.on("planner", lambda wt: write(wt, "README.md", "readme, extended\n"))
    script.add("planner", {"status": "success", "summary": "planned"})
    capsys.readouterr()
    code, data = run_json(
        capsys,
        ["task", "retry", T01, "--allow-writes", "--note", "go on", "--json", "--repo", str(repo)],
    )

    assert code == 0, data
    allowed = data["data"]["allow_writes"]
    assert allowed["run_id"] == run_id
    assert allowed["allow"] == ["README.md"]
    assert allowed["new_writes"] == ["src/app/", "README.md"]
    assert "README.md" in git(repo, "show", f"main:{TASK_FILE}")
    run = data["data"]["run"]
    assert run["run_id"] == run_id
    assert run["state"] == SUCCEEDED
    assert git(repo, "show", f"{run['branch']}:README.md") == "readme, extended"
    prompt = script.calls[-1].prompt
    note = prompt[prompt.index("## Retry note") :]
    assert "README.md" in note and "go on" in note
    assert "Continuing from phase: plan" in prompt


def test_protected_and_backlog_paths_are_refused(repo: Path, script: Script) -> None:
    run_id = _failed(repo, script, ".factory/config.yaml", "backlog/M01-core/x.md", "README.md")
    plan = plan_allow_writes(repo, T01)
    assert plan.run_id == run_id
    assert plan.allow == ["README.md"]
    assert {r.path: r.reason for r in plan.refused} == {
        ".factory/config.yaml": "protected",
        "backlog/M01-core/x.md": "backlog",
    }


def test_another_failure_has_no_paths_to_allow(repo: Path, script: Script) -> None:
    script.add("planner", {"status": "fail", "summary": "cannot"})
    assert run_task(repo, T01).run.failure_kind == failure.OTHER
    with pytest.raises(TaskRunError) as caught:
        plan_allow_writes(repo, T01)
    assert caught.value.code == "not_writes_violation"


class _Launcher:
    def __init__(self) -> None:
        self.notes: list[str | None] = []
        self.approves: list[str] = []

    def start_retry(self, repo: Path, task_id: str, run_id: str, **kw: Any) -> object:
        self.notes.append(kw.get("note"))
        return object()

    def start_approve(self, repo: Path, task_id: str, **kw: Any) -> None:
        self.approves.append(task_id)


def test_dashboard_allows_writes_needed(repo: Path, script: Script, tmp_path: Path) -> None:
    run_id = _failed(repo, script, "README.md")
    launcher = _Launcher()
    app = create_app(repo, static_dir=tmp_path / "nostatic", launcher=launcher)  # type: ignore[arg-type]
    client = TestClient(app, base_url=BASE)

    plan = client.get(f"/api/runs/{run_id}/allow-writes")
    assert plan.status_code == 200, plan.json()
    assert plan.json()["data"]["allow"] == ["README.md"]
    response = client.post(f"/api/runs/{run_id}/allow-writes", json={})
    assert response.status_code == 202, response.json()
    assert response.json()["data"]["action"] == "retry"
    assert launcher.notes and "README.md" in (launcher.notes[0] or "")


def test_ci_fix_run_is_not_retried_with_allow_writes(repo: Path, script: Script) -> None:
    run_id = _failed(repo, script, "README.md")
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        store.conn.execute("UPDATE task_runs SET workflow='ci-fix' WHERE run_id=?", (run_id,))
    finally:
        store.close()
    with pytest.raises(TaskRunError) as caught:
        plan_allow_writes(repo, T01)
    assert caught.value.code == "run_not_retryable"
    assert "--allow-writes" in caught.value.message
    assert plan_allow_writes(repo, T01, ci_fix=True).allow == ["README.md"]


def test_dashboard_allow_writes_of_a_ci_fix_run_starts_the_approve(
    repo: Path, script: Script, tmp_path: Path
) -> None:
    run_id = _failed(repo, script, "README.md")
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        store.conn.execute("UPDATE task_runs SET workflow='ci-fix' WHERE run_id=?", (run_id,))
    finally:
        store.close()
    launcher = _Launcher()
    app = create_app(repo, static_dir=tmp_path / "nostatic", launcher=launcher)  # type: ignore[arg-type]
    client = TestClient(app, base_url=BASE)

    plan = client.get(f"/api/runs/{run_id}/allow-writes")
    assert plan.status_code == 200, plan.json()
    assert plan.json()["data"]["allow"] == ["README.md"]
    response = client.post(f"/api/runs/{run_id}/allow-writes", json={})
    body = response.json()
    assert response.status_code == 202, body
    assert body["data"]["action"] == "approve" and body["data"]["started"] is True
    assert body["data"]["allow_writes"]["allow"] == ["README.md"]
    assert launcher.approves == [T01]
    assert launcher.notes == []  # no retry of the ci-fix run
    assert "README.md" in git(repo, "show", f"main:{TASK_FILE}")
