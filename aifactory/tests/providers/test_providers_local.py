"""Provider ``local`` against a temporary repo and a bare remote."""

from __future__ import annotations

from pathlib import Path

import pytest
from provider_repo import commit_file, git, isolate_git, make_repo

from aifactory.config.settings import ProjectSettings
from aifactory.providers import (
    CLOSED,
    CONFLICT,
    MERGEABLE,
    MERGED,
    OPEN,
    MergeFailed,
    ProviderError,
    PullRequest,
)
from aifactory.providers.local import LocalProvider

BRANCH = "factory/T01-1"


@pytest.fixture(autouse=True)
def _git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    isolate_git(monkeypatch)


def _provider(repo: Path, **settings: str) -> LocalProvider:
    return LocalProvider(repo, ProjectSettings.model_validate(settings))


def _pr(provider: LocalProvider) -> PullRequest:
    return provider.create_pr(BRANCH, "T01", "body")


def test_create_pr_with_remote(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, with_remote=True)
    pr = _pr(_provider(repo))
    assert pr.id == BRANCH
    assert pr.branch == BRANCH
    assert pr.base == "main"
    assert pr.url.endswith(f"origin.git#{BRANCH}")


def test_create_pr_without_remote(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, with_remote=False)
    assert _pr(_provider(repo)).url == f"local:{BRANCH}"


def test_push_sends_branch_to_bare(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, with_remote=True)
    sha = commit_file(repo, BRANCH, "b.txt", "b\n", "add b")
    _provider(repo).push(repo, BRANCH)
    assert git(tmp_path / "origin.git", "rev-parse", f"refs/heads/{BRANCH}") == sha


def test_push_without_remote_is_noop(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, with_remote=False)
    commit_file(repo, BRANCH, "b.txt", "b\n", "add b")
    _provider(repo).push(repo, BRANCH)


def test_status_mergeable_and_clean_checkout(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, with_remote=True)
    sha = commit_file(repo, BRANCH, "b.txt", "b\n", "add b")
    provider = _provider(repo)
    status = provider.status(_pr(provider))
    assert (status.state, status.mergeability, status.head_sha) == (OPEN, MERGEABLE, sha)
    assert git(repo, "status", "--porcelain") == ""
    assert len(git(repo, "worktree", "list").splitlines()) == 1


def test_status_conflict(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, with_remote=True)
    commit_file(repo, BRANCH, "a.txt", "one\nTWO-branch\nthree\n", "branch edit")
    commit_file(repo, "main", "a.txt", "one\nTWO-main\nthree\n", "main edit")
    provider = _provider(repo)
    status = provider.status(_pr(provider))
    assert (status.state, status.mergeability) == (OPEN, CONFLICT)
    assert git(repo, "status", "--porcelain") == ""
    assert len(git(repo, "worktree", "list").splitlines()) == 1


def test_status_closed_when_branch_is_gone(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, with_remote=False)
    provider = _provider(repo)
    assert provider.status(_pr(provider)).state == CLOSED


def test_status_unknown_base(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, with_remote=False)
    commit_file(repo, BRANCH, "b.txt", "b\n", "add b")
    provider = _provider(repo, base="nope")
    with pytest.raises(ProviderError) as info:
        provider.status(_pr(provider))
    assert info.value.code == "unknown_base"


def test_merge_squash_by_default(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, with_remote=True)
    commit_file(repo, BRANCH, "b.txt", "b\n", "add b")
    sha = commit_file(repo, BRANCH, "c.txt", "c\n", "add c")
    before = git(repo, "rev-parse", "main")
    provider = _provider(repo)
    pr = _pr(provider)
    new = provider.merge(pr, sha, "T01: squashed")
    assert new == git(repo, "rev-parse", "main")
    assert git(repo, "rev-list", "--count", f"{before}..main") == "1"
    assert git(repo, "log", "-1", "--format=%P", "main") == before
    assert git(repo, "log", "-1", "--format=%s", "main") == "T01: squashed"
    assert git(tmp_path / "origin.git", "rev-parse", "main") == new
    assert (repo / "c.txt").is_file()


def test_merge_strategy_from_config(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, with_remote=True)
    sha = commit_file(repo, BRANCH, "b.txt", "b\n", "add b")
    provider = _provider(repo, merge_strategy="merge")
    pr = _pr(provider)
    new = provider.merge(pr, sha, "T01: merged")
    assert new is not None
    assert len(git(repo, "log", "-1", "--format=%P", "main").split()) == 2
    assert provider.status(pr).state == MERGED


def test_explicit_strategy_overrides_config(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, with_remote=False)
    sha = commit_file(repo, BRANCH, "b.txt", "b\n", "add b")
    provider = _provider(repo, merge_strategy="squash")
    provider.merge(_pr(provider), sha, "T01: merged", strategy="merge")
    assert len(git(repo, "log", "-1", "--format=%P", "main").split()) == 2


def test_merge_conflict(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, with_remote=True)
    sha = commit_file(repo, BRANCH, "a.txt", "one\nTWO-branch\nthree\n", "branch edit")
    commit_file(repo, "main", "a.txt", "one\nTWO-main\nthree\n", "main edit")
    git(repo, "push", "-q", "origin", "main")
    before = git(repo, "rev-parse", "main")
    provider = _provider(repo)
    with pytest.raises(MergeFailed) as info:
        provider.merge(_pr(provider), sha, "T01")
    assert info.value.code == "conflict"
    assert git(repo, "rev-parse", "main") == before
    assert git(tmp_path / "origin.git", "rev-parse", "main") == before
    assert git(repo, "status", "--porcelain") == ""


def test_merge_moved_head(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, with_remote=False)
    commit_file(repo, BRANCH, "b.txt", "b\n", "add b")
    provider = _provider(repo)
    with pytest.raises(MergeFailed) as info:
        provider.merge(_pr(provider), "0" * 40, "T01")
    assert info.value.code == "merge_failed"


def test_merge_invalid_strategy(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, with_remote=False)
    sha = commit_file(repo, BRANCH, "b.txt", "b\n", "add b")
    provider = _provider(repo)
    with pytest.raises(ProviderError) as info:
        provider.merge(_pr(provider), sha, "T01", strategy="rebase")
    assert info.value.code == "invalid_strategy"


def test_comment_is_noop(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, with_remote=False)
    provider = _provider(repo)
    provider.comment(_pr(provider), "hello")
