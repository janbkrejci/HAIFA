"""Content versions of library items (AR15): ``sha256:<hex>`` of canonical content.

Neither the item name nor its type enters the hash, so equal content has an equal
version in the library, in a repo's ``.factory/`` copy and under any name.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from aifactory.library.model import Item, ItemFile

PREFIX = "sha256:"


def _ns(data: bytes) -> bytes:
    """Netstring ``<len>:<data>,`` so concatenated parts cannot run together."""
    return str(len(data)).encode("ascii") + b":" + data + b","


def _digest(data: bytes) -> str:
    return PREFIX + hashlib.sha256(data).hexdigest()


def agent_version(purpose: str, system: bytes, user: bytes) -> str:
    """Version of an agent: purpose, ``system.md`` and ``user.md``, each with its length."""
    return _digest(_ns(purpose.encode("utf-8")) + _ns(system) + _ns(user))


def workflow_version(data: bytes) -> str:
    """Version of a workflow: the bytes of its file."""
    return _digest(data)


def tree_version(files: Iterable[ItemFile]) -> str:
    """Version of a skill or extension: sorted (path, executable, bytes) of every file."""
    parts = []
    for item_file in sorted(files, key=lambda f: f.path.encode("utf-8")):
        parts.append(
            _ns(item_file.path.encode("utf-8"))
            + (b"1" if item_file.executable else b"0")
            + _ns(item_file.data)
        )
    return _digest(b"".join(parts))


def item_version(item: Item) -> str:
    """The version of ``item`` by its type."""
    if item.type == "agent":
        system = item.file("system.md")
        user = item.file("user.md")
        return agent_version(
            item.purpose,
            system.data if system is not None else b"",
            user.data if user is not None else b"",
        )
    if item.type == "workflow":
        return workflow_version(b"".join(f.data for f in item.files))
    return tree_version(item.files)
