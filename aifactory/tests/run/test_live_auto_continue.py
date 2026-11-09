"""Live repository policy: deterministic boundaries, no models or network."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from run_repo import Script, fake_env, make_run_repo
from test_auto_continue import T01, T02, T03, build, ids, runs_of, setup_chain
from test_parallel_chain import FakeRunner, no_files, setup_tasks, started

from aifactory.backlog import Task, load_backlog
from aifactory.cli import main
from aifactory.repo_settings import RepositorySettings
from aifactory.review.automerge import AutoMergeResult
from aifactory.run import TaskRunError, TaskRunRow, TaskRunStore, heal, queue, run_chain, run_task
from aifactory.run import retry as retry_mod
from aifactory.run import task as task_mod
from aifactory.run.members import ProcessRunner
from aifactory.run.policy import DISABLED, acceptance
from aifactory.web.launcher import RunLauncher
from aifactory.workflow import preflight


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


def test_off_during_accepted_run_finishes_it_without_next_task(
    tmp_path: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_run_repo(tmp_path / "repo")
    setup_chain(repo)
    build(script, "one")
    execute = task_mod._execute

    def execute_then_off(*args: Any, **kwargs: Any) -> task_mod.TaskRunResult:
        # Claim has happened; turning off must not stop this workflow's phases.
        RepositorySettings(repo).update({"auto_continue": False})
        return execute(*args, **kwargs)

    monkeypatch.setattr(task_mod, "_execute", execute_then_off)
    chain = run_chain(repo, T01, auto=True)
    assert chain.ok and ids(chain) == [T01]
    assert chain.stop == "disabled"
    assert "vypnuté" in str(chain.to_json()["stop_detail"])
    assert runs_of(repo, T02) == []


def test_off_between_selection_and_start(
    tmp_path: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_run_repo(tmp_path / "repo")
    setup_chain(repo)
    build(script, "one")
    select = queue.select_next

    def select_then_off(*args: Any, **kwargs: Any) -> queue.Selection:
        result = select(*args, **kwargs)
        assert result.next is not None
        RepositorySettings(repo).update({"auto_continue": False})
        return result

    monkeypatch.setattr(queue, "select_next", select_then_off)
    chain = run_chain(repo, T01)
    assert chain.stop == "disabled" and ids(chain) == [T01]
    assert chain.waiting[0].detail.startswith(DISABLED)
    assert runs_of(repo, T02) == []


def test_child_checks_policy_again_before_claim_and_manual_still_works(
    tmp_path: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_run_repo(tmp_path / "repo")
    setup_chain(repo)

    def off_before_claim(*args: Any, **kwargs: Any) -> None:
        preflight(*args, **kwargs)
        RepositorySettings(repo).update({"auto_continue": False})

    monkeypatch.setattr(task_mod, "preflight", off_before_claim)
    with pytest.raises(TaskRunError, match="vypnuté") as caught:
        run_task(repo, T01, started_by="auto-continue")
    assert caught.value.code == DISABLED and runs_of(repo, T01) == []
    build(script, "manual")
    assert run_task(repo, T01).ok


@pytest.mark.parametrize("quota_switch", [False, True])
def test_automatic_reclaim_checks_live_policy(
    tmp_path: Path, script: Script, monkeypatch: pytest.MonkeyPatch, quota_switch: bool
) -> None:
    from run_repo import ok

    repo = make_run_repo(tmp_path / "repo")
    setup_chain(repo)
    script.add("planner", ok(status="fail", summary="try again"))
    failed = run_task(repo, T01)
    assert not failed.ok

    def off_before_reclaim(*args: Any, **kwargs: Any) -> None:
        preflight(*args, **kwargs)
        RepositorySettings(repo).update({"auto_continue": False})

    monkeypatch.setattr(retry_mod, "preflight", off_before_reclaim)
    with pytest.raises(TaskRunError) as caught:
        retry_mod.retry_run(
            repo,
            T01,
            automatic=not quota_switch,
            switch={"auto": True} if quota_switch else None,
        )
    assert caught.value.code == DISABLED
    assert runs_of(repo, T01)[0].attempt == failed.run.attempt
    build(script, "manual_retry")
    assert retry_mod.retry_run(repo, T01).ok


def test_off_during_lock_retry_stops_retry_and_drains_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_run_repo(tmp_path / "repo")
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/"), (T03, "src/c/")])
    attempts: list[str] = []

    class BusyRunner(FakeRunner):
        def start(self, task_id: str, **kwargs: Any) -> TaskRunRow:
            attempts.append(task_id)
            if task_id == T02:
                RepositorySettings(repo).update({"auto_continue": False})
                raise TaskRunError("trace_db_locked", "another worker")
            return super().start(task_id, **kwargs)

    monkeypatch.setattr("aifactory.run.queue.time.sleep", lambda _: None)
    runner = BusyRunner(repo)
    chain = run_chain(repo, T01, max_parallel=3, runner=runner, pr_files=no_files)
    assert attempts == [T01, T02]
    assert started(runner) == [T01] and not runner.active()
    assert ids(chain) == [T01] and chain.runs[0].ok and chain.stop == "disabled"


def test_parallel_off_does_not_kill_accepted_members_or_refill(tmp_path: Path) -> None:
    repo = make_run_repo(tmp_path / "repo")
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/"), (T03, "src/c/")])

    class SwitchingRunner(FakeRunner):
        def wait_any(self) -> task_mod.TaskRunResult:
            RepositorySettings(repo).update({"auto_continue": False})
            return super().wait_any()

    runner = SwitchingRunner(repo)
    chain = run_chain(repo, T01, max_parallel=2, runner=runner, pr_files=no_files)
    assert started(runner) == [T01, T02]
    assert ids(chain) == [T01, T02] and all(r.ok for r in chain.runs)
    assert not runner.active() and chain.stop == "disabled"


def test_off_while_waiting_for_ci_blocks_following_task(
    tmp_path: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_auto_merge import build as reviewed_build
    from test_auto_merge import review, setup

    repo = make_run_repo(tmp_path / "repo")
    setup(repo, step="auto_merge: true\nauto_continue: true\n")
    reviewed_build(script, "one")
    review(script)

    def ci_then_off(*args: Any, **kwargs: Any) -> AutoMergeResult:
        RepositorySettings(repo).update({"auto_continue": False})
        return AutoMergeResult(False, "checks_pending", "CI is still running", None)

    monkeypatch.setattr("aifactory.review.automerge.try_auto_merge", ci_then_off)
    chain = run_chain(repo, T01)
    assert ids(chain) == [T01] and chain.stop == "disabled"
    assert chain.runs[0].ok and runs_of(repo, T02) == []


def test_off_blocks_automatic_heal(tmp_path: Path, script: Script) -> None:
    repo = make_run_repo(tmp_path / "repo")
    setup_chain(repo)
    build(script, "one")
    result = run_task(repo, T01)
    result.run = replace(result.run, state="failed", failure_kind="process_gone")
    task = load_backlog(repo).by_id[T01]
    assert isinstance(task, Task)
    RepositorySettings(repo).update({"auto_continue": False})

    def forbidden(*args: Any, **kwargs: Any) -> task_mod.TaskRunResult:
        raise AssertionError("automatic heal must not retry")

    assert heal.heal(repo, result, task, retry=forbidden) is None


@pytest.mark.parametrize("parallel", [1, 2])
def test_off_before_nothing_to_do_heal_drains_accepted_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, parallel: int
) -> None:
    repo = make_run_repo(tmp_path / "repo")
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/"), (T03, "src/c/")])

    class HealingRunner(FakeRunner):
        def wait_any(self) -> task_mod.TaskRunResult:
            result = super().wait_any()
            if result.run.task_id == T01:
                result.run = replace(
                    result.run,
                    failure_kind="nothing_to_do",
                    failure_detail='{"summary": "already complete"}',
                )
            return result

    runner = HealingRunner(repo, fail=(T01,))
    barriers: list[str] = []

    @contextmanager
    def off_before_acceptance(repo: Path, automatic: bool = True) -> Iterator[None]:
        # The chain and heal have read on; another accepted member is still active.
        assert RepositorySettings(repo).read().auto_continue
        assert runner.active() == ([T02] if parallel > 1 else [])
        barriers.append("off")
        RepositorySettings(repo).update({"auto_continue": False})
        with acceptance(repo, automatic):
            yield

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("disabled heal must not close the task")

    monkeypatch.setattr("aifactory.run.policy.acceptance", off_before_acceptance)
    monkeypatch.setattr(heal, "_close", forbidden)
    if parallel > 1:
        chain = run_chain(repo, T01, max_parallel=parallel, runner=runner, pr_files=no_files)
    else:
        # The first result already exists, as in a retry/publish continuation.
        runner.start(T01)
        first = runner.wait_any()
        chain = run_chain(repo, T01, max_parallel=1, first_run=lambda: first)
    assert barriers == ["off"]
    assert chain.stop == "disabled" and not runner.active()
    assert started(runner) == ([T01, T02] if parallel > 1 else [T01])
    assert ids(chain) == ([T01, T02] if parallel > 1 else [T01])
    assert chain.chain_id is not None
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        record = store.get_chain(chain.chain_id)
        assert record is not None and record.state == "finished" and record.stop == "disabled"
    finally:
        store.close()
    assert not chain.runs[0].closed_by_heal
    if parallel > 1:
        assert chain.runs[1].ok
    task = load_backlog(repo).by_id[T01]
    assert isinstance(task, Task) and task.status == "todo"


def test_publish_with_local_off_finishes_current_merge_without_continuation(
    tmp_path: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_auto_merge import build as reviewed_build
    from test_auto_merge import review, setup

    from aifactory.providers import ProviderError
    from aifactory.providers.local import LocalProvider
    from aifactory.review import publish_task

    repo = make_run_repo(tmp_path / "repo")
    setup(repo, step="auto_merge: true\nauto_continue: true\n")
    reviewed_build(script, "one")
    review(script)

    def offline(*args: Any, **kwargs: Any) -> None:
        raise ProviderError("push_failed", "temporary hosting failure")

    with monkeypatch.context() as patch:
        patch.setattr(LocalProvider, "push", offline)
        first = run_task(repo, T01)
    assert first.pr_error is not None
    RepositorySettings(repo).update({"auto_continue": False})
    result = publish_task(repo, T01)
    assert result.chain is not None and ids(result.chain) == [T01]
    assert result.chain.stop == "disabled"
    assert result.chain.runs[0].auto_merge is not None
    assert result.chain.runs[0].auto_merge.merged
    assert runs_of(repo, T02) == []


def test_web_dispatch_carries_automatic_origin_to_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_run_repo(tmp_path / "repo")
    launcher = RunLauncher()
    calls: list[list[str]] = []

    def launch(repo: Path, task_id: str, action: str, args: list[str], timeout: float) -> None:
        calls.append(args)

    monkeypatch.setattr(launcher, "_launch", launch)
    launcher.start(repo, T01, note=None, force=False, automatic=True)
    assert "--started-by=auto-continue" in calls[0]
    launcher.start(repo, T01, note=None, force=False)
    assert "--started-by=auto-continue" not in calls[1]


@pytest.mark.parametrize("auto", [False, True])
def test_cli_auto_cannot_enable_local_off(
    tmp_path: Path, script: Script, capsys: pytest.CaptureFixture[str], auto: bool
) -> None:
    repo = make_run_repo(tmp_path / "repo")
    setup_chain(repo, module_auto=True)
    RepositorySettings(repo).update({"auto_continue": False})
    build(script, "one")
    argv = ["task", "run", T01, "--repo", str(repo), "--json"]
    assert main([*argv, *(["--auto"] if auto else [])]) == 0
    output = capsys.readouterr()
    assert ("--auto is deprecated" in output.err) == auto
    assert runs_of(repo, T02) == []
    assert not RepositorySettings(repo).read().auto_continue


def test_off_blocks_member_spawn_before_popen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_run_repo(tmp_path / "repo")
    setup_chain(repo)
    RepositorySettings(repo).update({"auto_continue": False})

    popen = subprocess.Popen

    def forbidden(argv: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        if "task" in argv:
            raise AssertionError("must not spawn")
        return popen(argv, **kwargs)

    monkeypatch.setattr("aifactory.run.members.subprocess.Popen", forbidden)
    with pytest.raises(TaskRunError) as caught:
        ProcessRunner(repo).start(T01, started_by="auto-continue")
    assert caught.value.code == DISABLED


def test_two_workers_and_restart_read_persisted_policy_per_repository(tmp_path: Path) -> None:
    first = make_run_repo(tmp_path / "first")
    second = make_run_repo(tmp_path / "second")
    RepositorySettings(first).update({"auto_continue": True})
    RepositorySettings(second).update({"auto_continue": True})
    worker = (
        "import sys; from pathlib import Path; "
        "from aifactory.run.policy import acceptance; "
        "from aifactory.run.errors import TaskRunError\n"
        "try:\n"
        " with acceptance(Path(sys.argv[1])): print('accepted')\n"
        "except TaskRunError as exc: print(exc.code)\n"
    )

    def start(repo: Path) -> str:
        result = subprocess.run(
            [sys.executable, "-c", worker, str(repo)],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return result.stdout.strip()

    assert start(first) == "accepted"
    # Another worker and a fresh process after restart cannot reuse the earlier on.
    RepositorySettings(first).update({"auto_continue": False})
    assert start(first) == DISABLED
    assert start(first) == DISABLED
    assert start(second) == "accepted"
    with pytest.raises(TaskRunError):
        with acceptance(first):
            pytest.fail("off was bypassed")
    RepositorySettings(first).update({"auto_continue": True})
    assert runs_of(first, T01) == []  # enabling alone creates no run
    assert start(first) == "accepted"


def test_two_live_workers_observe_off_without_restart(tmp_path: Path) -> None:
    repo = make_run_repo(tmp_path / "repo")
    RepositorySettings(repo).update({"auto_continue": True})
    worker = (
        "import sys; from pathlib import Path; "
        "from aifactory.run.policy import acceptance; "
        "from aifactory.run.errors import TaskRunError\n"
        "for command in sys.stdin:\n"
        " try:\n"
        "  with acceptance(Path(sys.argv[1])): print('accepted', flush=True)\n"
        " except TaskRunError as exc: print(exc.code, flush=True)\n"
    )
    workers: list[subprocess.Popen[str]] = []

    def request(process: subprocess.Popen[str]) -> str:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write("start\n")
        process.stdin.flush()
        response = process.stdout.readline()
        assert isinstance(response, str)
        return response.strip()

    try:
        for _ in range(2):
            process = subprocess.Popen(
                [sys.executable, "-c", worker, str(repo)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            workers.append(process)
        assert [request(process) for process in workers] == ["accepted", "accepted"]
        RepositorySettings(repo).update({"auto_continue": False})
        assert [request(process) for process in workers] == [DISABLED, DISABLED]
        RepositorySettings(repo).update({"auto_continue": True})
        assert [request(process) for process in workers] == ["accepted", "accepted"]
    finally:
        for process in workers:
            process.communicate(timeout=30)
            assert process.returncode == 0
