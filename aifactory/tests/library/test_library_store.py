"""The library in the home directory: init, list, show, import (HAIFA-S05-T03)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from library_tree import SKILL_MD, WORKFLOW, put, skill_files, symlink

from aifactory.library import seed_agent_names, seed_workflow_names, store
from aifactory.library.history import cache_dir
from cli_json import run_json

Capsys = pytest.CaptureFixture[str]


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, encoding="utf-8"
    )
    return out.stdout.strip()


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake user home with HAIFA_HOME inside it and a git identity."""
    user_home = tmp_path / "home"
    user_home.mkdir()
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.setenv("USERPROFILE", str(user_home))  # Path.home() on Windows
    monkeypatch.setenv("HAIFA_HOME", str(user_home / ".config" / "haifa"))
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    for kind in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{kind}_NAME", "Ada Tester")
        monkeypatch.setenv(f"GIT_{kind}_EMAIL", "ada@example.com")
    return user_home


def _lib(home: Path) -> Path:
    return home / ".config" / "haifa" / "library"


def _init(capsys: Capsys) -> dict[str, Any]:
    rc, obj = run_json(capsys, ["library", "init", "--name", "team", "--json"])
    assert rc == 0, obj
    data: dict[str, Any] = obj["data"]
    return data


def _skill(home: Path, name: str = "lint", script: bytes = b"#!/bin/sh\nruff .\n") -> Path:
    folder = home / "work" / name
    for rel, (data, executable) in skill_files(name).items():
        put(folder, rel, script if rel == "bin/run.sh" else data, executable=executable)
    return folder


def test_init_creates_library_from_seed(home: Path, capsys: Capsys) -> None:
    data = _init(capsys)
    lib = _lib(home)
    assert data["committed"] and data["commit"] == _git(lib, "rev-parse", "HEAD")
    assert _git(lib, "rev-list", "--count", "HEAD") == "1"
    assert _git(lib, "status", "--porcelain") == ""
    meta = yaml.safe_load((lib / "library.yaml").read_text())
    assert meta["format"] == 1 and meta["name"] == "team"
    assert meta["min_factory_version"] is None
    assert len(meta["id"]) == 36
    expected = {f"agent/{n}" for n in seed_agent_names()}
    expected |= {f"workflow/{n}" for n in seed_workflow_names()}
    assert set(meta["seed"]) == expected
    assert all(v.startswith("sha256:") for v in meta["seed"].values())
    message = _git(lib, "log", "-1", "--format=%B")
    assert "agent/builder" in message and "seed" in message

    rc, obj = run_json(capsys, ["library", "init", "--json"])
    assert rc == 2 and obj["error"]["code"] == "library_exists"


def test_init_without_git_identity(
    home: Path, tmp_path: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "gitconfig"
    empty.write_text("", encoding="utf-8", newline="\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for kind in ("AUTHOR", "COMMITTER"):
        monkeypatch.delenv(f"GIT_{kind}_NAME")
        monkeypatch.delenv(f"GIT_{kind}_EMAIL")
    rc, obj = run_json(capsys, ["library", "init", "--json"])
    assert rc == 2 and obj["error"]["code"] == "git_identity_missing"
    assert not _lib(home).exists()


def test_library_path_override(home: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    other = home / "elsewhere"
    monkeypatch.setenv("HAIFA_LIBRARY", str(other))
    data = _init(capsys)
    assert data["library"] == str(other) and (other / "library.yaml").is_file()


def test_list_and_missing_library(home: Path, capsys: Capsys) -> None:
    rc, obj = run_json(capsys, ["library", "list", "--json"])
    assert rc == 2 and obj["error"]["code"] == "library_missing"
    _init(capsys)
    rc, obj = run_json(capsys, ["library", "list", "--json"])
    assert rc == 0
    items = obj["data"]["items"]
    assert {(i["type"], i["name"]) for i in items} >= {("agent", "builder"), ("workflow", "plan")}
    builder = next(i for i in items if i["name"] == "builder")
    assert builder["version"].startswith("sha256:")
    assert builder["short_version"] == builder["version"][7:15]
    assert builder["author"] == "Ada Tester <ada@example.com>" and builder["date"]
    rc, obj = run_json(capsys, ["library", "list", "--type", "workflow", "--json"])
    assert {i["type"] for i in obj["data"]["items"]} == {"workflow"}


def test_list_reads_head_not_working_tree(home: Path, capsys: Capsys) -> None:
    _init(capsys)
    put(_lib(home), "workflows/extra.yaml", WORKFLOW)
    rc, obj = run_json(capsys, ["library", "list", "--type", "workflow", "--json"])
    assert "extra" not in {i["name"] for i in obj["data"]["items"]}


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no exec bit to keep")
def test_import_skill_keeps_executable_and_shows_history(home: Path, capsys: Capsys) -> None:
    _init(capsys)
    lib = _lib(home)
    folder = _skill(home)

    rc, obj = run_json(
        capsys, ["library", "import", str(folder), "--type", "skill", "--dry-run", "--json"]
    )
    assert rc == 0, obj
    plan = obj["data"]
    assert plan["dry_run"] and not plan["committed"] and len(plan["digest"]) == 64
    assert plan["items"][0]["action"] == "create"
    paths = {f["path"]: f for f in plan["files"]}
    assert paths["skills/lint/bin/run.sh"]["mode"] == "100755"
    assert "+ruff ." in paths["skills/lint/bin/run.sh"]["diff"]
    assert not (lib / "skills").exists()

    rc, obj = run_json(capsys, ["library", "import", str(folder), "--type", "skill", "--json"])
    assert rc == 0, obj
    first = obj["data"]
    assert first["committed"] and first["digest"] == plan["digest"]
    assert os.access(lib / "skills/lint/bin/run.sh", os.X_OK)
    assert "100755" in _git(lib, "ls-tree", "HEAD", "skills/lint/bin/run.sh")
    assert _git(lib, "status", "--porcelain") == ""
    message = _git(lib, "log", "-1", "--format=%B")
    assert "skill/lint" in message and str(folder) in message

    rc, obj = run_json(capsys, ["library", "import", str(folder), "--type", "skill", "--json"])
    assert rc == 0 and not obj["data"]["committed"]
    assert obj["data"]["items"][0]["action"] == "unchanged" and obj["data"]["files"] == []

    put(folder, "bin/run.sh", b"#!/bin/sh\nruff check .\n", executable=True)
    rc, obj = run_json(capsys, ["library", "import", str(folder), "--type", "skill", "--json"])
    second = obj["data"]
    assert second["items"][0]["action"] == "update"
    assert second["items"][0]["previous_version"] == first["items"][0]["version"]

    rc, obj = run_json(capsys, ["library", "show", "skill", "lint", "--json"])
    assert rc == 0
    shown = obj["data"]
    assert [h["version"] for h in shown["history"]] == [
        first["items"][0]["version"],
        second["items"][0]["version"],
    ]
    assert [h["n"] for h in shown["history"]] == [1, 2]
    assert shown["history"][0]["commit"] == first["commit"]
    assert shown["history"][1]["author"] == "Ada Tester <ada@example.com>"
    files = {f["path"]: f for f in shown["files"]}
    assert files["bin/run.sh"]["executable"] and "ruff check" in files["bin/run.sh"]["content"]

    short = first["items"][0]["short_version"]
    rc, obj = run_json(capsys, ["library", "show", "skill", "lint", "--version", short, "--json"])
    assert rc == 0 and obj["data"]["version"] == first["items"][0]["version"]
    assert obj["data"]["commit"] == first["commit"]
    rc, obj = run_json(
        capsys, ["library", "show", "skill", "lint", "--version", "ffffffff", "--json"]
    )
    assert rc == 2 and obj["error"]["code"] == "unknown_version"
    rc, obj = run_json(capsys, ["library", "show", "skill", "nope", "--json"])
    assert rc == 2 and obj["error"]["code"] == "unknown_item"


def test_deleted_cache_is_recomputed(home: Path, capsys: Capsys) -> None:
    _init(capsys)
    folder = _skill(home)
    run_json(capsys, ["library", "import", str(folder), "--type", "skill", "--json"])
    rc, obj = run_json(capsys, ["library", "show", "skill", "lint", "--json"])
    before = obj["data"]["history"]
    cached = cache_dir() / "skill" / "lint.json"
    assert cached.is_file()
    shutil.rmtree(cache_dir())
    rc, obj = run_json(capsys, ["library", "show", "skill", "lint", "--json"])
    assert rc == 0 and obj["data"]["history"] == before
    assert cached.is_file()


def test_import_workflow_file_with_name(home: Path, capsys: Capsys) -> None:
    _init(capsys)
    path = put(home / "work", "my-plan.yaml", WORKFLOW)
    rc, obj = run_json(
        capsys, ["library", "import", str(path), "--type", "workflow", "--name", "solo", "--json"]
    )
    assert rc == 0, obj
    assert (_lib(home) / "workflows/solo.yaml").read_bytes() == WORKFLOW


def test_import_invalid_item(home: Path, capsys: Capsys) -> None:
    _init(capsys)
    folder = home / "work" / "broken"
    put(folder, "SKILL.md", SKILL_MD)  # name: lint, folder broken
    rc, obj = run_json(capsys, ["library", "import", str(folder), "--type", "skill", "--json"])
    assert rc == 2 and obj["error"]["code"] == "invalid_item"
    assert "name_mismatch" in {i["code"] for i in obj["error"]["issues"]}


def test_import_outside_home(home: Path, tmp_path: Path, capsys: Capsys) -> None:
    _init(capsys)
    outside = tmp_path / "outside" / "lint"
    for rel, (data, executable) in skill_files().items():
        put(outside, rel, data, executable=executable)
    rc, obj = run_json(capsys, ["library", "import", str(outside), "--type", "skill", "--json"])
    assert rc == 2 and obj["error"]["code"] == "outside_home"


def test_import_symlink_outside_home(home: Path, tmp_path: Path, capsys: Capsys) -> None:
    _init(capsys)
    outside = tmp_path / "outside" / "lint"
    for rel, (data, executable) in skill_files().items():
        put(outside, rel, data, executable=executable)
    link = home / "work" / "lint"
    link.parent.mkdir(parents=True)
    symlink(outside, link)
    rc, obj = run_json(capsys, ["library", "import", str(link), "--type", "skill", "--json"])
    assert rc == 2 and obj["error"]["code"] == "outside_home"

    inner = _skill(home, "fmt")
    symlink(tmp_path / "outside" / "lint" / "SKILL.md", inner / "secret")
    rc, obj = run_json(capsys, ["library", "import", str(inner), "--type", "skill", "--json"])
    assert rc == 2 and obj["error"]["code"] == "outside_home"


def test_import_refuses_dirty_library(home: Path, capsys: Capsys) -> None:
    _init(capsys)
    lib = _lib(home)
    (lib / "library.yaml").write_text(
        "format: 1\nname: changed by hand\n", encoding="utf-8", newline="\n"
    )
    folder = _skill(home)
    rc, obj = run_json(capsys, ["library", "import", str(folder), "--type", "skill", "--json"])
    assert rc == 2 and obj["error"]["code"] == "library_dirty"
    assert (lib / "library.yaml").read_text() == "format: 1\nname: changed by hand\n"
    assert _git(lib, "rev-list", "--count", "HEAD") == "1"


def test_concurrent_writes_are_serialized(home: Path, capsys: Capsys) -> None:
    _init(capsys)
    lib = _lib(home)
    folders = [_skill(home, "one"), _skill(home, "two")]
    results: list[store.WriteResult] = []
    errors: list[BaseException] = []

    def write(folder: Path) -> None:
        try:
            results.append(store.import_item(folder, "skill"))
        except BaseException as exc:  # noqa: BLE001 - reported by the assertion below
            errors.append(exc)

    with store.write_lock():
        threads = [threading.Thread(target=write, args=(f,)) for f in folders]
        for thread in threads:
            thread.start()
        time.sleep(0.5)
        assert results == [] and errors == []  # both wait for the lock
    for thread in threads:
        thread.join(timeout=60)
    assert errors == [] and len(results) == 2 and all(r.committed for r in results)
    assert _git(lib, "rev-list", "--count", "HEAD") == "3"
    assert {r.plan.head for r in results} == {
        _git(lib, "rev-parse", "HEAD~2"),
        _git(lib, "rev-parse", "HEAD~1"),
    }
    assert (lib / "skills/one/SKILL.md").is_file() and (lib / "skills/two/SKILL.md").is_file()
    assert _git(lib, "status", "--porcelain") == ""
