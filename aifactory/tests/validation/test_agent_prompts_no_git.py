"""Every agent that changes files is told to leave git to the workflow.

A commit made by the agent is undone by the write guard and fails the phase,
so the prompt must forbid it. No model is called; only files are read.
"""

from __future__ import annotations

import pytest
import yaml
from validation.sandbox import AIFACTORY_DIR

ROLES = AIFACTORY_DIR / "src/aifactory/engine/defaults/roles.yaml"
PROMPTS = AIFACTORY_DIR / "validation/template/.factory/prompts"
WRITING_ROLES = ("plan", "build", "fix", "revise", "resolve", "document")
RULE_FRAGMENTS = (
    "Do not commit: never run `git commit`",
    "Do not push: never run `git push`",
    "Do not create, switch or delete git branches",
    "the workflow commits them",
)


def writing_agents() -> set[str]:
    roles = yaml.safe_load(ROLES.read_text("utf-8"))["roles"]
    return {roles[r]["agent"] for r in WRITING_ROLES}


def test_writing_agents_are_known() -> None:
    assert writing_agents() == {"planner", "builder", "documenter"}


@pytest.mark.parametrize("agent", sorted(writing_agents()))
def test_prompt_forbids_git(agent: str) -> None:
    text = (PROMPTS / agent / "system.md").read_text("utf-8")
    for fragment in RULE_FRAGMENTS:
        assert fragment in text, (agent, fragment)
