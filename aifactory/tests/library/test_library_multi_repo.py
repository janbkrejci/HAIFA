"""Registered repository operations with three repos and local bare remotes."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from test_library_config_edit import _claim
from test_library_update import (
    LIB_SYSTEM,
    SKILL_MD,
    SYSTEM,
    Capsys,
    advance_library,
    commit_all,
    git,
    home,  # noqa: F401 - shared fixture
    lib,
    make_repo,
    repo,  # noqa: F401 - shared fixture
    write,
)

from aifactory.home import haifa_home
from cli_json import run_json


@pytest.fixture
def three(repo: Path, tmp_path: Path, capsys: Capsys) -> list[Path]:  # noqa: F811
    paths = [repo]
    for name in ("second", "third"):
        path = make_repo(tmp_path, name)
        rc, env = run_json(capsys, ["init", "--repo", str(path), "--commit", "--json"])
        assert rc == 0, env
        paths.append(path)
    registry = {
        "version": 1,
        "repos": [
            {
                "id": path.name,
                "name": path.name,
                "path": str(path),
                "added_at": "2026-10-07T00:00:00Z",
            }
            for path in paths
        ],
    }
    (haifa_home() / "dashboard.yaml").write_text(yaml.safe_dump(registry), encoding="utf-8")
    return paths


def multi(capsys: Capsys, *args: str) -> dict[str, Any]:
    rc, env = run_json(capsys, [*args, "--json"])
    assert rc == 0, env
    data: dict[str, Any] = env["data"]
    return data


def test_add_skill_to_builder_and_repeat(three: list[Path], capsys: Capsys) -> None:
    write(lib(), "skills/lint/SKILL.md", SKILL_MD)
    commit_all(lib(), "add lint")
    args = ("config", "add", "skill", "lint", "--agent", "builder", "--repos", "all")
    preview = multi(capsys, *args, "--dry-run", "--commit")
    assert all(row["plan"]["changed"] for row in preview["repos"])
    assert all(not (path / ".claude/skills/lint").exists() for path in three)
    expects = [
        part
        for row in preview["repos"]
        for part in ("--expect", f"{row['repo']['id']}={row['plan']['digest']}")
    ]
    result = multi(capsys, *args, "--commit", *expects)
    assert not result["partial"]
    for path, row in zip(three, result["repos"], strict=True):
        assert row["result"]["committed"] and row["result"]["pushed"]
        roster = yaml.safe_load((path / ".factory/agents.yaml").read_text())
        builder = next(agent for agent in roster["agents"] if agent["name"] == "builder")
        assert builder["skills"].count("lint") == 1
        assert (path / ".agents/skills/lint/SKILL.md").read_text() == SKILL_MD
    again = multi(capsys, *args, "--commit")
    assert all(not row["result"]["changed"] for row in again["repos"])


def test_where_states_alias_and_missing(three: list[Path], capsys: Capsys) -> None:
    multi(
        capsys, "config", "add", "agent", "builder", "--as", "other", "--repos", "repo", "--commit"
    )
    write(three[1], SYSTEM, "local builder\n")
    (three[2] / SYSTEM).unlink()
    rows = multi(capsys, "library", "where", "agent", "builder")["repos"]
    assert [(row["repo"]["id"], row["slot"], row["state"]) for row in rows] == [
        ("repo", "builder", "synced"),
        ("repo", "other", "synced"),
        ("second", "builder", "modified"),
        ("third", "builder", "missing"),
    ]
    advance_library(LIB_SYSTEM, "new library\n")
    rows = multi(capsys, "library", "where", "agent", "builder")["repos"]
    assert [row["state"] for row in rows] == ["outdated", "outdated", "diverged", "missing"]
    shutil.rmtree(three[2])
    rows = multi(capsys, "library", "where", "agent", "builder")["repos"]
    assert rows[-1]["state"] == "repo_missing"
    result = multi(capsys, "update", "--repos", "all", "--commit")
    assert result["repos"][-1]["status"] == "repo_missing"
    assert result["repos"][0]["status"] == "ok"


def test_update_continues_after_run_and_rejected_push(
    three: list[Path], tmp_path: Path, capsys: Capsys
) -> None:
    advance_library(LIB_SYSTEM, "updated builder\n")
    _claim(three[0], os.getpid())
    hook = tmp_path / "second-origin.git/hooks/pre-receive"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    before = [git(path, "rev-parse", "main") for path in three]
    data = multi(capsys, "update", "--repos", "all", "--item", "agent/builder", "--commit")
    assert [row["status"] for row in data["repos"]] == ["run_in_progress", "push_failed", "ok"]
    assert data["partial"]
    assert [git(path, "rev-parse", "main") for path in three[:2]] == before[:2]
    assert (three[2] / SYSTEM).read_text() == "updated builder\n"
    hook.unlink()
    retry = multi(capsys, "update", "--repos", "all", "--commit")
    assert [row["status"] for row in retry["repos"]] == ["run_in_progress", "ok", "ok"]
    assert not retry["repos"][2]["result"]["changed"]


def test_expect_is_per_repo(three: list[Path], capsys: Capsys) -> None:
    advance_library(LIB_SYSTEM, "updated builder\n")
    args = ("update", "--repos", "all", "--commit")
    preview = multi(capsys, *args, "--dry-run")
    expects = [
        part
        for row in preview["repos"]
        for part in (
            "--expect",
            f"{row['repo']['id']}="
            + (row["plan"]["digest"] if row["repo"]["id"] != "second" else "0" * 64),
        )
    ]
    data = multi(capsys, *args, *expects)
    assert [row["status"] for row in data["repos"]] == ["ok", "plan_changed", "ok"]
    assert (three[1] / SYSTEM).read_text() != "updated builder\n"
    rc, env = run_json(capsys, [*args, "--expect", "repo=abc", "--json"])
    assert rc == 2 and env["error"]["code"] == "conflicting_options"


def test_registry_required_and_options(capsys: Capsys) -> None:
    for args in (
        ["update", "--repos", "all"],
        ["config", "add", "skill", "lint", "--repos", "all"],
        ["library", "where", "agent", "builder"],
    ):
        rc, env = run_json(capsys, [*args, "--json"])
        assert rc == 2 and env["error"]["code"] == "registry_missing"


def test_item_filter_keeps_other_items(three: list[Path], capsys: Capsys) -> None:
    advance_library(LIB_SYSTEM, "new builder\n")
    data = multi(capsys, "update", "--repos", "all", "--item", "agent/tester", "--commit")
    assert all(row["status"] == "ok" for row in data["repos"])
    assert all((path / SYSTEM).read_text() != "new builder\n" for path in three)


def test_bind_existing_skill_and_dirty_repo(three: list[Path], capsys: Capsys) -> None:
    write(lib(), "skills/lint/SKILL.md", SKILL_MD)
    commit_all(lib(), "add lint")
    multi(capsys, "config", "add", "skill", "lint", "--repos", "all", "--commit")
    agent_file = three[1] / ".factory/agents.yaml"
    agent_file.write_text(agent_file.read_text() + "# local edit\n")
    args = ("config", "add", "skill", "lint", "--agent", "builder", "--repos", "all", "--commit")
    result = multi(capsys, *args)
    assert [row["status"] for row in result["repos"]] == ["ok", "dirty_paths", "ok"]
    for path in (three[0], three[2]):
        agents = yaml.safe_load((path / ".factory/agents.yaml").read_text())["agents"]
        assert next(agent for agent in agents if agent["name"] == "builder")["skills"] == ["lint"]
    again = multi(capsys, *args)
    assert not again["repos"][0]["result"]["changed"]


def test_invalid_registry_and_unknown_selection(three: list[Path], capsys: Capsys) -> None:
    rc, env = run_json(capsys, ["update", "--repos", "unregistered", "--json"])
    assert rc == 2 and env["error"]["code"] == "unknown_repo"
    (haifa_home() / "dashboard.yaml").write_text("repos: [broken]\n")
    rc, env = run_json(capsys, ["update", "--repos", "all", "--json"])
    assert rc == 2 and env["error"]["code"] == "registry_invalid"


def test_where_local_and_unknown(three: list[Path], capsys: Capsys) -> None:
    from aifactory.config.manifest import MANIFEST_FILE

    for path, action in ((three[0], "local"), (three[1], "unknown")):
        file = path / MANIFEST_FILE
        manifest = yaml.safe_load(file.read_text())
        if action == "local":
            del manifest["items"]["agents"]["builder"]
        else:
            manifest["items"]["agents"]["builder"]["version"] = "sha256:" + "0" * 64
            write(path, SYSTEM, "changed locally\n")
        file.write_text(yaml.safe_dump(manifest))
    rows = multi(capsys, "library", "where", "agent", "builder")["repos"]
    assert [row["state"] for row in rows] == ["local", "unknown", "synced"]


@pytest.fixture
def pr_provider(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[Path, str], Any]:
    """Hosting stub: real pushes to local bare remotes, in-memory open PRs."""
    from aifactory import providers
    from aifactory.config.settings import ProjectSettings
    from aifactory.providers.base import PullRequest
    from aifactory.providers.local import LocalProvider

    opened: dict[tuple[Path, str], Any] = {}

    class StubProvider(LocalProvider):
        def find_open_pr(self, branch: str) -> PullRequest | None:
            value = opened.get((self.root, branch))
            return value if isinstance(value, PullRequest) else None

        def create_pr(self, branch: str, title: str, body: str) -> PullRequest:
            key = (self.root, branch)
            assert key not in opened, "created a duplicate PR"
            pr = PullRequest(
                str(len(opened) + 1),
                f"stub://pr/{len(opened) + 1}",
                branch,
                self.settings.base,
                title,
            )
            opened[key] = pr
            return pr

    def provider(settings: ProjectSettings, root: Path) -> StubProvider:
        return StubProvider(root, settings)

    monkeypatch.setattr(providers, "get_provider", provider)
    return opened


@pytest.mark.parametrize("operation", ["add", "update"])
@pytest.mark.parametrize("partial", [False, True])
def test_pr_repeat_reuses_published_plan(
    three: list[Path],
    tmp_path: Path,
    capsys: Capsys,
    pr_provider: dict[tuple[Path, str], Any],
    operation: str,
    partial: bool,
) -> None:
    args: tuple[str, ...]
    if operation == "add":
        write(lib(), "skills/lint/SKILL.md", SKILL_MD)
        commit_all(lib(), "add lint")
        args = ("config", "add", "skill", "lint", "--agent", "builder")
    else:
        advance_library(LIB_SYSTEM, "new builder\n")
        args = ("update", "--item", "agent/builder")
    args = (*args, "--repos", "all", "--commit", "--pr")
    before = [git(path, "rev-parse", "main") for path in three]
    hook = tmp_path / "second-origin.git/hooks/pre-receive"
    if partial:
        hook.parent.mkdir(exist_ok=True)
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
    preview = multi(capsys, *args, "--dry-run")
    assert not pr_provider
    expects = [
        part
        for row in preview["repos"]
        for part in ("--expect", f"{row['repo']['id']}={row['plan']['digest']}")
    ]
    first = multi(capsys, *args, *expects)
    assert [row["status"] for row in first["repos"]] == [
        "ok",
        "push_failed" if partial else "ok",
        "ok",
    ]
    assert len(pr_provider) == (2 if partial else 3)
    if partial:
        hook.unlink()
    retry = multi(capsys, *args, *expects, "-m", "retry the same contents")
    assert not retry["partial"]
    assert len(pr_provider) == 3
    for original, repeated in zip(first["repos"], retry["repos"], strict=True):
        if original["status"] == "ok":
            assert repeated["result"]["commit"] == original["result"]["commit"]
            assert repeated["result"]["branch"] == original["result"]["branch"]
            assert repeated["result"]["pr"] == original["result"]["pr"]
    refs = [git(path, "for-each-ref", "--format=%(refname) %(objectname)") for path in three]
    third = multi(capsys, *args)
    assert not third["partial"] and len(pr_provider) == 3
    assert [
        git(path, "for-each-ref", "--format=%(refname) %(objectname)") for path in three
    ] == refs
    assert [git(path, "rev-parse", "main") for path in three] == before
    for path, row in zip(three, third["repos"], strict=True):
        branch = row["result"]["branch"]
        assert (
            git(tmp_path / f"{path.name}-origin.git", "rev-parse", branch)
            == row["result"]["commit"]
        )
        assert git(path, "status", "--porcelain") == ""


def test_pr_recovery_from_remote_and_edited_branch(
    three: list[Path],
    capsys: Capsys,
    pr_provider: dict[tuple[Path, str], Any],
) -> None:
    advance_library(LIB_SYSTEM, "new builder\n")
    args = ("update", "--repos", "all", "--commit", "--pr")
    first = multi(capsys, *args)
    branch = first["repos"][0]["result"]["branch"]
    git(three[0], "update-ref", "-d", f"refs/heads/{branch}")
    recovered = multi(capsys, *args)
    assert recovered["repos"][0]["result"]["commit"] == first["repos"][0]["result"]["commit"]
    assert recovered["repos"][0]["result"]["pr"] == first["repos"][0]["result"]["pr"]
    assert len(pr_provider) == 3
    git(three[0], "update-ref", f"refs/heads/{branch}", git(three[0], "rev-parse", "main"))
    changed = multi(capsys, *args)
    assert [row["status"] for row in changed["repos"]] == ["plan_changed", "ok", "ok"]
    assert len(pr_provider) == 3


def test_pr_retry_after_host_creation_failure(
    three: list[Path],
    capsys: Capsys,
    monkeypatch: pytest.MonkeyPatch,
    pr_provider: dict[tuple[Path, str], Any],
) -> None:
    from aifactory import providers
    from aifactory.library.config_edit import read_state
    from aifactory.providers.base import GitProvider, ProviderError, PullRequest

    cls = type(providers.get_provider(read_state(three[0], "base").settings, three[0]))
    create = cls.create_pr
    failed = False

    def fail_once(self: GitProvider, branch: str, title: str, body: str) -> PullRequest:
        nonlocal failed
        if self.root == three[1] and not failed:
            failed = True
            raise ProviderError("pr_failed", "stub hosting unavailable")
        return create(self, branch, title, body)

    monkeypatch.setattr(cls, "create_pr", fail_once)
    advance_library(LIB_SYSTEM, "new builder\n")
    args = ("update", "--repos", "all", "--commit", "--pr")
    first = multi(capsys, *args)
    assert [row["status"] for row in first["repos"]] == ["ok", "pr_failed", "ok"]
    refs = git(three[1], "for-each-ref", "--format=%(refname) %(objectname)")
    retry = multi(capsys, *args)
    assert not retry["partial"] and len(pr_provider) == 3
    assert git(three[1], "for-each-ref", "--format=%(refname) %(objectname)") == refs
    for i in (0, 2):
        assert retry["repos"][i]["result"]["pr"] == first["repos"][i]["result"]["pr"]
