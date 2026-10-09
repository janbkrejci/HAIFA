"""The ``rebase`` code step: bring the branch of a worktree up to date with base.

Used by the ``resolve`` workflow (``factory task resolve``). First a plain
``git rebase <onto>``; when it goes through, the branch history is kept and no
agent is needed. When it stops on a conflict, the rebase is aborted, the branch
is reset to ``onto`` and ``git merge --squash <before>`` replays all of its
changes at once: every conflict is then in the tree with its markers, so the
resolver settles them in one step and code commits them as one commit (the
default merge strategy is squash anyway, D9).

Plain git through ``subprocess``: the workflow package must not depend on
``aifactory.run``. Every call runs with ``GIT_EDITOR=true`` so git never waits
for an editor.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from pydantic import Field

from aifactory.engine import data_types as dt

__all__ = ["RebaseOutput", "conflict_markers", "rebase_onto", "unmerged_files"]

_MARKERS = ("<<<<<<<", ">>>>>>>")


class RebaseOutput(dt.EnvelopeBase):
    """What the rebase did: onto what, from where, and which files still conflict."""

    onto: str
    before: str
    clean: bool
    conflict: bool
    files: list[str] = Field(default_factory=list)
    squashed: bool = False


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GIT_EDITOR": "true"}
    return subprocess.run(
        ["git", "-c", "core.editor=true", *args],
        cwd=root,
        capture_output=True,
        text=True,
        env=env,
        encoding="utf-8",
    )


def _must(root: Path, *args: str) -> str:
    proc = _git(root, *args)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return proc.stdout.strip()


def unmerged_files(root: Path) -> list[str]:
    """Paths git reports as unmerged in `root`, sorted, each once."""
    out = _must(root, "diff", "--name-only", "--diff-filter=U")
    return sorted({line.strip() for line in out.splitlines() if line.strip()})


def _has_marker(line: str) -> bool:
    text = line.rstrip("\r\n")
    return any(text == m or text.startswith(m + " ") for m in _MARKERS)


def conflict_markers(root: Path, files: list[str]) -> list[str]:
    """Those of `files` that still contain a ``<<<<<<<`` or ``>>>>>>>`` line.

    ``=======`` is not checked: it is a markdown heading underline. A file that
    no longer exists (deleted while resolving) has no markers.
    """
    left: list[str] = []
    for rel in files:
        path = root / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(_has_marker(line) for line in text.splitlines()):
            left.append(rel)
    return left


def _summary(onto: str, files: list[str], squashed: bool) -> str:
    if files:
        return f"rebased onto {onto[:7]}: conflicts in {', '.join(files)}"
    if squashed:
        return f"rebased onto {onto[:7]} as one squashed commit"
    return f"rebased onto {onto[:7]} cleanly"


def rebase_onto(root: Path, onto: str) -> RebaseOutput:
    """Rebase the branch checked out in `root` onto `onto` (see the module docstring).

    Raises ``RuntimeError`` on any git failure other than the expected conflict.
    """
    before = _must(root, "rev-parse", "HEAD")
    onto = _must(root, "rev-parse", "--verify", "--quiet", f"{onto}^{{commit}}")

    def clean(squashed: bool = False) -> RebaseOutput:
        return RebaseOutput(
            status="success",
            summary=_summary(onto, [], squashed),
            onto=onto,
            before=before,
            clean=True,
            conflict=False,
            squashed=squashed,
        )

    if _git(root, "merge-base", "--is-ancestor", onto, "HEAD").returncode == 0:
        return clean()
    if _git(root, "rebase", "-q", "--no-autostash", onto).returncode == 0:
        return clean()

    _git(root, "rebase", "--abort")
    _must(root, "reset", "--hard", "-q", before)
    _must(root, "reset", "--hard", "-q", onto)
    merge = _git(root, "merge", "--squash", before)
    files = unmerged_files(root)
    if merge.returncode != 0 and not files:
        detail = merge.stderr.strip() or merge.stdout.strip()
        raise RuntimeError(f"git merge --squash {before[:7]} failed: {detail}")
    if not files:
        if _git(root, "diff", "--cached", "--quiet").returncode != 0:
            _must(root, "commit", "-q", "-m", f"Rebase onto {onto[:7]} (squash of {before[:7]})")
        return clean(squashed=True)
    return RebaseOutput(
        status="success",
        summary=_summary(onto, files, True),
        onto=onto,
        before=before,
        clean=False,
        conflict=True,
        files=files,
        squashed=True,
    )
