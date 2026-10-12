"""``base_changes: pr`` and ``base_pr_merge: auto``: factory's own base changes go through
pull requests, merged at once when asked (local provider, bare remote, fake ``gh``)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from aifactory.backlog import add_task, commit_backlog
from aifactory.config import ProjectSettings
from aifactory.config.commit import commit_config, pull_config
from aifactory.library.install import project_settings, render_config
from aifactory.providers.base import MergeFailed, PullRequest
from aifactory.providers.github import GhCli, GhError, GitHubProvider

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))

from run_repo import git, make_run_repo, write  # noqa: E402


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{key}_NAME", "t")
        monkeypatch.setenv(f"GIT_{key}_EMAIL", "t@example.com")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")


def _repo(tmp_path: Path, merge: str) -> Path:
    repo = make_run_repo(tmp_path / "repo")
    config = repo / ".factory/config.yaml"
    text = config.read_text(encoding="utf-8")
    write(repo, ".factory/config.yaml", f"{text}base_changes: pr\nbase_pr_merge: {merge}\n")
    write(repo, ".factory/local.yaml", f"trace_db: {tmp_path / 'trace.db'}\n")
    git(repo, "add", ".factory/config.yaml")
    git(repo, "commit", "-q", "-m", "factory changes base through pull requests")
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "-u", "origin", "main")
    return repo


def _remote(tmp_path: Path, ref: str) -> str:
    return git(tmp_path / "origin.git", "rev-parse", ref)


def _dirty(repo: Path) -> list[str]:
    return [line for line in git(repo, "status", "--porcelain").splitlines() if line.strip()]


def test_backlog_pr_waits_for_the_merge_and_the_pull_takes_it(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "manual")
    before = git(repo, "rev-parse", "main")
    added = add_task(repo, "M01-S01", "Třetí")

    result = commit_backlog(repo)

    assert result.committed and not result.merged
    assert result.pr is not None and result.pr["branch"] == "factory-backlog/1"
    assert git(repo, "rev-parse", "main") == before == _remote(tmp_path, "main")
    assert _remote(tmp_path, "factory-backlog/1") == result.commit
    assert _dirty(repo)  # the task stays in the working tree until the PR is merged

    git(repo, "push", "-q", "origin", "factory-backlog/1:main")  # the reviewer merges
    pulled = pull_config(repo)

    assert pulled.updated and git(repo, "rev-parse", "main") == result.commit
    assert _dirty(repo) == []
    assert git(repo, "show", f"main:{added.path}")


def test_backlog_pr_merged_at_once(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "auto")
    added = add_task(repo, "M01-S01", "Třetí")

    result = commit_backlog(repo)

    assert result.committed and result.merged and result.pr is not None
    assert git(repo, "rev-parse", "main") == result.commit == _remote(tmp_path, "main")
    assert git(repo, "show", f"main:{added.path}")
    assert _dirty(repo) == []


def test_config_commit_follows_the_setting(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "auto")
    path = repo / ".factory/config.yaml"
    write(repo, ".factory/config.yaml", path.read_text(encoding="utf-8") + "max_parallel_runs: 2\n")

    result = commit_config(repo)

    assert result.plan.target == "pr" and result.branch == "factory-config/1"
    assert result.merged and result.advanced
    assert git(repo, "rev-parse", "main") == _remote(tmp_path, "main") == result.commit
    assert _dirty(repo) == []


def test_init_writes_the_setting() -> None:
    settings = project_settings(
        base="develop", provider="github", base_changes="pr", base_pr_merge="auto"
    )
    text = render_config(settings).decode("utf-8")
    assert "base_changes: pr\n" in text and "base_pr_merge: auto\n" in text
    plain = render_config(project_settings(base="main", provider="local")).decode("utf-8")
    assert "base_changes" not in plain and "base_pr_merge" not in plain


class _Gh(GhCli):
    """``gh pr merge`` refused without ``--admin`` (a required review); the PR then merged."""

    def __init__(self, admin_ok: bool) -> None:
        super().__init__(Path("."))
        self.admin_ok = admin_ok
        self.calls: list[tuple[str, ...]] = []

    def run(self, *args: str, stdin: str | None = None) -> str:
        self.calls.append(args)
        if args[:2] == ("pr", "merge") and ("--admin" not in args or not self.admin_ok):
            raise GhError(args, 1, "base branch policy prohibits the merge\n")
        return ""

    def json(self, *args: str) -> Any:
        return {"state": "MERGED", "headRefOid": "h", "mergeCommit": {"oid": "m"}}


PR_7 = PullRequest(id="7", url="https://github.com/o/r/pull/7", branch="b", base="main", title="t")


def test_github_merges_its_own_pr_with_admin(tmp_path: Path) -> None:
    gh = _Gh(admin_ok=True)
    provider = GitHubProvider(tmp_path, ProjectSettings(), gh)
    assert provider.merge_own(PR_7, "h", "factory: x") == "m"
    merges = [c for c in gh.calls if c[:2] == ("pr", "merge")]
    assert len(merges) == 2 and "--admin" not in merges[0] and "--admin" in merges[1]
    assert merges[1][4:6] == ("--match-head-commit", "h")


def test_github_without_admin_rights_keeps_the_pr_open(tmp_path: Path) -> None:
    provider = GitHubProvider(tmp_path, ProjectSettings(), _Gh(admin_ok=False))
    with pytest.raises(MergeFailed) as info:
        provider.merge_own(PR_7, "h", "factory: x")
    assert "with --admin" in info.value.message
