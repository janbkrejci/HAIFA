"""`factory config commit` and `factory config pull` against a bare remote (no network)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from config_repo import AGENTS_YAML, commit_all, git, make_repo, write

from aifactory.config import load_local
from aifactory.run.store import ABORTED, RUNNING, TaskRunRow, TaskRunStore
from cli_json import run_json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "providers"))

from gh_fake import install_fake_gh, prepare_shared_gh, reply  # noqa: E402

Capsys = pytest.CaptureFixture[str]
AGENTS = ".factory/agents.yaml"
NEW_WORKFLOW = ".factory/workflows/x.yaml"
OLD_PROMPT = ".factory/workflows/plan-build.yaml"


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """`commit-tree` in the product code needs an identity and no signing."""
    for key in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{key}_NAME", "t")
        monkeypatch.setenv(f"GIT_{key}_EMAIL", "t@example.com")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")


def _repo(tmp_path: Path, *, remote: bool = True, gh: bool = False) -> Path:
    repo = make_repo(tmp_path / "repo")
    # the trace DB lives outside the repository, so snapshots see only git's state
    write(repo, ".factory/local.yaml", f"trace_db: {tmp_path / 'trace.db'}\n")
    if gh:
        write(repo, ".factory/config.yaml", "base: main\ngit_provider: github\n")
        commit_all(repo, "use github")
    if remote:
        bare = tmp_path / "origin.git"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
        git(repo, "remote", "add", "origin", str(bare))
        git(repo, "push", "-q", "-u", "origin", "main")
    return repo


def _bare(tmp_path: Path) -> Path:
    return tmp_path / "origin.git"


def _rev(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", ref).strip()


def _edit(repo: Path) -> None:
    write(repo, AGENTS, AGENTS_YAML.replace("model: opus", "model: haiku"))
    write(repo, NEW_WORKFLOW, "name: x\nsteps: [build]\n")
    (repo / OLD_PROMPT).unlink()


def _snapshot(repo: Path) -> tuple[str, bytes, dict[str, bytes]]:
    refs = git(repo, "for-each-ref", "--format=%(refname) %(objectname)")
    refs += git(repo, "symbolic-ref", "HEAD")
    index = (repo / ".git" / "index").read_bytes()
    files = {
        p.relative_to(repo).as_posix(): p.read_bytes()
        for p in repo.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(repo).parts
    }
    return refs, index, files


def _dry(capsys: Capsys, repo: Path, *extra: str) -> dict[str, Any]:
    argv = ["config", "commit", "--repo", str(repo), "--dry-run", *extra, "--json"]
    rc, obj = run_json(capsys, argv)
    assert rc == 0
    data: dict[str, Any] = obj["data"]
    return data


def _commit(capsys: Capsys, repo: Path, *extra: str) -> tuple[int, Any]:
    return run_json(capsys, ["config", "commit", "--repo", str(repo), *extra, "--json"])


def _store(repo: Path) -> TaskRunStore:
    return TaskRunStore(load_local(repo).trace_db_path(repo))


def _claim(repo: Path, pid: int) -> None:
    store = _store(repo)
    try:
        store.claim(
            TaskRunRow(
                run_id="r1",
                task_id="T1",
                branch="factory/T1-1",
                worktree=str(repo),
                base="main",
                base_sha=_rev(repo, "main"),
                head_sha=None,
                state=RUNNING,
                started_at="2026-01-01T00:00:00Z",
                pid=pid,
            )
        )
    finally:
        store.close()


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", ""])
    proc.wait()
    return proc.pid


def test_commit_and_push(tmp_path: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path)
    base_sha = _rev(repo, "main")
    _edit(repo)

    plan = _dry(capsys, repo)
    actions = {f["path"]: f["action"] for f in plan["files"]}
    assert actions == {AGENTS: "modify", NEW_WORKFLOW: "create", OLD_PROMPT: "delete"}
    assert plan["blockers"] == [] and plan["base_sha"] == base_sha
    assert len(plan["digest"]) == 64
    assert "+    model: haiku" in next(f for f in plan["files"] if f["path"] == AGENTS)["diff"]
    assert _dry(capsys, repo, "--pr")["digest"] == plan["digest"]

    rc, obj = _commit(capsys, repo, "--expect", plan["digest"], "-m", "config: haiku")
    assert rc == 0, obj
    data = obj["data"]
    assert data["committed"] and data["pushed"] and data["advanced"]
    sha = data["commit"]
    assert _rev(repo, "main") == sha == _rev(_bare(tmp_path), "main")
    assert _rev(repo, f"{sha}^") == base_sha
    names = git(repo, "show", "--name-only", "--format=", sha).split()
    assert sorted(names) == sorted(actions)
    assert git(repo, "show", f"{sha}:{AGENTS}") == (repo / AGENTS).read_text(encoding="utf-8")
    assert git(repo, "log", "-1", "--format=%s", sha).strip() == "config: haiku"
    assert git(repo, "status", "--porcelain", "--", ".factory/") == ""
    monkeypatch.chdir(repo)
    rc, status = run_json(capsys, ["config", "status", "--json"])
    assert rc == 0 and status["data"]["clean"]
    assert _dry(capsys, repo)["files"] == []


def test_rejected_push_changes_nothing(tmp_path: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path)
    hook = _bare(tmp_path) / "hooks" / "pre-receive"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    remote_before = _rev(_bare(tmp_path), "main")
    _edit(repo)
    git(repo, "add", "--", AGENTS)
    before = _snapshot(repo)

    rc, obj = _commit(capsys, repo)

    assert rc == 2 and obj["error"]["code"] == "push_failed"
    assert _snapshot(repo) == before
    assert _rev(_bare(tmp_path), "main") == remote_before


def _clone_push(tmp_path: Path, rel: str, text: str) -> str:
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(_bare(tmp_path)), str(other))
    write(other, rel, text)
    sha = commit_all(other, "elsewhere")
    git(other, "push", "-q", "origin", "main")
    return sha


def test_base_behind_and_diverged(tmp_path: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path)
    _clone_push(tmp_path, "README.md", "remote\n")
    _edit(repo)
    before = _snapshot(repo)

    rc, obj = _commit(capsys, repo)
    assert rc == 2 and obj["error"]["code"] == "base_behind"
    assert [b["code"] for b in obj["data"]["blockers"]] == ["base_behind"]
    plan = _dry(capsys, repo)
    assert [b["code"] for b in plan["blockers"]] == ["base_behind"]
    # the fetch may add the remote-tracking ref; nothing else changes
    assert _snapshot(repo)[1:] == before[1:]

    write(repo, "local.txt", "local\n")
    git(repo, "add", "local.txt")
    git(repo, "commit", "-q", "-m", "local only")
    before = _snapshot(repo)
    rc, obj = _commit(capsys, repo)
    assert rc == 2 and obj["error"]["code"] == "base_diverged"
    assert _snapshot(repo) == before


def test_plan_changed(tmp_path: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path)
    _edit(repo)
    old = _dry(capsys, repo)["digest"]
    write(repo, "README.md", "unrelated\n")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "unrelated")
    git(repo, "push", "-q", "origin", "main")

    rc, obj = _commit(capsys, repo, "--expect", old)
    assert rc == 2 and obj["error"]["code"] == "plan_changed"

    new = _dry(capsys, repo)["digest"]
    assert new != old
    rc, obj = _commit(capsys, repo, "--expect", new)
    assert rc == 0 and obj["data"]["committed"]


def test_live_run_blocks_dead_run_does_not(tmp_path: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path)
    _edit(repo)
    _claim(repo, os.getpid())
    before = _snapshot(repo)

    rc, obj = _commit(capsys, repo)
    assert rc == 2 and obj["error"]["code"] == "run_in_progress"
    assert _snapshot(repo) == before

    store = _store(repo)
    store.conn.execute("DELETE FROM task_runs")
    store.close()
    _claim(repo, _dead_pid())
    rc, obj = _commit(capsys, repo)
    assert rc == 0 and obj["data"]["advanced"]
    store = _store(repo)
    try:
        row = store.get("r1")
    finally:
        store.close()
    assert row is not None and row.state == ABORTED


def test_other_work_survives(tmp_path: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path)
    write(repo, "README.md", "readme\n")
    write(repo, "notes.txt", "notes\n")
    commit_all(repo, "more files")
    git(repo, "push", "-q", "origin", "main")
    write(repo, "README.md", "staged readme\n")
    git(repo, "add", "README.md")
    write(repo, "notes.txt", "unstaged notes\n")
    _edit(repo)
    staged_readme = git(repo, "show", ":README.md")

    rc, obj = _commit(capsys, repo)

    assert rc == 0 and obj["data"]["advanced"]
    sha = obj["data"]["commit"]
    assert git(repo, "diff", "--cached", "--name-only").split() == ["README.md"]
    assert git(repo, "show", ":README.md") == staged_readme
    assert git(repo, "diff", "--name-only").split() == ["notes.txt"]
    assert (repo / "notes.txt").read_text(encoding="utf-8") == "unstaged notes\n"
    names = git(repo, "show", "--name-only", "--format=", sha).split()
    assert "README.md" not in names and "notes.txt" not in names


def test_repo_without_remote(tmp_path: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path, remote=False)
    _edit(repo)
    rc, obj = _commit(capsys, repo)
    assert rc == 0
    data = obj["data"]
    assert data["committed"] and not data["pushed"] and data["advanced"]
    assert _rev(repo, "main") == data["commit"]
    assert git(repo, "status", "--porcelain") == ""


def test_not_on_base_and_pr_without_remote(tmp_path: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path, remote=False)
    git(repo, "checkout", "-q", "-b", "side")
    _edit(repo)
    base_sha = _rev(repo, "main")

    rc, obj = _commit(capsys, repo)
    assert rc == 2 and obj["error"]["code"] == "not_on_base"

    rc, obj = _commit(capsys, repo, "--pr")
    assert rc == 0, obj
    data = obj["data"]
    assert data["branch"] == "factory-config/1" and not data["pushed"]
    assert _rev(repo, "main") == base_sha
    assert _rev(repo, "factory-config/1^") == base_sha


def test_invalid_working_tree(tmp_path: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path)
    write(repo, AGENTS, "agents: [\n")
    assert [b["code"] for b in _dry(capsys, repo)["blockers"]] == ["invalid_config"]
    rc, obj = _commit(capsys, repo)
    assert rc == 2 and obj["error"]["code"] == "invalid_config"
    assert obj["error"]["issues"]


def test_nothing_to_commit(tmp_path: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path)
    rc, obj = _commit(capsys, repo)
    assert rc == 0
    assert obj["data"]["committed"] is False and obj["data"]["files"] == []


@pytest.fixture(scope="module")
def _shared_gh(tmp_path_factory: pytest.TempPathFactory) -> None:
    prepare_shared_gh(tmp_path_factory.mktemp("ghwarm"))


@pytest.mark.usefixtures("_shared_gh")
def test_pr_through_github(tmp_path: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, gh=True)
    log = install_fake_gh(
        tmp_path, monkeypatch, {"pr create": reply("https://github.com/o/r/pull/9\n")}
    )
    git(repo, "checkout", "-q", "-b", "side")
    _edit(repo)
    base_sha = _rev(repo, "main")
    before = _snapshot(repo)

    rc, obj = _commit(capsys, repo, "--pr", "-m", "config: haiku")

    assert rc == 0, obj
    data = obj["data"]
    assert data["branch"] == "factory-config/1" and data["pushed"]
    assert data["pr"]["url"] == "https://github.com/o/r/pull/9"
    assert _rev(_bare(tmp_path), "factory-config/1") == data["commit"]
    assert _rev(repo, f"{data['commit']}^") == base_sha
    after = _snapshot(repo)
    assert after[1:] == before[1:]
    assert _rev(repo, "main") == base_sha and git(repo, "symbolic-ref", "HEAD").strip().endswith(
        "side"
    )
    creates = [a for a in log.argvs() if a[:2] == ["pr", "create"]]
    assert creates and creates[0][2:6] == ["--base", "main", "--head", "factory-config/1"]

    rc, obj = _commit(capsys, repo, "--pr")
    assert rc == 0 and obj["data"]["branch"] == "factory-config/2"


def _pull(capsys: Capsys, repo: Path) -> tuple[int, Any]:
    return run_json(capsys, ["config", "pull", "--repo", str(repo), "--json"])


def test_pull_fast_forwards(tmp_path: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path)
    theirs = _clone_push(tmp_path, AGENTS, "remote agents\n")
    rc, obj = _pull(capsys, repo)
    assert rc == 0 and obj["data"]["updated"] and obj["data"]["after"] == theirs
    assert _rev(repo, "main") == theirs
    assert (repo / AGENTS).read_text(encoding="utf-8") == "remote agents\n"
    rc, obj = _pull(capsys, repo)
    assert rc == 0 and obj["data"]["updated"] is False


def test_pull_expected_digest_refuses_changes_and_accepts_reviewed_plan(tmp_path: Path) -> None:
    from aifactory.config.commit import ConfigCommitError, plan_pull_config, pull_config

    repo = _repo(tmp_path)
    original = _rev(repo, "main")
    _clone_push(tmp_path, AGENTS, "remote agents\n")
    plan = plan_pull_config(repo)
    assert _rev(repo, "main") == original
    before = _snapshot(repo)
    with pytest.raises(ConfigCommitError) as error:
        pull_config(repo, expect="stale-digest")
    assert error.value.code == "plan_changed"
    assert _snapshot(repo) == before
    result = pull_config(repo, expect=plan["digest"])
    assert result.updated and result.after == plan["after"]
    assert _rev(repo, "main") == plan["after"]


def test_pull_refuses_diverged_dirty_and_running(tmp_path: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path)
    _clone_push(tmp_path, "README.md", "remote\n")

    write(repo, AGENTS, "dirty\n")
    before = _snapshot(repo)
    rc, obj = _pull(capsys, repo)
    assert rc == 2 and obj["error"]["code"] == "dirty_base"
    assert _snapshot(repo)[1:] == before[1:] and _rev(repo, "main") == _rev(repo, "HEAD")
    git(repo, "checkout", "-q", "--", AGENTS)

    _claim(repo, os.getpid())
    main_before = _rev(repo, "main")
    rc, obj = _pull(capsys, repo)
    assert rc == 2 and obj["error"]["code"] == "run_in_progress"
    assert _rev(repo, "main") == main_before
    store = _store(repo)
    store.conn.execute("DELETE FROM task_runs")
    store.close()

    write(repo, "local.txt", "local\n")
    git(repo, "add", "local.txt")
    git(repo, "commit", "-q", "-m", "local only")
    before = _snapshot(repo)
    rc, obj = _pull(capsys, repo)
    assert rc == 2 and obj["error"]["code"] == "base_diverged"
    assert _snapshot(repo) == before


def test_pull_without_remote(tmp_path: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path, remote=False)
    rc, obj = _pull(capsys, repo)
    assert rc == 2 and obj["error"]["code"] == "no_remote"
