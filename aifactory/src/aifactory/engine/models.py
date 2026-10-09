"""Which harness runs a model, and what the engineer is allowed to type.

One roster now spans two coding agents, so a model name has to answer a
question it never had to before: WHO runs this? The answer is derivable from
the name itself — `opus` and `claude-sonnet-5` are Claude Code, anything
written `provider/id` is pi — which is what lets a single `--model builder=opus`
switch the harness, the model and the billing in one flag, with no second
option to keep in sync.

Short names are resolved here too, because an ad-hoc chain is typed by hand:
`@longcat` should find `nousresearch/meituan/longcat-2.0:free` without the
engineer copying 40 characters out of a catalog, and should say so plainly when
it matches two models instead of guessing between them.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import agent_cc, agent_pi


@dataclass(frozen=True)
class ResolvedModel:
    """A model name, settled: which harness runs it and what to write in config."""
    harness: str                    # "pi" | "claude_code"
    model: str                      # the value an AgentConfig.model should hold
    label: str                      # what to show a human


def looks_like_claude(pattern: str) -> bool:
    """Is this a Claude Code model rather than a pi provider/id pattern?"""
    candidate = pattern.split("/", 1)[1] if pattern.startswith("anthropic/") else pattern
    return candidate in agent_cc.MODEL_ALIASES or candidate.startswith("claude-")


def resolve(pattern: str) -> ResolvedModel:
    """Resolve what the engineer typed into a harness plus a config-ready model.

    Claude first, because its aliases are short words that would also match a
    dozen pi catalog entries as substrings: `opus` means the Claude alias, and
    a pi model that happens to contain "opus" is reached by its provider/id.
    """
    pattern = pattern.strip()
    if not pattern:
        raise ValueError("empty model name")
    if looks_like_claude(pattern):
        _, model_id = agent_cc.resolve_model(pattern)
        return ResolvedModel(harness="claude_code", model=model_id, label=model_id)
    provider, model_id = agent_pi.resolve_model(pattern)   # raises on ambiguity
    return ResolvedModel(harness="pi", model=f"{provider}/{model_id}",
                         label=f"{provider}/{model_id}")


def free_models() -> list[str]:
    """Every pi model that costs nothing — the default menu for cheap chains."""
    return [f"{provider}/{model_id}"
            for provider, model_id, _ in agent_pi._pi_catalog()
            if model_id.endswith(":free")]


def claude_models() -> list[str]:
    """The Claude Code aliases, which always point at the current model."""
    return list(agent_cc.MODEL_ALIASES)


def catalog(free_only: bool = False, query: str = "") -> list[tuple[str, str, int]]:
    """Everything runnable, as (harness, model, context_window) rows.

    Claude first and unfiltered by `free_only`: nothing it runs is free, and a
    menu that hid it would be lying about what the factory can do.
    """
    rows: list[tuple[str, str, int]] = []
    for alias in claude_models():
        _, model_id = agent_cc.resolve_model(alias)
        rows.append(("claude_code", alias, agent_cc.context_window("anthropic", model_id)))
    for provider, model_id, window in agent_pi._pi_catalog():
        if free_only and not model_id.endswith(":free"):
            continue
        rows.append(("pi", f"{provider}/{model_id}", window))
    if query:
        rows = [row for row in rows if query.lower() in row[1].lower()]
    return rows
