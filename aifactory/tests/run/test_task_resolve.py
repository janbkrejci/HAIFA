"""``factory task resolve``: a PR in conflict with base, provider ``local``, fake harnesses.

Two tasks change the same line; the first is merged, the second no longer
merges, gets resolved (rebase, agent, test, push) and is then approved. No test
calls a model: the harnesses are scripted and the suite result is scripted too.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from run_repo import (
    SPEC,
    T01,
    T02,
    Script,
    commit_all,
    fake_env,
    git,
    make_run_repo,
    ok,
    plan_envelope,
    write,
)
from workflow_fakes import FakeCodeRunner

import aifactory.review
from aifactory.cli import main
from aifactory.review import ReviewError, approve_task, resolve_task
from aifactory.run import TaskPrRow, TaskRunResult, TaskRunStore, run_task
from aifactory.workflow import EngineCodeRunner
from cli_json import run_json

Capsys = pytest.CaptureFixture[str]
MODEL = "src/app/model.py"
SPEC2 = "specs/M01-S01-T02-loader.md"
TASK1 = "backlog/M01-core/S01-model/M01-S01-T01-schema.md"
TASK2 = "backlog/M01-core/S01-model/M01-S01-T02-loader.md"
BRANCH1 = f"factory/{T01}-1"
BRANCH2 = f"factory/{T02}-1"


class ResolveCode(FakeCodeRunner):
    """A real ``rebase`` step and a scripted suite."""

    def rebase(self, run: Any) -> Any:
        return EngineCodeRunner().rebase(run)


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    repo = make_run_repo(tmp_path / "repo")
    write(repo, MODEL, "VALUE = 0\n")
    commit_all(repo, "model")
    return repo


def plan(script: Script, spec: str, rel: str, text: str) -> None:
    def effect(wt: Path) -> None:
        write(wt, spec, "# spec\n")
        write(wt, rel, text)

    script.on("planner", effect)
    script.add("planner", ok(artifacts=[spec], commit_message=f"Plan {spec}"))


def run_both(repo: Path, script: Script, second: tuple[str, str] = (MODEL, "VALUE = 2\n")) -> None:
    """T01 sets VALUE = 1, T02 writes `second`; both get a PR, T01 is merged."""
    plan(script, SPEC, MODEL, "VALUE = 1\n")
    first = run_task(repo, T01)
    assert first.ok, (first.run.error, first.pr_error)
    plan(script, SPEC2, *second)
    other = run_task(repo, T02, force=True)
    assert other.ok, (other.run.error, other.pr_error)
    approve_task(repo, T01)


def tester(script: Script) -> None:
    """The tester's plan for the resolve run (one check; the suite result is scripted)."""
    script.add("tester", plan_envelope())


def resolver(script: Script, *effects: Callable[[Path], object], **fields: Any) -> None:
    script.on("builder", *effects)
    script.add("builder", ok(**fields))


def settle(wt: Path) -> None:
    write(wt, MODEL, "VALUE = 3\n")


def stored_pr(repo: Path, branch: str = BRANCH2) -> TaskPrRow:
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        row = store.pr_for_branch(branch)
    finally:
        store.close()
    assert row is not None
    return row


def builder_calls(script: Script) -> list[Any]:
    return [c for c in script.calls if c.agent == "builder"]


def tip(repo: Path, branch: str = BRANCH2) -> str:
    return git(repo, "rev-parse", f"refs/heads/{branch}")


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant], cwd=repo, check=False
    )
    return proc.returncode == 0


def cli_json(capsys: Capsys, *argv: str) -> tuple[int, Any]:
    capsys.readouterr()
    return run_json(capsys, argv)


def assert_restored(repo: Path, result: TaskRunResult, before: str) -> None:
    assert result.run.state == "failed"
    assert result.pr is None
    assert tip(repo) == before
    worktree = Path(result.run.worktree)
    assert git(worktree, "status", "--porcelain") == ""
    assert git(worktree, "ls-files", "-u") == ""
    git_dir = Path(git(worktree, "rev-parse", "--absolute-git-dir"))
    for leftover in ("rebase-merge", "rebase-apply", "MERGE_HEAD", "SQUASH_MSG"):
        assert not (git_dir / leftover).exists(), leftover


def test_conflict_resolve_then_approve(
    repo: Path, script: Script, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_both(repo, script)

    with pytest.raises(ReviewError) as exc:
        approve_task(repo, T02)
    assert exc.value.code == "conflict"
    assert f"factory task resolve {T02}" in exc.value.message
    code, data = cli_json(capsys, "task", "approve", T02, "--json", "--repo", str(repo))
    assert code == 2
    assert data["error"]["code"] == "conflict"
    assert "task resolve" in data["error"]["message"]

    before_pr = stored_pr(repo)
    resolver(script, settle, changed_files=[MODEL], commit_message="Resolve model conflict")
    tester(script)
    code_runner = ResolveCode([True])

    def with_fakes(repo_: Path, task_id: str, **kwargs: Any) -> TaskRunResult:
        return resolve_task(repo_, task_id, code=code_runner, **kwargs)

    monkeypatch.setattr(aifactory.review, "resolve_task", with_fakes)
    code, data = cli_json(capsys, "task", "resolve", T02, "--json", "--repo", str(repo))

    assert code == 0, data
    assert data["ok"] is True
    run = data["data"]["run"]
    assert run["workflow"] == "resolve"
    assert run["branch"] == BRANCH2
    calls = builder_calls(script)
    assert len(calls) == 1
    assert MODEL in calls[0].previous()
    assert "## Resolve" in calls[0].prompt
    main_sha = git(repo, "rev-parse", "main")
    assert is_ancestor(repo, main_sha, BRANCH2)
    assert git(repo, "show", f"{BRANCH2}:{MODEL}") == "VALUE = 3"
    assert git(repo, "show", f"{BRANCH2}:{SPEC2}") == "# spec"
    assert git(repo, "status", "--porcelain") == ""
    pr = stored_pr(repo)
    assert pr.state == "open"
    assert pr.base_sha == main_sha != before_pr.base_sha
    assert data["data"]["pr"]["base_sha"] == main_sha

    approved = approve_task(repo, T02)
    assert approved.pr.state == "merged"
    assert git(repo, "show", f"main:{MODEL}") == "VALUE = 3"
    for task_file in (TASK1, TASK2):
        assert "status: done" in git(repo, "show", f"main:{task_file}")
    runs_line = git(repo, "show", f"main:{TASK2}").split("## Běhy", 1)[1]
    assert "workflow plan-commit" in runs_line
    assert "workflow resolve" not in runs_line


def test_clean_rebase_skips_agent(repo: Path, script: Script) -> None:
    run_both(repo, script, ("src/app/loader.py", "LOADER = 1\n"))
    before = tip(repo)

    tester(script)
    result = resolve_task(repo, T02, code=ResolveCode([True]))

    assert result.ok, (result.run.error, result.pr_error)
    assert builder_calls(script) == []
    assert result.run.workflow == "resolve"
    assert tip(repo) != before
    assert is_ancestor(repo, "main", BRANCH2)
    assert git(repo, "rev-list", "--count", f"main..{BRANCH2}") == "1"
    assert stored_pr(repo).base_sha == git(repo, "rev-parse", "main")
    approve_task(repo, T02)
    assert git(repo, "show", "main:src/app/loader.py") == "LOADER = 1"


def test_unresolved_conflict_restores_branch(repo: Path, script: Script) -> None:
    run_both(repo, script)
    before = tip(repo)
    base_sha = stored_pr(repo).base_sha
    resolver(script)

    tester(script)
    result = resolve_task(repo, T02, code=ResolveCode([True]))

    assert result.run.error is not None and "conflict markers" in result.run.error
    assert result.run.head_sha == before
    assert_restored(repo, result, before)
    assert stored_pr(repo).base_sha == base_sha


def _writer(text: str) -> Callable[[Path], None]:
    def effect(wt: Path) -> None:
        write(wt, MODEL, text)

    return effect


def test_red_suite_restores_branch(repo: Path, script: Script) -> None:
    run_both(repo, script)
    before = tip(repo)
    resolver(script, settle, changed_files=[MODEL])
    for value in (4, 5):  # fix_1, fix_2: the suite stays red, test_3 ends the loop
        resolver(script, _writer(f"VALUE = {value}\n"), changed_files=[MODEL])
        tester(script)  # the plan after each fix

    tester(script)
    result = resolve_task(repo, T02, code=ResolveCode([False, False, False]))

    assert len(builder_calls(script)) == 3
    assert_restored(repo, result, before)


def test_clean_rebase_red_suite_restores_branch(repo: Path, script: Script) -> None:
    run_both(repo, script, ("src/app/loader.py", "LOADER = 1\n"))
    before = tip(repo)

    tester(script)
    result = resolve_task(repo, T02, code=ResolveCode([False, False, False]))

    assert builder_calls(script) == []
    assert_restored(repo, result, before)


class SuiteCode(ResolveCode):
    """A real ``rebase`` and a suite that is red exactly while the model says ``BROKEN``."""

    def test(self, run: Any, plan: Any) -> Any:
        text = (Path(run.repo_root) / MODEL).read_text(encoding="utf-8")
        return self._result("BROKEN" not in text, "test")


def test_fix_repairs_what_resolve_broke(repo: Path, script: Script) -> None:
    run_both(repo, script)
    before = tip(repo)
    resolver(
        script,
        lambda wt: write(wt, MODEL, "VALUE = 3\nBROKEN = True\n"),
        changed_files=[MODEL],
        commit_message="Resolve model conflict",
    )
    resolver(
        script,
        lambda wt: write(wt, MODEL, "VALUE = 3\n"),
        changed_files=[MODEL],
        commit_message="Fix model",
    )
    tester(script)  # the plan after the fix

    tester(script)
    result = resolve_task(repo, T02, code=SuiteCode([]))

    assert result.run.state == "succeeded", result.run.error
    assert result.ok, (result.run.error, result.pr_error)
    assert len(builder_calls(script)) == 2
    assert result.workflow_run is not None
    names = [name for name, _, _ in result.workflow_run.phases]
    assert names == [
        "request",
        "rebase",
        "resolve",
        "test_plan",
        "rebuild_1",
        "test_1",
        "fix_1",
        "test_plan_1",
        "rebuild_2",
        "test_2",
    ], names
    assert git(repo, "show", f"{BRANCH2}:{MODEL}") == "VALUE = 3"
    assert tip(repo) != before
    assert is_ancestor(repo, git(repo, "rev-parse", "main"), BRANCH2)


def test_resolver_outside_conflict_is_breach(repo: Path, script: Script) -> None:
    run_both(repo, script)
    before = tip(repo)

    def settle_and_more(wt: Path) -> None:
        settle(wt)
        write(wt, "src/app/other.py", "OTHER = 1\n")

    resolver(script, settle_and_more, changed_files=[MODEL, "src/app/other.py"])

    tester(script)
    result = resolve_task(repo, T02, code=ResolveCode([True]))

    assert result.run.error is not None and "src/app/other.py" in result.run.error
    assert not (Path(result.run.worktree) / "src/app/other.py").exists()
    assert_restored(repo, result, before)


def test_resolve_force_pushes(repo: Path, script: Script, tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, capture_output=True
    )
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "-u", "origin", "main")
    run_both(repo, script)
    before = tip(repo)
    assert git(origin, "rev-parse", BRANCH2) == before
    resolver(script, settle, changed_files=[MODEL])

    tester(script)
    result = resolve_task(repo, T02, code=ResolveCode([True]))

    assert result.ok, (result.run.error, result.pr_error)
    assert git(origin, "rev-parse", BRANCH2) == tip(repo) != before
    assert is_ancestor(origin, git(origin, "rev-parse", "main"), git(origin, "rev-parse", BRANCH2))


def test_resolve_without_pr(repo: Path, script: Script, capsys: Capsys) -> None:
    with pytest.raises(ReviewError) as exc:
        resolve_task(repo, T02, code=ResolveCode([]))
    assert exc.value.code == "no_pr"
    code, data = cli_json(capsys, "task", "resolve", T02, "--json", "--repo", str(repo))
    assert code == 2
    assert data["error"]["code"] == "no_pr"


def test_help_mentions_resolve(capsys: Capsys) -> None:
    with pytest.raises(SystemExit):
        main(["task", "--help"])
    assert "resolve" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["task", "resolve", "--help"])
    out = capsys.readouterr().out
    assert "rebase" in out and "before the rebase" in out
