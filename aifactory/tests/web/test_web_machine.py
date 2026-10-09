"""Outside-repo checks, explicit home, read-only behavior and deterministic cache TTL."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from multi_repo import git, write
from starlette.testclient import TestClient
from test_web_library import client as client
from test_web_library import initialize, response, state

from aifactory.check import run_check
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
    first = response(client.get("/api/machine/check"))
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
    assert not response(client.get("/api/machine/check?offline=1"))["cached"]
    assert len(fake.calls) == calls
    assert response(client.get("/api/machine/check?offline=1"))["cached"]
    assert not state(client).home.exists()
    response(client.get("/api/machine/check?fresh=maybe"), 400, "usage_error")
    response(client.get("/api/machine/check?offline=maybe"), 400, "usage_error")


def test_machine_failure_matches_cli(client: TestClient) -> None:
    fake = FakeMachine(present=set())
    state(client).check_machine = fake
    res = client.get("/api/machine/check")
    data = response(res, 200, "checks_failed")
    report = run_check(
        machine.outside_repo(),
        require_repo=False,
        machine=machine.HomeMachine(fake, state(client).home),
    )
    errors = report.errors()
    message = f"{len(errors)} error(s): {', '.join(dict.fromkeys(f.code for f in errors))}"
    assert res.json()["error"]["message"] == message
    assert data["findings"] == report.to_json()["findings"]
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
    data = response(client.get("/api/machine/check"))
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
    data = response(client.get("/api/machine/check?offline=1"))
    assert not any(
        f["code"] == "harness_missing" and "claude" in f["message"] for f in data["findings"]
    )
    assert not state(client).home.exists()
    initialize(client)
    refreshed = response(client.get("/api/machine/check?offline=1"))
    assert not refreshed["cached"]
    assert not any(f["code"] == "library_missing" for f in refreshed["findings"])


def test_harness_repo_counts_follow_registry_with_cached_probes(
    client: TestClient, tmp_path: Path
) -> None:
    from aifactory.library.install import init_repo
    from aifactory.web.library import environment

    initialize(client)
    state(client).check_machine = FakeMachine()
    first = response(client.get("/api/machine/check?offline=1"))
    assert first["harness_repos"] == {"claude": 0, "codex": 0, "pi": 0}
    for name in ("one", "two"):
        repo = tmp_path / name
        repo.mkdir()
        git(repo, "init", "-b", "main")
        write(repo, "README.md", "repo\n")
        git(repo, "add", "README.md")
        git(repo, "commit", "-m", "initial")
        init_repo(repo, agents=["builder"], environ=environment(state(client).home))
        if name == "one":
            git(repo, "add", ".factory", ".gitignore")
            git(repo, "commit", "-m", "install factory")
        response(client.post("/api/repos", json={"path": str(repo)}), 201)
    cached = response(client.get("/api/machine/check?offline=1"))
    assert cached["cached"]
    assert cached["harness_repos"] == {"claude": 2, "codex": 0, "pi": 0}
