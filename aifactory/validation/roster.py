"""The agent roster of the sandbox: agents.yaml and the workflow, optionally from --roster DIR.

``--roster DIR`` replaces the template's ``.factory/agents.yaml`` and
``.factory/workflows/simple-sdlc.yaml`` with ``DIR/agents.yaml`` and
``DIR/workflows/simple-sdlc.yaml`` for one run. The prompts (with the
validation rule of the reviewer) stay those of the template. ``step_harnesses``
reads the effective harness of every agent step, which R1 and R10 compare the
trace with.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Mapping
from pathlib import Path

import yaml

from validation.sandbox import HAIFA_ROOT, SetupError

ROSTER_FILES: tuple[tuple[str, str], ...] = (
    ("agents.yaml", ".factory/agents.yaml"),
    ("workflows/simple-sdlc.yaml", ".factory/workflows/simple-sdlc.yaml"),
)
WORKFLOW = ".factory/workflows/simple-sdlc.yaml"
AGENTS_CONFIG = ".factory/agents.yaml"
REQUIRED_AGENTS = (
    "planner",
    "builder",
    "tester",
    "test-reviewer",
    "reviewer",
    "documenter",
)


def _agent_names(path: Path) -> list[str]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SetupError(f"cannot read {path}: {exc}") from exc
    entries = data.get("agents") if isinstance(data, dict) else None
    return [
        str(e["name"])
        for e in (entries if isinstance(entries, list) else [])
        if isinstance(e, dict) and e.get("name")
    ]


def resolve_roster(value: Path) -> Path:
    """The absolute roster dir (relative to the HAIFA root); ``SetupError`` if incomplete."""
    path = value if value.is_absolute() else HAIFA_ROOT / value
    path = path.resolve()
    if not path.is_dir():
        raise SetupError(f"--roster {value}: {path} is not a directory")
    missing = [src for src, _ in ROSTER_FILES if not (path / src).is_file()]
    if missing:
        raise SetupError(f"--roster {value}: missing {', '.join(missing)} in {path}")
    names = _agent_names(path / "agents.yaml")
    absent = [a for a in REQUIRED_AGENTS if a not in names]
    if absent:
        raise SetupError(
            f"--roster {value}: agents.yaml lacks agent(s) {', '.join(absent)} "
            f"(needs {', '.join(REQUIRED_AGENTS)})"
        )
    return path


def apply_roster(dest: Path, roster: Path) -> list[str]:
    """Copy the roster files over the materialized template in `dest`; return the targets."""
    written: list[str] = []
    for src, target in ROSTER_FILES:
        path = dest / target
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(roster / src, path)
        written.append(target)
    return written


def canonical(name: str) -> str:
    """The canonical harness name (``claude_code`` -> ``claude``); unknown names as they are."""
    from aifactory.harness import ALIASES

    return ALIASES.get(name, name)


def agent_harnesses(agents_yaml: Path) -> dict[str, str]:
    """The harness of every agent of an ``agents.yaml`` (defaults applied), by name."""
    from aifactory.harness.config import HarnessConfigError, normalize_raw

    try:
        raw = yaml.safe_load(agents_yaml.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise SetupError(f"{agents_yaml}: not a mapping")
        data = normalize_raw(raw)
    except (HarnessConfigError, OSError, yaml.YAMLError) as exc:
        raise SetupError(f"cannot read {agents_yaml}: {exc}") from exc
    return {
        str(agent["name"]): canonical(str(agent["coding_agent"]))
        for agent in data["agents"]
        if agent.get("name")
    }


def workflow_harnesses(agents_yaml: Path, workflow_yaml: Path) -> dict[str, str]:
    """The effective harness of every agent step of `workflow_yaml`, by phase id."""
    from aifactory.engine.role_registry import load_roles
    from aifactory.workflow import RoleStep, WorkflowError, parse_workflow, walk

    try:
        data = yaml.safe_load(workflow_yaml.read_text(encoding="utf-8"))
        workflow = parse_workflow(data, load_roles())
    except (WorkflowError, OSError, yaml.YAMLError) as exc:
        raise SetupError(f"cannot read the workflow {workflow_yaml}: {exc}") from exc
    agents = agent_harnesses(agents_yaml)
    harnesses: dict[str, str] = {}
    for step in walk(workflow.steps):
        if not isinstance(step, RoleStep):
            continue
        harness = step.harness or agents.get(step.role.agent)
        if not harness:
            raise SetupError(
                f"step {step.phase_id}: agent {step.role.agent!r} is not in {agents_yaml}"
            )
        harnesses[step.phase_id] = canonical(harness)
    return harnesses


def step_harnesses(repo: Path) -> dict[str, str]:
    """The effective harness of every agent step of the workflow in `repo`, by phase id."""
    return workflow_harnesses(repo / AGENTS_CONFIG, repo / WORKFLOW)


def harness_of_phase(harnesses: Mapping[str, str], phase: str) -> str | None:
    """The expected harness of a trace phase (``fix_2`` -> the ``fix`` step), or None."""
    if phase in harnesses:
        return harnesses[phase]
    return harnesses.get(re.sub(r"_\d+$", "", phase))
