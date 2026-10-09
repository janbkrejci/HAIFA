"""Migrations of the repo configuration that ``factory update`` offers (AR25, D26).

A migration changes one file of the shared configuration when its detector finds the
old form. The detector makes it idempotent: once applied, it no longer matches, so the
manifest records nothing. ``factory update`` lists every detected migration with its diff
and applies it only with ``--migrate ID``. Files are edited by a ruamel.yaml round trip,
so comments, key order and flow style stay.

``m001``: ``levels: [module, step, task]`` in ``.factory/config.yaml`` becomes
``[project, step, task]`` (the top backlog level was renamed).
"""

from __future__ import annotations

import difflib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import yaml

from aifactory.config.settings import CONFIG_FILE


@dataclass(frozen=True)
class Migration:
    """One migration: the file it changes, its detector and the edit."""

    id: str
    title: str
    path: str
    detect: Callable[[bytes], bool]
    apply: Callable[[str], str]

    def diff(self, before: str, after: str) -> str:
        return "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{self.path}",
                tofile=f"b/{self.path}",
            )
        )


def _levels(data: bytes) -> list[Any] | None:
    try:
        raw = yaml.safe_load(data.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError):
        return None
    levels = raw.get("levels") if isinstance(raw, dict) else None
    return levels if isinstance(levels, list) else None


def _m001_detect(data: bytes) -> bool:
    levels = _levels(data)
    return levels is not None and "module" in levels and "project" not in levels


def _m001_apply(text: str) -> str:
    from aifactory.config.yamledit import edit_yaml

    def change(doc: Any) -> None:
        seq = doc["levels"]
        for i, value in enumerate(seq):
            if value == "module":
                seq[i] = "project"  # in place: the sequence keeps its style and comments

    return edit_yaml(text, change)


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        "m001",
        "levels: module -> project",
        CONFIG_FILE,
        _m001_detect,
        _m001_apply,
    ),
)


def known_ids() -> list[str]:
    return [m.id for m in MIGRATIONS]


def detected(files: Mapping[str, bytes]) -> list[Migration]:
    """The migrations whose detector matches `files` (relative path -> bytes)."""
    out: list[Migration] = []
    for migration in MIGRATIONS:
        data = files.get(migration.path)
        if data is not None and migration.detect(data):
            out.append(migration)
    return out


__all__ = ["MIGRATIONS", "Migration", "detected", "known_ids"]
