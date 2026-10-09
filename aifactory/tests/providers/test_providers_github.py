"""Provider ``github`` against a fake ``gh`` (no network)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from gh_fake import GhLog, install_fake_gh, prepare_shared_gh, reply

from aifactory.config.settings import ProjectSettings
from aifactory.providers import (
    CLOSED,
    CONFLICT,
    MERGEABLE,
    MERGED,
    OPEN,
    UNKNOWN,
    MergeFailed,
    ProviderError,
    PullRequest,
)
from aifactory.providers.github import GhCli, GitHubProvider

HEAD = "a" * 40
MERGE_SHA = "b" * 40
PR = PullRequest(
    id="7", url="https://github.com/o/r/pull/7", branch="factory/T01-1", base="main", title="T01"
)
DELAY = 0.5


@pytest.fixture(scope="module", autouse=True)
def _shared_gh(tmp_path_factory: pytest.TempPathFactory) -> None:
    prepare_shared_gh(tmp_path_factory.mktemp("ghwarm"))


def view(
    state: str = "OPEN", mergeable: str = "MERGEABLE", merge: str | None = None
) -> dict[str, Any]:
    data: dict[str, Any] = {"state": state, "mergeable": mergeable, "headRefOid": HEAD}
    data["mergeCommit"] = {"oid": merge} if merge else None
    return reply(data)


def _provider(
    tmp_path: Path,
    sleeps: list[float],
    attempts: int = 5,
    merge_attempts: int = 15,
    **settings: str,
) -> GitHubProvider:
    return GitHubProvider(
        tmp_path,
        ProjectSettings.model_validate({"git_provider": "github", **settings}),
        attempts=attempts,
        merge_attempts=merge_attempts,
        delay=DELAY,
        sleep=sleeps.append,
    )


def _pr_calls(log: GhLog, key: str) -> list[list[str]]:
    return [argv for argv in log.argvs() if " ".join(argv[:2]) == key]


def test_create_pr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_gh(
        tmp_path, monkeypatch, {"pr create": reply("Creating...\nhttps://github.com/o/r/pull/7\n")}
    )
    pr = _provider(tmp_path, []).create_pr("factory/T01-1", "T01: title", "the body")
    assert pr == PullRequest(
        id="7",
        url="https://github.com/o/r/pull/7",
        branch="factory/T01-1",
        base="main",
        title="T01: title",
    )
    (call,) = log.calls()
    assert call["argv"] == [
        "pr",
        "create",
        "--base",
        "main",
        "--head",
        "factory/T01-1",
        "--title",
        "T01: title",
        "--body-file",
        "-",
    ]
    assert call["stdin"] == "the body"
    assert Path(call["cwd"]).resolve() == tmp_path.resolve()


def test_create_pr_without_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_gh(tmp_path, monkeypatch, {"pr create": reply("nothing useful\n")})
    with pytest.raises(ProviderError) as info:
        _provider(tmp_path, []).create_pr("factory/T01-1", "T01", "body")
    assert info.value.code == "gh_failed"


@pytest.mark.parametrize(
    ("answer", "state", "mergeability", "merge_sha"),
    [
        (view("OPEN", "MERGEABLE"), OPEN, MERGEABLE, None),
        (view("OPEN", "CONFLICTING"), OPEN, CONFLICT, None),
        (view("MERGED", "UNKNOWN", MERGE_SHA), MERGED, UNKNOWN, MERGE_SHA),
        (view("CLOSED", "UNKNOWN"), CLOSED, UNKNOWN, None),
    ],
)
def test_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    answer: dict[str, Any],
    state: str,
    mergeability: str,
    merge_sha: str | None,
) -> None:
    log = install_fake_gh(tmp_path, monkeypatch, {"pr view": answer})
    sleeps: list[float] = []
    status = _provider(tmp_path, sleeps).status(PR)
    assert (status.state, status.mergeability) == (state, mergeability)
    assert status.head_sha == HEAD
    assert status.merge_sha == merge_sha
    assert log.argvs() == [["pr", "view", "7", "--json", "state,mergeable,headRefOid,mergeCommit"]]
    assert sleeps == []


def test_status_retries_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {"pr view": [view(mergeable="UNKNOWN"), view(mergeable="UNKNOWN"), view()]},
    )
    sleeps: list[float] = []
    status = _provider(tmp_path, sleeps).status(PR)
    assert (status.state, status.mergeability) == (OPEN, MERGEABLE)
    assert len(_pr_calls(log, "pr view")) == 3
    assert sleeps == [DELAY, DELAY]


def test_status_unknown_runs_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_gh(tmp_path, monkeypatch, {"pr view": view(mergeable="UNKNOWN")})
    sleeps: list[float] = []
    status = _provider(tmp_path, sleeps, attempts=3).status(PR)
    assert (status.state, status.mergeability) == (OPEN, UNKNOWN)
    assert len(_pr_calls(log, "pr view")) == 3
    assert sleeps == [DELAY, DELAY]


def test_default_status_unknown_runs_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_gh(tmp_path, monkeypatch, {"pr view": view(mergeable="UNKNOWN")})
    sleeps: list[float] = []
    provider = GitHubProvider(tmp_path, ProjectSettings(), sleep=sleeps.append)

    status = provider.status(PR)

    assert (status.state, status.mergeability) == (OPEN, UNKNOWN)
    assert len(_pr_calls(log, "pr view")) == 30
    assert sleeps == [2.0] * 29


@pytest.mark.parametrize("state", ["CLOSED", "MERGED"])
def test_status_stops_when_unknown_pr_is_no_longer_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {"pr view": [view(mergeable="UNKNOWN"), view(state, "UNKNOWN", MERGE_SHA)]},
    )
    sleeps: list[float] = []
    provider = GitHubProvider(tmp_path, ProjectSettings(), sleep=sleeps.append)

    status = provider.status(PR)

    assert status.state == state.lower()
    assert len(_pr_calls(log, "pr view")) == 2
    assert sleeps == [2.0]


def test_unknown_then_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    responses: dict[str, Any] = {
        "pr view": [view(mergeable="UNKNOWN"), view(mergeable="CONFLICTING")]
    }
    log = install_fake_gh(tmp_path, monkeypatch, responses)
    sleeps: list[float] = []
    provider = _provider(tmp_path, sleeps)
    status = provider.status(PR)
    assert (status.state, status.mergeability) == (OPEN, CONFLICT)
    assert sleeps == [DELAY]

    log.respond("pr view", [view(mergeable="UNKNOWN"), view(mergeable="CONFLICTING")])
    with pytest.raises(MergeFailed) as info:
        provider.merge(PR, HEAD, "T01")
    assert info.value.code == "conflict"
    assert _pr_calls(log, "pr merge") == []


def test_merge_default_squash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {"pr view": [view(), view("MERGED", "UNKNOWN", MERGE_SHA)], "pr merge": reply("")},
    )
    assert _provider(tmp_path, []).merge(PR, HEAD, "T01: subject") == MERGE_SHA
    assert _pr_calls(log, "pr merge") == [
        ["pr", "merge", "7", "--squash", "--match-head-commit", HEAD, "--subject", "T01: subject"]
    ]


def test_merge_strategy_from_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {"pr view": [view(), view("MERGED", "UNKNOWN", MERGE_SHA)], "pr merge": reply("")},
    )
    _provider(tmp_path, [], merge_strategy="merge").merge(PR, HEAD, "T01")
    (call,) = _pr_calls(log, "pr merge")
    assert "--merge" in call
    assert "--squash" not in call


def test_merge_failure_turns_out_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_gh(
        tmp_path,
        monkeypatch,
        {
            "pr view": [view(mergeable="UNKNOWN"), view(mergeable="CONFLICTING")],
            "pr merge": reply(exit=1, stderr="not mergeable"),
        },
    )
    with pytest.raises(MergeFailed) as info:
        _provider(tmp_path, [], attempts=1).merge(PR, HEAD, "T01")
    assert info.value.code == "conflict"


def test_merge_failure_other(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {"pr view": view(), "pr merge": reply(exit=1, stderr="head moved")},
    )
    sleeps: list[float] = []
    with pytest.raises(MergeFailed) as info:
        _provider(tmp_path, sleeps).merge(PR, HEAD, "T01")
    assert info.value.code == "merge_failed"
    assert "head moved" in info.value.message
    assert len(_pr_calls(log, "pr merge")) == 1
    assert sleeps == []


BASE_MODIFIED = (
    "GraphQL: Base branch was modified. Review and try the merge again. (mergePullRequest)\n"
)


def test_merge_retries_base_branch_modified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {
            "pr view": [view(), view(), view("MERGED", "UNKNOWN", MERGE_SHA)],
            "pr merge": [reply(exit=1, stderr=BASE_MODIFIED), reply("")],
        },
    )
    sleeps: list[float] = []
    assert _provider(tmp_path, sleeps).merge(PR, HEAD, "T01") == MERGE_SHA
    assert len(_pr_calls(log, "pr merge")) == 2
    assert sleeps == [DELAY]


def test_merge_transient_runs_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {"pr view": view(), "pr merge": reply(exit=1, stderr=BASE_MODIFIED)},
    )
    sleeps: list[float] = []
    with pytest.raises(MergeFailed) as info:
        _provider(tmp_path, sleeps, attempts=3).merge(PR, HEAD, "T01")
    assert info.value.code == "merge_failed"
    assert "Base branch was modified" in info.value.message
    assert len(_pr_calls(log, "pr merge")) == 3
    assert sleeps == [DELAY, DELAY]


def test_merge_transient_but_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {
            "pr view": [view(), view(mergeable="CONFLICTING")],
            "pr merge": reply(exit=1, stderr=BASE_MODIFIED),
        },
    )
    sleeps: list[float] = []
    with pytest.raises(MergeFailed) as info:
        _provider(tmp_path, sleeps).merge(PR, HEAD, "T01")
    assert info.value.code == "conflict"
    assert len(_pr_calls(log, "pr merge")) == 1
    assert sleeps == []


def test_default_transient_merge_retry_budget_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {"pr view": view(), "pr merge": reply(exit=1, stderr=BASE_MODIFIED)},
    )
    sleeps: list[float] = []
    provider = GitHubProvider(tmp_path, ProjectSettings(), sleep=sleeps.append)

    with pytest.raises(MergeFailed) as info:
        provider.merge(PR, HEAD, "T01")

    assert info.value.code == "merge_failed"
    assert "gave up after 5 attempts" in info.value.message
    assert len(_pr_calls(log, "pr merge")) == 5
    assert sleeps == [2.0] * 4


def test_merge_failure_but_merged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {
            "pr view": [view(), view("MERGED", "UNKNOWN", MERGE_SHA)],
            "pr merge": reply(exit=1, stderr=BASE_MODIFIED),
        },
    )
    sleeps: list[float] = []
    assert _provider(tmp_path, sleeps).merge(PR, HEAD, "T01") == MERGE_SHA
    assert len(_pr_calls(log, "pr merge")) == 1
    assert sleeps == []


NOT_MERGEABLE = "GraphQL: Pull Request is not mergeable (mergePullRequest)\n"


def test_merge_waits_for_unknown_mergeability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unknown = view(mergeable="UNKNOWN")
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {
            "pr view": [unknown, unknown, unknown, view(), view("MERGED", "UNKNOWN", MERGE_SHA)],
            "pr merge": reply(""),
        },
    )
    sleeps: list[float] = []
    # status() alone would give up after 2 asks; merge waits up to merge_attempts.
    provider = _provider(tmp_path, sleeps, attempts=2, merge_attempts=5)
    assert provider.merge(PR, HEAD, "T01") == MERGE_SHA
    assert len(_pr_calls(log, "pr merge")) == 1
    assert sleeps == [DELAY, DELAY, DELAY]


def test_merge_not_mergeable_while_unknown_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unknown = view(mergeable="UNKNOWN")
    merged = view("MERGED", "UNKNOWN", MERGE_SHA)
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {
            # 3 asks before the merge, one after each rejection, then the merged PR
            "pr view": [unknown] * 3 + [unknown, unknown, merged],
            "pr merge": [
                reply(exit=1, stderr=NOT_MERGEABLE),
                reply(exit=1, stderr=NOT_MERGEABLE),
                reply(""),
            ],
        },
    )
    sleeps: list[float] = []
    provider = _provider(tmp_path, sleeps, attempts=1, merge_attempts=3)
    assert provider.merge(PR, HEAD, "T01") == MERGE_SHA
    assert len(_pr_calls(log, "pr merge")) == 3
    assert sleeps == [DELAY] * 4


def test_merge_not_mergeable_conflicting_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {
            "pr view": [view(), view(mergeable="CONFLICTING")],
            "pr merge": reply(exit=1, stderr=NOT_MERGEABLE),
        },
    )
    sleeps: list[float] = []
    with pytest.raises(MergeFailed) as info:
        _provider(tmp_path, sleeps).merge(PR, HEAD, "T01")
    assert info.value.code == "conflict"
    assert len(_pr_calls(log, "pr merge")) == 1
    assert sleeps == []


def test_merge_not_mergeable_runs_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_gh(
        tmp_path,
        monkeypatch,
        {"pr view": view(mergeable="UNKNOWN"), "pr merge": reply(exit=1, stderr=NOT_MERGEABLE)},
    )
    sleeps: list[float] = []
    with pytest.raises(MergeFailed) as info:
        _provider(tmp_path, sleeps, attempts=1, merge_attempts=3).merge(PR, HEAD, "T01")
    assert info.value.code == "merge_failed"
    assert "not mergeable" in info.value.message
    assert "unknown" in info.value.message
    assert len(_pr_calls(log, "pr merge")) == 3
    # 2 pauses waiting before the merge, 2 between the 3 merge attempts
    assert sleeps == [DELAY] * 4


def test_merge_attempts_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _provider(tmp_path, [], merge_attempts=0)


def test_merge_already_merged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_gh(tmp_path, monkeypatch, {"pr view": view("MERGED", "UNKNOWN", MERGE_SHA)})
    assert _provider(tmp_path, []).merge(PR, HEAD, "T01") == MERGE_SHA
    assert _pr_calls(log, "pr merge") == []


def test_merge_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_gh(tmp_path, monkeypatch, {"pr view": view("CLOSED", "UNKNOWN")})
    with pytest.raises(MergeFailed) as info:
        _provider(tmp_path, []).merge(PR, HEAD, "T01")
    assert info.value.code == "merge_failed"
    assert _pr_calls(log, "pr merge") == []


def test_comment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_gh(tmp_path, monkeypatch, {"pr comment": reply("")})
    _provider(tmp_path, []).comment(PR, "hello")
    (call,) = log.calls()
    assert call["argv"] == ["pr", "comment", "7", "--body-file", "-"]
    assert call["stdin"] == "hello"


def test_update_pr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_gh(tmp_path, monkeypatch, {"pr edit": reply("")})
    _provider(tmp_path, []).update_pr(PR, "new body")
    (call,) = log.calls()
    assert call["argv"] == ["pr", "edit", "7", "--body-file", "-"]
    assert call["stdin"] == "new body"


def test_gh_missing(tmp_path: Path) -> None:
    gh = GhCli(tmp_path, executable=str(tmp_path / "nope"))
    with pytest.raises(ProviderError) as info:
        gh.run("pr", "view", "7")
    assert info.value.code == "gh_missing"


def test_attempts_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _provider(tmp_path, [], attempts=0)
