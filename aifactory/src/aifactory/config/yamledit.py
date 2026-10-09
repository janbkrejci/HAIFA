"""Round-trip edits of ``.factory/agents.yaml``, ``config.yaml`` and ``roles.yaml``.

The files are edited with ruamel.yaml in round-trip mode, so comments, key order and
quoting stay as the operator wrote them; only the changed values move. The sequence
indentation is taken from the text (``- `` flush under its key, as PyYAML writes it, or
indented ``  - ``). Every change of these files in code goes through ``edit_yaml``, never
through ``yaml.safe_dump`` of the parsed data, which would drop the comments.

``factory config add|set|remove`` change only ``agents.yaml``; ``config.yaml`` and
``roles.yaml`` are only read by them.
"""

from __future__ import annotations

import io
import re
from collections.abc import Callable, Mapping
from typing import Any

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

_SEQ_LINE = re.compile(r"^( *)- ", re.MULTILINE)
_FIRST = ("name", "purpose", "harness", "model", "thinking")


def _indent(text: str) -> tuple[int, int, int]:
    """(mapping, sequence, offset) of the first block sequence in `text`."""
    found = _SEQ_LINE.search(text)
    if found is None or not found.group(1):
        return 2, 2, 0
    offset = len(found.group(1))
    # nested sequences may be deeper; the first one sits under a top-level key
    return 2, offset + 2, offset


def load_rt(text: str) -> tuple[YAML, Any]:
    """A round-trip loader configured for `text` and the document (an empty map if none)."""
    rt = YAML(typ="rt")
    rt.preserve_quotes = True
    rt.width = 4096
    mapping, sequence, offset = _indent(text)
    rt.indent(mapping=mapping, sequence=sequence, offset=offset)
    data = rt.load(text) if text.strip() else None
    if data is None:
        data = CommentedMap()
    return rt, data


def dump_rt(rt: YAML, data: Any) -> str:
    out = io.StringIO()
    rt.dump(data, out)
    return out.getvalue()


def edit_yaml(text: str, change: Callable[[Any], None]) -> str:
    """`text` with `change` applied to its document; ``ValueError`` when it stops parsing."""
    rt, data = load_rt(text)
    change(data)
    result = dump_rt(rt, data)
    try:
        yaml.safe_load(result)
    except yaml.YAMLError as exc:  # pragma: no cover - ruamel writes valid YAML
        raise ValueError(f"the edited YAML does not parse: {exc}") from exc
    return result


# ── agents.yaml ───────────────────────────────────────────────────────────────


def _agents(doc: Any) -> Any:
    if not isinstance(doc, CommentedMap):
        raise ValueError("agents.yaml must be a mapping")
    agents = doc.get("agents")
    if agents is None:
        agents = CommentedSeq()
        doc["agents"] = agents
    if not isinstance(agents, list):
        raise ValueError("agents.yaml: `agents` must be a list")
    return agents


def _entry(doc: Any, slot: str) -> CommentedMap:
    for entry in _agents(doc):
        if isinstance(entry, CommentedMap) and entry.get("name") == slot:
            return entry
    raise KeyError(slot)


def _value(value: Any) -> Any:
    if isinstance(value, list | tuple):
        return CommentedSeq(list(value))
    return value


def roster_add(doc: Any, entry: Mapping[str, Any]) -> None:
    """Append a roster entry; key order name, purpose, harness, model, thinking, the rest."""
    new = CommentedMap()
    for key in (*[k for k in _FIRST if k in entry], *[k for k in entry if k not in _FIRST]):
        new[key] = _value(entry[key])
    _agents(doc).append(new)


def roster_set(doc: Any, slot: str, changes: Mapping[str, Any | None]) -> None:
    """Change keys of one roster entry in place; a None value removes the key.

    A new ``harness`` replaces a legacy ``coding_agent`` key at the same position.
    """
    entry = _entry(doc, slot)
    for key, value in changes.items():
        if key == "harness" and value is not None and "coding_agent" in entry:
            if "harness" in entry:
                del entry["coding_agent"]
            else:
                pos = list(entry).index("coding_agent")
                del entry["coding_agent"]
                entry.insert(pos, "harness", value)
                continue
        if value is None:
            if key in entry:
                del entry[key]
            continue
        if key in entry and entry[key] == value:
            continue
        if key not in entry and key in _FIRST:
            # a new name/purpose/harness/model/thinking goes after the ones before it
            before = [k for k in _FIRST[: _FIRST.index(key)] if k in entry]
            if before:
                entry.insert(list(entry).index(before[-1]) + 1, key, _value(value))
                continue
        entry[key] = _value(value)


def roster_remove(doc: Any, slot: str) -> None:
    """Remove the roster entry of `slot` (``KeyError`` when there is none)."""
    agents = _agents(doc)
    for i, entry in enumerate(agents):
        if isinstance(entry, Mapping) and entry.get("name") == slot:
            del agents[i]
            return
    raise KeyError(slot)
