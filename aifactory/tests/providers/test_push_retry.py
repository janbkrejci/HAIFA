"""``providers.git.push``: transient failures are retried, a rejected push is not (fake git)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from git_fake import HTTP2, REJECTED, install_fake_git

from aifactory.providers import ProviderError
from aifactory.providers import git as pgit


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return proc.stdout.strip()


def test_fake_git_preserves_revision_arguments(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    install_fake_git(tmp_path, monkeypatch)
    assert _git(repo, "rev-parse", "--verify", "main^{commit}") == head


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "branch", "factory/x-1")
    return repo


@pytest.fixture(name="sleeps")
def sleeps_fixture(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(pgit, "_sleep", slept.append)
    return slept


def _remote_tip(repo: Path, branch: str) -> str:
    return _git(repo, "ls-remote", "origin", f"refs/heads/{branch}")


def test_transient_failure_then_success(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    fake = install_fake_git(tmp_path, monkeypatch)
    fake.fail_push(1, HTTP2)
    fake.fail_push(2, "fatal: unable to access 'https://h/r.git/': Operation timed out\n")

    pgit.push(repo, "origin", "factory/x-1")

    assert fake.pushes() == 3
    assert sleeps == [pgit.PUSH_DELAY, pgit.PUSH_DELAY * 2]
    assert _remote_tip(repo, "factory/x-1")


def test_rejected_push_is_not_retried(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    fake = install_fake_git(tmp_path, monkeypatch)
    fake.fail_push(1, REJECTED)

    with pytest.raises(ProviderError) as info:
        pgit.push(repo, "origin", "factory/x-1")

    assert info.value.code == "push_failed"
    assert "non-fast-forward" in info.value.message
    assert "gave up" not in info.value.message
    assert fake.pushes() == 1
    assert sleeps == []
    assert _remote_tip(repo, "factory/x-1") == ""


def test_gives_up_after_bounded_attempts(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    fake = install_fake_git(tmp_path, monkeypatch)
    for n in range(1, pgit.PUSH_ATTEMPTS + 2):
        fake.fail_push(n, HTTP2)

    with pytest.raises(ProviderError) as info:
        pgit.push(repo, "origin", "factory/x-1")

    assert info.value.code == "push_failed"
    assert f"gave up after {pgit.PUSH_ATTEMPTS} attempts" in info.value.message
    assert fake.pushes() == pgit.PUSH_ATTEMPTS
    assert len(sleeps) == pgit.PUSH_ATTEMPTS - 1
    assert 2 <= pgit.PUSH_ATTEMPTS <= 9


@pytest.mark.parametrize(
    "stderr",
    [
        HTTP2,
        "fatal: the remote end hung up unexpectedly",
        "ssh: connect to host github.com port 22: Operation timed out",
        "fatal: unable to access 'https://github.com/o/r.git/': Could not resolve host: x",
        "error: RPC failed; HTTP 502 curl 22 The requested URL returned error: 502",
    ],
)
def test_transient_errors(stderr: str) -> None:
    assert pgit.transient_push_error(stderr)


@pytest.mark.parametrize(
    "stderr",
    [
        REJECTED,
        " ! [rejected]  main -> main (fetch first)",
        " ! [remote rejected] factory/x -> factory/x (protected branch hook declined)",
        "ERROR: Permission to o/r.git denied to someone.\nfatal: Could not read from remote "
        "repository.",
        "remote: Permission to o/r.git denied.\nfatal: unable to access "
        "'https://github.com/o/r.git/': The requested URL returned error: 403",
        "error: failed to push some refs: stale info",
        "fatal: something unexpected",
    ],
)
def test_rejections_are_not_transient(stderr: str) -> None:
    assert not pgit.transient_push_error(stderr)
