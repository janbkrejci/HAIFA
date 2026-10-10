"""The Review screen's API with provider ``local`` and the fake harnesses.

Return and resolve start through the test double ``ThreadLauncher`` (the fake harnesses
live in the test process; the process launcher is covered by ``test_web_launcher``).
Approve, return and resolve go through ``aifactory.review.approve_task``, ``return_task``
and ``resolve_task``, the functions behind ``factory task approve|return|resolve``. No test
calls a model or the network.
"""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

import aifactory.review
from aifactory.review import approve_task, resolve_task
from aifactory.run import TaskRunResult, TaskRunStore, run_task
from aifactory.skill import envelope_problems
from aifactory.web import create_app
from aifactory.web.review import _review_verdict
from aifactory.workflow import EngineCodeRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workflow"))

from run_repo import SPEC, T01, T02, Script, commit_all, fake_env, git, make_run_repo, ok, write  # noqa: E402,I001
from workflow_fakes import FakeCodeRunner, plan_envelope  # noqa: E402
from thread_launcher import ThreadLauncher  # noqa: E402,I001

BASE = "http://127.0.0.1:4700"
MODEL = "src/app/model.py"
SPEC2 = "specs/M01-S01-T02-loader.md"
TASK1 = "backlog/M01-core/S01-model/M01-S01-T01-schema.md"
BRANCH1 = f"factory/{T01}-1"
BRANCH2 = f"factory/{T02}-1"
MODULE_INDEX = "backlog/M01-core/index.md"


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
    write(
        repo,
        MODULE_INDEX,
        "---\nid: M01\ntitle: Core\nworkflow: plan-commit\nowner: alice\n---\n\nJádro.\n",
    )
    write(repo, MODEL, "VALUE = 0\n")
    commit_all(repo, "owner and model")
    return repo


@pytest.fixture(name="app")
def app_fixture(repo: Path, tmp_path: Path, script: Script) -> Iterator[Starlette]:
    app = create_app(repo, static_dir=tmp_path / "nostatic", launcher=ThreadLauncher())
    try:
        yield app
    finally:
        wait(app)


@pytest.fixture(name="client")
def client_fixture(app: Starlette) -> TestClient:
    return TestClient(app, base_url=BASE)


def wait(app: Starlette) -> None:
    launcher = app.state.launcher
    launcher.wait(timeout=60)
    assert not launcher.busy()


def _check(response: Any, status: int) -> Any:
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == status, body
    return body


def plan(script: Script, spec: str, rel: str | None = None, text: str = "") -> None:
    def effect(wt: Path) -> None:
        write(wt, spec, "# spec\n")
        if rel is not None:
            write(wt, rel, text)

    script.on("planner", effect)
    script.add("planner", ok(artifacts=[spec], commit_message=f"Plan {spec}"))


def first_run(repo: Path, script: Script) -> TaskRunResult:
    plan(script, SPEC)
    result = run_task(repo, T01)
    assert result.ok, (result.run.error, result.pr_error)
    return result


def run_both(repo: Path, script: Script) -> None:
    """T01 sets VALUE = 1, T02 sets VALUE = 2; both get a PR, T01 is merged."""
    plan(script, SPEC, MODEL, "VALUE = 1\n")
    first = run_task(repo, T01)
    assert first.ok, (first.run.error, first.pr_error)
    plan(script, SPEC2, MODEL, "VALUE = 2\n")
    other = run_task(repo, T02, force=True)
    assert other.ok, (other.run.error, other.pr_error)
    approve_task(repo, T01)


def runs_of(repo: Path, task_id: str) -> list[Any]:
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        return store.for_task(task_id)
    finally:
        store.close()


def spy(monkeypatch: pytest.MonkeyPatch, name: str, **extra: Any) -> list[tuple[Any, ...]]:
    """Replace ``aifactory.review.<name>`` by a wrapper that records calls and delegates."""
    original: Callable[..., Any] = getattr(aifactory.review, name)
    calls: list[tuple[Any, ...]] = []

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        return original(*args, **kwargs, **extra)

    monkeypatch.setattr(aifactory.review, name, wrapper)
    return calls


def test_list_shows_open_pr_with_mergeability_cost(
    client: TestClient, repo: Path, script: Script
) -> None:
    first_run(repo, script)
    data = _check(client.get("/api/review"), 200)["data"]
    [item] = data["prs"]
    assert item["task_id"] == T01
    assert item["task_title"] == "Schema"
    assert item["project_id"] == "M01"
    assert "module_id" not in item
    assert data["levels"] == ["project", "step", "task"]
    assert "owner" not in item
    assert item["provider_state"] == "open"
    assert item["mergeability"] == "mergeable"
    assert item["awaiting_review"] is True
    assert item["running_run"] is None
    assert isinstance(item["cost"], float)
    assert isinstance(item["tokens"], int)
    assert item["runs"] == 1
    assert item["pr"]["url"] == f"local:{BRANCH1}"
    assert "body" not in item["pr"]
    assert data["provider"] == "local"
    assert data["approve_review_sent"] is False
    assert "OB3" in data["approve_note"]


def test_list_without_trace_db_is_empty(client: TestClient) -> None:
    data = _check(client.get("/api/review"), 200)["data"]
    assert data["prs"] == []
    for key in ("owners", "me", "filters"):
        assert key not in data


def test_owner_query_is_ignored(client: TestClient, repo: Path, script: Script) -> None:
    first_run(repo, script)
    git(repo, "config", "user.name", "alice")
    data = _check(client.get("/api/review?owner=bob"), 200)["data"]
    assert len(data["prs"]) == 1
    for key in ("owners", "me", "filters"):
        assert key not in data
    assert "owner" not in data["prs"][0]


def test_detail_has_body_diff_checks_runs(client: TestClient, repo: Path, script: Script) -> None:
    result = first_run(repo, script)
    data = _check(client.get(f"/api/review/{T01}"), 200)["data"]
    assert "## Zadání" in data["pr"]["body"]
    assert "owner" not in data
    assert data["project_id"] == "M01"
    assert data["levels"] == ["project", "step", "task"]
    files = {f["path"]: f for f in data["diff"]["files"]}
    spec = files[SPEC]
    assert spec["status"] == "added"
    assert spec["additions"] >= 1
    assert "+# spec" in spec["patch"]
    assert spec["binary"] is False
    assert data["diff"]["stat"]["files"] == len(files)
    assert data["diff"]["merge_base"]
    assert data["runs"][0]["run_id"] == result.run.run_id
    assert isinstance(data["checks"], list)
    assert all("kind" in c for c in data["checks"])
    assert data["review"] is None
    assert data["actions"] == {"approve": True, "return": True, "resolve": True}
    assert data["approve_review_sent"] is False


def test_review_verdict_reads_reviewer_envelope(tmp_path: Path) -> None:
    db = tmp_path / "trace.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE envelopes (adw_id TEXT, phase_id TEXT, agent TEXT, output_type TEXT, "
        "payload_json TEXT, valid INTEGER, attempt INTEGER, created_at TEXT)"
    )
    rows = [
        ("r1", "builder", '{"summary": "built"}', "2026-01-01T00:00:01"),
        (
            "r1",
            "reviewer",
            '{"approved": true, "blocking": [], "summary": "ok", '
            '"findings": [{"requirement": "a", "met": true, "evidence": "e"}]}',
            "2026-01-01T00:00:02",
        ),
        ("r2", "reviewer", '{"approved": false, "summary": "other"}', "2026-01-01T00:00:03"),
    ]
    for adw_id, agent, payload, created in rows:
        conn.execute(
            "INSERT INTO envelopes VALUES (?, 'p', ?, 'X', ?, 1, 1, ?)",
            (adw_id, agent, payload, created),
        )
    conn.commit()
    conn.close()
    verdict = _review_verdict(db, ["r1"])
    assert verdict is not None
    assert verdict["approved"] is True
    assert verdict["summary"] == "ok"
    assert verdict["blocking"] == []
    assert verdict["findings"][0]["requirement"] == "a"
    assert verdict["agent"] == "reviewer"
    assert verdict["run_id"] == "r1"
    assert _review_verdict(db, ["nope"]) is None
    assert _review_verdict(tmp_path / "missing.db", ["r1"]) is None


def test_detail_unknown_task_is_404(client: TestClient) -> None:
    body = _check(client.get("/api/review/M09-S09-T09"), 404)
    assert body["error"]["code"] == "no_pr"


def test_approve_calls_core_and_merges(
    client: TestClient, repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_run(repo, script)
    calls = spy(monkeypatch, "approve_task")
    data = _check(client.post(f"/api/review/{T01}/approve"), 200)["data"]
    assert calls == [(repo, T01)]
    assert data["pr"]["state"] == "merged"
    assert data["reviewed"] is False
    assert data["approve_review_sent"] is False
    assert "OB3" in data["approve_note"]
    assert "status: done" in git(repo, "show", f"main:{TASK1}")
    body = _check(client.post(f"/api/review/{T01}/approve"), 409)
    assert body["error"]["code"] == "pr_not_open"
    assert _check(client.get("/api/review"), 200)["data"]["prs"] == []


def test_return_starts_run_on_same_branch(
    app: Starlette,
    client: TestClient,
    repo: Path,
    script: Script,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_run(repo, script)
    for payload in ({}, {"note": "  "}):
        body = _check(client.post(f"/api/review/{T01}/return", json=payload), 400)
        assert body["error"]["code"] == "missing_note"
    body = _check(client.post(f"/api/review/{T01}/return", json={"note": 5}), 400)
    assert body["error"]["code"] == "usage_error"
    body = _check(client.post(f"/api/review/{T01}/return", json={"x": 1}), 400)
    assert body["error"]["code"] == "usage_error"

    calls = spy(monkeypatch, "return_task")
    plan(script, SPEC)
    data = _check(client.post(f"/api/review/{T01}/return", json={"note": "přidej test"}), 202)[
        "data"
    ]
    assert data["action"] == "return"
    assert data["pending"] is False
    assert data["run"]["branch"] == BRANCH1
    wait(app)
    assert calls == [(repo, T01, "přidej test")]
    newest = runs_of(repo, T01)[0]
    assert newest.run_id == data["run"]["run_id"]
    assert newest.note == "přidej test"
    assert newest.state == "succeeded", newest.error


def test_return_without_pr_is_404(client: TestClient) -> None:
    body = _check(client.post(f"/api/review/{T01}/return", json={"note": "x"}), 404)
    assert body["error"]["code"] == "no_pr"


def test_conflict_offers_resolve(
    app: Starlette,
    client: TestClient,
    repo: Path,
    script: Script,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_both(repo, script)
    [item] = _check(client.get("/api/review"), 200)["data"]["prs"]
    assert item["task_id"] == T02
    assert item["mergeability"] == "conflict"
    detail = _check(client.get(f"/api/review/{T02}"), 200)["data"]
    assert detail["actions"]["approve"] is False
    assert detail["actions"]["resolve"] is True
    body = _check(client.post(f"/api/review/{T02}/approve"), 409)
    assert body["error"]["code"] == "conflict"

    def settle(wt: Path) -> None:
        write(wt, MODEL, "VALUE = 3\n")

    script.on("builder", settle)
    script.add("builder", ok(changed_files=[MODEL], commit_message="Resolve model conflict"))
    script.add("tester", plan_envelope())
    script.add("test-reviewer", ok(approved=True, summary="plan fits", findings=[], blocking=[]))
    calls = spy(monkeypatch, "resolve_task", code=ResolveCode([True]))
    body = _check(client.post(f"/api/review/{T02}/resolve", json={"x": 1}), 400)
    assert body["error"]["code"] == "usage_error"
    data = _check(client.post(f"/api/review/{T02}/resolve", json={}), 202)["data"]
    assert data["action"] == "resolve"
    assert data["run"]["workflow"] == "resolve"
    assert data["run"]["branch"] == BRANCH2
    wait(app)
    assert calls == [(repo, T02)]
    assert runs_of(repo, T02)[0].state == "succeeded"
    detail = _check(client.get(f"/api/review/{T02}"), 200)["data"]
    assert detail["mergeability"] == "mergeable"
    assert detail["actions"]["approve"] is True


def test_resolve_is_the_core_function() -> None:
    assert aifactory.review.resolve_task is resolve_task


def test_list_done_only_on_request(client: TestClient, repo: Path, script: Script) -> None:
    run_both(repo, script)
    data = _check(client.get("/api/review"), 200)["data"]
    assert "done" not in data
    assert [p["task_id"] for p in data["prs"]] == [T02]
    assert "done" not in _check(client.get("/api/review?done=0"), 200)["data"]
    data = _check(client.get("/api/review?done=1"), 200)["data"]
    assert [p["task_id"] for p in data["prs"]] == [T02]
    [item] = data["done"]
    assert item["task_id"] == T01
    assert item["task_title"] == "Schema"
    assert item["project_id"] == "M01"
    assert item["provider_state"] == "merged"
    assert item["pr"]["merged_at"]
    assert item["done_at"] == item["pr"]["merged_at"]
    assert item["pr"]["url"] == f"local:{BRANCH1}"
    assert "body" not in item["pr"]
    assert isinstance(item["cost"], float)
    assert isinstance(item["tokens"], int)


def test_list_done_without_trace_db_is_empty(client: TestClient) -> None:
    data = _check(client.get("/api/review?done=true"), 200)["data"]
    assert data["prs"] == []
    assert data["done"] == []


def test_done_lists_closed_newest_first(client: TestClient, repo: Path, script: Script) -> None:
    run_both(repo, script)
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        row = store.open_pr(T02)
        assert row is not None
        store.update_pr(row.branch, state="closed", updated_at="2999-01-01T00:00:00Z")
    finally:
        store.close()
    data = _check(client.get("/api/review?done=1"), 200)["data"]
    assert data["prs"] == []
    assert [p["task_id"] for p in data["done"]] == [T02, T01]
    assert [p["provider_state"] for p in data["done"]] == ["closed", "merged"]
    assert data["done"][0]["done_at"] == "2999-01-01T00:00:00Z"


def test_done_detail_is_read_only(client: TestClient, repo: Path, script: Script) -> None:
    run_both(repo, script)
    detail = _check(client.get(f"/api/review/{T01}"), 200)["data"]
    assert detail["provider_state"] == "merged"
    assert detail["actions"] == {"approve": False, "return": False, "resolve": False}
