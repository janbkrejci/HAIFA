"""``plan_init(replace=True)`` (the dashboard's "add repository") and ``uninstall``."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from test_library_install_commit import git, home, make_repo

from aifactory.library.install import GITIGNORE_LINES
from aifactory.library.install_commit import commit_init, plan_init
from aifactory.library.uninstall import plan_uninstall, uninstall

__all__ = ["home"]

OWN_PROMPT = ".factory/prompts/builder/system.md"


def commit_push(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    git(root, "push", "-q", "origin", "main")
    return git(root, "rev-parse", "HEAD")


def tree(root: Path, ref: str = "HEAD") -> set[str]:
    return set(git(root, "ls-tree", "-r", "--name-only", ref).splitlines())


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def config(root: Path, ref: str = "HEAD") -> dict[str, object]:
    data = yaml.safe_load(git(root, "show", f"{ref}:.factory/config.yaml"))
    assert isinstance(data, dict)
    return data


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


@pytest.fixture
def installed(repo: Path) -> Path:
    result = commit_init(repo)
    assert result.committed and result.pushed
    return repo


# ── plan_init(replace=True) ──────────────────────────────────────────────────


def test_replace_keeps_an_installed_repo_as_it_is(installed: Path) -> None:
    repo = installed
    write(repo, OWN_PROMPT, "our builder\n")
    text = (repo / ".factory/config.yaml").read_text(encoding="utf-8")
    write(repo, ".factory/config.yaml", text.replace("docs_root: factory\n", "docs_root: work\n"))
    commit_push(repo, "own folder and an own prompt")
    assert [b.code for b in plan_init(repo).blockers] == ["already_installed"]
    head = git(repo, "rev-parse", "HEAD")

    plan = plan_init(repo, replace=True)

    assert plan.blockers == () and plan.publish.files == ()
    result = commit_init(repo, replace=True)
    assert result.committed is False
    assert git(repo, "rev-parse", "HEAD") == head
    assert OWN_PROMPT in tree(repo) and config(repo)["docs_root"] == "work"


def test_replace_adds_only_the_missing_gitignore_lines(installed: Path) -> None:
    repo = installed
    write(repo, ".gitignore", "node_modules/\n")
    commit_push(repo, "lose the factory lines")

    result = commit_init(repo, replace=True)

    assert result.committed and result.pushed
    assert [f.path for f in result.plan.publish.files] == [".gitignore"]
    lines = git(repo, "show", "HEAD:.gitignore").splitlines()
    assert lines == ["node_modules/", *GITIGNORE_LINES]


def test_replace_installs_config_into_a_repo_without_it(repo: Path) -> None:
    result = commit_init(repo, replace=True)
    assert result.committed
    paths = {f.path for f in result.plan.publish.files}
    assert paths == {".factory/config.yaml", ".gitignore", "factory/backlog/.gitkeep"}


# ── uninstall ────────────────────────────────────────────────────────────────


def test_uninstall_commits_the_removal_and_pushes(installed: Path) -> None:
    repo = installed
    assert (repo / ".gitignore").read_text(encoding="utf-8").split() == list(GITIGNORE_LINES)
    write(repo, ".factory/local.yaml", "max_parallel_runs: 1\n")  # ignored: not committed
    write(repo, ".factory/worktrees/r-1/file", "left over")
    head = git(repo, "rev-parse", "HEAD")
    plan = plan_uninstall(repo)
    assert plan.publish.blockers == ()
    actions = {f.path: f.action for f in plan.publish.files}
    assert actions[".gitignore"] == "delete"  # only factory's lines were there
    assert all(a == "delete" for a in actions.values())
    assert {p for p in actions if p.startswith(".factory/")} == {
        p for p in tree(repo) if p.startswith(".factory/")
    }
    assert git(repo, "rev-parse", "HEAD") == head

    result = uninstall(repo)
    assert result.committed and result.pushed
    assert result.commit == git(repo, "rev-parse", "HEAD") == git(repo, "rev-parse", "origin/main")
    assert git(repo, "rev-parse", "HEAD~1") == head
    assert git(repo, "log", "-1", "--format=%s") == "factory: remove factory from this repository"
    assert tree(repo) == {"README.md", "justfile", "factory/backlog/.gitkeep"}  # the backlog stays
    assert not (repo / ".factory").exists() and not (repo / ".gitignore").exists()
    assert git(repo, "status", "--porcelain") == ""


def test_uninstall_keeps_other_gitignore_lines(repo: Path) -> None:
    write(repo, ".gitignore", "node_modules/\n")
    commit_push(repo, "ignore")
    commit_init(repo)
    assert "node_modules/" in (repo / ".gitignore").read_text(encoding="utf-8")
    plan = plan_uninstall(repo)
    assert {f.path: f.action for f in plan.publish.files}[".gitignore"] == "modify"
    uninstall(repo)
    assert git(repo, "show", "HEAD:.gitignore") == "node_modules/"
    assert (repo / ".gitignore").read_text(encoding="utf-8") == "node_modules/\n"


def test_uninstall_without_factory_commits_nothing(repo: Path) -> None:
    head = git(repo, "rev-parse", "HEAD")
    result = uninstall(repo)
    assert result.committed is False
    assert git(repo, "rev-parse", "HEAD") == head
