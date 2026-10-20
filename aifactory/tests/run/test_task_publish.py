"""``factory task publish``: push and PR again after ``pr_failed``; adopt a known hosting PR.

Provider ``github`` against a fake ``gh`` and a fake ``git`` whose pushes fail as scripted
(the remote is a bare repository on disk); provider ``local`` for the refusals. No test
calls a model or the network.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from run_repo import SPEC, T01, Script, commit_all, fake_env, git, make_run_repo, ok, write

from aifactory.providers import git as pgit
from aifactory.review import ReviewError, publish_task
from aifactory.run import TaskRunStore, run_task
from cli_json import run_json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "providers"))

from gh_fake import GhLog, install_fake_gh, prepare_shared_gh, reply  # noqa: E402
from git_fake import HTTP2, REJECTED, FakeGit, install_fake_git  # noqa: E402

Capsys = pytest.CaptureFixture[str]
BRANCH = f"factory/{T01}-1"
PR_URL = "https://github.com/o/r/pull/7"


@pytest.fixture(scope="module", autouse=True)
def _shared_gh(tmp_path_factory: pytest.TempPathFactory) -> None:
    prepare_shared_gh(tmp_path_factory.mktemp("ghwarm"))


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


@pytest.fixture(name="sleeps")
def sleeps_fixture(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(pgit, "_sleep", slept.append)
    return slept


def succeed(script: Script) -> None:
    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add schema spec"))


def github_repo(repo: Path, tmp_path: Path) -> Path:
    """`repo` on provider github with a bare `origin` on disk."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, capture_output=True
    )
    git(repo, "remote", "add", "origin", str(origin))
    write(repo, ".factory/config.yaml", "base: main\ndocs_root: .\ngit_provider: github\n")
    commit_all(repo, "github")
    git(repo, "push", "-q", "-u", "origin", "main")
    return origin


def publish_cli(capsys: Capsys, repo: Path) -> tuple[int, Any]:
    capsys.readouterr()  # what the run printed
    return run_json(capsys, ["task", "publish", T01, "--json", "--repo", str(repo)])


def store_of(repo: Path) -> TaskRunStore:
    return TaskRunStore(repo / ".factory" / "trace.db")


def remote_has(origin: Path, branch: str) -> bool:
    out = subprocess.run(
        ["git", "for-each-ref", f"refs/heads/{branch}"],
        cwd=origin,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return bool(out.strip())


def failed_publish_run(
    repo: Path,
    script: Script,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    prepared: bool = False,
) -> tuple[Path, GhLog, FakeGit]:
    """A succeeded run of T01 whose push failed on the network every time (``pr_failed``)."""
    origin = github_repo(repo, tmp_path)
    log = install_fake_gh(
        tmp_path, monkeypatch, {"pr create": reply(PR_URL + "\n"), "pr list": reply([])}
    )
    fake = install_fake_git(tmp_path, monkeypatch)
    for n in range(1, pgit.PUSH_ATTEMPTS + 1):
        fake.fail_push(n, HTTP2)
    if not prepared:
        succeed(script)
    result = run_task(repo, T01)
    assert result.run.state == "succeeded"
    assert result.pr is None
    assert result.pr_error is not None and result.pr_error.startswith("push_failed:")
    assert "HTTP2 framing layer" in result.pr_error
    assert result.run.pr_error == result.pr_error
    assert not remote_has(origin, BRANCH)
    assert [a for a in log.argvs() if a[:2] == ["pr", "create"]] == []
    return origin, log, fake


@pytest.mark.parametrize(
    "push_error", [HTTP2, " ! [remote rejected] x -> x (Internal Server Error)"]
)
def test_push_retries_transient_error_in_task_run(
    repo: Path,
    script: Script,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sleeps: list[float],
    push_error: str,
) -> None:
    origin = github_repo(repo, tmp_path)
    log = install_fake_gh(tmp_path, monkeypatch, {"pr create": reply(PR_URL + "\n")})
    fake = install_fake_git(tmp_path, monkeypatch)
    fake.fail_push(1, push_error)
    succeed(script)

    result = run_task(repo, T01)

    assert result.ok, (result.run.error, result.pr_error)
    assert result.pr is not None and result.pr.url == PR_URL
    assert fake.pushes() == 2
    assert sleeps == [pgit.PUSH_DELAY]
    assert remote_has(origin, BRANCH)
    assert result.run.pr_error is None
    assert len([a for a in log.argvs() if a[:2] == ["pr", "create"]]) == 1


def test_rejected_push_in_task_run_is_not_retried(
    repo: Path,
    script: Script,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sleeps: list[float],
) -> None:
    github_repo(repo, tmp_path)
    install_fake_gh(tmp_path, monkeypatch, {"pr create": reply(PR_URL + "\n")})
    fake = install_fake_git(tmp_path, monkeypatch)
    fake.fail_push(1, REJECTED)
    succeed(script)

    result = run_task(repo, T01)

    assert result.run.state == "succeeded"
    assert result.pr_error is not None and "non-fast-forward" in result.pr_error
    assert fake.pushes() == 1
    assert sleeps == []


def test_publish_after_pr_failed(
    repo: Path,
    script: Script,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Capsys,
    sleeps: list[float],
) -> None:
    origin, log, _ = failed_publish_run(repo, script, tmp_path, monkeypatch)
    store = store_of(repo)
    try:
        run_id = store.for_task(T01)[0].run_id
        kept_body = store.pr_body_of(run_id)
    finally:
        store.close()
    assert kept_body is not None and "### Agenti" in kept_body
    assert "- žádný agent neběžel" not in kept_body  # the body of the run, not a rebuilt one
    log.clear()

    rc, env = publish_cli(capsys, repo)

    assert rc == 0, env
    data = env["data"]
    assert data["pr_error"] is None
    assert data["auto_merge"] is None
    assert data["pr"]["url"] == PR_URL and data["pr"]["pr_id"] == "7"
    assert data["run"]["run_id"] == run_id and data["run"]["pr_error"] is None
    assert remote_has(origin, BRANCH)
    assert [a[:2] for a in log.argvs()] == [["pr", "list"], ["pr", "create"]]
    creates = [c for c in log.calls() if c["argv"][:2] == ["pr", "create"]]
    assert len(creates) == 1
    assert creates[0]["stdin"] == kept_body
    store = store_of(repo)
    try:
        saved = store.pr_for_branch(BRANCH)
        assert saved is not None and saved.task_id == T01 and saved.state == "open"
        assert saved.body == kept_body
        assert store.get(run_id).pr_error is None  # type: ignore[union-attr]
        assert store.pr_body_of(run_id) is None
    finally:
        store.close()

    # a second publish finds the PR and changes nothing
    log.clear()
    rc, env = publish_cli(capsys, repo)
    assert rc == 2
    assert env["error"]["code"] == "pr_exists"
    assert log.argvs() == []


def test_publish_failing_again_keeps_error(
    repo: Path,
    script: Script,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Capsys,
    sleeps: list[float],
) -> None:
    _, log, fake = failed_publish_run(repo, script, tmp_path, monkeypatch)
    fake.fail_push(1, REJECTED)

    rc, env = publish_cli(capsys, repo)

    assert rc == 1
    assert env["error"]["code"] == "pr_failed"
    assert "non-fast-forward" in env["data"]["pr_error"]
    assert "non-fast-forward" in env["data"]["run"]["pr_error"]
    assert env["data"]["pr"] is None
    assert [a for a in log.argvs() if a[:2] == ["pr", "create"]] == []


def test_publish_adopts_existing_hosting_pr(
    repo: Path,
    script: Script,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Capsys,
    sleeps: list[float],
) -> None:
    failed_publish_run(repo, script, tmp_path, monkeypatch)
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {
            "pr list": reply(
                [
                    {
                        "number": 9,
                        "url": "https://github.com/o/r/pull/9",
                        "title": f"{T01}: Schema",
                        "baseRefName": "main",
                        "headRefName": BRANCH,
                    }
                ]
            ),
            "pr create": reply(stderr="a pull request already exists", exit=1),
        },
    )

    rc, env = publish_cli(capsys, repo)

    assert rc == 0, env
    assert env["data"]["pr"]["pr_id"] == "9"
    argvs = log.argvs()
    assert [a[:2] for a in argvs] == [["pr", "list"], ["pr", "edit"]]
    assert argvs[0][argvs[0].index("--head") + 1] == BRANCH
    assert argvs[1][2] == "9"
    store = store_of(repo)
    try:
        saved = store.pr_for_branch(BRANCH)
        assert saved is not None
        assert saved.pr_id == "9" and saved.url == "https://github.com/o/r/pull/9"
        assert saved.state == "open" and saved.provider == "github"
        assert saved.body == log.calls()[1]["stdin"]
    finally:
        store.close()


def test_task_run_adopts_pr_when_create_fails(
    repo: Path,
    script: Script,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sleeps: list[float],
) -> None:
    github_repo(repo, tmp_path)
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {
            "pr create": reply(stderr="a pull request for branch already exists", exit=1),
            "pr list": reply([{"number": 4, "url": "https://github.com/o/r/pull/4", "title": "t"}]),
        },
    )
    succeed(script)

    result = run_task(repo, T01)

    assert result.ok, (result.run.error, result.pr_error)
    assert result.pr is not None and result.pr.pr_id == "4"
    assert [a[:2] for a in log.argvs()] == [["pr", "create"], ["pr", "list"], ["pr", "edit"]]


def test_publish_without_succeeded_run(repo: Path, capsys: Capsys) -> None:
    rc, env = publish_cli(capsys, repo)
    assert rc == 2
    assert env["error"]["code"] == "no_succeeded_run"


def test_publish_refuses_known_pr_local(repo: Path, script: Script, capsys: Capsys) -> None:
    succeed(script)
    result = run_task(repo, T01)
    assert result.ok and result.pr is not None

    rc, env = publish_cli(capsys, repo)

    assert rc == 2
    assert env["error"]["code"] == "pr_exists"


def test_publish_run_id_must_be_last_succeeded(repo: Path, script: Script) -> None:
    succeed(script)
    run_task(repo, T01)
    with pytest.raises(ReviewError) as info:
        publish_task(repo, T01, run_id="nope")
    assert info.value.code == "invalid_value"


def test_skill_describes_publish(capsys: Capsys) -> None:
    from aifactory.cli import main

    assert main(["--skill"]) == 0
    text: Any = capsys.readouterr().out
    assert "factory task publish" in text
    for code in ("no_succeeded_run", "pr_exists", "pr_failed"):
        assert code in text


def test_dashboard_shows_pr_error_and_publishes(
    repo: Path,
    script: Script,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sleeps: list[float],
) -> None:
    from starlette.testclient import TestClient

    from aifactory.skill import envelope_problems
    from aifactory.web import create_app

    _, log, _ = failed_publish_run(repo, script, tmp_path, monkeypatch)
    client = TestClient(
        create_app(repo, static_dir=tmp_path / "nostatic"), base_url="http://127.0.0.1:4700"
    )
    listed = client.get("/api/runs").json()
    run = listed["data"]["runs"][0]
    assert run["pr"] is None
    assert run["pr_error"].startswith("push_failed:")

    response = client.post(f"/api/runs/{run['run_id']}/publish")
    body = response.json()
    assert envelope_problems(body) == []
    assert response.status_code == 200, body
    assert body["data"]["pr_error"] is None
    assert body["data"]["pr"]["url"] == PR_URL
    assert body["data"]["run"]["pr"]["url"] == PR_URL
    assert body["data"]["run"]["pr_error"] is None

    again = client.post(f"/api/runs/{run['run_id']}/publish")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "pr_exists"
    assert len([a for a in log.argvs() if a[:2] == ["pr", "create"]]) == 1


@pytest.mark.parametrize("parallel", [1, 2])
def test_publish_finishes_merge_and_continues(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch, parallel: int
) -> None:
    from test_auto_merge import T02, build, review, setup, status_on_main

    from aifactory.providers import ProviderError
    from aifactory.providers.local import LocalProvider

    setup(repo, step="auto_merge: true\nauto_continue: true\n")
    build(script, "one")
    review(script)
    with monkeypatch.context() as patch:

        def fail(*args: Any, **kwargs: Any) -> None:
            raise ProviderError("push_failed", "temporary hosting error")

        patch.setattr(LocalProvider, "push", fail)
        first = run_task(repo, T01)
    assert first.pr_error is not None
    build(script, "two")
    review(script)
    # Parallel children normally run as processes; keep this test's fake harness local.
    from aifactory.run import queue

    if parallel == 1:
        result = publish_task(repo, T01)
        assert result.chain is not None
        assert [r.run.task_id for r in result.chain.runs] == [T01, T02]
        assert all(r.auto_merge and r.auto_merge.merged for r in result.chain.runs)
        assert status_on_main(repo, T02) == "done"
    else:
        # The first publication/merge runs in-process even for a parallel chain.
        # Stop automatic selection so no fake harness must cross process boundaries.
        monkeypatch.setattr(queue, "_max_parallel", lambda repo: 2)
        monkeypatch.setattr(queue, "auto_continue_enabled", lambda task: False)
        result = publish_task(repo, T01)
        assert result.chain is not None and result.chain.max_parallel == 2
    assert result.chain.runs[0].run.run_id == first.run.run_id
    assert result.chain.runs[0].auto_merge is not None
    assert result.chain.runs[0].auto_merge.merged
    assert status_on_main(repo, T01) == "done"


@pytest.mark.parametrize("green", [True, False])
def test_publish_github_applies_ci_gate(
    repo: Path,
    script: Script,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sleeps: list[float],
    capsys: Capsys,
    green: bool,
) -> None:
    from test_auto_merge import MERGE_SHA, _view, build, review, setup

    from aifactory.review import ci

    setup(repo)
    build(script, "one")
    review(script)
    _, log, _ = failed_publish_run(repo, script, tmp_path, monkeypatch, prepared=True)
    monkeypatch.setattr(ci, "AUTO_MERGE_CHECKS_TIMEOUT", 0.0)
    monkeypatch.setattr(ci, "AUTO_MERGE_CHECKS_APPEAR", 0.0)
    monkeypatch.setattr(ci, "CI_FIX_ROUNDS", 0)
    views = [_view(), _view(), _view(), _view(), _view("MERGED", MERGE_SHA)]
    log.respond("pr view", views if green else _view())
    log.respond("pr checks", reply([{"name": "ci", "bucket": "pass" if green else "fail"}]))

    rc, env = publish_cli(capsys, repo)

    assert rc == 0, env
    outcome = env["data"]["auto_merge"]
    assert outcome["merged"] is green, outcome
    assert outcome["code"] == (None if green else "checks_failing")
    assert len(env["data"]["chain"]["runs"]) == 1
    store = store_of(repo)
    try:
        pr = store.latest_pr(T01)
        assert pr is not None
        assert pr.state == ("merged" if green else "open")
        assert (
            pr.auto_merge_error is None
            if green
            else (pr.auto_merge_error or "").startswith("checks_failing:")
        )
    finally:
        store.close()


@pytest.mark.parametrize("approve_resolution", [True, False])
def test_publish_resolves_conflicts_like_run(
    repo: Path,
    script: Script,
    monkeypatch: pytest.MonkeyPatch,
    approve_resolution: bool,
) -> None:
    from test_auto_merge import ResolveCode, _resolver, build, review, setup

    from aifactory.providers import ProviderError
    from aifactory.providers.local import LocalProvider

    setup(repo)
    build(script, "one", text="NAME = 'branch'\n")
    review(script)
    with monkeypatch.context() as patch:

        def fail(*args: Any, **kwargs: Any) -> None:
            raise ProviderError("push_failed", "temporary hosting error")

        patch.setattr(LocalProvider, "push", fail)
        first = run_task(repo, T01)
    assert first.pr_error is not None
    write(repo, "src/app/one.py", "NAME = 'main'\n")
    commit_all(repo, "conflicting change on main")
    _resolver(script)
    review(script, approved=approve_resolution)

    result = publish_task(repo, T01, code=ResolveCode([True]))

    assert result.chain is not None
    merge = result.chain.runs[0].auto_merge
    assert merge is not None and merge.merged is approve_resolution
    assert len(result.chain.runs) == 2  # the original run and its resolution
    store = store_of(repo)
    try:
        pr = store.latest_pr(T01)
        assert pr is not None
        if approve_resolution:
            assert pr.state == "merged" and pr.auto_merge_error is None
        else:
            assert pr.state == "open" and pr.auto_merge_error
            assert pr.auto_merge_error.startswith(f"{merge.code}:")
    finally:
        store.close()


def test_dashboard_publish_merges_after_response(
    repo: Path,
    script: Script,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading

    from starlette.testclient import TestClient
    from test_auto_merge import build, review, setup

    from aifactory.providers import ProviderError
    from aifactory.providers.local import LocalProvider
    from aifactory.review import automerge
    from aifactory.web import create_app

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
    from thread_launcher import ThreadLauncher

    setup(repo)
    build(script, "one")
    review(script)
    with monkeypatch.context() as patch:

        def fail(*args: Any, **kwargs: Any) -> None:
            raise ProviderError("push_failed", "temporary hosting error")

        patch.setattr(LocalProvider, "push", fail)
        first = run_task(repo, T01)
    assert first.pr_error
    waiting, release = threading.Event(), threading.Event()
    from aifactory.review import approve_task as real_approve

    def approve(*args: Any, **kwargs: Any) -> Any:
        waiting.set()
        assert release.wait(10)
        return real_approve(*args, **kwargs)

    monkeypatch.setattr(automerge, "approve_task", approve)

    class Launcher(ThreadLauncher):
        def start_publish(self, repo: Path, task_id: str, *, timeout: float = 3.0) -> None:
            super().start_publish(repo, task_id, timeout=0.05)

    launcher = Launcher()
    client = TestClient(create_app(repo, launcher=launcher), base_url="http://127.0.0.1:4700")
    try:
        response = client.post(f"/api/runs/{first.run.run_id}/publish")
        assert response.status_code == 200, response.json()
        assert response.json()["data"]["started"] is True
        assert waiting.wait(5) and launcher.busy()
    finally:
        release.set()
        launcher.wait(10)
    assert not launcher.busy() and launcher.last_error is None
    store = store_of(repo)
    try:
        pr = store.latest_pr(T01)
        assert pr is not None and pr.state == "merged" and not pr.auto_merge_error
    finally:
        store.close()


def test_publish_uses_last_kept_review(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from test_auto_merge import T02, build, review, setup

    from aifactory.providers import ProviderError
    from aifactory.providers.local import LocalProvider
    from aifactory.run.task import session_dir_of
    from aifactory.workflow.journal import JOURNAL_FILE, read_journal

    setup(repo, step="auto_merge: true\nauto_continue: true\n")
    build(script, "one")
    review(script)
    with monkeypatch.context() as patch:

        def fail(*args: Any, **kwargs: Any) -> None:
            raise ProviderError("push_failed", "temporary hosting error")

        patch.setattr(LocalProvider, "push", fail)
        first = run_task(repo, T01)
    assert first.run.state == "succeeded" and first.pr_error is not None
    assert first.pr is None

    journal = read_journal(session_dir_of(repo, first.run.run_id) / JOURNAL_FILE)
    approved = next(e for e in reversed(journal.entries) if e.output == "ReviewOutput")
    assert approved.kept and approved.envelope is not None
    assert approved.envelope["approved"] is True
    rejection = "Missing regression coverage in the original run"
    journal.entries.extend(
        [
            replace(
                approved,
                phase="review_2",
                envelope={**approved.envelope, "approved": False, "blocking": [rejection]},
            ),
            replace(approved, phase="triage_review", kept=False),
        ]
    )
    journal.save()
    calls_before = len(script.calls)

    result = publish_task(repo, T01)

    assert result.chain is not None
    assert [r.run.run_id for r in result.chain.runs] == [first.run.run_id]
    assert result.chain.stop == "not_merged"
    merge = result.chain.runs[0].auto_merge
    assert merge is not None and not merge.merged
    assert merge.code == "review_rejected" and rejection in (merge.reason or "")
    assert len(script.calls) == calls_before
    store = store_of(repo)
    try:
        pr = store.latest_pr(T01)
        assert pr is not None and pr.state == "open"
        assert pr.auto_merge_error is not None
        assert pr.auto_merge_error.startswith("review_rejected:")
        assert rejection in pr.auto_merge_error
        assert store.for_task(T02) == []
    finally:
        store.close()


@pytest.mark.parametrize("dashboard", [False, True], ids=["direct", "dashboard"])
def test_publish_without_auto_merge_does_not_continue(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch, dashboard: bool
) -> None:
    from test_auto_merge import T02, build, review, setup

    from aifactory.providers import ProviderError
    from aifactory.providers.local import LocalProvider

    setup(
        repo,
        step="auto_merge: true\nauto_continue: true\n",
        t01_extra="auto_merge: false\n",
        t02_depends=False,
    )
    build(script, "one")
    review(script)
    with monkeypatch.context() as patch:

        def fail(*args: Any, **kwargs: Any) -> None:
            raise ProviderError("push_failed", "temporary hosting error")

        patch.setattr(LocalProvider, "push", fail)
        first = run_task(repo, T01)
    assert first.run.state == "succeeded" and first.pr_error is not None
    assert first.pr is None
    calls_before = len(script.calls)

    if dashboard:
        from starlette.testclient import TestClient

        from aifactory.web import create_app

        client = TestClient(create_app(repo), base_url="http://127.0.0.1:4700")
        response = client.post(f"/api/runs/{first.run.run_id}/publish")
        assert response.status_code == 200, response.json()
        data = response.json()["data"]
        assert data["pr"]["state"] == "open" and data["pr_error"] is None
        assert not data.get("started")
    else:
        result = publish_task(repo, T01)
        assert result.ok and result.chain is None
        assert result.pr is not None and result.pr.state == "open"

    assert len(script.calls) == calls_before
    store = store_of(repo)
    try:
        pr = store.latest_pr(T01)
        assert pr is not None and pr.state == "open" and pr.auto_merge_error is None
        assert store.for_task(T02) == []
        assert [r.run_id for r in store.all_runs()] == [first.run.run_id]
    finally:
        store.close()
