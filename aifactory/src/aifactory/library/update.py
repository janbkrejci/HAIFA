"""``factory update``: bring new versions of the repo's items from the library (AR24, D20).

The library is the library HEAD in the home directory, or the seed when there is none.
Every item of ``.factory/manifest.yaml`` is compared file by file, with three versions of
each file (a unit):

- base: the manifest version of the item, read from the history of the library item;
- ours: the copy in the repo;
- theirs: the library head.

Units: an agent has ``purpose`` (its roster entry), ``system.md`` and ``user.md``; a
workflow its one file; a skill or an extension every file, also files added or deleted
on either side. Other files in the prompt folder of an agent are never touched. The
copy of a skill in ``.agents/skills/`` is rewritten from the result whenever the skill
changes.

The rule per unit (first match): a missing item (state ``missing``) gets its missing
files back (``restore``); ours = theirs is ``same``; ours = base takes theirs (``take``);
theirs = base keeps ours (``keep``); ``--take TYPE/NAME[:FILE]`` takes theirs
(``taken``); ``--merge TYPE/NAME`` takes the result of ``git merge-file`` (``merged``)
only when it has no conflict and the merged item is valid, else ``merge_conflict``;
otherwise the unit is a ``conflict``: ours stays and the plan shows both diffs. An item
whose manifest version is not in the library history (``unknown``) has no base: the plan
shows ours against theirs, ours stays unless ``--take``. Text is never merged without
``--merge`` and a repo change is never overwritten without ``--take`` or ``--merge``.

The same plan moves every manifest entry to the library head, sets ``written_by`` to the
installed HAIFA, restores the missing prompts of declared agents and the runtime lines of
``.gitignore``, and lists the migrations (``library/migrations.py``) with their diff; a
migration runs only with ``--migrate ID``.

Modes as ``config add`` (``config_edit.finish_plan`` and ``execute_plan``): ``--dry-run``
(the plan and its digest), the working tree (the default), ``--commit [--pr] [--expect
DIGEST] [-m TEXT]`` (one commit on base or a pull request).

Refused before anything else: ``not_onboarded`` (no manifest in base; fix ``factory
onboard`` or ``factory init``), ``config_not_committed`` (the manifest is only in the
working tree) and ``format_unsupported`` (a manifest format newer than this HAIFA).
"""

from __future__ import annotations

import difflib
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from aifactory import __version__
from aifactory.config.errors import ConfigError
from aifactory.config.loader import (
    AGENTS_FILE,
    EXTENSIONS_DIR,
    PROMPTS_DIR,
    SKILLS_DIR,
    SKILLS_MIRROR_DIR,
    WORKFLOWS_DIR,
)
from aifactory.config.manifest import MANIFEST_FILE, Manifest, ManifestEntry, parse_manifest
from aifactory.library import history as hist
from aifactory.library.config_edit import (
    Change,
    ConfigPlan,
    ConfigResult,
    RepoState,
    Target,
    _check_type,
    _diff,
    _edit_agents,
    _manifest_set,
    _new_entry,
    _with_manifest,
    execute_plan,
    finish_plan,
    read_state,
)
from aifactory.library.model import ITEM_TYPES, Item, ItemFile, ItemType
from aifactory.library.store import LibraryStoreError
from aifactory.providers import git

Unit = tuple[bytes, bool] | None  # (content, executable); None: the file is absent
FileStatus = Literal["same", "take", "keep", "conflict", "unknown", "taken", "merged", "restore"]
ItemAction = Literal["same", "update", "keep", "conflict", "unknown", "restore", "absent"]
GITIGNORE = ".gitignore"
PROMPT_FILES = ("system.md", "user.md")


# ── refusals ──────────────────────────────────────────────────────────────────


def _parse(data: bytes, label: str) -> Manifest:
    try:
        return parse_manifest(data.decode("utf-8"), label)
    except UnicodeDecodeError as exc:
        raise LibraryStoreError("invalid_config", f"{label}: not UTF-8") from exc
    except ConfigError as exc:
        if exc.code == "format_unsupported":
            raise LibraryStoreError(
                "format_unsupported", str(exc), data={"fix": "factory upgrade"}
            ) from exc
        from aifactory.engine.role_registry import Issue

        issues = [Issue("invalid_config", i.message, i.path) for i in exc.issues]
        raise LibraryStoreError("invalid_config", f"{label} does not load", issues=issues) from exc


def _refuse(root: Path, base: str, base_sha: str, worktree: bool) -> None:
    """``not_onboarded``, ``config_not_committed`` or ``format_unsupported``."""
    from aifactory.library.install import CONFIG_FILE, SSSF_CONFIG_DIR

    found = git.blob_at(root, base_sha, MANIFEST_FILE)
    if found is None:
        if (root / MANIFEST_FILE).is_file():
            raise LibraryStoreError(
                "config_not_committed",
                f"{MANIFEST_FILE} is in the working tree but not in {base}; "
                "run factory config commit first",
                data={"fix": "factory config commit"},
            )
        factory = (
            git.blob_at(root, base_sha, CONFIG_FILE) is not None
            or (root / CONFIG_FILE).is_file()
            or (root / SSSF_CONFIG_DIR).is_dir()
        )
        raise LibraryStoreError(
            "not_onboarded",
            f"{root} has no {MANIFEST_FILE} in {base}; run factory onboard (existing .factory/ "
            "or adws/) or factory init (no factory yet)",
            data={"fix": "factory onboard" if factory else "factory init"},
        )
    _parse(git.read_blob(root, found[1]), f"{MANIFEST_FILE} in {base}")
    disk = root / MANIFEST_FILE
    if worktree and disk.is_file():
        _parse(disk.read_bytes(), str(disk))


# ── selectors ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Selector:
    type: ItemType
    name: str
    file: str | None


def parse_selector(text: str, option: str) -> Selector:
    """``TYPE/NAME[:FILE]``; ``invalid_value`` on a malformed one."""
    head, sep, file = text.strip().partition(":")
    kind, slash, name = head.partition("/")
    if not slash or not name or (sep and not file):
        raise LibraryStoreError(
            "invalid_value",
            f"{option} {text!r}: use TYPE/NAME" + ("[:FILE]" if option == "--take" else ""),
        )
    if option == "--merge" and sep:
        raise LibraryStoreError(
            "invalid_value", f"--merge {text!r}: merges a whole item, use TYPE/NAME"
        )
    return Selector(_check_type(kind, name), name, file if sep else None)


def _selectors(
    take: Sequence[str], merge: Sequence[str], manifest: Manifest
) -> tuple[list[Selector], set[tuple[str, str]]]:
    takes = [parse_selector(t, "--take") for t in take]
    merges = [parse_selector(m, "--merge") for m in merge]
    for s in [*takes, *merges]:
        if manifest.entry(s.type, s.name) is None:
            raise LibraryStoreError(
                "unknown_item",
                f"{s.type}/{s.name} is not in {MANIFEST_FILE}; update takes items of the manifest",
            )
    merged: set[tuple[str, str]] = {(s.type, s.name) for s in merges}
    both = sorted(f"{t}/{n}" for t, n in merged & {(s.type, s.name) for s in takes})
    if both:
        raise LibraryStoreError(
            "conflicting_options", f"--take and --merge name the same item: {', '.join(both)}"
        )
    return takes, merged


# ── units and the rule ────────────────────────────────────────────────────────


def _item_units(item: Item | None, slot: str) -> dict[str, Unit]:
    """The units of a library item (base or theirs)."""
    if item is None:
        return {}
    if item.type == "agent":
        out: dict[str, Unit] = {"purpose": (item.purpose.encode("utf-8"), False)}
        for prompt in PROMPT_FILES:
            found = item.file(prompt)
            out[prompt] = (found.data, False) if found is not None else None
        return out
    if item.type == "workflow":
        return {f"{slot}.yaml": (b"".join(f.data for f in item.files), False)}
    return {f.path: (f.data, f.executable) for f in item.files}


def _prefix(kind: ItemType, slot: str) -> str:
    if kind == "agent":
        return f"{PROMPTS_DIR}/{slot}/"
    if kind == "skill":
        return f"{SKILLS_DIR}/{slot}/"
    if kind == "extension":
        return f"{EXTENSIONS_DIR}/{slot}/"
    return f"{WORKFLOWS_DIR}/"


def _repo_units(state: RepoState, kind: ItemType, slot: str) -> dict[str, Unit]:
    """The units of the copy in the repo (ours)."""

    def unit(path: str) -> Unit:
        data = state.files.get(path)
        return None if data is None else (data, path in state.executable)

    if kind == "agent":
        entry = state.roster_entry(slot)
        purpose: Unit = None
        if entry is not None:
            value = entry.get("purpose")
            purpose = ((value if isinstance(value, str) else "").encode("utf-8"), False)
        out: dict[str, Unit] = {"purpose": purpose}
        for prompt in PROMPT_FILES:
            data = state.files.get(f"{PROMPTS_DIR}/{slot}/{prompt}")
            out[prompt] = None if data is None else (data, False)
        return out
    if kind == "workflow":
        return {f"{slot}.yaml": unit(f"{WORKFLOWS_DIR}/{slot}.yaml")}
    prefix = _prefix(kind, slot)
    return {p[len(prefix) :]: unit(p) for p in sorted(state.files) if p.startswith(prefix)}


def unit_rule(
    b: Unit,
    o: Unit,
    t: Unit,
    *,
    has_base: bool,
    missing: bool = False,
    take: bool = False,
    merge: bool = False,
) -> FileStatus:
    """The status of one unit from base, ours and theirs; ``merged`` means: merge it."""
    if missing and o is None and t is not None:
        return "restore"
    if o == t:
        return "same"
    if has_base and o == b:
        return "take"
    if take:
        return "taken"
    if not has_base:
        return "unknown"
    if t == b:
        return "keep"
    if merge:
        return "merged"
    return "conflict"


def _text(unit: Unit) -> str | None:
    if unit is None:
        return None
    try:
        return unit[0].decode("utf-8")
    except UnicodeDecodeError:
        return None


def _udiff(a: Unit, b: Unit, from_label: str, to_label: str) -> str | None:
    old, new = _text(a), _text(b)
    if (a is not None and old is None) or (b is not None and new is None):
        return None
    return "".join(
        difflib.unified_diff(
            (old or "").splitlines(keepends=True),
            (new or "").splitlines(keepends=True),
            fromfile=from_label if a is not None else "/dev/null",
            tofile=to_label if b is not None else "/dev/null",
        )
    )


def _binary(*units: Unit) -> bool:
    return any(u is not None and _text(u) is None for u in units)


def merge_text(ours: str, base: str, theirs: str) -> tuple[str, int]:
    """``git merge-file`` of the three texts: (result, number of conflicts)."""
    with tempfile.TemporaryDirectory(prefix="factory-merge-") as tmp:
        names = ("ours", "base", "theirs")
        for name, text in zip(names, (ours, base, theirs), strict=True):
            (Path(tmp) / name).write_bytes(text.encode("utf-8"))
        proc = subprocess.run(
            ["git", "merge-file", "-p", "-L", "repo", "-L", "base", "-L", "library", *names],
            cwd=tmp,
            capture_output=True,
        )
    if proc.returncode < 0 or proc.returncode > 127:
        raise LibraryStoreError(
            "merge_conflict", f"git merge-file failed: {proc.stderr.decode('utf-8', 'replace')}"
        )
    return proc.stdout.decode("utf-8", "replace"), proc.returncode


def _merge_unit(kind: ItemType, slot: str, unit: str, b: Unit, o: Unit, t: Unit) -> Unit:
    where = f"{kind}/{slot}:{unit}"
    texts = [_text(x) for x in (o, b, t)]
    if any(x is None for x in texts):
        raise LibraryStoreError(
            "merge_conflict",
            f"{where}: a version is missing or not text, git merge-file cannot merge it; "
            "keep the repo copy or --take",
            data={"type": kind, "name": slot, "file": unit, "conflicts": None},
        )
    ours, base, theirs = (str(x) for x in texts)
    purpose = unit == "purpose" and kind == "agent"
    if purpose:
        ours, base, theirs = ours + "\n", base + "\n", theirs + "\n"
    merged, conflicts = merge_text(ours, base, theirs)
    if conflicts:
        raise LibraryStoreError(
            "merge_conflict",
            f"{where}: git merge-file left {conflicts} conflict(s); keep the repo copy or --take",
            data={"type": kind, "name": slot, "file": unit, "conflicts": conflicts},
        )
    if purpose:
        merged = merged.removesuffix("\n")
    assert o is not None and b is not None and t is not None
    exe = t[1] if o[1] == b[1] else o[1]
    return merged.encode("utf-8"), exe


def _result_item(kind: ItemType, slot: str, units: Mapping[str, Unit]) -> Item:
    if kind == "agent":
        purpose = units.get("purpose")
        files = tuple(
            ItemFile(p, False, u[0]) for p in PROMPT_FILES if (u := units.get(p)) is not None
        )
        return Item(kind, slot, files, purpose=purpose[0].decode("utf-8") if purpose else "")
    files = tuple(ItemFile(p, u[1], u[0]) for p, u in sorted(units.items()) if u is not None)
    return Item(kind, slot, files)


# ── one item ──────────────────────────────────────────────────────────────────


@dataclass
class _ItemPlan:
    type: ItemType
    name: str
    item: str
    state: str
    manifest_version: str
    library_version: str | None
    repo_version: str | None
    action: ItemAction
    files: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Unit] = field(default_factory=dict)
    ours: dict[str, Unit] = field(default_factory=dict)
    theirs: Item | None = None
    merge_available: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "item": self.item,
            "state": self.state,
            "manifest_version": self.manifest_version,
            "library_version": self.library_version,
            "repo_version": self.repo_version,
            "short": {
                "manifest": hist.short(self.manifest_version),
                "library": hist.short(self.library_version),
                "repo": hist.short(self.repo_version),
            },
            "action": self.action,
            "merge_available": self.merge_available,
            "files": self.files,
        }


def _plan_item(
    state: RepoState,
    source: Any,
    environ: Mapping[str, str] | None,
    kind: ItemType,
    slot: str,
    entry: ManifestEntry,
    takes: Sequence[Selector],
    merges: set[tuple[str, str]],
    warnings: list[str],
) -> _ItemPlan:
    from aifactory.library.config_transfer import library_version
    from aifactory.library.state import item_state

    r = state.version(kind, slot)
    m = entry.version
    try:
        theirs, _ = library_version(source, environ, kind, entry.item, None)
    except LibraryStoreError as exc:
        if exc.code not in ("unknown_item", "invalid_item"):
            raise
        where = "the seed" if source.library is None else f"the library {source.library.name}"
        warnings.append(
            f"item_not_in_library: {kind}/{slot} ({entry.item}) is not in {where}; kept"
        )
        state_name = item_state(True, r, m, None, [])
        return _ItemPlan(kind, slot, entry.item, state_name, m, None, r, "absent")
    lib = theirs.version
    selected = [s for s in takes if (s.type, s.name) == (kind, slot)]
    merge = (kind, slot) in merges
    base: Item | None
    if m == lib:
        base = theirs
    else:
        try:
            base, _ = library_version(source, environ, kind, entry.item, m)
        except LibraryStoreError as exc:
            if exc.code != "unknown_version":
                raise
            base = None
    state_name = item_state(True, r, m, lib, [m] if base is not None else [])
    plan = _ItemPlan(kind, slot, entry.item, state_name, m, lib, r, "same", theirs=theirs)
    b_units = _item_units(base, slot)
    t_units = _item_units(theirs, slot)
    o_units = _repo_units(state, kind, slot)
    plan.ours = o_units
    names = sorted(set(b_units) | set(t_units) | set(o_units))
    if kind == "agent":
        names = ["purpose", *PROMPT_FILES]
    for s in selected:
        if s.file is not None and s.file not in names:
            raise LibraryStoreError(
                "invalid_value",
                f"--take {kind}/{slot}:{s.file}: no such file; files: {', '.join(names)}",
            )
    if merge and base is None:
        raise LibraryStoreError(
            "invalid_value",
            f"--merge {kind}/{slot}: the item has no base version (state unknown); use --take",
        )
    if r is not None and r == lib:
        plan.result = dict(o_units)
        return plan
    statuses: list[str] = []
    for unit in names:
        b, o, t = b_units.get(unit), o_units.get(unit), t_units.get(unit)
        take = any(s.file is None or s.file == unit for s in selected)
        status = unit_rule(
            b, o, t, has_base=base is not None, missing=r is None, take=take, merge=merge
        )
        if status in ("restore", "take", "taken"):
            result = t
        elif status == "merged":
            result = _merge_unit(kind, slot, unit, b, o, t)
        else:
            result = o
        plan.result[unit] = result
        statuses.append(status)
        row: dict[str, Any] = {
            "file": unit,
            "status": status,
            "binary": _binary(b, o, t),
            "ours_diff": None,
            "theirs_diff": None,
            "diff": None,
        }
        if status == "conflict":
            row["ours_diff"] = _udiff(b, o, f"base/{unit}", f"repo/{unit}")
            row["theirs_diff"] = _udiff(b, t, f"base/{unit}", f"library/{unit}")
            warnings.append(
                f"update_conflict: {kind}/{slot}:{unit} kept the repo copy; "
                f"--take {kind}/{slot}:{unit} or --merge {kind}/{slot}"
            )
        elif status == "unknown":
            row["diff"] = _udiff(o, t, f"repo/{unit}", f"library/{unit}")
            warnings.append(
                f"update_unknown: {kind}/{slot}:{unit} has no base version, kept the repo "
                f"copy; --take {kind}/{slot}:{unit}"
            )
        elif status != "same":
            row["diff"] = _udiff(o, plan.result[unit], f"repo/{unit}", f"result/{unit}")
        plan.files.append(row)
    if base is not None:
        from aifactory.library.load import validate_item

        try:
            candidate = {
                unit: _merge_unit(
                    kind, slot, unit, b_units.get(unit), o_units.get(unit), t_units.get(unit)
                )
                if unit_rule(b_units.get(unit), o_units.get(unit), t_units.get(unit), has_base=True)
                == "conflict"
                else plan.result.get(unit)
                for unit in names
            }
            plan.merge_available = not validate_item(_result_item(kind, slot, candidate))
        except LibraryStoreError:
            plan.merge_available = False
    if any(s in ("merged", "take", "taken") for s in statuses):
        issues = []
        if merge:
            from aifactory.library.load import validate_item

            issues = validate_item(_result_item(kind, slot, plan.result))
        if issues:
            raise LibraryStoreError(
                "merge_conflict",
                f"{kind}/{slot}: the merged item is not valid; keep the repo copy or --take",
                data={"type": kind, "name": slot, "file": None, "conflicts": 0},
                issues=issues,
            )
        plan.action = "update"
    elif "restore" in statuses:
        plan.action = "restore"
    elif "conflict" in statuses:
        plan.action = "conflict"
    elif "unknown" in statuses:
        plan.action = "unknown"
    elif "keep" in statuses:
        plan.action = "keep"
    return plan


def _apply_item(current: RepoState, plan: _ItemPlan) -> RepoState:
    """Write the result units of an item that differ from ours into the state."""
    from aifactory.config.yamledit import roster_add, roster_set

    kind, slot = plan.type, plan.name
    changed = {u for u, v in plan.result.items() if v != plan.ours.get(u)}
    if not changed:
        return current
    files: dict[str, bytes | None] = {}
    exe: set[str] = set()
    if kind == "agent":
        for prompt in PROMPT_FILES:
            if prompt in changed:
                value = plan.result[prompt]
                files[f"{PROMPTS_DIR}/{slot}/{prompt}"] = value[0] if value else None
        if "purpose" in changed:
            value = plan.result["purpose"]
            if value is not None:
                text = value[0].decode("utf-8")
                if current.roster_entry(slot) is not None:
                    files[AGENTS_FILE] = _edit_agents(
                        current, lambda doc: roster_set(doc, slot, {"purpose": text})
                    )
                elif plan.theirs is not None:
                    entry = _new_entry(plan.theirs, slot, current.settings, None, None, None)
                    entry["purpose"] = text
                    files[AGENTS_FILE] = _edit_agents(current, lambda doc: roster_add(doc, entry))
        return current.apply(files, exe)
    if kind == "workflow":
        value = plan.result[f"{slot}.yaml"]
        files[f"{WORKFLOWS_DIR}/{slot}.yaml"] = value[0] if value else None
        return current.apply(files, exe)
    roots = (SKILLS_DIR, SKILLS_MIRROR_DIR) if kind == "skill" else (EXTENSIONS_DIR,)
    for top in roots:
        prefix = f"{top}/{slot}/"
        for path in current.files:
            if path.startswith(prefix):
                files[path] = None
        for unit, value in plan.result.items():
            if value is None:
                continue
            files[prefix + unit] = value[0]
            if value[1]:
                exe.add(prefix + unit)
    return current.apply(files, exe)


# ── the plan ──────────────────────────────────────────────────────────────────


def _with_gitignore(state: RepoState) -> RepoState:
    """The state with the current ``.gitignore`` (so the plan modifies it, not creates it)."""
    files, blobs = dict(state.files), dict(state.blobs)
    if state.mode == "worktree":
        disk = state.root / GITIGNORE
        if disk.is_file():
            files[GITIGNORE] = disk.read_bytes()
    else:
        found = git.blob_at(state.root, state.base_sha, GITIGNORE)
        if found is not None:
            files[GITIGNORE] = git.read_blob(state.root, found[1])
            blobs[GITIGNORE] = found[1]
    return RepoState(
        state.root, state.mode, state.base, state.base_sha, files, set(state.executable), blobs
    )


def _missing_prompts(
    current: RepoState, source: Any, manifest: Manifest, warnings: list[str]
) -> tuple[RepoState, list[dict[str, Any]]]:
    """Missing prompts of roster agents that are not in the manifest, from the library."""
    restored: list[dict[str, Any]] = []
    for entry in current.roster:
        slot = str(entry["name"])
        if manifest.entry("agent", slot) is not None:
            continue
        missing = [p for p in PROMPT_FILES if f"{PROMPTS_DIR}/{slot}/{p}" not in current.files]
        if not missing:
            continue
        try:
            item = source.load("agent", [slot])[slot]
        except LibraryStoreError:
            for prompt in missing:
                warnings.append(
                    f"prompt_missing: agent {slot} has no {prompt} and the library has no "
                    f"agent {slot}"
                )
            continue
        files: dict[str, bytes | None] = {}
        for prompt in missing:
            found = item.file(prompt)
            files[f"{PROMPTS_DIR}/{slot}/{prompt}"] = found.data if found else b""
        current = current.apply(files, set())
        restored.append({"type": "agent", "name": slot, "files": missing})
    return current, restored


def plan_update(
    path: Path,
    *,
    item: Sequence[str] = (),
    take: Sequence[str] = (),
    merge: Sequence[str] = (),
    migrate: Sequence[str] = (),
    commit: bool = False,
    pr: bool = False,
    environ: Mapping[str, str] | None = None,
) -> ConfigPlan:
    """The plan of ``factory update`` for its target; writes nothing."""
    from aifactory.config.run import worktree_base
    from aifactory.library import migrations
    from aifactory.library.config_transfer import _connect
    from aifactory.library.install import GITIGNORE_LINES, _repo_root, _Source
    from aifactory.library.install_commit import _append_lines

    root = _repo_root(path)
    target: Target = "pr" if commit and pr else "direct" if commit else "worktree"
    base = worktree_base(root)
    base_sha = git.rev_parse(root, f"refs/heads/{base}")
    if base_sha is None:
        raise LibraryStoreError("unknown_base", f"base {base!r} does not exist in {root}")
    _refuse(root, base, base_sha, worktree=not commit)
    known = migrations.known_ids()
    unknown_ids = [m for m in migrate if m not in known]
    if unknown_ids:
        raise LibraryStoreError(
            "invalid_value",
            f"--migrate {', '.join(unknown_ids)}: unknown migration; known: {known}",
        )
    state = _with_gitignore(read_state(root, "base" if commit else "worktree"))
    manifest = state.manifest
    takes, merges = _selectors(take, merge, manifest)
    selected_items = {parse_selector(value, "--item") for value in item}
    if any(selector.file is not None for selector in selected_items):
        raise LibraryStoreError("invalid_value", "--item needs TYPE/NAME without a file")
    source = _Source(environ)
    warnings: list[str] = []
    current = state
    items: list[_ItemPlan] = []
    new_manifest = manifest
    for kind in ITEM_TYPES:
        for slot, entry in sorted(manifest.items.of(kind).items()):
            if selected_items and not any(
                selector.type == kind and selector.name in (slot, entry.item)
                for selector in selected_items
            ):
                continue
            plan = _plan_item(state, source, environ, kind, slot, entry, takes, merges, warnings)
            items.append(plan)
            current = _apply_item(current, plan)
            if plan.library_version is not None:
                new_manifest = _manifest_set(
                    new_manifest,
                    kind,
                    slot,
                    ManifestEntry(item=entry.item, version=plan.library_version),
                )
    current, restored = (
        (current, []) if item else _missing_prompts(current, source, manifest, warnings)
    )
    # .gitignore
    text = (current.files.get(GITIGNORE) or b"").decode("utf-8", "replace")
    present = {line.strip() for line in text.splitlines()}
    added = [line for line in GITIGNORE_LINES if line not in present]
    if added:
        current = current.apply({GITIGNORE: _append_lines(text, added).encode("utf-8")}, set())
    # manifest
    new_manifest = new_manifest.model_copy(update={"written_by": __version__})
    change = Change()
    new_manifest = _connect(change, manifest, new_manifest, source)
    manifest_changed = new_manifest != manifest
    if manifest_changed:
        current = current.apply(_with_manifest(current, new_manifest), set())
    # migrations
    found: list[dict[str, Any]] = []
    applied: list[str] = []
    for migration in migrations.detected(current.files):
        before = current.files[migration.path].decode("utf-8")
        try:
            after = migration.apply(before)
        except (ValueError, KeyError, TypeError) as exc:
            raise LibraryStoreError(
                "invalid_config", f"{migration.path}: migration {migration.id}: {exc}"
            ) from exc
        selected = migration.id in migrate
        found.append(
            {
                "id": migration.id,
                "title": migration.title,
                "path": migration.path,
                "diff": migration.diff(before, after),
                "selected": selected,
                "applied": selected,
            }
        )
        if selected:
            exe = {migration.path} if migration.path in current.executable else set()
            current = current.apply({migration.path: after.encode("utf-8")}, exe)
            applied.append(migration.id)
        else:
            warnings.append(
                f"migration_available: {migration.id} {migration.title}; "
                f"run with --migrate {migration.id}"
            )
    for wanted in migrate:
        if wanted not in applied:
            warnings.append(f"migration_not_needed: {wanted}")
    _diff(state, current, change)
    change.warnings = warnings + change.warnings
    count = sum(1 for i in items if i.action in ("update", "restore")) + len(restored)
    origin = "the seed" if source.library is None else f"the library {source.library.name}"
    subject = f"factory: update {count} item(s) from {origin}"
    if applied:
        subject += f" + migrations {', '.join(applied)}"
    conflicts = [
        f"{i.type}/{i.name}:{f['file']}"
        for i in items
        for f in i.files
        if f["status"] == "conflict"
    ]
    change.detail = {
        "update": {
            "subject": subject,
            "items": [i.to_json() for i in items],
            "restored": restored,
            "conflicts": conflicts,
            "gitignore": {"added": added},
            "migrations": found,
            "manifest": {"changed": manifest_changed, "written_by": __version__},
        }
    }
    return finish_plan(
        "update", root, target, state, change, source, environ, type="", name="", slot=None
    )


def run_update(
    path: Path,
    *,
    item: Sequence[str] = (),
    take: Sequence[str] = (),
    merge: Sequence[str] = (),
    migrate: Sequence[str] = (),
    dry_run: bool = False,
    commit: bool = False,
    pr: bool = False,
    expect: str | None = None,
    message: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> ConfigResult:
    """Plan, then write to the working tree or commit to base; see the module docstring."""
    plan = plan_update(
        path,
        item=item,
        take=take,
        merge=merge,
        migrate=migrate,
        commit=commit,
        pr=pr,
        environ=environ,
    )
    return execute_plan(plan, dry_run=dry_run, expect=expect, message=message, environ=environ)


__all__ = ["merge_text", "parse_selector", "plan_update", "run_update", "unit_rule"]
