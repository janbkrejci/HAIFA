"""YAML workflows: load, validate and run them over the engine.

A workflow is data (product brief, "Workflow jako data"): a list of steps, where
a step is a role from the registry (``.factory/roles.yaml``) or a deterministic
code step (``test``, ``quality``, ``commit``, ``changes``, ``command``,
``rebase``, ``rebuild``), plus
``repeat`` loops with ``max``/``until``, ``when`` guards and an ``accept``
criterion. Conditions read only fields of typed envelopes and are never
evaluated as Python.
"""

from aifactory.engine.role_registry import Issue
from aifactory.workflow.check import CheckResult, check_agents, check_workflow
from aifactory.workflow.conditions import (
    Condition,
    ConditionError,
    evaluate,
    parse_condition,
    refs,
    truthy,
)
from aifactory.workflow.interpreter import (
    CodeRunner,
    EngineCodeRunner,
    StepRecord,
    WorkflowRun,
    preflight,
    run_workflow,
)
from aifactory.workflow.model import (
    CodeStep,
    Repeat,
    RoleStep,
    Step,
    Workflow,
    WorkflowError,
    walk,
)
from aifactory.workflow.parse import DEFAULT_WORKFLOWS_DIR, load_workflow, outline, parse_workflow
from aifactory.workflow.rebase import RebaseOutput, conflict_markers, rebase_onto, unmerged_files
from aifactory.workflow.rebuild import Generated, RebuildOutput, covered

__all__ = [
    "DEFAULT_WORKFLOWS_DIR",
    "CheckResult",
    "CodeRunner",
    "CodeStep",
    "Condition",
    "ConditionError",
    "EngineCodeRunner",
    "Generated",
    "RebaseOutput",
    "RebuildOutput",
    "Issue",
    "Repeat",
    "RoleStep",
    "Step",
    "StepRecord",
    "Workflow",
    "WorkflowError",
    "WorkflowRun",
    "check_agents",
    "check_workflow",
    "conflict_markers",
    "covered",
    "evaluate",
    "load_workflow",
    "outline",
    "parse_condition",
    "parse_workflow",
    "preflight",
    "rebase_onto",
    "refs",
    "run_workflow",
    "truthy",
    "unmerged_files",
    "walk",
]
