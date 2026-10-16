"""``factory task retry``: continue a failed or stopped run; fake harnesses, provider ``local``.

No test calls a model or the network: the agents are scripted, the suite result is
scripted, git is real (commits, rebase, a bare ``origin`` for the base pull).
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from run_repo import (
    PLAN_APPROVED,
    T01,
    USER_PROMPT,
    Script,
    commit_all,
    fake_env,
    git,
    make_run_repo,
    ok,
    plan_envelope,
    write,
)
from workflow_fakes import FakeCodeRunner, triage_envelope

from aifactory import failure
from aifactory.engine import data_types as dt
from aifactory.review import approve_task
from aifactory.run import TaskRunError, TaskRunRow, TaskRunStore, run_task
from aifactory.run.retry import plan_retry, retry_run
from aifactory.workflow import EngineCodeRunner, Journal, JournalEntry, read_journal
from cli_json import run_json

Capsys = pytest.CaptureFixture[str]
CORE = "backlog/M01-core"
MODEL = "src/app/one.py"
WORKFLOW = "build-test-review"
AGENTS = (
    "defaults:\n  harness: claude\n  model: sonnet\n"
    "agents:\n  - name: planner\n  - name: builder\n  - name: tester\n  - name: documenter\n"
    "  - name: reviewer\n"
)
WORKFLOW_YAML = f"""\
name: {WORKFLOW}
description: Build, test with repairs, review with revision, commit
steps:
  - build
  - test_plan
  - repeat: {{max: 2, until: test.passed}}
    steps: [test, fix]
  - repeat: {{max: 2, until: review.approved}}
    steps:
      - review:
          input: [build, fix, revise]
      - revise
      - test:
          id: retest
  - commit:
      when: test.passed and review.approved
accept: test.passed and review.approved
"""


class GitCode(FakeCodeRunner):
    """Scripted tests; real commits and rebase in the run's worktree."""

    def commit(self, run: Any, message: str) -> str:
        self.commits.append(message)
        return str(EngineCodeRunner().commit(run, message))

    def rebase(self, run: Any) -> Any:
        return EngineCodeRunner().rebase(run)

    def baseline(self) -> str:
        return EngineCodeRunner().baseline()


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    repo = make_run_repo(tmp_path / "repo")
    write(repo, ".factory/agents.yaml", AGENTS)
    write(repo, ".factory/prompts/reviewer/system.md", "You are the reviewer.\n")
    write(repo, ".factory/prompts/reviewer/user.md", USER_PROMPT)
    write(repo, f".factory/workflows/{WORKFLOW}.yaml", WORKFLOW_YAML)
    write(repo, f"{CORE}/index.md", f"---\nid: M01\ntitle: Core\nworkflow: {WORKFLOW}\n---\n")
    write(repo, MODEL, "NAME = 'base'\n")
    commit_all(repo, "retry setup")
    return repo


def build(script: Script, text: str = "NAME = 'one'\n") -> None:
    script.on("builder", lambda wt: write(wt, MODEL, text))
    script.add("builder", ok(changed_files=[MODEL], commit_message="Build one"))


def test_plan(script: Script) -> None:
    script.add("tester", plan_envelope(sys.executable, "-c", "pass"))
    script.add("test-reviewer", dict(PLAN_APPROVED))


def review(script: Script, approved: bool) -> None:
    if approved:
        script.add("reviewer", ok(approved=True, findings=[{"requirement": "x", "met": True}]))
    else:
        script.add("reviewer", ok(approved=False, blocking=["missing tests"]))


def revise(script: Script) -> None:
    script.add("builder", ok(changed_files=[], commit_message="Revise"))


def rejected_run(repo: Path, script: Script) -> Any:
    """A run whose review rejects twice: accept not met, the run failed."""
    build(script)
    test_plan(script)
    review(script, approved=False)
    revise(script)
    review(script, approved=False)
    result = run_task(repo, T01, code=GitCode([True, True]))
    assert result.run.state == "failed"
    assert result.run.error == "Review neschválilo ani po 2 kolech: missing tests"
    return result


def test_rejected_run_explains_accept(repo: Path, script: Script) -> None:
    """accept_not_met: the expression, its values, the loop rounds and the objections."""
    run = rejected_run(repo, script).run
    assert run.failure_kind == failure.ACCEPT_NOT_MET
    detail = run.failure_detail_dict()
    assert detail is not None
    assert detail["accept"] == "test.passed and review.approved"
    assert detail["values"] == {"test.passed": True, "review.approved": False}
    rounds = {r["until"]: (r["rounds"], r["max"]) for r in detail["rounds"]}
    assert rounds == {"test.passed": (1, 2), "review.approved": (2, 2)}
    assert detail["review"]["step"] == "review"
    assert detail["review"]["objections"] == ["missing tests"]
    assert "test" not in detail  # every test passed


def test_failed_tests_explain_accept(repo: Path, script: Script) -> None:
    """A test loop that stays red: the error quotes the failed check, the detail keeps it."""

    class RedCode(GitCode):
        def _result(self, passed: bool, what: str) -> dt.QualityResult:
            failures = [] if passed else ["unit: `pytest` exited 1\n" + "x" * 5000]
            return dt.QualityResult(passed=passed, checks=[], failures=failures, artifacts=[])

    build(script)
    test_plan(script)
    triage = triage_envelope("code", sys.executable, "-c", "pass")
    script.add("tester", triage)
    script.add("builder", ok(changed_files=[], commit_message="Fix"))
    script.add("tester", triage)
    review(script, approved=True)
    run = run_task(repo, T01, code=RedCode([False, False])).run
    assert run.state == "failed" and run.failure_kind == failure.ACCEPT_NOT_MET
    assert run.error == "Testy neprošly ani po 2 kolech: unit: `pytest` exited 1"
    detail = run.failure_detail_dict()
    assert detail is not None
    assert detail["values"] == {"test.passed": False, "review.approved": True}
    assert "review" not in detail
    checks = detail["test"]["failed_checks"]
    assert checks[0].startswith("unit: `pytest` exited 1\n…\n")
    assert len(checks[0]) <= 800 and checks[0].endswith("x")


def calls(script: Script, agent: str) -> list[Any]:
    return [c for c in script.calls if c.agent == agent]


def phases(repo: Path, run_id: str) -> list[str]:
    db = sqlite3.connect(repo / ".factory" / "trace.db")
    try:
        rows = db.execute("SELECT name FROM phases WHERE adw_id = ? ORDER BY seq", (run_id,))
        return [str(r[0]) for r in rows]
    finally:
        db.close()


def add_origin(repo: Path, tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "-u", "origin", "main")
    return origin


def push_to_origin(origin: Path, tmp_path: Path, rel: str, text: str) -> str:
    """A commit on origin/main made elsewhere: the local base is behind it."""
    clone = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
    for key, value in (("user.name", "Other"), ("user.email", "o@example.com")):
        git(clone, "config", key, value)
    write(clone, rel, text)
    sha = commit_all(clone, f"other: {rel}")
    git(clone, "push", "-q", "origin", "main")
    return sha


@pytest.mark.parametrize("harness", ["claude", "codex", "pi"])
def test_retry_after_rejected_review_continues_at_the_review(
    repo: Path, script: Script, capsys: Capsys, harness: str
) -> None:
    if harness != "claude":
        write(
            repo, ".factory/agents.yaml", AGENTS.replace("harness: claude", f"harness: {harness}")
        )
        commit_all(repo, "select retry harness")
    first = rejected_run(repo, script)
    run_id = first.run.run_id
    builder_before = len(calls(script, "builder"))
    reviewer_session = calls(script, "reviewer")[0].session

    review(script, approved=True)
    code = GitCode([])
    result = retry_run(repo, T01, note="The missing tests are out of scope.", code=code)

    assert result.ok, (result.run.error, result.pr_error)
    assert result.run.run_id == run_id
    assert result.run.worktree == first.run.worktree
    assert result.run.branch == first.run.branch
    assert result.run.attempt == 2
    retry = result.run.retry_list()[0]
    assert retry["from_phase"] == "review_1"
    assert retry["note"] == "The missing tests are out of scope."
    # no done phase ran again: no builder, no tester, no test; only the review
    assert len(calls(script, "builder")) == builder_before
    assert code.plans == []
    last = calls(script, "reviewer")[-1]
    assert last.session == reviewer_session
    assert last.harness == harness
    assert "## Continuation" in last.prompt
    assert "## Retry note\nThe missing tests are out of scope." in last.prompt
    handoff = repo / ".factory/data/sessions" / run_id / "context_handoff/retry_attempt_1.json"
    previous_outputs = json.loads(handoff.read_text(encoding="utf-8"))
    assert previous_outputs["entries"][-1]["phase"] == "review_2"
    assert git(repo, "show", f"{first.run.branch}:{MODEL}") == "NAME = 'one'"
    names = phases(repo, run_id)
    assert names.count("build") == 1 and names.count("review_1") == 2
    assert result.pr is not None and result.pr.branch == first.run.branch

    # a succeeded run is not retried
    capsys.readouterr()
    code_, data = run_json(capsys, ["task", "retry", T01, "--json", "--repo", str(repo)])
    assert code_ == 2
    assert data["error"]["code"] == "run_not_retryable"


def test_retry_after_stop_continues_at_the_stopped_phase(repo: Path, script: Script) -> None:
    build(script)
    test_plan(script)

    def stop_here(wt: Path) -> None:
        store = TaskRunStore(repo / ".factory" / "trace.db")
        try:
            running = store.running(T01)
            assert running is not None
            store.mark_stopped(running.run_id, "stopped by user")
        finally:
            store.close()
        raise SystemExit(143)

    script.on("reviewer", stop_here)
    review(script, approved=False)  # consumed by the stopped call
    with pytest.raises(SystemExit):
        run_task(repo, T01, code=GitCode([True]))
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        stopped = store.for_task(T01)[0]
    finally:
        store.close()
    assert stopped.state == "stopped"

    review(script, approved=True)
    code = GitCode([])
    result = retry_run(repo, T01, code=code)

    assert result.ok, result.run.error
    assert result.run.run_id == stopped.run_id
    assert result.run.retry_list()[0]["from_phase"] == "review_1"
    assert result.run.retry_list()[0]["previous_state"] == "stopped"
    assert len(calls(script, "builder")) == 1
    assert len(calls(script, "tester")) == 1
    assert code.plans == []
    assert calls(script, "reviewer")[-1].session == calls(script, "reviewer")[0].session
    assert git(repo, "show", f"{stopped.branch}:{MODEL}") == "NAME = 'one'"


def test_retry_after_stop_at_phase_gate_keeps_completed_tests(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.run import task as run_mod

    build(script)
    test_plan(script)

    def stop_before_review(store: TaskRunStore, run_id: str) -> Any:
        def gate() -> None:
            path = repo / ".factory/data/sessions" / run_id / "workflow_journal.json"
            current = json.loads(path.read_text(encoding="utf-8"))["current"]
            if current["phase"] == "review_1":
                store.mark_stopped(run_id, "stopped while waiting at phase gate")
                raise SystemExit(143)

        return gate

    with monkeypatch.context() as patch:
        patch.setattr(run_mod, "PauseGate", stop_before_review)
        with pytest.raises(SystemExit):
            run_task(repo, T01, code=GitCode([True]))
    review(script, approved=True)
    code = GitCode([])
    result = retry_run(repo, T01, code=code)
    assert result.ok, result.run.error
    assert result.run.retry_list()[0]["from_phase"] == "review_1"
    assert code.plans == []
    assert len(calls(script, "builder")) == 1
    assert len(calls(script, "tester")) == 1


def test_retry_refuses_approved_task_without_a_merged_pr(repo: Path, script: Script) -> None:
    first = rejected_run(repo, script)
    path = repo / f"{CORE}/S01-model/{T01}-schema.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("status: todo", "status: done"),
        encoding="utf-8",
    )
    commit_all(repo, "approve task in backlog")
    before_calls = len(script.calls)
    with pytest.raises(TaskRunError) as exc:
        retry_run(repo, T01, run_id=first.run.run_id)
    assert exc.value.code == "task_done"
    assert len(script.calls) == before_calls


def test_retry_from_build_reuses_the_builder_session(repo: Path, script: Script) -> None:
    first = rejected_run(repo, script)
    previous_session = calls(script, "builder")[0].session
    build(script, "NAME = 'updated'\n")
    test_plan(script)
    review(script, approved=True)
    result = retry_run(repo, T01, run_id=first.run.run_id, from_phase="build", code=GitCode([True]))
    assert result.ok, result.run.error
    assert result.run.retry_list()[0]["from_phase"] == "build"
    assert calls(script, "builder")[-1].session == previous_session
    assert git(repo, "show", f"{first.run.branch}:{MODEL}") == "NAME = 'updated'"


@pytest.mark.parametrize("published", [False, True])
def test_retry_rebases_onto_a_moved_base_and_tests_before_the_review(
    repo: Path, script: Script, tmp_path: Path, published: bool
) -> None:
    origin = add_origin(repo, tmp_path)
    first = rejected_run(repo, script)
    if published:
        commit_all(Path(first.run.worktree), "preserve failed implementation")
        git(repo, "push", "-q", "-u", "origin", first.run.branch)
    moved = push_to_origin(origin, tmp_path, "README.md", "readme, newer\n")

    review(script, approved=True)
    code = GitCode([True])
    result = retry_run(repo, T01, code=code)

    assert result.ok, result.run.error
    assert git(repo, "rev-parse", "main") == moved  # base was pulled first
    branch = first.run.branch
    assert git(repo, "merge-base", "--is-ancestor", moved, branch) == ""
    assert git(repo, "show", f"{branch}:README.md") == "readme, newer"
    assert git(repo, "show", f"{branch}:{MODEL}") == "NAME = 'one'"
    assert len(code.plans) == 1  # the test ran again before the review
    retry = result.run.retry_list()[0]
    assert retry["rebased_onto"] == moved
    assert retry["from_phase"] == "test_1"
    assert result.run.base_sha == moved
    assert result.pr is not None and result.pr.base_sha == moved
    assert git(repo, "rev-parse", f"origin/{branch}") == git(repo, "rev-parse", branch)
    assert len(calls(script, "builder")) == 2  # build and revise of the first attempt


def test_retry_resolves_a_conflict_after_the_rebase(
    repo: Path, script: Script, tmp_path: Path
) -> None:
    origin = add_origin(repo, tmp_path)
    first = rejected_run(repo, script)
    moved = push_to_origin(origin, tmp_path, MODEL, "NAME = 'main'\n")

    script.on("builder", lambda wt: write(wt, MODEL, "NAME = 'both'\n"))
    script.add("builder", ok(changed_files=[MODEL], commit_message="Resolve"))
    test_plan(script)  # the resolve workflow plans its checks
    review(script, approved=True)
    code = GitCode([True, True])  # the resolve run's test, then the task's test
    result = retry_run(repo, T01, code=code)

    assert result.ok, result.run.error
    resolver = calls(script, "builder")[-1]
    assert "## Resolve" in resolver.prompt
    branch = first.run.branch
    assert git(repo, "merge-base", "--is-ancestor", moved, branch) == ""
    assert git(repo, "show", f"{branch}:{MODEL}") == "NAME = 'both'"
    assert len(code.plans) == 2
    assert result.run.retry_list()[0]["rebased_onto"] == moved


def test_retry_reads_changed_task_configuration_and_workflow_from_pulled_base(
    repo: Path,
    script: Script,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aifactory.run import task as run_mod

    origin = add_origin(repo, tmp_path)
    build(script)
    test_plan(script)

    def stop_before_review(store: TaskRunStore, run_id: str) -> Any:
        def gate() -> None:
            journal = read_journal(
                repo / ".factory/data/sessions" / run_id / "workflow_journal.json"
            )
            if journal.current and journal.current["phase"] == "review_1":
                store.mark_stopped(run_id, "stopped before review")
                raise SystemExit(143)

        return gate

    with monkeypatch.context() as patch:
        patch.setattr(run_mod, "PauseGate", stop_before_review)
        with pytest.raises(SystemExit):
            run_task(repo, T01, code=GitCode([True]))
    store = TaskRunStore(repo / ".factory/trace.db")
    try:
        first = store.for_task(T01)[0]
    finally:
        store.close()

    clone = tmp_path / "updated-base"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
    git(clone, "config", "user.name", "Other")
    git(clone, "config", "user.email", "o@example.com")
    task_path = f"{CORE}/S01-model/{T01}-schema.md"
    write(
        clone,
        task_path,
        (
            f"---\nid: {T01}\ntitle: Updated task\nstatus: todo\nworkflow: current\n"
            "harness: codex\nmodel: gpt-5.5\nwrites: [src/new/]\n---\n\n"
            "## Zadání\nUse the updated task from base.\n"
        ),
    )
    write(
        clone,
        ".factory/workflows/current.yaml",
        (
            "name: current\ndescription: Updated workflow without review\n"
            "steps: [build, test_plan, test, commit]\naccept: test.passed\n"
        ),
    )
    write(
        clone, ".factory/config.yaml", "base: main\ngit_provider: local\ndocs_root: updated-docs\n"
    )
    shutil.copytree(clone / "backlog", clone / "updated-docs/backlog")
    moved = commit_all(clone, "update task, settings and workflow")
    git(clone, "push", "-q", "origin", "main")
    assert git(repo, "rev-parse", "main") != moved

    script.on("builder", lambda wt: write(wt, "src/new/current.py", "CURRENT = True\n"))
    script.add(
        "builder", ok(changed_files=["src/new/current.py"], commit_message="Apply current task")
    )
    test_plan(script)
    code = GitCode([True])
    result = retry_run(repo, T01, code=code)

    assert result.ok, result.run.error
    assert (result.run.run_id, result.run.attempt) == (first.run_id, 2)
    assert result.workflow_run is not None
    assert result.workflow_run.results["test"]["passed"] is True
    assert "review" not in result.workflow_run.results
    assert result.run.base_sha == git(repo, "rev-parse", "main") == moved
    assert any(
        "review_1" in warning and "not in workflow current" in warning
        for warning in result.warnings
    )
    assert result.run.retry_list()[0]["from_phase"] is None
    builder = calls(script, "builder")[-1]
    assert builder.harness == "codex" and builder.model == "gpt-5.5"
    assert "Use the updated task from base." in builder.prompt
    assert "src/new/" in builder.prompt and "updated-docs/" in builder.prompt
    assert not calls(script, "reviewer")
    assert len(code.plans) == 1
    assert git(repo, "show", f"{first.branch}:src/new/current.py") == "CURRENT = True"
    assert phases(repo, first.run_id).count("build") == 2


def test_failed_resolve_leaves_the_branch_and_skips_the_workflow(
    repo: Path, script: Script, tmp_path: Path
) -> None:
    origin = add_origin(repo, tmp_path)
    first = rejected_run(repo, script)
    worktree = Path(first.run.worktree)
    tip = git(repo, "rev-parse", first.run.branch)
    status = git(worktree, "status", "--porcelain")
    push_to_origin(origin, tmp_path, MODEL, "NAME = 'main'\n")

    # the resolver leaves the conflict markers in place
    script.add("builder", ok(changed_files=[MODEL], commit_message="Resolve"))
    test_plan(script)
    reviews = len(calls(script, "reviewer"))
    result = retry_run(repo, T01, code=GitCode([True]))

    assert result.run.state == "failed"
    assert "resolve after the rebase" in (result.run.error or "")
    assert git(repo, "rev-parse", first.run.branch) == tip
    assert git(worktree, "status", "--porcelain") == status
    assert git(worktree, "show", f"HEAD:{MODEL}") == "NAME = 'base'"
    assert (worktree / MODEL).read_text(encoding="utf-8") == "NAME = 'one'\n"
    assert len(calls(script, "reviewer")) == reviews

    # A failed resolve must not lose the original rejected review as the retry target.
    script.on("builder", lambda wt: write(wt, MODEL, "NAME = 'both'\n"))
    script.add("builder", ok(changed_files=[MODEL], commit_message="Resolve"))
    test_plan(script)
    review(script, approved=True)
    retried = retry_run(repo, T01, code=GitCode([True, True]))
    assert retried.ok, retried.run.error
    assert retried.run.attempt == 3
    assert len(calls(script, "reviewer")) == reviews + 1


def test_retry_refuses_a_diverged_base_without_changing_the_run(
    repo: Path, script: Script, tmp_path: Path
) -> None:
    origin = add_origin(repo, tmp_path)
    failed = rejected_run(repo, script)
    push_to_origin(origin, tmp_path, "README.md", "remote\n")
    write(repo, "README.md", "local\n")
    local_tip = commit_all(repo, "local base diverges")
    worktree = Path(failed.run.worktree)
    branch_tip = git(worktree, "rev-parse", "HEAD")
    status = git(worktree, "status", "--porcelain")
    before_calls = len(script.calls)
    with pytest.raises(TaskRunError) as exc:
        retry_run(repo, T01, code=GitCode([]))
    assert exc.value.code == "base_diverged"
    assert git(repo, "rev-parse", "main") == local_tip
    assert git(worktree, "rev-parse", "HEAD") == branch_tip
    assert git(worktree, "status", "--porcelain") == status
    assert len(script.calls) == before_calls
    store = TaskRunStore(repo / ".factory/trace.db")
    try:
        row = store.get(failed.run.run_id)
        assert row is not None and row.state == "failed" and row.attempt == 1
    finally:
        store.close()


def test_retry_refuses_a_merged_task_and_a_running_one(repo: Path, script: Script) -> None:
    failed = rejected_run(repo, script)

    # a run of the task in progress
    store = TaskRunStore(repo / ".factory" / "trace.db")
    busy = TaskRunRow(
        "busy0001", T01, "factory/x", "wt", "main", "0", None, "running", "now", pid=os.getpid()
    )
    store.claim(busy)
    try:
        with pytest.raises(TaskRunError) as exc:
            retry_run(repo, T01, run_id=failed.run.run_id)
        assert exc.value.code == "already_running"
    finally:
        store.finish("busy0001", "failed", None, "gone")
        store.close()

    with pytest.raises(TaskRunError) as exc:
        retry_run(repo, T01, run_id=failed.run.run_id, from_phase="nope")
    assert exc.value.code == "unknown_phase"

    build(script)
    test_plan(script)
    review(script, approved=True)
    done = run_task(repo, T01, code=GitCode([True]))
    assert done.ok, done.run.error
    approve_task(repo, T01)
    with pytest.raises(TaskRunError) as exc:
        retry_run(repo, T01, run_id=failed.run.run_id)
    assert exc.value.code == "task_done"
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        assert store.get(failed.run.run_id).state == "failed"  # type: ignore[union-attr]
    finally:
        store.close()


def test_journal_records_every_finished_phase(repo: Path, script: Script) -> None:
    first = rejected_run(repo, script)
    session = repo / ".factory" / "data" / "sessions" / first.run.run_id
    data = json.loads((session / "workflow_journal.json").read_text(encoding="utf-8"))
    names = [e["phase"] for e in data["entries"]]
    assert names[:3] == ["build", "test_plan", "test_review"]
    assert "review_2" in names and data["current"] is None


def test_retry_plan_honors_from_and_warns_when_the_failed_step_is_removed() -> None:
    from workflow_fakes import workflow

    previous = Journal(
        None,
        entries=[
            JournalEntry("build", "build", "agent", "build"),
            JournalEntry("test", "test", "code", "test", action="test"),
        ],
        current={"phase": "review", "step": "review"},
    )
    header = "name: retry\ndescription: Continue work after a stopped phase\n"
    current = workflow(header + "steps: [build, test_plan, test, review]\n")
    chosen = plan_retry(previous, current, run_id="r", error="stopped", from_phase="test")
    assert chosen.limit == 1 and chosen.resume == "test" and chosen.warnings == []
    changed = workflow(header + "steps: [build, test_plan, test]\n")
    fallback = plan_retry(previous, changed, run_id="r", error="stopped")
    assert fallback.limit == 0 and fallback.resume is None
    assert "not in workflow" in fallback.warnings[0]
