"""``factory config export|revert|diff`` with bare remotes of the library and the repo.

No network and no model: the remotes are local bare repositories, the harness CLI a stub.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from aifactory.config.manifest import MANIFEST_FILE
from aifactory.library import store
from cli_json import run_json
from fake_exe import make_executable

Capsys = pytest.CaptureFixture[str]
AGENTS = ".factory/agents.yaml"
SYSTEM = ".factory/prompts/builder/system.md"


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return proc.stdout.strip()


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """``$HAIFA_HOME`` in tmp, a git identity, and only claude on this machine."""
    path = tmp_path / "haifa-home"
    monkeypatch.setenv("HAIFA_HOME", str(path))
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    for kind in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{kind}_NAME", "Ada Tester")
        monkeypatch.setenv(f"GIT_{kind}_EMAIL", "ada@example.com")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    claude = tmp_path / "bin" / "claude"
    claude.parent.mkdir()
    claude.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8", newline="\n")
    claude = make_executable(claude)
    monkeypatch.setenv("CLAUDE_CODE_PATH", str(claude))
    monkeypatch.setenv("CODEX_PATH", "codex-not-installed-anywhere")
    monkeypatch.setenv("PI_PATH", "pi-not-installed-anywhere")
    return path


def make_repo(tmp_path: Path, name: str = "repo") -> Path:
    path = tmp_path / name
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    (path / "README.md").write_text("readme\n", encoding="utf-8", newline="\n")
    (path / "justfile").write_text("test:\n    echo ok\n", encoding="utf-8", newline="\n")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "init")
    bare = tmp_path / f"{name}-origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(path, "remote", "add", "origin", str(bare))
    git(path, "push", "-q", "-u", "origin", "main")
    git(path, "remote", "set-head", "origin", "main")
    return path.resolve()


def library_bare(tmp_path: Path) -> Path:
    return tmp_path / "library-origin.git"


def repo_bare(tmp_path: Path, name: str = "repo") -> Path:
    return tmp_path / f"{name}-origin.git"


def init_repo(capsys: Capsys, tmp_path: Path, name: str = "repo") -> Path:
    path = make_repo(tmp_path, name)
    rc, env = run_json(capsys, ["init", "--repo", str(path), "--commit", "--json"])
    assert rc == 0, env
    return path


@pytest.fixture
def repo(tmp_path: Path, capsys: Capsys) -> Path:
    """A shared library (bare remote) from the seed and a repo installed from it."""
    bare = library_bare(tmp_path)
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    store.init_library("team", remote=str(bare))
    return init_repo(capsys, tmp_path)


def cfg(capsys: Capsys, repo: Path, *args: str) -> tuple[int, Any]:
    return run_json(capsys, ["config", *args, "--repo", str(repo), "--json"])


def ok(capsys: Capsys, repo: Path, *args: str) -> dict[str, Any]:
    rc, env = cfg(capsys, repo, *args)
    assert rc == 0, env
    data: dict[str, Any] = env["data"]
    return data


def fail(capsys: Capsys, repo: Path, code: str, *args: str) -> dict[str, Any]:
    rc, env = cfg(capsys, repo, *args)
    assert rc == 2 and env["error"]["code"] == code, env
    error: dict[str, Any] = {**env["error"], "data": env["data"]}
    return error


def rev(path: Path, ref: str = "main") -> str:
    return git(path, "rev-parse", ref)


def lib() -> Path:
    return store.library_root()


def lib_file(rel: str) -> str:
    return git(lib(), "show", f"HEAD:{rel}")


def manifest(repo: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((repo / MANIFEST_FILE).read_text(encoding="utf-8"))
    return data


def snapshot(repo: Path) -> dict[str, bytes]:
    return {
        p.relative_to(repo).as_posix(): p.read_bytes()
        for p in repo.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(repo).parts
    }


def write(base: Path, rel: str, text: str) -> None:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def commit_all(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    git(repo, "push", "-q", "origin", "main")


def reject_pushes(bare: Path) -> Path:
    hook = bare / "hooks" / "pre-receive"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    return hook


def advance_library(rel: str, text: str) -> None:
    """Another machine changed the library: a commit pushed to its remote."""
    write(lib(), rel, text)
    git(lib(), "add", "-A")
    git(lib(), "commit", "-q", "-m", f"change {rel}")
    git(lib(), "push", "-q", "origin", "main")


def states(capsys: Capsys, repo: Path) -> dict[tuple[str, str], str]:
    data = ok(capsys, repo, "items")
    return {(i["type"], i["name"]): i["state"] for i in data["items"]}


# ── export ────────────────────────────────────────────────────────────────────


def test_export_modified_prompt_and_add_to_other_repo(
    repo: Path, tmp_path: Path, capsys: Capsys
) -> None:
    base = rev(repo)
    lib_head = rev(lib(), "HEAD")
    text = (repo / SYSTEM).read_text(encoding="utf-8") + "Always run the tests.\n"
    write(repo, SYSTEM, text)
    assert states(capsys, repo)[("agent", "builder")] == "modified"

    dry = ok(capsys, repo, "export", "agent", "builder", "--dry-run")
    assert dry["dry_run"] and dry["export"]["action"] == "update"
    assert [f["path"] for f in dry["library_plan"]["files"]] == ["agents/builder/system.md"]
    assert dry["paths"] == [MANIFEST_FILE]
    assert rev(lib(), "HEAD") == lib_head

    data = ok(capsys, repo, "export", "agent", "builder", "--expect", dry["digest"])

    assert data["written"] and data["library_commit"] == rev(lib(), "HEAD") != lib_head
    assert rev(library_bare(tmp_path), "main") == rev(lib(), "HEAD")  # pushed
    assert lib_file("agents/builder/system.md") + "\n" == text
    entry = manifest(repo)["items"]["agents"]["builder"]
    assert entry == {"item": "builder", "version": data["export"]["version"]}
    assert states(capsys, repo)[("agent", "builder")] == "synced"
    assert rev(repo) == base  # working tree only
    # the same export again: nothing to change
    again = ok(capsys, repo, "export", "agent", "builder")
    assert again["changed"] is False and again["export"]["action"] == "connect"

    # another repo takes the exported agent from the library
    other = init_repo(capsys, tmp_path, "other")
    ok(capsys, other, "add", "agent", "builder", "--as", "builder2")
    assert (other / ".factory/prompts/builder2/system.md").read_text(encoding="utf-8") == text
    assert manifest(other)["items"]["agents"]["builder2"]["item"] == "builder"


def test_export_as_new_item(repo: Path, capsys: Capsys) -> None:
    write(repo, ".factory/prompts/builder/user.md", "Build {{prompt}} strictly.\n")

    data = ok(capsys, repo, "export", "agent", "builder", "--as", "builder-strict")

    assert data["export"]["action"] == "create" and data["export"]["item"] == "builder-strict"
    assert lib_file("agents/builder-strict/user.md") == "Build {{prompt}} strictly."
    # defaults come from the library item the slot was connected to
    assert lib_file("agents/builder-strict/agent.yaml") == lib_file("agents/builder/agent.yaml")
    entry = manifest(repo)["items"]["agents"]["builder"]
    assert entry["item"] == "builder-strict"
    # builder itself is unchanged in the library
    assert "strictly" not in lib_file("agents/builder/user.md")
    # a name with other content is refused
    write(repo, ".factory/prompts/reviewer/user.md", "Review it.\n")
    error = fail(capsys, repo, "item_exists", "export", "agent", "reviewer", "--as", "builder")
    assert "--as" in error["data"]["fix"]
    # --as is only for agents and workflows
    fail(capsys, repo, "conflicting_options", "export", "skill", "x", "--as", "y")


def test_export_local_item(repo: Path, capsys: Capsys) -> None:
    raw = yaml.safe_load((repo / AGENTS).read_text(encoding="utf-8"))
    helper = {
        "name": "helper",
        "purpose": "Help with the docs.",
        "harness": "claude",
        "model": "claude-opus-5-5",
        "writes": ["specs/", "README.md"],
    }
    raw["agents"].append(helper)
    (repo / AGENTS).write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    write(repo, ".factory/prompts/helper/system.md", "You help.\n")
    write(repo, ".factory/prompts/helper/user.md", "{{prompt}}\n")
    assert states(capsys, repo)[("agent", "helper")] == "local"

    data = ok(capsys, repo, "export", "agent", "helper")

    assert data["export"]["action"] == "create" and data["export"]["previous_item"] is None
    meta = yaml.safe_load(lib_file("agents/helper/agent.yaml"))
    assert meta["purpose"] == "Help with the docs."
    assert meta["defaults"]["harness"] == "claude"
    assert meta["defaults"]["model"] == "claude-opus-5-5"
    assert meta["defaults"]["writes"] == ["$specs_dir/", "README.md"]
    assert manifest(repo)["items"]["agents"]["helper"]["item"] == "helper"
    assert states(capsys, repo)[("agent", "helper")] == "synced"


def test_library_changed_since(repo: Path, capsys: Capsys) -> None:
    advance_library("agents/builder/system.md", "Library builder v2.\n")
    write(repo, SYSTEM, "Repo builder v2.\n")
    before = snapshot(repo)
    lib_head = rev(lib(), "HEAD")

    error = fail(capsys, repo, "library_changed_since", "export", "agent", "builder")

    assert "factory update" in error["data"]["fix"] and "--as" in error["data"]["fix"]
    assert snapshot(repo) == before
    assert rev(lib(), "HEAD") == lib_head
    # --as is the way out
    data = ok(capsys, repo, "export", "agent", "builder", "--as", "builder-mine")
    assert data["export"]["action"] == "create"


def test_rejected_library_push_leaves_repo(repo: Path, tmp_path: Path, capsys: Capsys) -> None:
    write(repo, SYSTEM, "Repo builder v2.\n")
    commit_all(repo, "builder v2")
    reject_pushes(library_bare(tmp_path))
    before = snapshot(repo)
    base, remote = rev(repo), rev(repo_bare(tmp_path))
    lib_head = rev(lib(), "HEAD")

    for extra in ((), ("--commit",)):
        fail(capsys, repo, "push_failed", "export", "agent", "builder", *extra)

        assert snapshot(repo) == before
        assert rev(repo) == base and rev(repo_bare(tmp_path)) == remote
        assert rev(lib(), "HEAD") == lib_head
        assert rev(library_bare(tmp_path)) == lib_head


def test_rejected_repo_push_then_export_again(repo: Path, tmp_path: Path, capsys: Capsys) -> None:
    write(repo, SYSTEM, "Repo builder v2.\n")
    commit_all(repo, "builder v2")
    hook = reject_pushes(repo_bare(tmp_path))
    base = rev(repo)

    error = fail(capsys, repo, "push_failed", "export", "agent", "builder", "--commit")

    library_commit = error["data"]["library_commit"]
    assert library_commit == rev(lib(), "HEAD") == rev(library_bare(tmp_path))
    assert lib_file("agents/builder/system.md") == "Repo builder v2."
    assert rev(repo) == base  # the repo did not move
    assert "builder" in manifest(repo)["items"]["agents"]

    hook.unlink()
    data = ok(capsys, repo, "export", "agent", "builder", "--commit", "-m", "connect builder")

    assert data["export"]["action"] == "connect" and data["committed"]
    assert data["library_commit"] is None and data["library_plan"] is None
    assert rev(lib(), "HEAD") == library_commit  # no second library version
    assert rev(repo) != base and rev(repo_bare(tmp_path)) == rev(repo)
    assert git(repo, "log", "-1", "--format=%s") == "connect builder"
    entry = manifest(repo)["items"]["agents"]["builder"]
    assert entry["version"] == data["export"]["version"]
    assert git(repo, "status", "--porcelain") == ""


# ── revert ────────────────────────────────────────────────────────────────────


def test_revert_to_manifest_and_head(repo: Path, capsys: Capsys) -> None:
    original = (repo / SYSTEM).read_bytes()
    version = manifest(repo)["items"]["agents"]["builder"]["version"]
    write(repo, SYSTEM, "Changed here.\n")
    write(repo, ".factory/prompts/builder/extra.md", "stray\n")

    data = ok(capsys, repo, "revert", "agent", "builder")

    assert data["revert"]["to"] == "manifest" and data["revert"]["version"] == version
    assert (repo / SYSTEM).read_bytes() == original
    assert not (repo / ".factory/prompts/builder/extra.md").exists()
    assert manifest(repo)["items"]["agents"]["builder"]["version"] == version
    assert ok(capsys, repo, "revert", "agent", "builder")["changed"] is False

    # the library moved on: --to head takes it and moves the manifest version
    advance_library("agents/builder/system.md", "Library builder v2.\n")
    assert ok(capsys, repo, "revert", "agent", "builder", "--dry-run")["changed"] is False
    data = ok(capsys, repo, "revert", "agent", "builder", "--to", "head")
    assert (repo / SYSTEM).read_text(encoding="utf-8") == "Library builder v2.\n"
    assert manifest(repo)["items"]["agents"]["builder"]["version"] == data["revert"]["version"]
    assert data["revert"]["version"] != version
    assert states(capsys, repo)[("agent", "builder")] == "synced"
    # and back to the old manifest version is no longer what the manifest says
    data = ok(capsys, repo, "revert", "agent", "builder")
    assert data["changed"] is False


def test_revert_unknown_and_local(repo: Path, capsys: Capsys) -> None:
    text = (repo / MANIFEST_FILE).read_text(encoding="utf-8")
    version = manifest(repo)["items"]["agents"]["builder"]["version"]
    (repo / MANIFEST_FILE).write_text(
        text.replace(version, "sha256:" + "0" * 64, 1), encoding="utf-8"
    )
    error = fail(capsys, repo, "unknown_version", "revert", "agent", "builder")
    assert error["data"]["state"] == "unknown"
    assert ok(capsys, repo, "revert", "agent", "builder", "--to", "head")["changed"]

    write(repo, ".factory/workflows/mine.yaml", "name: mine\ndescription: x\nsteps: [build]\n")
    fail(capsys, repo, "unknown_item", "revert", "workflow", "mine")


# ── diff ──────────────────────────────────────────────────────────────────────


def test_diff_against_manifest_and_head(repo: Path, capsys: Capsys) -> None:
    text = (repo / SYSTEM).read_text(encoding="utf-8")
    write(repo, SYSTEM, text + "Repo line.\n")
    advance_library("agents/builder/user.md", "Library user v2 {{prompt}}\n")
    before = snapshot(repo)

    data = ok(capsys, repo, "diff", "agent", "builder")

    assert snapshot(repo) == before  # read only
    assert data["state"] == "diverged" and data["item"] == "builder"
    m, h = data["manifest"], data["head"]
    assert m["available"] and m["version"] == data["manifest_version"]
    assert [(f["path"], f["status"]) for f in m["files"]] == [(SYSTEM, "modified")]
    assert "+Repo line." in m["files"][0]["diff"]
    paths = {f["path"]: f for f in h["files"]}
    assert set(paths) == {SYSTEM, ".factory/prompts/builder/user.md"}
    assert "-Library user v2" in paths[".factory/prompts/builder/user.md"]["diff"]
    assert h["version"] == data["library_version"] != m["version"]

    # a synced item has no differences
    other = ok(capsys, repo, "diff", "agent", "reviewer")
    assert other["state"] == "synced" and other["manifest"]["same"] and other["head"]["same"]
    fail(capsys, repo, "unknown_item", "diff", "agent", "nobody")
