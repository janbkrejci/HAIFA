"""Outside-repo checks, explicit home, read-only behavior and explicit refreshes."""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from multi_repo import git, register, write
from starlette.testclient import TestClient
from test_web_library import client as client
from test_web_library import initialize, response, state

from aifactory.check import Probe, run_check
from aifactory.check.machine import SystemMachine
from aifactory.web import machine
from fake_exe import make_executable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "check"))
from factory_check_repo import GIT_IDENTITY, FakeMachine  # noqa: E402


def test_machine_cache_and_offline(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMachine()
    state(client).check_machine = fake
    clock = [100.0]
    monkeypatch.setattr(machine, "_clock", lambda: clock[0])
    first = response(client.get("/api/machine/check?fresh=1"))
    assert not first["in_repo"] and not first["cached"]
    assert all(first[k] is None for k in ("repo", "state", "base", "commit"))
    assert {f["scope"] for f in first["findings"]} <= {"machine", "library"}
    calls = len(fake.calls)
    assert calls > 0
    clock[0] = 159.9
    cached = response(client.get("/api/machine/check"))
    assert cached["cached"] and cached["checked_at"] == first["checked_at"]
    assert len(fake.calls) == calls
    # Caller-owned payloads cannot corrupt the cache.
    cached["findings"].clear()
    assert response(client.get("/api/machine/check"))["findings"]
    clock[0] = 10_000.0
    assert response(client.get("/api/machine/check"))["cached"]
    assert len(fake.calls) == calls
    assert not response(client.get("/api/machine/check?fresh=1"))["cached"]
    assert len(fake.calls) > calls
    calls = len(fake.calls)
    assert not response(client.get("/api/machine/check?offline=1&fresh=1"))["cached"]
    assert len(fake.calls) == calls
    assert response(client.get("/api/machine/check?offline=1"))["cached"]
    assert not state(client).home.exists()
    response(client.get("/api/machine/check?fresh=maybe"), 400, "usage_error")
    response(client.get("/api/machine/check?offline=maybe"), 400, "usage_error")


def test_machine_failure_matches_cli(client: TestClient) -> None:
    fake = FakeMachine(present=set())
    state(client).check_machine = fake
    res = client.get("/api/machine/check?fresh=1")
    data = response(res, 200, "checks_failed")
    report = run_check(
        machine.outside_repo(),
        require_repo=False,
        machine=machine.HomeMachine(fake, state(client).home),
    )
    errors = report.errors()
    message = f"{len(errors)} error(s): {', '.join(dict.fromkeys(f.code for f in errors))}"
    assert res.json()["error"]["message"] == message
    # The dashboard leaves out the info about harnesses no registered repository uses.
    assert data["findings"] == [
        f
        for f in report.to_json()["findings"]
        if not (f["code"] == "harness_missing" and f["severity"] == "info")
    ]
    assert data["missing_harnesses"] == ["claude", "codex", "pi"]
    assert response(client.get("/api/machine/check"), 200, "checks_failed")["cached"]


def test_machine_home_in_repo_and_override(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(repo))
    # Both cwd and the dashboard home can be under a repository.
    state(client).home = repo / "home"
    override = tmp_path / "overridden-library"
    fake = FakeMachine(environ={**GIT_IDENTITY, "HAIFA_LIBRARY": str(override)})
    state(client).check_machine = fake
    data = response(client.get("/api/machine/check?fresh=1"))
    assert not data["in_repo"]
    finding = next(f for f in data["findings"] if f["code"] == "library_missing")
    assert str(override) in finding["message"]
    assert not state(client).home.exists()
    adapter = machine.HomeMachine(fake, state(client).home)
    assert (
        adapter.env("HAIFA_HOME") == adapter.environment()["HAIFA_HOME"] == str(state(client).home)
    )


def test_machine_fake_executables(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = write(state(client).user_home, "bin/claude", '#!/bin/sh\necho "1.0"\nexit 0\n')
    make_executable(binary)
    monkeypatch.setenv("CLAUDE_CODE_PATH", str(binary))
    monkeypatch.setenv("CODEX_PATH", "missing-codex-for-test")
    monkeypatch.setenv("PI_PATH", "missing-pi-for-test")
    monkeypatch.setenv("PATH", str(binary.parent) + os.pathsep + os.environ["PATH"])
    state(client).check_machine = SystemMachine()
    data = response(client.get("/api/machine/check?offline=1&fresh=1"))
    assert not any(
        f["code"] == "harness_missing" and "claude" in f["message"] for f in data["findings"]
    )
    assert not state(client).home.exists()
    initialize(client)
    refreshed = response(client.get("/api/machine/check?offline=1"), 200, "checks_failed")
    assert refreshed["cached"] and refreshed["stale"]
    assert not any(f["code"] == "library_missing" for f in refreshed["findings"])


def test_harness_repo_counts_follow_registry_with_cached_probes(
    client: TestClient, tmp_path: Path
) -> None:
    from aifactory.library.install import init_repo

    initialize(client)
    state(client).check_machine = FakeMachine()
    first = response(client.get("/api/machine/check?offline=1&fresh=1"))
    assert first["harness_repos"] == {"claude": 0, "codex": 0, "pi": 0}
    for name in ("one", "two"):
        repo = tmp_path / name
        repo.mkdir()
        git(repo, "init", "-b", "main")
        write(repo, "README.md", "repo\n")
        git(repo, "add", "README.md")
        git(repo, "commit", "-m", "initial")
        init_repo(repo)
        if name == "one":
            git(repo, "add", ".factory", ".gitignore")
            git(repo, "commit", "-m", "install factory")
        register(client, repo)
    cached = response(client.get("/api/machine/check?offline=1"))
    assert cached["cached"]
    assert cached["harness_repos"] == {"claude": 2, "codex": 0, "pi": 0}


def test_missing_harness_info_only_for_harnesses_repos_use(
    client: TestClient, tmp_path: Path
) -> None:
    from aifactory.library.install import init_repo

    initialize(client)
    state(client).check_machine = FakeMachine(present={"git", "uv", "just", "node"})

    def missing(data: dict[str, object]) -> list[str]:
        findings = data["findings"]
        assert isinstance(findings, list)
        return [f["message"].split()[1] for f in findings if f["code"] == "harness_missing"]

    first = response(client.get("/api/machine/check?offline=1&fresh=1"))
    assert missing(first) == []
    assert first["missing_harnesses"] == ["claude", "codex", "pi"]
    assert first["counts"]["info"] == sum(f["severity"] == "info" for f in first["findings"])
    assert all(f["fix"] or f["action"] for f in first["findings"])
    repo = tmp_path / "one"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    write(repo, "README.md", "repo\n")
    git(repo, "add", "README.md")
    git(repo, "commit", "-m", "initial")
    init_repo(repo)
    register(client, repo)
    assert missing(response(client.get("/api/machine/check?offline=1"))) == ["claude"]


@pytest.mark.skipif(
    sys.platform == "win32", reason="Windows cannot delete a process's working directory"
)
def test_machine_check_survives_a_deleted_working_directory(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A dashboard started in an unpacked bundle keeps running after the folder is deleted.
    gone = tmp_path / "unpacked-bundle"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    with pytest.raises(FileNotFoundError):
        os.getcwd()
    assert machine.outside_repo().is_dir()
    state(client).check_machine = FakeMachine()
    assert response(client.get("/api/machine/check?fresh=1"))["in_repo"] is False


def test_internal_error_says_where_a_nameless_error_was_raised(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(machine, "run_check", fail)
    state(client).check_machine = FakeMachine()
    server = TestClient(client.app, base_url=str(client.base_url), raise_server_exceptions=False)
    body = server.get("/api/machine/check?fresh=1").json()
    assert body["error"]["code"] == "internal_error"
    message = body["error"]["message"]
    assert message.startswith("FileNotFoundError: [Errno 2] No such file or directory (in ")
    assert "machine.py:" in message


# -- one bounded check: progress, timeout, shared jobs, late results (T108) --


@dataclass
class BlockingMachine(FakeMachine):
    """A fake whose ``claude auth status`` hangs until ``release`` (an unresponsive probe)."""

    release: threading.Event = field(default_factory=threading.Event)
    entered: threading.Event = field(default_factory=threading.Event)
    blocks: int = 1
    hung: int = 0

    def run(
        self, argv: Sequence[str], timeout: float = 15, cwd: Path | None = None
    ) -> Probe | None:
        if tuple(argv) == ("claude", "auth", "status") and self.hung < self.blocks:
            self.hung += 1
            self.entered.set()
            assert self.release.wait(10), "the test never released the probe"
        return super().run(argv, timeout, cwd)


def _small_budget(monkeypatch: pytest.MonkeyPatch, budget: float = 0.5) -> None:
    monkeypatch.setattr(machine, "CHECK_BUDGET", budget)
    monkeypatch.setattr(machine, "RESULT_GRACE", 0.1)


def _idle(client: TestClient) -> None:
    """Wait until no machine check job runs (a released probe lets it finish)."""
    deadline = time.monotonic() + 10
    while any(not job.done.is_set() for job in list(state(client).library.jobs.values())):
        assert time.monotonic() < deadline, "the check job never ended"
        time.sleep(0.01)


def test_timeout_names_the_step_keeps_the_last_result_and_a_retry_checks_again(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    state(client).check_machine = FakeMachine(present={"git", "uv", "just", "claude"})
    first = response(client.get("/api/machine/check?fresh=1"))
    blocking = BlockingMachine(present={"git", "uv", "just", "claude"})
    state(client).check_machine = blocking
    _small_budget(monkeypatch)
    started = time.monotonic()
    res = client.get("/api/machine/check?fresh=1")
    assert time.monotonic() - started < 5, "the request must end at the budget"
    data = response(res, 200, "check_timeout")
    assert data["timed_out"] and data["stale"] and data["cached"] and not data["ok"]
    # The last known result with its time, never a success of the unfinished check.
    assert data["checked_at"] == first["checked_at"]
    assert data["findings"] == first["findings"]
    assert data["progress"]["step"] == "machine: logins"
    assert data["progress"]["detail"] == "claude auth status"
    message = res.json()["error"]["message"]
    assert "0.5 s" in message and "machine: logins (claude auth status)" in message
    # The server's progress answers while the probe still hangs.
    progress = response(client.get("/api/machine/progress"))
    assert progress["job"]["step"] == "machine: logins" and progress["job"]["running"]
    assert progress["checked_at"] == first["checked_at"]
    # A page read skips the expired job without starting another one.
    seq = state(client).library.seq
    previous = response(client.get("/api/machine/check"))
    assert previous["checked_at"] == first["checked_at"]
    assert state(client).library.seq == seq and blocking.hung == 1
    # A retry does not join the expired job: it checks again and succeeds.
    retried = response(client.get("/api/machine/check?fresh=1"))
    assert not retried.get("timed_out") and not retried["cached"]
    assert retried["checked_at"] != first["checked_at"]
    blocking.release.set()
    _idle(client)
    # The expired job ran out of budget: its late result never replaces the newer one.
    assert response(client.get("/api/machine/check"))["checked_at"] == retried["checked_at"]
    assert response(client.get("/api/machine/progress"))["job"] is None


def test_first_check_timeout_has_no_result_and_is_not_ok(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocking = BlockingMachine(present={"git", "uv", "just", "claude"})
    state(client).check_machine = blocking
    _small_budget(monkeypatch)
    data = response(client.get("/api/machine/check?fresh=1"), 200, "check_timeout")
    assert data["timed_out"] and not data["ok"] and not data["cached"]
    assert data["checked_at"] is None and data["findings"] == []
    blocking.release.set()
    _idle(client)
    # Nothing of the exhausted check was cached; a read must not retry it.
    assert not state(client).library.checks
    calls = list(blocking.calls)
    data = response(client.get("/api/machine/check"), 200, "checks_failed")
    assert not data["checked"] and not data["ok"]
    assert blocking.calls == calls


def test_concurrent_requests_share_one_check_and_its_timeout(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocking = BlockingMachine(present={"git", "uv", "just", "claude"})
    home, global_state = state(client).home, state(client).library
    monkeypatch.setattr(machine, "RESULT_GRACE", 0.1)
    results: list[tuple[dict[str, Any], bool, str]] = []

    def request() -> None:
        results.append(
            machine.check_view(
                home, global_state, offline=False, fresh=True, machine=blocking, budget=1.0
            )
        )

    threads = [threading.Thread(target=request) for _ in range(4)]
    for thread in threads:
        thread.start()
    assert blocking.entered.wait(5)
    for thread in threads:
        thread.join(10)
        assert not thread.is_alive(), "a waiting request must end at the shared deadline"
    # Repeated clicks and other dashboards joined one check: one probe, one job.
    assert blocking.hung == 1
    assert blocking.calls.count(("claude", "auth", "status")) == 0  # still hanging
    assert len(results) == 4
    assert all(data["timed_out"] and not ok for data, ok, _ in results)
    assert len({data["progress"]["seq"] for data, _, _ in results}) == 1
    blocking.release.set()
    _idle(client)


def test_joined_check_answers_every_waiting_request(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocking = BlockingMachine(present={"git", "uv", "just", "claude"})
    home, global_state = state(client).home, state(client).library
    results: list[dict[str, Any]] = []

    def request(fresh: bool) -> None:
        data, _, _ = machine.check_view(
            home, global_state, offline=False, fresh=fresh, machine=blocking
        )
        results.append(data)

    startup = threading.Thread(target=request, args=(True,))
    startup.start()
    assert blocking.entered.wait(5)
    job = global_state.jobs[False]
    joined = threading.Event()
    original_wait = job.done.wait

    def wait(timeout: float | None = None) -> bool:
        joined.set()
        return bool(original_wait(timeout))

    monkeypatch.setattr(job.done, "wait", wait)
    reader = threading.Thread(target=request, args=(False,))
    reader.start()
    assert joined.wait(5), "the page read must join the startup job"
    blocking.release.set()
    for thread in (startup, reader):
        thread.join(10)
        assert not thread.is_alive()
    assert blocking.calls.count(("claude", "auth", "status")) == 1
    assert len(results) == 2 and len({data["checked_at"] for data in results}) == 1
    assert all(data["checked"] and not data.get("timed_out") for data in results)


def test_older_result_never_replaces_a_newer_one(client: TestClient) -> None:
    global_state = state(client).library
    home = state(client).home
    fake = FakeMachine()

    def job(seq: int) -> machine.CheckJob:
        return machine.CheckJob(
            offline=False,
            seq=seq,
            epoch=global_state.epoch,
            budget=30,
            started=machine._clock(),
            started_at="",
        )

    newer, older = job(2), job(1)
    machine._work(newer, home, global_state, fake)
    machine._work(older, home, global_state, fake)
    assert older.result is not None and not older.exhausted
    assert global_state.checks[False].seq == 2


def test_check_started_before_a_library_write_is_not_cached(client: TestClient) -> None:
    blocking = BlockingMachine(present={"git", "uv", "just", "claude"})
    home, global_state = state(client).home, state(client).library
    thread = threading.Thread(
        target=machine.check_view,
        args=(home, global_state),
        kwargs={"offline": False, "fresh": True, "machine": blocking},
    )
    thread.start()
    assert blocking.entered.wait(5)
    global_state.invalidate()  # a library sync while the check runs
    unread = FakeMachine()
    empty, ok, _ = machine.check_view(
        home, global_state, offline=False, fresh=False, machine=unread
    )
    assert not ok and not empty["checked"] and not unread.calls
    assert global_state.seq == 1
    # Only an explicit request after the write starts a replacement check.
    data, _, _ = machine.check_view(
        home, global_state, offline=False, fresh=True, machine=FakeMachine()
    )
    assert not data["cached"] and not data.get("timed_out")
    blocking.release.set()
    thread.join(10)
    assert global_state.checks[False].report["checked_at"] == data["checked_at"]


def test_unresponsive_registry_read_is_bounded(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.library.install import init_repo

    initialize(client)
    repo = tmp_path / "one"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    write(repo, "README.md", "repo\n")
    git(repo, "add", "README.md")
    git(repo, "commit", "-m", "initial")
    init_repo(repo)
    register(client, repo)
    state(client).check_machine = FakeMachine()
    first = response(client.get("/api/machine/check?offline=1&fresh=1"))
    assert first["harness_repos"]["claude"] == 1
    # The roster read gets no time left: the view still answers with known counts.
    monkeypatch.setattr(machine, "REGISTRY_BUDGET", 0.0)
    data = response(client.get("/api/machine/check?offline=1"))
    assert data["cached"] and data["harness_repos"]["claude"] == 1


def test_cached_check_follows_a_library_changed_outside_the_dashboard(
    client: TestClient, tmp_path: Path
) -> None:
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(bare))
    root = initialize(client, remote=str(bare))
    fake = FakeMachine()
    state(client).check_machine = fake

    def codes(data: dict[str, Any]) -> set[str]:
        return {f["code"] for f in data["findings"]}

    first = response(client.get("/api/machine/check?fresh=1"))
    assert "library_behind" not in codes(first)
    probes = len(fake.calls)
    # Another clone advances the remote; the library fetches it with git, not HAIFA.
    other = tmp_path / "other"
    git(tmp_path, "clone", str(bare), str(other))
    write(other, "note.txt", "remote change\n")
    git(other, "add", "note.txt")
    git(other, "commit", "-m", "remote change")
    git(other, "push", "origin", "main")
    git(root, "fetch", "origin")
    behind = response(client.get("/api/machine/check"))
    assert behind["cached"] and behind["checked_at"] == first["checked_at"]
    assert "library_behind" in codes(behind)
    # Synced by the CLI or git: the cached check no longer shows the old state.
    git(root, "merge", "--ff-only", "origin/main")
    synced = response(client.get("/api/machine/check"))
    assert synced["cached"] and "library_behind" not in codes(synced)
    # The expensive probes were not run again for these cached reads.
    assert len(fake.calls) == probes


def test_read_without_result_never_starts_probes(client: TestClient) -> None:
    fake = FakeMachine()
    state(client).check_machine = fake
    data = response(client.get("/api/machine/check"), 200, "checks_failed")
    assert data["checked"] is False and data["ok"] is False
    assert data["checked_at"] is None and not data.get("timed_out")
    assert not fake.calls and not state(client).library.jobs


def test_invalidated_result_is_read_as_stale_until_explicit_refresh(client: TestClient) -> None:
    fake = FakeMachine()
    state(client).check_machine = fake
    first = response(client.get("/api/machine/check?fresh=1"))
    calls = list(fake.calls)
    global_state = state(client).library
    global_state.invalidate()
    stale = response(client.get("/api/machine/check"), 200, "checks_failed")
    assert stale["checked"] and stale["stale"] and not stale["ok"]
    assert stale["checked_at"] == first["checked_at"]
    assert fake.calls == calls and not global_state.jobs
    refreshed = response(client.get("/api/machine/check?fresh=1"))
    assert refreshed["checked"] and not refreshed["stale"] and not refreshed["cached"]
    assert len(fake.calls) > len(calls)
    assert global_state.checks[False].report["checked_at"] == refreshed["checked_at"]


def test_late_result_after_invalidation_is_not_available_to_reads(client: TestClient) -> None:
    global_state = state(client).library
    job = machine.CheckJob(
        offline=False,
        seq=1,
        epoch=global_state.epoch,
        budget=30,
        started=machine._clock(),
        started_at="",
    )
    global_state.invalidate()
    machine._work(job, state(client).home, global_state, FakeMachine())
    assert job.result is not None and not job.exhausted
    assert not global_state.checks and not global_state.last_checks
    fake = FakeMachine()
    data, ok, _ = machine.check_view(
        state(client).home, global_state, offline=False, fresh=False, machine=fake
    )
    assert not ok and not data["checked"] and not fake.calls


@pytest.mark.parametrize("remaining", [0.0, 0.27])
def test_registry_exhaustion_starts_no_git_and_logs_no_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    remaining: float,
) -> None:
    from aifactory import procrun
    from aifactory.library import inherit
    from aifactory.web.registry import RepoEntry

    global_state = machine.GlobalState()
    entry = RepoEntry("a", "A", str(tmp_path), "")
    global_state.roster_counts[entry.path] = (("known",), frozenset({"claude"}))
    monkeypatch.setattr(machine, "_registered", lambda home: [entry])
    monkeypatch.setattr(procrun, "remaining", lambda: remaining)

    def forbidden(*args: object) -> None:
        pytest.fail("exhausted registry must not start git")

    monkeypatch.setattr(inherit, "library_head", forbidden)
    counts = machine._harness_repos(tmp_path, FakeMachine(), global_state)
    assert counts["claude"] == 1
    assert not any(record.exc_info for record in caplog.records)


def test_registry_git_timeout_degrades_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import subprocess

    from aifactory.library import inherit

    def timed_out(*args: object) -> None:
        raise subprocess.TimeoutExpired(["git", "rev-parse"], 0.27)

    monkeypatch.setattr(inherit, "library_head", timed_out)
    counts = machine._harness_repos(tmp_path, FakeMachine(), machine.GlobalState())
    assert not any(counts.values())
    assert not any(record.exc_info for record in caplog.records)


def test_library_git_timeout_preserves_cached_check(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import subprocess

    state(client).check_machine = FakeMachine()
    first = response(client.get("/api/machine/check?offline=1&fresh=1"))

    def timed_out(*args: object) -> None:
        raise subprocess.TimeoutExpired(["git", "rev-parse"], 0.27)

    monkeypatch.setattr(machine, "_current_library", timed_out)
    caplog.clear()
    cached = response(client.get("/api/machine/check?offline=1"))
    assert cached["cached"] and cached["library_stale"]
    assert cached["checked_at"] == first["checked_at"]
    assert cached["findings"] == first["findings"]
    assert not any(record.exc_info for record in caplog.records)
