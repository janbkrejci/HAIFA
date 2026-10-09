"""Sharing the library through a git remote (HAIFA-S05-T06).

Two homes A and B share a bare remote on disk; no network is used. A URL with a password is
mapped onto the bare remote with ``url.<path>.insteadOf``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from library_tree import put, skill_files

from aifactory.library import remote
from aifactory.providers.git import redact_url
from cli_json import run_json

Capsys = pytest.CaptureFixture[str]


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, encoding="utf-8"
    )
    return out.stdout.strip()


class Homes:
    def __init__(self, tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp = tmp
        self.mp = monkeypatch
        self.user = tmp / "home"
        self.user.mkdir()
        monkeypatch.setenv("HOME", str(self.user))
        monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
        for kind in ("AUTHOR", "COMMITTER"):
            monkeypatch.setenv(f"GIT_{kind}_NAME", "Ada Tester")
            monkeypatch.setenv(f"GIT_{kind}_EMAIL", "ada@example.com")
        self.bare = tmp / "remote.git"
        _git(tmp, "init", "--bare", "--quiet", "-b", "main", str(self.bare))

    def use(self, name: str) -> Path:
        """Switch HAIFA_HOME to home `name`; its library path."""
        home = self.user / name
        self.mp.setenv("HAIFA_HOME", str(home))
        return home / "library"

    def skill(self, name: str, text: str = "Run the linter.") -> Path:
        folder = self.user / "work" / name
        for rel, (data, executable) in skill_files(name).items():
            if rel == "SKILL.md":
                data = data.replace(b"Run the linter.", text.encode())
            put(folder, rel, data, executable=executable)
        return folder


@pytest.fixture
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Homes:
    return Homes(tmp_path, monkeypatch)


def _ok(capsys: Capsys, argv: list[str]) -> dict[str, Any]:
    rc, obj = run_json(capsys, argv)
    assert rc == 0, obj
    data: dict[str, Any] = obj["data"]
    return data


def _fail(capsys: Capsys, argv: list[str]) -> dict[str, Any]:
    rc, obj = run_json(capsys, argv)
    assert rc == 2, obj
    error: dict[str, Any] = obj["error"]
    return {**error, "data": obj["data"]}


def _import(homes: Homes, name: str, text: str = "Run it.") -> list[str]:
    path = homes.skill(name, text)
    return ["library", "import", str(path), "--type", "skill", "--json"]


def _snapshot(lib: Path) -> dict[str, bytes]:
    """Refs, HEAD, index and every working-tree file, byte for byte."""
    snap = {
        "refs": _git(lib, "for-each-ref", "--format=%(refname) %(objectname)").encode(),
        "HEAD": (lib / ".git" / "HEAD").read_bytes(),
        "index": (lib / ".git" / "index").read_bytes(),
    }
    for path in sorted(lib.rglob("*")):
        if ".git" not in path.relative_to(lib).parts and path.is_file():
            snap[str(path.relative_to(lib))] = path.read_bytes()
    return snap


def _shared(homes: Homes, capsys: Capsys) -> tuple[Path, Path]:
    """A initializes the library on the remote, B clones it."""
    lib_a = homes.use("a")
    _ok(capsys, ["library", "init", "--name", "team", "--remote", str(homes.bare), "--json"])
    lib_b = homes.use("b")
    _ok(capsys, ["library", "clone", str(homes.bare), "--json"])
    return lib_a, lib_b


def test_init_with_remote_pushes_and_clone_joins(homes: Homes, capsys: Capsys) -> None:
    lib_a = homes.use("a")
    data = _ok(capsys, ["library", "init", "--name", "team", "--remote", str(homes.bare), "--json"])
    assert _git(homes.bare, "rev-parse", "main") == data["commit"]
    assert _git(lib_a, "remote", "get-url", "origin") == str(homes.bare)
    status = _ok(capsys, ["library", "status", "--json"])
    assert status["remote"] == str(homes.bare) and status["branch"] == "main"
    assert (status["ahead"], status["behind"]) == (0, 0)
    assert status["name"] == "team" and status["dirty"] is False

    lib_b = homes.use("b")
    cloned = _ok(capsys, ["library", "clone", str(homes.bare), "--branch", "main", "--json"])
    assert cloned["library"] == str(lib_b) and cloned["id"] == status["id"]
    assert _git(lib_b, "rev-parse", "HEAD") == data["commit"]
    assert not list(lib_b.parent.glob(".library-clone-*"))
    assert _fail(capsys, ["library", "clone", str(homes.bare), "--json"])["code"] == (
        "library_exists"
    )


def test_init_refuses_non_empty_remote(homes: Homes, capsys: Capsys) -> None:
    homes.use("a")
    _ok(capsys, ["library", "init", "--remote", str(homes.bare), "--json"])
    lib_b = homes.use("b")
    error = _fail(capsys, ["library", "init", "--remote", str(homes.bare), "--json"])
    assert error["code"] == "remote_not_empty"
    assert not lib_b.exists()


def test_write_in_b_behind_a_then_pull(homes: Homes, capsys: Capsys) -> None:
    lib_a, lib_b = _shared(homes, capsys)
    homes.use("a")
    first = _ok(capsys, _import(homes, "lint"))
    assert _git(homes.bare, "rev-parse", "main") == first["commit"]
    assert _git(lib_a, "rev-parse", "HEAD") == first["commit"]

    homes.use("b")
    before = _snapshot(lib_b)
    error = _fail(capsys, _import(homes, "fmt"))
    assert error["code"] == "library_behind"
    assert error["data"]["fix"] == "factory library pull" and error["data"]["behind"] == 1
    assert {k: v for k, v in _snapshot(lib_b).items() if k != "refs"} == {
        k: v for k, v in before.items() if k != "refs"
    }
    status = _ok(capsys, ["library", "status", "--json"])
    assert (status["ahead"], status["behind"]) == (0, 1) and status["last_fetch"]

    pulled = _ok(capsys, ["library", "pull", "--json"])
    assert pulled["pulled"] == 1 and pulled["after"] == first["commit"]
    second = _ok(capsys, _import(homes, "fmt"))
    assert second["committed"]
    assert _git(homes.bare, "rev-parse", "main") == second["commit"]
    assert _git(lib_b, "rev-parse", "HEAD") == second["commit"]

    homes.use("a")
    assert _fail(capsys, _import(homes, "docs"))["code"] == "library_behind"
    status = _ok(capsys, ["library", "status", "--fetch", "--json"])
    assert status["behind"] == 1


def test_diverged_pull_and_push_refused(homes: Homes, capsys: Capsys) -> None:
    lib_a, lib_b = _shared(homes, capsys)
    homes.use("a")
    _ok(capsys, _import(homes, "lint"))
    homes.use("b")
    put(lib_b, "notes.md", "local\n")
    _git(lib_b, "add", "notes.md")
    _git(lib_b, "commit", "--quiet", "-m", "local note")
    local = _git(lib_b, "rev-parse", "HEAD")
    assert _fail(capsys, ["library", "pull", "--json"])["code"] == "library_diverged"
    assert _fail(capsys, ["library", "push", "--json"])["code"] == "library_diverged"
    assert _fail(capsys, _import(homes, "fmt"))["code"] == "library_diverged"
    assert _git(lib_b, "rev-parse", "HEAD") == local
    assert _git(homes.bare, "rev-parse", "main") == _git(lib_a, "rev-parse", "HEAD")


def test_pull_refuses_dirty_and_push_sends_local_commits(homes: Homes, capsys: Capsys) -> None:
    _lib_a, lib_b = _shared(homes, capsys)
    homes.use("b")
    put(lib_b, "notes.md", "local\n")
    assert _fail(capsys, ["library", "pull", "--json"])["code"] == "library_dirty"
    status = _ok(capsys, ["library", "status", "--json"])
    assert status["dirty"] and status["uncommitted"] == ["?? notes.md"]
    _git(lib_b, "add", "notes.md")
    _git(lib_b, "commit", "--quiet", "-m", "local note")
    assert _ok(capsys, ["library", "status", "--json"])["ahead"] == 1
    pushed = _ok(capsys, ["library", "push", "--json"])
    assert pushed["pushed"] == 1
    assert _git(homes.bare, "rev-parse", "main") == _git(lib_b, "rev-parse", "HEAD")
    assert _ok(capsys, ["library", "push", "--json"])["pushed"] == 0
    homes.use("a")
    assert _fail(capsys, ["library", "push", "--json"])["code"] == "library_behind"


def test_rejected_push_changes_nothing(homes: Homes, capsys: Capsys) -> None:
    lib_a, _lib_b = _shared(homes, capsys)
    hook = homes.bare / "hooks" / "pre-receive"
    hook.parent.mkdir(exist_ok=True)
    _git(homes.bare, "config", "core.hooksPath", str(hook.parent))
    hook.write_text(
        "#!/bin/sh\necho rejected by policy >&2\nexit 1\n", encoding="utf-8", newline="\n"
    )
    hook.chmod(0o755)
    homes.use("a")
    remote_before = _git(homes.bare, "rev-parse", "main")
    before = _snapshot(lib_a)
    error = _fail(capsys, _import(homes, "lint"))
    assert error["code"] == "push_failed"
    assert _snapshot(lib_a) == before
    assert _git(homes.bare, "rev-parse", "main") == remote_before


def test_url_with_password_is_stored_and_shown_without_it(
    homes: Homes, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "https://ada:s3cret@example.invalid/team/library.git"
    plain = "https://example.invalid/team/library.git"
    monkeypatch.setenv("GIT_CONFIG_COUNT", "2")
    for n, url in enumerate((secret, plain)):
        monkeypatch.setenv(f"GIT_CONFIG_KEY_{n}", f"url.{homes.bare}.insteadOf")
        monkeypatch.setenv(f"GIT_CONFIG_VALUE_{n}", url)
    lib_a = homes.use("a")
    _ok(capsys, ["library", "init", "--remote", secret, "--json"])
    assert _git(lib_a, "config", "--get", "remote.origin.url") == plain
    assert "s3cret" not in (lib_a / ".git" / "config").read_text()
    assert _ok(capsys, ["library", "status", "--json"])["remote"] == plain

    lib_b = homes.use("b")
    cloned = _ok(capsys, ["library", "clone", secret, "--json"])
    assert cloned["remote"] == plain
    assert "s3cret" not in (lib_b / ".git" / "config").read_text()
    error = _fail(capsys, ["library", "init", "--remote", secret, "--json"])
    assert "s3cret" not in error["message"]


def test_clone_validates_library_yaml(homes: Homes, capsys: Capsys) -> None:
    lib = homes.use("a")
    assert _fail(capsys, ["library", "clone", str(homes.bare), "--json"])["code"] == (
        "invalid_library"
    )
    work = homes.tmp / "work"
    _git(homes.tmp, "init", "--quiet", "-b", "main", str(work))
    put(work, "library.yaml", yaml.safe_dump({"format": 1, "name": "x"}))
    _git(work, "add", ".")
    _git(work, "commit", "--quiet", "-m", "no id")
    _git(work, "push", "--quiet", str(homes.bare), "main")
    assert _fail(capsys, ["library", "clone", str(homes.bare), "--json"])["code"] == (
        "invalid_library"
    )
    assert not lib.exists()
    assert _fail(capsys, ["library", "clone", str(homes.tmp / "nope"), "--json"])["code"] == (
        "clone_failed"
    )


def test_status_without_remote_and_min_version(homes: Homes, capsys: Capsys) -> None:
    homes.use("a")
    _ok(capsys, ["library", "init", "--json"])
    status = _ok(capsys, ["library", "status", "--json"])
    assert status["remote"] is None and status["ahead"] is None
    assert status["compatible"] is None and status["last_fetch"] is None
    assert _fail(capsys, ["library", "pull", "--json"])["code"] == "no_remote"
    assert _fail(capsys, ["library", "status", "--fetch", "--json"])["code"] == "no_remote"
    assert remote.compatible("0.0.1", "0.1.0") is True
    assert remote.compatible("9.0", "0.1.0") is False
    assert remote.compatible("0.10.0", "0.9.9") is False


def test_redact_url() -> None:
    assert redact_url("https://u:p@host/x.git") == "https://host/x.git"
    assert redact_url("https://token@host:8443/x") == "https://host:8443/x"
    assert redact_url("ssh://git:pw@host/x") == "ssh://git@host/x"
    assert redact_url("git@host:team/x.git") == "git@host:team/x.git"
    assert redact_url("/srv/library.git") == "/srv/library.git"
