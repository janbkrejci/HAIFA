"""„Povolit tyto cesty a pokračovat“: a ``writes_violation`` run extends the task's writes
and continues (``factory task retry --allow-writes``, ``/api/runs/{id}/allow-writes``).

Real git and engine, fake harnesses (``run_repo``); no model is called.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from run_repo import T01, Script, fake_env, git, make_run_repo, ok, write
from starlette.testclient import TestClient

from aifactory import failure
from aifactory.backlog import find_task, load_for_edit
from aifactory.run import TaskRunError, TaskRunStore, run_task
from aifactory.run.allow_writes import allow_writes, plan_allow_writes, violation_paths
from aifactory.run.scope import effective_task_writes
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


def _failed_run(repo: Path, script: Script, *paths: str, main: str | None = None) -> str:
    """A run of T01 whose planner writes `paths` in its worktree (and `main` in the repo)."""

    def outside(wt: Path) -> None:
        for path in paths:
            write(wt, path, "outside\n")
        if main is not None:
            write(repo, main, "hijacked\n")

    script.on("planner", outside)
    script.add("planner", ok())
    result = run_task(repo, T01)
    assert result.run.state == FAILED
    assert result.run.failure_kind == failure.WRITES_VIOLATION
    return result.run.run_id


def _writes_in_base(repo: Path) -> str:
    return git(repo, "show", f"main:{TASK_FILE}")


def test_allow_writes_extends_writes_and_the_retry_finishes(
    repo: Path, script: Script, capsys: Capsys
) -> None:
    run_id = _failed_run(repo, script, "README.md")
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        detail = store.get(run_id).failure_detail_dict()  # type: ignore[union-attr]
    finally:
        store.close()
    assert detail is not None and detail["paths"] == ["README.md"]
    assert detail["main_paths"] == []

    # the retry: the planner writes README.md again, now inside writes
    script.on("planner", lambda wt: write(wt, "README.md", "readme, extended\n"))
    script.add("planner", ok())
    capsys.readouterr()
    code, data = run_json(
        capsys, ["task", "retry", T01, "--allow-writes", "--json", "--repo", str(repo)]
    )

    assert code == 0, data
    allowed = data["data"]["allow_writes"]
    assert allowed["run_id"] == run_id
    assert allowed["allow"] == ["README.md"]
    assert allowed["new_writes"] == ["src/app/", "README.md"]
    assert allowed["commit"]["committed"] is True
    assert "README.md" in _writes_in_base(repo)
    assert git(repo, "status", "--porcelain", "--", "backlog") == ""
    task = find_task(load_for_edit(repo), T01)
    assert effective_task_writes(task) == ("src/app/", "README.md")
    run = data["data"]["run"]
    assert run["run_id"] == run_id
    assert run["state"] == SUCCEEDED
    assert run["attempt"] == 2
    branch = run["branch"]
    assert git(repo, "show", f"{branch}:README.md") == "readme, extended"


def test_protected_backlog_and_main_checkout_paths_are_refused(
    repo: Path, script: Script, capsys: Capsys
) -> None:
    run_id = _failed_run(
        repo, script, ".factory/notes.md", "backlog/M01-core/extra.md", main="README.md"
    )
    plan = plan_allow_writes(repo, T01)
    assert plan.run_id == run_id
    assert plan.allow == []
    assert {r.path: r.reason for r in plan.refused} == {
        ".factory/notes.md": "protected",
        "backlog/M01-core/extra.md": "backlog",
        "README.md": "main_checkout",
    }
    before = _writes_in_base(repo)
    capsys.readouterr()
    code, data = run_json(
        capsys, ["task", "retry", T01, "--allow-writes", "--json", "--repo", str(repo)]
    )
    assert code != 0
    assert data["error"]["code"] == "nothing_to_allow"
    assert "protected_files" in data["error"]["message"]
    assert _writes_in_base(repo) == before
    assert git(repo, "status", "--porcelain", "--", "backlog") == ""


def test_only_a_writes_violation_has_paths_to_allow(repo: Path, script: Script) -> None:
    script.add("planner", {"status": "fail", "summary": "cannot"})
    assert run_task(repo, T01).run.state == FAILED
    with pytest.raises(TaskRunError) as caught:
        allow_writes(repo, T01)
    assert caught.value.code == "not_writes_violation"


def test_paths_of_an_older_run_come_from_its_problems() -> None:
    detail = {
        "problems": [
            "worktree: HEAD — agent committed, reset to abc1234",
            "worktree: docs/x.md — deleted",
            "main checkout: README.md — restored",
        ]
    }
    assert violation_paths(detail) == (["docs/x.md"], [])


class _Launcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def start_retry(
        self,
        repo: Path,
        task_id: str,
        run_id: str,
        *,
        note: str | None = None,
        from_phase: str | None = None,
        timeout: float = 30.0,
    ) -> object:
        self.calls.append((task_id, run_id, note))
        return object()


def test_dashboard_plan_and_action(repo: Path, script: Script, tmp_path: Path) -> None:
    run_id = _failed_run(repo, script, "README.md", ".factory/x.md")
    launcher = _Launcher()
    app = create_app(repo, static_dir=tmp_path / "nostatic", launcher=launcher)  # type: ignore[arg-type]
    client = TestClient(app, base_url=BASE)

    response = client.get(f"/api/runs/{run_id}/allow-writes")
    assert response.status_code == 200, response.json()
    plan = response.json()["data"]
    assert plan["allow"] == ["README.md"]
    assert [(r["path"], r["reason"]) for r in plan["refused"]] == [(".factory/x.md", "protected")]

    response = client.post(f"/api/runs/{run_id}/allow-writes", json={"note": " go "})
    body = response.json()
    assert response.status_code == 202, body
    assert body["data"]["allow_writes"]["new_writes"] == ["src/app/", "README.md"]
    assert [(t, r) for t, r, _ in launcher.calls] == [(T01, run_id)]
    note = launcher.calls[0][2] or ""
    assert "README.md" in note and ".factory/x.md" in note and note.endswith("go")
    assert "README.md" in _writes_in_base(repo)

    # The permissions are already committed: retry without another backlog edit.
    before = git(repo, "rev-parse", "main")
    again = client.post(f"/api/runs/{run_id}/allow-writes", json={})
    assert again.status_code == 202, again.json()
    assert again.json()["data"]["allow_writes"]["commit"]["committed"] is False
    assert git(repo, "rev-parse", "main") == before
    assert len(launcher.calls) == 2
    assert ".factory/x.md" in (launcher.calls[-1][2] or "")


def test_allow_writes_with_base_changes_pr_waits_for_the_backlog_pr(
    tmp_path: Path, script: Script, capsys: Capsys
) -> None:
    repo = make_run_repo(tmp_path / "pr-repo")
    config = (repo / ".factory/config.yaml").read_text(encoding="utf-8")
    write(repo, ".factory/config.yaml", f"{config}base_changes: pr\nbase_pr_merge: manual\n")
    git(repo, "add", ".factory/config.yaml")
    git(repo, "commit", "-q", "-m", "factory changes base through pull requests")
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "-u", "origin", "main")
    run_id = _failed_run(repo, script, "README.md")
    before = git(repo, "rev-parse", "main")
    calls = len(script.calls)

    capsys.readouterr()
    code, data = run_json(
        capsys, ["task", "retry", T01, "--allow-writes", "--json", "--repo", str(repo)]
    )

    assert code == 2, data
    assert data["error"]["code"] == "writes_in_pr"
    assert "after it is merged" in data["error"]["message"]
    # base did not move, the change waits on the backlog PR branch
    assert git(repo, "rev-parse", "main") == before
    assert "README.md" in git(bare, "show", f"factory-backlog/1:{TASK_FILE}")
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        row = store.get(run_id)
    finally:
        store.close()
    assert row is not None
    assert (row.state, row.attempt) == (FAILED, 1)
    assert len(script.calls) == calls  # no agent ran again
    assert git(repo, "status", "--porcelain", "--", "backlog") == ""


@pytest.mark.parametrize("result_kind", ["no-op", "committed", "merged-pr", "partial"])
def test_retry_refuses_writes_missing_from_base(
    repo: Path, script: Script, capsys: Capsys, monkeypatch: pytest.MonkeyPatch, result_kind: str
) -> None:
    from importlib import import_module

    from aifactory.backlog import BacklogCommit, commit_backlog, edit_task

    module = import_module("aifactory.run.allow_writes")
    run_id = _failed_run(repo, script, "README.md", "docs/extra.md")
    calls = len(script.calls)

    def incomplete_commit(root: Path, message: str) -> BacklogCommit:
        if result_kind == "partial":
            edit_task(root, T01, writes=["src/app/", "README.md"])
            return commit_backlog(root, message)
        return BacklogCommit(
            committed=result_kind != "no-op",
            commit=None,
            base="main",
            paths=[],
            pushed=False,
            pr={"url": "https://example.test/pr/1"} if result_kind == "merged-pr" else None,
            merged=result_kind == "merged-pr",
        )

    monkeypatch.setattr(module, "commit_backlog", incomplete_commit)
    capsys.readouterr()
    code, data = run_json(
        capsys, ["task", "retry", T01, "--allow-writes", "--json", "--repo", str(repo)]
    )
    assert code == 2, data
    assert data["error"]["code"] == "writes_not_committed"
    message = data["error"]["message"]
    assert "docs/extra.md" in message
    assert ("README.md" in message) == (result_kind != "partial")
    assert "commit the backlog" in message
    assert f"factory task retry {T01}" in message
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        row = store.get(run_id)
    finally:
        store.close()
    assert row is not None
    assert (row.state, row.attempt) == (FAILED, 1)
    assert len(script.calls) == calls
    assert git(repo, "status", "--porcelain", "--", "backlog") == ""


@pytest.mark.parametrize("result_kind", ["no-op", "merged-pr"])
def test_all_commit_results_verify_effective_writes_in_base(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch, result_kind: str
) -> None:
    from dataclasses import replace
    from importlib import import_module

    from aifactory.backlog import BacklogCommit, commit_backlog, edit_container, edit_task

    module = import_module("aifactory.run.allow_writes")
    _failed_run(repo, script, "docs/extra.md")

    def commit_inherited_writes(root: Path, message: str) -> BacklogCommit:
        # The path is covered through an inherited directory, not an own literal path.
        edit_container(root, "M01-S01", values={"writes": ["src/app/", "docs/"]})
        edit_task(root, T01, clear_writes=True)
        result = commit_backlog(root, message)
        if result_kind == "no-op":
            return replace(result, committed=False)
        return replace(result, pr={"url": "https://example.test/pr/1"}, merged=True)

    monkeypatch.setattr(module, "commit_backlog", commit_inherited_writes)
    result = allow_writes(repo, T01)
    assert result.plan.allow == ["docs/extra.md"]
    assert "docs/" in _writes_in_base(repo) or "docs/" in git(
        repo, "show", "main:backlog/M01-core/S01-model/index.md"
    )


@pytest.mark.parametrize(
    "remote_change",
    ["none", "unrelated", "writes", "synced-writes", "dirty-unrelated", "dirty-writes"],
)
def test_retry_updates_base_before_allowing_writes(
    repo: Path, script: Script, capsys: Capsys, tmp_path: Path, remote_change: str
) -> None:
    from aifactory.backlog import edit_task

    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "-u", "origin", "main")
    run_id = _failed_run(repo, script, "README.md")
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(bare), str(other))
    git(other, "config", "user.name", "Test")
    git(other, "config", "user.email", "test@example.test")
    if remote_change in ("writes", "synced-writes", "dirty-writes"):
        edit_task(other, T01, writes=["src/app/", "README.md"])
    elif remote_change in ("unrelated", "dirty-unrelated"):
        write(other, "remote.txt", "remote change\n")
    if remote_change != "none":
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "advance remote")
        git(other, "push", "-q", "origin", "main")
    remote_tip = git(other, "rev-parse", "HEAD")
    if remote_change == "synced-writes":
        git(repo, "pull", "--ff-only", "-q")
    if remote_change.startswith("dirty-"):
        write(repo, "README.md", "operator staged change\n")
        git(repo, "add", "README.md")
        write(repo, "README.md", "operator staged and unstaged change\n")
    before_staged = git(repo, "diff", "--cached", "--", "README.md")
    before_unstaged = git(repo, "diff", "--", "README.md")
    before_readme = (repo / "README.md").read_bytes()
    script.on("planner", lambda wt: write(wt, "README.md", "allowed\n"))
    script.add("planner", ok())
    capsys.readouterr()
    code, data = run_json(
        capsys, ["task", "retry", T01, "--allow-writes", "--json", "--repo", str(repo)]
    )
    assert code == 0, data
    assert data["data"]["run"]["run_id"] == run_id
    assert data["data"]["run"]["state"] == SUCCEEDED
    no_edit = remote_change in ("writes", "synced-writes", "dirty-writes")
    assert data["data"]["allow_writes"]["commit"]["committed"] is not no_edit
    if no_edit:
        assert git(repo, "rev-parse", "main") == remote_tip
    assert "README.md" in _writes_in_base(repo)
    assert git(repo, "diff", "--cached", "--", "README.md") == before_staged
    assert git(repo, "diff", "--", "README.md") == before_unstaged
    assert (repo / "README.md").read_bytes() == before_readme
    assert git(repo, "status", "--porcelain", "--", "backlog") == ""


@pytest.mark.parametrize("failure_point", ["edit", "commit"])
def test_failed_allow_writes_restores_file_and_index(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch, failure_point: str
) -> None:
    from importlib import import_module

    module = import_module("aifactory.run.allow_writes")
    _failed_run(repo, script, "README.md")
    # Preserve an operator's pre-existing staged and unstaged task changes exactly.
    task = repo / TASK_FILE
    task.write_bytes(task.read_bytes() + b"\nOperator's staged note.\n")
    git(repo, "add", TASK_FILE)
    task.write_bytes(task.read_bytes() + b"Unstaged note.\n")
    before = task.read_bytes()
    staged = git(repo, "diff", "--cached")
    original_edit = module.edit_task

    def fail_edit(root: Path, task_id: str, *, writes: list[str]) -> None:
        original_edit(root, task_id, writes=writes)
        raise RuntimeError("edit failed")

    def fail_commit(root: Path, message: str) -> None:
        git(root, "add", TASK_FILE)
        raise RuntimeError("commit failed")

    monkeypatch.setattr(
        module,
        "edit_task" if failure_point == "edit" else "commit_backlog",
        fail_edit if failure_point == "edit" else fail_commit,
    )
    with pytest.raises(RuntimeError, match="failed"):
        allow_writes(repo, T01)
    assert task.read_bytes() == before
    assert git(repo, "diff", "--cached") == staged


def test_behind_base_with_dirty_checkout_fails_before_edit(
    repo: Path, script: Script, tmp_path: Path
) -> None:
    _failed_run(repo, script, "README.md")
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "-u", "origin", "main")
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(bare), str(other))
    git(other, "config", "user.name", "Test")
    git(other, "config", "user.email", "test@example.test")
    write(other, "README.md", "remote edit\n")
    git(other, "add", "README.md")
    git(other, "commit", "-q", "-m", "remote edit")
    git(other, "push", "-q", "origin", "main")
    write(repo, "README.md", "operator edit\n")
    before = (repo / TASK_FILE).read_bytes()
    head = git(repo, "rev-parse", "HEAD")
    status = git(repo, "status", "--porcelain")
    with pytest.raises(TaskRunError) as caught:
        allow_writes(repo, T01)
    assert caught.value.code == "dirty_base"
    assert (repo / TASK_FILE).read_bytes() == before
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "status", "--porcelain") == status
