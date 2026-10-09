"""``library.detect``: provider from the remote URL, base and harness CLIs (HAIFA-S01-T12)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aifactory.library.detect import RemoteInfo, detect, parse_remote_url
from fake_exe import make_executable


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return proc.stdout.strip()


def _gh(owner: str, repo: str) -> RemoteInfo:
    return RemoteInfo("github", github={"owner": owner, "repo": repo})


def _az(org: str, project: str, repo: str) -> RemoteInfo:
    return RemoteInfo("azure", azure={"organization": org, "project": project, "repository": repo})


LOCAL = RemoteInfo("local")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/acme/widgets.git", _gh("acme", "widgets")),
        ("https://github.com/acme/widgets", _gh("acme", "widgets")),
        ("https://github.com/acme/widgets/", _gh("acme", "widgets")),
        ("https://user:token@github.com/acme/widgets.git", _gh("acme", "widgets")),
        ("ssh://git@github.com/acme/widgets.git", _gh("acme", "widgets")),
        ("git@github.com:acme/widgets.git", _gh("acme", "widgets")),
        ("git@github.com:acme/widgets", _gh("acme", "widgets")),
        ("https://dev.azure.com/contoso/Proj/_git/repo", _az("contoso", "Proj", "repo")),
        ("https://contoso@dev.azure.com/contoso/Proj/_git/repo", _az("contoso", "Proj", "repo")),
        (
            "https://dev.azure.com/contoso/My%20Project/_git/my-repo",
            _az("contoso", "My Project", "my-repo"),
        ),
        ("git@ssh.dev.azure.com:v3/contoso/Proj/repo", _az("contoso", "Proj", "repo")),
        ("ssh://git@ssh.dev.azure.com/v3/contoso/Proj/repo", _az("contoso", "Proj", "repo")),
        ("https://contoso.visualstudio.com/Proj/_git/repo", _az("contoso", "Proj", "repo")),
        (
            "https://contoso.visualstudio.com/DefaultCollection/Proj/_git/repo",
            _az("contoso", "Proj", "repo"),
        ),
        ("contoso@vs-ssh.visualstudio.com:v3/contoso/Proj/repo", _az("contoso", "Proj", "repo")),
        (
            "ssh://contoso@vs-ssh.visualstudio.com/v3/contoso/Proj/repo",
            _az("contoso", "Proj", "repo"),
        ),
        ("https://gitlab.com/acme/widgets.git", LOCAL),
        ("git@gitlab.com:acme/widgets.git", LOCAL),
        ("https://github.com/acme", LOCAL),
        ("https://dev.azure.com/contoso/Proj", LOCAL),
        ("/srv/git/origin.git", LOCAL),
        ("../origin.git", LOCAL),
        ("file:///srv/git/origin.git", LOCAL),
        ("", LOCAL),
        (None, LOCAL),
    ],
)
def test_parse_remote_url(url: str | None, expected: RemoteInfo) -> None:
    assert parse_remote_url(url) == expected


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q", "-b", "trunk")
    _git(
        path,
        "-c",
        "user.name=T",
        "-c",
        "user.email=t@e",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "i",
    )
    return path


def test_detect_without_remote(repo: Path) -> None:
    found = detect(repo)
    assert found.remote is None and found.remote_url is None
    assert (found.base, found.base_source) == ("trunk", "branch")
    assert found.provider == "local"


def test_detect_base_from_remote_head(repo: Path, tmp_path: Path) -> None:
    bare = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-q", "origin", "trunk:main", "trunk:dev")
    _git(repo, "fetch", "-q", "origin")
    _git(repo, "remote", "set-head", "origin", "dev")

    found = detect(repo)

    assert (found.remote, found.base, found.base_source) == ("origin", "dev", "remote_head")
    assert found.to_json()["remote_url"] == str(bare)


def test_detect_other_remote_and_redacted_url(repo: Path) -> None:
    _git(repo, "remote", "add", "upstream", "https://u:secret@dev.azure.com/c/P/_git/r")
    found = detect(repo).to_json()
    assert found["remote"] == "upstream"
    assert found["remote_url"] == "https://dev.azure.com/c/P/_git/r"
    assert found["provider"] == "azure"
    assert found["azure"] == {"organization": "c", "project": "P", "repository": "r"}
    assert found["base"] == "trunk"


def test_detect_harnesses(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = tmp_path / "bin" / "claude-fake"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8", newline="\n")
    fake = make_executable(fake)
    monkeypatch.setenv("CLAUDE_CODE_PATH", str(fake))
    monkeypatch.setenv("CODEX_PATH", "codex-not-installed-anywhere")
    monkeypatch.setenv("PI_PATH", "pi-not-installed-anywhere")

    harnesses = detect(repo).to_json()["harnesses"]

    assert harnesses["claude"] == {"installed": True, "path": str(fake)}
    assert harnesses["codex"] == {"installed": False, "path": None}
    assert harnesses["pi"]["installed"] is False
