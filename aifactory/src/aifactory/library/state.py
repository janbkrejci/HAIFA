"""States of the items in a repo against the library (AR23).

R is the version of the copy in the repo, M the version recorded in the manifest, L the
head of the library (the seed when there is no library) and H the history of the library
item. States are computed, never stored. The conditions are checked in this order:

=========================  ============
no entry in the manifest   ``local``
entry without files        ``missing``
R = L                      ``synced``
M not in H                 ``unknown``
R = M, L ≠ M               ``outdated``
R ≠ M, L = M               ``modified``
otherwise                  ``diverged``
=========================  ============
"""

from __future__ import annotations

import functools
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from aifactory.config.loader import AGENTS_FILE, EXTENSIONS_DIR, PROMPTS_DIR, SKILLS_DIR
from aifactory.config.manifest import Manifest, read_manifest
from aifactory.config.run import worktree_base
from aifactory.config.source import FACTORY_DIR, repo_root, resolve_commit
from aifactory.library import history as hist
from aifactory.library.load import check_repo_item
from aifactory.library.model import ITEM_TYPES, ItemType, check_name
from aifactory.library.seed import seed_items
from aifactory.library.store import library_root
from aifactory.library.tree import item_versions, read_blobs, tree_files, write_files
from aifactory.providers import git

ItemState = Literal["local", "missing", "synced", "unknown", "outdated", "modified", "diverged"]
ITEM_STATES: tuple[ItemState, ...] = (
    "local",
    "missing",
    "synced",
    "unknown",
    "outdated",
    "modified",
    "diverged",
)


def item_state(
    recorded: bool,
    repo: str | None,
    manifest: str | None,
    library: str | None,
    history: Sequence[str],
) -> ItemState:
    """The state of one item from R (`repo`), M (`manifest`), L (`library`) and H."""
    if not recorded:
        return "local"
    if repo is None:
        return "missing"
    if repo == library:
        return "synced"
    if manifest not in history:
        return "unknown"
    if repo == manifest:
        return "outdated"
    if library == manifest:
        return "modified"
    return "diverged"


# ── the library side: L and H ─────────────────────────────────────────────────


@functools.cache
def _seed_versions() -> dict[tuple[ItemType, str], str]:
    return {(i.type, i.name): i.version for i in seed_items()}


@dataclass(frozen=True)
class LibrarySide:
    """Where L and H come from: the library at `root` (HEAD `head`) or the seed.

    ``save_cache=False`` never writes the history cache in ``$HAIFA_HOME``."""

    source: Literal["library", "seed"]
    root: Path | None
    head: str | None
    environ: Mapping[str, str] | None = None
    save_cache: bool = True

    def heads(self, keys: Iterable[tuple[ItemType, str]]) -> dict[tuple[ItemType, str], str | None]:
        keys = list(keys)
        if self.root is None or self.head is None:
            seed = _seed_versions()
            return {k: seed.get(k) for k in keys}
        return item_versions(self.root, self.head, keys)

    def history(self, type: ItemType, name: str) -> list[str]:
        if self.root is None:
            version = _seed_versions().get((type, name))
            return [version] if version is not None else []
        return [
            r.version for r in hist.history(self.root, type, name, self.environ, self.save_cache)
        ]

    def to_json(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "path": str(self.root) if self.root is not None else None,
            "head": self.head,
        }


def library_side(environ: Mapping[str, str] | None = None, save_cache: bool = True) -> LibrarySide:
    """The library in the home directory, or the seed when there is none."""
    root = library_root(environ)
    if (root / ".git").exists():
        head = git.rev_parse(root, "HEAD")
        if head is not None:
            return LibrarySide("library", root, head, environ, save_cache)
    return LibrarySide("seed", None, None, environ, save_cache)


# ── the repo side: R ──────────────────────────────────────────────────────────


def _roster_names(repo: Path) -> list[str]:
    try:
        raw = yaml.safe_load((repo / AGENTS_FILE).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return []
    agents = raw.get("agents") if isinstance(raw, dict) else None
    if not isinstance(agents, list):
        return []
    return [str(a["name"]) for a in agents if isinstance(a, dict) and a.get("name")]


def _dirs(repo: Path, rel: str) -> list[str]:
    base = repo / rel
    if not base.is_dir():
        return []
    return [p.name for p in base.iterdir() if p.is_dir() and not p.is_symlink()]


def repo_item_names(repo: Path) -> dict[ItemType, list[str]]:
    """Names of the items present in the ``.factory/`` of `repo`, by type."""
    workflows = repo / FACTORY_DIR / "workflows"
    found: dict[ItemType, set[str]] = {
        "agent": {*_roster_names(repo), *_dirs(repo, PROMPTS_DIR)},
        "workflow": (
            {p.stem for p in workflows.glob("*.yaml") if p.is_file()}
            if workflows.is_dir()
            else set()
        ),
        "skill": set(_dirs(repo, SKILLS_DIR)),
        "extension": set(_dirs(repo, EXTENSIONS_DIR)),
    }
    return {t: sorted(n for n in names if check_name(n)) for t, names in found.items()}


def repo_version(repo: Path, type: ItemType, name: str) -> str | None:
    """R: the version of the copy in `repo`, or None when its files are missing."""
    item, _ = check_repo_item(repo, type, name)
    return item.version if item is not None else None


@dataclass(frozen=True)
class RepoItem:
    type: ItemType
    name: str
    item: str | None
    state: ItemState
    repo_version: str | None
    manifest_version: str | None
    library_version: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "item": self.item,
            "state": self.state,
            "repo_version": self.repo_version,
            "manifest_version": self.manifest_version,
            "library_version": self.library_version,
            "short": {
                "repo": hist.short(self.repo_version),
                "manifest": hist.short(self.manifest_version),
                "library": hist.short(self.library_version),
            },
        }


def item_states(repo: Path, manifest: Manifest | None, side: LibrarySide) -> list[RepoItem]:
    """Every item of the repo copy at `repo` and of `manifest`, with its state."""
    present = repo_item_names(repo)
    keys: list[tuple[ItemType, str]] = []
    for kind in ITEM_TYPES:
        names = set(present[kind])
        if manifest is not None:
            names |= set(manifest.items.of(kind))
        keys += [(kind, name) for name in sorted(names)]
    entries = {k: manifest.entry(*k) if manifest is not None else None for k in keys}
    library_keys = {(k[0], e.item) for k, e in entries.items() if e is not None}
    heads = side.heads(sorted(library_keys, key=lambda k: (ITEM_TYPES.index(k[0]), k[1])))
    out: list[RepoItem] = []
    for kind, name in keys:
        entry = entries[(kind, name)]
        r = repo_version(repo, kind, name)
        if entry is None:
            out.append(RepoItem(kind, name, None, "local", r, None, None))
            continue
        lib = heads.get((kind, entry.item))
        # H is read from the library only when the state depends on it
        history = side.history(kind, entry.item) if r is not None and r != lib else []
        state = item_state(True, r, entry.version, lib, history)
        out.append(RepoItem(kind, name, entry.item, state, r, entry.version, lib))
    return out


def extract_factory(root: Path, sha: str, dest: Path) -> None:
    files = tree_files(root, sha, [FACTORY_DIR + "/"])
    files = [f for f in files if not f.path.endswith("/local.yaml")]
    write_files(dest, files, read_blobs(root, (f.blob for f in files)))


def repo_items(
    path: Path,
    base: str | None = None,
    environ: Mapping[str, str] | None = None,
    save_cache: bool = True,
) -> dict[str, Any]:
    """States of the items of the repo at `path`.

    Without `base` the working tree is compared; with `base` (``""``: the ``base`` of
    ``config.yaml``) the tree of that commit. ``save_cache=False`` writes nothing.
    """
    root = repo_root(path)
    side = library_side(environ, save_cache)
    if base is None:
        manifest = read_manifest(root)
        items = item_states(root, manifest, side)
        ref, sha = None, None
    else:
        ref = base.strip() or worktree_base(root)
        sha = resolve_commit(root, ref)
        with tempfile.TemporaryDirectory(prefix="aifactory-items-") as tmp:
            copy = Path(tmp)
            extract_factory(root, sha, copy)
            manifest = read_manifest(copy)
            items = item_states(copy, manifest, side)
    return {
        "repo": str(root),
        "base": ref,
        "commit": sha,
        "manifest": manifest.to_json() if manifest is not None else None,
        "format": manifest.format if manifest is not None else 0,
        "library": side.to_json(),
        "items": [i.to_json() for i in items],
    }
