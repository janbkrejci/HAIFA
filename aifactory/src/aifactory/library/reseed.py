"""Take new seed versions into the library after a HAIFA upgrade (AR16).

``seed`` in ``library.yaml`` records the seed version of every seed item. For each item of
the installed seed with version S, library head L and recorded version R:

==========================  ==========================================
L missing                   ``create``: added
L = S                       ``unchanged``
L = R                       ``update``: the team did not change it, replaced
otherwise (team change)     ``kept`` with the diff, ``take`` with ``--take``
==========================  ==========================================

``seed`` is then set to S for every seed item; keys the seed no longer has stay. The write
goes the way of every library write: lock, clean library, fetch, commit, push, fast-forward.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from aifactory import __version__
from aifactory.library import store
from aifactory.library.store import (
    LIBRARY_FILE,
    REMOTE,
    LibraryPlan,
    LibraryStoreError,
    NewFile,
    PlanItem,
    SeedItem,
    WriteResult,
    _apply,
    _dirty,
    _message,
    _planned,
    check_identity,
    check_remote,
    current_branch,
    library_root,
    read_meta,
    require_library,
    seed_versions,
    write_lock,
)
from aifactory.library.tree import item_tree_path, item_versions
from aifactory.providers import git
from aifactory.providers.publish import plan_digest


def recorded_seed(meta: Mapping[str, Any]) -> dict[str, str]:
    """``seed`` of ``library.yaml`` (empty when missing or invalid)."""
    raw = meta.get("seed")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if isinstance(v, str)}


def seed_updates(meta: Mapping[str, Any], seed: Sequence[SeedItem] | None = None) -> list[str]:
    """``type/name`` of the installed seed items whose version differs from ``seed``."""
    recorded = recorded_seed(meta)
    items = store.packaged_seed() if seed is None else seed
    return [i.key for i in items if recorded.get(i.key) != i.version]


def _parse_take(take: Iterable[str], seed: Sequence[SeedItem]) -> set[str]:
    keys = {i.key for i in seed}
    out: set[str] = set()
    for entry in take:
        kind, sep, name = entry.partition("/")
        if not sep or not kind or not name:
            raise LibraryStoreError("invalid_value", f"--take {entry!r}: use TYP/JMENO")
        if entry not in keys:
            raise LibraryStoreError("not_in_seed", f"--take {entry}: the seed has no such item")
        out.add(entry)
    return out


def _meta_file(meta: dict[str, Any], seed: dict[str, str]) -> NewFile | None:
    """The new ``library.yaml`` when ``seed`` changes, else None."""
    recorded = recorded_seed(meta)
    merged = {**recorded, **seed}
    if merged == recorded and isinstance(meta.get("seed"), dict):
        return None
    data = {**meta, "seed": merged}
    return NewFile(LIBRARY_FILE, False, yaml.safe_dump(data, sort_keys=False).encode())


def _seed_plan(root: Path, head: str, take: set[str], seed: Sequence[SeedItem]) -> LibraryPlan:
    meta = read_meta(root, head)
    recorded = recorded_seed(meta)
    heads = item_versions(root, head, [(i.type, i.name) for i in seed])
    items: list[PlanItem] = []
    new: list[NewFile] = []
    replace: list[str] = []
    for s in seed:
        lib = heads[(s.type, s.name)]
        spec = item_tree_path(s.type, s.name)
        if lib is None:
            action = "create"
        elif lib == s.version:
            action = "unchanged"
        elif lib == recorded.get(s.key):
            action = "update"
        elif s.key in take:
            action = "take"
        else:
            diff = _planned(root, head, s.files, [spec])
            items.append(PlanItem(s.type, s.name, s.version, lib, "kept", tuple(diff)))
            continue
        if action != "unchanged":
            new += s.files
            replace.append(spec)
        items.append(PlanItem(s.type, s.name, s.version, lib, action))
    meta_file = _meta_file(meta, seed_versions(seed))
    planned = _planned(root, head, new, replace)
    if meta_file is not None:
        planned += _planned(root, head, [meta_file], [LIBRARY_FILE])
    planned.sort(key=lambda f: f.path)
    source = f"seed of aifactory {__version__}"
    written = [i for i in items if i.action in ("create", "update", "take")]
    return LibraryPlan(
        str(root),
        head,
        source,
        tuple(items),
        tuple(planned),
        plan_digest("library", head, planned),
        _message("library: take the new seed", written, source),
    )


def seed_library(
    take: Iterable[str] = (),
    *,
    dry_run: bool = False,
    environ: Mapping[str, str] | None = None,
) -> WriteResult:
    """Plan taking the installed seed into the library and, without `dry_run`, commit it."""
    seed = store.packaged_seed()
    wanted = _parse_take(take, seed)
    root = library_root(environ)
    if dry_run:
        head = require_library(root)
        plan = _seed_plan(root, head, wanted, seed)
        warnings = (
            [f"the library at {root} has uncommitted changes; the write will be refused"]
            if _dirty(root)
            else []
        )
        return WriteResult(plan, True, False, None, warnings)
    require_library(root)
    check_identity(root)
    with write_lock(environ):
        head = require_library(root)
        dirty = _dirty(root)
        if dirty:
            raise LibraryStoreError(
                "library_dirty",
                f"the library at {root} has uncommitted changes: {', '.join(dirty[:5])}",
            )
        if git.has_remote(root, REMOTE):
            check_remote(root, head, current_branch(root))
        plan = _seed_plan(root, head, wanted, seed)
        if not plan.files:
            return WriteResult(plan, False, False, None)
        sha = _apply(root, plan)
    return WriteResult(plan, False, True, sha)
