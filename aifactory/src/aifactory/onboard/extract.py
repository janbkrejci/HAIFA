"""Extraction of a repo's own configuration into library items (decision 8, D30).

``extract_pre_library`` reads a ``.factory/`` from before the library (the tree of base)
and decides for every agent of the roster and every workflow of ``.factory/workflows/``:

- ``linked``: the library has the content already, as a version in the history of the item
  of the same name or as the head of another item; the slot points there.
- ``carried_over``: ``--keep-local TYP/JMENO``; the slot points to the library item of the
  same name at its head and the difference stays in the repo (the item is ``modified``).
- ``converted``: a new library item, named after the slot when that name is free and
  ``<slot>-<slug of the repo folder>`` otherwise (D30), or the name of ``--name``.
- ``manual``: the copy is not a valid item; it stays ``local``.

Workflows the backlog in base names and the repo lacks are added from the library
(``linked``). Every other shared file of ``.factory/`` stays as it is (``left_in_place``).

The sssf extractor (``onboard/sssf.py``) fills the same ``Extraction``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from aifactory.config.loader import PROMPTS_DIR, WORKFLOWS_DIR
from aifactory.config.manifest import ManifestEntry
from aifactory.library import history as hist
from aifactory.library.load import check_repo_item
from aifactory.library.model import Item, ItemType, check_name
from aifactory.library.store import LibraryStoreError, SeedItem
from aifactory.onboard.adopt import _library_files, _roster, _settings

if TYPE_CHECKING:
    from aifactory.library.config_edit import RepoState
    from aifactory.library.install import _Source

ReportCode = Literal[
    "linked",
    "converted",
    "carried_over",
    "changed_meaning",
    "not_converted",
    "manual",
    "left_in_place",
]
REPORT_CODES: tuple[ReportCode, ...] = (
    "linked",
    "converted",
    "carried_over",
    "changed_meaning",
    "not_converted",
    "manual",
    "left_in_place",
)
EXTRACT_TYPES: tuple[ItemType, ...] = ("agent", "workflow")
INTERNAL_WORKFLOWS = frozenset({"resolve"})
SSSF_DIR = "adws/"
_SLUG = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class ReportRow:
    """One line of the onboarding report."""

    code: ReportCode
    subject: str
    message: str
    item: str | None = None
    version: str | None = None
    detail: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "subject": self.subject,
            "message": self.message,
            "item": self.item,
            "version": self.version,
            "detail": self.detail,
        }


@dataclass
class Extraction:
    """What an extractor found: library items to write, manifest entries, files to add."""

    library_items: list[SeedItem] = field(default_factory=list)
    entries: dict[ItemType, dict[str, ManifestEntry]] = field(
        default_factory=lambda: {"agent": {}, "workflow": {}, "extension": {}}
    )
    files: dict[str, bytes] = field(default_factory=dict)
    report: list[ReportRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    added_workflows: list[str] = field(default_factory=list)


def slug(name: str) -> str:
    """The slug of a repo folder name: lowercase, runs of other characters become ``-``."""
    out = _SLUG.sub("-", name.lower()).strip("-")[:40].strip("-")
    return out or "repo"


def _library_heads(
    source: _Source, types: tuple[ItemType, ...] = EXTRACT_TYPES
) -> dict[tuple[ItemType, str], str | None]:
    from aifactory.library.tree import item_paths, item_versions, tree_files

    assert source.root is not None and source.head is not None
    keys = [k for k in item_paths(tree_files(source.root, source.head)) if k[0] in types]
    return item_versions(source.root, source.head, keys)


def _check_options(
    where: str,
    keep_local: set[tuple[ItemType, str]],
    names: Mapping[tuple[ItemType, str], str],
    slots: list[tuple[ItemType, str]],
) -> None:
    known = set(slots)
    for kind, name in sorted(keep_local | set(names)):
        if (kind, name) not in known:
            raise LibraryStoreError(
                "invalid_value",
                f"{kind}/{name} is not {where}",
            )
    both = sorted(keep_local & set(names))
    if both:
        kind, name = both[0]
        raise LibraryStoreError(
            "conflicting_options",
            f"{kind}/{name} has both --keep-local and --name; choose one",
        )
    for (kind, _name), new in names.items():
        if not check_name(new):
            raise LibraryStoreError("invalid_value", f"invalid {kind} name {new!r} for --name")


def extract_pre_library(
    state: RepoState,
    source: _Source,
    environ: Mapping[str, str] | None,
    *,
    keep_local: set[tuple[ItemType, str]] | None = None,
    names: Mapping[tuple[ItemType, str], str] | None = None,
    sssf_leftover: bool = False,
) -> Extraction:
    """Decide every agent and workflow of the ``.factory/`` of base; see the module docstring.

    Raises ``invalid_value``, ``conflicting_options``, ``unknown_item`` (``--keep-local`` of an
    item the library lacks) and ``name_taken`` (a new item's name is another item).
    """
    from aifactory.library.config_edit import _base_tasks

    keep = set(keep_local or ())
    renames = dict(names or {})
    assert source.root is not None and source.head is not None
    root = source.root
    out = Extraction()
    roster_slots = [str(a["name"]) for a in state.roster]
    workflow_names = sorted(state.workflows())
    slots: list[tuple[ItemType, str]] = [("agent", s) for s in roster_slots]
    slots += [("workflow", w) for w in workflow_names]
    where = f"an agent of the roster or a workflow of .factory/workflows/ in {state.base}"
    _check_options(where, keep, renames, slots)
    heads = _library_heads(source)
    repo_slug = slug(state.root.name)
    # names of new items of this run: (type, name) -> version, and version -> name per type
    planned: dict[tuple[ItemType, str], str] = {}
    by_version: dict[tuple[ItemType, str], str] = {}
    with state.materialized() as copy:
        roster, settings = _roster(copy), _settings(copy)
        for kind, slot in slots:
            subject = f"{kind}/{slot}"
            item, issues = check_repo_item(copy, kind, slot)
            if item is None or issues:
                detail = "; ".join(f"{i.path}: {i.message}" for i in issues) or "unreadable"
                out.report.append(
                    ReportRow("manual", subject, f"not a valid item, it stays local: {detail}")
                )
                continue
            version = item.version
            entry = _link(root, kind, slot, version, heads, environ)
            if entry is not None:
                name, how = entry
                out.entries[kind][slot] = ManifestEntry(item=name, version=version)
                out.report.append(ReportRow("linked", subject, how, name, version))
                continue
            if (kind, version) in by_version:
                name = by_version[(kind, version)]
                out.entries[kind][slot] = ManifestEntry(item=name, version=version)
                out.report.append(
                    ReportRow(
                        "linked",
                        subject,
                        f"same content as the new library item {name}",
                        name,
                        version,
                    )
                )
                continue
            if (kind, slot) in keep:
                head = heads.get((kind, slot))
                if head is None:
                    raise LibraryStoreError(
                        "unknown_item",
                        f"--keep-local {subject}: the library has no {kind} {slot!r}",
                    )
                out.entries[kind][slot] = ManifestEntry(item=slot, version=head)
                out.report.append(
                    ReportRow(
                        "carried_over",
                        subject,
                        f"the repo copy differs from library item {slot}; the difference "
                        "stays in the repo",
                        slot,
                        head,
                    )
                )
                continue
            name = _new_name(kind, slot, renames, heads, planned, repo_slug)
            planned[(kind, name)] = version
            by_version[(kind, version)] = name
            files = _library_files(item, name, roster, settings, slot)
            out.library_items.append(SeedItem(kind, name, version, files))
            out.entries[kind][slot] = ManifestEntry(item=name, version=version)
            out.report.append(
                ReportRow("converted", subject, f"new library item {name}", name, version)
            )
    _backlog_workflows(state, source, workflow_names, out, _base_tasks(state))
    _left_in_place(state, roster_slots, workflow_names, sssf_leftover, out)
    return out


def _link(
    root: Path,
    kind: ItemType,
    slot: str,
    version: str,
    heads: Mapping[tuple[ItemType, str], str | None],
    environ: Mapping[str, str] | None,
) -> tuple[str, str] | None:
    """(library item, message) when the library has `version` already."""
    if (kind, slot) in heads:
        own = {r.version for r in hist.history(root, kind, slot, environ)}
        if version in own:
            where = "head" if heads[(kind, slot)] == version else "history"
            return slot, f"the library item {slot} has this version ({where})"
    for (k, name), head in sorted(heads.items()):
        if k == kind and head == version:
            return name, f"same content as the head of library item {name}"
    return None


def _new_name(
    kind: ItemType,
    slot: str,
    renames: Mapping[tuple[ItemType, str], str],
    heads: Mapping[tuple[ItemType, str], str | None],
    planned: Mapping[tuple[ItemType, str], str],
    repo_slug: str,
) -> str:
    def taken(name: str) -> bool:
        return (kind, name) in heads or (kind, name) in planned

    given = renames.get((kind, slot))
    if given is not None:
        name = given
    elif not taken(slot):
        name = slot
    else:
        name = f"{slot}-{repo_slug}"[:48].rstrip("-")
        if not check_name(name):
            raise LibraryStoreError(
                "invalid_value",
                f"{kind}/{slot}: {name!r} is not a valid item name; use --name {kind}/{slot}=NEW",
            )
    if taken(name):
        raise LibraryStoreError(
            "name_taken",
            f"{kind}/{slot}: the library already has a {kind} {name!r} with other content; "
            f"choose a name with --name {kind}/{slot}=NEW or connect it with --keep-local",
            data={"type": kind, "name": slot, "item": name, "fix": "--name TYP/JMÉNO=NOVÉ"},
        )
    return name


def _backlog_workflows(
    state: RepoState,
    source: _Source,
    present: list[str],
    out: Extraction,
    tasks: list[tuple[str, object]],
) -> None:
    named = {wf for _, wf in tasks if isinstance(wf, str)}
    for wf in sorted(named - set(present) - INTERNAL_WORKFLOWS):
        subject = f"workflow/{wf}"
        try:
            item: Item = source.load("workflow", [wf])[wf]
        except LibraryStoreError as exc:
            if exc.code not in ("unknown_item", "invalid_item"):
                raise
            out.report.append(
                ReportRow(
                    "manual",
                    subject,
                    "tasks of the backlog name it; neither the repo nor the library has it",
                )
            )
            out.warnings.append(
                f"unknown_workflow: tasks name workflow {wf}; neither the repo nor the "
                "library has it"
            )
            continue
        out.files[f"{WORKFLOWS_DIR}/{wf}.yaml"] = item.files[0].data
        out.entries["workflow"][wf] = ManifestEntry(item=wf, version=item.version)
        out.added_workflows.append(wf)
        out.report.append(
            ReportRow(
                "linked",
                subject,
                "added from the library; the backlog uses it",
                wf,
                item.version,
            )
        )


def _left_in_place(
    state: RepoState,
    roster_slots: list[str],
    workflows: list[str],
    sssf_leftover: bool,
    out: Extraction,
) -> None:
    items = {f"{WORKFLOWS_DIR}/{w}.yaml" for w in workflows}
    prefixes = tuple(f"{PROMPTS_DIR}/{s}/" for s in roster_slots)
    for path in sorted(state.files):
        if path in items or path.startswith(prefixes):
            continue
        out.report.append(
            ReportRow("left_in_place", path, "stays in the repo as it is (not a library item)")
        )
    if sssf_leftover:
        out.report.append(
            ReportRow("left_in_place", SSSF_DIR, "sssf adws/ stays; delete it in a separate commit")
        )


__all__ = [
    "EXTRACT_TYPES",
    "REPORT_CODES",
    "Extraction",
    "ReportCode",
    "ReportRow",
    "extract_pre_library",
    "slug",
]
