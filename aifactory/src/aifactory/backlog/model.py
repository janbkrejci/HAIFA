"""Data model of a loaded backlog: containers (project, step, ...) and tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

from aifactory.config import ProjectSettings

VALID_STATUSES: tuple[str, ...] = ("todo", "done", "cancelled")
# computed from `depends_on`, never stored in a file
DERIVED_STATES: tuple[str, ...] = ("ready", "blocked")
INHERITED_KEYS: tuple[str, ...] = (
    "harness",
    "model",
    "thinking",
    "source",
    "target",
    "test",
    "test_timeout",
    "workflow",
    "specs_dir",
    "docs_dir",
    "workdir",
    "writes",
    "auto_continue",
    "auto_merge",
)
# inherited keys whose value must be ``true`` or ``false``
FLAG_KEYS: tuple[str, ...] = ("auto_continue", "auto_merge")
LIST_FIELDS: tuple[str, ...] = ("depends_on", "related", "writes")
INDEX_FILE = "index.md"


@dataclass
class Issue:
    """One problem in the backlog; ``path`` is relative to the repository root."""

    code: str
    message: str
    path: str
    id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message, "path": self.path, "id": self.id}


@dataclass
class Container:
    """A directory with an ``index.md`` (a project, a step, ...)."""

    id: str | None
    title: str | None
    level: str
    path: str
    index_path: str | None = None
    defaults: dict[str, object] = field(default_factory=dict)
    extra: dict[str, object] = field(default_factory=dict)
    parent: Container | None = None
    children: list[Container] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    body: str = ""


@dataclass
class Task:
    """A markdown file with a YAML header."""

    id: str
    title: str
    status: str
    level: str
    path: str
    parent: Container
    own: dict[str, object] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    body: str = ""


Node: TypeAlias = Container | Task


def node_file(node: Node) -> str:
    """The file that defines ``node``: the task file or the container's ``index.md``."""
    if isinstance(node, Container):
        return node.index_path or node.path
    return node.path


@dataclass
class Unmet:
    """A dependency that is not satisfied yet."""

    id: str
    reason: str
    missing: list[str]

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "reason": self.reason, "missing": list(self.missing)}


@dataclass
class Backlog:
    root: Path
    settings: ProjectSettings
    containers: list[Container] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    by_id: dict[str, Node] = field(default_factory=dict)
    # existing backlog root directories, relative to ``root``
    roots: list[str] = field(default_factory=list)
