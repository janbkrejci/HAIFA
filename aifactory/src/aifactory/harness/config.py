"""The harness is written on the agent, never inferred from the model (D13).

The engine's config types (``aifactory.engine.data_types``) type ``coding_agent``
as ``Literal["pi", "claude_code"]`` with a default of ``"pi"``. HAIFA needs
``claude | codex | pi`` and no default at all, so this module subclasses them
(``isinstance`` with the engine's classes still holds) and loads configs
through its own ``load_config``. The engine's module globals are left alone.

In YAML the key is ``harness``; ``coding_agent`` is accepted for sssf
compatibility. Both end up in ``coding_agent``, which is what the engine reads.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from aifactory.engine import data_types as dt
from aifactory.harness import HARNESSES, HarnessName, canonical, install

# Keys an agent inherits from `defaults`, exactly as `agents.load_config` does.
INHERITED = (
    "coding_agent",
    "model",
    "thinking",
    "color",
    "tools",
    "writes",
    "disallowed_commands",
)


class HarnessConfigError(ValueError):
    """The config names no harness, an unknown one, or two conflicting ones."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        super().__init__("harness config invalid:\n- " + "\n- ".join(self.problems))


class AgentConfig(dt.AgentConfig):
    coding_agent: HarnessName  # type: ignore[assignment]

    @property
    def harness(self) -> str:
        return str(self.coding_agent)


class ConfigDefaults(dt.ConfigDefaults):
    coding_agent: HarnessName | None = None  # type: ignore[assignment]

    @property
    def harness(self) -> str | None:
        return None if self.coding_agent is None else str(self.coding_agent)


class SSSFConfig(dt.SSSFConfig):
    defaults: ConfigDefaults = Field(default_factory=ConfigDefaults)
    agents: list[AgentConfig] = Field(default_factory=list)  # type: ignore[assignment]


def _harness_of(entry: dict[str, Any], label: str, problems: list[str]) -> str | None:
    """Fold ``harness``/``coding_agent`` of one mapping into a canonical name (or None)."""
    values: dict[str, str] = {}
    for key in ("harness", "coding_agent"):
        if entry.get(key) is None:
            continue
        raw = str(entry[key])
        try:
            values[key] = canonical(raw)
        except ValueError as exc:
            problems.append(f"{label}: {exc}")
            return None
    entry.pop("harness", None)
    entry.pop("coding_agent", None)
    if not values:
        return None
    if len(set(values.values())) > 1:
        problems.append(
            f"{label}: harness {values['harness']!r} conflicts with "
            f"coding_agent {values['coding_agent']!r}"
        )
        return None
    return next(iter(values.values()))


def normalize_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """A config mapping with an explicit, canonical ``coding_agent`` on every agent.

    Raises ``HarnessConfigError`` listing every problem. Nothing is ever filled
    in from the model name or from the engine's ``"pi"`` default.
    """
    data = copy.deepcopy(raw or {})
    problems: list[str] = []
    defaults = data.get("defaults") or {}
    data["defaults"] = defaults
    default_harness = _harness_of(defaults, "defaults", problems)
    if default_harness is not None:
        defaults["coding_agent"] = default_harness

    choices = "|".join(HARNESSES)
    agents = data.get("agents") or []
    data["agents"] = agents
    for index, agent in enumerate(agents):
        label = f"agent {agent.get('name') or f'#{index}'!r}"
        before = len(problems)
        chosen = _harness_of(agent, label, problems)
        if chosen is not None:
            agent["coding_agent"] = chosen
        for key in INHERITED:
            if key in defaults and defaults[key] is not None:
                agent.setdefault(key, defaults[key])
        agent.setdefault("harness_engineering", defaults.get("harness_engineering", []))
        if "coding_agent" not in agent and len(problems) == before:
            problems.append(f"{label}: harness is not set ({choices})")
    if problems:
        raise HarnessConfigError(problems)
    return data


def load_config(path: str | Path) -> SSSFConfig:
    """Load a roster YAML with explicit harnesses into the widened config types."""
    raw = yaml.safe_load(Path(path).read_text()) or {}
    if not isinstance(raw, dict):
        raise HarnessConfigError([f"{path}: config must be a mapping"])
    return SSSFConfig.model_validate(normalize_raw(raw))


def validate(cfg: dt.SSSFConfig, required: list[str]) -> None:
    """Register every harness, then let the engine check ``required`` agents.

    The engine resolves each model against the agent's chosen harness and
    refuses ``harness_engineering`` outside pi. Failures are ``SystemExit``.
    """
    agents = install()
    agents.validate(cfg, required)
