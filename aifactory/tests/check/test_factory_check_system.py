"""``factory check`` on the real machine with fake ``claude``, ``codex``, ``pi``, ``gh``, ``az``.

PATH holds only the fakes and the directory of the real git, so ``uv`` and ``node`` are
missing on purpose. Every fake logs its argv; ``--offline`` must log no login or hosting
call. The check must change nothing in the repo, the library or ``$HAIFA_HOME``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from factory_check_repo import GIT_IDENTITY, commit_all, make_check_repo, write

from aifactory.cli import main
from aifactory.config import MANIFEST_FILE
from aifactory.home import haifa_home
from aifactory.library.store import init_library, library_root
from cli_json import run_json
from fake_exe import make_executable

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="PATH is limited to POSIX shell fakes and git"
)

Capsys = pytest.CaptureFixture[str]
ORIGINAL_PATH = os.environ.get("PATH", "")
FAKES = ("claude", "codex", "pi", "gh", "az")
FAKE = """\
#!/bin/sh
echo "${0##*/} $*" >> "$FAKE_LOG"
if [ "$1" = "--version" ]; then echo "1.0"; exit 0; fi
if [ "$1" = "--list-models" ]; then
  echo "provider model context"
  echo "openai gpt-5 400K"
fi
exit "${FAKE_RC:-0}"
"""
ROSTER = """\
defaults:
  harness: claude
  model: sonnet
agents:
  - name: planner
    model: opus
  - name: builder
    harness: pi
    model: openai/gpt-5
  - name: reviewer
    harness: codex
"""


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fakes on PATH next to the real git; returns the call log."""
    git = shutil.which("git")
    assert git is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in FAKES:
        path = bin_dir / name
        path.write_text(FAKE, encoding="utf-8", newline="\n")
        make_executable(path)
    calls = tmp_path / "calls.log"
    calls.write_text("", encoding="utf-8")
    # git alone, not its directory: uv or node may be installed next to it (Homebrew)
    git_dir = tmp_path / "git-bin"
    git_dir.mkdir()
    (git_dir / Path(git).name).symlink_to(Path(git).resolve())
    monkeypatch.setenv("PATH", os.pathsep.join([str(bin_dir), str(git_dir)]))
    monkeypatch.setenv("FAKE_LOG", str(calls))
    monkeypatch.delenv("FAKE_RC", raising=False)
    monkeypatch.delenv("HAIFA_LIBRARY", raising=False)
    for name in ("CLAUDE_CODE_PATH", "CODEX_PATH", "PI_PATH", "AZURE_DEVOPS_EXT_PAT"):
        monkeypatch.delenv(name, raising=False)
    for key, value in GIT_IDENTITY.items():
        monkeypatch.setenv(key, value)
    return calls


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = make_check_repo(tmp_path / "repo")
    write(repo, ".factory/agents.yaml", ROSTER)
    write(repo, ".factory/prompts/reviewer/system.md", "You review.\n")
    write(repo, ".factory/prompts/reviewer/user.md", "Review: {{prompt}}\n")
    write(repo, ".factory/config.yaml", "base: main\ngit_provider: github\n")
    commit_all(repo, "roster")
    return repo


def _lines(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8").splitlines()


def test_offline_calls_no_login_and_no_hosting(
    log: Path, repo: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo)
    rc, obj = run_json(capsys, ["check", "--offline", "--json"])
    codes = {f["code"] for f in obj["data"]["findings"]}
    assert "node_missing" in codes and "uv_missing" in codes  # not on the limited PATH
    assert rc == 1
    lines = _lines(log)
    assert lines, "the harness versions are still read"
    for line in lines:
        assert line.split()[0] not in ("gh", "az"), line
        assert line.endswith("--version"), line
    text = "\n".join(lines)
    for word in ("auth", "login", "account", "--list-models"):
        assert word not in text


def test_online_calls_every_login(
    log: Path, repo: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo)
    run_json(capsys, ["check", "--json"])
    lines = _lines(log)
    assert "claude auth status" in lines
    assert "codex login status" in lines
    assert "pi auth check --model openai/gpt-5 --json --no-refresh" in lines
    assert "pi --list-models" in lines
    assert "gh auth status --hostname github.com" in lines

    log.write_text("", encoding="utf-8")
    monkeypatch.setenv("FAKE_RC", "1")
    rc, obj = run_json(capsys, ["check", "--json"])
    assert rc == 1
    logins = [f for f in obj["data"]["findings"] if f["code"] == "harness_login"]
    assert sorted(f["message"].split()[0] for f in logins) == ["claude", "codex", "pi"]
    assert "gh_login" in {f["code"] for f in obj["data"]["findings"]}


def test_outside_a_repository(
    log: Path, tmp_path: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "plain"
    outside.mkdir()
    monkeypatch.chdir(outside)
    rc, obj = run_json(capsys, ["check", "--json"])
    data = obj["data"]
    assert rc == 0 and data["in_repo"] is False
    assert {f["scope"] for f in data["findings"]} <= {"machine", "library"}
    assert "claude auth status" in _lines(log)
    assert not [line for line in _lines(log) if line.split()[0] in ("gh", "az")]

    log.write_text("", encoding="utf-8")
    rc, obj = run_json(capsys, ["check", "--offline", "--json"])
    assert all(line.endswith("--version") for line in _lines(log))


# -- the check changes nothing --


def _tree(root: Path) -> dict[str, Any]:
    if not root.exists():
        return {}
    out: dict[str, Any] = {}
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        if path.is_file() and not path.is_symlink():
            out[rel] = (path.read_bytes(), path.stat().st_mtime_ns)
        else:
            out[rel] = None
    return out


def _git(root: Path, *args: str) -> str:
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}  # the snapshot itself must not refresh
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=env,
    )
    return proc.stdout


def _snapshot(repo: Path) -> dict[str, Any]:
    lib = library_root()
    return {
        "repo_status": _git(repo, "status", "--porcelain=v1", "-uall"),
        "repo_head": _git(repo, "rev-parse", "HEAD"),
        "repo_refs": _git(repo, "for-each-ref"),
        "repo_files": {k: v for k, v in _tree(repo).items() if not k.startswith(".git/")},
        "repo_git_index": (repo / ".git" / "index").read_bytes(),
        "library_head": _git(lib, "rev-parse", "HEAD") if lib.exists() else None,
        "library_status": _git(lib, "status", "--porcelain=v1", "-uall") if lib.exists() else None,
        "library_refs": _git(lib, "for-each-ref") if lib.exists() else None,
        "home": _tree(haifa_home()),
    }


def _install(repo: Path) -> None:
    """A manifest whose plan-build has a version the library does not know (reads H)."""
    write(
        repo,
        MANIFEST_FILE,
        "format: 1\nwritten_by: 0.2.0\nlibrary: null\nitems:\n  workflows:\n"
        f"    plan-build:\n      item: plan-build\n      version: sha256:{'0' * 64}\n",
    )
    commit_all(repo, "manifest")


@pytest.mark.parametrize("with_library", [False, True])
def test_check_changes_nothing(
    log: Path,
    repo: Path,
    tmp_path: Path,
    capsys: Capsys,
    monkeypatch: pytest.MonkeyPatch,
    with_library: bool,
) -> None:
    if with_library:
        bare = tmp_path / "remote.git"
        limited = os.environ["PATH"]
        monkeypatch.setenv("PATH", ORIGINAL_PATH)  # pushing to the bare remote needs the full PATH
        subprocess.run(["git", "init", "--bare", "-q", "-b", "main", str(bare)], check=True)
        init_library(remote=str(bare))
        monkeypatch.setenv("PATH", limited)
        write(library_root(), "draft.txt", "uncommitted\n")
        _install(repo)
    write(repo, ".factory/prompts/builder/user.md", "Changed: {{prompt}}\n")
    outside = tmp_path / "plain"
    outside.mkdir()
    before = _snapshot(repo)
    repo_codes: set[str] = set()
    for cwd, offline in ((repo, False), (repo, True), (outside, False), (outside, True)):
        monkeypatch.chdir(cwd)
        argv = ["check", "--json"] + (["--offline"] if offline else [])
        assert main(argv) in (0, 1)
        data = json.loads(capsys.readouterr().out)["data"]
        assert data["in_repo"] is (cwd == repo)
        if cwd == repo:
            repo_codes |= {f["code"] for f in data["findings"]}
        after = _snapshot(repo)
        changed = {
            key: sorted(set(before[key]) ^ set(after[key]))
            or [k for k in before[key] if before[key][k] != after[key].get(k)]
            if isinstance(before[key], dict)
            else key
            for key in before
            if before[key] != after[key]
        }
        assert changed == {}, (cwd, offline)
    home = haifa_home()
    if with_library:
        assert {"item_unknown", "library_dirty"} <= repo_codes
        assert not (home / "cache").exists()
    else:
        assert not library_root().exists()
        assert not (home / "library.lock").exists()
