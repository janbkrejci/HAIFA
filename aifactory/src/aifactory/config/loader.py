"""Load the whole ``.factory/`` configuration from one ``ConfigSource``.

Every file is read through the source, so a run that loads from a commit sees
exactly that commit's configuration. ``local.yaml`` is not part of it; see
``aifactory.config.settings.load_local``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pydantic import ValidationError

from aifactory.config.errors import ConfigError, ConfigIssue
from aifactory.config.manifest import MANIFEST_FILE, Manifest, parse_manifest
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
    manifest: Manifest | None = None

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
        self.seed_agents: set[str] = set()  # roster agents taken from the packaged seed

    def read(self, rel: str) -> str | None:
        text = self.source.read_text(rel)
        if text is not None:
            self.files[rel] = text
        return text

    def label(self, rel: str) -> str:
        return self.source.label(rel)


SEED_FALLBACK_AGENTS: tuple[str, ...] = ("tester", "test-reviewer")
"""Agents a roster without them gets from the packaged seed (both came with 3.0)."""


def _seed_prompt(agent: str, kind: str) -> str:
    return (resources.files("aifactory") / "seed" / "agents" / agent / f"{kind}.md").read_text(
        encoding="utf-8"
    )


def _seed_entry(agent: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    """A roster entry for a seed agent: the roster defaults, else the seed agent's own."""
    text = (resources.files("aifactory") / "seed" / "agents" / agent / "agent.yaml").read_text(
        encoding="utf-8"
    )
    seed = (yaml.safe_load(text) or {}).get("defaults") or {}
    defaults = raw.get("defaults") or {}
    entry: dict[str, Any] = {"name": agent, "writes": []}
    for key in ("harness", "model", "thinking"):
        if key not in defaults and key in seed:
            entry[key] = seed[key]
    return entry


def _load_agents(reader: _Reader) -> SSSFConfig | None:
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
    names = {str(a.get("name") or "") for a in agents}
    missing = [name for name in SEED_FALLBACK_AGENTS if name not in names]
    if missing and agents:
        # A roster from before 3.0 has no tester; it gets the seed's with the roster defaults.
        raw = {**raw, "agents": [*agents, *(_seed_entry(n, raw) for n in missing)]}
        reader.seed_agents.update(missing)
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
            data = yaml.safe_load(text)
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
            if text is None and name in reader.seed_agents:
                text = _seed_prompt(name, kind)
            if text is None:
                if name in declared:
                    reader.issues.append(
                        ConfigIssue(reader.label(rel), f"missing prompt for agent '{name}'")
                    )
                text = ""
            texts[kind] = text
        prompts[name] = AgentPrompts(system=texts["system"], user=texts["user"])
    return prompts


def _load_workflows(reader: _Reader) -> dict[str, dict[str, Any]]:
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
    return workflows


def _load_manifest(reader: _Reader) -> Manifest | None:
    """The manifest, or None (format 0). A format this HAIFA does not know raises at once."""
    text = reader.read(MANIFEST_FILE)
    if text is None:
        return None
    try:
        return parse_manifest(text, reader.label(MANIFEST_FILE))
    except ConfigError as exc:
        if exc.code != "invalid_config":
            raise
        reader.issues.extend(exc.issues)
        return None


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


def load_config(source: ConfigSource) -> FactoryConfig:
    """Load and validate ``.factory/`` from ``source``; raise ``ConfigError`` listing all issues.

    A manifest format newer than this HAIFA knows raises ``format_unsupported`` before
    anything else is read.
    """
    reader = _Reader(source)
    manifest = _load_manifest(reader)
    settings = parse_project_settings(
        reader.read(CONFIG_FILE), reader.label(CONFIG_FILE), reader.issues
    )
    agents = _load_agents(reader)
    roles = _load_roles(reader)
    declared = [agent.name for agent in agents.agents] if agents is not None else []
    prompts = _load_prompts(reader, declared)
    workflows = _load_workflows(reader)
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
        manifest=manifest,
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
