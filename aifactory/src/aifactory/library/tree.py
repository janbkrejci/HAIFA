"""Read library items from a commit of the library repo, never from its working tree.

The files of an item in a commit are written into a temporary directory in the library
layout and read there by the L1 loader, so validation and versions are the same as for
a library on disk.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from aifactory.engine.role_registry import Issue
from aifactory.library.load import check_library_item, library_path
from aifactory.library.model import ITEM_TYPES, Item, ItemFile, ItemType, check_name
from aifactory.library.version import agent_version, tree_version, workflow_version
from aifactory.providers.base import ProviderError
from aifactory.providers.git import run_bytes

_READ_ENV = {"GIT_OPTIONAL_LOCKS": "0"}
_DIRS: dict[str, ItemType] = {
    "agents": "agent",
    "workflows": "workflow",
    "skills": "skill",
    "extensions": "extension",
}


@dataclass(frozen=True)
class TreeFile:
    """One file of a commit: path from the library root, git mode, blob sha."""

    path: str
    mode: str
    blob: str


def _git(root: Path, args: list[str], input_bytes: bytes | None = None) -> bytes:
    proc = run_bytes(root, args, env=_READ_ENV, input_bytes=input_bytes)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip() or "failed"
        raise ProviderError("commit_failed", f"git {args[0]}: {detail}")
    return proc.stdout


def tree_files(root: Path, commit: str, paths: Iterable[str] = ()) -> list[TreeFile]:
    """Every file of `commit` (below `paths`, when given), recursively."""
    out = _git(root, ["ls-tree", "-r", "-z", "--full-tree", commit, "--", *paths])
    files: list[TreeFile] = []
    for entry in out.decode("utf-8", "surrogateescape").split("\0"):
        if not entry:
            continue
        header, _, path = entry.partition("\t")
        parts = header.split()
        if len(parts) == 3 and parts[1] == "blob":
            files.append(TreeFile(path=path, mode=parts[0], blob=parts[2]))
    return files


def read_blobs(root: Path, blobs: Iterable[str]) -> dict[str, bytes]:
    """The content of every blob, read in one ``git cat-file --batch``."""
    wanted = sorted(set(blobs))
    if not wanted:
        return {}
    out = _git(
        root, ["cat-file", "--batch"], input_bytes="".join(f"{b}\n" for b in wanted).encode()
    )
    found: dict[str, bytes] = {}
    pos = 0
    for _ in wanted:
        end = out.index(b"\n", pos)
        sha, kind, size = out[pos:end].decode().split()
        start = end + 1
        found[sha] = out[start : start + int(size)]
        pos = start + int(size) + 1
        if kind != "blob":
            raise ProviderError("commit_failed", f"{sha} is a {kind}, not a blob")
    return found


def item_paths(files: Iterable[TreeFile]) -> list[tuple[ItemType, str]]:
    """(type, name) of every item in a list of commit files, sorted by type and name."""
    found: set[tuple[ItemType, str]] = set()
    for f in files:
        parts = f.path.split("/")
        kind = _DIRS.get(parts[0])
        if kind is None or len(parts) < 2:
            continue
        if kind == "workflow":
            if len(parts) == 2 and parts[1].endswith(".yaml"):
                name = parts[1].removesuffix(".yaml")
            else:
                continue
        elif len(parts) >= 3:
            name = parts[1]
        else:
            continue
        if check_name(name):
            found.add((kind, name))
    return sorted(found, key=lambda k: (ITEM_TYPES.index(k[0]), k[1]))


def item_tree_path(type: ItemType, name: str) -> str:
    """The git pathspec of an item: its file, or its folder with a trailing slash."""
    rel = library_path(type, name)
    return rel if type == "workflow" else rel + "/"


def write_files(dest: Path, files: Iterable[TreeFile], blobs: dict[str, bytes]) -> None:
    """Write commit files below `dest`; symlinks stay symlinks (the loader rejects them)."""
    for f in files:
        path = dest / f.path
        path.parent.mkdir(parents=True, exist_ok=True)
        if f.mode == "120000":
            os.symlink(blobs[f.blob].decode("utf-8", "surrogateescape"), path)
            continue
        path.write_bytes(blobs[f.blob])
        path.chmod(0o755 if f.mode == "100755" else 0o644)


def _own(files: Iterable[TreeFile], kind: ItemType, name: str) -> list[TreeFile]:
    prefix = item_tree_path(kind, name)
    return [
        f for f in files if f.path == prefix or (kind != "workflow" and f.path.startswith(prefix))
    ]


def _version(kind: ItemType, name: str, own: list[TreeFile], blobs: dict[str, bytes]) -> str | None:
    """The content version of an item from its commit files, without validating it."""
    if not own or any(f.mode not in ("100644", "100755") for f in own):
        return None
    prefix = item_tree_path(kind, name)
    files = [ItemFile(f.path.removeprefix(prefix), f.mode == "100755", blobs[f.blob]) for f in own]
    if kind == "workflow":
        return workflow_version(files[0].data)
    if kind != "agent":
        return tree_version(files)
    by_name = {f.path: f.data for f in files}
    if not all(n in by_name for n in ("agent.yaml", "system.md", "user.md")):
        return None
    try:
        meta = yaml.safe_load(by_name["agent.yaml"].decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError):
        return None
    purpose = meta.get("purpose") if isinstance(meta, dict) else None
    if not isinstance(purpose, str):
        return None
    return agent_version(purpose, by_name["system.md"], by_name["user.md"])


def item_versions(
    root: Path, commit: str, keys: Iterable[tuple[ItemType, str]]
) -> dict[tuple[ItemType, str], str | None]:
    """The version of each item of `keys` in `commit` (None: missing or unreadable)."""
    keys = list(keys)
    files = tree_files(root, commit, [item_tree_path(t, n) for t, n in keys]) if keys else []
    blobs = read_blobs(root, (f.blob for f in files))
    return {(k, n): _version(k, n, _own(files, k, n), blobs) for k, n in keys}


def read_items(
    root: Path, commit: str, keys: Iterable[tuple[ItemType, str]]
) -> dict[tuple[ItemType, str], tuple[Item | None, list[Issue], list[TreeFile]]]:
    """Each item of `keys` as it is in `commit`, with its problems and its commit files."""
    keys = list(keys)
    files = tree_files(root, commit, [item_tree_path(t, n) for t, n in keys]) if keys else []
    blobs = read_blobs(root, (f.blob for f in files))
    out: dict[tuple[ItemType, str], tuple[Item | None, list[Issue], list[TreeFile]]] = {}
    with tempfile.TemporaryDirectory(prefix="aifactory-library-") as tmp:
        base = Path(tmp)
        write_files(base, files, blobs)
        for kind, name in keys:
            own = _own(files, kind, name)
            if not own:
                out[(kind, name)] = (None, [], [])
                continue
            item, issues = check_library_item(base, kind, name)
            out[(kind, name)] = (item, issues, own)
    return out
