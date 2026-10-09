"""``factory config add|set|remove`` with a temporary library and a bare remote (no network)."""

from __future__ import annotations

import difflib
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from aifactory.config.loader import load_config
from aifactory.config.manifest import MANIFEST_FILE
from aifactory.config.source import WorktreeSource
from aifactory.config.yamledit import edit_yaml, roster_set
from aifactory.library import store
from cli_json import run_json
from fake_exe import make_executable

Capsys = pytest.CaptureFixture[str]
AGENTS = ".factory/agents.yaml"
SOLO = (
    "name: solo\n"
    "description: Scout alone, then review.\n"
    "steps:\n"
    "  - plan:\n"
    "      agent: scout\n"
    "  - review\n"
)
SKILL_MD = "---\nname: lint\ndescription: Lint the code.\n---\nRun the linter.\n"


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


def make_repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    (path / "README.md").write_text("readme\n", encoding="utf-8", newline="\n")
    (path / "justfile").write_text("test:\n    echo ok\n", encoding="utf-8", newline="\n")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "init")
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(path, "remote", "add", "origin", str(bare))
    git(path, "push", "-q", "-u", "origin", "main")
    git(path, "remote", "set-head", "origin", "main")
    return path.resolve()


def put(base: Path, rel: str, text: str) -> None:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def make_library() -> Path:
    """The library from the seed plus a skill ``lint`` and a workflow ``solo``."""
    store.init_library("team")
    root = store.library_root()
    put(root, "skills/lint/SKILL.md", SKILL_MD)
    put(root, "skills/lint/bin/run.sh", "#!/bin/sh\nruff .\n")
    (root / "skills/lint/bin/run.sh").chmod(0o755)
    put(root, "workflows/solo.yaml", SOLO)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "add lint and solo")
    return root


@pytest.fixture
def repo(tmp_path: Path, capsys: Capsys) -> Path:
    """An onboarded repo (factory init --commit from the seed) and a library with extras."""
    path = make_repo(tmp_path)
    rc, env = run_json(capsys, ["init", "--repo", str(path), "--commit", "--json"])
    assert rc == 0, env
    make_library()
    return path


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


def rev(repo: Path, ref: str = "main") -> str:
    return git(repo, "rev-parse", ref)


def manifest(repo: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((repo / MANIFEST_FILE).read_text(encoding="utf-8"))
    return data


def roster(repo: Path) -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load((repo / AGENTS).read_text(encoding="utf-8"))
    return {a["name"]: a for a in raw["agents"]}


def files(repo: Path) -> dict[str, bytes]:
    return {
        p.relative_to(repo).as_posix(): p.read_bytes()
        for p in repo.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(repo).parts
    }


def commit_all(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    git(repo, "push", "-q", "origin", "main")


def _claim(repo: Path, pid: int) -> None:
    from aifactory.config import load_local
    from aifactory.run.store import RUNNING, TaskRunRow, TaskRunStore

    runs = TaskRunStore(load_local(repo).trace_db_path(repo))
    try:
        runs.claim(
            TaskRunRow(
                run_id="r1",
                task_id="T1",
                branch="factory/T1-1",
                worktree=str(repo),
                base="main",
                base_sha=rev(repo),
                head_sha=None,
                state=RUNNING,
                started_at="2026-01-01T00:00:00Z",
                pid=pid,
            )
        )
    finally:
        runs.close()


# ── add ───────────────────────────────────────────────────────────────────────


def test_add_workflow_with_closure(repo: Path, capsys: Capsys) -> None:
    base = rev(repo)

    data = ok(capsys, repo, "add", "workflow", "solo")

    assert data["written"] and not data["committed"] and data["target"] == "worktree"
    added = {(a["type"], a["name"]): a["reason"] for a in data["added"]}
    assert added == {("workflow", "solo"): "requested", ("agent", "scout"): "dependency"}
    assert {"type": "agent", "name": "reviewer", "reason": "present"} in data["kept"]
    assert (repo / ".factory/workflows/solo.yaml").read_text(encoding="utf-8") == SOLO
    assert (repo / ".factory/prompts/scout/system.md").is_file()
    items = manifest(repo)["items"]
    assert items["workflows"]["solo"]["item"] == "solo" and items["workflows"]["solo"]["version"]
    assert items["agents"]["scout"]["version"]
    assert "scout" in roster(repo)
    load_config(WorktreeSource(repo))
    assert rev(repo) == base
    # the same again: nothing to change
    assert ok(capsys, repo, "add", "workflow", "solo")["changed"] is False


def test_add_agent_as_other_slot(repo: Path, capsys: Capsys) -> None:
    base = rev(repo)

    data = ok(
        capsys, repo, "add", "agent", "planner", "--as", "planner2", "--thinking", "high",
        "--model", "claude-opus-5-5",
    )  # fmt: skip

    entry = roster(repo)["planner2"]
    assert entry["thinking"] == "high" and entry["model"] == "claude-opus-5-5"
    assert entry["harness"] == "claude" and entry["writes"] == ["specs/"]
    assert data["bindings"]["planner2"]["thinking"] == "high"
    assert (repo / ".factory/prompts/planner2/system.md").read_bytes() == (
        repo / ".factory/prompts/planner/system.md"
    ).read_bytes()
    assert manifest(repo)["items"]["agents"]["planner2"]["item"] == "planner"
    assert rev(repo) == base


def test_slot_taken_and_same_content_noop(repo: Path, capsys: Capsys) -> None:
    before = files(repo)
    data = ok(capsys, repo, "add", "agent", "builder")
    assert data["changed"] is False and data["kept"][0]["reason"] == "same_content"
    assert files(repo) == before

    prompt = repo / ".factory/prompts/builder/system.md"
    prompt.write_text("changed\n", encoding="utf-8")
    before = files(repo)
    error = fail(capsys, repo, "slot_taken", "add", "agent", "builder")
    assert "--as" in error["data"]["fix"]
    assert files(repo) == before


def test_add_skill_to_both_trees(repo: Path, capsys: Capsys) -> None:
    base = rev(repo)

    data = ok(capsys, repo, "add", "skill", "lint")

    assert [a["name"] for a in data["added"]] == ["lint"]
    for top in (".claude/skills/lint", ".agents/skills/lint"):
        assert (repo / top / "SKILL.md").read_text(encoding="utf-8") == SKILL_MD
        assert os.access(repo / top / "bin/run.sh", os.X_OK)
    assert manifest(repo)["items"]["skills"]["lint"]["item"] == "lint"
    rc, env = run_json(capsys, ["skills", "sync", "--repo", str(repo), "--json"])
    assert rc == 0, env
    assert env["data"]["added"] == env["data"]["updated"] == env["data"]["removed"] == []
    assert rev(repo) == base
    fail(capsys, repo, "conflicting_options", "add", "skill", "lint", "--as", "other")


# ── set ───────────────────────────────────────────────────────────────────────


def test_set_keeps_comments_and_order(repo: Path, capsys: Capsys) -> None:
    path = repo / AGENTS
    text = path.read_text(encoding="utf-8")
    text = "# our agents\n" + text.replace("- name: builder\n", "- name: builder  # builds\n")
    path.write_text(text, encoding="utf-8", newline="\n")
    commit_all(repo, "comment the roster")
    base, before_manifest = rev(repo), manifest(repo)

    data = ok(
        capsys, repo, "set", "agent", "builder", "--thinking", "high", "--tools", "read,bash",
        "--color", "#112233",
    )  # fmt: skip

    after = path.read_text(encoding="utf-8")
    diff = list(difflib.ndiff(text.splitlines(), after.splitlines()))
    removed = [line[2:] for line in diff if line.startswith("- ")]
    added = [line[2:] for line in diff if line.startswith("+ ")]
    assert removed == ["  thinking: medium"]
    assert added == ["  thinking: high", "  tools:", "  - read", "  - bash", "  color: '#112233'"]
    assert after.startswith("# our agents\n") and "- name: builder  # builds\n" in after
    assert data["bindings"]["builder"]["tools"] == ["read", "bash"]
    assert manifest(repo) == before_manifest
    assert rev(repo) == base


def test_set_invalid_thinking(repo: Path, capsys: Capsys) -> None:
    before = files(repo)
    fail(capsys, repo, "invalid_value", "set", "agent", "builder", "--thinking", "unknown-level")
    fail(capsys, repo, "unknown_item", "set", "agent", "nobody", "--model", "x")
    assert files(repo) == before


def test_yamledit_roundtrip() -> None:
    flush = "# top\nagents:\n- name: a  # first\n  tools:\n  - read\n  purpose: 'x'\n"
    indented = "agents:\n  - name: a\n    tools:\n      - read\n"
    for text in (flush, indented):
        assert edit_yaml(text, lambda doc: None) == text
    legacy = "agents:\n- name: a\n  coding_agent: claude\n  model: m\n"
    out = edit_yaml(legacy, lambda doc: roster_set(doc, "a", {"harness": "codex"}))
    assert out == "agents:\n- name: a\n  harness: codex\n  model: m\n"


# ── remove ────────────────────────────────────────────────────────────────────


def test_remove_in_use_and_prune(repo: Path, capsys: Capsys) -> None:
    ok(capsys, repo, "add", "workflow", "solo")
    base = rev(repo)
    error = fail(capsys, repo, "in_use", "remove", "agent", "reviewer")
    assert any(u.startswith("workflow simple-sdlc") for u in error["data"]["used_by"])

    data = ok(capsys, repo, "remove", "workflow", "solo", "--prune")

    removed = {(r["type"], r["name"]): r["reason"] for r in data["removed"]}
    assert removed == {("workflow", "solo"): "requested", ("agent", "scout"): "pruned"}
    assert {"type": "agent", "name": "reviewer"}.items() <= next(
        k for k in data["kept"] if k["name"] == "reviewer"
    ).items()
    assert not (repo / ".factory/workflows/solo.yaml").exists()
    assert not (repo / ".factory/prompts/scout").exists()
    assert "scout" not in roster(repo) and "reviewer" in roster(repo)
    assert "scout" not in manifest(repo)["items"]["agents"]
    assert rev(repo) == base


def test_remove_keeps_local_and_backlog_in_base(repo: Path, capsys: Capsys) -> None:
    ok(capsys, repo, "add", "workflow", "solo")
    # scout becomes local: no manifest entry, so --prune leaves it
    path = repo / MANIFEST_FILE
    raw = manifest(repo)
    del raw["items"]["agents"]["scout"]
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    data = ok(capsys, repo, "remove", "workflow", "solo", "--prune", "--dry-run")
    assert {"type": "agent", "name": "scout", "reason": "local"} in data["kept"]

    put(repo, "backlog/M01-core/index.md", "---\nid: M01\ntitle: M01\n---\n")
    put(repo, "backlog/M01-core/S01-a/index.md", "---\nid: M01-S01\ntitle: S\n---\n")
    put(
        repo,
        "backlog/M01-core/S01-a/M01-S01-T01-x.md",
        "---\nid: M01-S01-T01\ntitle: T\nstatus: todo\nworkflow: solo\n---\n\nbody\n",
    )
    git(repo, "add", "backlog")
    git(repo, "commit", "-q", "-m", "backlog")
    git(repo, "push", "-q", "origin", "main")
    error = fail(capsys, repo, "in_use", "remove", "workflow", "solo")
    assert error["data"]["used_by"] == ["backlog task M01-S01-T01"]


# ── commit and blockers ───────────────────────────────────────────────────────


def test_commit_and_plan_changed(repo: Path, capsys: Capsys, tmp_path: Path) -> None:
    before = files(repo)
    old = ok(capsys, repo, "add", "workflow", "solo", "--commit", "--dry-run")
    assert old["dry_run"] and old["target"] == "direct" and old["blockers"] == []
    assert files(repo) == before

    put(repo, "notes.txt", "unrelated\n")
    commit_all(repo, "unrelated")
    head = rev(repo)
    fail(capsys, repo, "plan_changed", "add", "workflow", "solo", "--commit", "--expect",
         old["digest"])  # fmt: skip
    assert rev(repo) == head and not (repo / ".factory/workflows/solo.yaml").exists()

    new = ok(capsys, repo, "add", "workflow", "solo", "--commit", "--dry-run")
    data = ok(capsys, repo, "add", "workflow", "solo", "--commit", "--expect", new["digest"],
              "-m", "add solo")  # fmt: skip

    assert data["committed"] and data["pushed"] and data["advanced"]
    assert git(repo, "rev-parse", "main~1") == head
    assert git(tmp_path / "origin.git", "rev-parse", "main") == rev(repo)
    assert git(repo, "log", "-1", "--format=%s") == "add solo"
    assert (repo / ".factory/workflows/solo.yaml").read_text(encoding="utf-8") == SOLO
    assert git(repo, "status", "--porcelain") == ""

    data = ok(capsys, repo, "remove", "workflow", "solo", "--commit")
    assert data["committed"]
    assert not (repo / ".factory/workflows/solo.yaml").exists()
    assert git(repo, "status", "--porcelain") == ""
    assert git(tmp_path / "origin.git", "rev-parse", "main") == rev(repo)


def test_worktree_expect_and_run_in_progress(repo: Path, capsys: Capsys) -> None:
    base = rev(repo)
    before = files(repo)
    plan = ok(capsys, repo, "add", "workflow", "solo", "--dry-run")
    assert files(repo) == before
    fail(capsys, repo, "plan_changed", "add", "workflow", "solo", "--expect", "0" * 64)
    assert files(repo) == before
    data = ok(capsys, repo, "add", "workflow", "solo", "--expect", plan["digest"])
    assert data["written"]
    ok(capsys, repo, "remove", "workflow", "solo", "--prune")

    _claim(repo, os.getpid())
    before = files(repo)
    fail(capsys, repo, "run_in_progress", "add", "workflow", "solo")
    fail(capsys, repo, "run_in_progress", "add", "workflow", "solo", "--commit")
    assert files(repo) == before
    assert rev(repo) == base


def test_not_onboarded(tmp_path: Path, capsys: Capsys) -> None:
    path = make_repo(tmp_path)
    error = fail(capsys, path, "not_onboarded", "add", "agent", "builder")
    assert error["data"]["fix"] == "factory onboard"


def test_option_conflicts(repo: Path, capsys: Capsys) -> None:
    fail(capsys, repo, "conflicting_options", "add", "workflow", "solo", "--pr")
    fail(capsys, repo, "conflicting_options", "add", "workflow", "solo", "-m", "x")
    fail(capsys, repo, "conflicting_options", "add", "workflow", "solo", "--dry-run",
         "--expect", "abc")  # fmt: skip
    fail(capsys, repo, "conflicting_options", "add", "workflow", "solo", "--harness", "claude")
