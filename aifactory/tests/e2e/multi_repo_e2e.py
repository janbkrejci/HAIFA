"""Local repo and content proofs for the multi-repository browser acceptance test."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

from f3_repo import git

from fake_exe import make_executable


def fresh_repo(root: Path) -> tuple[Path, Path]:
    repo = root / "repo-b"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("fresh repository\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "initial")
    bare = root / "origin.git"
    git(root, "init", "-q", "--bare", "-b", "main", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "-u", "origin", "main")
    git(repo, "remote", "set-head", "origin", "main")
    return repo, bare


def diagnostic_tripwire(root: Path) -> tuple[Path, Path]:
    """Allow only offline installation probes; any model/hosting command fails."""
    marker = root / "model-called"
    probe = root / "probe"
    probe.write_text(
        "#!/usr/bin/env python\nimport sys\nfrom pathlib import Path\n"
        "if sys.argv[1:] in (['--version'], ['auth', 'status'], ['login', 'status']):\n"
        "    print('test CLI 1.0')\n"
        "elif sys.argv[1:] == ['--list-models']:\n"
        "    print('provider model context\\nopenai gpt-5.5 272K')\n"
        "elif sys.argv[1:] == ['app-server', '--stdio', '-c', 'mcp_servers={}', "
        "'-c', 'analytics.enabled=false']:\n"
        "    sys.exit(0)\n"
        f"else:\n    Path({str(marker)!r}).write_text(str(sys.argv))\n    sys.exit(97)\n",
        encoding="utf-8",
    )
    return make_executable(probe), marker


def repo_snapshot(repo: Path, bare: Path) -> dict[str, Any]:
    """Compare all content (including ignored files), modes, directories and Git refs."""
    files: dict[str, tuple[str, int, str]] = {}
    for directory, dirs, names in os.walk(repo, followlinks=False):
        if Path(directory) == repo:
            dirs[:] = [name for name in dirs if name != ".git"]
            names = [name for name in names if name != ".git"]
        for name in [*dirs, *names]:
            path = Path(directory) / name
            mode = path.lstat().st_mode
            if path.is_symlink():
                kind, digest = "link", os.readlink(path)
            elif path.is_dir():
                kind, digest = "directory", ""
            else:
                kind, digest = "file", hashlib.sha256(path.read_bytes()).hexdigest()
            files[path.relative_to(repo).as_posix()] = (kind, stat.S_IMODE(mode), digest)
    return {
        "exists": repo.is_dir(),
        "status": subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout,
        "head": git(repo, "rev-parse", "HEAD"),
        "refs": git(repo, "for-each-ref", "--sort=refname", "--format=%(refname) %(objectname)"),
        "remote_head": git(bare, "rev-parse", "HEAD"),
        "remote_refs": git(
            bare, "for-each-ref", "--sort=refname", "--format=%(refname) %(objectname)"
        ),
        "files": files,
    }
