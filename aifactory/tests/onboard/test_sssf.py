"""`factory onboard` of sssf installations (adws/, AR32): golden reports and commits.

Fixtures are `vendor/sssf/templates` stamped into temporary repos with small patches.
Machines are `HAIFA_HOME` directories; the library and the repos have bare remotes in
`tmp_path`. No model and no network: pi and codex count as missing, so preflight never
asks a real pi for its catalogue.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from onboard_repo import (
    JSST_BUILDER_RULES,
    JSST_REVIEWER_RULE,
    PLANNER_CHANGED_LINE,
    SSSF_PROMPTS,
    SSSF_ROSTER,
    commit_all,
    copy_haifa_factory,
    git,
    haifa_backlog,
    init_repo,
    patch_amber,
    patch_jsst,
    patch_modified_chain,
    patch_omnibus,
    sssf_repo,
    stamp_sssf,
    worktree_snapshot,
)

from aifactory.config.manifest import MANIFEST_FILE, parse_manifest
from aifactory.library import store
from aifactory.library.seed import SEED_DIR
from aifactory.onboard import repo_state
from cli_json import run_json

Capsys = pytest.CaptureFixture[str]
GOLDEN = Path(__file__).parent / "golden"
STOCK_AGENTS = ("planner", "builder", "scout", "reviewer", "documenter")


@pytest.fixture(autouse=True)
def identity(monkeypatch: pytest.MonkeyPatch) -> None:
    for kind in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{kind}_NAME", "Ada Tester")
        monkeypatch.setenv(f"GIT_{kind}_EMAIL", "ada@example.com")
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)


@pytest.fixture(autouse=True)
def no_pi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "aifactory.library.config_edit._missing_harnesses", lambda: frozenset({"pi", "codex"})
    )


@pytest.fixture
def library_remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Machine 1 with a library (from the seed) pushed to a bare remote."""
    monkeypatch.setenv("HAIFA_HOME", str(tmp_path / "machine1"))
    path = tmp_path / "library.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(path))
    store.init_library("team", remote=str(path))
    return path


def _onboard(capsys: Capsys, repo: Path, *args: str) -> tuple[int, Any]:
    return run_json(capsys, ["onboard", "--repo", str(repo), *args, "--json"])


def _dry_run(capsys: Capsys, repo: Path, *args: str) -> dict[str, Any]:
    rc, obj = _onboard(capsys, repo, "--dry-run", *args)
    assert rc == 0, obj
    data: dict[str, Any] = obj["data"]
    return data


def _lines(data: dict[str, Any]) -> list[str]:
    return [f"{r['code']} {r['subject']} {r['item'] or '-'}" for r in data["report"]]


def _golden(data: dict[str, Any], case: str) -> None:
    expected = (GOLDEN / f"sssf_{case}.txt").read_text(encoding="utf-8").splitlines()
    assert _lines(data) == expected


def _row(data: dict[str, Any], code: str, subject: str) -> dict[str, Any]:
    found = [r for r in data["report"] if r["code"] == code and r["subject"] == subject]
    assert len(found) == 1, (code, subject, _lines(data))
    row: dict[str, Any] = found[0]
    return row


def _codes(data: dict[str, Any]) -> list[str]:
    return [b["code"] for b in data["blockers"]]


def _planned(data: dict[str, Any], path: str) -> bytes:
    """The bytes the plan writes to `path`."""
    found = next(f for f in data["files"] if f["path"] == path)
    assert found["content"] is not None
    content: str = found["content"]
    return content.encode("utf-8")


def _seed_prompt(agent: str, name: str) -> bytes:
    return (SEED_DIR / "agents" / agent / name).read_bytes()


def _library_file(rel: str) -> bytes:
    return (store.library_root() / rel).read_bytes()


def _adws(repo: Path) -> list[tuple[str, int, bytes]]:
    return [f for f in worktree_snapshot(repo) if f[0].startswith("adws/")]


# ── Omnibus: every agent on claude ────────────────────────────────────────────


def test_omnibus(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    from aifactory.config.loader import load_config
    from aifactory.config.source import CommitSource
    from aifactory.library.install_commit import validate_source

    repo = sssf_repo(tmp_path, "omnibus", origin=True)
    origin = tmp_path / "omnibus.git"
    patch_omnibus(repo)
    commit_all(repo, "omnibus")
    git(repo, "push", "-q", "origin", "main")
    old = git(repo, "rev-parse", "main")
    adws = _adws(repo)

    data = _dry_run(capsys, repo)
    assert data["blockers"] == [] and data["validation"]["ok"], data["validation"]
    assert data["state"] == "sssf" and data["source"] == "sssf"
    _golden(data, "omnibus")
    assert data["library_plan"] is None
    for agent in STOCK_AGENTS:
        assert _row(data, "linked", f"agent/{agent}")["item"] == agent
    quality = "adws/adw_modules/quality.py"
    assert "test_timeout 1800" in _row(data, "converted", f"{quality}:test")["message"]
    assert "just, lint" in _row(data, "not_converted", f"{quality}:lint")["message"]
    config = yaml.safe_load(_planned(data, ".factory/config.yaml"))
    assert config["test_command"] == ["just", "test"] and config["test_timeout"] == 1800
    assert config["protected_files"] == [
        ".factory/",
        "adws/adw_modules/",
        "adws/adw_sssf_config/",
        "adws/adw_*.py",
    ]
    assert (config["base"], config["git_provider"], config["remote"]) == (
        "main",
        "local",
        "origin",
    )
    text = _planned(data, ".factory/agents.yaml").decode("utf-8")
    assert text.startswith("# agents of this repo, converted by factory onboard from the sssf ")
    assert SSSF_ROSTER in text.splitlines()[0]
    agents = {a["name"]: a for a in yaml.safe_load(text)["agents"]}
    assert all(a["harness"] == "claude" and a["model"] == "opus" for a in agents.values())
    assert agents["scout"]["thinking"] == "medium"
    assert agents["documenter"]["thinking"] == "medium"
    assert agents["planner"]["thinking"] == "high"
    assert "harness_engineering" not in agents["planner"]
    assert _adws(repo) == adws

    rc, obj = _onboard(capsys, repo, "--commit", "--expect", data["digest"])
    assert rc == 0, obj
    assert obj["data"]["committed"] and obj["data"]["pushed"]
    new = git(repo, "rev-parse", "main")
    assert git(origin, "rev-parse", "main") == new
    manifest = parse_manifest(git(repo, "show", f"main:{MANIFEST_FILE}"), "test")
    assert manifest.onboarding is not None
    assert manifest.onboarding.source == "sssf"
    assert manifest.onboarding.source_commit == old
    assert sorted(manifest.items.agents) == sorted(STOCK_AGENTS)
    assert sorted(manifest.items.workflows) == ["simple-sdlc"]
    assert "(sssf)" in git(repo, "log", "-1", "--format=%s", "main")
    source = CommitSource(repo, "main", new)
    cfg = load_config(source)
    assert cfg.settings.test_timeout == 1800
    workflow = (repo / ".factory" / "workflows" / "simple-sdlc.yaml").read_bytes()
    assert validate_source(source, {"simple-sdlc": workflow}) == []
    assert git(repo, "rev-parse", f"{old}:adws") == git(repo, "rev-parse", f"{new}:adws")
    for line in git(repo, "diff", "--name-status", old, new).splitlines():
        status, path = line.split("\t")
        assert (status == "A" and path.startswith(".factory/")) or (
            status in ("A", "M") and path == ".gitignore"
        ), line
    assert _adws(repo) == adws
    assert repo_state(repo).state == "onboarded"

    data = _dry_run(capsys, repo)
    assert _codes(data) == ["already_onboarded"]
    rc, obj = _onboard(capsys, repo, "--commit")
    assert rc == 2 and obj["error"]["code"] == "already_onboarded"


# ── JSST and amber: pi with an extension, merged prompts ──────────────────────


def _jsst(tmp_path: Path, capsys: Capsys, library_remote: Path) -> None:
    repo = sssf_repo(tmp_path, "jsst", origin=False)
    patch_jsst(repo)
    commit_all(repo, "jsst")
    old = git(repo, "rev-parse", "main")
    library_head = git(store.library_root(), "rev-parse", "HEAD")

    data = _dry_run(capsys, repo)
    assert data["blockers"] == [] and data["validation"]["ok"], data["validation"]
    assert any(w.startswith("no_remote:") for w in data["warnings"])
    _golden(data, "jsst")
    assert _row(data, "converted", "agent/builder")["item"] == "builder-jsst"
    assert _row(data, "converted", "agent/reviewer")["item"] == "reviewer-jsst"
    assert "merged cleanly" in _row(data, "converted", "agent/reviewer")["message"]
    builder = _planned(data, ".factory/prompts/builder/system.md")
    assert JSST_BUILDER_RULES.encode("utf-8") in builder
    assert _seed_prompt("builder", "system.md").splitlines()[-1] in builder.splitlines()
    reviewer = _planned(data, ".factory/prompts/reviewer/system.md")
    assert JSST_REVIEWER_RULE.encode("utf-8") in reviewer
    agents = {
        a["name"]: a for a in yaml.safe_load(_planned(data, ".factory/agents.yaml"))["agents"]
    }
    bound = [".factory/extensions/subagents/subagents.ts"]
    for name in ("planner", "scout"):
        assert agents[name]["harness"] == "pi"
        assert agents[name]["harness_engineering"] == bound
    for name in ("builder", "reviewer"):
        assert agents[name]["harness"] == "claude"
        assert "harness_engineering" not in agents[name]
    extension = ".factory/extensions/subagents/"
    assert {f"{extension}subagents.ts", f"{extension}themeMap.ts"} <= set(data["paths"])
    planned = {(i["type"], i["name"]) for i in data["library_plan"]["items"]}
    assert planned == {
        ("agent", "builder-jsst"),
        ("agent", "reviewer-jsst"),
        ("extension", "subagents"),
    }

    rc, obj = _onboard(capsys, repo, "--commit", "--expect", data["digest"])
    assert rc == 0, obj
    done = obj["data"]
    assert done["committed"] and done["advanced"] and not done["pushed"]
    library_commit = done["library_commit"]
    assert library_commit != library_head
    assert git(library_remote, "rev-parse", "main") == library_commit
    assert git(repo, "rev-parse", "main") != old
    for name in ("builder-jsst", "reviewer-jsst"):
        meta = yaml.safe_load(_library_file(f"agents/{name}/agent.yaml"))
        assert meta["defaults"]["harness"] == "claude"
    assert _library_file("extensions/subagents/themeMap.ts")
    manifest = parse_manifest(git(repo, "show", f"main:{MANIFEST_FILE}"), "test")
    assert manifest.items.extensions["subagents"].item == "subagents"
    assert manifest.items.agents["builder"].item == "builder-jsst"


def test_jsst_then_amber(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    _jsst(tmp_path, capsys, library_remote)
    repo = sssf_repo(tmp_path, "amber-swiss-clock", origin=True)
    patch_amber(repo)
    commit_all(repo, "amber")
    git(repo, "push", "-q", "origin", "main")
    data = _dry_run(capsys, repo)
    assert data["blockers"] == [] and data["validation"]["ok"], data["validation"]
    _golden(data, "amber")
    assert _row(data, "linked", "extension/subagents")["item"] == "subagents"
    row = _row(data, "converted", "agent/builder")
    assert row["item"] == "builder-amber-swiss-clock" and "merged cleanly" in row["message"]
    rc, obj = _onboard(capsys, repo, "--commit", "--expect", data["digest"])
    assert rc == 0, obj
    assert obj["data"]["pushed"]


# ── a modified chain, a foreign agent, conflicts ──────────────────────────────


def test_modified_chain(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    repo = sssf_repo(tmp_path, "chained", origin=False)
    patch_modified_chain(repo)
    commit_all(repo, "modified")
    adws = _adws(repo)
    data = _dry_run(capsys, repo)
    assert data["blockers"] == [] and data["validation"]["ok"], data["validation"]
    _golden(data, "modified_chain")
    assert any(w.startswith("alternate_rosters:") for w in data["warnings"])
    conflict = _row(data, "manual", "agent/planner/system.md")
    assert conflict["detail"] is not None
    assert "+" + PLANNER_CHANGED_LINE.rstrip("\n") in conflict["detail"].splitlines()
    assert _planned(data, ".factory/prompts/planner/system.md") == _seed_prompt(
        "planner", "system.md"
    )
    assert _row(data, "manual", "agent/planner/user.md")["detail"]
    assert _row(data, "linked", "agent/planner")["item"] == "planner"
    assert "port the change by hand" in _row(data, "manual", "adws/adw_plan.py")["message"]
    assert "    +" + PLANNER_CHANGED_LINE.rstrip("\n") in data["message"]
    tester = next(
        i for i in data["library_plan"]["items"] if (i["type"], i["name"]) == ("agent", "tester")
    )
    assert tester["action"] == "create"
    from aifactory.onboard import plan_onboard

    plan = plan_onboard(repo)
    assert plan.extraction is not None
    item = next(i for i in plan.extraction.library_items if i.key == "agent/tester")
    meta = yaml.safe_load(next(f for f in item.files if f.path.endswith("agent.yaml")).data)
    assert meta["defaults"]["extensions"] == ["subagents"]
    assert meta["defaults"]["harness"] == "pi"

    data = _dry_run(capsys, repo, "--workflows")
    assert data["blockers"] == [] and data["validation"]["ok"], data["validation"]
    _golden(data, "modified_chain_workflows")
    for wf in ("plan-build", "plan-build-test", "document", "scout"):
        assert _row(data, "linked", f"workflow/{wf}")["item"] == wf
        assert f".factory/workflows/{wf}.yaml" in data["paths"]
    assert ".factory/workflows/plan.yaml" not in data["paths"]
    rc, obj = _onboard(capsys, repo, "--commit", "--workflows", "--expect", data["digest"])
    assert rc == 0, obj
    assert _adws(repo) == adws


# ── blockers and the base ─────────────────────────────────────────────────────


def test_roster_missing(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    repo = sssf_repo(tmp_path, "norost", origin=False)
    git(repo, "mv", SSSF_ROSTER, "adws/adw_sssf_config/alt.yaml")
    commit_all(repo, "only alt")
    data = _dry_run(capsys, repo)
    assert _codes(data) == ["sssf_roster_invalid"]
    rc, obj = _onboard(capsys, repo, "--commit")
    assert rc == 2 and obj["error"]["code"] == "sssf_roster_invalid"


def test_source_not_committed(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    repo = sssf_repo(tmp_path, "dirty", origin=False)
    path = repo / SSSF_PROMPTS / "builder" / "system.md"
    path.write_text(path.read_text(encoding="utf-8") + "- local\n", encoding="utf-8")
    data = _dry_run(capsys, repo)
    assert _codes(data) == ["source_not_committed"]
    assert f"{SSSF_PROMPTS}/builder/system.md" in data["blockers"][0]["message"]
    rc, obj = _onboard(capsys, repo, "--commit")
    assert rc == 2 and obj["error"]["code"] == "source_not_committed"


def test_workflows_on_pre_library(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    repo = init_repo(tmp_path / "haifa")
    copy_haifa_factory(repo)
    haifa_backlog(repo)
    commit_all(repo, "pre library")
    rc, obj = _onboard(capsys, repo, "--dry-run", "--workflows")
    assert rc == 2 and obj["error"]["code"] == "conflicting_options"


def test_base_from_detection(tmp_path: Path, library_remote: Path, capsys: Capsys) -> None:
    repo = tmp_path / "master"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "master")
    stamp_sssf(repo)
    commit_all(repo, "sssf on master")
    data = _dry_run(capsys, repo)
    assert data["state"] == "sssf" and data["base"] == "master"
    assert data["blockers"] == [], data["blockers"]
    config = yaml.safe_load(_planned(data, ".factory/config.yaml"))
    assert config["base"] == "master" and "remote" not in config
