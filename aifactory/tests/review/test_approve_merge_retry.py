"""Approve with provider ``github`` when GitHub rejects the merge with a transient error.

A fake ``gh`` and the fake harness; no test calls a model or the network.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from aifactory.config import load_run_config
from aifactory.config.settings import AzureSettings
from aifactory.providers.azure import AzCli, AzureProvider
from aifactory.providers.github import GitHubProvider
from aifactory.review import ReviewError, approve_task
from aifactory.run import TaskPrRow, TaskRunStore, run_task

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "providers"))

from run_repo import SPEC, T01, Script, fake_env, git, make_run_repo, ok, write  # noqa: E402,I001
from gh_fake import install_fake_gh, prepare_shared_gh, reply  # noqa: E402

BRANCH = f"factory/{T01}-1"
MERGE_SHA = "b" * 40
DONE = f"{T01}: status done"
BASE_MODIFIED = (
    "GraphQL: Base branch was modified. Review and try the merge again. (mergePullRequest)\n"
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


def view(
    state: str = "OPEN", merge: str | None = None, mergeable: str | None = None
) -> dict[str, Any]:
    return reply(
        {
            "state": state,
            "mergeable": mergeable or ("MERGEABLE" if state == "OPEN" else "UNKNOWN"),
            "headRefOid": "x",
            "mergeCommit": {"oid": merge} if merge else None,
        }
    )


def stored_pr(repo: Path) -> TaskPrRow | None:
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        return store.pr_for_branch(BRANCH)
    finally:
        store.close()


def done_commits(repo: Path, ref: str) -> int:
    return git(repo, "log", "--format=%s", ref).splitlines().count(DONE)


def test_approve_again_after_transient_merge_failure(
    repo: Path, script: Script, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, capture_output=True
    )
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "-u", "origin", "main")
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {
            "pr create": reply("https://github.com/o/r/pull/7\n"),
            "pr view": view(),
            "pr merge": reply(exit=1, stderr=BASE_MODIFIED),
        },
    )
    provider = GitHubProvider(
        repo, load_run_config(repo).config.settings, attempts=2, delay=0, sleep=lambda _: None
    )

    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add schema spec"))
    run = run_task(repo, T01, provider=provider)
    assert run.ok, (run.run.error, run.pr_error)

    with pytest.raises(ReviewError) as info:
        approve_task(repo, T01, provider=provider)
    assert info.value.code == "merge_failed"
    assert "Base branch was modified" in info.value.message
    merges = [a for a in log.argvs() if a[:2] == ["pr", "merge"]]
    assert len(merges) == 2
    tip = git(origin, "rev-parse", BRANCH)
    assert done_commits(origin, BRANCH) == 1
    saved = stored_pr(repo)
    assert saved is not None and saved.state == "open"

    log.clear()
    log.respond("pr merge", reply(""))
    log.respond("pr view", [view(), view(), view("MERGED", MERGE_SHA)])

    result = approve_task(repo, T01, provider=provider)

    assert result.merge_sha == MERGE_SHA
    assert result.reviewed is False
    assert git(origin, "rev-parse", BRANCH) == tip
    assert done_commits(origin, BRANCH) == 1
    merges = [a for a in log.argvs() if a[:2] == ["pr", "merge"]]
    assert len(merges) == 1
    assert merges[0][merges[0].index("--match-head-commit") + 1] == tip
    saved = stored_pr(repo)
    assert saved is not None and saved.state == "merged"


NOT_MERGEABLE = "GraphQL: Pull Request is not mergeable (mergePullRequest)\n"


def _github_task(
    repo: Path, script: Script, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kwargs: Any
) -> tuple[GitHubProvider, Any, Path]:
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, capture_output=True
    )
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "-u", "origin", "main")
    log = install_fake_gh(
        tmp_path, monkeypatch, {"pr create": reply("https://github.com/o/r/pull/7\n")}
    )
    provider = GitHubProvider(
        repo, load_run_config(repo).config.settings, delay=0, sleep=lambda _: None, **kwargs
    )
    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add schema spec"))
    run = run_task(repo, T01, provider=provider)
    assert run.ok, (run.run.error, run.pr_error)
    log.clear()
    return provider, log, origin


def test_approve_retries_not_mergeable_while_unknown(
    repo: Path, script: Script, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider, log, _ = _github_task(
        repo, script, tmp_path, monkeypatch, attempts=1, merge_attempts=5
    )
    unknown = view(mergeable="UNKNOWN")
    # approve's check, merge's wait (all unknown), status after the rejection, merged
    log.respond("pr view", [view()] + [unknown] * 5 + [unknown, view("MERGED", MERGE_SHA)])
    log.respond("pr merge", [reply(exit=1, stderr=NOT_MERGEABLE), reply("")])

    result = approve_task(repo, T01, provider=provider)

    assert result.merge_sha == MERGE_SHA
    assert len([a for a in log.argvs() if a[:2] == ["pr", "merge"]]) == 2
    saved = stored_pr(repo)
    assert saved is not None and saved.state == "merged"


def test_approve_not_mergeable_runs_out(
    repo: Path, script: Script, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider, log, origin = _github_task(
        repo, script, tmp_path, monkeypatch, attempts=1, merge_attempts=3
    )
    log.respond("pr view", [view(), view(mergeable="UNKNOWN")])
    log.respond("pr merge", reply(exit=1, stderr=NOT_MERGEABLE))

    with pytest.raises(ReviewError) as info:
        approve_task(repo, T01, provider=provider)

    assert info.value.code == "merge_failed"
    assert "not mergeable" in info.value.message
    assert len([a for a in log.argvs() if a[:2] == ["pr", "merge"]]) == 3
    assert done_commits(origin, BRANCH) == 1
    saved = stored_pr(repo)
    assert saved is not None and saved.state == "open"


def test_approve_not_mergeable_conflicting_not_retried(
    repo: Path, script: Script, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider, log, _ = _github_task(repo, script, tmp_path, monkeypatch, attempts=1)
    log.respond("pr view", [view(), view(), view(mergeable="CONFLICTING")])
    log.respond("pr merge", reply(exit=1, stderr=NOT_MERGEABLE))

    with pytest.raises(ReviewError) as info:
        approve_task(repo, T01, provider=provider)

    assert info.value.code == "conflict"
    assert len([a for a in log.argvs() if a[:2] == ["pr", "merge"]]) == 1


@pytest.mark.parametrize("failure", ["vote", "merge"])
def test_azure_approve_final_push_before_vote_and_retry(
    repo: Path, script: Script, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    # Reuse the offline run fixture; Azure's fake below observes the bare remote's real tip.
    _, _, origin = _github_task(repo, script, tmp_path, monkeypatch)
    settings = load_run_config(repo).config.settings.model_copy(
        update={
            "git_provider": "azure",
            "azure": AzureSettings(organization="contoso", project="p", repository="r"),
        }
    )
    calls: list[str] = []
    vote_heads: list[str] = []
    fail = True

    class OfflineAz(AzCli):
        def run(self, *args: str) -> str:
            from aifactory.providers.azure import AzError

            command = " ".join(args[:3])
            calls.append(command)
            if command == "repos pr show":
                return json.dumps(
                    {
                        "status": "active",
                        "mergeStatus": "succeeded",
                        "lastMergeSourceCommit": {"commitId": git(origin, "rev-parse", BRANCH)},
                    }
                )
            if command == "repos pr set-vote":
                # A successful push must already include exactly one done commit.
                assert done_commits(origin, BRANCH) == 1
                vote_heads.append(git(origin, "rev-parse", BRANCH))
                if fail and failure == "vote":
                    raise AzError(args, 1, "vote permission denied")
            if command == "repos pr update":
                assert vote_heads[-1] == git(origin, "rev-parse", BRANCH)
                if fail and failure == "merge":
                    raise AzError(args, 1, "branch policy rejected completion")
                return json.dumps(
                    {"status": "completed", "lastMergeCommit": {"commitId": MERGE_SHA}}
                )
            return "{}"

    provider = AzureProvider(repo, settings, OfflineAz(repo), attempts=1, delay=0)
    with pytest.raises(ReviewError) as info:
        approve_task(repo, T01, provider=provider)
    assert info.value.code == ("approve_failed" if failure == "vote" else "merge_failed")
    assert ("repos pr update" in calls) is (failure == "merge")
    assert done_commits(origin, BRANCH) == 1
    tip = git(origin, "rev-parse", BRANCH)
    saved = stored_pr(repo)
    assert saved is not None and saved.state == "open"

    fail = False
    calls.clear()
    result = approve_task(repo, T01, provider=provider)
    assert result.reviewed is True
    assert result.to_json()["reviewed"] is True
    assert calls.index("repos pr set-vote") < calls.index("repos pr update")
    assert vote_heads == [tip, tip]
    assert done_commits(origin, BRANCH) == 1
    assert result.merge_sha == MERGE_SHA
