"""The ``rebuild`` code step: rebuild generated outputs that a rebase left in conflict.

Used by the ``resolve`` workflow (``factory task resolve``). A generated output
(``generated:`` in ``.factory/config.yaml``, e.g. a frontend bundle kept in git)
is never merged by hand: when both sides changed it, the right result is a new
build. The resolver agent may not touch such files (``ConflictWriteGuard``);
this step runs the configured build command for every output that has a
conflicted file, after the agent settled the other conflicts.

A build may change files only inside the outputs it rebuilds. Any other path
it changes fails the step (the resolve run then restores the branch). Without
a conflicted generated output the step does nothing.

Plain git through ``subprocess``: the workflow package must not depend on
``aifactory.run`` or ``aifactory.config``; the outputs come in as ``Generated``.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from aifactory.engine import data_types as dt

__all__ = ["Generated", "RebuildOutput", "covered", "covers", "rebuild_generated", "to_rebuild"]


@dataclass(frozen=True)
class Generated:
    """A generated output: its path (file or directory) and the command that builds it."""

    path: str
    argv: tuple[str, ...]
    timeout: int = 600


class RebuildOutput(dt.EnvelopeBase):
    """Which outputs were rebuilt and which files the builds changed."""

    built: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)


def _norm(path: str) -> str:
    text = path.strip()
    while text.startswith("./"):
        text = text[2:]
    return text.rstrip("/")


def covers(output: str, path: str) -> bool:
    """Whether ``path`` is the output ``output`` or lies inside it."""
    root = _norm(output)
    target = _norm(path)
    return bool(root) and (target == root or target.startswith(root + "/"))


def covered(path: str, outputs: Iterable[Generated]) -> bool:
    """Whether ``path`` belongs to any of ``outputs``."""
    return any(covers(g.path, path) for g in outputs)


def to_rebuild(outputs: Sequence[Generated], files: Iterable[str]) -> list[Generated]:
    """The outputs that contain at least one of ``files`` (the conflicted ones), in order."""
    names = list(files)
    return [g for g in outputs if any(covers(g.path, f) for f in names)]


def _state(root: Path) -> dict[str, str | None]:
    """Every path git reports as changed or untracked, with a hash of its content."""
    proc = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    entries = proc.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    paths: list[str] = []
    skip = False
    for entry in entries:
        if skip:
            skip = False
            continue
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC":
            skip = True  # the next entry is the rename's source
    state: dict[str, str | None] = {}
    for rel in paths:
        path = root / rel
        try:
            state[rel] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        except OSError:
            state[rel] = None
    return state


def _changed(before: dict[str, str | None], after: dict[str, str | None]) -> list[str]:
    paths = set(before) | set(after)
    return sorted(p for p in paths if before.get(p, "clean") != after.get(p, "clean"))


def rebuild_generated(
    root: Path,
    outputs: Sequence[Generated],
    files: Iterable[str],
    build: Callable[[Generated], str | None],
) -> RebuildOutput:
    """Rebuild every output of ``outputs`` that contains one of ``files``.

    ``build`` runs one output's command in ``root`` and returns why it failed,
    or None. Raises ``RuntimeError`` when a build fails or changes a file
    outside the outputs being rebuilt.
    """
    targets = to_rebuild(outputs, files)
    if not targets:
        return RebuildOutput(status="success", summary="no generated output in conflict")
    before = _state(root)
    for output in targets:
        failure = build(output)
        if failure is not None:
            raise RuntimeError(f"rebuild of {output.path} failed: {failure}")
    changed = _changed(before, _state(root))
    outside = [p for p in changed if not covered(p, targets)]
    if outside:
        raise RuntimeError(
            "the rebuild changed files outside the generated outputs "
            f"{', '.join(g.path for g in targets)}: {', '.join(outside)}"
        )
    built = [g.path for g in targets]
    return RebuildOutput(
        status="success",
        summary=f"rebuilt {', '.join(built)} ({len(changed)} files changed)",
        built=built,
        files=changed,
    )
