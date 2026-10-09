"""Per-step override of harness, model and thinking (D13).

A workflow step may run its agent on a different harness, model or thinking
level. The override is explicit: changing only the model never changes the
harness. ``step_override`` swaps the agent in ``cfg.agents`` for the duration
of one phase, because the engine resolves the agent by name from there.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, TypeVar

from aifactory.engine import data_types as dt
from aifactory.harness import canonical, load
from aifactory.harness.config import HarnessConfigError

THINKING_LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")

AgentT = TypeVar("AgentT", bound=dt.AgentConfig)


@dataclass(frozen=True)
class StepOverride:
    harness: str | None = None
    model: str | None = None
    thinking: str | None = None


def effective_agent(agent: AgentT, override: StepOverride) -> AgentT:
    """The agent as this step runs it: only the fields the override names change."""
    update: dict[str, Any] = {}
    if override.harness is not None:
        update["coding_agent"] = canonical(override.harness)
    if override.model is not None:
        update["model"] = override.model
    if override.thinking is not None:
        update["thinking"] = override.thinking
    harness = update.get("coding_agent", agent.coding_agent)
    if harness != "pi" and agent.harness_engineering:
        # pi extensions belong to pi only
        update["harness_engineering"] = []
    return agent.model_copy(update=update)


def check_override(agent: dt.AgentConfig, override: StepOverride) -> list[str]:
    """Problems with applying ``override`` to ``agent``; runs nothing."""
    label = f"agent {agent.name!r}"
    problems: list[str] = []
    harness = str(agent.coding_agent)
    if override.harness is not None:
        try:
            harness = canonical(override.harness)
        except ValueError as exc:
            problems.append(f"{label}: {exc}")
            return problems
    if override.thinking is not None and override.thinking not in THINKING_LEVELS:
        problems.append(
            f"{label}: thinking {override.thinking!r} is not one of {list(THINKING_LEVELS)}"
        )
    model = override.model if override.model is not None else agent.model
    try:
        load(harness).resolve_model(model)
    except ValueError as exc:
        problems.append(f"{label}: harness {harness!r} cannot run model {model!r}: {exc}")
    return problems


@contextmanager
def step_override(
    cfg: dt.SSSFConfig, agent_name: str, override: StepOverride
) -> Iterator[dt.AgentConfig]:
    """Run the body with ``agent_name`` replaced by its overridden form.

    Invalid overrides raise ``HarnessConfigError`` before anything changes; the
    original agent is always put back, even when the body raises.
    """
    index = next((i for i, a in enumerate(cfg.agents) if a.name == agent_name), None)
    if index is None:
        raise HarnessConfigError([f"agent {agent_name!r} is not defined in the config"])
    original = cfg.agents[index]
    problems = check_override(original, override)
    if problems:
        raise HarnessConfigError(problems)
    effective = effective_agent(original, override)
    cfg.agents[index] = effective
    try:
        yield effective
    finally:
        cfg.agents[index] = original
