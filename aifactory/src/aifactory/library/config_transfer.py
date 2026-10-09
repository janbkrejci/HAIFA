"""``factory config export|revert|diff``: move items between the repo and the library.

``export TYPE NAME [--as NEW]`` writes the copy in the repo into the library and then
records it in ``.factory/manifest.yaml`` (the item it is connected to and its version):

- an item with a manifest entry becomes the next version of its library item;
- with ``--as NEW`` (agents and workflows) or for a ``local`` item (no manifest entry) it
  becomes a new library item; a library item of that name with other content is
  ``item_exists`` (pick another name with ``--as``), one with the same content is only
  connected;
- when the library head moved on since the manifest version and the repo copy differs
  from it, the export is ``library_changed_since`` (fix: ``factory update`` or ``--as``).

An exported agent keeps the ``agent.yaml`` of its library item with the purpose of the
roster; a new one gets its ``defaults`` from the roster entry (``$specs_dir/`` and
``$docs_dir/`` put back into ``writes``).

The library is written first (``store.import_items``: lock, fetch, push without force,
then fast-forward), the repo after it (working tree, ``--commit`` or ``--commit --pr``,
as ``config add``). A rejected library push stops before the repo is touched. When the
repo write fails after the library push, the library holds an unused version: the same
export run again finds the repo copy equal to the library head and only connects it.

``revert TYPE NAME [--to manifest|head]`` puts the copy in the repo back to the manifest
version (found in the library history; ``unknown_version`` when it is not there, state
``unknown``) or to the library head, which also moves the manifest version. Bindings in
``agents.yaml`` stay; only the purpose of an agent follows the version.

``diff TYPE NAME`` only reads: the files of the repo copy against the manifest version and
against the library head (unified diffs, library version first).
"""

from __future__ import annotations

import difflib
import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from aifactory.config.loader import AGENTS_FILE
from aifactory.config.manifest import Manifest, ManifestEntry
from aifactory.config.settings import ProjectSettings
from aifactory.library import history as hist
from aifactory.library.config_edit import (
    Change,
    RepoState,
    _bindings,
    _check_type,
    _diff,
    _edit_agents,
    _item_files,
    _manifest_set,
    _new_entry,
    _with_manifest,
    read_state,
)
from aifactory.library.model import Item, ItemType
from aifactory.library.store import LibraryStoreError, NewFile, SeedItem
from aifactory.providers import git

if TYPE_CHECKING:
    from aifactory.library.install import _Source

REVERT_TARGETS = ("manifest", "head")


# ── helpers ───────────────────────────────────────────────────────────────────


def _library(source: _Source, environ: Mapping[str, str] | None) -> tuple[Path, str]:
    """The root and HEAD of the library; ``library_missing`` without one (no seed export)."""
    from aifactory.library.store import library_root

    if source.root is None or source.head is None:
        raise LibraryStoreError(
            "library_missing",
            f"no library at {library_root(environ)}; export needs one: factory library init "
            "(or factory library clone)",
        )
    return source.root, source.head


def repo_item(state: RepoState, kind: ItemType, name: str) -> Item:
    """The copy of the item in the repo state; ``unknown_item`` or ``invalid_item``."""
    from aifactory.library.load import check_repo_item

    if not state.item_paths(kind, name) and not (
        kind == "agent" and state.roster_entry(name) is not None
    ):
        raise LibraryStoreError("unknown_item", f"no {kind} {name!r} in the repo")
    with state.materialized() as tmp:
        item, issues = check_repo_item(tmp, kind, name)
    if item is None or issues:
        raise LibraryStoreError(
            "invalid_item", f"the {kind} {name!r} in the repo is not valid", issues=issues
        )
    return item


def library_version(
    source: _Source,
    environ: Mapping[str, str] | None,
    kind: ItemType,
    name: str,
    version: str | None,
) -> tuple[Item, str | None]:
    """The library item at the head (`version` None) or at `version` of its history.

    Returns the item and the library commit it was read from (None for the seed).
    """
    from aifactory.library.tree import read_items

    if source.root is None or source.head is None:
        item = source.load(kind, [name])[name]
        if version is not None and item.version != version:
            raise _unknown_version(kind, name, version, "the seed")
        return item, None
    if version is None:
        return source.load(kind, [name])[name], source.head
    revisions = hist.history(source.root, kind, name, environ)
    hits = [r for r in revisions if r.version == version]
    if not hits:
        raise _unknown_version(kind, name, version, f"the library at {source.root}")
    commit = hits[-1].commit
    found, issues, files = read_items(source.root, commit, [(kind, name)])[(kind, name)]
    if found is None or issues or not files:
        raise LibraryStoreError(
            "invalid_item",
            f"{kind} {name!r} at {commit[:12]} of the library is not valid",
            issues=issues,
        )
    return found, commit


def _unknown_version(kind: str, name: str, version: str, where: str) -> LibraryStoreError:
    return LibraryStoreError(
        "unknown_version",
        f"the manifest version {hist.short(version)} of {kind} {name!r} is not in the history "
        f"of {where} (state unknown); revert --to head or export it",
        data={"state": "unknown", "version": version, "fix": "--to head"},
    )


def _unexpand(writes: list[str], settings: ProjectSettings) -> list[str]:
    out: list[str] = []
    for entry in writes:
        for variable, value in (
            ("$specs_dir/", settings.specs_dir),
            ("$docs_dir/", settings.docs_dir),
        ):
            prefix = value.rstrip("/") + "/"
            if entry.startswith(prefix):
                entry = variable + entry[len(prefix) :]
                break
        out.append(entry)
    return out


def _agent_yaml(
    state: RepoState,
    root: Path,
    head: str,
    names: list[str],
    item: Item,
    slot: str,
) -> bytes:
    """``agent.yaml`` of an exported agent: the library one with the roster purpose, else
    a new one with the roster bindings as defaults."""
    from aifactory.config.yamledit import edit_yaml
    from aifactory.library.load import library_path

    for name in names:
        found = git.blob_at(root, head, f"{library_path('agent', name)}/agent.yaml")
        if found is None:
            continue
        text = git.read_blob(root, found[1]).decode("utf-8", "replace")
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError:
            continue
        if not isinstance(raw, dict):
            continue
        if raw.get("purpose") == item.purpose:
            return text.encode("utf-8")

        def set_purpose(doc: Any) -> None:
            doc["purpose"] = item.purpose

        try:
            return edit_yaml(text, set_purpose).encode("utf-8")
        except ValueError:
            continue
    binding = _bindings(state.roster_entry(slot))
    defaults: dict[str, Any] = {}
    for key in ("harness", "model", "thinking"):
        if isinstance(binding.get(key), str):
            defaults[key] = binding[key]
    for key in ("tools", "writes"):
        value = binding.get(key)
        if isinstance(value, list):
            values = [str(v) for v in value]
            defaults[key] = _unexpand(values, state.settings) if key == "writes" else values
    if isinstance(binding.get("color"), str):
        defaults["color"] = binding["color"]
    data: dict[str, Any] = {"purpose": item.purpose}
    if defaults:
        data["defaults"] = defaults
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True).encode("utf-8")


def _library_item(item: Item, name: str, agent_yaml: bytes | None) -> SeedItem:
    """The files of `item` in the library layout under `name`."""
    from aifactory.library.load import library_path

    rel = library_path(item.type, name)
    files: list[NewFile] = []
    if item.type == "agent":
        files.append(NewFile(f"{rel}/agent.yaml", False, agent_yaml or b""))
        for prompt in ("system.md", "user.md"):
            found = item.file(prompt)
            files.append(
                NewFile(
                    f"{rel}/{prompt}",
                    bool(found and found.executable),
                    found.data if found else b"",
                )
            )
    elif item.type == "workflow":
        files.append(NewFile(rel, False, item.files[0].data))
    else:
        files += [NewFile(f"{rel}/{f.path}", f.executable, f.data) for f in item.files]
    return SeedItem(item.type, name, item.version, tuple(files))


def _connect(change: Change, manifest: Manifest, new: Manifest, source: _Source) -> Manifest:
    library = source.library
    if library is None:
        return new
    if manifest.library is None:
        return new.model_copy(update={"library": library})
    if manifest.library.id != library.id:
        change.warnings.append(
            f"library_mismatch: the repo came from the library {manifest.library.name} "
            f"({manifest.library.id}), the item now is in {library.name} ({library.id})"
        )
    return new


# ── export ────────────────────────────────────────────────────────────────────


def plan_export(
    state: RepoState,
    source: _Source,
    environ: Mapping[str, str] | None,
    type: str,
    name: str,
    *,
    slot: str | None = None,
) -> Change:
    """The change of ``config export``: library items to write and the new manifest."""
    from aifactory.library.tree import item_versions

    kind = _check_type(type, name)
    if slot is not None:
        if kind not in ("agent", "workflow"):
            raise LibraryStoreError(
                "conflicting_options",
                f"--as is only for agents and workflows; a {kind} keeps its name",
            )
        _check_type(kind, slot, "name")
    manifest = state.manifest
    root, head = _library(source, environ)
    entry = manifest.entry(kind, name)
    copy = repo_item(state, kind, name)
    r = copy.version
    m = entry.version if entry is not None else None
    item_name = slot or (entry.item if entry is not None else name)
    lib = item_versions(root, head, [(kind, item_name)])[(kind, item_name)]
    connected = slot is None and entry is not None
    versions = {
        "repo_version": r,
        "manifest_version": m,
        "library_version": lib,
    }
    if connected:
        if lib is not None and lib != m and r != lib:
            raise LibraryStoreError(
                "library_changed_since",
                f"the library {kind} {item_name!r} changed since the manifest version "
                f"({hist.short(m)} -> {hist.short(lib)}) and the repo copy "
                f"({hist.short(r)}) differs from it; take the library version with factory "
                "update, or export the copy as a new item with --as NEW",
                data={
                    "type": kind,
                    "name": name,
                    "item": item_name,
                    "fix": "factory update | --as NEW",
                    **versions,
                },
            )
    elif lib is not None and lib != r:
        how = "--as" if slot is not None else "the local item"
        raise LibraryStoreError(
            "item_exists",
            f"the library already has a {kind} {item_name!r} with other content ({how}); "
            "pick another name with --as NEW",
            data={"type": kind, "name": name, "item": item_name, "fix": "--as <name>", **versions},
        )
    change = Change()
    write = lib != r
    action = "connect" if not write else "update" if lib is not None else "create"
    if write:
        agent_yaml = None
        if kind == "agent":
            names = [item_name] + ([entry.item] if entry is not None else [])
            agent_yaml = _agent_yaml(state, root, head, names, copy, name)
        change.library_items.append(_library_item(copy, item_name, agent_yaml))
    new = _manifest_set(manifest, kind, name, ManifestEntry(item=item_name, version=r))
    new = _connect(change, manifest, new, source)
    files: dict[str, bytes | None] = {}
    if new != manifest:
        files = _with_manifest(state, new)
    _diff(state, state.apply(files, set()), change)
    change.detail = {
        "export": {
            "item": item_name,
            "previous_item": entry.item if entry is not None else None,
            "action": action,
            "version": r,
            "short_version": hist.short(r),
            **versions,
        }
    }
    return change


# ── revert ────────────────────────────────────────────────────────────────────


def plan_revert(
    state: RepoState,
    source: _Source,
    environ: Mapping[str, str] | None,
    type: str,
    name: str,
    *,
    to: str = "manifest",
) -> Change:
    """The change of ``config revert``: the item files back to a library version."""
    from aifactory.config.yamledit import roster_add, roster_set

    kind = _check_type(type, name)
    if to not in REVERT_TARGETS:
        raise LibraryStoreError("invalid_value", f"--to {to!r}: use one of {list(REVERT_TARGETS)}")
    manifest = state.manifest
    entry = manifest.entry(kind, name)
    if entry is None:
        raise LibraryStoreError(
            "unknown_item",
            f"{kind} {name!r} is not in the manifest (local); there is no version to revert to",
        )
    wanted = entry.version if to == "manifest" else None
    item, commit = library_version(source, environ, kind, entry.item, wanted)
    before = state.version(kind, name)
    files: dict[str, bytes | None] = dict.fromkeys(state.item_paths(kind, name))
    new_files, exe = _item_files(state, item, name)
    files.update(new_files)
    if kind == "agent":
        if state.roster_entry(name) is not None:
            files[AGENTS_FILE] = _edit_agents(
                state, lambda doc: roster_set(doc, name, {"purpose": item.purpose})
            )
        else:
            roster = _new_entry(item, name, state.settings, None, None, None)
            files[AGENTS_FILE] = _edit_agents(state, lambda doc: roster_add(doc, roster))
    new = _manifest_set(manifest, kind, name, ManifestEntry(item=entry.item, version=item.version))
    if new != manifest:
        files.update(_with_manifest(state, new))
    change = Change()
    _diff(state, state.apply(files, exe), change)
    change.detail = {
        "revert": {
            "to": to,
            "item": entry.item,
            "version": item.version,
            "short_version": hist.short(item.version),
            "commit": commit,
            "repo_version": before,
            "manifest_version": entry.version,
        }
    }
    return change


# ── diff ──────────────────────────────────────────────────────────────────────


def _text(data: bytes) -> list[str] | None:
    try:
        return data.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return None


def _file_diffs(
    label: str,
    expected: Mapping[str, bytes],
    expected_exe: set[str],
    repo: Mapping[str, bytes],
    repo_exe: set[str],
) -> list[dict[str, Any]]:
    """The files that differ, from the library version (`expected`) to the repo copy."""
    out: list[dict[str, Any]] = []
    for path in sorted(set(expected) | set(repo)):
        old, new = expected.get(path), repo.get(path)
        if old == new and (path in expected_exe) == (path in repo_exe):
            continue
        status = "added" if old is None else "removed" if new is None else "modified"
        if old == new:
            status = "mode"
        a, b = _text(old or b""), _text(new or b"")
        diff: str | None = None
        if a is not None and b is not None:
            diff = "".join(
                difflib.unified_diff(
                    a,
                    b,
                    fromfile=f"{label}/{path}" if old is not None else "/dev/null",
                    tofile=f"repo/{path}" if new is not None else "/dev/null",
                )
            )
        out.append(
            {
                "path": path,
                "status": status,
                "binary": a is None or b is None,
                "diff": diff,
            }
        )
    return out


def diff_item(
    path: Path, type: str, name: str, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """``config diff``: the repo copy against the manifest version and the library head."""
    from aifactory.library.install import _repo_root, _Source
    from aifactory.library.state import item_state, library_side

    root = _repo_root(path)
    state = read_state(root, "worktree")
    manifest = state.manifest
    kind = _check_type(type, name)
    if not state.has(kind, name):
        raise LibraryStoreError("unknown_item", f"no {kind} {name!r} in the repo")
    entry = manifest.entry(kind, name)
    item_name = entry.item if entry is not None else name
    source = _Source(environ)
    side = library_side(environ)
    r = state.version(kind, name)
    lib = side.heads([(kind, item_name)])[(kind, item_name)]
    m = entry.version if entry is not None else None
    history = side.history(kind, item_name) if entry is not None and r != lib else []
    repo_files = {p: state.files[p] for p in state.item_paths(kind, name)}
    repo_exe = {p for p in repo_files if p in state.executable}
    roster = state.roster_entry(name) if kind == "agent" else None
    against: dict[str, Any] = {}
    for label in REVERT_TARGETS:
        if label == "manifest" and entry is None:
            against[label] = {"available": False, "reason": "local", "version": None, "files": []}
            continue
        wanted = m if label == "manifest" else None
        try:
            item, commit = library_version(source, environ, kind, item_name, wanted)
        except LibraryStoreError as exc:
            if exc.code not in ("unknown_item", "unknown_version", "invalid_item"):
                raise
            reason = "unknown" if exc.code == "unknown_version" else exc.code
            against[label] = {
                "available": False,
                "reason": reason,
                "version": wanted,
                "files": [],
            }
            continue
        expected, expected_exe = _item_files(state, item, name)
        diffs = _file_diffs(label, expected, expected_exe, repo_files, repo_exe)
        if kind == "agent":
            purpose = roster.get("purpose") if roster is not None else None
            purpose = purpose if isinstance(purpose, str) else ""
            if purpose != item.purpose:
                diffs.append(
                    {
                        "path": f"{AGENTS_FILE}#{name}.purpose",
                        "status": "modified",
                        "binary": False,
                        "diff": "".join(
                            difflib.unified_diff(
                                [item.purpose + "\n"],
                                [purpose + "\n"],
                                fromfile=f"{label}/purpose",
                                tofile="repo/purpose",
                            )
                        ),
                    }
                )
        against[label] = {
            "available": True,
            "version": item.version,
            "short_version": hist.short(item.version),
            "commit": commit,
            "same": not diffs,
            "files": diffs,
        }
    return {
        "repo": str(root),
        "type": kind,
        "name": name,
        "item": item_name if entry is not None else None,
        "state": item_state(entry is not None, r, m, lib, history),
        "repo_version": r,
        "manifest_version": m,
        "library_version": lib,
        "library": side.to_json(),
        "manifest": against["manifest"],
        "head": against["head"],
    }


def combined_digest(repo: str, library: str | None) -> str:
    """The digest of an export: the repo plan and the library plan together."""
    if library is None:
        return repo
    return hashlib.sha256(f"aifactory-export-v1\0{repo}\0{library}".encode()).hexdigest()


__all__ = [
    "REVERT_TARGETS",
    "combined_digest",
    "diff_item",
    "library_version",
    "plan_export",
    "plan_revert",
    "repo_item",
]
