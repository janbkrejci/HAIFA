"""The library a repo inherits from: HEAD of ``$HAIFA_HOME/library``, else the seed.

Agents, workflows, skills and extensions are looked up in the repo's ``.factory/`` first
and here second; the repo copy wins. The library is read from the tree of its HEAD
commit, never from its working tree. Without a library (no repository or no commit) the
packaged seed is used instead; the two are never mixed. Items that do not validate are
left out, as if the library did not have them.

A snapshot is cached per library commit, so loading the configuration again costs one
``git rev-parse``.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aifactory import yamlload
from aifactory.library.model import Item, ItemType

_CACHE: dict[tuple[str, str], LibrarySnapshot] = {}
_CACHE_LIMIT = 8


@dataclass(frozen=True)
class LibrarySnapshot:
    """Every valid item of one library commit (``commit`` None: the packaged seed)."""

    commit: str | None
    agents: Mapping[str, Item] = field(default_factory=dict)
    workflows: Mapping[str, Item] = field(default_factory=dict)
    skills: Mapping[str, Item] = field(default_factory=dict)
    extensions: Mapping[str, Item] = field(default_factory=dict)
    _parsed: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def label(self) -> str:
        return "seed" if self.commit is None else f"library@{self.commit[:7]}"

    def workflow_data(self, name: str) -> dict[str, Any]:
        """The parsed YAML of workflow `name` (a copy; parsed once per snapshot)."""
        if name not in self._parsed:
            self._parsed[name] = yamlload.safe_load(self.workflows[name].files[0].data)
        return copy.deepcopy(self._parsed[name])

    def of(self, kind: ItemType) -> Mapping[str, Item]:
        return {
            "agent": self.agents,
            "workflow": self.workflows,
            "skill": self.skills,
            "extension": self.extensions,
        }[kind]


def with_item(snapshot: LibrarySnapshot, item: Item) -> LibrarySnapshot:
    """`snapshot` with `item` added or replaced (what the library holds after a move)."""
    items = {**snapshot.of(item.type), item.name: item}
    return LibrarySnapshot(
        commit=snapshot.commit,
        agents=items if item.type == "agent" else snapshot.agents,
        workflows=items if item.type == "workflow" else snapshot.workflows,
        skills=items if item.type == "skill" else snapshot.skills,
        extensions=items if item.type == "extension" else snapshot.extensions,
    )


def _by_type(items: list[Item]) -> dict[ItemType, dict[str, Item]]:
    out: dict[ItemType, dict[str, Item]] = {
        "agent": {},
        "workflow": {},
        "skill": {},
        "extension": {},
    }
    for item in items:
        out[item.type][item.name] = item
    return out


def _snapshot(commit: str | None, items: list[Item]) -> LibrarySnapshot:
    found = _by_type(items)
    return LibrarySnapshot(
        commit=commit,
        agents=found["agent"],
        workflows=found["workflow"],
        skills=found["skill"],
        extensions=found["extension"],
    )


def seed_snapshot() -> LibrarySnapshot:
    """The packaged seed. Its workflows are the package defaults, read without validating
    them again (``tests/workflow/test_default_workflows.py`` does)."""
    key = ("", "seed")
    cached = _CACHE.get(key)
    if cached is None:
        from aifactory.library.load import load_library_item
        from aifactory.library.model import ItemFile
        from aifactory.library.seed import (
            SEED_DIR,
            seed_agent_names,
            seed_extension_names,
            seed_workflow_names,
        )
        from aifactory.workflow.parse import DEFAULT_WORKFLOWS_DIR

        items = [load_library_item(SEED_DIR, "agent", n) for n in seed_agent_names()]
        items += [load_library_item(SEED_DIR, "extension", n) for n in seed_extension_names()]
        for name in seed_workflow_names():
            data = (DEFAULT_WORKFLOWS_DIR / f"{name}.yaml").read_bytes()
            items.append(Item("workflow", name, (ItemFile(f"{name}.yaml", False, data),)))
        cached = _CACHE[key] = _snapshot(None, items)
    return cached


def library_head(root: Path) -> str | None:
    """The HEAD commit of the library at ``root``, or None when there is none."""
    from aifactory.providers import git

    if not (root / ".git").exists():
        return None
    return git.rev_parse(root, "HEAD")


def commit_snapshot(root: Path, commit: str) -> LibrarySnapshot:
    """Every valid item of ``commit`` of the library at ``root``."""
    key = (str(root), commit)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    from aifactory.library.tree import item_paths, read_items, tree_files

    keys = item_paths(tree_files(root, commit))
    loaded = read_items(root, commit, keys)
    items = [item for item, issues, _ in loaded.values() if item is not None and not issues]
    snapshot = _snapshot(commit, items)
    if len(_CACHE) >= _CACHE_LIMIT:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = snapshot
    return snapshot


def library_snapshot(environ: Mapping[str, str] | None = None) -> LibrarySnapshot:
    """The items a repo inherits now: the library HEAD, else the seed."""
    from aifactory.library.store import library_root

    root = library_root(environ)
    head = library_head(root)
    if head is None:
        return seed_snapshot()
    return commit_snapshot(root, head)


def snapshot_at(commit: str | None, environ: Mapping[str, str] | None = None) -> LibrarySnapshot:
    """The snapshot of library ``commit`` (None: the seed)."""
    if commit is None:
        return seed_snapshot()
    from aifactory.library.store import library_root

    return commit_snapshot(library_root(environ), commit)


IGNORE_ALL = "*\n"
"""The ``.gitignore`` of a copied item: git sees none of its files."""


def _write_item(dest: Path, item: Item) -> None:
    for f in item.files:
        path = dest / f.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f.data)
        path.chmod(0o755 if f.executable else 0o644)
    (dest / ".gitignore").write_text(IGNORE_ALL, encoding="utf-8")


def copy_library_items(worktree: Path, commit: str | None) -> list[str]:
    """Copy the library skills and extensions the run's checkout lacks into it.

    A skill goes to ``.claude/skills/<name>/`` (claude) and ``.agents/skills/<name>/``
    (codex, pi), an extension to ``.factory/extensions/<name>/``; a skill or extension
    the repo has itself is left alone. Each copy holds a ``.gitignore`` that ignores it,
    so it is never committed and the write guard does not see it. Returns the folders
    written, relative to ``worktree``.
    """
    from aifactory.config.loader import EXTENSIONS_DIR, SKILLS_DIR, SKILLS_MIRROR_DIR

    snapshot = snapshot_at(commit)
    written: list[str] = []
    for name, item in snapshot.skills.items():
        if (worktree / SKILLS_DIR / name).exists():
            continue
        for top in (SKILLS_DIR, SKILLS_MIRROR_DIR):
            _write_item(worktree / top / name, item)
            written.append(f"{top}/{name}")
    for name, item in snapshot.extensions.items():
        if (worktree / EXTENSIONS_DIR / name).exists():
            continue
        _write_item(worktree / EXTENSIONS_DIR / name, item)
        written.append(f"{EXTENSIONS_DIR}/{name}")
    return written
