"""``plan_init(replace=True)`` (install over an existing ``.factory/``) and ``uninstall``."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from test_library_install_commit import git, home, make_repo

from aifactory.library import store
from aifactory.library.install import GITIGNORE_LINES
from aifactory.library.install_commit import commit_init, plan_init
from aifactory.library.uninstall import plan_uninstall, uninstall

__all__ = ["home"]

STALE = ".factory/prompts/retired/system.md"
BUILDER_PROMPT = ".factory/prompts/builder/system.md"


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


def test_replace_installs_over_an_installed_repo(installed: Path) -> None:
    repo = installed
    write(repo, STALE, "retired\n")
    text = (repo / ".factory/config.yaml").read_text(encoding="utf-8")
    write(repo, ".factory/config.yaml", text + "specs_dir: work/specs\n")
    commit_push(repo, "own folder and a retired prompt")
    assert [b.code for b in plan_init(repo).blockers] == ["already_installed"]

    plan = plan_init(repo, replace=True)
    assert plan.blockers == ()
    actions = {f.path: f.action for f in plan.publish.files}
    assert actions[STALE] == "delete"
    head = git(repo, "rev-parse", "HEAD")
    assert git(repo, "rev-parse", "HEAD") == head  # planning writes nothing

    result = commit_init(repo, replace=True)
    assert result.committed and result.pushed
    assert git(repo, "rev-parse", "HEAD~1") == head
    assert git(repo, "rev-parse", "origin/main") == result.commit
    assert STALE not in tree(repo) and not (repo / STALE).exists()
    assert config(repo)["specs_dir"] == "work/specs"  # the old folders are kept
    assert ".factory/manifest.yaml" in tree(repo)


def test_replace_installs_over_a_pre_library_config(repo: Path) -> None:
    write(repo, ".factory/config.yaml", "base: main\nbacklog_dir: tasks\n")
    write(repo, ".factory/agents.yaml", "agents:\n- name: old\n  purpose: Old.\n")
    commit_push(repo, "pre-library config")
    assert plan_init(repo).blockers  # without replace: refused
    result = commit_init(repo, replace=True)
    assert result.committed
    assert config(repo)["backlog_dir"] == "tasks"
    agents = yaml.safe_load(git(repo, "show", "HEAD:.factory/agents.yaml"))
    assert "old" not in {a["name"] for a in agents["agents"]}
    assert "tasks/.gitkeep" in tree(repo)


def test_replace_with_the_same_install_commits_nothing(installed: Path) -> None:
    repo = installed
    head = git(repo, "rev-parse", "HEAD")
    plan = plan_init(repo, replace=True)
    assert plan.blockers == () and plan.publish.files == ()
    result = commit_init(repo, replace=True)
    assert result.committed is False and result.commit is None
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "status", "--porcelain") == ""


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
    assert tree(repo) == {"README.md", "justfile", "backlog/.gitkeep"}  # the backlog stays
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


def test_uninstall_exports_own_items_to_the_library(repo: Path, tmp_path: Path, home: Path) -> None:
    environ = {**os.environ, "HAIFA_HOME": str(home)}
    bare = tmp_path / "library.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    library = Path(store.init_library("team", environ, remote=str(bare)).plan.library)
    commit_init(repo)
    assert plan_uninstall(repo).own_items == []
    prompt = repo / BUILDER_PROMPT
    prompt.write_text(prompt.read_text(encoding="utf-8") + "Repo rule.\n", encoding="utf-8")
    commit_push(repo, "own builder")
    own = plan_uninstall(repo).own_items
    assert [(i["type"], i["name"]) for i in own] == [("agent", "builder")]

    result = uninstall(repo, export=[("agent", "builder")])
    assert result.exported == [{"type": "agent", "name": "builder"}]
    assert result.committed
    exported = (library / "agents/builder/system.md").read_text(encoding="utf-8")
    assert exported.endswith("Repo rule.\n")
    assert not (repo / ".factory").exists()


def test_uninstall_without_factory_commits_nothing(repo: Path) -> None:
    head = git(repo, "rev-parse", "HEAD")
    result = uninstall(repo)
    assert result.committed is False
    assert git(repo, "rev-parse", "HEAD") == head
