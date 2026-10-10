"""Auto-merge after a reviewed run: `run_chain`, `try_auto_merge`, CLI; fake harnesses.

Provider ``local`` (a branch is the PR) and a fake ``gh`` for ``github``; no test
calls a model or the network.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from run_repo import (
    USER_PROMPT,
    Script,
    commit_all,
    fake_env,
    git,
    make_run_repo,
    ok,
    scripted_plan,
    write,
)
from workflow_fakes import FakeCodeRunner

import aifactory.review.automerge as automerge
from aifactory.backlog import Task, load_backlog
from aifactory.cli import main
from aifactory.config import load_run_config
from aifactory.providers.github import GitHubProvider
from aifactory.review import approve_task, try_auto_merge
from aifactory.review.automerge import AutoMergeResult, resolve_and_merge
from aifactory.run import (
    STOP_DISABLED,
    STOP_EXHAUSTED,
    STOP_FAILED,
    STOP_NOT_MERGED,
    TaskPrRow,
    TaskRunStore,
    run_chain,
    run_task,
)
from aifactory.run.store import MERGED_BY_AUTO, MERGED_BY_OPERATOR
from aifactory.workflow import EngineCodeRunner
from cli_json import read_envelope

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "providers"))

from gh_fake import install_fake_gh, prepare_shared_gh, reply  # noqa: E402

Capsys = pytest.CaptureFixture[str]
T01, T02, T03 = "M01-S01-T01", "M01-S01-T02", "M01-S01-T03"
CORE = "backlog/M01-core"
REVIEWED = "plan-review-commit"
MERGE_SHA = "b" * 40

AGENTS = (
    "defaults:\n  harness: claude\n  model: sonnet\n"
    "agents:\n  - name: planner\n  - name: builder\n  - name: tester\n  - name: documenter\n"
    "  - name: reviewer\n"
)


@pytest.fixture(scope="module", autouse=True)
def _shared_gh(tmp_path_factory: pytest.TempPathFactory) -> None:
    prepare_shared_gh(tmp_path_factory.mktemp("ghwarm"))


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def _task(
    repo: Path, task_id: str, *, depends_on: list[str] | None = None, extra: str = ""
) -> None:
    deps = f"depends_on: [{', '.join(depends_on)}]\n" if depends_on else ""
    write(
        repo,
        f"{CORE}/S01-model/{task_id}.md",
        f"---\nid: {task_id}\ntitle: Task {task_id}\nstatus: todo\n{deps}{extra}---\n\n"
        f"Do {task_id}.\n",
    )


def setup(
    repo: Path,
    *,
    workflow: str = REVIEWED,
    step: str = "auto_merge: true\n",
    t01_extra: str = "",
    t02_depends: bool = True,
) -> None:
    """S01 with T01..T03 writing src/app/; a workflow with review (no accept on it)."""
    write(repo, ".factory/agents.yaml", AGENTS)
    write(repo, ".factory/prompts/reviewer/system.md", "You are the reviewer.\n")
    write(repo, ".factory/prompts/reviewer/user.md", USER_PROMPT)
    write(
        repo,
        f".factory/workflows/{REVIEWED}.yaml",
        f"name: {REVIEWED}\ndescription: Plan, review, commit\nsteps: [plan, review, commit]\n",
    )
    write(repo, f"{CORE}/index.md", f"---\nid: M01\ntitle: Core\nworkflow: {workflow}\n---\n")
    s01 = repo / CORE / "S01-model"
    shutil.rmtree(s01)
    write(
        repo,
        f"{CORE}/S01-model/index.md",
        f"---\nid: M01-S01\ntitle: Model\nwrites: [src/app/]\n{step}---\n",
    )
    _task(repo, T01, extra=t01_extra)
    _task(repo, T02, depends_on=[T01] if t02_depends else None)
    commit_all(repo, "auto-merge backlog")


def build(script: Script, name: str, path: str | None = None, text: str | None = None) -> None:
    rel = path or f"src/app/{name}.py"
    body = text if text is not None else f"NAME = {name!r}\n"
    script.on("planner", lambda wt: write(wt, rel, body))
    script.add("planner", ok(artifacts=[], changed_files=[rel], commit_message=f"Add {name}"))


def review(script: Script, *, approved: bool = True) -> None:
    if approved:
        script.add("reviewer", ok(approved=True, findings=[{"requirement": "x", "met": True}]))
    else:
        script.add("reviewer", ok(approved=False, blocking=["missing tests"]))


def pr_row(repo: Path, task_id: str) -> TaskPrRow | None:
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        return store.latest_pr(task_id)
    finally:
        store.close()


def on_main(repo: Path, rel: str) -> bool:
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"main:{rel}"], cwd=repo, capture_output=True
        ).returncode
        == 0
    )


def status_on_main(repo: Path, task_id: str) -> str:
    text = git(repo, "show", f"main:{CORE}/S01-model/{task_id}.md")
    return next(
        line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("status:")
    )


def base_task(repo: Path, task_id: str) -> Task:
    node = load_backlog(repo).by_id[task_id]
    assert isinstance(node, Task)
    return node


# ── run_chain, provider local ────────────────────────────────────────────────


def test_merges_a_reviewed_run(repo: Path, script: Script) -> None:
    setup(repo)
    build(script, "one")
    review(script)

    chain = run_chain(repo, T01)

    assert chain.stop == STOP_DISABLED
    result = chain.runs[0]
    assert result.auto_merge is not None and result.auto_merge.merged, result.auto_merge
    assert on_main(repo, "src/app/one.py")
    assert status_on_main(repo, T01) == "done"
    row = pr_row(repo, T01)
    assert row is not None
    assert (row.state, row.merged_by, row.auto_merge_error) == ("merged", MERGED_BY_AUTO, None)
    assert chain.to_json()["runs"][0]["auto_merge"]["merged_by"] == "auto-merge"  # type: ignore[index]


def test_failed_run_is_not_merged(repo: Path, script: Script) -> None:
    setup(repo)
    build(script, "bad", path="README.md")  # outside writes: the run fails

    chain = run_chain(repo, T01)

    assert chain.stop == STOP_FAILED
    assert chain.runs[0].auto_merge is None
    assert pr_row(repo, T01) is None


def test_workflow_without_review_is_never_merged(repo: Path, script: Script) -> None:
    setup(repo, workflow="plan-commit")
    build(script, "one")

    chain = run_chain(repo, T01)

    result = chain.runs[0]
    assert result.ok
    assert result.auto_merge is not None and not result.auto_merge.merged
    assert result.auto_merge.code == "no_review_phase"
    row = pr_row(repo, T01)
    assert row is not None and row.state == "open"
    assert (row.auto_merge_error or "").startswith("no_review_phase: ")
    assert not on_main(repo, "src/app/one.py")


def test_rejected_review_is_not_merged(repo: Path, script: Script) -> None:
    setup(repo)
    build(script, "one")
    review(script, approved=False)

    chain = run_chain(repo, T01)

    result = chain.runs[0]
    assert result.ok, result.run.error
    assert result.auto_merge is not None and result.auto_merge.code == "review_rejected"
    row = pr_row(repo, T01)
    assert row is not None and row.state == "open"
    assert (row.auto_merge_error or "").startswith("review_rejected: ")
    assert "missing tests" in (row.auto_merge_error or "")
    assert not on_main(repo, "src/app/one.py")


def test_task_switches_auto_merge_off(repo: Path, script: Script) -> None:
    setup(repo, t01_extra="auto_merge: false\n")
    build(script, "one")
    review(script)

    chain = run_chain(repo, T01)

    assert chain.stop == STOP_DISABLED
    assert chain.runs[0].auto_merge is None
    row = pr_row(repo, T01)
    assert row is not None and row.state == "open" and row.auto_merge_error is None


def test_conflict_keeps_the_pr_open(repo: Path, script: Script) -> None:
    setup(repo)
    build(script, "one", text="NAME = 'branch'\n")
    review(script)
    result = run_task(repo, T01)
    assert result.ok, (result.run.error, result.pr_error)
    write(repo, "src/app/one.py", "NAME = 'main'\n")
    commit_all(repo, "conflicting change on main")

    merge = try_auto_merge(repo, result, base_task(repo, T01))

    assert not merge.merged and merge.code == "conflict"
    row = pr_row(repo, T01)
    assert row is not None and row.state == "open"
    assert (row.auto_merge_error or "").startswith("conflict: ")
    assert git(repo, "show", "main:src/app/one.py") == "NAME = 'main'"


def test_chain_continues_after_the_merge(repo: Path, script: Script) -> None:
    setup(repo, step="auto_merge: true\nauto_continue: true\n")
    build(script, "one")
    review(script)
    build(script, "two")
    review(script)

    chain = run_chain(repo, T01)

    assert [r.run.task_id for r in chain.runs] == [T01, T02]
    assert chain.stop == STOP_EXHAUSTED
    assert all(r.auto_merge is not None and r.auto_merge.merged for r in chain.runs)
    second = chain.runs[1].run
    # T02 started from the base that holds T01's merged change
    assert git(repo, "cat-file", "-t", f"{second.base_sha}:src/app/one.py") == "blob"
    for task_id in (T01, T02):
        row = pr_row(repo, task_id)
        assert row is not None and row.merged_by == MERGED_BY_AUTO
        assert status_on_main(repo, task_id) == "done"


def test_chain_stops_when_not_merged(repo: Path, script: Script, capsys: Capsys) -> None:
    setup(repo, step="auto_merge: true\nauto_continue: true\n")
    build(script, "one")
    review(script, approved=False)

    code = main(["task", "run", T01, "--repo", str(repo)])

    out = capsys.readouterr().out
    assert code == 0
    assert "auto-merge: not merged (review_rejected)" in out
    assert f"factory task approve {T01}" in out
    assert "auto-continue: stopped (not_merged)" in out
    assert pr_row(repo, T02) is None


def test_cli_json_reports_auto_merge(repo: Path, script: Script, capsys: Capsys) -> None:
    setup(repo)
    build(script, "one")
    review(script)

    code = main(["task", "run", T01, "--repo", str(repo), "--json"])

    env = read_envelope(capsys)
    assert code == 0
    data = env["data"]
    assert data["auto_merge"]["merged"] is True
    assert data["auto_merge"]["merged_by"] == "auto-merge"
    assert data["chain"]["runs"][0]["auto_merge"]["merged"] is True
    assert data["chain"]["stop"] == STOP_DISABLED


def test_cli_text_reports_merge(repo: Path, script: Script, capsys: Capsys) -> None:
    setup(repo)
    build(script, "one")
    review(script)

    assert main(["task", "run", T01, "--repo", str(repo)]) == 0

    out = capsys.readouterr().out
    assert "auto-merge: merged " in out
    assert STOP_NOT_MERGED not in out


def test_operator_approve_records_operator(repo: Path, script: Script) -> None:
    setup(repo, step="")
    build(script, "one")
    review(script)
    result = run_task(repo, T01)
    assert result.ok

    approved = approve_task(repo, T01)

    assert approved.merged_by == MERGED_BY_OPERATOR
    assert approved.to_json()["merged_by"] == "operator"
    row = pr_row(repo, T01)
    assert row is not None and row.merged_by == MERGED_BY_OPERATOR


# ── provider github with a fake gh ───────────────────────────────────────────


def _view(state: str = "OPEN", merge: str | None = None) -> dict[str, Any]:
    return reply(
        {
            "state": state,
            "mergeable": "MERGEABLE" if state == "OPEN" else "UNKNOWN",
            "headRefOid": "x",
            "mergeCommit": {"oid": merge} if merge else None,
        }
    )


def _github_run(
    repo: Path, script: Script, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, GitHubProvider, Any]:
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, capture_output=True
    )
    setup(repo)
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "-u", "origin", "main")
    write(repo, ".factory/config.yaml", "base: main\ngit_provider: github\n")
    commit_all(repo, "github")
    git(repo, "push", "-q", "origin", "main")
    log = install_fake_gh(
        tmp_path, monkeypatch, {"pr create": reply("https://github.com/o/r/pull/7\n")}
    )
    provider = GitHubProvider(
        repo, load_run_config(repo).config.settings, attempts=1, delay=0, sleep=lambda _: None
    )
    build(script, "one")
    review(script)
    result = run_task(repo, T01, provider=provider)
    assert result.ok, (result.run.error, result.pr_error)
    log.clear()
    return result, provider, log


def _merges(log: Any) -> list[list[str]]:
    return [a for a in log.argvs() if a[:2] == ["pr", "merge"]]


def test_github_red_checks_block(
    repo: Path, script: Script, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, provider, log = _github_run(repo, script, tmp_path, monkeypatch)
    log.respond("pr view", _view())
    log.respond(
        "pr checks", reply([{"name": "ci", "bucket": "fail"}, {"name": "lint", "bucket": "pass"}])
    )

    merge = try_auto_merge(repo, result, base_task(repo, T01), provider=provider)

    assert not merge.merged and merge.code == "checks_failing"
    assert "ci" in (merge.reason or "") and "lint" not in (merge.reason or "")
    assert _merges(log) == []
    row = pr_row(repo, T01)
    assert row is not None and row.state == "open"
    assert (row.auto_merge_error or "").startswith("checks_failing: ")


@pytest.mark.parametrize(
    "checks",
    [
        reply([{"name": "ci", "bucket": "pass"}, {"name": "slow", "bucket": "pending"}]),
        reply(exit=1, stderr="no checks reported on the 'factory/M01-S01-T01-1' branch\n"),
    ],
    ids=["green-and-pending", "no-checks"],
)
def test_github_merges_without_red_checks(
    repo: Path,
    script: Script,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    checks: dict[str, Any],
) -> None:
    result, provider, log = _github_run(repo, script, tmp_path, monkeypatch)
    # auto-merge status, approve's status, merge's status, the state after `pr merge`
    log.respond("pr view", [_view(), _view(), _view(), _view("MERGED", MERGE_SHA)])
    log.respond("pr checks", checks)
    log.respond("pr merge", reply(""))

    merge = try_auto_merge(repo, result, base_task(repo, T01), provider=provider)

    assert merge.merged, (merge.code, merge.reason)
    assert merge.merge_sha == MERGE_SHA
    assert len(_merges(log)) == 1
    assert any(a[:2] == ["pr", "checks"] for a in log.argvs())
    row = pr_row(repo, T01)
    assert row is not None
    assert (row.state, row.merged_by, row.merge_sha) == ("merged", MERGED_BY_AUTO, MERGE_SHA)


def test_github_unknown_mergeability_retries_until_status_error(
    repo: Path, script: Script, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _, log = _github_run(repo, script, tmp_path, monkeypatch)
    sleeps: list[float] = []
    monkeypatch.setattr(automerge, "sleep", sleeps.append)
    provider = GitHubProvider(repo, load_run_config(repo).config.settings, sleep=sleeps.append)
    unknown = reply({"state": "OPEN", "mergeable": "UNKNOWN", "headRefOid": "x"})
    log.respond("pr view", [unknown] * 30 + [reply(exit=1, stderr="upstream unavailable")])
    log.respond("pr checks", reply([]))

    merge = try_auto_merge(repo, result, base_task(repo, T01), provider=provider)

    assert merge.code == "status_unavailable"
    assert "upstream unavailable" in (merge.reason or "")
    assert _merges(log) == []
    assert sleeps == [2.0] * 30
    row = pr_row(repo, T01)
    assert row is not None and row.state == "open"
    assert (row.auto_merge_error or "").startswith("status_unavailable: ")


@pytest.mark.parametrize("mergeable", ["MERGEABLE", "CONFLICTING", "CHECKS_FAILING"])
def test_github_auto_merge_waits_for_slow_mergeability(
    repo: Path,
    script: Script,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mergeable: str,
) -> None:
    result, _, log = _github_run(repo, script, tmp_path, monkeypatch)
    sleeps: list[float] = []
    monkeypatch.setattr(automerge, "sleep", sleeps.append)
    provider = GitHubProvider(repo, load_run_config(repo).config.settings, sleep=sleeps.append)
    unknown = reply({"state": "OPEN", "mergeable": "UNKNOWN", "headRefOid": "x"})
    resolved = reply(
        {
            "state": "OPEN",
            "mergeable": "MERGEABLE" if mergeable == "CHECKS_FAILING" else mergeable,
            "headRefOid": "x",
        }
    )
    # Resolve beyond two full polling batches without any operator action.
    log.respond(
        "pr view", [unknown] * 64 + [resolved, _view(), _view(), _view("MERGED", MERGE_SHA)]
    )
    log.respond(
        "pr checks",
        reply([{"name": "ci", "bucket": "fail"}] if mergeable == "CHECKS_FAILING" else []),
    )
    log.respond("pr merge", reply(""))

    merge = try_auto_merge(repo, result, base_task(repo, T01), provider=provider)

    assert sleeps == [2.0] * 64
    row = pr_row(repo, T01)
    assert row is not None
    if mergeable == "MERGEABLE":
        assert merge.merged, (merge.code, merge.reason)
        assert len(_merges(log)) == 1
        assert (row.state, row.merged_by, row.auto_merge_error) == ("merged", MERGED_BY_AUTO, None)
    else:
        code = "checks_failing" if mergeable == "CHECKS_FAILING" else "conflict"
        assert not merge.merged and merge.code == code
        assert _merges(log) == []
        assert row.state == "open"
        assert (row.auto_merge_error or "").startswith(f"{code}: ")


@pytest.mark.parametrize("state", ["CLOSED", "MERGED"])
def test_github_auto_merge_stops_if_unknown_pr_becomes_inactive(
    repo: Path,
    script: Script,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    result, _, log = _github_run(repo, script, tmp_path, monkeypatch)
    sleeps: list[float] = []
    monkeypatch.setattr(automerge, "sleep", sleeps.append)
    provider = GitHubProvider(repo, load_run_config(repo).config.settings, sleep=sleeps.append)
    unknown = reply({"state": "OPEN", "mergeable": "UNKNOWN", "headRefOid": "x"})
    log.respond("pr view", [unknown] * 31 + [_view(state, MERGE_SHA)])
    log.respond("pr checks", reply([]))

    merge = try_auto_merge(repo, result, base_task(repo, T01), provider=provider)

    assert not merge.merged and merge.code == "pr_not_open"
    assert state.lower() in (merge.reason or "")
    assert _merges(log) == []
    assert sleeps == [2.0] * 31


# ── trace DB of an older version ─────────────────────────────────────────────


def test_store_adds_the_new_columns(tmp_path: Path) -> None:
    db = tmp_path / "trace.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE task_prs (branch TEXT PRIMARY KEY, task_id TEXT NOT NULL, "
        "provider TEXT NOT NULL, pr_id TEXT NOT NULL, url TEXT NOT NULL, base TEXT NOT NULL, "
        "base_sha TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, state TEXT NOT NULL, "
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, merged_at TEXT, merge_sha TEXT);"
        "INSERT INTO task_prs VALUES ('factory/T-1', 'T', 'local', 'factory/T-1', 'u', 'main', "
        "'s', 't', 'b', 'merged', 'c', 'u', 'm', 'x');"
    )
    conn.commit()
    conn.close()

    store = TaskRunStore(db)
    try:
        row = store.pr_for_branch("factory/T-1")
        assert row is not None and row.merged_by is None and row.auto_merge_error is None
        store.update_pr("factory/T-1", merged_by=MERGED_BY_OPERATOR)
        again = store.pr_for_branch("factory/T-1")
        assert again is not None and again.merged_by == MERGED_BY_OPERATOR
    finally:
        store.close()
    TaskRunStore(db).close()  # opening an up-to-date DB again changes nothing
    columns = [r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(task_prs)")]
    assert columns[-2:] == ["merged_by", "auto_merge_error"]
    assert json.dumps(columns)  # plain strings


def test_store_adds_started_by_to_older_runs(tmp_path: Path) -> None:
    db = tmp_path / "trace.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE task_runs (run_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, "
        "branch TEXT NOT NULL, worktree TEXT NOT NULL, base TEXT NOT NULL, "
        "base_sha TEXT NOT NULL, head_sha TEXT, state TEXT NOT NULL, started_at TEXT NOT NULL, "
        "ended_at TEXT, pid INTEGER, workflow TEXT, note TEXT, error TEXT);"
        "INSERT INTO task_runs VALUES ('r1', 'T', 'b', 'w', 'main', 's', NULL, 'succeeded', "
        "'2026-01-01', '2026-01-01', NULL, 'plan', NULL, NULL);"
    )
    conn.commit()
    conn.close()
    store = TaskRunStore(db)
    try:
        row = store.get("r1")
        assert row is not None and row.started_by is None and row.archived == 0
    finally:
        store.close()


# ── auto-resolve ─────────────────────────────────────────────────────────────


class ResolveCode(FakeCodeRunner):
    """A real ``rebase`` step and a scripted suite."""

    def rebase(self, run: Any) -> Any:
        return EngineCodeRunner().rebase(run)


def _conflicting_run(repo: Path, script: Script) -> Any:
    setup(repo)
    build(script, "one", text="NAME = 'branch'\n")
    review(script)
    result = run_task(repo, T01)
    assert result.ok, (result.run.error, result.pr_error)
    write(repo, "src/app/one.py", "NAME = 'main'\n")
    commit_all(repo, "conflicting change on main")
    return result


def _resolver(script: Script) -> None:
    script.on("builder", lambda wt: write(wt, "src/app/one.py", "NAME = 'both'\n"))
    script.add("builder", ok(changed_files=["src/app/one.py"], commit_message="Resolve one"))
    scripted_plan(script)


def test_conflict_is_resolved_reviewed_and_merged(repo: Path, script: Script) -> None:
    result = _conflicting_run(repo, script)
    _resolver(script)
    review(script)

    resolved, merge = resolve_and_merge(
        repo, result, base_task(repo, T01), code=ResolveCode([True])
    )

    assert resolved is not None and resolved.run.workflow == "resolve-reviewed"
    assert (result.run.started_by, resolved.run.started_by) == ("manual", "auto-resolve")
    assert merge.merged, (merge.code, merge.reason)
    assert git(repo, "show", "main:src/app/one.py") == "NAME = 'both'"
    row = pr_row(repo, T01)
    assert row is not None and row.state == "merged" and not row.auto_merge_error
    assert [c.agent for c in script.calls][-4:] == [
        "builder",
        "tester",
        "test-reviewer",
        "reviewer",
    ]


def test_rejected_resolution_keeps_the_pr_open(repo: Path, script: Script) -> None:
    result = _conflicting_run(repo, script)
    _resolver(script)
    review(script, approved=False)

    _, merge = resolve_and_merge(repo, result, base_task(repo, T01), code=ResolveCode([True]))

    assert not merge.merged and merge.code == "resolve_failed"
    row = pr_row(repo, T01)
    assert row is not None and row.state == "open"
    assert (row.auto_merge_error or "").startswith("resolve_failed: ")
    assert git(repo, "show", "main:src/app/one.py") == "NAME = 'main'"


def test_chain_resolves_a_conflict_once(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup(repo)
    build(script, "one")
    review(script)
    calls: list[str] = []

    def conflict(repo_: Path, result: Any, task: Task, **_: Any) -> AutoMergeResult:
        return AutoMergeResult(False, "conflict", "the PR does not merge into base", "url")

    def resolve_once(repo_: Path, result: Any, task: Task, **_: Any) -> Any:
        calls.append(task.id)
        return None, AutoMergeResult(False, "conflict", "again (after auto-resolve)", "url")

    monkeypatch.setattr(automerge, "try_auto_merge", conflict)
    monkeypatch.setattr(automerge, "resolve_and_merge", resolve_once)

    chain = run_chain(repo, T01)

    assert calls == [T01]
    assert chain.stop == STOP_DISABLED
    assert chain.runs[0].auto_merge is not None
    assert chain.runs[0].auto_merge.reason == "again (after auto-resolve)"


# ── auto-resolve in a parallel chain member (`task run --member`) ────────────


def _member(
    repo: Path,
    script: Script,
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    approve: bool = True,
) -> Any:
    """`_member_run` of a run whose PR conflicts; `events` records the lock and resolve."""
    import contextlib

    import aifactory.run as run_pkg
    from aifactory.cli import _member_run
    from aifactory.review import flow as review_flow

    result = _conflicting_run(repo, script)
    _resolver(script)
    review(script, approved=approve)
    monkeypatch.setattr(run_pkg, "run_task", lambda *a, **k: result)
    real_lock = TaskRunStore.merge_lock
    real_resolve = review_flow.resolve_task

    @contextlib.contextmanager
    def merge_lock(self: TaskRunStore, timeout: float = 600.0) -> Iterator[None]:
        with real_lock(self, timeout):
            events.append("lock")
            yield
            events.append("unlock")

    def resolve_task(*args: Any, **kwargs: Any) -> Any:
        events.append("resolve")
        return real_resolve(*args, **kwargs)

    monkeypatch.setattr(TaskRunStore, "merge_lock", merge_lock)
    monkeypatch.setattr(review_flow, "resolve_task", resolve_task)
    return _member_run(repo, T01, None, False, code=ResolveCode([True]))


def test_member_resolves_a_conflict_and_merges(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    member = _member(repo, script, monkeypatch, events)

    merge = member.auto_merge
    assert merge is not None and merge.merged, (merge.code, merge.reason)
    # the resolve runs outside the lock, the merge after it under the lock
    assert events == ["lock", "unlock", "resolve", "lock", "unlock"]
    resolved = member.resolve_run
    assert resolved is not None and resolved.run.workflow == "resolve-reviewed"
    assert resolved.run.run_id != member.run.run_id
    assert git(repo, "show", "main:src/app/one.py") == "NAME = 'both'"
    row = pr_row(repo, T01)
    assert row is not None and row.state == "merged" and not row.auto_merge_error


def test_member_rejected_resolution_keeps_the_pr_open(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    member = _member(repo, script, monkeypatch, events, approve=False)

    merge = member.auto_merge
    assert merge is not None and not merge.merged and merge.code == "resolve_failed"
    assert events == ["lock", "unlock", "resolve"]  # no merge, no second lock
    assert member.resolve_run is not None and member.resolve_run.run.state != "succeeded"
    row = pr_row(repo, T01)
    assert row is not None and row.state == "open"
    assert (row.auto_merge_error or "").startswith("resolve_failed: ")
    assert git(repo, "show", "main:src/app/one.py") == "NAME = 'main'"
