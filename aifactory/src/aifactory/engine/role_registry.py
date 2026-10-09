"""Role registry loaded from YAML: step name -> agent, output type, gates, description.

The ported sssf module ``aifactory.engine.roles`` keeps this table in Python. Here
it is data (``defaults/roles.yaml``, later ``.factory/roles.yaml``). Output types and
gates stay in the engine code; the YAML only picks them by name from
``aifactory.engine.data_types`` and ``aifactory.engine.gates``.

A roles mapping without ``code_steps`` is an overlay: it is merged onto the
packaged registry before validation (an existing role keeps the fields it does
not name; a new role needs ``agent``, ``output_type``, ``gates`` and
``description``). A mapping with ``code_steps`` replaces the registry.
"""

from __future__ import annotations

import copy  # aifactory: overlay merge works on copies of the packaged data
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from aifactory import packagedata  # aifactory: packaged data as of process start
from aifactory.engine import loader as engine

# Deterministic step actions. The step name is the action.
CODE_ACTIONS: tuple[str, ...] = (
    "test",
    "quality",
    "commit",
    "changes",
    "command",
    "rebase",
    "rebuild",
)
VERIFY_ACTIONS: tuple[str, ...] = ("test", "quality", "command")
COMMIT_FIELDS: frozenset[str] = frozenset({"sha", "committed", "message"})
# Fields of ``aifactory.workflow.rebase.RebaseOutput`` (spelled out: workflow imports this module).
REBASE_FIELDS: frozenset[str] = frozenset(
    {
        "status",
        "summary",
        "artifacts",
        "notes_for_next_agent",
        "onto",
        "before",
        "clean",
        "conflict",
        "files",
        "squashed",
    }
)
# Fields of ``aifactory.workflow.rebuild.RebuildOutput``.
REBUILD_FIELDS: frozenset[str] = frozenset(
    {"status", "summary", "artifacts", "notes_for_next_agent", "built", "files"}
)
RAN_FIELD = "ran"

DEFAULTS_DIR = Path(str(resources.files("aifactory.engine") / "defaults"))
DEFAULT_ROLES_PATH = DEFAULTS_DIR / "roles.yaml"

_ROLE_KEYS = frozenset({"agent", "output_type", "gates", "description", "aliases", "retries"})
_CODE_KEYS = frozenset({"owner", "description"})
# aifactory: fields a role new to an overlay must set (the rest have defaults)
OVERLAY_REQUIRED: tuple[str, ...] = ("agent", "output_type", "gates", "description")


@dataclass(frozen=True)
class Issue:
    """One validation problem: machine code, human message, where it is."""

    code: str
    message: str
    path: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "path": self.path}


class RolesError(Exception):
    """The role registry is invalid. ``issues`` lists every problem found."""

    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        super().__init__("; ".join(f"{i.path}: {i.code}: {i.message}" for i in issues))


@dataclass(frozen=True)
class RoleDef:
    """One agent step: who runs it, what it must return, what proves it."""

    name: str
    agent: str
    output_type: type[Any]
    output_type_name: str
    gates: tuple[Callable[..., Any], ...]
    gate_names: tuple[str, ...]
    description: str
    retries: int = 1


@dataclass(frozen=True)
class CodeStepDef:
    """One deterministic step. ``name`` is also the action it performs."""

    name: str
    owner: str
    description: str


@dataclass(frozen=True)
class RoleRegistry:
    """Every step name a workflow may use. Aliases map to the same ``RoleDef``."""

    roles: dict[str, RoleDef] = field(default_factory=dict)
    code_steps: dict[str, CodeStepDef] = field(default_factory=dict)

    def is_role(self, name: str) -> bool:
        return name in self.roles

    def is_code(self, name: str) -> bool:
        return name in self.code_steps

    def known_steps(self) -> list[str]:
        return sorted(set(self.roles) | set(self.code_steps))

    def result_fields(self, name: str) -> frozenset[str]:
        """Fields a condition may read from this step's result (always with ``ran``)."""
        data_types = engine.load_engine_module("data_types")
        fields: set[str]
        if name in self.roles:
            fields = set(self.roles[name].output_type.model_fields)
        elif name in VERIFY_ACTIONS:
            fields = set(data_types.VerifyOutput.model_fields)
        elif name == "changes":
            fields = set(data_types.ChangesOutput.model_fields)
        elif name == "commit":
            fields = set(COMMIT_FIELDS)
        elif name == "rebase":
            fields = set(REBASE_FIELDS)
        elif name == "rebuild":
            fields = set(REBUILD_FIELDS)
        else:
            raise KeyError(name)
        return frozenset(fields | {RAN_FIELD})


def check_description(name: str, text: object) -> str | None:
    """Rule 7 (vendor SKILL.md): a description must exist and not restate the name.

    Uses the engine's own ``PhaseParams`` validator, so the load-time check and
    the run-time check can never disagree. Returns the error text, or None.
    """
    if not isinstance(text, str):
        return f"phase {name!r}: description must be a string"
    data_types = engine.load_engine_module("data_types")
    try:
        data_types.PhaseParams(name=name, kind="code", owner="x", description=text)
    except ValidationError as error:
        messages = [str(e.get("msg", "")).removeprefix("Value error, ") for e in error.errors()]
        return "; ".join(messages) or str(error)
    return None


def _str_list(value: object) -> list[str] | None:
    if value is None:
        return []
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    return None


class _Loader:
    def __init__(self) -> None:
        self.issues: list[Issue] = []
        self.data_types = engine.load_engine_module("data_types")
        self.gates = engine.load_engine_module("gates")

    def add(self, code: str, message: str, path: str) -> None:
        self.issues.append(Issue(code, message, path))

    def output_type(self, value: object, path: str) -> type[Any] | None:
        if not isinstance(value, str) or not value:
            self.add("missing_output_type", "output_type must name a data_types class", path)
            return None
        found = getattr(self.data_types, value, None)
        base = self.data_types.EnvelopeBase
        if not isinstance(found, type):
            self.add("unknown_output_type", f"no class {value!r} in adw_modules.data_types", path)
            return None
        if not issubclass(found, base):
            self.add("invalid_output_type", f"{value!r} is not an EnvelopeBase subclass", path)
            return None
        return found

    def gate_list(self, value: object, path: str) -> list[tuple[str, Callable[..., Any]]]:
        names = _str_list(value)
        if names is None:
            self.add("invalid_gates", "gates must be a list of gate names", path)
            return []
        found: list[tuple[str, Callable[..., Any]]] = []
        for i, name in enumerate(names):
            gate = getattr(self.gates, name, None)
            if gate is None or not callable(gate) or name.startswith("_"):
                self.add("unknown_gate", f"no gate {name!r} in adw_modules.gates", f"{path}[{i}]")
                continue
            found.append((name, gate))
        return found

    def description(self, name: str, value: object, path: str) -> str:
        problem = check_description(name, value)
        if problem:
            self.add("bad_description", problem, path)
            return ""
        return " ".join(str(value).split())

    def role(self, name: str, spec: object, path: str) -> tuple[RoleDef | None, list[str]]:
        if not isinstance(spec, Mapping):
            self.add("invalid_role", "a role must be a mapping", path)
            return None, []
        for key in spec:
            if key not in _ROLE_KEYS:
                self.add("unknown_key", f"unknown role key {key!r}", f"{path}.{key}")
        agent = spec.get("agent")
        if not isinstance(agent, str) or not agent.strip():
            self.add("missing_agent", "agent must be a non-empty roster name", f"{path}.agent")
        output_type = self.output_type(spec.get("output_type"), f"{path}.output_type")
        gates = self.gate_list(spec.get("gates"), f"{path}.gates")
        description = self.description(name, spec.get("description"), f"{path}.description")
        retries = spec.get("retries", 1)
        if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
            self.add("invalid_retries", "retries must be an integer >= 0", f"{path}.retries")
            retries = 1
        aliases = _str_list(spec.get("aliases"))
        if aliases is None:
            self.add("invalid_aliases", "aliases must be a list of names", f"{path}.aliases")
            aliases = []
        if output_type is None or not isinstance(agent, str) or not agent.strip():
            return None, aliases
        role = RoleDef(
            name=name,
            agent=agent.strip(),
            output_type=output_type,
            output_type_name=output_type.__name__,
            gates=tuple(g for _, g in gates),
            gate_names=tuple(n for n, _ in gates),
            description=description,
            retries=retries,
        )
        return role, aliases

    def code_step(self, name: str, spec: object, path: str) -> CodeStepDef | None:
        if name not in CODE_ACTIONS:
            self.add(
                "unknown_code_step",
                f"unknown code step {name!r}, known actions: {', '.join(CODE_ACTIONS)}",
                path,
            )
            return None
        if not isinstance(spec, Mapping):
            self.add("invalid_code_step", "a code step must be a mapping", path)
            return None
        for key in spec:
            if key not in _CODE_KEYS:
                self.add("unknown_key", f"unknown code step key {key!r}", f"{path}.{key}")
        owner = spec.get("owner")
        if not isinstance(owner, str) or not owner.strip():
            self.add("missing_owner", "owner must be a non-empty name", f"{path}.owner")
            return None
        description = self.description(name, spec.get("description"), f"{path}.description")
        return CodeStepDef(name=name, owner=owner.strip(), description=description)

    def registry(self, data: object) -> RoleRegistry:
        if not isinstance(data, Mapping):
            self.add("not_a_mapping", "the roles file must be a mapping", "")
            return RoleRegistry()
        for key in data:
            if key not in ("roles", "code_steps"):
                self.add("unknown_key", f"unknown top-level key {key!r}", str(key))
        raw_roles = data.get("roles")
        raw_code = data.get("code_steps")
        if not isinstance(raw_roles, Mapping) or not raw_roles:
            self.add("missing_roles", "`roles` must be a non-empty mapping", "roles")
            raw_roles = {}
        if not isinstance(raw_code, Mapping):
            self.add("missing_code_steps", "`code_steps` must be a mapping", "code_steps")
            raw_code = {}

        code_steps: dict[str, CodeStepDef] = {}
        for name, spec in raw_code.items():
            step = self.code_step(str(name), spec, f"code_steps.{name}")
            if step is not None:
                code_steps[step.name] = step
        for action in CODE_ACTIONS:
            if action not in raw_code:
                self.add("missing_code_step", f"code step {action!r} is not defined", "code_steps")

        roles: dict[str, RoleDef] = {}
        seen: set[str] = set()
        pending: list[tuple[str, RoleDef | None, str]] = []
        for name, spec in raw_roles.items():
            path = f"roles.{name}"
            role, aliases = self.role(str(name), spec, path)
            pending.append((str(name), role, path))
            pending.extend((a, role, f"{path}.aliases") for a in aliases)
        for name, role, path in pending:
            if name in code_steps:
                self.add("alias_conflict", f"{name!r} is already a code step", path)
            elif name in seen:
                self.add("alias_conflict", f"{name!r} is defined more than once", path)
            elif role is not None:
                roles[name] = role
            seen.add(name)
        return RoleRegistry(roles=roles, code_steps=code_steps)


def _default_data() -> dict[str, Any]:  # aifactory: raw packaged registry, base of an overlay
    data = yaml.safe_load(packagedata.read_text(DEFAULT_ROLES_PATH))  # aifactory: start-time data
    assert isinstance(data, dict)
    return data


def is_overlay(data: object) -> bool:  # aifactory
    """A roles mapping without ``code_steps`` overlays the packaged registry."""
    return isinstance(data, Mapping) and "code_steps" not in data


def merge_overlay(data: Mapping[Any, Any], base: Mapping[Any, Any]) -> dict[str, Any]:  # aifactory
    """Merge an overlay onto ``base`` (raw YAML); raise ``RolesError`` on structural problems.

    The result still goes through the normal validation, so unknown keys, output
    types and gates are reported with the same codes and paths as in a full file.
    """
    issues: list[Issue] = []
    raw = data.get("roles")
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise RolesError([Issue("missing_roles", "`roles` must be a mapping", "roles")])
    base_roles: Mapping[Any, Any] = base.get("roles") or {}
    alias_of: dict[str, str] = {}
    for canonical_name, spec in base_roles.items():
        if isinstance(spec, Mapping):
            for alias in spec.get("aliases") or []:
                alias_of[str(alias)] = str(canonical_name)
    merged: dict[str, Any] = {str(k): copy.deepcopy(v) for k, v in base_roles.items()}
    for name, spec in raw.items():
        path = f"roles.{name}"
        if not isinstance(spec, Mapping):
            issues.append(Issue("invalid_role", "a role must be a mapping", path))
            continue
        if name in alias_of:
            canonical_name = alias_of[name]
            issues.append(
                Issue(
                    "alias_conflict",
                    f"{name!r} is an alias of {canonical_name!r} — override {canonical_name!r}",
                    path,
                )
            )
            continue
        if name in base_roles:
            merged[str(name)] = {**merged[str(name)], **spec}
            continue
        missing = [key for key in OVERLAY_REQUIRED if key not in spec]
        for key in missing:
            issues.append(
                Issue(
                    "missing_key",
                    f"a new role needs {key!r} (this file overlays the packaged registry; "
                    "add `code_steps` to replace it)",
                    f"{path}.{key}",
                )
            )
        if not missing:
            merged[str(name)] = dict(spec)
    if issues:
        raise RolesError(issues)
    result: dict[str, Any] = {str(k): v for k, v in data.items()}
    result["roles"] = merged
    result["code_steps"] = copy.deepcopy(base.get("code_steps"))
    return result


def parse_roles(data: object, base: Mapping[Any, Any] | None = None) -> RoleRegistry:
    """Build a registry from already-parsed YAML; raise ``RolesError`` on any problem.

    A mapping without ``code_steps`` overlays ``base`` (default: the packaged registry).
    """
    # aifactory: a file without `code_steps` overlays the packaged registry (D24)
    if is_overlay(data):
        assert isinstance(data, Mapping)
        data = merge_overlay(data, base if base is not None else _default_data())
    loader = _Loader()
    registry = loader.registry(data)
    if loader.issues:
        raise RolesError(loader.issues)
    return registry


def load_roles(path: Path | None = None) -> RoleRegistry:
    """Load the role registry (default: the packaged ``defaults/roles.yaml``)."""
    source = path or DEFAULT_ROLES_PATH
    try:
        text = packagedata.read_text(source)  # aifactory: start-time data for the packaged file
    except OSError as error:
        raise RolesError([Issue("missing_file", str(error), str(source))]) from error
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise RolesError([Issue("invalid_yaml", str(error), str(source))]) from error
    return parse_roles(data)
