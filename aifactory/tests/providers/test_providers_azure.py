"""Provider ``azure`` against a fake ``az`` (no network)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from az_fake import (
    HEAD,
    MERGE_SHA,
    ORG_URL,
    WEB_URL,
    AzLog,
    call_key,
    install_fake_az,
    pr_json,
    prepare_shared_az,
    reply,
    thread_json,
)

from aifactory.config.errors import ConfigIssue
from aifactory.config.settings import AzureSettings, ProjectSettings, parse_project_settings
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
from aifactory.providers.azure import API_VERSION, AzCli, AzureProvider

PR = PullRequest(
    id="7", url=f"{WEB_URL}/pullrequest/7", branch="factory/T01-1", base="main", title="T01"
)
DELAY = 0.5
TAIL = ["--detect", "false", "--output", "json", "--only-show-errors"]
AZURE = {"organization": "contoso", "project": "Fab Rikam", "repository": "app"}


@pytest.fixture(scope="module", autouse=True)
def _shared_az(tmp_path_factory: pytest.TempPathFactory) -> None:
    prepare_shared_az(tmp_path_factory.mktemp("azwarm"))


def show(**kwargs: Any) -> dict[str, Any]:
    return reply(pr_json(**kwargs))


def _provider(
    tmp_path: Path,
    sleeps: list[float],
    attempts: int = 5,
    az: AzCli | None = None,
    **settings: str,
) -> AzureProvider:
    return AzureProvider(
        tmp_path,
        ProjectSettings.model_validate({"git_provider": "azure", "azure": AZURE, **settings}),
        az,
        attempts=attempts,
        delay=DELAY,
        sleep=sleeps.append,
    )


def _calls(log: AzLog, key: str) -> list[list[str]]:
    return [argv for argv in log.argvs() if call_key(argv) == key]


def _issues(text: str) -> list[ConfigIssue]:
    issues: list[ConfigIssue] = []
    assert parse_project_settings(text, "config.yaml", issues) is None
    return issues


# -- configuration ----------------------------------------------------------


@pytest.mark.parametrize(
    ("organization", "url"),
    [
        ("contoso", "https://dev.azure.com/contoso"),
        ("https://dev.azure.com/contoso/", "https://dev.azure.com/contoso"),
        ("https://contoso.visualstudio.com", "https://contoso.visualstudio.com"),
    ],
)
def test_organization_url(organization: str, url: str) -> None:
    settings = AzureSettings(organization=organization, project="p", repository="r")
    assert settings.organization_url == url


def test_azure_needs_section() -> None:
    issues = _issues("git_provider: azure\n")
    assert any("azure" in str(issue) for issue in issues)


@pytest.mark.parametrize(
    "section",
    [
        "azure:\n  organization: contoso\n  project: ' '\n  repository: app\n",
        "azure:\n  organization: contoso\n  project: p\n  repository: app\n  extra: 1\n",
        "azure:\n  organization: contoso\n  project: p\n",
    ],
)
def test_azure_section_is_validated(section: str) -> None:
    issues = _issues(f"git_provider: azure\n{section}")
    assert any("azure" in str(issue) for issue in issues)


def test_azure_section_parses() -> None:
    issues: list[ConfigIssue] = []
    text = "git_provider: azure\nazure:\n  organization: contoso\n  project: P\n  repository: r\n"
    settings = parse_project_settings(text, "config.yaml", issues)
    assert settings is not None, issues
    assert settings.azure == AzureSettings(organization="contoso", project="P", repository="r")
    assert settings.model_dump(mode="json")["azure"]["project"] == "P"


def test_attempts_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _provider(tmp_path, [], attempts=0)


def test_constructor_does_not_run_az(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(tmp_path, monkeypatch)
    _provider(tmp_path, [])
    assert log.calls() == []


# -- provider self-check ----------------------------------------------------


def test_az_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_az(tmp_path, monkeypatch)
    provider = _provider(tmp_path, [], az=AzCli(tmp_path, executable=str(tmp_path / "nope")))
    with pytest.raises(ProviderError) as info:
        provider.create_pr("factory/T01-1", "T01", "body")
    assert info.value.code == "az_missing"
    assert "install" in info.value.message


def test_az_version_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_az(tmp_path, monkeypatch, {"--version": reply(exit=1, stderr="broken")})
    with pytest.raises(ProviderError) as info:
        _provider(tmp_path, []).status(PR)
    assert info.value.code == "az_missing"


def test_devops_extension_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(
        tmp_path,
        monkeypatch,
        {"extension show": reply(exit=1, stderr="The extension azure-devops is not installed.")},
    )
    with pytest.raises(ProviderError) as info:
        _provider(tmp_path, []).status(PR)
    assert info.value.code == "az_devops_missing"
    assert "az extension add --name azure-devops" in info.value.message
    assert _calls(log, "repos pr show") == []


def test_not_logged_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(
        tmp_path,
        monkeypatch,
        {"account show": reply(exit=1, stderr="Please run 'az login' to setup account.")},
    )
    with pytest.raises(ProviderError) as info:
        _provider(tmp_path, []).create_pr("factory/T01-1", "T01", "body")
    assert info.value.code == "az_not_logged_in"
    assert "az login" in info.value.message
    assert _calls(log, "repos pr create") == []


def test_pat_skips_login_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(
        tmp_path,
        monkeypatch,
        {"account show": reply(exit=1, stderr="Please run 'az login'"), "repos pr show": show()},
    )
    monkeypatch.setenv("AZURE_DEVOPS_EXT_PAT", "secret")
    assert _provider(tmp_path, []).status(PR).state == OPEN
    assert _calls(log, "account show") == []


def test_check_runs_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(tmp_path, monkeypatch, {"repos pr show": show()})
    provider = _provider(tmp_path, [])
    provider.status(PR)
    provider.comment(PR, "hi")
    assert [call_key(argv) for argv in log.argvs()] == [
        "--version",
        "extension show",
        "account show",
        "repos pr show",
        "devops invoke",
    ]


@pytest.mark.parametrize(
    ("stderr", "code"),
    [
        ("ERROR: Please run 'az login' to setup account.", "az_not_logged_in"),
        ("TF400813: The user is not authorized to access this resource.", "az_not_logged_in"),
        ("TF401180: The requested pull request was not found.", "az_failed"),
    ],
)
def test_operation_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stderr: str, code: str
) -> None:
    install_fake_az(tmp_path, monkeypatch, {"repos pr show": reply(exit=1, stderr=stderr)})
    with pytest.raises(ProviderError) as info:
        _provider(tmp_path, []).status(PR)
    assert info.value.code == code


# -- create_pr --------------------------------------------------------------


def test_create_pr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(tmp_path, monkeypatch, {"repos pr create": show()})
    pr = _provider(tmp_path, []).create_pr("factory/T01-1", "T01: title", "the body")
    assert pr == PullRequest(
        id="7",
        url=f"{WEB_URL}/pullrequest/7",
        branch="factory/T01-1",
        base="main",
        title="T01: title",
    )
    (call,) = [c for c in log.calls() if call_key(c["argv"]) == "repos pr create"]
    assert call["argv"] == [
        "repos",
        "pr",
        "create",
        "--org",
        ORG_URL,
        "--project",
        "Fab Rikam",
        "--repository",
        "app",
        "--source-branch",
        "factory/T01-1",
        "--target-branch",
        "main",
        "--title",
        "T01: title",
        "--description",
        "the body",
        *TAIL,
    ]
    assert Path(call["cwd"]).resolve() == tmp_path.resolve()


def test_update_pr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(tmp_path, monkeypatch, {"repos pr update": show()})
    _provider(tmp_path, []).update_pr(PR, "line one\nline two")
    assert _calls(log, "repos pr update") == [
        [
            "repos",
            "pr",
            "update",
            "--id",
            "7",
            "--org",
            ORG_URL,
            "--description",
            "line one",
            "line two",
            *TAIL,
        ]
    ]


def test_create_pr_description_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(tmp_path, monkeypatch, {"repos pr create": show()})
    provider = _provider(tmp_path, [])
    provider.create_pr("factory/T01-1", "T01", "# Title\n\n- item one\n---\n-x\nend")
    (argv,) = _calls(log, "repos pr create")
    start = argv.index("--description") + 1
    assert argv[start : argv.index("--detect")] == [
        "# Title",
        "",
        "- item one",
        " ---",
        " -x",
        "end",
    ]

    log.clear()
    provider.create_pr("factory/T01-1", "T01", "")
    (argv,) = _calls(log, "repos pr create")
    assert "--description" not in argv


def test_create_pr_url_without_web_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_az(tmp_path, monkeypatch, {"repos pr create": show(id=12, web_url=None)})
    pr = _provider(tmp_path, []).create_pr("factory/T01-1", "T01", "body")
    assert pr.id == "12"
    assert pr.url == f"{ORG_URL}/Fab%20Rikam/_git/app/pullrequest/12"


@pytest.mark.parametrize(
    "answer",
    [reply({"status": "active"}), reply("not json"), reply([1, 2])],
)
def test_create_pr_bad_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: dict[str, Any]
) -> None:
    install_fake_az(tmp_path, monkeypatch, {"repos pr create": answer})
    with pytest.raises(ProviderError) as info:
        _provider(tmp_path, []).create_pr("factory/T01-1", "T01", "body")
    assert info.value.code == "az_failed"


def test_create_pr_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_az(
        tmp_path,
        monkeypatch,
        {"repos pr create": reply(exit=1, stderr="TF401179: An active pull request exists.")},
    )
    with pytest.raises(ProviderError) as info:
        _provider(tmp_path, []).create_pr("factory/T01-1", "T01", "body")
    assert info.value.code == "az_failed"
    assert "TF401179" in info.value.message


# -- status -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "state", "mergeability", "merge_sha"),
    [
        (show(merge_status="succeeded"), OPEN, MERGEABLE, None),
        (show(merge_status="conflicts"), OPEN, CONFLICT, None),
        (show(status="completed", merge=MERGE_SHA), MERGED, UNKNOWN, MERGE_SHA),
        (show(status="abandoned", merge_status="notSet"), CLOSED, UNKNOWN, None),
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
    log = install_fake_az(tmp_path, monkeypatch, {"repos pr show": answer})
    sleeps: list[float] = []
    status = _provider(tmp_path, sleeps).status(PR)
    assert (status.state, status.mergeability) == (state, mergeability)
    assert status.head_sha == HEAD
    assert status.merge_sha == merge_sha
    assert _calls(log, "repos pr show") == [
        ["repos", "pr", "show", "--id", "7", "--org", ORG_URL, *TAIL]
    ]
    assert sleeps == []


def test_status_retries_queued(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(
        tmp_path,
        monkeypatch,
        {"repos pr show": [show(merge_status="queued"), show(merge_status="succeeded")]},
    )
    sleeps: list[float] = []
    status = _provider(tmp_path, sleeps).status(PR)
    assert (status.state, status.mergeability) == (OPEN, MERGEABLE)
    assert len(_calls(log, "repos pr show")) == 2
    assert sleeps == [DELAY]


def test_status_unknown_runs_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(tmp_path, monkeypatch, {"repos pr show": show(merge_status="notSet")})
    sleeps: list[float] = []
    status = _provider(tmp_path, sleeps, attempts=3).status(PR)
    assert (status.state, status.mergeability) == (OPEN, UNKNOWN)
    assert len(_calls(log, "repos pr show")) == 3
    assert sleeps == [DELAY, DELAY]


def test_status_queued_then_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_az(
        tmp_path,
        monkeypatch,
        {"repos pr show": [show(merge_status="queued"), show(merge_status="conflicts")]},
    )
    sleeps: list[float] = []
    status = _provider(tmp_path, sleeps).status(PR)
    assert (status.state, status.mergeability) == (OPEN, CONFLICT)
    assert sleeps == [DELAY]


def test_status_not_an_object(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_az(tmp_path, monkeypatch, {"repos pr show": reply([])})
    with pytest.raises(ProviderError) as info:
        _provider(tmp_path, []).status(PR)
    assert info.value.code == "az_failed"


# -- merge ------------------------------------------------------------------


def _update_argv(squash: str, subject: str) -> list[str]:
    return [
        "repos",
        "pr",
        "update",
        "--id",
        "7",
        "--org",
        ORG_URL,
        "--status",
        "completed",
        "--squash",
        squash,
        "--merge-commit-message",
        subject,
        "--delete-source-branch",
        "false",
        *TAIL,
    ]


def test_merge_default_squash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(
        tmp_path,
        monkeypatch,
        {"repos pr show": show(), "repos pr update": show(status="completed", merge=MERGE_SHA)},
    )
    assert _provider(tmp_path, []).merge(PR, HEAD, "T01: subject") == MERGE_SHA
    assert _calls(log, "repos pr update") == [_update_argv("true", "T01: subject")]


def test_merge_strategy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    responses: dict[str, Any] = {
        "repos pr show": show(),
        "repos pr update": show(status="completed", merge=MERGE_SHA),
    }
    log = install_fake_az(tmp_path, monkeypatch, responses)
    provider = _provider(tmp_path, [], merge_strategy="merge")
    provider.merge(PR, HEAD, "T01")
    assert _calls(log, "repos pr update") == [_update_argv("false", "T01")]

    log.clear()
    provider.merge(PR, HEAD, "T01", strategy="squash")
    assert _calls(log, "repos pr update") == [_update_argv("true", "T01")]


def test_merge_invalid_strategy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(tmp_path, monkeypatch)
    with pytest.raises(ProviderError) as info:
        _provider(tmp_path, []).merge(PR, HEAD, "T01", strategy="rebase")
    assert info.value.code == "invalid_strategy"
    assert log.calls() == []


def test_merge_already_merged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(
        tmp_path, monkeypatch, {"repos pr show": show(status="completed", merge=MERGE_SHA)}
    )
    assert _provider(tmp_path, []).merge(PR, HEAD, "T01") == MERGE_SHA
    assert _calls(log, "repos pr update") == []


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        (show(status="abandoned"), "merge_failed"),
        (show(merge_status="conflicts"), "conflict"),
        (show(head="d" * 40), "merge_failed"),
    ],
)
def test_merge_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: dict[str, Any], code: str
) -> None:
    log = install_fake_az(tmp_path, monkeypatch, {"repos pr show": answer})
    with pytest.raises(MergeFailed) as info:
        _provider(tmp_path, []).merge(PR, HEAD, "T01")
    assert info.value.code == code
    assert _calls(log, "repos pr update") == []


def test_merge_head_moved_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_az(tmp_path, monkeypatch, {"repos pr show": show(head="d" * 40)})
    with pytest.raises(MergeFailed) as info:
        _provider(tmp_path, []).merge(PR, HEAD, "T01")
    assert "moved" in info.value.message


def test_merge_failure_turns_out_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_az(
        tmp_path,
        monkeypatch,
        {
            "repos pr show": [show(), show(merge_status="conflicts")],
            "repos pr update": reply(exit=1, stderr="TF401181: merge conflicts"),
        },
    )
    with pytest.raises(MergeFailed) as info:
        _provider(tmp_path, []).merge(PR, HEAD, "T01")
    assert info.value.code == "conflict"


def test_merge_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_az(
        tmp_path,
        monkeypatch,
        {
            "repos pr show": show(),
            "repos pr update": reply(exit=1, stderr="TF401027: policy rejected"),
        },
    )
    with pytest.raises(MergeFailed) as info:
        _provider(tmp_path, []).merge(PR, HEAD, "T01")
    assert info.value.code == "merge_failed"
    assert "TF401027" in info.value.message


def test_merge_not_logged_in_is_not_wrapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_az(
        tmp_path,
        monkeypatch,
        {
            "repos pr show": show(),
            "repos pr update": reply(exit=1, stderr="Please run 'az login' to setup account."),
        },
    )
    with pytest.raises(ProviderError) as info:
        _provider(tmp_path, []).merge(PR, HEAD, "T01")
    assert not isinstance(info.value, MergeFailed)
    assert info.value.code == "az_not_logged_in"


def test_merge_completes_asynchronously(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_az(
        tmp_path,
        monkeypatch,
        {
            "repos pr show": [show(), show(), show(status="completed", merge=MERGE_SHA)],
            "repos pr update": show(),
        },
    )
    sleeps: list[float] = []
    assert _provider(tmp_path, sleeps).merge(PR, HEAD, "T01") == MERGE_SHA
    assert sleeps == [DELAY]


def test_merge_never_completes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(
        tmp_path, monkeypatch, {"repos pr show": show(), "repos pr update": show()}
    )
    sleeps: list[float] = []
    with pytest.raises(MergeFailed) as info:
        _provider(tmp_path, sleeps, attempts=3).merge(PR, HEAD, "T01")
    assert info.value.code == "merge_failed"
    assert "not completed" in info.value.message
    assert len(_calls(log, "repos pr show")) == 1 + 3
    assert sleeps == [DELAY, DELAY]


# -- comment ----------------------------------------------------------------


def test_comment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(tmp_path, monkeypatch, {"devops invoke": reply(thread_json())})
    _provider(tmp_path, []).comment(PR, "hello")
    (call,) = [c for c in log.calls() if call_key(c["argv"]) == "devops invoke"]
    argv = call["argv"]
    path = argv[argv.index("--in-file") + 1]
    assert argv == [
        "devops",
        "invoke",
        "--area",
        "git",
        "--resource",
        "pullRequestThreads",
        "--route-parameters",
        "project=Fab Rikam",
        "repositoryId=app",
        "pullRequestId=7",
        "--http-method",
        "POST",
        "--in-file",
        path,
        "--api-version",
        API_VERSION,
        "--org",
        ORG_URL,
        "--output",
        "json",
        "--only-show-errors",
    ]
    assert call["in_file"] == {
        "comments": [{"parentCommentId": 0, "content": "hello", "commentType": 1}],
        "status": 1,
    }
    assert not Path(path).exists()


def test_comment_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(
        tmp_path, monkeypatch, {"devops invoke": reply(exit=1, stderr="TF401180: not found")}
    )
    with pytest.raises(ProviderError) as info:
        _provider(tmp_path, []).comment(PR, "hello")
    assert info.value.code == "az_failed"
    (call,) = [c for c in log.calls() if call_key(c["argv"]) == "devops invoke"]
    assert not Path(call["argv"][call["argv"].index("--in-file") + 1]).exists()


# -- approval ---------------------------------------------------------------


def test_approve_vote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(tmp_path, monkeypatch, {"repos pr show": show()})
    assert _provider(tmp_path, []).approve(PR, HEAD) is True
    assert _calls(log, "repos pr set-vote") == [
        ["repos", "pr", "set-vote", "--id", "7", "--vote", "approve", "--org", ORG_URL, *TAIL]
    ]
    assert len(_calls(log, "repos pr show")) == 2


@pytest.mark.parametrize("head", ["d" * 40, None])
def test_approve_wrong_head_no_vote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, head: str | None
) -> None:
    log = install_fake_az(tmp_path, monkeypatch, {"repos pr show": show(head=head)})
    with pytest.raises(ProviderError, match="approval head changed"):
        _provider(tmp_path, []).approve(PR, HEAD)
    assert _calls(log, "repos pr set-vote") == []


def test_approve_head_moves_during_vote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = install_fake_az(tmp_path, monkeypatch, {"repos pr show": [show(), show(head="d" * 40)]})
    with pytest.raises(ProviderError, match="merge stopped"):
        _provider(tmp_path, []).approve(PR, HEAD)
    assert len(_calls(log, "repos pr set-vote")) == 1


def test_approve_vote_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_az(
        tmp_path,
        monkeypatch,
        {
            "repos pr show": show(),
            "repos pr set-vote": reply(exit=1, stderr="permission denied"),
        },
    )
    with pytest.raises(ProviderError) as info:
        _provider(tmp_path, []).approve(PR, HEAD)
    assert info.value.code == "approve_failed"
    assert "permission denied" in info.value.message


@pytest.mark.parametrize("state", ["completed", "abandoned"])
def test_approve_closed_pr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str) -> None:
    log = install_fake_az(tmp_path, monkeypatch, {"repos pr show": show(status=state)})
    provider = _provider(tmp_path, [])
    if state == "completed":
        assert provider.approve(PR, HEAD) is False
    else:
        with pytest.raises(ProviderError):
            provider.approve(PR, HEAD)
    assert _calls(log, "repos pr set-vote") == []


@pytest.mark.parametrize("found", [False, True])
def test_find_open_pr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, found: bool) -> None:
    entry = {"pullRequestId": 7, "title": "existing", "repository": {"webUrl": WEB_URL}}
    log = install_fake_az(tmp_path, monkeypatch, {"repos pr list": reply([entry] if found else [])})
    provider = _provider(tmp_path, [])
    pr = provider.find_open_pr("factory-config/plan-digest")
    if found:
        assert pr is not None
        assert pr.id == "7" and pr.url == f"{WEB_URL}/pullrequest/7"
        assert pr.branch == "factory-config/plan-digest" and pr.base == "main"
    else:
        assert pr is None
    argv = _calls(log, "repos pr list")[0]
    assert argv[argv.index("--source-branch") + 1] == "factory-config/plan-digest"
    assert argv[argv.index("--target-branch") + 1] == "main"
    assert argv[argv.index("--status") + 1] == "active"
