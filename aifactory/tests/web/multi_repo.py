"""Git repos and a client for the multi-repo dashboard tests (no model, no network)."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from aifactory.config.manifest import (
    MANIFEST_FILE,
    LibraryRef,
    Manifest,
    Onboarding,
    dump_manifest,
)
from aifactory.web import create_multi_app

BASE = "http://127.0.0.1:4700"
CONFIG = "base: main\n"
AGENTS = "defaults:\n  harness: claude\nagents:\n  - name: builder\n    purpose: Build.\n"
SSSF_ROSTER = "adws/adw_sssf_config/sssf.config.yaml"
MANIFEST = Manifest(
    written_by="0.1.0",
    library=LibraryRef(id="lib-1", name="team", remote="https://example.com/lib.git"),
    onboarding=Onboarding(
        source="sssf",
        source_commit="a" * 40,
        at="2026-10-02T10:00:00Z",
        by="Ada Tester",
        factory="0.1.0",
        library_commit="b" * 40,
    ),
)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _clear_readonly(func: Callable[[str], Any], path: str, _exc: object) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def rmtree(path: Path) -> None:
    """``shutil.rmtree``; on Windows it clears the read-only bit git objects have first."""
    if sys.platform == "win32":
        shutil.rmtree(path, onerror=_clear_readonly)
    else:
        shutil.rmtree(path)


def symlink(link: Path, target: Path) -> None:
    """``link.symlink_to(target)``; on Windows skip the test when symlinks need a privilege."""
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError as error:
        if sys.platform == "win32":
            pytest.skip(f"cannot create symlinks here: {error}")
        raise


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def commit_all(root: Path, message: str = "commit") -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", message)
    return git(root, "rev-parse", "HEAD")


def init_repo(path: Path, *, commit: bool = True) -> Path:
    """A git repo on ``main`` at ``path`` (with one commit unless ``commit`` is False)."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    if commit:
        write(path, "README.md", "readme\n")
        commit_all(path, "readme")
    return path.resolve()


def onboard(root: Path) -> None:
    """Commit config, agents and a manifest: the ``onboarded`` state."""
    write(root, ".factory/config.yaml", CONFIG)
    write(root, ".factory/agents.yaml", AGENTS)
    write(root, MANIFEST_FILE, dump_manifest(MANIFEST))
    commit_all(root, "onboard")


def multi_client(home: Path, tmp_path: Path, **kwargs: Any) -> TestClient:
    app = create_multi_app(home=home, static_dir=tmp_path / "nostatic", **kwargs)
    return TestClient(app, base_url=BASE)


def register(client: TestClient, path: Path) -> dict[str, Any]:
    """Register ``path`` in the client's registry without installing factory (what
    ``POST /api/repos`` did before it installed); returns the ``repo_status`` item."""
    from aifactory.web.repos import register_repo, repo_status

    entry, _created, _warnings = register_repo(client.app.state.registry, str(path))  # type: ignore[attr-defined]
    return repo_status(entry)
