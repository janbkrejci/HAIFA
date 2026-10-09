"""Item states against the library (AR23, L4) over a temporary library history."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from library_tree import put

from aifactory.config import MANIFEST_FILE
from aifactory.library import seed_items, workflow_version
from aifactory.library.state import item_state, repo_items
from aifactory.workflow import DEFAULT_WORKFLOWS_DIR
from cli_json import run_json

Capsys = pytest.CaptureFixture[str]

V1 = b"name: w\ndescription: one\nsteps: [plan]\n"
V2 = b"name: w\ndescription: two\nsteps: [plan]\n"
OWN = b"name: w\ndescription: own\nsteps: [plan]\n"
FOREIGN = "sha256:" + "0" * 64


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    return proc.stdout.strip()


def _commit(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


@pytest.mark.parametrize(
    ("recorded", "r", "m", "lib", "h", "state"),
    [
        (False, "a", None, None, [], "local"),
        (True, None, "a", "a", ["a"], "missing"),
        (True, "b", "a", "b", ["a", "b"], "synced"),
        (True, "b", "x", "b", ["a", "b"], "synced"),  # synced wins over unknown
        (True, "c", "x", "b", ["a", "b"], "unknown"),
        (True, "a", "a", "b", ["a", "b"], "outdated"),
        (True, "c", "a", "a", ["a"], "modified"),
        (True, "c", "a", "b", ["a", "b"], "diverged"),
    ],
)
def test_state_order(
    recorded: bool, r: str | None, m: str | None, lib: str | None, h: list[str], state: str
) -> None:
    assert item_state(recorded, r, m, lib, h) == state


@pytest.fixture
def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A library with workflow `w` at V1 then V2 and workflow `stay` only at V1."""
    root = tmp_path / "library"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    put(root, "library.yaml", "format: 1\nid: x\nname: test\n")
    put(root, "workflows/w.yaml", V1)
    put(root, "workflows/stay.yaml", V1)
    _commit(root, "v1")
    put(root, "workflows/w.yaml", V2)
    _commit(root, "v2")
    monkeypatch.setenv("HAIFA_LIBRARY", str(root))
    return root


def _repo(path: Path, workflows: dict[str, bytes], manifest: dict[str, tuple[str, str]]) -> Path:
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    put(path, ".factory/config.yaml", "base: main\n")
    for name, data in workflows.items():
        put(path, f".factory/workflows/{name}.yaml", data)
    entries = {slot: {"item": item, "version": v} for slot, (item, v) in manifest.items()}
    manifest_data = {
        "format": 1,
        "written_by": "0.2.0",
        "library": None,
        "items": {"workflows": entries},
    }
    put(path, MANIFEST_FILE, yaml.safe_dump(manifest_data))
    _commit(path, "factory")
    return path


def _states(data: dict[str, Any]) -> dict[str, str]:
    return {i["name"]: i["state"] for i in data["items"]}


def test_every_state_over_library_history(tmp_path: Path, library: Path) -> None:
    v1, v2 = workflow_version(V1), workflow_version(V2)
    repo = _repo(
        tmp_path / "repo",
        {
            "synced": V2,
            "outdated": V1,
            "modified": OWN,
            "diverged": OWN,
            "unknown": OWN,
            "own": OWN,
        },
        {
            "synced": ("w", v1),
            "outdated": ("w", v1),
            "modified": ("stay", v1),
            "diverged": ("w", v1),
            "unknown": ("w", FOREIGN),
            "missing": ("w", v1),
        },
    )
    data = repo_items(repo)
    assert data["library"]["source"] == "library"
    assert data["format"] == 1
    assert _states(data) == {
        "diverged": "diverged",
        "missing": "missing",
        "modified": "modified",
        "outdated": "outdated",
        "own": "local",
        "synced": "synced",
        "unknown": "unknown",
    }
    by_name = {i["name"]: i for i in data["items"]}
    assert by_name["outdated"]["repo_version"] == v1
    assert by_name["outdated"]["manifest_version"] == v1
    assert by_name["outdated"]["library_version"] == v2
    assert by_name["outdated"]["item"] == "w"
    assert by_name["own"]["item"] is None


def test_working_tree_or_base(tmp_path: Path, library: Path) -> None:
    v1 = workflow_version(V1)
    repo = _repo(tmp_path / "repo", {"x": V1}, {"x": ("w", v1)})
    put(repo, ".factory/workflows/x.yaml", V2)
    assert _states(repo_items(repo)) == {"x": "synced"}
    assert _states(repo_items(repo, "")) == {"x": "outdated"}
    assert _states(repo_items(repo, "main")) == {"x": "outdated"}


def test_seed_without_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAIFA_LIBRARY", str(tmp_path / "none"))
    plan = (DEFAULT_WORKFLOWS_DIR / "plan.yaml").read_bytes()
    seed = {(i.type, i.name): i.version for i in seed_items()}[("workflow", "plan")]
    assert seed == workflow_version(plan)
    repo = _repo(
        tmp_path / "repo",
        {"plan": plan, "mine": OWN, "gone": OWN},
        {"plan": ("plan", seed), "mine": ("plan", seed), "gone": ("plan", FOREIGN)},
    )
    data = repo_items(repo)
    assert data["library"] == {"source": "seed", "path": None, "head": None}
    assert _states(data) == {"gone": "unknown", "mine": "modified", "plan": "synced"}


def test_repo_without_manifest_is_all_local(tmp_path: Path, library: Path) -> None:
    repo = _repo(tmp_path / "repo", {"x": V1}, {})
    (repo / MANIFEST_FILE).unlink()
    data = repo_items(repo)
    assert data["manifest"] is None
    assert data["format"] == 0
    assert _states(data) == {"x": "local"}


def test_cli_config_items(tmp_path: Path, library: Path, capsys: Capsys) -> None:
    v1 = workflow_version(V1)
    repo = _repo(tmp_path / "repo", {"x": V1}, {"x": ("w", v1)})
    rc, obj = run_json(capsys, ["config", "items", "--repo", str(repo), "--json"])
    assert rc == 0
    assert obj["data"]["base"] is None
    [item] = obj["data"]["items"]
    assert item["state"] == "outdated"
    assert item["library_version"] == workflow_version(V2)
    rc, obj = run_json(capsys, ["config", "items", "--repo", str(repo), "--base", "--json"])
    assert rc == 0
    assert obj["data"]["base"] == "main"
    put(repo, MANIFEST_FILE, "format: 2\nwritten_by: 9.0.0\n")
    rc, obj = run_json(capsys, ["config", "items", "--repo", str(repo), "--json"])
    assert rc == 2
    assert obj["error"]["code"] == "format_unsupported"
