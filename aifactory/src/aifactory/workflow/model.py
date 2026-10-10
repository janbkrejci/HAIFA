"""The parsed form of a workflow: role steps, code steps and ``repeat`` loops."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from aifactory.engine.role_registry import Issue, RoleDef
from aifactory.harness.override import StepOverride
from aifactory.workflow.conditions import Condition

__all__ = [
    "DEFAULT_COMMAND_TIMEOUT",
    "CodeStep",
    "Repeat",
    "RoleStep",
    "Step",
    "Workflow",
    "WorkflowError",
    "walk",
]

DEFAULT_COMMAND_TIMEOUT = 600


class WorkflowError(Exception):
    """The workflow is invalid. ``issues`` lists every problem found."""

    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        super().__init__("; ".join(f"{i.path}: {i.code}: {i.message}" for i in issues))


@dataclass(frozen=True)
class RoleStep:
    name: str  # as written: also the key its result is read under
    role: RoleDef
    phase_id: str
    description: str
    path: str
    harness: str | None = None
    model: str | None = None
    thinking: str | None = None
    agent: str | None = None  # explicit `agent:` of the step; ``role.agent`` already holds it
    when: Condition | None = None
    inputs: tuple[str, ...] = ()  # steps whose latest result is ``previous_envelope``
    # Further template variables: (name, steps); each gets the latest result of
    # its steps (``input: {test_result: [test, retest]}``).
    variables: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def key(self) -> str:
        return self.name

    @property
    def override(self) -> StepOverride:
        return StepOverride(harness=self.harness, model=self.model, thinking=self.thinking)


@dataclass(frozen=True)
class CodeStep:
    name: str
    action: str
    key: str  # condition namespace name: the step name, or the id of a `command`
    phase_id: str
    owner: str
    description: str
    path: str
    argv: tuple[str, ...] = ()
    timeout: int = DEFAULT_COMMAND_TIMEOUT
    when: Condition | None = None


@dataclass(frozen=True)
class Repeat:
    """A bounded loop over ``steps``.

    ``until`` is checked after every body step that ran; the loop ends the moment
    it holds. ``until_tail`` is the index of the last body item that produces a
    result ``until`` reads (computed at parse time): in the last iteration the loop
    stops right after that item, because what follows it would repair work that
    nothing checks any more. ``None`` means the last iteration runs the whole body.
    """

    max: int
    until: Condition | None
    when: Condition | None
    steps: tuple[Step, ...]
    path: str
    until_tail: int | None = None


Step = RoleStep | CodeStep | Repeat


@dataclass(frozen=True)
class Workflow:
    name: str
    description: str
    steps: tuple[Step, ...]
    accept: Condition | None = None
    source: Path | None = None


def walk(steps: Sequence[Step]) -> Iterator[RoleStep | CodeStep]:
    """Every leaf step, depth first, in source order."""
    for step in steps:
        if isinstance(step, Repeat):
            yield from walk(step.steps)
        else:
            yield step
