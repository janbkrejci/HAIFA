"""``factory config add|set|remove``: manage the items of a repo by the library.

``add TYPE NAME`` copies an item from the library HEAD (the seed when there is no library)
into the repo and records it in ``.factory/manifest.yaml``, with its closure: a workflow
brings the agents of its steps (roles from the repo registry, or ``agent:`` of a step), an
agent the skills and extensions of its defaults. A dependency whose name is already in the
repo is kept as it is (``kept``, reason ``present``). The requested item goes to slot
``--as SLOT`` (agents and workflows) or its own name; a slot that holds other content is
``slot_taken`` (pick another with ``--as``), one that holds the same content is a no-op.
The roster entry of a new agent slot has the ``defaults`` of the item (``$specs_dir/``
and ``$docs_dir/`` from ``config.yaml``) overridden by ``--harness``, ``--model`` and
``--thinking``. Skills go to ``.claude/skills/<name>/`` with a copy in
``.agents/skills/<name>/``; extensions to ``.factory/extensions/<name>/``.

``set agent SLOT`` changes only the bindings of the slot in ``agents.yaml`` (harness,
model, thinking, tools, writes, color); the manifest and the prompts stay, bindings are
not part of the version (AR20). ``remove TYPE NAME`` removes an item, refused with
``in_use`` while a workflow of the repo or ``roles.yaml`` names an agent, a backlog task in
base names a workflow, or another agent of the manifest binds a skill or extension.
``--prune`` also removes the dependencies recorded in the manifest that nothing else uses
(local items are never pruned).

``export`` and ``revert`` (``library/config_transfer.py``) plan through the same targets;
an export writes the library before the repo (``Change.library_items``).

``agents.yaml`` is edited by a ruamel.yaml round trip (``config.yaml`` and ``roles.yaml``
are only read), so comments and key order stay.

Every command computes a plan with a ``digest`` (``publish.plan_digest`` over the changed
paths). Targets: ``worktree`` (the default: the files are written to the working tree,
nothing is committed; ``factory config commit`` commits them later), ``direct``
(``--commit``: one commit on base through ``providers.publish``, pushed before base moves,
the files reach the checkout afterwards) and ``pr`` (``--commit --pr``). ``--dry-run``
returns the plan of the target; ``--expect DIGEST`` refuses a plan that changed since
(``plan_changed``). The worktree target reads the working tree, the others the tree of
base. The planned configuration must load and every workflow of the repo must pass its
preflight (``invalid_plan``).

Blockers (the first one is raised, exit 2): ``run_in_progress`` and ``invalid_plan``
(worktree); ``dirty_paths``, ``invalid_plan``, ``not_on_base``, ``run_in_progress``,
``base_behind`` and ``base_diverged`` (direct); ``dirty_paths`` and ``invalid_plan`` (pr).

Raised: ``not_onboarded`` (no manifest; ``factory init``), ``invalid_value``,
``conflicting_options``, ``unknown_item``, ``invalid_item``, ``slot_taken``, ``in_use``,
``unknown_base``, ``invalid_config``, ``plan_changed`` and the publish codes
(``commit_failed``, ``base_moved``, ``push_failed``, ``fetch_failed``).
"""

from __future__ import annotations

import contextlib
import functools
import os
import re
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml

from aifactory.config.errors import ConfigError, ConfigIssue
from aifactory.config.loader import (
    AGENTS_FILE,
    EXTENSIONS_DIR,
    PROMPTS_DIR,
    ROLES_FILE,
    SKILLS_DIR,
    SKILLS_MIRROR_DIR,
    WORKFLOWS_DIR,
)
from aifactory.config.manifest import ITEM_KEYS, MANIFEST_FILE, Manifest, ManifestEntry
from aifactory.config.settings import CONFIG_FILE, ProjectSettings, parse_project_settings
from aifactory.config.source import FACTORY_DIR
from aifactory.engine.role_registry import Issue, RoleRegistry, load_roles
from aifactory.library.model import ITEM_TYPES, Item, ItemFile, ItemType, check_name
from aifactory.library.store import LibraryStoreError, SeedItem
from aifactory.providers import git
from aifactory.providers.base import ProviderError, PullRequest
from aifactory.providers.publish import (
    DIRECT,
    PR,
    Blocker,
    PlannedFile,
    PublishPlan,
    plan_digest,
)

if TYPE_CHECKING:
    from aifactory.library.install import _Source
    from aifactory.library.store import LibraryPlan
    from aifactory.run.store import TaskRunStore

Command = Literal["add", "set", "remove", "export", "revert", "update"]
Target = Literal["worktree", "direct", "pr"]
BINDING_KEYS = ("harness", "model", "thinking", "tools", "writes", "color")
_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
_ROOTS = (FACTORY_DIR + "/", SKILLS_DIR + "/", SKILLS_MIRROR_DIR + "/")
_RUNTIME_DIRS = ("data", "worktrees")


def _shared(path: str) -> bool:
    """A path of the shared configuration (never local.yaml, runtime data or the trace DB)."""
    if not path.startswith(_ROOTS):
        return False
    if not path.startswith(FACTORY_DIR + "/"):
        return True
    rest = path[len(FACTORY_DIR) + 1 :]
    first = rest.split("/", 1)[0]
    if rest == "local.yaml" or first in _RUNTIME_DIRS:
        return False
    return not ("/" not in rest and rest.startswith("trace.db"))


# ── the state of the repo ─────────────────────────────────────────────────────


@dataclass
class RepoState:
    """The shared configuration of the repo: the working tree or the tree of base."""

    root: Path
    mode: Literal["worktree", "base"]
    base: str
    base_sha: str
    files: dict[str, bytes]
    executable: set[str] = field(default_factory=set)
    blobs: dict[str, str] = field(default_factory=dict)  # base mode: blob of each path

    def apply(self, change: Mapping[str, bytes | None], executable: set[str]) -> RepoState:
        files = dict(self.files)
        exe = set(self.executable)
        for path, data in change.items():
            exe.discard(path)
            if data is None:
                files.pop(path, None)
            else:
                files[path] = data
                if path in executable:
                    exe.add(path)
        return RepoState(self.root, self.mode, self.base, self.base_sha, files, exe, self.blobs)

    # ── parsed files ──

    @functools.cached_property
    def manifest(self) -> Manifest:
        from aifactory.config.manifest import parse_manifest

        data = self.files.get(MANIFEST_FILE)
        if data is None:
            on_disk = (self.root / MANIFEST_FILE).is_file()
            if self.mode == "base" and on_disk:
                raise LibraryStoreError(
                    "not_onboarded",
                    f"{MANIFEST_FILE} is in the working tree but not in {self.base}; "
                    "run factory config commit",
                    data={"fix": "factory config commit"},
                )
            raise LibraryStoreError(
                "not_onboarded",
                f"the repo has no {MANIFEST_FILE}; install factory with factory init",
                data={"fix": "factory init"},
            )
        try:
            return parse_manifest(data.decode("utf-8"), MANIFEST_FILE)
        except (ConfigError, UnicodeDecodeError) as exc:
            raise _config_error(exc) from exc

    @functools.cached_property
    def settings(self) -> ProjectSettings:
        issues: list[ConfigIssue] = []
        data = self.files.get(CONFIG_FILE)
        text = data.decode("utf-8", "replace") if data is not None else None
        found = parse_project_settings(text, CONFIG_FILE, issues)
        if found is None:
            raise _config_error(ConfigError(issues))
        return found

    @functools.cached_property
    def roles(self) -> RoleRegistry:
        """The role registry of the repo (the packaged one when roles.yaml does not load)."""
        from aifactory.config.loader import load_config
        from aifactory.config.source import OverlaySource

        try:
            return load_config(OverlaySource(None, self.factory_files())).roles
        except ConfigError:
            return load_roles()

    @functools.cached_property
    def roster(self) -> list[dict[str, Any]]:
        raw = _yaml(self.files.get(AGENTS_FILE))
        agents = raw.get("agents") if isinstance(raw, dict) else None
        if not isinstance(agents, list):
            return []
        return [a for a in agents if isinstance(a, dict) and isinstance(a.get("name"), str)]

    def roster_entry(self, slot: str) -> dict[str, Any] | None:
        return next((a for a in self.roster if a["name"] == slot), None)

    def factory_files(self) -> dict[str, bytes | None]:
        return {p: d for p, d in self.files.items() if p.startswith(FACTORY_DIR + "/")}

    def workflows(self) -> dict[str, bytes]:
        prefix = WORKFLOWS_DIR + "/"
        return {
            p[len(prefix) : -len(".yaml")]: d
            for p, d in sorted(self.files.items())
            if p.startswith(prefix) and p.endswith(".yaml") and "/" not in p[len(prefix) :]
        }

    # ── items ──

    def item_paths(self, type: ItemType, name: str) -> list[str]:
        """The files of an item in the repo (the roster entry is not a file of its own)."""
        if type == "workflow":
            rel = f"{WORKFLOWS_DIR}/{name}.yaml"
            return [rel] if rel in self.files else []
        if type == "agent":
            prefixes: tuple[str, ...] = (f"{PROMPTS_DIR}/{name}/",)
        elif type == "skill":
            prefixes = (f"{SKILLS_DIR}/{name}/", f"{SKILLS_MIRROR_DIR}/{name}/")
        else:
            prefixes = (f"{EXTENSIONS_DIR}/{name}/",)
        return sorted(p for p in self.files if p.startswith(prefixes))

    def has(self, type: ItemType, name: str) -> bool:
        if type == "agent" and self.roster_entry(name) is not None:
            return True
        return bool(self.item_paths(type, name)) or self.manifest.entry(type, name) is not None

    @contextlib.contextmanager
    def materialized(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory(prefix="factory-config-") as tmp:
            base = Path(tmp)
            for rel, data in self.files.items():
                path = base / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod(0o755 if rel in self.executable else 0o644)
            yield base

    def version(self, type: ItemType, name: str) -> str | None:
        """R: the version of the copy in the repo, None when its files are missing."""
        from aifactory.library.state import repo_version

        with self.materialized() as tmp:
            return repo_version(tmp, type, name)


def _yaml(data: bytes | None) -> Any:
    if data is None:
        return None
    try:
        return yaml.safe_load(data.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError):
        return None


def _config_error(exc: Exception) -> LibraryStoreError:
    issues = []
    if isinstance(exc, ConfigError):
        issues = [Issue("invalid_config", i.message, i.path) for i in exc.issues]
    return LibraryStoreError(
        "invalid_config", "the configuration of the repo does not load", issues=issues
    )


def _worktree_files(root: Path) -> tuple[dict[str, bytes], set[str]]:
    files: dict[str, bytes] = {}
    exe: set[str] = set()
    for top in _ROOTS:
        base = root / top
        if not base.is_dir() or base.is_symlink():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            here = Path(dirpath)
            rel_dir = here.relative_to(root).as_posix()
            if rel_dir == FACTORY_DIR:
                dirnames[:] = [d for d in dirnames if d not in _RUNTIME_DIRS]
            dirnames[:] = [d for d in dirnames if d != ".git" and not (here / d).is_symlink()]
            for name in filenames:
                path = here / name
                rel = f"{rel_dir}/{name}"
                if path.is_symlink() or not path.is_file() or not _shared(rel):
                    continue
                files[rel] = path.read_bytes()
                if os.access(path, os.X_OK) and os.name != "nt":
                    exe.add(rel)
    return files, exe


def read_state(root: Path, mode: Literal["worktree", "base"]) -> RepoState:
    """The shared configuration of the working tree, or of the tree of base."""
    from aifactory.config.run import worktree_base
    from aifactory.library.tree import read_blobs, tree_files

    base = worktree_base(root)
    base_sha = git.rev_parse(root, f"refs/heads/{base}")
    if base_sha is None:
        raise LibraryStoreError("unknown_base", f"base {base!r} does not exist in {root}")
    if mode == "worktree":
        files, exe = _worktree_files(root)
        return RepoState(root, mode, base, base_sha, files, exe)
    try:
        found = [
            f
            for f in tree_files(root, base_sha, list(_ROOTS))
            if f.mode in ("100644", "100755") and _shared(f.path)
        ]
        blobs = read_blobs(root, (f.blob for f in found))
    except ProviderError as exc:
        raise LibraryStoreError(exc.code, exc.message) from exc
    return RepoState(
        root,
        mode,
        base,
        base_sha,
        {f.path: blobs[f.blob] for f in found},
        {f.path for f in found if f.mode == "100755"},
        {f.path: f.blob for f in found},
    )


# ── the change ────────────────────────────────────────────────────────────────


@dataclass
class Change:
    files: dict[str, bytes | None] = field(default_factory=dict)  # None = delete
    executable: set[str] = field(default_factory=set)
    added: list[dict[str, Any]] = field(default_factory=list)
    kept: list[dict[str, Any]] = field(default_factory=list)
    removed: list[dict[str, Any]] = field(default_factory=list)
    bindings: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)  # set: the binding keys given
    library_items: list[SeedItem] = field(default_factory=list)  # export: written first
    detail: dict[str, Any] = field(default_factory=dict)  # export/revert: extra JSON keys


def _diff(before: RepoState, after: RepoState, change: Change) -> None:
    """Put the paths that differ between the two states into `change`."""
    for path in sorted(set(before.files) | set(after.files)):
        old, new = before.files.get(path), after.files.get(path)
        old_exe, new_exe = path in before.executable, path in after.executable
        if old == new and (new is None or old_exe == new_exe):
            continue
        change.files[path] = new
        if new is not None and new_exe:
            change.executable.add(path)


def _bindings(entry: Mapping[str, Any] | None) -> dict[str, Any]:
    entry = entry or {}
    out = {k: entry.get(k) for k in BINDING_KEYS}
    if out["harness"] is None and entry.get("coding_agent") is not None:
        out["harness"] = entry.get("coding_agent")
    return out


def _edit_agents(state: RepoState, edit: Any) -> bytes:
    from aifactory.config.yamledit import edit_yaml

    data = state.files.get(AGENTS_FILE, b"")
    try:
        text = edit_yaml(data.decode("utf-8"), edit)
    except (UnicodeDecodeError, ValueError, KeyError) as exc:
        raise LibraryStoreError("invalid_config", f"{AGENTS_FILE}: {exc}") from exc
    return text.encode("utf-8")


def _with_manifest(state: RepoState, manifest: Manifest) -> dict[str, bytes | None]:
    from aifactory.config.manifest import dump_manifest

    return {MANIFEST_FILE: dump_manifest(manifest).encode("utf-8")}


def _manifest_set(
    manifest: Manifest, type: str, slot: str, entry: ManifestEntry | None
) -> Manifest:
    entries = dict(manifest.items.of(type))
    if entry is None:
        entries.pop(slot, None)
    else:
        entries[slot] = entry
    items = manifest.items.model_copy(update={ITEM_KEYS[type]: entries})
    return manifest.model_copy(update={"items": items})


def _check_type(type: str, name: str, what: str = "name") -> ItemType:
    if type not in ITEM_TYPES:
        raise LibraryStoreError("invalid_value", f"unknown item type {type!r}: {list(ITEM_TYPES)}")
    if not check_name(name):
        raise LibraryStoreError(
            "invalid_value", f"invalid {what} {name!r}: [a-z0-9][a-z0-9-]{{0,47}}"
        )
    return type


def _check_harness(value: str) -> str:
    from aifactory import harness

    try:
        return harness.canonical(value)
    except ValueError as exc:
        raise LibraryStoreError("invalid_value", f"--harness {value!r}: {exc}") from exc


def _check_thinking(value: str) -> str:
    from aifactory.harness.override import THINKING_LEVELS

    if value not in THINKING_LEVELS:
        raise LibraryStoreError(
            "invalid_value",
            f"--thinking {value!r}: unknown thinking level, available: {list(THINKING_LEVELS)}",
        )
    return value


# ── add ───────────────────────────────────────────────────────────────────────


def _new_entry(
    item: Item,
    slot: str,
    settings: ProjectSettings,
    harness: str | None,
    model: str | None,
    thinking: str | None,
) -> dict[str, Any]:
    from aifactory.library.agent import roster_entry

    try:
        entry = roster_entry(item, settings)
    except ValueError as exc:
        raise LibraryStoreError("invalid_item", f"agent {item.name!r}: {exc}") from exc
    entry["name"] = slot
    if harness is not None:
        changed = harness != entry.get("harness")
        entry["harness"] = harness
        if changed:
            entry.pop("model", None)
            entry.pop("thinking", None)
    if model is not None:
        entry["model"] = model
    if thinking is not None:
        entry["thinking"] = thinking
    return entry


def _item_files(state: RepoState, item: Item, slot: str) -> tuple[dict[str, bytes], set[str]]:
    """The files of `item` in the repo at `slot` (the roster entry is added apart)."""
    files: dict[str, bytes] = {}
    exe: set[str] = set()
    if item.type == "agent":
        for prompt in ("system.md", "user.md"):
            found = item.file(prompt)
            files[f"{PROMPTS_DIR}/{slot}/{prompt}"] = found.data if found else b""
    elif item.type == "workflow":
        files[f"{WORKFLOWS_DIR}/{slot}.yaml"] = item.files[0].data
    else:
        roots = (SKILLS_DIR, SKILLS_MIRROR_DIR) if item.type == "skill" else (EXTENSIONS_DIR,)
        for top in roots:
            for f in item.files:
                rel = f"{top}/{slot}/{f.path}"
                files[rel] = f.data
                if f.executable:
                    exe.add(rel)
    return files, exe


def _dependencies(item: Item, roles: RoleRegistry) -> list[tuple[ItemType, str]]:
    from aifactory.library.install import _workflow_agents

    if item.type == "workflow":
        return [("agent", a) for a in _workflow_agents(item, roles)]
    if item.type == "agent" and item.defaults is not None:
        return [("skill", s) for s in item.defaults.skills] + [
            ("extension", e) for e in item.defaults.extensions
        ]
    return []


def plan_add(
    state: RepoState,
    source: _Source,
    type: str,
    name: str,
    *,
    slot: str | None = None,
    harness: str | None = None,
    model: str | None = None,
    thinking: str | None = None,
    agent: str | None = None,
) -> Change:
    """The change of ``config add``; see the module docstring."""
    kind = _check_type(type, name)
    if slot is not None:
        if kind not in ("agent", "workflow"):
            raise LibraryStoreError(
                "conflicting_options",
                f"--as is only for agents and workflows; a {kind} keeps its name",
            )
        _check_type(kind, slot, "slot")
    if kind != "agent" and any(v is not None for v in (harness, model, thinking)):
        raise LibraryStoreError(
            "conflicting_options", "--harness, --model and --thinking are only for agents"
        )
    harness = _check_harness(harness) if harness is not None else None
    thinking = _check_thinking(thinking) if thinking is not None else None
    target = slot or name
    manifest, settings = state.manifest, state.settings
    change = Change()
    item = source.load(kind, [name])[name]
    if agent is not None:
        if kind not in ("skill", "extension"):
            raise LibraryStoreError("conflicting_options", "--agent is for skills and extensions")
        agent_entry = state.roster_entry(agent)
        if agent_entry is None:
            raise LibraryStoreError("unknown_item", f"no agent {agent!r} in {AGENTS_FILE}")
        key = "skills" if kind == "skill" else "extensions"
        values = list(agent_entry.get(key) or [])
        if name not in values:
            from aifactory.config.yamledit import roster_set

            values.append(name)
            data = _edit_agents(state, lambda doc: roster_set(doc, agent, {key: values}))
            change.files[AGENTS_FILE] = data
    if state.has(kind, target):
        entry = manifest.entry(kind, target)
        same = state.version(kind, target) == item.version
        if same and (entry is None or entry.item == item.name):
            change.kept.append(
                {"type": kind, "name": target, "item": item.name, "reason": "same_content"}
            )
            return change
        raise LibraryStoreError(
            "slot_taken",
            f"{kind} slot {target!r} is taken by other content; pick another with --as NEW",
            data={"fix": "--as <slot>", "slot": target, "type": kind},
        )
    library = source.library
    if manifest.library is not None and library is not None and manifest.library.id != library.id:
        change.warnings.append(
            f"library_mismatch: the repo came from the library {manifest.library.name} "
            f"({manifest.library.id}), this item from {library.name} ({library.id})"
        )
    roles = state.roles
    queue: list[tuple[Item, str, str]] = [(item, target, "requested")]
    planned: set[tuple[str, str]] = {(kind, target)}
    new_files: dict[str, bytes | None] = {}
    exe: set[str] = set()
    entries: list[dict[str, Any]] = []
    while queue:
        current, at, reason = queue.pop(0)
        files, executable = _item_files(state, current, at)
        new_files.update(files)
        exe |= executable
        if current.type == "agent":
            if reason == "requested":
                roster = _new_entry(current, at, settings, harness, model, thinking)
            else:
                roster = _new_entry(current, at, settings, None, None, None)
            entries.append(roster)
            change.bindings[at] = _bindings(roster)
        manifest = _manifest_set(
            manifest, current.type, at, ManifestEntry(item=current.name, version=current.version)
        )
        change.added.append(
            {
                "type": current.type,
                "name": at,
                "item": current.name,
                "version": current.version,
                "reason": reason,
            }
        )
        for dep_type, dep in _dependencies(current, roles):
            if (dep_type, dep) in planned:
                continue
            planned.add((dep_type, dep))
            if state.has(dep_type, dep):
                change.kept.append({"type": dep_type, "name": dep, "reason": "present"})
                continue
            queue.append((source.load(dep_type, [dep])[dep], dep, "dependency"))
    if agent is not None and AGENTS_FILE in change.files:
        new_files[AGENTS_FILE] = change.files[AGENTS_FILE]
    if entries:
        from aifactory.config.yamledit import roster_add

        def add_all(doc: Any) -> None:
            for entry in entries:
                roster_add(doc, entry)

        new_files[AGENTS_FILE] = _edit_agents(state, add_all)
    new_files.update(_with_manifest(state, manifest))
    _diff(state, state.apply(new_files, exe), change)
    return change


# ── set ───────────────────────────────────────────────────────────────────────


def _list(value: str, what: str) -> list[str] | None:
    if value.strip() == "-":
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def plan_set(
    state: RepoState,
    type: str,
    slot: str,
    *,
    harness: str | None = None,
    model: str | None = None,
    thinking: str | None = None,
    tools: str | None = None,
    writes: str | None = None,
    color: str | None = None,
) -> Change:
    """The change of ``config set agent SLOT``: only the bindings in ``agents.yaml``."""
    from aifactory.config.yamledit import roster_set
    from aifactory.library.agent import expand_writes

    if type != "agent":
        raise LibraryStoreError("invalid_value", f"config set takes agents only, not {type!r}")
    state.manifest  # noqa: B018 - not_onboarded first
    if state.roster_entry(slot) is None:
        raise LibraryStoreError("unknown_item", f"no agent {slot!r} in {AGENTS_FILE}")
    values: dict[str, Any] = {}
    if harness is not None:
        values["harness"] = _check_harness(harness)
    if model is not None:
        if not model.strip():
            raise LibraryStoreError("invalid_value", "--model must not be empty")
        values["model"] = model.strip()
    if thinking is not None:
        values["thinking"] = _check_thinking(thinking)
    if tools is not None:
        values["tools"] = _list(tools, "tools")
    if writes is not None:
        entries = _list(writes, "writes")
        try:
            values["writes"] = expand_writes(entries, state.settings)
        except ValueError as exc:
            raise LibraryStoreError("invalid_value", f"--writes: {exc}") from exc
    if color is not None:
        if color.strip() == "-":
            values["color"] = None
        elif not _COLOR.fullmatch(color.strip()):
            raise LibraryStoreError("invalid_value", f"--color {color!r}: use #rrggbb")
        else:
            values["color"] = color.strip()
    if not values:
        raise LibraryStoreError(
            "invalid_value",
            "nothing to set: give --harness, --model, --thinking, --tools, --writes or --color",
        )
    data = _edit_agents(state, lambda doc: roster_set(doc, slot, values))
    change = Change(keys=list(values))
    after = state.apply({AGENTS_FILE: data}, set())
    _diff(state, after, change)
    change.bindings[slot] = _bindings(after.roster_entry(slot))
    return change


# ── remove ────────────────────────────────────────────────────────────────────


class _Uses:
    """What makes an item in use; library agents and the base backlog are read once."""

    def __init__(self, source: _Source | None, base_state: RepoState) -> None:
        self.source = source
        self.base = base_state
        self._agents: dict[str, Item | None] = {}
        self._tasks: list[tuple[str, object]] | None = None

    def library_agent(self, name: str) -> Item | None:
        if name not in self._agents:
            item = None
            if self.source is not None:
                try:
                    item = self.source.load("agent", [name])[name]
                except LibraryStoreError:
                    item = None
            self._agents[name] = item
        return self._agents[name]

    def tasks(self) -> list[tuple[str, object]]:
        """(id, effective workflow) of every task of the backlog in base."""
        if self._tasks is None:
            self._tasks = _base_tasks(self.base)
        return self._tasks

    def reasons(self, state: RepoState, type: ItemType, name: str) -> list[str]:
        out: list[str] = []
        if type == "agent":
            out += _agent_uses(state, name)
        elif type == "workflow":
            out += [f"backlog task {tid}" for tid, wf in self.tasks() if wf == name]
        else:
            for slot, entry in sorted(state.manifest.items.agents.items()):
                item = self.library_agent(entry.item)
                if item is None or item.defaults is None:
                    continue
                bound = item.defaults.skills if type == "skill" else item.defaults.extensions
                if name in bound:
                    out.append(f"agent {slot}")
            if type == "extension":
                prefix = f"{EXTENSIONS_DIR}/{name}"
                for entry_ in state.roster:
                    used = entry_.get("harness_engineering")
                    paths = used if isinstance(used, list) else [used] if used else []
                    if any(str(p).rstrip("/") == prefix or prefix + "/" in str(p) for p in paths):
                        reason = f"agent {entry_['name']}"
                        if reason not in out:
                            out.append(reason)
        return out

    def dependencies(
        self, state: RepoState, type: ItemType, name: str
    ) -> list[tuple[ItemType, str]]:
        if type == "workflow":
            data = state.files.get(f"{WORKFLOWS_DIR}/{name}.yaml")
            if data is None:
                return []
            item = Item("workflow", name, (ItemFile(f"{name}.yaml", False, data),))
            try:
                return _dependencies(item, state.roles)
            except LibraryStoreError:
                return []
        if type == "agent":
            entry = state.manifest.entry("agent", name)
            found = self.library_agent(entry.item) if entry is not None else None
            return _dependencies(found, state.roles) if found is not None else []
        return []


def _agent_uses(state: RepoState, name: str) -> list[str]:
    from aifactory.workflow.model import RoleStep, WorkflowError, walk
    from aifactory.workflow.parse import parse_workflow

    out: list[str] = []
    roles = state.roles
    for wf_name, data in state.workflows().items():
        raw = _yaml(data)
        try:
            workflow = parse_workflow(raw, roles)
        except WorkflowError:
            continue
        for step in walk(workflow.steps):
            if isinstance(step, RoleStep) and step.role.agent == name:
                out.append(f"workflow {wf_name} step {step.path}")
    raw = _yaml(state.files.get(ROLES_FILE))
    declared = raw.get("roles") if isinstance(raw, dict) else None
    if isinstance(declared, dict):
        for role, spec in declared.items():
            if isinstance(spec, dict) and spec.get("agent") == name:
                out.append(f"roles.yaml role {role}")
    return out


def _backlog_prefix(pattern: str) -> str:
    from aifactory.backlog.roots import is_glob

    parts: list[str] = []
    for part in pattern.strip("/").split("/"):
        if not part or part == ".":
            continue
        if is_glob(part):
            break
        parts.append(part)
    return "/".join(parts) + "/" if parts else ""


def _base_tasks(state: RepoState) -> list[tuple[str, object]]:
    """(id, effective workflow) of each task of the backlog in base (empty when unreadable)."""
    from aifactory.backlog.derived import effective_workflow
    from aifactory.backlog.loader import iter_tasks, load_backlog
    from aifactory.library.tree import read_blobs, tree_files, write_files

    root, sha = state.root, state.base_sha
    config = git.blob_at(root, sha, CONFIG_FILE)
    if config is None:
        return []
    issues: list[ConfigIssue] = []
    text = git.read_blob(root, config[1]).decode("utf-8", "replace")
    settings = parse_project_settings(text, CONFIG_FILE, issues)
    if settings is None:
        return []
    prefixes = sorted({_backlog_prefix(p) for p in settings.backlog_patterns})
    paths = [CONFIG_FILE, *prefixes] if "" not in prefixes else []
    try:
        files = [f for f in tree_files(root, sha, paths) if f.mode in ("100644", "100755")]
        blobs = read_blobs(root, (f.blob for f in files))
    except ProviderError:
        return []
    with tempfile.TemporaryDirectory(prefix="factory-backlog-") as tmp:
        write_files(Path(tmp), files, blobs)
        try:
            backlog = load_backlog(Path(tmp), settings)
        except (ConfigError, OSError, ValueError):
            return []
        return [(str(t.id), effective_workflow(t)) for t in iter_tasks(backlog)]


def _removal(state: RepoState, type: ItemType, name: str) -> dict[str, bytes | None]:
    files: dict[str, bytes | None] = dict.fromkeys(state.item_paths(type, name))
    if type == "agent" and state.roster_entry(name) is not None:
        from aifactory.config.yamledit import roster_remove

        files[AGENTS_FILE] = _edit_agents(state, lambda doc: roster_remove(doc, name))
    if state.manifest.entry(type, name) is not None:
        files.update(_with_manifest(state, _manifest_set(state.manifest, type, name, None)))
    return files


def plan_remove(
    state: RepoState, source: _Source | None, type: str, name: str, *, prune: bool = False
) -> Change:
    """The change of ``config remove``; see the module docstring."""
    kind = _check_type(type, name)
    if not state.has(kind, name):
        raise LibraryStoreError("unknown_item", f"no {kind} {name!r} in the repo")
    uses = _Uses(source, state)
    after = state.apply(_removal(state, kind, name), set())
    reasons = uses.reasons(after, kind, name)
    if reasons:
        raise LibraryStoreError(
            "in_use",
            f"{kind} {name!r} is used by: {', '.join(reasons)}",
            data={"type": kind, "name": name, "used_by": reasons},
        )
    change = Change()
    change.removed.append({"type": kind, "name": name, "reason": "requested"})
    current = after
    if prune:
        queue = uses.dependencies(state, kind, name)
        seen: set[tuple[str, str]] = {(kind, name)}
        while queue:
            dep_type, dep = queue.pop(0)
            if (dep_type, dep) in seen:
                continue
            seen.add((dep_type, dep))
            if current.manifest.entry(dep_type, dep) is None:
                if current.has(dep_type, dep):
                    change.kept.append({"type": dep_type, "name": dep, "reason": "local"})
                continue
            nxt = current.apply(_removal(current, dep_type, dep), set())
            used = uses.reasons(nxt, dep_type, dep)
            if used:
                change.kept.append(
                    {"type": dep_type, "name": dep, "reason": "in_use", "used_by": used}
                )
                continue
            queue += uses.dependencies(current, dep_type, dep)
            current = nxt
            change.removed.append({"type": dep_type, "name": dep, "reason": "pruned"})
    _diff(state, current, change)
    return change


# ── plan ──────────────────────────────────────────────────────────────────────


@dataclass
class ConfigPlan:
    command: Command
    type: str
    name: str
    slot: str | None
    target: Target
    state: RepoState
    change: Change
    publish: PublishPlan
    issues: list[Issue]
    warnings: list[str]
    source: _Source | None
    library_plan: LibraryPlan | None = None  # export: the library write, made first

    @property
    def blockers(self) -> tuple[Blocker, ...]:
        return self.publish.blockers

    @property
    def library_changed(self) -> bool:
        return self.library_plan is not None and bool(self.library_plan.files)

    @property
    def changed(self) -> bool:
        return bool(self.publish.files) or self.library_changed

    def to_json(self) -> dict[str, Any]:
        library = self.source.library if self.source is not None else None
        change = self.change
        return {
            "repo": str(self.state.root),
            "command": self.command,
            "type": self.type,
            "name": self.name,
            "slot": self.slot,
            **self.publish.to_json(),
            "target": self.target,
            "paths": [f.path for f in self.publish.files],
            "added": change.added,
            "kept": change.kept,
            "removed": change.removed,
            "bindings": change.bindings,
            "changed": self.changed,
            "validation": {"ok": not self.issues, "issues": [i.to_dict() for i in self.issues]},
            "warnings": self.warnings,
            "source": self.source.kind if self.source is not None else None,
            "library": library.model_dump(mode="json") if library else None,
            **change.detail,
            **(
                {"library_plan": self.library_plan.to_json() if self.library_plan else None}
                if self.command == "export"
                else {}
            ),
        }


def _planned_files(state: RepoState, change: Change) -> list[PlannedFile]:
    files: list[PlannedFile] = []
    for path in sorted(change.files):
        new = change.files[path]
        old = state.files.get(path)
        if old is None and new is None:
            continue
        old_blob: str | None = None
        if old is not None:
            old_blob = state.blobs.get(path) or git.hash_blob(state.root, old, write=False)
        mode = None if new is None else "100755" if path in change.executable else "100644"
        old_mode = None if old is None else "100755" if path in state.executable else "100644"
        if old == new and old_mode == mode:
            continue
        action: Literal["create", "modify", "delete"] = (
            "create" if old is None else "delete" if new is None else "modify"
        )
        files.append(
            PlannedFile(
                path=path,
                action=action,
                old_mode=old_mode,
                old_blob=old_blob,
                mode=mode,
                content=new,
                old_content=old,
            )
        )
    return files


def _missing_harnesses() -> frozenset[str]:
    from aifactory import harness
    from aifactory.harness.check import installed_path

    return frozenset(n for n in harness.CLI_BINARIES if installed_path(n) is None)


def _harness_warnings(change: Change, missing: frozenset[str]) -> list[str]:
    from aifactory.harness.check import binary_name

    out = []
    for slot, binding in change.bindings.items():
        name = binding.get("harness")
        if isinstance(name, str) and name in missing:
            out.append(
                f"harness_missing: agent {slot} uses harness {name}, whose CLI "
                f"{binary_name(name)} is not on PATH"
            )
    return out


def _validate(state: RepoState, change: Change, missing: frozenset[str]) -> list[Issue]:
    from aifactory.config.source import OverlaySource
    from aifactory.library.install_commit import validate_source

    if not any(p.startswith(FACTORY_DIR + "/") for p in change.files):
        return []
    after = state.apply(change.files, change.executable)
    return validate_source(OverlaySource(None, after.factory_files()), after.workflows(), missing)


def _dirty(root: Path, files: Sequence[PlannedFile]) -> list[str]:
    from aifactory.library.install_commit import _dirty as dirty

    return dirty(root, files)


def _store(root: Path) -> TaskRunStore | None:
    from aifactory.library.install_commit import _store as store

    return store(root)


def plan_config(
    command: Command,
    path: Path,
    *,
    type: str,
    name: str,
    commit: bool = False,
    pr: bool = False,
    environ: Mapping[str, str] | None = None,
    **options: Any,
) -> ConfigPlan:
    """The plan of ``config add|set|remove|export|revert`` for its target; writes nothing."""
    from aifactory.library.install import _repo_root, _Source

    root = _repo_root(path)
    target: Target = "pr" if commit and pr else "direct" if commit else "worktree"
    state = read_state(root, "base" if commit else "worktree")
    state.manifest  # noqa: B018 - not_onboarded before anything else
    source: _Source | None = None
    if command == "add":
        source = _Source(environ)
        change = plan_add(state, source, type, name, **options)
    elif command == "set":
        change = plan_set(state, type, name, **options)
    elif command == "export":
        from aifactory.library.config_transfer import plan_export

        source = _Source(environ)
        change = plan_export(state, source, environ, type, name, **options)
    elif command == "revert":
        from aifactory.library.config_transfer import plan_revert

        source = _Source(environ)
        change = plan_revert(state, source, environ, type, name, **options)
    else:
        source = _Source(environ)
        change = plan_remove(state, source, type, name, **options)
    slot = options.get("slot") if command == "add" else None
    return finish_plan(
        command,
        root,
        target,
        state,
        change,
        source,
        environ,
        type=type,
        name=name,
        slot=slot or (name if command != "remove" else None),
    )


def finish_plan(
    command: Command,
    root: Path,
    target: Target,
    state: RepoState,
    change: Change,
    source: _Source | None,
    environ: Mapping[str, str] | None,
    *,
    type: str,
    name: str,
    slot: str | None,
) -> ConfigPlan:
    """The plan of a computed change: blockers, validation, warnings and the digest."""
    from aifactory.providers.publish import direct_blockers, run_blocker

    files = _planned_files(state, change)
    blockers: list[Blocker] = []
    warnings = list(change.warnings)
    issues: list[Issue] = []
    if files:
        missing = _missing_harnesses()
        if target != "worktree":
            dirty = _dirty(root, files)
            if dirty:
                blockers.append(
                    Blocker(
                        "dirty_paths",
                        "planned paths exist in the working tree with other content: "
                        + ", ".join(dirty)
                        + "; commit them (factory config commit) or move them away first",
                    )
                )
        issues = _validate(state, change, missing)
        if issues:
            blockers.append(
                Blocker(
                    "invalid_plan",
                    f"the planned configuration has {len(issues)} problem(s); see the issues",
                )
            )
        store = _store(root) if target != "pr" else None
        try:
            if target == "worktree" and store is not None:
                running = run_blocker(store)
                if running is not None:
                    blockers.insert(0, running)
            elif target == "direct":
                found, notes = direct_blockers(
                    root,
                    remote=state.settings.remote,
                    base=state.base,
                    base_sha=state.base_sha,
                    store=store,
                    check_remote=True,
                )
                blockers += found
                warnings += notes
        except ProviderError as exc:
            raise LibraryStoreError(exc.code, exc.message) from exc
        finally:
            if store is not None:
                store.close()
        warnings += _harness_warnings(change, missing)
    library_plan = _library_plan(command, type, name, root, change, environ)
    digest = plan_digest(state.base, state.base_sha, files)
    if library_plan is not None:
        from aifactory.library.config_transfer import combined_digest

        digest = combined_digest(digest, library_plan.digest)
    publish = PublishPlan(
        base=state.base,
        base_sha=state.base_sha,
        target=PR if target == "pr" else DIRECT,
        files=tuple(files),
        blockers=tuple(blockers),
        digest=digest,
    )
    return ConfigPlan(
        command=command,
        type=type,
        name=name,
        slot=slot,
        target=target,
        state=state,
        change=change,
        publish=publish,
        issues=issues,
        warnings=warnings,
        source=source,
        library_plan=library_plan,
    )


def _library_source(command: str, type: str, name: str, root: Path) -> tuple[str, str]:
    """(source, subject) of the library commit of an export."""
    return f"repo {root} {type} {name}", f"library: export {type}/{name} from {root.name}"


def _library_plan(
    command: Command,
    type: str,
    name: str,
    root: Path,
    change: Change,
    environ: Mapping[str, str] | None,
) -> LibraryPlan | None:
    """The library write of an export (a dry run of ``store.import_items``)."""
    if command != "export" or not change.library_items:
        return None
    from aifactory.library.store import import_items

    source, subject = _library_source(command, type, name, root)
    result = import_items(change.library_items, source, subject, dry_run=True, environ=environ)
    change.warnings += result.warnings
    return result.plan


# ── run ───────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ConfigResult:
    plan: ConfigPlan
    dry_run: bool
    written: bool = False
    committed: bool = False
    commit: str | None = None
    pushed: bool = False
    advanced: bool = False
    branch: str | None = None
    pr: PullRequest | None = None
    extra_warnings: tuple[str, ...] = ()
    library_commit: str | None = None  # export: the library commit written first

    @property
    def warnings(self) -> list[str]:
        return list(self.plan.warnings) + list(self.extra_warnings)

    def to_json(self) -> dict[str, Any]:
        pr = None
        if self.pr is not None:
            pr = {"id": self.pr.id, "url": self.pr.url, "branch": self.pr.branch}
        return {
            **self.plan.to_json(),
            "dry_run": self.dry_run,
            "written": self.written,
            "committed": self.committed,
            "commit": self.commit,
            "pushed": self.pushed,
            "advanced": self.advanced,
            "branch": self.branch,
            "pr": pr,
            **({"library_commit": self.library_commit} if self.plan.command == "export" else {}),
        }


def _subject(plan: ConfigPlan) -> str:
    if plan.command == "add":
        library = plan.source.library if plan.source is not None else None
        origin = "the seed" if library is None else f"the library {library.name}"
        return f"factory: add {plan.type} {plan.slot} from {origin}"
    if plan.command == "set":
        return f"factory: set agent {plan.name} ({', '.join(plan.change.keys) or 'bindings'})"
    if plan.command == "export":
        info = plan.change.detail.get("export", {})
        library = plan.source.library if plan.source is not None else None
        where = f"the library {library.name}" if library is not None else "the library"
        return (
            f"factory: export {plan.type} {plan.name} to {where} as {info.get('item')} "
            f"{hist_short(info.get('version'))}"
        )
    if plan.command == "update":
        return str(plan.change.detail.get("update", {}).get("subject") or "factory: update")
    if plan.command == "revert":
        info = plan.change.detail.get("revert", {})
        what = "manifest version" if info.get("to") == "manifest" else "library head"
        return (
            f"factory: revert {plan.type} {plan.name} to the {what} "
            f"{hist_short(info.get('version'))}"
        )
    return f"factory: remove {plan.type} {plan.name}"


def hist_short(version: object) -> str:
    from aifactory.library.history import short

    found = short(version) if isinstance(version, str) else None
    return found or "-"


def _body(plan: ConfigPlan) -> str:
    lines = [f"- {f.action} `{f.path}`" for f in plan.publish.files]
    return (
        f"{_subject(plan)}:\n\n" + "\n".join(lines) + f"\n\nPlan digest: `{plan.publish.digest}`\n"
    )


_STOPS = (FACTORY_DIR, SKILLS_DIR, SKILLS_MIRROR_DIR)


def _prune_up(root: Path, folder: Path) -> None:
    stops = {(root / s).resolve() for s in _STOPS} | {root.resolve()}
    current = folder.resolve()
    while current not in stops and root.resolve() in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def write_worktree(root: Path, change: Change) -> None:
    """Write the change to the working tree: atomic replaces, deletions, empty folders go."""
    for path, data in sorted(change.files.items()):
        target = root / path
        if data is None:
            if target.is_file() or target.is_symlink():
                target.unlink()
                _prune_up(root, target.parent)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.factory-tmp")
        tmp.write_bytes(data)
        tmp.chmod(0o755 if path in change.executable else 0o644)
        os.replace(tmp, target)


def run_config(
    command: Command,
    path: Path,
    *,
    type: str,
    name: str,
    dry_run: bool = False,
    commit: bool = False,
    pr: bool = False,
    expect: str | None = None,
    message: str | None = None,
    environ: Mapping[str, str] | None = None,
    **options: Any,
) -> ConfigResult:
    """Plan, then write to the working tree or commit to base; see the module docstring.

    ``export`` writes the library first and stops there when that fails.
    """
    plan = plan_config(
        command, path, type=type, name=name, commit=commit, pr=pr, environ=environ, **options
    )
    return execute_plan(plan, dry_run=dry_run, expect=expect, message=message, environ=environ)


def execute_plan(
    plan: ConfigPlan,
    *,
    dry_run: bool = False,
    expect: str | None = None,
    message: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> ConfigResult:
    """Return the dry run, or check ``--expect`` and the blockers and write the plan."""
    command = plan.command
    if dry_run:
        return ConfigResult(plan, True)
    if expect is not None and expect.strip() != plan.publish.digest:
        raise LibraryStoreError(
            "plan_changed",
            "the plan changed since it was reviewed (--expect); run --dry-run again",
            data=plan.to_json(),
        )
    if plan.blockers:
        first = plan.blockers[0]
        issues = plan.issues if first.code == "invalid_plan" else []
        raise LibraryStoreError(first.code, first.message, data=plan.to_json(), issues=issues)
    if not plan.changed:
        return ConfigResult(plan, False)
    library_commit = _write_library(plan, environ)
    try:
        result = _write_repo(plan, command, message)
    except LibraryStoreError as exc:
        if library_commit is None:
            raise
        data = dict(exc.data or plan.to_json())
        data["library_commit"] = library_commit
        data["fix"] = "run the same factory config export again; it connects the library version"
        raise LibraryStoreError(
            exc.code,
            f"{exc.message}; the library already has the new version "
            f"({library_commit[:12]}), run the export again to connect it",
            data=data,
            issues=exc.issues,
        ) from exc
    if library_commit is not None:
        from dataclasses import replace

        result = replace(result, library_commit=library_commit)
    return result


def _write_library(plan: ConfigPlan, environ: Mapping[str, str] | None) -> str | None:
    """Export: write the library first (lock, fetch, push without force, fast-forward)."""
    if not plan.library_changed or plan.library_plan is None:
        return None
    from aifactory.library.store import import_items

    source, subject = _library_source(plan.command, plan.type, plan.name, plan.state.root)
    written = import_items(
        plan.change.library_items,
        source,
        subject,
        environ=environ,
        expect_head=plan.library_plan.head,
    )
    return written.commit


def _write_repo(plan: ConfigPlan, command: Command, message: str | None) -> ConfigResult:
    """Write the repo side of the plan: the working tree, a commit on base or a PR."""
    from aifactory.config.commit import CONFIG_BRANCH_PREFIX
    from aifactory.providers import get_provider, publish

    root = plan.state.root
    if not plan.publish.files:
        return ConfigResult(plan, False)
    if plan.target == "worktree":
        write_worktree(root, plan.change)
        return ConfigResult(
            plan,
            False,
            written=True,
            extra_warnings=(
                f"written to the working tree only; runs use {plan.state.base} until "
                "factory config commit",
            ),
        )
    subject = (message or "").strip() or _subject(plan)
    settings = plan.state.settings
    try:
        if plan.target == "pr":
            result = publish.publish_pr(
                root,
                provider=get_provider(settings, root),
                settings=settings,
                plan=plan.publish,
                message=subject,
                body=_body(plan),
                prefix=CONFIG_BRANCH_PREFIX,
                reuse_plan=command in ("add", "update"),
            )
        else:
            store = _store(root)
            try:
                result = publish.publish_direct(
                    root,
                    settings=settings,
                    plan=plan.publish,
                    message=subject,
                    store=store,
                    materialize=True,
                    command=command if command == "update" else f"config {command}",
                )
            finally:
                if store is not None:
                    store.close()
    except ProviderError as exc:
        raise LibraryStoreError(exc.code, exc.message, data=plan.to_json()) from exc
    except RuntimeError as exc:
        raise LibraryStoreError("commit_failed", str(exc), data=plan.to_json()) from exc
    return ConfigResult(
        plan,
        False,
        committed=True,
        commit=result.commit,
        pushed=result.pushed,
        advanced=result.advanced,
        branch=result.branch,
        pr=result.pr,
        extra_warnings=tuple(result.warnings),
    )


__all__ = [
    "Change",
    "ConfigPlan",
    "ConfigResult",
    "RepoState",
    "execute_plan",
    "finish_plan",
    "plan_add",
    "plan_config",
    "plan_remove",
    "plan_set",
    "read_state",
    "run_config",
    "write_worktree",
]
