"""`factory adopt`: take over an onboarded repo on a second machine (AR35, O1).

Two machines are two `HAIFA_HOME` directories; the shared library lives in a bare remote.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from onboard_repo import commit_all, git, init_repo, snapshot, write

from aifactory.config.manifest import MANIFEST_FILE, parse_manifest
from aifactory.library import store
from aifactory.library.install import init_repo as factory_init
from aifactory.library.version import workflow_version
from aifactory.onboard import adopt_repo
from cli_json import run_json

Capsys = pytest.CaptureFixture[str]
CUSTOM_WORKFLOW = b"name: custom\ndescription: Our own flow\nsteps:\n  - plan\n  - build\n"
MAPPER_SYSTEM = b"You map the repo.\n"
MAPPER_USER = b"Scout: {{prompt}}\n"
TEAM_BUILDER = b"You are the builder of this repo only.\n"
FOREIGN = "sha256:" + "f" * 64


@pytest.fixture(autouse=True)
def identity(monkeypatch: pytest.MonkeyPatch) -> None:
    for kind in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{kind}_NAME", "Ada Tester")
        monkeypatch.setenv(f"GIT_{kind}_EMAIL", "ada@example.com")
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)


def _machine(monkeypatch: pytest.MonkeyPatch, home: Path) -> Path:
    monkeypatch.setenv("HAIFA_HOME", str(home))
    return home


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    path = tmp_path / "library.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(path))
    return path


@pytest.fixture
def onboarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote: Path) -> Path:
    """Machine 1 creates the shared library and a repo installed from it, committed."""
    _machine(monkeypatch, tmp_path / "machine1")
    store.init_library("team", remote=str(remote))
    repo = init_repo(tmp_path / "repo")
    factory_init(repo)
    commit_all(repo, "install factory")
    return repo


def _add_to_manifest(repo: Path, kind: str, name: str, item: str, version: str) -> None:
    path = repo / MANIFEST_FILE
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["items"].setdefault(kind, {})[name] = {"item": item, "version": version}
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8", newline="\n")


def _add_local_items(repo: Path) -> None:
    """A workflow and an agent only this repo has, recorded in the manifest."""
    write(repo, ".factory/workflows/custom.yaml", CUSTOM_WORKFLOW)
    _add_to_manifest(repo, "workflows", "custom", "custom", workflow_version(CUSTOM_WORKFLOW))
    write(repo, ".factory/prompts/mapper/system.md", MAPPER_SYSTEM)
    write(repo, ".factory/prompts/mapper/user.md", MAPPER_USER)
    agents = repo / ".factory" / "agents.yaml"
    roster = yaml.safe_load(agents.read_text(encoding="utf-8"))
    roster["agents"].append(
        {"name": "mapper", "purpose": "Map the repo.", "harness": "claude", "thinking": "low"}
    )
    agents.write_text(yaml.safe_dump(roster, sort_keys=False), encoding="utf-8", newline="\n")
    from aifactory.library.load import load_repo_item

    mapper = load_repo_item(repo, "agent", "mapper")
    _add_to_manifest(repo, "agents", "mapper", "mapper", mapper.version)


def _items(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f"{i['type']}/{i['name']}": i for i in data["items"]}


# ── refusals ──────────────────────────────────────────────────────────────────


def test_not_onboarded(tmp_path: Path, capsys: Capsys) -> None:
    repo = init_repo(tmp_path / "plain")
    write(repo, ".factory/config.yaml", "base: main\n")
    commit_all(repo, "pre library")
    rc, obj = run_json(capsys, ["adopt", "--repo", str(repo), "--json"])
    assert rc == 2
    assert obj["error"]["code"] == "not_onboarded"
    assert obj["data"] == {"state": "pre_library", "action": "onboard"}


def test_not_a_repository(tmp_path: Path, capsys: Capsys) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()
    rc, obj = run_json(capsys, ["adopt", "--repo", str(folder), "--json"])
    assert rc == 2 and obj["error"]["code"] == "not_a_repository"


def test_without_library(
    onboarded: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote: Path, capsys: Capsys
) -> None:
    _machine(monkeypatch, tmp_path / "machine2")
    before = snapshot(onboarded)
    rc, obj = run_json(capsys, ["adopt", "--repo", str(onboarded), "--json"])
    assert rc == 2
    assert obj["error"]["code"] == "library_missing"
    assert obj["data"]["command"] == f"factory library clone {remote}"
    assert snapshot(onboarded) == before
    assert not (tmp_path / "machine2" / "library").exists()


# ── adopt ─────────────────────────────────────────────────────────────────────


def test_same_library_has_everything(
    onboarded: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote: Path, capsys: Capsys
) -> None:
    _machine(monkeypatch, tmp_path / "machine2")
    store_root = store.library_root()
    from aifactory.library.remote import clone_library

    clone_library(str(remote))
    head = git(store_root, "rev-parse", "HEAD")
    before = snapshot(onboarded)
    rc, obj = run_json(capsys, ["adopt", "--repo", str(onboarded), "--json"])
    assert rc == 0, obj
    data = obj["data"]
    assert data["state"] == "onboarded" and data["library"]["matches"] is True
    assert data["imported"] == [] and data["committed"] is False and data["plan"] is None
    assert {i["adopt"] for i in data["items"]} == {"present"}
    assert {i["state"] for i in data["items"]} == {"synced"}
    assert data["repo_changed"] is False and obj["warnings"] == []
    assert git(store_root, "rev-parse", "HEAD") == head
    assert snapshot(onboarded) == before


def test_other_library_warns(
    onboarded: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Capsys
) -> None:
    expected = parse_manifest((onboarded / MANIFEST_FILE).read_text(encoding="utf-8"), "m")
    _machine(monkeypatch, tmp_path / "machine2")
    store.init_library("private")
    before = snapshot(onboarded)
    rc, obj = run_json(capsys, ["adopt", "--repo", str(onboarded), "--json"])
    assert rc == 0, obj
    library = obj["data"]["library"]
    assert library["matches"] is False and library["name"] == "private"
    assert expected.library is not None and library["expected_id"] == expected.library.id
    assert any(w.startswith("library_mismatch:") for w in obj["warnings"])
    assert snapshot(onboarded) == before


def test_missing_items_are_imported_and_pushed(
    onboarded: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote: Path, capsys: Capsys
) -> None:
    _add_local_items(onboarded)
    commit_all(onboarded, "local items")
    write(onboarded, ".factory/workflows/custom.yaml", b"uncommitted change\n")  # base wins
    _machine(monkeypatch, tmp_path / "machine2")
    from aifactory.library.remote import clone_library

    clone_library(str(remote))
    lib = store.library_root()
    head = git(lib, "rev-parse", "HEAD")
    before = snapshot(onboarded)

    rc, obj = run_json(capsys, ["adopt", "--repo", str(onboarded), "--dry-run", "--json"])
    assert rc == 0, obj
    items = _items(obj["data"])
    assert items["workflow/custom"]["adopt"] == "import"
    assert items["agent/mapper"]["adopt"] == "import"
    assert {i["action"] for i in obj["data"]["plan"]["items"]} == {"create"}
    assert git(lib, "rev-parse", "HEAD") == head  # dry run writes nothing

    rc, obj = run_json(capsys, ["adopt", "--repo", str(onboarded), "--json"])
    assert rc == 0, obj
    data = obj["data"]
    assert sorted(data["imported"]) == ["agent/mapper", "workflow/custom"]
    assert data["committed"] is True
    items = _items(data)
    assert items["workflow/custom"]["state"] == "synced"
    assert items["agent/mapper"]["state"] == "synced"
    assert items["agent/builder"]["adopt"] == "present"
    commit = data["library_commit"]
    assert git(lib, "rev-parse", "HEAD") == commit
    # pushed to the shared remote, no force: the remote has the new commit on main
    assert git(remote, "rev-parse", "main") == commit
    assert git(remote, "show", "main:workflows/custom.yaml") + "\n" == CUSTOM_WORKFLOW.decode()
    meta = yaml.safe_load(git(remote, "show", "main:agents/mapper/agent.yaml"))
    assert meta == {
        "purpose": "Map the repo.",
        "defaults": {"harness": "claude", "thinking": "low"},
    }
    assert git(remote, "show", "main:agents/mapper/system.md") + "\n" == MAPPER_SYSTEM.decode()
    # the repo is byte for byte the same, its uncommitted change included
    assert snapshot(onboarded) == before

    rc, obj = run_json(capsys, ["adopt", "--repo", str(onboarded), "--json"])
    assert rc == 0 and obj["data"]["imported"] == [] and obj["data"]["committed"] is False


def test_missing_version_stays_unknown(
    onboarded: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote: Path, capsys: Capsys
) -> None:
    write(onboarded, ".factory/prompts/builder/system.md", TEAM_BUILDER)
    _add_to_manifest(onboarded, "agents", "builder", "builder", FOREIGN)
    commit_all(onboarded, "builder of a version the library never had")
    _machine(monkeypatch, tmp_path / "machine2")
    from aifactory.library.remote import clone_library

    clone_library(str(remote))
    lib = store.library_root()
    head = git(lib, "rev-parse", "HEAD")
    before = snapshot(onboarded)
    rc, obj = run_json(capsys, ["adopt", "--repo", str(onboarded), "--json"])
    assert rc == 0, obj
    builder = _items(obj["data"])["agent/builder"]
    assert (builder["state"], builder["adopt"]) == ("unknown", "unknown")
    assert builder["fix"] == "factory config export agent builder --as NOVE"
    assert any("agent/builder" in w for w in obj["warnings"])
    assert obj["data"]["imported"] == []
    assert git(lib, "rev-parse", "HEAD") == head
    assert snapshot(onboarded) == before


def test_adopt_api_text(
    onboarded: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote: Path, capsys: Capsys
) -> None:
    _machine(monkeypatch, tmp_path / "machine2")
    from aifactory.cli import main
    from aifactory.library.remote import clone_library

    clone_library(str(remote))
    result = adopt_repo(onboarded)
    assert result.repo.state == "onboarded" and not result.committed
    assert main(["adopt", "--repo", str(onboarded)]) == 0
    out = capsys.readouterr().out
    assert "present" in out and "the repository was not changed" in out
