"""Capture the complete worktree diff against a pinned baseline."""

import subprocess
from pathlib import Path

from aifactory.testing.model import Context


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root).decode("utf-8", "surrogateescape")


def docs_only(paths: list[str]) -> bool:
    return all(
        p.endswith((".md", ".rst"))
        and ("/" not in p or p.split("/")[0] in {"docs", "specs", "app_docs", "backlog"})
        for p in paths
    )


def capture(
    root: Path,
    baseline: str | None,
    fallback: list[str],
    timeout: int,
    force_full: bool = False,
    defer_to: str | None = None,
) -> Context:
    base = baseline or git(root, "merge-base", "HEAD", "main").strip()
    base = git(root, "rev-parse", "--verify", f"{base}^{{commit}}").strip()
    paths = git(root, "diff", "--no-renames", "--name-only", "-z", base).split("\0")
    paths += git(root, "diff", "--no-renames", "--name-only", "-z").split("\0")
    paths += git(root, "diff", "--cached", "--no-renames", "--name-only", "-z").split("\0")
    paths += git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    return Context(
        repo_root=str(root.resolve()),
        baseline=base,
        head=git(root, "rev-parse", "HEAD").strip(),
        changed_paths=sorted(set(filter(None, paths))),
        force_full=force_full,
        fallback_argv=fallback,
        test_timeout=timeout,
        defer_to=defer_to,
    )
