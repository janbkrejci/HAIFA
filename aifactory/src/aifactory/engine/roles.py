"""What each step in a composed chain IS — the registry `adw_compose` reads.

A hand-written ADW states its own output types, gates and descriptions inline,
which is right: that file is the workflow. A chain typed on the command line
has nowhere to say them, so the knowledge lives here once, keyed by the step
name the engineer types. `plan` always means the planner, always parses as
PlanOutput, always runs the artifact gates — whichever model happens to be
behind it today.

Adding a role is adding a row. Nothing in `adw_compose` knows the names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Type

from . import gates
from .data_types import (BuildOutput, DocumentOutput, EnvelopeBase,
                         GenericOutput, PlanOutput, ReviewOutput, ScoutOutput)


@dataclass(frozen=True)
class RoleSpec:
    """One agent step: who runs it, what it must return, what proves it."""

    agent: str                              # the roster name this step calls
    output_type: Type[EnvelopeBase]
    description: str                        # shown in the trace, the console and the UI
    gates: list[Callable] = field(default_factory=list)
    retries: int = 1


@dataclass(frozen=True)
class CodeSpec:
    """One deterministic step: a known command, run by code, never by an agent."""

    action: str                             # dispatched in adw_compose
    description: str


# Step name -> role. Aliases share a spec so `plan` and `planner` both work:
# the chain is typed by hand and both spellings are the obvious one to someone.
ROLES: dict[str, RoleSpec] = {
    "plan": RoleSpec(agent="planner", output_type=PlanOutput,
                     description="Turn the request into an implementable plan",
                     gates=[gates.artifacts_exist, gates.files_non_empty]),
    "build": RoleSpec(agent="builder", output_type=BuildOutput,
                      description="Implement what the previous step asked for",
                      gates=[gates.diff_matches_claims]),
    "scout": RoleSpec(agent="scout", output_type=ScoutOutput,
                      description="Find and report where things live; change nothing",
                      gates=[gates.artifacts_exist]),
    "review": RoleSpec(agent="reviewer", output_type=ReviewOutput,
                       description="Confirm the work matches what was asked for",
                       gates=[gates.artifacts_exist, gates.verdict_consistent]),
    "document": RoleSpec(agent="documenter", output_type=DocumentOutput,
                         description="Write up the completed change from the diff",
                         gates=[gates.artifacts_exist, gates.files_non_empty]),
    "ask": RoleSpec(agent="builder", output_type=GenericOutput,
                    description="Answer the request directly, with no fixed output shape"),
}
ROLES["planner"] = ROLES["plan"]
ROLES["builder"] = ROLES["build"]
ROLES["reviewer"] = ROLES["review"]
ROLES["documenter"] = ROLES["document"]
ROLES["fix"] = RoleSpec(agent="builder", output_type=BuildOutput,
                        description="Repair what the previous step reported, from its "
                                    "verbatim output",
                        gates=[gates.diff_matches_claims])

# Deterministic steps. A known command is code, not an agent (SKILL.md rule 8).
CODE_STEPS: dict[str, CodeSpec] = {
    "test": CodeSpec(action="test",
                     description="Run the suite — a known command, so code runs it and no "
                                 "agent has to rediscover it"),
    "quality": CodeSpec(action="quality",
                        description="Run lint, typecheck and build — known commands, all of them"),
    "commit": CodeSpec(action="commit",
                       description="Commit what the previous step produced, in its own words"),
    "changes": CodeSpec(action="changes",
                        description="Diff the run against its pinned baseline, for the documenter"),
}


def is_role(name: str) -> bool:
    return name in ROLES


def is_code(name: str) -> bool:
    return name in CODE_STEPS


def known_steps() -> list[str]:
    """Every step name a chain may use, for error messages and --help."""
    return sorted(set(ROLES) | set(CODE_STEPS))
