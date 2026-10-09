"""Temporary git repositories with an optional bare remote (helpers, not fixtures)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import repo_templates


def isolate_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """No global or system git config; a fixed identity for commits."""
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    for key, value in {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }.items():
        monkeypatch.setenv(key, value)


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.stdout.strip()


def _build_repo(repo: Path) -> None:
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "a.txt").write_text("one\ntwo\nthree\n", encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "initial")


def make_repo(tmp_path: Path, *, with_remote: bool) -> Path:
    """A repo on ``main`` with one commit (``a.txt``); optionally a bare ``origin``."""
    repo = tmp_path / "repo"
    repo_templates.build(repo, "provider", _build_repo)
    if with_remote:
        bare = tmp_path / "origin.git"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
        git(repo, "remote", "add", "origin", str(bare))
        git(repo, "push", "-q", "-u", "origin", "main")
    return repo


def commit_file(repo: Path, branch: str, path: str, text: str, message: str) -> str:
    """Commit `text` to `path` on `branch` (created from HEAD if new); back to main."""
    exists = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=repo,
        capture_output=True,
    )
    if exists.returncode == 0:
        git(repo, "checkout", "-q", branch)
    else:
        git(repo, "checkout", "-q", "-b", branch)
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    sha = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "main")
    return sha
