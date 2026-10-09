"""The flags every ADW shares, in one place.

`--model` exists because the roster is a starting point, not a verdict. Trying
a chain on a free model and then on Opus should cost one flag, not a commit to
`sssf.config.yaml` — and because a model name says which harness runs it (see
`models.py`), the same flag moves an agent between pi and Claude Code without a
second option that could disagree with the first.
"""

from __future__ import annotations

import argparse

from . import models
from .data_types import ModelOverrides, SSSFConfig

MODEL_HELP = (
    "override a model for this run: --model opus (every agent) or "
    "--model builder=opus (one agent). Repeatable. The model name decides the "
    "harness: an alias or claude-* id runs on Claude Code, provider/id on pi."
)


def add_common(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """The three flags every ADW answers to, plus --model."""
    parser.add_argument("--config", default="adws/adw_sssf_config/sssf.config.yaml")
    parser.add_argument("--adw-id", default=None, help="join or pin an existing session")
    parser.add_argument("--model", action="append", default=[], metavar="[AGENT=]MODEL",
                        help=MODEL_HELP)
    return parser


def parse_overrides(values: list[str]) -> ModelOverrides:
    """`["opus", "planner=haiku"]` -> the overrides to apply before validation."""
    overrides = ModelOverrides()
    for value in values or []:
        agent, _, model = value.partition("=")
        if model:
            overrides.per_agent[agent.strip()] = model.strip()
        else:
            overrides.every_agent = agent.strip()
    return overrides


def apply_overrides(cfg: SSSFConfig, overrides: ModelOverrides) -> list[str]:
    """Rewrite the roster in memory. Returns one line per change, for the log.

    Switching harness is a real switch, not just a different model string: pi
    extensions are pi's, so an agent moved to Claude Code loses the
    `harness_engineering` its roster entry names. Dropping that silently would
    leave the agent's prompt promising tools that no longer exist, so it is
    dropped loudly here instead.
    """
    if not overrides.per_agent and not overrides.every_agent:
        return []
    known = {agent.name for agent in cfg.agents}
    unknown = set(overrides.per_agent) - known
    if unknown:
        raise SystemExit(f"--model names unknown agent(s): {sorted(unknown)} — "
                         f"the roster has {sorted(known)}")

    changes = []
    for agent in cfg.agents:
        pattern = overrides.per_agent.get(agent.name) or overrides.every_agent
        if not pattern:
            continue
        resolved = models.resolve(pattern)
        was = f"{agent.coding_agent}/{agent.model}"
        agent.model = resolved.model
        if resolved.harness != agent.coding_agent:
            agent.coding_agent = resolved.harness
            if resolved.harness != "pi" and agent.harness_engineering:
                changes.append(f"{agent.name}: dropped pi extensions "
                               f"{agent.harness_engineering} — Claude Code cannot load them")
                agent.harness_engineering = []
        changes.append(f"{agent.name}: {was} -> {agent.coding_agent}/{agent.model}")
    return changes


def load(config: str, model_flags: list[str]) -> tuple[SSSFConfig, list[str]]:
    """Load the roster with this run's overrides already applied."""
    from . import agents                      # local: agents imports the harnesses
    cfg = agents.load_config(config)
    return cfg, apply_overrides(cfg, parse_overrides(model_flags))
