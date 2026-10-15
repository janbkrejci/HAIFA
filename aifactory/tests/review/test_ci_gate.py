"""The CI gate of approve and auto-merge (``review.ci``) with a provider of scripted checks.

The provider is ``local`` (a branch is the PR, the merge is local) whose ``checks`` and
``check_logs`` answer from a script; the agents are the fake harnesses. No test calls a
model or the network.
"""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from aifactory.backlog import Task, load_backlog
from aifactory.config import load_run_config
from aifactory.providers import (
    CHECKS_FAILING,
    CHECKS_NONE,
    CHECKS_PASSING,
    CHECKS_PENDING,
    ChecksStatus,
    GitProvider,
    PrStatus,
    PullRequest,
)
from aifactory.providers.local import LocalProvider
from aifactory.review import ReviewError, approve_task, ci, try_auto_merge
from aifactory.run import TaskPrRow, TaskRunRow, TaskRunStore, run_task
from aifactory.run.errors import TaskRunError
from aifactory.run.store import MERGED_BY_AUTO, MERGED_BY_OPERATOR
from aifactory.run.task import TaskRunResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))

from run_repo import (  # noqa: E402,I001
    SPEC,
    T01,
    USER_PROMPT,
    Script,
    commit_all,
    fake_env,
    git,
    make_run_repo,
    ok,
    write,
)

BRANCH = f"factory/{T01}-1"
FIX = "src/app/fix.py"
RED = ChecksStatus(CHECKS_FAILING, ("unit tests",))
GREEN = ChecksStatus(CHECKS_PASSING)
NONE = ChecksStatus(CHECKS_NONE)
PENDING = ChecksStatus(CHECKS_PENDING)
LOG = "FAILED tests/test_app.py::test_fix - AssertionError: 1 != 2"


class CiProvider(LocalProvider):
    """``local`` with checks from a script (the last one repeats) and logs per check."""

    reports_checks = True

    def __init__(self, repo: Path, checks: list[ChecksStatus]) -> None:
        super().__init__(repo, load_run_config(repo).config.settings)
        self.script = list(checks)
        self.asked: list[str] = []  # the PR head at each read of the checks
        self.logs_for: list[tuple[str, ...]] = []

    def checks(self, pr: PullRequest) -> ChecksStatus:
        self.asked.append(git(self.root, "rev-parse", pr.branch))
        return self.script.pop(0) if len(self.script) > 1 else self.script[0]

    def check_logs(self, pr: PullRequest, failing: tuple[str, ...]) -> dict[str, str]:
        self.logs_for.append(failing)
        return {name: LOG for name in failing}


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    """The run repo with a reviewed workflow and a ``ci-fix`` the planner plays."""
    repo = make_run_repo(tmp_path / "repo")
    write(
        repo,
        ".factory/agents.yaml",
        "defaults:\n  harness: claude\n  model: sonnet\n"
        "agents:\n  - name: planner\n  - name: builder\n  - name: tester\n"
        "  - name: documenter\n  - name: reviewer\n",
    )
    write(repo, ".factory/prompts/reviewer/system.md", "You are the reviewer.\n")
    write(repo, ".factory/prompts/reviewer/user.md", USER_PROMPT)
    write(
        repo,
        ".factory/workflows/plan-review-commit.yaml",
        "name: plan-review-commit\ndescription: Plan, review, commit\n"
        "steps: [plan, review, commit]\n",
    )
    # The repo's own ci-fix wins over the packaged one: the planner plays the repair.
    write(
        repo,
        ".factory/workflows/ci-fix.yaml",
        "name: ci-fix\ndescription: Repair the red checks\nsteps: [plan, commit]\n",
    )
    index = repo / "backlog/M01-core/index.md"
    index.write_text(
        index.read_text(encoding="utf-8").replace("plan-commit", "plan-review-commit"),
        encoding="utf-8",
    )
    commit_all(repo, "reviewed workflow and ci-fix")
    return repo


def first_run(repo: Path, script: Script) -> TaskRunResult:
    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add schema spec"))
    script.add("reviewer", ok(approved=True, findings=[{"requirement": "x", "met": True}]))
    result = run_task(repo, T01)
    assert result.ok, (result.run.error, result.pr_error)
    return result


def repair(script: Script, *, outside: bool = False) -> None:
    """The planner of a ci-fix run; `outside` writes outside the task's scope (run fails)."""
    rel = "README.md" if outside else FIX
    script.on("planner", lambda wt: write(wt, rel, "FIXED = True\n"))
    script.add("planner", ok(artifacts=[], changed_files=[rel], commit_message="Fix CI"))


def pr(repo: Path) -> TaskPrRow:
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        row = store.latest_pr(T01)
    finally:
        store.close()
    assert row is not None
    return row


def runs(repo: Path) -> list[TaskRunRow]:
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        return store.for_task(T01)  # newest first
    finally:
        store.close()


def prs(repo: Path) -> int:
    conn = sqlite3.connect(repo / ".factory" / "trace.db")
    try:
        return int(conn.execute("SELECT COUNT(*) FROM task_prs").fetchone()[0])
    finally:
        conn.close()


def on_main(repo: Path, rel: str) -> bool:
    return bool(git(repo, "ls-tree", "--name-only", "main", rel))


def base_task(repo: Path) -> Task:
    node = load_backlog(repo).by_id[T01]
    assert isinstance(node, Task)
    return node


def approve(
    repo: Path, first: TaskRunResult, provider: GitProvider, auto: bool
) -> tuple[bool, str | None, list[str]]:
    """``(merged, code, ci_fix_runs)`` of an operator approve or an auto-merge of `first`."""
    if auto:
        merge = try_auto_merge(repo, first, base_task(repo), provider=provider)
        fixes = merge.approve.ci_fix_runs if merge.approve is not None else []
        return merge.merged, merge.code, fixes
    try:
        approved = approve_task(repo, T01, provider=provider)
    except ReviewError as exc:
        return False, exc.code, []
    return True, None, approved.ci_fix_runs


MODES = pytest.mark.parametrize("auto", [False, True], ids=["operator", "auto-merge"])


@MODES
@pytest.mark.parametrize("checks", [NONE, GREEN], ids=["no-checks", "green"])
def test_merges_without_red_checks(
    repo: Path, script: Script, auto: bool, checks: ChecksStatus
) -> None:
    first = first_run(repo, script)
    provider = CiProvider(repo, [checks])

    merged, code, fixes = approve(repo, first, provider, auto)

    assert (merged, code, fixes) == (True, None, [])
    row = pr(repo)
    assert row.state == "merged" and row.auto_merge_error is None
    assert row.merged_by == (MERGED_BY_AUTO if auto else MERGED_BY_OPERATOR)
    # the checks read are those of the head with the status: done commit
    assert provider.asked == [git(repo, "rev-parse", BRANCH)]
    assert git(repo, "log", "-1", "--format=%s", BRANCH) == f"{T01}: status done"
    assert provider.logs_for == []
    assert [r.workflow for r in runs(repo)] == ["plan-review-commit"]


@MODES
def test_red_checks_are_repaired_on_the_same_branch(repo: Path, script: Script, auto: bool) -> None:
    first = first_run(repo, script)
    provider = CiProvider(repo, [RED, GREEN])
    repair(script)

    merged, code, fixes = approve(repo, first, provider, auto)

    assert (merged, code) == (True, None)
    fix_run = runs(repo)[0]
    assert fixes == [fix_run.run_id]
    assert (fix_run.workflow, fix_run.started_by, fix_run.branch, fix_run.state) == (
        "ci-fix",
        "auto-ci-fix",
        BRANCH,
        "succeeded",
    )
    assert fix_run.note is not None
    assert "CI checks failed on this PR" in fix_run.note
    assert "- unit tests" in fix_run.note and LOG in fix_run.note
    assert LOG in script.calls[-1].prompt  # the repair agent got the log
    assert provider.logs_for == [("unit tests",)]
    assert prs(repo) == 1  # the same PR, no new one
    row = pr(repo)
    assert row.state == "merged" and row.branch == BRANCH and row.auto_merge_error is None
    assert on_main(repo, FIX)
    # the repair lands on top of the done commit; the second read is of the repaired head
    assert git(repo, "log", "-2", "--format=%s", BRANCH).splitlines() == [
        "Fix CI",
        f"{T01}: status done",
    ]
    assert provider.asked == [git(repo, "rev-parse", f"{BRANCH}~1"), git(repo, "rev-parse", BRANCH)]


@MODES
def test_checks_red_after_every_repair_keep_the_pr_open(
    repo: Path, script: Script, auto: bool
) -> None:
    first = first_run(repo, script)
    provider = CiProvider(repo, [RED])
    for _ in range(ci.CI_FIX_ROUNDS):
        repair(script)

    merged, code, _ = approve(repo, first, provider, auto)

    assert (merged, code) == (False, "checks_failing")
    fix_runs = [r for r in runs(repo) if r.workflow == "ci-fix"]
    assert len(fix_runs) == ci.CI_FIX_ROUNDS
    assert all(r.branch == BRANCH and r.started_by == "auto-ci-fix" for r in fix_runs)
    row = pr(repo)
    assert row.state == "open"
    error = row.auto_merge_error or ""
    assert error.startswith("checks_failing: ")
    assert "unit tests" in error and f"after {ci.CI_FIX_ROUNDS} ci-fix run(s)" in error
    assert not on_main(repo, FIX)
    assert len(provider.asked) == ci.CI_FIX_ROUNDS + 1


@MODES
def test_checks_running_past_the_limit_keep_the_pr_open(
    repo: Path, script: Script, auto: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _Clock()
    monkeypatch.setattr(ci, "_clock", clock)
    monkeypatch.setattr(ci, "sleep", clock.sleep)
    monkeypatch.setattr(ci, "AUTO_MERGE_CHECKS_TIMEOUT", 60.0)
    first = first_run(repo, script)
    provider = CiProvider(repo, [PENDING])

    merged, code, _ = approve(repo, first, provider, auto)

    assert (merged, code) == (False, "checks_pending")
    assert clock.sleeps == [ci.AUTO_MERGE_CHECKS_DELAY] * 4
    assert [r.workflow for r in runs(repo)] == ["plan-review-commit"]
    row = pr(repo)
    assert row.state == "open" and (row.auto_merge_error or "").startswith("checks_pending: ")


@MODES
def test_failed_repair_run_keeps_the_pr_open(repo: Path, script: Script, auto: bool) -> None:
    first = first_run(repo, script)
    provider = CiProvider(repo, [RED, GREEN])
    repair(script, outside=True)

    merged, code, _ = approve(repo, first, provider, auto)

    assert (merged, code) == (False, "ci_fix_failed")
    fix_run = runs(repo)[0]
    assert fix_run.workflow == "ci-fix" and fix_run.state == "failed"
    row = pr(repo)
    assert row.state == "open"
    error = row.auto_merge_error or ""
    assert error.startswith("ci_fix_failed: ") and fix_run.run_id in error
    assert len(provider.asked) == 1


def test_approve_records_the_repairs(
    repo: Path, script: Script, capsys: pytest.CaptureFixture[str]
) -> None:
    first_run(repo, script)
    repair(script)
    provider = CiProvider(repo, [RED, GREEN])

    approved = approve_task(repo, T01, provider=provider)

    assert approved.to_json()["ci_fix_runs"] == approved.ci_fix_runs
    assert len(approved.ci_fix_runs) == 1


# ── head_checks, ci_report, run_task ─────────────────────────────────────────


class _Clock:
    """A clock that moves only when the gate sleeps."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class _Hosting:
    """Shows the previous head (and its green checks) until the third status read."""

    reports_checks = True

    def __init__(self) -> None:
        self.reads = 0

    def status(self, pr: PullRequest) -> PrStatus:
        self.reads += 1
        return PrStatus("open", "mergeable", head_sha="new" if self.reads >= 3 else "old")

    def checks(self, pr: PullRequest) -> ChecksStatus:
        return RED if self.reads >= 3 else GREEN


PR = PullRequest(id="7", url="u", branch=BRANCH, base="main", title="t")


def test_head_checks_ignore_the_previous_head(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock()
    monkeypatch.setattr(ci, "_clock", clock)
    monkeypatch.setattr(ci, "sleep", clock.sleep)
    monkeypatch.setattr(ci, "AUTO_MERGE_CHECKS_APPEAR", 90.0)
    hosting = _Hosting()

    checks = ci.head_checks(cast(GitProvider, hosting), PR, "new")

    assert checks == RED
    assert hosting.reads == 3
    assert clock.sleeps == [ci.AUTO_MERGE_CHECKS_DELAY] * 2


def test_ci_report_keeps_the_end_of_long_logs() -> None:
    long_log = "start\n" + "x" * (ci.CI_REPORT_LIMIT * 2) + "\nthe real error"
    report = ci.ci_report(("a", "b"), {"a": long_log, "b": "short log"})

    assert len(report) <= ci.CI_REPORT_LIMIT
    assert report.startswith("## CI checks failed on this PR\n\n- a\n- b\n")
    assert "the real error" in report and "start" not in report
    assert "short log" in report
    assert report.rstrip().endswith("your allowed paths.")
    assert "do not disable or skip checks" in report


def test_ci_report_without_logs_names_the_checks() -> None:
    report = ci.ci_report(("lint",), {})
    assert "- lint" in report and "```" not in report


def test_run_task_with_a_workflow_needs_the_branch(repo: Path) -> None:
    with pytest.raises(TaskRunError) as info:
        run_task(repo, T01, workflow_name="ci-fix")
    assert info.value.code == "unknown_branch"
