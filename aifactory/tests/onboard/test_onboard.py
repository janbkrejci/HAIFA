"""`factory onboard`: the one-time extraction of a `.factory/` from before the library.

Machines are `HAIFA_HOME` directories; the library and the repo have bare remotes in
`tmp_path`. No model and no network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from onboard_repo import (
    bare_origin,
    commit_all,
    copy_haifa_factory,
    git,
    haifa_backlog,
    init_repo,
    library_with_versions,
    reject_pushes,
    sandbox_factory,
    stamp_sssf,
    worktree_snapshot,
    write,
)

from aifactory.config.manifest import MANIFEST_FILE, parse_manifest
from aifactory.library import store
from aifactory.library.store import NewFile, SeedItem
from aifactory.library.version import workflow_version
from aifactory.onboard import repo_state
from cli_json import run_json

Capsys = pytest.CaptureFixture[str]
AGENTS = ("planner", "builder", "reviewer", "documenter")
SLUG = "haifa-sandbox"


@pytest.fixture(autouse=True)
def identity(monkeypatch: pytest.MonkeyPatch) -> None:
    for kind in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{kind}_NAME", "Ada Tester")
        monkeypatch.setenv(f"GIT_{kind}_EMAIL", "ada@example.com")
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)


@pytest.fixture
def library_remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Machine 1 with a library (from the seed) pushed to a bare remote."""
    monkeypatch.setenv("HAIFA_HOME", str(tmp_path / "machine1"))
    path = tmp_path / "library.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(path))
    store.init_library("team", remote=str(path))
    return path


def _repo(tmp_path: Path, name: str, *, sandbox: bool = False, provider: str | None = None) -> Path:
    repo = init_repo(tmp_path / name)
    git(repo, "config", "user.name", "Ada Tester")
    git(repo, "config", "user.email", "ada@example.com")
    if sandbox:
        sandbox_factory(repo)
    else:
        copy_haifa_factory(repo)
    haifa_backlog(repo)
    if provider is not None:
        config = repo / ".factory" / "config.yaml"
        text = config.read_text(encoding="utf-8").replace("git_provider: github", provider)
        config.write_text(text, encoding="utf-8")
    commit_all(repo, "pre library factory")
    return repo


def _library_head() -> str:
    return git(store.library_root(), "rev-parse", "HEAD")


def _onboard(capsys: Capsys, repo: Path, *args: str) -> tuple[int, Any]:
    return run_json(capsys, ["onboard", "--repo", str(repo), *args, "--json"])


def _rows(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["subject"]: r for r in data["report"]}


def _codes(data: dict[str, Any]) -> list[str]:
    return [b["code"] for b in data["blockers"]]


def _manifest_at(repo: Path, ref: str) -> Any:
    return parse_manifest(git(repo, "show", f"{ref}:{MANIFEST_FILE}"), "test")


def _heads(repo: Path) -> str:
    return git(repo, "for-each-ref", "refs/heads")


def _index(repo: Path) -> bytes:
    return (repo / ".git" / "index").read_bytes()


# ── HAIFA copy: everything linked ─────────────────────────────────────────────


@pytest.fixture
def haifa(tmp_path: Path, library_remote: Path) -> Path:
    repo = _repo(tmp_path, "haifa")
    bare_origin(repo, tmp_path)
    library_with_versions(repo)
    return repo


def test_haifa_copy_dry_run_and_commit(haifa: Path, tmp_path: Path, capsys: Capsys) -> None:
    repo = haifa
    library_head = _library_head()
    old = git(repo, "rev-parse", "main")
    files, heads, index = worktree_snapshot(repo), _heads(repo), _index(repo)

    rc, obj = _onboard(capsys, repo, "--dry-run")
    assert rc == 0, obj
    data = obj["data"]
    assert data["blockers"] == [] and data["state"] == "pre_library"
    rows = _rows(data)
    for agent in AGENTS:
        assert rows[f"agent/{agent}"]["code"] == "linked", rows[f"agent/{agent}"]
        assert rows[f"agent/{agent}"]["item"] == agent
    for wf in ("build-test-review", "finish-test-review", "simple-sdlc", "plan-build-test"):
        assert rows[f"workflow/{wf}"]["code"] == "linked"
    for path in (".factory/config.yaml", ".factory/agents.yaml", "adws/"):
        assert rows[path]["code"] == "left_in_place"
    assert data["library_plan"] is None
    assert sorted(data["paths"]) == [
        ".factory/manifest.yaml",
        ".factory/workflows/plan-build-test.yaml",
        ".factory/workflows/simple-sdlc.yaml",
        ".gitignore",
    ]
    assert worktree_snapshot(repo) == files
    assert _heads(repo) == heads and _index(repo) == index
    assert "linked agent/planner" in data["message"]

    rc, obj = _onboard(capsys, repo, "--commit", "--expect", data["digest"])
    assert rc == 0, obj
    done = obj["data"]
    assert done["committed"] and done["pushed"] and done["advanced"]
    assert done["library_commit"] == library_head
    assert _library_head() == library_head
    new = git(repo, "rev-parse", "main")
    assert git(repo, "rev-parse", f"{new}:adws") == git(repo, "rev-parse", f"{old}:adws")
    assert git(repo, "rev-parse", "origin/main") == new
    manifest = _manifest_at(repo, "main")
    assert manifest.onboarding is not None
    assert manifest.onboarding.source == "pre_library"
    assert manifest.onboarding.source_commit == old
    assert manifest.onboarding.by == "Ada Tester"
    assert manifest.onboarding.library_commit == library_head
    assert sorted(manifest.items.agents) == sorted(AGENTS)
    assert sorted(manifest.items.workflows) == [
        "build-test-review",
        "finish-test-review",
        "plan-build-test",
        "simple-sdlc",
    ]
    assert repo_state(repo).state == "onboarded"
    message = git(repo, "log", "-1", "--format=%B", "main")
    assert "linked agent/builder" in message and data["digest"] in message

    # the bytes of the source stay: only additions under .factory/ and .gitignore lines
    for path in git(repo, "ls-tree", "-r", "--name-only", old, "--", ".factory/").splitlines():
        assert git(repo, "rev-parse", f"{new}:{path}") == git(repo, "rev-parse", f"{old}:{path}")
    for line in git(repo, "diff", "--name-status", old, new).splitlines():
        status, path = line.split("\t")
        assert (status == "A" and path.startswith(".factory/")) or path == ".gitignore", line
    diff = git(repo, "diff", old, new, "--", ".gitignore").splitlines()
    assert not [d for d in diff if d.startswith("-") and not d.startswith("---")]


def test_second_onboard_is_refused(haifa: Path, capsys: Capsys) -> None:
    rc, obj = _onboard(capsys, haifa, "--commit")
    assert rc == 0, obj
    head, library = git(haifa, "rev-parse", "main"), _library_head()
    files = worktree_snapshot(haifa)
    rc, obj = _onboard(capsys, haifa, "--dry-run")
    assert rc == 0
    assert obj["data"]["blockers"][0]["code"] == "already_onboarded"
    assert obj["data"]["files"] == []
    rc, obj = _onboard(capsys, haifa, "--commit")
    assert rc == 2 and obj["error"]["code"] == "already_onboarded"
    assert obj["data"]["fix"] == "factory adopt"
    assert git(haifa, "rev-parse", "main") == head and _library_head() == library
    assert worktree_snapshot(haifa) == files


def test_digest_is_stable_and_covers_the_library(haifa: Path, capsys: Capsys) -> None:
    _, first = _onboard(capsys, haifa, "--dry-run")
    _, second = _onboard(capsys, haifa, "--dry-run")
    assert first["data"]["digest"] == second["data"]["digest"]
    plan = next(s for s in store.packaged_seed() if s.key == "workflow/plan")
    data = plan.files[0].data + b"# extra\n"
    extra = SeedItem(
        "workflow", "extra", workflow_version(data), (NewFile("workflows/extra.yaml", False, data),)
    )
    store.import_items([extra], "test", "library: extra")
    _, third = _onboard(capsys, haifa, "--dry-run")
    assert third["data"]["digest"] != first["data"]["digest"]
    rc, obj = _onboard(capsys, haifa, "--commit", "--expect", first["data"]["digest"])
    assert rc == 2 and obj["error"]["code"] == "plan_changed"


# ── haifa-sandbox: changed agents ─────────────────────────────────────────────


def test_sandbox_creates_new_items(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path, SLUG, sandbox=True)
    origin = bare_origin(repo, tmp_path)
    before = _library_head()
    rc, obj = _onboard(capsys, repo, "--dry-run", "--name", "agent/builder=builder-x")
    assert rc == 0, obj
    data = obj["data"]
    rows = _rows(data)
    assert data["blockers"] == []
    for agent in ("planner", "reviewer", "documenter"):
        assert rows[f"agent/{agent}"]["code"] == "converted"
        assert rows[f"agent/{agent}"]["item"] == f"{agent}-{SLUG}"
    assert rows["agent/builder"]["item"] == "builder-x"
    assert rows["workflow/simple-sdlc"]["item"] == f"simple-sdlc-{SLUG}"
    assert rows["workflow/build-test-review"] == {
        **rows["workflow/build-test-review"],
        "code": "converted",
        "item": "build-test-review",
    }
    planned = {i["name"] for i in data["library_plan"]["items"]}
    assert "builder-x" in planned and f"planner-{SLUG}" in planned
    assert _library_head() == before

    rc, obj = _onboard(
        capsys, repo, "--commit", "--expect", data["digest"], "--name", "agent/builder=builder-x"
    )
    assert rc == 0, obj
    library_commit = obj["data"]["library_commit"]
    assert library_commit != before and _library_head() == library_commit
    assert git(library_remote, "rev-parse", "main") == library_commit
    manifest = _manifest_at(repo, "main")
    assert manifest.items.agents["planner"].item == f"planner-{SLUG}"
    assert manifest.items.workflows["simple-sdlc"].item == f"simple-sdlc-{SLUG}"
    assert manifest.onboarding is not None
    assert manifest.onboarding.library_commit == library_commit
    assert git(origin, "rev-parse", "main") == git(repo, "rev-parse", "main")


def test_sandbox_keep_local(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path, SLUG, sandbox=True)
    bare_origin(repo, tmp_path)
    before = _library_head()
    keep = [arg for a in AGENTS for arg in ("--keep-local", f"agent/{a}")]
    keep += ["--keep-local", "workflow/simple-sdlc", "--name", "workflow/build-test-review=btr"]
    rc, obj = _onboard(capsys, repo, "--dry-run", *keep)
    assert rc == 0, obj
    rows = _rows(obj["data"])
    for agent in AGENTS:
        assert rows[f"agent/{agent}"]["code"] == "carried_over"
        assert rows[f"agent/{agent}"]["item"] == agent
    assert rows["workflow/simple-sdlc"]["code"] == "carried_over"
    assert rows["workflow/finish-test-review"]["code"] == "converted"
    assert [i["name"] for i in obj["data"]["library_plan"]["items"]] == [
        "btr",
        "finish-test-review",
    ]

    rc, obj = _onboard(capsys, repo, "--commit", *keep)
    assert rc == 0, obj
    from aifactory.library.state import extract_factory, item_states, library_side

    copy = tmp_path / "copy"
    extract_factory(repo, git(repo, "rev-parse", "main"), copy)
    manifest = _manifest_at(repo, "main")
    states = {(s.type, s.name): s.state for s in item_states(copy, manifest, library_side())}
    for agent in AGENTS:
        assert states[("agent", agent)] == "modified"
        assert manifest.items.agents[agent].item == agent
    assert states[("workflow", "simple-sdlc")] == "modified"
    assert git(store.library_root(), "rev-list", "--count", f"{before}..HEAD") == "1"


def test_keep_local_unknown_and_bad_options(
    tmp_path: Path, library_remote: Path, capsys: Capsys
) -> None:
    repo = _repo(tmp_path, SLUG, sandbox=True)
    rc, obj = _onboard(capsys, repo, "--keep-local", "workflow/build-test-review")
    assert rc == 2 and obj["error"]["code"] == "unknown_item"
    rc, obj = _onboard(capsys, repo, "--keep-local", "agent/nobody")
    assert rc == 2 and obj["error"]["code"] == "invalid_value"
    rc, obj = _onboard(capsys, repo, "--name", "agent/builder")
    assert rc == 2 and obj["error"]["code"] == "invalid_value"
    rc, obj = _onboard(capsys, repo, "--name", "agent/builder=planner")
    assert rc == 2 and obj["error"]["code"] == "name_taken"
    rc, obj = _onboard(capsys, repo, "--expect", "abc")
    assert rc == 2 and obj["error"]["code"] == "conflicting_options"
    rc, obj = _onboard(capsys, repo, "--dry-run", "--commit")
    assert rc == 2 and obj["error"]["code"] == "conflicting_options"


# ── pushes refused ────────────────────────────────────────────────────────────


def test_library_push_rejected_leaves_repo(
    tmp_path: Path, library_remote: Path, capsys: Capsys
) -> None:
    repo = _repo(tmp_path, SLUG, sandbox=True)
    origin = bare_origin(repo, tmp_path)
    reject_pushes(library_remote)
    head, library = git(repo, "rev-parse", "main"), _library_head()
    files, index = worktree_snapshot(repo), _index(repo)
    rc, obj = _onboard(capsys, repo, "--commit")
    assert rc == 2 and obj["error"]["code"] == "push_failed"
    assert git(repo, "rev-parse", "main") == head
    assert git(origin, "rev-parse", "main") == head
    assert worktree_snapshot(repo) == files and _index(repo) == index
    assert _library_head() == library


def test_repo_push_rejected_then_retry(
    tmp_path: Path, library_remote: Path, capsys: Capsys
) -> None:
    repo = _repo(tmp_path, SLUG, sandbox=True)
    origin = bare_origin(repo, tmp_path)
    hook = reject_pushes(origin)
    head = git(repo, "rev-parse", "main")
    rc, obj = _onboard(capsys, repo, "--commit")
    assert rc == 2 and obj["error"]["code"] == "push_failed"
    library_commit = obj["data"]["library_commit"]
    assert library_commit and git(library_remote, "rev-parse", "main") == library_commit
    assert git(repo, "rev-parse", "main") == head
    assert repo_state(repo).state == "pre_library"

    hook.unlink()
    rc, obj = _onboard(capsys, repo, "--dry-run")
    assert rc == 0, obj
    data = obj["data"]
    rows = _rows(data)
    for agent in AGENTS:
        assert rows[f"agent/{agent}"]["code"] == "linked"
        assert rows[f"agent/{agent}"]["item"] == f"{agent}-{SLUG}"
    assert data["library_plan"] is None and data["blockers"] == []
    rc, obj = _onboard(capsys, repo, "--commit", "--expect", data["digest"])
    assert rc == 0, obj
    manifest = _manifest_at(repo, "main")
    assert manifest.items.agents["builder"].item == f"builder-{SLUG}"
    assert git(origin, "rev-parse", "main") == git(repo, "rev-parse", "main")


# ── the remote check ──────────────────────────────────────────────────────────


def test_onboarded_in_remote(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    repo_a = _repo(tmp_path, "a")
    origin = bare_origin(repo_a, tmp_path)
    repo_b = tmp_path / "b"
    git(tmp_path, "clone", "-q", str(origin), str(repo_b))
    rc, obj = _onboard(capsys, repo_a, "--commit")
    assert rc == 0, obj
    assert repo_state(repo_b).state == "pre_library"
    rc, obj = _onboard(capsys, repo_b, "--dry-run")
    assert rc == 0
    blocker = next(b for b in obj["data"]["blockers"] if b["code"] == "onboarded_in_remote")
    assert "factory config pull" in blocker["fix"] and "factory adopt" in blocker["fix"]


def test_onboarding_pending_and_pr(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path, "a", provider="git_provider: local")
    origin = bare_origin(repo, tmp_path)
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(origin), str(other))
    head = git(repo, "rev-parse", "main")
    rc, obj = _onboard(capsys, repo, "--commit", "--pr")
    assert rc == 0, obj
    assert obj["data"]["branch"] == "factory-config/onboarding"
    assert obj["data"]["pr"]["branch"] == "factory-config/onboarding"
    assert git(repo, "rev-parse", "main") == head
    assert git(origin, "rev-parse", "refs/heads/factory-config/onboarding")
    rc, obj = _onboard(capsys, other, "--dry-run")
    assert "onboarding_pending" in _codes(obj["data"])
    rc, obj = _onboard(capsys, other, "--commit")
    assert rc == 2 and obj["error"]["code"] == "onboarding_pending"


def test_pending_branch_pushed(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path, "a")
    bare_origin(repo, tmp_path)
    git(repo, "push", "-q", "origin", "main:refs/heads/factory-config/onboarding")
    rc, obj = _onboard(capsys, repo)
    assert rc == 0 and _codes(obj["data"]) == ["onboarding_pending"]


def test_remote_unchecked(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path, "a")
    bare_origin(repo, tmp_path)
    git(repo, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    rc, obj = _onboard(capsys, repo, "--dry-run")
    assert rc == 0 and _codes(obj["data"]) == ["remote_unchecked"]
    assert obj["data"]["remote"]["checked"] is False


def test_no_remote_commits_locally(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path, "a")
    rc, obj = _onboard(capsys, repo, "--dry-run")
    assert rc == 0 and obj["data"]["blockers"] == []
    assert any(w.startswith("no_remote:") for w in obj["warnings"])
    rc, obj = _onboard(capsys, repo, "--commit")
    assert rc == 0, obj
    assert obj["data"]["advanced"] and not obj["data"]["pushed"]
    assert repo_state(repo).state == "onboarded"
    assert (repo / MANIFEST_FILE).is_file()


# ── other blockers ────────────────────────────────────────────────────────────


def test_source_not_committed(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path, "a")
    agents = repo / ".factory" / "agents.yaml"
    agents.write_text(agents.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
    rc, obj = _onboard(capsys, repo)
    assert rc == 0 and "source_not_committed" in _codes(obj["data"])
    rc, obj = _onboard(capsys, repo, "--commit")
    assert rc == 2 and obj["error"]["code"] == "source_not_committed"


def test_library_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Capsys) -> None:
    monkeypatch.setenv("HAIFA_HOME", str(tmp_path / "empty"))
    repo = _repo(tmp_path, "a")
    rc, obj = _onboard(capsys, repo)
    assert rc == 0 and _codes(obj["data"]) == ["library_missing"]


def test_library_dirty(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path, "a")
    write(store.library_root(), "stray.txt", "x\n")
    rc, obj = _onboard(capsys, repo)
    assert rc == 0 and "library_dirty" in _codes(obj["data"])


def test_state_blockers(
    tmp_path: Path, library_remote: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    # an sssf repo is converted now (test_sssf.py); pi and codex count as missing so that
    # preflight never asks a real pi for its catalogue
    monkeypatch.setattr(
        "aifactory.library.config_edit._missing_harnesses", lambda: frozenset({"pi", "codex"})
    )
    sssf = init_repo(tmp_path / "sssf")
    stamp_sssf(sssf)
    commit_all(sssf, "sssf")
    rc, obj = _onboard(capsys, sssf)
    assert rc == 0 and obj["data"]["state"] == "sssf"
    assert obj["data"]["report"] and _codes(obj["data"]) == []

    plain = init_repo(tmp_path / "plain")
    rc, obj = _onboard(capsys, plain)
    assert _codes(obj["data"]) == ["not_installed"]
    rc, obj = _onboard(capsys, plain, "--commit")
    assert rc == 2 and obj["error"]["code"] == "not_installed"

    wt = init_repo(tmp_path / "wt")
    write(wt, ".factory/config.yaml", "base: main\n")
    rc, obj = _onboard(capsys, wt)
    assert _codes(obj["data"]) == ["config_not_committed"]


def test_backlog_workflow_unknown(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    repo = _repo(tmp_path, "a")
    task = repo / "backlog" / "P" / "S01" / "T01.md"
    task.write_text(
        task.read_text(encoding="utf-8").replace("simple-sdlc", "nowhere"), encoding="utf-8"
    )
    commit_all(repo, "unknown workflow")
    rc, obj = _onboard(capsys, repo)
    assert rc == 0
    assert _rows(obj["data"])["workflow/nowhere"]["code"] == "manual"
    assert any(w.startswith("unknown_workflow:") for w in obj["warnings"])


def test_text_output(haifa: Path, capsys: Capsys) -> None:
    from aifactory.cli import main

    assert main(["onboard", "--repo", str(haifa)]) == 0
    out = capsys.readouterr().out
    assert "linked" in out and "next: factory onboard --commit --expect" in out
