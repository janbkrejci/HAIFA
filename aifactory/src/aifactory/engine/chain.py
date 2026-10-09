"""Parsing an ad-hoc chain, and saving one worth keeping.

A chain is what the engineer types instead of writing an ADW:

    scout@ling -> plan@longcat -> build@opus~high -> test -> review@sonnet

`name` picks a step from `roles.py`, `@model` says who runs it (see
`models.py`, which derives the harness from the name), and `~thinking` tunes
effort. Everything is optional but the name.

A model is attached to the STEP, not to the agent, so the same agent can appear
twice at two price points — `build@haiku -> fix@opus` is a cheap first pass
with an expensive repair. Switching an agent's model mid-run gives it a fresh
session by design: `agents._agent_session_id` rejoins a context window only
while the model is unchanged, and a context built by one model is not a context
the next one can be billed for or trusted to have read.

`~thinking` uses a tilde rather than a colon because pi model ids already
contain colons (`...longcat-2.0:free`), and a separator that appears inside the
value it separates is a bug waiting for its first free model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from . import models, roles
from .data_types import ChainStep, Recipe

RECIPE_DIR = Path("adws/adw_recipes")
SEPARATOR = "->"


def parse(text: str) -> list[ChainStep]:
    """`"plan@longcat -> build@opus"` -> the steps, validated against the registry."""
    steps: list[ChainStep] = []
    tokens = [token.strip() for line in text.splitlines()
              for token in line.split(SEPARATOR) if token.strip()]
    if not tokens:
        raise SystemExit("empty chain — write something like "
                         f"\"plan -> build -> test -> review\" ({SEPARATOR}-separated)")
    for token in tokens:
        steps.append(_parse_step(token))
    return steps


def _parse_step(token: str) -> ChainStep:
    name, _, tail = token.partition("@")
    model, _, thinking = tail.partition("~")
    name = name.strip().lower()
    if not (roles.is_role(name) or roles.is_code(name)):
        raise SystemExit(f"unknown step {name!r} — known steps: "
                         f"{', '.join(roles.known_steps())}")
    kind = "agent" if roles.is_role(name) else "code"
    if kind == "code" and (model or thinking):
        raise SystemExit(f"step {name!r} is deterministic code — it has no model to set")
    return ChainStep(name=name, kind=kind, model=model.strip(),
                     thinking=thinking.strip(), raw=token.strip())


def render(steps: list[ChainStep]) -> str:
    """The chain as the engineer would type it — for the console and recipes."""
    return f" {SEPARATOR} ".join(step.raw for step in steps)


def required_agents(steps: list[ChainStep]) -> list[str]:
    """Every roster name this chain will call, deduplicated, in first-seen order."""
    names: list[str] = []
    for step in steps:
        if step.kind != "agent":
            continue
        agent = roles.ROLES[step.name].agent
        if agent not in names:
            names.append(agent)
    return names


def resolve_models(steps: list[ChainStep]) -> dict[str, str]:
    """Settle every `@model` up front: `{step.raw: config-ready model}`.

    Done before the session is minted so a typo in the last step of a chain
    fails now, not twenty minutes and three agents later.
    """
    resolved: dict[str, str] = {}
    for step in steps:
        if step.model:
            try:
                resolved[step.raw] = models.resolve(step.model).model
            except ValueError as error:
                raise SystemExit(f"step {step.raw!r}: {error}") from None
    return resolved


def apply_step(cfg, step: ChainStep, resolved: dict[str, str]) -> str:
    """Point this step's agent at this step's model. Returns a line for the log."""
    if step.kind != "agent":
        return ""
    spec = roles.ROLES[step.name]
    agent = next(a for a in cfg.agents if a.name == spec.agent)
    note = ""
    model = resolved.get(step.raw, "")
    if model and (model != agent.model):
        harness = models.resolve(model).harness
        note = f"{agent.name}: {agent.coding_agent}/{agent.model} -> {harness}/{model}"
        agent.model = model
        if harness != agent.coding_agent:
            agent.coding_agent = harness
            if harness != "pi":
                agent.harness_engineering = []   # pi extensions are pi's
    if step.thinking and step.thinking != agent.thinking:
        note = f"{note}; thinking {agent.thinking} -> {step.thinking}" if note else \
               f"{agent.name}: thinking {agent.thinking} -> {step.thinking}"
        agent.thinking = step.thinking
    return note


# ── recipes ──────────────────────────────────────────────────────────────────

def recipe_path(name: str) -> Path:
    return RECIPE_DIR / f"{name}.yaml"


def load_recipe(name: str) -> Recipe:
    path = recipe_path(name)
    if not path.is_file():
        available = sorted(p.stem for p in RECIPE_DIR.glob("*.yaml")) if RECIPE_DIR.is_dir() else []
        raise SystemExit(f"no recipe {name!r} at {path} — "
                         f"available: {available or 'none saved yet'}")
    raw = yaml.safe_load(path.read_text()) or {}
    steps = [_parse_step(_token(entry)) for entry in raw.get("steps", [])]
    if not steps:
        raise SystemExit(f"recipe {name!r} has no steps")
    return Recipe(name=raw.get("name", name), description=raw.get("description", ""),
                  steps=steps)


def _token(entry) -> str:
    """A recipe step is either a written chain token or its expanded fields."""
    if isinstance(entry, str):
        return entry
    name = entry.get("step") or entry.get("role") or entry.get("code") or ""
    token = str(name)
    if entry.get("model"):
        token += f"@{entry['model']}"
    if entry.get("thinking"):
        token += f"~{entry['thinking']}"
    return token


def save_recipe(name: str, steps: list[ChainStep], description: str = "") -> Path:
    """Write this chain out so the next run is `--recipe <name>`."""
    path = recipe_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": name,
        "description": description or f"Saved chain: {render(steps)}",
        "steps": [{key: value for key, value in
                   (("step", step.name), ("model", step.model), ("thinking", step.thinking))
                   if value}
                  for step in steps],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8", newline="\n")
    return path


def with_implied_steps(steps: list[ChainStep]) -> tuple[list[ChainStep], list[str]]:
    """Insert the deterministic steps a chain cannot work without.

    `document` reads a diff, and the diff is produced by the `changes` step. An
    engineer typing a chain by hand should not have to remember that, but they
    do have to SEE it: the inserted step is returned as a note the run prints
    and records, never a silent addition to what was asked for.
    """
    filled: list[ChainStep] = []
    notes: list[str] = []
    for step in steps:
        if step.name in ("document", "documenter") and not any(
                earlier.name == "changes" for earlier in filled):
            filled.append(ChainStep(name="changes", kind="code", raw="changes"))
            notes.append("inserted `changes` before `document` — the documenter "
                         "writes from a diff, and that step is what produces one")
        filled.append(step)
    return filled, notes


def validate(cfg, steps: list[ChainStep], resolved: dict[str, str]) -> None:
    """Check every (agent, model) pair the chain will use, before anything spawns.

    A chain can point one agent at two models, so validating the roster once is
    not enough: each pairing is applied to a throwaway copy of the roster and
    checked on its own, which is what makes a typo in the last step fail in the
    first second.
    """
    from . import agents                      # local: agents imports the harnesses
    probe = cfg.model_copy(deep=True)
    seen: set[tuple[str, str]] = set()
    for step in steps:
        if step.kind != "agent":
            continue
        agent_name = roles.ROLES[step.name].agent
        key = (agent_name, resolved.get(step.raw, ""))
        if key in seen:
            continue
        seen.add(key)
        apply_step(probe, step, resolved)
        agents.validate(probe, [agent_name])
