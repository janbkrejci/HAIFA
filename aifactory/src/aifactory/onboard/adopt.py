"""``factory adopt``: take over an onboarded repo on another machine (AR35, decision 8).

An onboarded repo is never extracted again. Adopt reads ``.factory/`` from the base
commit (``ls-tree`` and ``cat-file``, nothing checked out, nothing written to the repo)
and fills the library on this machine to match the committed manifest:

- no library: ``library_missing`` with ``factory library clone <remote of the manifest>``;
- a library with another ``id``: the warning ``library_mismatch``;
- an item the library does not have at all: imported from the copy in base, all in one
  library commit (the library write of ``aifactory.library.store``);
- an item the library has, but without the version of the manifest: left ``unknown``
  with the fix ``factory config export TYP JMENO --as NOVE``.
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import ValidationError

from aifactory.config.errors import ConfigError
from aifactory.config.loader import AGENTS_FILE
from aifactory.config.manifest import MANIFEST_FILE, Manifest, parse_manifest
from aifactory.config.settings import CONFIG_FILE, ProjectSettings, parse_project_settings
from aifactory.config.source import git as read_git
from aifactory.config.source import repo_root
from aifactory.library import history as hist
from aifactory.library.load import check_repo_item
from aifactory.library.load import library_path as item_library_path
from aifactory.library.model import ITEM_TYPES, AgentDefaults, Item, ItemType
from aifactory.library.state import LibrarySide, RepoItem, extract_factory, item_states
from aifactory.library.store import (
    LibraryStoreError,
    NewFile,
    SeedItem,
    import_items,
    library_root,
    read_meta,
)
from aifactory.onboard.state import RepoState, repo_state
from aifactory.providers import git

AdoptStatus = Literal["present", "imported", "import", "invalid", "unknown"]
ADOPT_STATUSES: tuple[AdoptStatus, ...] = ("present", "imported", "import", "invalid", "unknown")
DEFAULT_KEYS = ("model", "thinking", "tools", "writes", "color", "skills", "extensions")
_HARNESS_KEYS = ("harness", "coding_agent")


@dataclass(frozen=True)
class AdoptItem:
    """One item of the manifest: its state against the library and what adopt did."""

    state: RepoItem
    adopt: AdoptStatus
    fix: str | None = None
    issues: tuple[dict[str, str], ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            **self.state.to_json(),
            "adopt": self.adopt,
            "fix": self.fix,
            "issues": list(self.issues),
        }


@dataclass
class AdoptResult:
    repo: RepoState
    library: dict[str, Any]
    dry_run: bool
    items: list[AdoptItem]
    plan: dict[str, Any] | None
    committed: bool
    library_commit: str | None
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "repo": self.repo.repo,
            "base": self.repo.base,
            "commit": self.repo.commit,
            "state": self.repo.state,
            "onboarding": self.repo.onboarding,
            "manifest_library": self.repo.library,
            "library": self.library,
            "dry_run": self.dry_run,
            "imported": [
                f"{i.state.type}/{i.state.item}" for i in self.items if i.adopt == "imported"
            ],
            "items": [i.to_json() for i in self.items],
            "plan": self.plan,
            "committed": self.committed,
            "library_commit": self.library_commit,
            "repo_changed": False,
        }


# ── the copy in base as library items ─────────────────────────────────────────


def _roster(copy: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Roster defaults and the entry of every agent of ``.factory/agents.yaml``."""
    try:
        raw = yaml.safe_load((copy / AGENTS_FILE).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return {}, {}
    if not isinstance(raw, dict):
        return {}, {}
    defaults = raw.get("defaults") if isinstance(raw.get("defaults"), dict) else {}
    agents = raw.get("agents") if isinstance(raw.get("agents"), list) else []
    entries = {str(a["name"]): a for a in agents or [] if isinstance(a, dict) and a.get("name")}
    return dict(defaults or {}), entries


def _settings(copy: Path) -> ProjectSettings:
    path = copy / CONFIG_FILE
    text = path.read_text(encoding="utf-8") if path.is_file() else None
    found = parse_project_settings(text, CONFIG_FILE, []) if text is not None else None
    return found if found is not None else ProjectSettings()


def _unexpand(writes: Sequence[Any], settings: ProjectSettings) -> list[str]:
    """``writes`` with the project's specs and docs directories back as variables."""
    out: list[str] = []
    for entry in (str(w) for w in writes):
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


def _agent_defaults(
    roster_defaults: Mapping[str, Any], entry: Mapping[str, Any], settings: ProjectSettings
) -> dict[str, Any]:
    """The library ``defaults`` of an agent from its roster entry over the roster defaults."""
    merged = {**roster_defaults, **entry}
    data: dict[str, Any] = {}
    harness = next((merged[k] for k in _HARNESS_KEYS if merged.get(k) is not None), None)
    if harness is not None:
        data["harness"] = str(harness)
    for key in DEFAULT_KEYS:
        value = merged.get(key)
        if value is None:
            continue
        if key == "writes" and isinstance(value, list):
            value = _unexpand(value, settings)
        data[key] = value
    try:
        AgentDefaults.model_validate(data)
    except ValidationError:
        # bindings the library does not accept stay in the repo; the content is what counts
        return {}
    return data


def _library_files(
    item: Item,
    name: str,
    roster: tuple[dict[str, Any], dict[str, dict[str, Any]]],
    settings: ProjectSettings,
    slot: str,
) -> tuple[NewFile, ...]:
    """The files of the repo copy ``item`` as library item ``name``."""
    rel = item_library_path(item.type, name)
    if item.type == "workflow":
        f = item.files[0]
        return (NewFile(rel, f.executable, f.data),)
    files = [NewFile(f"{rel}/{f.path}", f.executable, f.data) for f in item.files]
    if item.type == "agent":
        meta: dict[str, Any] = {"purpose": item.purpose}
        defaults = _agent_defaults(roster[0], roster[1].get(slot, {}), settings)
        if defaults:
            meta["defaults"] = defaults
        text = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
        files.insert(0, NewFile(f"{rel}/agent.yaml", False, text.encode("utf-8")))
    return tuple(files)


# ── adopt ─────────────────────────────────────────────────────────────────────


def _manifest(state: RepoState) -> Manifest:
    if state.manifest is not None:
        return state.manifest
    root = Path(state.repo)
    sha = state.commit or ""
    label = f"{state.base}@{sha[:7]}:{MANIFEST_FILE}"
    try:
        return parse_manifest(read_git(root, "cat-file", "blob", f"{sha}:{MANIFEST_FILE}"), label)
    except ConfigError as exc:
        if exc.code == "format_unsupported":
            raise LibraryStoreError("format_unsupported", str(exc)) from exc
        raise LibraryStoreError("invalid_config", str(exc)) from exc


def _library_missing(manifest: Manifest, root: Path) -> LibraryStoreError:
    remote = manifest.library.remote if manifest.library is not None else None
    command = f"factory library clone {remote}" if remote else None
    if command is not None:
        message = f"no library at {root}; the repo uses the library at {remote}: run {command}"
    else:
        message = (
            f"no library at {root} and the manifest names no library remote; ask who onboarded "
            "the repo for the library remote and run factory library clone URL"
        )
    return LibraryStoreError(
        "library_missing",
        message,
        data={"library": str(root), "remote": remote, "command": command, "fix": command},
    )


def _side(environ: Mapping[str, str] | None) -> LibrarySide | None:
    root = library_root(environ)
    if not (root / ".git").exists():
        return None
    head = git.rev_parse(root, "HEAD")
    if head is None:
        return None
    return LibrarySide("library", root, head, environ)


def _library_json(side: LibrarySide, manifest: Manifest) -> dict[str, Any]:
    assert side.root is not None and side.head is not None
    meta = read_meta(side.root, side.head)
    expected = manifest.library.id if manifest.library is not None else None
    return {
        "path": str(side.root),
        "head": side.head,
        "id": meta.get("id"),
        "name": meta.get("name"),
        "expected_id": expected,
        "matches": expected is None or meta.get("id") == expected,
    }


def _export_fix(type: str, name: str) -> str:
    return f"factory config export {type} {name} --as NOVE"


def adopt_repo(
    path: Path, *, dry_run: bool = False, environ: Mapping[str, str] | None = None
) -> AdoptResult:
    """Fill this machine's library from the onboarded repo at ``path``; the repo is not written.

    Raises ``LibraryStoreError``: ``not_a_repository``, ``not_onboarded``,
    ``invalid_config``/``format_unsupported`` (the manifest in base), ``library_missing``
    and the codes of a library write (``library_dirty``, ``library_behind``, ...).
    """
    try:
        root = repo_root(path)
    except ConfigError as exc:
        raise LibraryStoreError("not_a_repository", f"{path} is not a git repository") from exc
    state = repo_state(root)
    if state.state != "onboarded" or state.commit is None:
        raise LibraryStoreError(
            "not_onboarded",
            f"the repo is '{state.state}' in {state.base}, not onboarded; run factory "
            f"{state.action.replace('_', ' ')}",
            data={"state": state.state, "action": state.action},
        )
    manifest = _manifest(state)
    side = _side(environ)
    if side is None:
        raise _library_missing(manifest, library_root(environ))
    library = _library_json(side, manifest)
    warnings: list[str] = []
    if not library["matches"]:
        warnings.append(
            f"library_mismatch: the repo was onboarded with library {library['expected_id']} "
            f"({manifest.library.name if manifest.library else '-'}), this machine has "
            f"{library['id']} ({library['name']}); items are compared with this library"
        )
    with tempfile.TemporaryDirectory(prefix="aifactory-adopt-") as tmp:
        copy = Path(tmp)
        extract_factory(root, state.commit, copy)
        items, plan, committed, commit = _adopt(
            copy, manifest, side, state, dry_run, environ, warnings
        )
    return AdoptResult(state, library, dry_run, items, plan, committed, commit, warnings)


def _adopt(
    copy: Path,
    manifest: Manifest,
    side: LibrarySide,
    state: RepoState,
    dry_run: bool,
    environ: Mapping[str, str] | None,
    warnings: list[str],
) -> tuple[list[AdoptItem], dict[str, Any] | None, bool, str | None]:
    entries = [
        (kind, slot, entry)
        for kind in ITEM_TYPES
        for slot, entry in sorted(manifest.items.of(kind).items())
    ]
    heads = side.heads({(kind, e.item) for kind, _, e in entries})
    roster, settings = _roster(copy), _settings(copy)
    # (type, library item) -> the slot whose copy is imported; one import per item
    chosen: dict[tuple[ItemType, str], str] = {}
    invalid: dict[tuple[ItemType, str], list[dict[str, str]]] = {}
    new: list[SeedItem] = []
    for kind, _slot, entry in entries:
        key = (kind, entry.item)
        if heads.get(key) is not None or key in chosen or key in invalid:
            continue
        slots = [s for k, s, e in entries if k == kind and e.item == entry.item]
        loaded = {s: check_repo_item(copy, kind, s) for s in slots}
        valid = {s: i for s, (i, issues) in loaded.items() if i is not None and not issues}
        if not valid:
            invalid[key] = [i.to_dict() for s in slots for i in loaded[s][1]]
            continue
        same = [s for s, i in valid.items() if i.version == manifest.items.of(kind)[s].version]
        pick = same[0] if same else sorted(valid)[0]
        item = valid[pick]
        chosen[key] = pick
        files = _library_files(item, entry.item, roster, settings, pick)
        new.append(SeedItem(kind, entry.item, item.version, files))
    plan: dict[str, Any] | None = None
    committed, commit = False, None
    if new:
        source = f"{state.repo} {state.base}@{(state.commit or '')[:12]}"
        subject = f"library: adopt {len(new)} item(s) from {Path(state.repo).name}"
        result = import_items(new, source, subject, dry_run=dry_run, environ=environ)
        plan = result.plan.to_json()
        committed, commit = result.committed, result.commit
        warnings.extend(result.warnings)
        if committed and side.root is not None and commit is not None:
            side = LibrarySide("library", side.root, commit, environ)
    states = {(s.type, s.name): s for s in item_states(copy, manifest, side)}
    out: list[AdoptItem] = []
    for kind, slot, entry in entries:
        repo_item = states[(kind, slot)]
        key = (kind, entry.item)
        if key in invalid:
            out.append(AdoptItem(repo_item, "invalid", None, tuple(invalid[key])))
            warnings.append(
                f"{kind}/{slot}: the copy in base is not a valid library item and was not "
                "imported; see items[].issues"
            )
        elif key in chosen and not committed:
            out.append(AdoptItem(repo_item, "import"))
        elif key in chosen:
            status: AdoptStatus = "imported" if chosen[key] == slot else "present"
            out.append(AdoptItem(repo_item, status))
        elif repo_item.state == "unknown":
            fix = _export_fix(kind, slot)
            out.append(AdoptItem(repo_item, "unknown", fix))
            warnings.append(
                f"{kind}/{slot}: version {hist.short(entry.version)} of the manifest is not in "
                f"the history of library item {entry.item}; run {fix}"
            )
        else:
            out.append(AdoptItem(repo_item, "present"))
    return out, plan, committed, commit
