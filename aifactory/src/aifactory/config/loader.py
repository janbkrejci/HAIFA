"""Load the whole ``.factory/`` configuration from one ``ConfigSource``.

Every file is read through the source, so a run that loads from a commit sees
exactly that commit's configuration. ``local.yaml`` is not part of it; see
``aifactory.config.settings.load_local``.

Agents and workflows the repo does not have are inherited from the library
(``aifactory.library.inherit``: HEAD of ``$HAIFA_HOME/library``, else the seed). A copy in
the repo wins. An agent with prompts in ``.factory/prompts/<name>/`` is the repo's own copy
and takes nothing from the library. A roster entry in ``agents.yaml`` without prompts there
overrides only the keys it sets of the library agent of the same name (bindings, writes and
so on); the prompts and every key it does not set come from the library. Library agents get
the roster ``defaults`` for harness, model and thinking before their own.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import ValidationError

from aifactory import yamlload
from aifactory.config.errors import ConfigError, ConfigIssue
from aifactory.config.settings import (
    CONFIG_FILE,
    ProjectSettings,
    parse_mapping,
    parse_project_settings,
    validation_issues,
)
from aifactory.config.source import ConfigSource, WorktreeSource, repo_root
from aifactory.engine.role_registry import RoleRegistry, RolesError, load_roles, parse_roles
from aifactory.harness.config import HarnessConfigError, SSSFConfig, normalize_raw

if TYPE_CHECKING:
    from aifactory.library.inherit import LibrarySnapshot
    from aifactory.library.model import Item

AGENTS_FILE = ".factory/agents.yaml"
ROLES_FILE = ".factory/roles.yaml"
PROMPTS_DIR = ".factory/prompts"
WORKFLOWS_DIR = ".factory/workflows"
# skills of the repo: the source in .claude/skills/, a copy in .agents/skills/ (Skilly v repu)
SKILLS_DIR = ".claude/skills"
SKILLS_MIRROR_DIR = ".agents/skills"
EXTENSIONS_DIR = ".factory/extensions"
PROMPT_KINDS = ("system", "user")


def prompt_path(agent: str, kind: str) -> str:
    return f"{PROMPTS_DIR}/{agent}/{kind}.md"


@dataclass(frozen=True)
class AgentPrompts:
    system: str
    user: str


@dataclass(frozen=True)
class FactoryConfig:
    """The project configuration as one consistent snapshot."""

    settings: ProjectSettings
    agents: SSSFConfig
    roles: RoleRegistry
    prompts: Mapping[str, AgentPrompts]
    workflows: Mapping[str, dict[str, Any]]
    files: Mapping[str, str] = field(repr=False)
    source: str
    library: str | None = None
    """The library commit the inherited items come from; None: the seed (or none)."""
    inherited: frozenset[str] = frozenset()
    """``agent/<name>`` and ``workflow/<name>`` taken from the library."""

    @property
    def digest(self) -> str:
        """sha256 over every file read, so equal digests mean equal configuration."""
        hasher = hashlib.sha256()
        for rel in sorted(self.files):
            hasher.update(rel.encode("utf-8") + b"\0")
            hasher.update(self.files[rel].encode("utf-8") + b"\0")
        return hasher.hexdigest()


class _Reader:
    def __init__(self, source: ConfigSource) -> None:
        self.source = source
        self.files: dict[str, str] = {}
        self.issues: list[ConfigIssue] = []
        self.library_agents: dict[str, Item] = {}  # agents whose prompts come from the library
        self.inherited: set[str] = set()

    def read(self, rel: str) -> str | None:
        text = self.source.read_text(rel)
        if text is not None:
            self.files[rel] = text
        return text

    def label(self, rel: str) -> str:
        return self.source.label(rel)


def _canonical(value: object) -> str:
    from aifactory.harness import canonical

    try:
        return canonical(str(value))
    except ValueError:
        return str(value)


def _library_entry(
    item: Item,
    raw: Mapping[str, Any],
    settings: ProjectSettings,
    override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The roster entry of a library agent under the roster ``defaults`` and ``override``.

    A binding (harness, model, thinking) set there replaces the library's; a different
    harness drops the library's model too.
    """
    from aifactory.library.agent import roster_entry

    entry = roster_entry(item, settings)
    if item.defaults is not None and item.defaults.skills:
        entry["skills"] = list(item.defaults.skills)
    for over in (raw.get("defaults") or {}, override or {}):
        harness = over.get("harness") or over.get("coding_agent")
        if harness and _canonical(harness) != entry.get("harness"):
            entry.pop("model", None)
        if harness:
            entry.pop("harness", None)
        for key in ("model", "thinking"):
            if over.get(key) is not None:
                entry.pop(key, None)
    return {**entry, **(override or {})}


def _has_prompts(reader: _Reader, name: str) -> bool:
    return any(
        reader.source.read_text(prompt_path(name, kind)) is not None for kind in PROMPT_KINDS
    )


def _inherit_agents(
    reader: _Reader,
    raw: dict[str, Any],
    library: LibrarySnapshot | None,
    settings: ProjectSettings | None,
) -> dict[str, Any]:
    """``raw`` with the library agents the repo lacks and its overrides completed."""
    if library is None or not library.agents:
        return raw
    settings = settings if settings is not None else ProjectSettings()
    agents: list[dict[str, Any]] = []
    names: set[str] = set()
    for entry in raw.get("agents") or []:
        name = str(entry.get("name") or "")
        names.add(name)
        item = library.agents.get(name)
        if item is not None and not _has_prompts(reader, name):
            entry = _library_entry(item, raw, settings, entry)
            reader.library_agents[name] = item
            reader.inherited.add(f"agent/{name}")
        agents.append(entry)
    for name, item in library.agents.items():
        if name not in names:
            agents.append(_library_entry(item, raw, settings))
            reader.library_agents[name] = item
            reader.inherited.add(f"agent/{name}")
    return {**raw, "agents": agents}


def _load_agents(
    reader: _Reader,
    library: LibrarySnapshot | None = None,
    settings: ProjectSettings | None = None,
) -> SSSFConfig | None:
    label = reader.label(AGENTS_FILE)
    raw = parse_mapping(reader.read(AGENTS_FILE), label, reader.issues)
    if raw is None:
        return None
    agents = raw.get("agents") or []
    if not isinstance(agents, list) or not all(isinstance(a, dict) for a in agents):
        reader.issues.append(ConfigIssue(label, "agents: must be a list of mappings"))
        return None
    if raw.get("defaults") is not None and not isinstance(raw["defaults"], dict):
        reader.issues.append(ConfigIssue(label, "defaults: must be a mapping"))
        return None
    before = len(reader.issues)
    for index, agent in enumerate(agents):
        if "prompt_engineering" in agent:
            name = agent.get("name") or f"#{index}"
            reader.issues.append(
                ConfigIssue(
                    label,
                    f"agent '{name}': prompt_engineering is not allowed; "
                    f"prompts live in {PROMPTS_DIR}/{name}/",
                )
            )
    if len(reader.issues) > before:
        return None
    raw = _inherit_agents(reader, raw, library, settings)
    try:
        data = normalize_raw(raw)
    except HarnessConfigError as exc:
        reader.issues.extend(ConfigIssue(label, problem) for problem in exc.problems)
        return None
    for agent in data["agents"]:
        name = str(agent.get("name") or "")
        agent["prompt_engineering"] = {kind: prompt_path(name, kind) for kind in PROMPT_KINDS}
    try:
        return SSSFConfig.model_validate(data)
    except ValidationError as exc:
        reader.issues.extend(validation_issues(exc, label))
        return None


def _load_roles(reader: _Reader) -> RoleRegistry | None:
    """Load `.factory/roles.yaml`; a file without `code_steps` overlays the packaged registry."""
    label = reader.label(ROLES_FILE)
    text = reader.read(ROLES_FILE)
    try:
        if text is None:
            return load_roles()
        try:
            data = yamlload.safe_load(text)
        except yaml.YAMLError as exc:
            reader.issues.append(ConfigIssue(label, f"invalid YAML: {exc}"))
            return None
        return parse_roles(data)
    except RolesError as exc:
        reader.issues.extend(
            ConfigIssue(label, f"{i.path}: {i.code}: {i.message}") for i in exc.issues
        )
        return None


def _load_prompts(reader: _Reader, declared: list[str]) -> dict[str, AgentPrompts]:
    prefix = PROMPTS_DIR + "/"
    present: set[str] = set()
    for rel in reader.source.list_files(PROMPTS_DIR):
        parts = rel[len(prefix) :].split("/")
        if len(parts) >= 2 and parts[0]:
            present.add(parts[0])
    prompts: dict[str, AgentPrompts] = {}
    for name in [*declared, *sorted(present - set(declared))]:
        texts: dict[str, str] = {}
        for kind in PROMPT_KINDS:
            rel = prompt_path(name, kind)
            text = reader.read(rel)
            item = reader.library_agents.get(name)
            if text is None and item is not None:
                text = _library_text(reader, item, f"{kind}.md")
            if text is None:
                if name in declared:
                    reader.issues.append(
                        ConfigIssue(reader.label(rel), f"missing prompt for agent '{name}'")
                    )
                text = ""
            texts[kind] = text
        prompts[name] = AgentPrompts(system=texts["system"], user=texts["user"])
    return prompts


def _library_text(reader: _Reader, item: Item, path: str) -> str | None:
    """The text of a file of a library item; recorded for the digest."""
    found = item.file(path)
    if found is None:
        return None
    text = found.data.decode("utf-8")
    reader.files[f"library:{item.type}/{item.name}/{path}"] = text
    return text


def _load_workflows(
    reader: _Reader, library: LibrarySnapshot | None = None
) -> dict[str, dict[str, Any]]:
    workflows: dict[str, dict[str, Any]] = {}
    for rel in reader.source.list_files(WORKFLOWS_DIR):
        path = PurePosixPath(rel)
        if path.parent != PurePosixPath(WORKFLOWS_DIR) or path.suffix != ".yaml":
            continue
        label = reader.label(rel)
        text = reader.read(rel)
        data = parse_mapping(text, label, reader.issues)
        if data is not None:
            workflows[path.stem] = data
    if library is None:
        return workflows
    for name, item in library.workflows.items():
        if name in workflows:
            continue
        _library_text(reader, item, item.files[0].path)
        workflows[name] = library.workflow_data(name)  # a valid library item is a mapping
        reader.inherited.add(f"workflow/{name}")
    return workflows


class _RosterFile:
    """A ``ConfigSource`` whose ``.factory/agents.yaml`` is the text of one file."""

    def __init__(self, path: Path, text: str) -> None:
        self.path = path
        self.text = text

    def read_text(self, rel: str) -> str | None:
        return self.text if rel == AGENTS_FILE else None

    def list_files(self, rel_dir: str) -> list[str]:
        return []

    def label(self, rel: str) -> str:
        return str(self.path)

    @property
    def name(self) -> str:
        return str(self.path)


def load_roster_file(path: str | Path) -> SSSFConfig:
    """Load a HAIFA roster (``.factory/agents.yaml`` format) from ``path``.

    Raises ``ConfigError`` when the file is missing, unreadable or invalid.
    """
    file = Path(path)
    try:
        text = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError([ConfigIssue(str(file), f"cannot read the roster: {exc}")]) from exc
    reader = _Reader(_RosterFile(file, text))
    agents = _load_agents(reader)
    if reader.issues or agents is None:
        raise ConfigError(reader.issues or [ConfigIssue(str(file), "invalid roster")])
    return agents


def load_config(source: ConfigSource, library: LibrarySnapshot | None = None) -> FactoryConfig:
    """Load and validate ``.factory/`` from ``source``; raise ``ConfigError`` listing all issues.

    What the repo lacks comes from ``library`` (default: the library HEAD, else the seed).
    """
    if library is None:
        from aifactory.library.inherit import library_snapshot

        library = library_snapshot()
    reader = _Reader(source)
    settings = parse_project_settings(
        reader.read(CONFIG_FILE), reader.label(CONFIG_FILE), reader.issues
    )
    agents = _load_agents(reader, library, settings)
    roles = _load_roles(reader)
    declared = [agent.name for agent in agents.agents] if agents is not None else []
    prompts = _load_prompts(reader, declared)
    workflows = _load_workflows(reader, library)
    if reader.issues or settings is None or agents is None or roles is None:
        raise ConfigError(reader.issues)
    return FactoryConfig(
        settings=settings,
        agents=agents,
        roles=roles,
        prompts=prompts,
        workflows=workflows,
        files=dict(reader.files),
        source=source.name,
        library=library.commit,
        inherited=frozenset(reader.inherited),
    )


def load_worktree_config(root: Path) -> FactoryConfig:
    """Load ``.factory/`` from the working tree of the repository containing ``root``."""
    return load_config(WorktreeSource(repo_root(root)))


def write_prompts(config: FactoryConfig, dest: Path) -> SSSFConfig:
    """Write each agent's prompts under ``dest/<agent>/`` and point the roster at them."""
    agents = []
    for agent in config.agents.agents:
        prompts = config.prompts.get(agent.name, AgentPrompts(system="", user=""))
        folder = dest / agent.name
        folder.mkdir(parents=True, exist_ok=True)
        paths = {}
        for kind in PROMPT_KINDS:
            path = (folder / f"{kind}.md").resolve()
            path.write_text(getattr(prompts, kind), encoding="utf-8", newline="\n")
            paths[kind] = str(path)
        engineering = agent.prompt_engineering.model_copy(update=paths)
        agents.append(agent.model_copy(update={"prompt_engineering": engineering}))
    return config.agents.model_copy(update={"agents": agents})
