"""Library items: types, names, files and agent defaults (AR14, AR20)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from aifactory import harness
from aifactory.engine.role_registry import Issue
from aifactory.harness.override import THINKING_LEVELS

ItemType = Literal["agent", "workflow", "skill", "extension"]
ITEM_TYPES: tuple[ItemType, ...] = ("agent", "workflow", "skill", "extension")
NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
MAX_ITEM_BYTES = 2 * 1024 * 1024
MAX_ITEM_FILES = 200
WRITES_VARIABLES = ("$specs_dir/", "$docs_dir/")


def check_name(name: str) -> bool:
    """True when ``name`` is a valid item name."""
    return NAME_RE.fullmatch(name) is not None


@dataclass(frozen=True)
class ItemFile:
    """One file of an item: relative POSIX path, executable bit, content."""

    path: str
    executable: bool
    data: bytes


class AgentDefaults(BaseModel):
    """Default bindings of a library agent. They are not part of its version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    harness: str | None = None
    model: str | None = None
    thinking: str | None = None
    tools: tuple[str, ...] | None = None
    writes: tuple[str, ...] | None = None
    color: str | None = None
    skills: tuple[str, ...] = ()
    extensions: tuple[str, ...] = ()

    @field_validator("harness")
    @classmethod
    def _harness(cls, value: str | None) -> str | None:
        return None if value is None else harness.canonical(value)

    @field_validator("thinking")
    @classmethod
    def _thinking(cls, value: str | None) -> str | None:
        if value is not None and value not in THINKING_LEVELS:
            raise ValueError(
                f"unknown thinking level {value!r}, available: {list(THINKING_LEVELS)}"
            )
        return value

    @field_validator("writes")
    @classmethod
    def _writes(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        for entry in value or ():
            if "$" not in entry:
                continue
            prefix = next((v for v in WRITES_VARIABLES if entry.startswith(v)), None)
            if prefix is None or "$" in entry[len(prefix) :]:
                raise ValueError(
                    f"writes entry {entry!r}: only {list(WRITES_VARIABLES)} may start an entry"
                )
        return value

    @field_validator("skills", "extensions")
    @classmethod
    def _names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        bad = [name for name in value if not check_name(name)]
        if bad:
            raise ValueError(f"invalid item names: {bad}")
        return value


@dataclass(frozen=True)
class Item:
    """One library item as loaded from the library or from a repo copy."""

    type: ItemType
    name: str
    files: tuple[ItemFile, ...]
    purpose: str = ""
    defaults: AgentDefaults | None = None

    @property
    def version(self) -> str:
        from aifactory.library.version import item_version

        return item_version(self)

    def file(self, path: str) -> ItemFile | None:
        """The file at ``path`` or ``None``."""
        return next((f for f in self.files if f.path == path), None)


class LibraryError(Exception):
    """A library item is invalid. ``issues`` lists every problem found."""

    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        super().__init__("; ".join(f"{i.path}: {i.code}: {i.message}" for i in issues))
