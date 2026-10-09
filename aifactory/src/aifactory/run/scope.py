"""What a task run may change: the task's `writes` plus its two named outputs.

The engine checks every agent phase against the agent's own `writes` and the
protected files (``permissions.permitted``). A task narrows that further: during
a task run a path inside the worktree must be allowed both by the agent **and**
by the task scope. The scope is an intersection, never a union. The session
runtime (``permissions.always_writable``) stays writable, as in the engine.

The task scope is ``effective_writes(task)`` plus exactly two files, the spec
``<specs_dir>/<task-id>-<slug>.md`` and the documentation
``<docs_dir>/<task-id>-<slug>.md``. They are files, not directories: the
planner and the documenter of the stock workflows write into the repo, and
naming the exact file makes the code enforce that outputs are named by the task
(a plan written as ``specs/<run-id>_plan.md`` is reverted and fails the phase).

``specs_dir`` and ``docs_dir`` are the nearest values set in the backlog (task,
then ``index.md`` upwards: step, project), else those of ``.factory/config.yaml``.
A backlog value that is not a directory inside the repository raises
``OutputDirError``. An agent whose own `writes` is a non-empty list may write
the two outputs even outside its `writes` (``guard.py``); ``writes: []`` may not.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from aifactory.backlog import (
    Task,
    effective_docs_dir,
    effective_specs_dir,
    effective_writes,
    slugify,
)
from aifactory.config import ProjectSettings, check_relative_dir
from aifactory.engine import permissions


def normalize(pattern: str) -> str:
    value = pattern.strip()
    while value.startswith("./"):
        value = value[2:]
    return value


def matches(path: str, pattern: str) -> bool:
    """Engine matching, plus a bare path without wildcards also covers its subtree."""
    path = normalize(path)
    pattern = normalize(pattern)
    if not pattern:
        return False
    if pattern.endswith("/") or "*" in pattern or "?" in pattern:
        return bool(permissions._matches(path, pattern))
    return path == pattern or path.startswith(pattern + "/")


@dataclass(frozen=True)
class OutputPaths:
    """Where the spec and the documentation of a task go, relative to the worktree."""

    spec: str
    doc: str


@dataclass(frozen=True)
class TaskScope:
    task_id: str
    writes: tuple[str, ...]
    outputs: tuple[str, ...]

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.writes, *self.outputs)))

    def permits(self, path: str) -> bool:
        return any(matches(path, pattern) for pattern in self.paths)

    def is_output(self, path: str) -> bool:
        """Whether ``path`` is the spec or the documentation of the task."""
        return normalize(path) in self.outputs


class OutputDirError(ValueError):
    """A ``specs_dir``/``docs_dir`` of the backlog that is not a directory inside the repo."""

    def __init__(self, key: str, value: object, reason: str) -> None:
        self.key = key
        self.value = value
        super().__init__(f"{key} {value!r} is not a directory inside the repository: {reason}")


def task_slug(task: Task) -> str:
    """The task file's name without ``.md`` and the ``<task-id>-`` prefix, else from the title."""
    stem = PurePosixPath(task.path).stem
    slug = stem.removeprefix(f"{task.id}-") if stem != task.id else ""
    slug = slug.strip("-")
    if not slug:
        slug = slugify(task.title or "")
    return slug or "task"


def _in_dir(directory: str, name: str) -> str:
    folder = normalize(directory).strip("/")
    if folder in ("", "."):
        return name
    return f"{folder}/{name}"


def _output_dir(key: str, value: object, fallback: str) -> str:
    if value is None:
        return fallback
    try:
        return check_relative_dir(value)
    except ValueError as exc:
        raise OutputDirError(key, value, str(exc)) from exc


def output_paths(task: Task, settings: ProjectSettings) -> OutputPaths:
    """Spec and documentation in the nearest ``specs_dir``/``docs_dir``, else the config's."""
    name = f"{task.id}-{task_slug(task)}.md"
    specs = _output_dir("specs_dir", effective_specs_dir(task), settings.specs_dir)
    docs = _output_dir("docs_dir", effective_docs_dir(task), settings.docs_dir)
    return OutputPaths(spec=_in_dir(specs, name), doc=_in_dir(docs, name))


def effective_task_writes(task: Task) -> tuple[str, ...]:
    """The task's effective `writes`, normalized, without empty entries."""
    return tuple(normalize(w) for w in effective_writes(task) if w.strip())


def task_scope(task: Task, outputs: OutputPaths) -> TaskScope:
    writes = effective_task_writes(task)
    return TaskScope(task_id=task.id, writes=writes, outputs=(outputs.spec, outputs.doc))


# -- overlap of write paths (auto-continue with parallel runs, ``queue.Occupancy``) --

_WILDCARDS = ("*", "?", "[")


def _has_wildcard(pattern: str) -> bool:
    return any(c in pattern for c in _WILDCARDS)


def literal_prefix(pattern: str) -> str:
    """The directory or file a pattern stays inside: everything before its first wildcard.

    ``src/app/`` -> ``src/app``, ``src/**/x.py`` -> ``src``, ``**`` -> ``""`` (the whole
    repo), ``justfile`` -> ``justfile``.
    """
    value = normalize(pattern)
    cut = min((value.index(c) for c in _WILDCARDS if c in value), default=-1)
    if cut >= 0:
        value = value[:cut]
        value = value[: value.rfind("/") + 1] if "/" in value else ""
    value = value.rstrip("/")
    return "" if value == "." else value


def paths_overlap(a: str, b: str) -> bool:
    """Whether two patterns (or a pattern and a file) may name a common path.

    Conservative: compares the literal prefixes on ``/`` boundaries, so ``src/app`` and
    ``src/application`` do not overlap, ``src/app/`` and ``src/app/x.py`` do, ``**``
    overlaps everything.
    """
    pa, pb = literal_prefix(a), literal_prefix(b)
    if not pa or not pb or pa == pb:
        return True
    return pa.startswith(pb + "/") or pb.startswith(pa + "/")


def overlaps(writes: Iterable[str], paths: Iterable[str]) -> list[str]:
    """The entries of `paths` that overlap some pattern of `writes`, sorted."""
    patterns = list(writes)
    return sorted({p for p in paths if any(paths_overlap(w, p) for w in patterns)})


def is_wide(writes: Iterable[str], root: Path | None = None) -> list[str]:
    """The `writes` that cover the whole repo or a whole top-level package ([] = not wide).

    Wide: a pattern whose literal prefix is empty (``**``, ``.``), or a single path
    segment that is a directory (``aifactory/``, ``src/*``, or an existing directory
    ``root/<name>``). ``justfile`` or ``src/app/`` alone are not wide.
    """
    wide: list[str] = []
    for pattern in writes:
        value = normalize(pattern)
        prefix = literal_prefix(value)
        if not prefix:
            wide.append(pattern)
            continue
        if "/" in prefix:
            continue
        rest = value[len(prefix) :]
        directory = (
            rest.startswith("/")
            or _has_wildcard(rest)
            or (root is not None and (root / prefix).is_dir())
        )
        if directory:
            wide.append(pattern)
    return wide
