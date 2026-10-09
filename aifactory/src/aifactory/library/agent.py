"""Agent items in a project: ``writes`` variables and roster entries (AR20)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from aifactory.config.settings import ProjectSettings
from aifactory.library.model import Item


def expand_writes(writes: Sequence[str] | None, settings: ProjectSettings) -> list[str] | None:
    """Replace ``$specs_dir/`` and ``$docs_dir/`` with the project's directories."""
    if writes is None:
        return None
    dirs = {"$specs_dir/": settings.specs_dir, "$docs_dir/": settings.docs_dir}
    out = []
    for entry in writes:
        for variable, value in dirs.items():
            if entry.startswith(variable):
                entry = f"{value.rstrip('/')}/" + entry[len(variable) :]
                break
        if "$" in entry:
            raise ValueError(f"writes entry {entry!r}: unknown variable")
        out.append(entry)
    return out


def roster_entry(item: Item, settings: ProjectSettings) -> dict[str, Any]:
    """The ``.factory/agents.yaml`` entry for a library agent with its default bindings."""
    if item.type != "agent" or item.defaults is None:
        raise ValueError(f"{item.type} {item.name!r} is not a library agent")
    defaults = item.defaults
    entry: dict[str, Any] = {"name": item.name, "purpose": item.purpose}
    if defaults.harness is not None:
        entry["harness"] = defaults.harness
    if defaults.model is not None:
        entry["model"] = defaults.model
    if defaults.thinking is not None:
        entry["thinking"] = defaults.thinking
    if defaults.tools is not None:
        entry["tools"] = list(defaults.tools)
    writes = expand_writes(defaults.writes, settings)
    if writes is not None:
        entry["writes"] = writes
    if defaults.color is not None:
        entry["color"] = defaults.color
    return entry
