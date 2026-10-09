"""Static validation of a workflow file for ``factory workflow check`` and preflight.

Checks the workflow against the role registry and, when a roster is given,
checks every agent the workflow uses (with each step's harness/model/thinking
override) against it. Nothing runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aifactory.engine import data_types as dt
from aifactory.engine.role_registry import Issue, RoleRegistry
from aifactory.harness.override import check_override
from aifactory.workflow.model import RoleStep, Workflow, WorkflowError, walk
from aifactory.workflow.parse import load_workflow, outline

__all__ = ["CheckResult", "check_agents", "check_workflow"]

NO_AGENTS_WARNING = "agents not checked: no .factory/agents.yaml"


def _role_steps(workflow: Workflow) -> list[RoleStep]:
    """One role step per distinct (agent, harness, model, thinking), in source order."""
    seen: set[tuple[str, str | None, str | None, str | None]] = set()
    steps: list[RoleStep] = []
    for step in walk(workflow.steps):
        if not isinstance(step, RoleStep):
            continue
        key = (step.role.agent, step.harness, step.model, step.thinking)
        if key not in seen:
            seen.add(key)
            steps.append(step)
    return steps


def check_agents(workflow: Workflow, cfg: dt.SSSFConfig) -> list[Issue]:
    """Every agent the workflow uses must be in the roster and accept the step's override.

    A step's own `agent:` replaces the role's agent; an unknown one is reported at
    the step's `.agent` path.
    """
    roster = {agent.name: agent for agent in cfg.agents}
    issues: list[Issue] = []
    for step in _role_steps(workflow):
        name = step.role.agent
        agent = roster.get(name)
        if agent is None:
            known = ", ".join(sorted(roster)) or "none"
            if step.agent is not None:
                issues.append(
                    Issue(
                        "unknown_agent",
                        f"step {step.name!r} sets agent {name!r}, which is not in the roster "
                        f"(agents: {known})",
                        f"{step.path}.agent",
                    )
                )
                continue
            issues.append(
                Issue(
                    "unknown_agent",
                    f"step {step.name!r} needs agent {name!r}, which is not in the roster "
                    f"(agents: {known})",
                    step.path,
                )
            )
            continue
        for problem in check_override(agent, step.override):
            issues.append(Issue("invalid_agent", problem, step.path))
    return issues


@dataclass
class CheckResult:
    ok: bool
    path: str
    workflow: str | None
    issues: list[Issue]
    outline: list[dict[str, Any]]
    roles_source: str = "packaged defaults"
    agents_source: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "workflow": self.workflow,
            "errors": [i.to_dict() for i in self.issues],
            "steps": self.outline,
            "roles": self.roles_source,
            "agents": self.agents_source,
            "warnings": list(self.warnings),
        }


def check_workflow(
    path: Path,
    roles: RoleRegistry,
    cfg: dt.SSSFConfig | None = None,
    *,
    roles_source: str = "packaged defaults",
    agents_source: str | None = None,
) -> CheckResult:
    """Validate a workflow file against ``roles`` and, if given, the roster ``cfg``."""
    warnings = [] if cfg is not None else [NO_AGENTS_WARNING]

    def result(workflow: Workflow | None, issues: list[Issue]) -> CheckResult:
        return CheckResult(
            ok=not issues,
            path=str(path),
            workflow=workflow.name if workflow is not None else None,
            issues=issues,
            outline=outline(workflow.steps) if workflow is not None else [],
            roles_source=roles_source,
            agents_source=agents_source,
            warnings=warnings,
        )

    if not path.is_file():
        return result(None, [Issue("missing_file", f"no workflow file at {path}", "")])
    try:
        workflow = load_workflow(path, roles)
    except WorkflowError as error:
        return result(None, error.issues)
    issues = check_agents(workflow, cfg) if cfg is not None else []
    return result(workflow, issues)
