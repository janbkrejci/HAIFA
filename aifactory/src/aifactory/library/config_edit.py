"""``factory config set|remove|move``: manage the repo's own copies of library items.

A repo inherits agents, workflows, skills and extensions from the library
(``aifactory.library.inherit``); what it has in ``.factory/`` (and ``.claude/skills/``) is
its own copy and wins. ``set agent NAME`` changes only the bindings of the agent in
``agents.yaml`` (harness, model, thinking, tools, writes, color); an agent the repo
inherits gets an entry that overrides just those keys. ``remove TYPE NAME`` deletes the
repo copy, refused with ``in_use`` while the library lacks the item and a workflow of the
repo or ``roles.yaml`` names the agent, a backlog task in base names the workflow, or a
roster agent binds the skill or extension. ``move TYPE NAME`` ("Move to library") writes
the repo copy into the library and deletes it from the repo: the library commit is made
first (lock, fetch, push without force, fast-forward), then the repo change.

``agents.yaml`` is edited by a ruamel.yaml round trip (``config.yaml`` and ``roles.yaml``
are only read), so comments and key order stay.

Every command computes a plan with a ``digest`` (``publish.plan_digest`` over the changed
paths, for ``move`` combined with the library plan). Targets: ``worktree`` (the default:
the files are written to the working tree, nothing is committed; ``factory config commit``
commits them later), ``direct`` (``--commit``: one commit on base through
``providers.publish``, pushed before base moves, the files reach the checkout afterwards)
and ``pr`` (``--commit --pr``). ``--dry-run`` returns the plan of the target; ``--expect
DIGEST`` refuses a plan that changed since (``plan_changed``). The worktree target reads
the working tree, the others the tree of base. The planned configuration must load and
every workflow of the repo must pass its preflight (``invalid_plan``).

Blockers (the first one is raised, exit 2): ``run_in_progress`` and ``invalid_plan``
(worktree); ``dirty_paths``, ``invalid_plan``, ``not_on_base``, ``run_in_progress``,
``base_behind`` and ``base_diverged`` (direct); ``dirty_paths`` and ``invalid_plan`` (pr).

Raised: ``invalid_value``, ``unknown_item``, ``invalid_item``, ``in_use``,
``library_missing`` (move without a library), ``unknown_base``, ``invalid_config``,
``plan_changed`` and the publish codes (``commit_failed``, ``base_moved``,
``push_failed``, ``fetch_failed``).
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import os
import re
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml

from aifactory import yamlload
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
from aifactory.config.settings import CONFIG_FILE, ProjectSettings, parse_project_settings
from aifactory.config.source import FACTORY_DIR
from aifactory.engine.role_registry import Issue, RoleRegistry, load_roles
from aifactory.library.model import ITEM_TYPES, Item, ItemType, check_name
from aifactory.library.store import LibraryStoreError, NewFile, SeedItem
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
    from aifactory.library.inherit import LibrarySnapshot
    from aifactory.library.store import LibraryPlan
    from aifactory.run.store import TaskRunStore

Command = Literal["set", "remove", "move"]
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
        return bool(self.item_paths(type, name))

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


def _yaml(data: bytes | None) -> Any:
    if data is None:
        return None
    try:
        return yamlload.safe_load(data.decode("utf-8"))
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
    removed: list[dict[str, Any]] = field(default_factory=list)
    bindings: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)  # set: the binding keys given
    library_items: list[SeedItem] = field(default_factory=list)  # move: written first
    moved: Item | None = None  # move: the item as the library will hold it


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


# ── set ───────────────────────────────────────────────────────────────────────


def _list(value: str, what: str) -> list[str] | None:
    if value.strip() == "-":
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def plan_set(
    state: RepoState,
    library: LibrarySnapshot,
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
    from aifactory.config.yamledit import roster_add, roster_set
    from aifactory.library.agent import expand_writes

    if type != "agent":
        raise LibraryStoreError("invalid_value", f"config set takes agents only, not {type!r}")
    inherited = state.roster_entry(slot) is None
    if inherited and slot not in library.agents:
        raise LibraryStoreError(
            "unknown_item", f"no agent {slot!r} in {AGENTS_FILE} nor in the {library.label}"
        )
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
    if inherited:
        entry = {"name": slot, **{k: v for k, v in values.items() if v is not None}}
        data = _edit_agents(state, lambda doc: roster_add(doc, entry))
    else:
        data = _edit_agents(state, lambda doc: roster_set(doc, slot, values))
    change = Change(keys=list(values))
    after = state.apply({AGENTS_FILE: data}, set())
    _diff(state, after, change)
    change.bindings[slot] = _bindings(after.roster_entry(slot))
    return change


# ── remove ────────────────────────────────────────────────────────────────────


def _uses(state: RepoState, type: ItemType, name: str) -> list[str]:
    """What in the repo (or the backlog in base) needs the item."""
    if type == "agent":
        return _agent_uses(state, name)
    if type == "workflow":
        return [f"backlog task {tid}" for tid, wf in _base_tasks(state) if wf == name]
    out: list[str] = []
    for entry in state.roster:
        if type == "skill":
            bound = entry.get("skills") or []
            if isinstance(bound, list) and name in bound:
                out.append(f"agent {entry['name']}")
            continue
        prefix = f"{EXTENSIONS_DIR}/{name}"
        used = entry.get("harness_engineering")
        paths = used if isinstance(used, list) else [used] if used else []
        if any(str(p).rstrip("/") == prefix or prefix + "/" in str(p) for p in paths):
            out.append(f"agent {entry['name']}")
    return out


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
    return files


def plan_remove(state: RepoState, library: LibrarySnapshot, type: str, name: str) -> Change:
    """The change of ``config remove``; see the module docstring."""
    kind = _check_type(type, name)
    if not state.has(kind, name):
        raise LibraryStoreError("unknown_item", f"no {kind} {name!r} in the repo")
    after = state.apply(_removal(state, kind, name), set())
    reasons = [] if name in library.of(kind) else _uses(after, kind, name)
    if reasons:
        raise LibraryStoreError(
            "in_use",
            f"{kind} {name!r} is used by: {', '.join(reasons)}",
            data={"type": kind, "name": name, "used_by": reasons},
        )
    change = Change()
    change.removed.append({"type": kind, "name": name, "reason": "requested"})
    _diff(state, after, change)
    return change


# ── move ──────────────────────────────────────────────────────────────────────


def repo_item(state: RepoState, kind: ItemType, name: str) -> Item:
    """The copy of the item in the repo state; ``unknown_item`` or ``invalid_item``."""
    from aifactory.library.load import check_repo_item

    if not state.item_paths(kind, name):
        raise LibraryStoreError("unknown_item", f"the repo has no own copy of {kind} {name!r}")
    with state.materialized() as tmp:
        item, issues = check_repo_item(tmp, kind, name)
    if item is None or issues:
        raise LibraryStoreError(
            "invalid_item", f"the {kind} {name!r} in the repo is not valid", issues=issues
        )
    return item


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


def _agent_yaml(state: RepoState, library: LibrarySnapshot, item: Item) -> bytes:
    """``agent.yaml`` of a moved agent: the library defaults with the repo purpose, else
    the roster bindings as defaults."""
    known = library.agents.get(item.name)
    defaults: dict[str, Any] = {}
    if known is not None and known.defaults is not None:
        defaults = known.defaults.model_dump(mode="json", exclude_defaults=True)
    else:
        binding = _bindings(state.roster_entry(item.name))
        for key in ("harness", "model", "thinking", "color"):
            if isinstance(binding.get(key), str):
                defaults[key] = binding[key]
        for key in ("tools", "writes"):
            value = binding.get(key)
            if isinstance(value, list):
                values = [str(v) for v in value]
                defaults[key] = _unexpand(values, state.settings) if key == "writes" else values
    data: dict[str, Any] = {"purpose": item.purpose}
    if defaults:
        data["defaults"] = defaults
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True).encode("utf-8")


def _library_item(item: Item, agent_yaml: bytes | None) -> SeedItem:
    """The files of `item` in the library layout."""
    from aifactory.library.load import library_path

    rel = library_path(item.type, item.name)
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
    return SeedItem(item.type, item.name, item.version, tuple(files))


def plan_move(state: RepoState, library: LibrarySnapshot, type: str, name: str) -> Change:
    """The change of ``config move``: the library item to write and the repo copy to delete.

    An agent's roster entry keeps only its bindings (an override of the library agent);
    an entry left with only its name is removed.
    """
    from aifactory.config.yamledit import roster_remove, roster_set

    kind = _check_type(type, name)
    if library.commit is None:
        raise LibraryStoreError(
            "library_missing",
            "there is no library to move into; create one with factory library init "
            "(or factory library clone)",
        )
    item = repo_item(state, kind, name)
    change = Change(moved=item)
    agent_yaml = _agent_yaml(state, library, item) if kind == "agent" else None
    if agent_yaml is not None:
        from aifactory.library.model import AgentDefaults

        defaults = yamlload.safe_load(agent_yaml).get("defaults") or {}
        change.moved = replace(item, defaults=AgentDefaults.model_validate(defaults))
    change.library_items.append(_library_item(item, agent_yaml))
    files: dict[str, bytes | None] = dict.fromkeys(state.item_paths(kind, name))
    entry = state.roster_entry(name) if kind == "agent" else None
    if entry is not None:
        rest = [k for k in entry if k not in ("name", "purpose")]
        if rest:
            files[AGENTS_FILE] = _edit_agents(
                state, lambda doc: roster_set(doc, name, {"purpose": None})
            )
        else:
            files[AGENTS_FILE] = _edit_agents(state, lambda doc: roster_remove(doc, name))
    change.removed.append({"type": kind, "name": name, "reason": "moved"})
    _diff(state, state.apply(files, set()), change)
    return change


# ── plan ──────────────────────────────────────────────────────────────────────


@dataclass
class ConfigPlan:
    command: Command
    type: str
    name: str
    target: Target
    state: RepoState
    change: Change
    publish: PublishPlan
    issues: list[Issue]
    warnings: list[str]
    library: LibrarySnapshot
    library_plan: LibraryPlan | None = None  # move: the library write, made first

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
        change = self.change
        return {
            "repo": str(self.state.root),
            "command": self.command,
            "type": self.type,
            "name": self.name,
            **self.publish.to_json(),
            "target": self.target,
            "paths": [f.path for f in self.publish.files],
            "removed": change.removed,
            "bindings": change.bindings,
            "changed": self.changed,
            "validation": {"ok": not self.issues, "issues": [i.to_dict() for i in self.issues]},
            "warnings": self.warnings,
            "library": self.library.commit,
            **(
                {"library_plan": self.library_plan.to_json() if self.library_plan else None}
                if self.command == "move"
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


def _validate(
    state: RepoState, change: Change, missing: frozenset[str], library: LibrarySnapshot
) -> list[Issue]:
    """The planned configuration loads (with the library as it will be) and preflights."""
    from aifactory.config.source import OverlaySource
    from aifactory.library.inherit import with_item
    from aifactory.library.install_commit import validate_source

    if not any(p.startswith(FACTORY_DIR + "/") for p in change.files):
        return []
    after = state.apply(change.files, change.executable)
    if change.moved is not None:
        library = with_item(library, change.moved)
    source = OverlaySource(None, after.factory_files())
    return validate_source(source, after.workflows(), missing, library)


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
    """The plan of ``config set|remove|move`` for its target; writes nothing."""
    from aifactory.library.inherit import library_snapshot
    from aifactory.library.install import _repo_root
    from aifactory.providers.publish import uses_pr

    root = _repo_root(path)
    state = read_state(root, "base" if commit else "worktree")
    pr = commit and uses_pr(state.settings, pr)
    target: Target = "pr" if pr else "direct" if commit else "worktree"
    library = library_snapshot(environ)
    if command == "set":
        change = plan_set(state, library, type, name, **options)
    elif command == "move":
        change = plan_move(state, library, type, name)
    else:
        change = plan_remove(state, library, type, name)
    return finish_plan(command, root, target, state, change, library, environ, type=type, name=name)


def finish_plan(
    command: Command,
    root: Path,
    target: Target,
    state: RepoState,
    change: Change,
    library: LibrarySnapshot,
    environ: Mapping[str, str] | None,
    *,
    type: str,
    name: str,
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
        issues = _validate(state, change, missing, library)
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
    library_plan = _library_plan(type, name, root, change, environ)
    digest = plan_digest(state.base, state.base_sha, files)
    if library_plan is not None:
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
        target=target,
        state=state,
        change=change,
        publish=publish,
        issues=issues,
        warnings=warnings,
        library=library,
        library_plan=library_plan,
    )


def combined_digest(repo: str, library: str | None) -> str:
    """The digest of a move: the repo plan and the library plan together."""
    if library is None:
        return repo
    return hashlib.sha256(f"aifactory-move-v1\0{repo}\0{library}".encode()).hexdigest()


def _library_source(type: str, name: str, root: Path) -> tuple[str, str]:
    """(source, subject) of the library commit of a move."""
    return f"repo {root} {type} {name}", f"library: move {type}/{name} from {root.name}"


def _library_plan(
    type: str,
    name: str,
    root: Path,
    change: Change,
    environ: Mapping[str, str] | None,
) -> LibraryPlan | None:
    """The library write of a move (a dry run of ``store.import_items``)."""
    if not change.library_items:
        return None
    from aifactory.library.store import import_items

    source, subject = _library_source(type, name, root)
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
    library_commit: str | None = None  # move: the library commit written first
    merged: bool = False

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
            "merged": self.merged,
            **({"library_commit": self.library_commit} if self.plan.command == "move" else {}),
        }


def _subject(plan: ConfigPlan) -> str:
    if plan.command == "set":
        return f"factory: set agent {plan.name} ({', '.join(plan.change.keys) or 'bindings'})"
    if plan.command == "move":
        return f"factory: move {plan.type} {plan.name} to the library"
    return f"factory: remove {plan.type} {plan.name}"


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

    ``move`` writes the library first and stops there when that fails.
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
        data["fix"] = "run the same factory config move again; the library is done"
        raise LibraryStoreError(
            exc.code,
            f"{exc.message}; the library already has the item "
            f"({library_commit[:12]}), run the move again to delete the repo copy",
            data=data,
            issues=exc.issues,
        ) from exc
    if library_commit is not None:
        result = replace(result, library_commit=library_commit)
    return result


def _write_library(plan: ConfigPlan, environ: Mapping[str, str] | None) -> str | None:
    """Move: write the library first (lock, fetch, a pull request when shared, fast-forward)."""
    if not plan.library_changed or plan.library_plan is None:
        return None
    from aifactory.library.store import import_items

    source, subject = _library_source(plan.type, plan.name, plan.state.root)
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
            provider = get_provider(settings, root)
            result = publish.publish_pr(
                root,
                provider=provider,
                settings=settings,
                plan=plan.publish,
                message=subject,
                body=_body(plan),
                prefix=CONFIG_BRANCH_PREFIX,
            )
            if settings.base_pr_merge == "auto":
                store = _store(root)
                try:
                    result = publish.finish_pr(
                        root,
                        provider=provider,
                        settings=settings,
                        plan=plan.publish,
                        result=result,
                        message=subject,
                        store=store,
                        materialize=True,
                        command=f"config {command}",
                    )
                finally:
                    if store is not None:
                        store.close()
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
                    command=f"config {command}",
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
        merged=result.merged,
    )


__all__ = [
    "Change",
    "ConfigPlan",
    "ConfigResult",
    "RepoState",
    "execute_plan",
    "finish_plan",
    "plan_config",
    "plan_move",
    "plan_remove",
    "plan_set",
    "read_state",
    "run_config",
    "write_worktree",
]
