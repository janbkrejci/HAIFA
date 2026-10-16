"""Stacked PRs (``stacked_prs: true``): a task whose dependency waits in an open PR starts
from that PR's branch, waits for its merge and is rebased onto base without its commits."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from run_repo import (
    T01,
    T02,
    Script,
    commit_all,
    fake_env,
    git,
    make_run_repo,
    ok,
    scripted_plan,
    write,
)

from aifactory.review import ReviewError, approve_task, resolve_task
from aifactory.run import TaskRunStore, run_task
from aifactory.run.errors import TaskRunError
from aifactory.web.review import review_detail


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    repo = make_run_repo(tmp_path / "repo")
    write(repo, ".factory/config.yaml", "base: main\ndocs_root: .\nstacked_prs: true\n")
    commit_all(repo, "stacked PRs")
    return repo


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


def builds(script: Script, rel: str) -> None:
    script.on("planner", lambda wt: write(wt, rel, f"# {rel}\n"))
    script.add("planner", ok(artifacts=[rel], commit_message=f"Add {rel}"))


def test_dependent_stacks_on_the_open_pr_and_lands_after_it(repo: Path, script: Script) -> None:
    builds(script, "src/app/a.py")
    first = run_task(repo, T01)
    assert first.ok and first.pr is not None

    builds(script, "src/app/b.py")
    second = run_task(repo, T02)
    assert second.ok, (second.run.error, second.pr_error)
    assert second.run.stacked_on == first.run.branch
    assert git(repo, "show", f"{second.run.branch}:src/app/a.py") == "# src/app/a.py"
    assert second.pr is not None and "Navazuje na" in second.pr.body
    # the review screen shows only T02's own changes while it is stacked
    detail, _ = review_detail(repo, T02)
    assert detail["stacked_on"]["task_id"] == T01
    assert detail["diff"]["base"] == first.run.branch
    assert "src/app/a.py" not in {f["path"] for f in detail["diff"]["files"]}
    assert "src/app/b.py" in {f["path"] for f in detail["diff"]["files"]}

    with pytest.raises(ReviewError) as caught:
        approve_task(repo, T02)
    assert caught.value.code == "task_blocked"
    with pytest.raises(ReviewError) as stacked:
        resolve_task(repo, T02)
    assert stacked.value.code == "stacked_on_open_pr"

    scripted_plan(script)  # the restack's resolve run tests the rebased branch
    merged = approve_task(repo, T01)
    assert not [w for w in merged.warnings if "restack" in w], (merged.warnings, _debug_runs(repo))
    # restacked onto main: only T02's own commit is left on its branch
    branch = second.run.branch
    assert git(repo, "merge-base", "--is-ancestor", "main", branch) == ""
    assert git(repo, "log", "--format=%s", f"main..{branch}") == "Add src/app/b.py"

    approve_task(repo, T02)
    assert git(repo, "show", "main:src/app/a.py") == "# src/app/a.py"
    assert git(repo, "show", "main:src/app/b.py") == "# src/app/b.py"


def test_without_stacked_prs_the_dependent_waits(repo: Path, script: Script) -> None:
    write(repo, ".factory/config.yaml", "base: main\ndocs_root: .\n")
    commit_all(repo, "no stacking")
    builds(script, "src/app/a.py")
    assert run_task(repo, T01).ok
    with pytest.raises(TaskRunError) as caught:
        run_task(repo, T02)
    assert caught.value.code == "unmet_dependencies"
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        assert store.for_task(T02) == []
    finally:
        store.close()


def _debug_runs(repo: Path) -> list[tuple[str, str, str | None]]:
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        return [(r.run_id, r.state, r.error) for r in store.for_task(T02)]
    finally:
        store.close()
