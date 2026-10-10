"""Load and validate YAML workflows against the role registry.

Everything that can be checked without running is checked here, and every
problem is reported at once: unknown roles, harnesses, thinking levels,
condition syntax, references to steps and fields that do not exist, loops
without a bound, and descriptions that only restate a phase name. A role step
may pick another roster agent with `agent:`; it keeps the role's output type
and gates.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping, Sequence
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from aifactory import packagedata
from aifactory.engine.role_registry import (
    CodeStepDef,
    Issue,
    RoleDef,
    RoleRegistry,
    check_description,
    load_roles,
)
from aifactory.harness import ALIASES, HARNESSES, canonical
from aifactory.harness.override import THINKING_LEVELS
from aifactory.workflow.conditions import Condition, ConditionError, parse_condition, refs
from aifactory.workflow.model import (
    DEFAULT_COMMAND_TIMEOUT,
    CodeStep,
    Repeat,
    RoleStep,
    Step,
    Workflow,
    WorkflowError,
    walk,
)

__all__ = [
    "DEFAULT_WORKFLOWS_DIR",
    "HARNESS_NAMES",
    "load_workflow",
    "outline",
    "parse_workflow",
]

DEFAULT_WORKFLOWS_DIR = Path(str(resources.files("aifactory") / "defaults" / "workflows"))
"""The packaged workflows (one per ported Python ADW)."""

HARNESS_NAMES: tuple[str, ...] = (*HARNESSES, *ALIASES)
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PREVIOUS_VARIABLE = "previous_envelope"
# Prompt variables the engine fills itself; an `input:` mapping may not name them.
RESERVED_VARIABLES = frozenset({"prompt", "context_handoff_dir"})

_TOP_KEYS = frozenset({"name", "description", "steps", "accept"})
_ROLE_OPTS = frozenset(
    {"agent", "harness", "model", "thinking", "when", "id", "description", "input", "coverage"}
)
PLAN_COVERAGES = ("full", "scoped")
_CODE_OPTS = frozenset({"when", "id", "description"})
_COMMAND_OPTS = _CODE_OPTS | {"argv", "timeout"}
_OVERRIDES = ("harness", "model", "thinking")
_REPEAT_OPTS = frozenset({"max", "until", "when"})
TEST_PLAN_TYPE = "TestPlanOutput"
TEST_PLAN_STEP = "test_plan"


def _until_tail(until: Condition | None, steps: Sequence[Step]) -> int | None:
    """Index of the last body item that produces a result ``until`` reads, or None."""
    if until is None:
        return None
    keys = {ref.step for ref in refs(until.node)}
    tail: int | None = None
    for index, step in enumerate(steps):
        leaves = walk(step.steps) if isinstance(step, Repeat) else [step]
        produced = {leaf.key for leaf in leaves}
        if produced & keys:
            tail = index
    return tail


class _Parser:
    def __init__(self, roles: RoleRegistry) -> None:
        self.roles = roles
        self.issues: list[Issue] = []
        self.namespace: dict[str, frozenset[str]] = {}
        self.command_ids: dict[str, str] = {}
        self.conditions: list[tuple[Condition, str]] = []
        self.inputs: list[tuple[str, str]] = []

    def add(self, code: str, message: str, path: str) -> None:
        self.issues.append(Issue(code, message, path))

    def condition(self, value: object, path: str) -> Condition | None:
        if value is None:
            return None
        try:
            parsed = parse_condition(value)
        except ConditionError as error:
            self.add("bad_condition", f"{value!r}: {error}", path)
            return None
        self.conditions.append((parsed, path))
        return parsed

    def description(self, phase: str, value: object, default: str, path: str) -> str:
        text = default if value is None else value
        problem = check_description(phase, text)
        if problem:
            self.add("bad_description", problem, path)
            return default
        return " ".join(str(text).split())

    def phase_id(self, value: object, default: str, path: str) -> str:
        if value is None:
            return default
        if not isinstance(value, str) or not ID_RE.match(value):
            self.add("invalid_id", f"id {value!r} must match {ID_RE.pattern}", path)
            return default
        return value

    def steps(self, items: object, path: str) -> tuple[Step, ...]:
        if not isinstance(items, list):
            return ()
        parsed: list[Step] = []
        for i, item in enumerate(items):
            step = self.item(item, f"{path}[{i}]")
            if step is not None:
                parsed.append(step)
        return tuple(parsed)

    def item(self, item: object, path: str) -> Step | None:
        if isinstance(item, str):
            return self.leaf(item, {}, path)
        if not isinstance(item, Mapping) or not item:
            self.add(
                "invalid_step", "a step is a name, a {name: options} mapping or a repeat", path
            )
            return None
        if "repeat" in item:
            return self.repeat(item, path)
        if len(item) != 1:
            first = next(iter(item))
            for key in list(item)[1:]:
                self.add(
                    "unknown_key",
                    f"unexpected key {key!r} beside step {first!r} — options go inside the step",
                    f"{path}.{key}",
                )
        name, opts = next(iter(item.items()))
        if opts is None:
            opts = {}
        if not isinstance(opts, Mapping):
            self.add("invalid_step", f"options of step {name!r} must be a mapping", path)
            return None
        return self.leaf(str(name), opts, f"{path}.{name}")

    def repeat(self, item: Mapping[Any, Any], path: str) -> Repeat | None:
        for key in item:
            if key not in ("repeat", "steps"):
                self.add(
                    "unknown_key",
                    f"a repeat takes only `steps` beside it, not {key!r}",
                    f"{path}.{key}",
                )
        opts = item.get("repeat")
        rpath = f"{path}.repeat"
        if opts is None:
            opts = {}
        if not isinstance(opts, Mapping):
            self.add("invalid_step", "repeat options must be a mapping", rpath)
            opts = {}
        for key in opts:
            if key not in _REPEAT_OPTS:
                self.add("unknown_key", f"unknown repeat option {key!r}", f"{rpath}.{key}")
        max_ = opts.get("max")
        ok = True
        if max_ is None:
            self.add("missing_max", "repeat needs `max`, the bound on iterations", f"{rpath}.max")
            ok = False
        elif not isinstance(max_, int) or isinstance(max_, bool) or max_ < 1:
            self.add("invalid_max", f"max must be an integer >= 1, got {max_!r}", f"{rpath}.max")
            ok = False
        until = self.condition(opts.get("until"), f"{rpath}.until")
        when = self.condition(opts.get("when"), f"{rpath}.when")
        body = item.get("steps")
        if not isinstance(body, list) or not body:
            self.add("empty_repeat", "repeat needs a non-empty `steps` list", f"{path}.steps")
            return None
        steps = self.steps(body, f"{path}.steps")
        if not ok:
            return None
        assert isinstance(max_, int)
        return Repeat(
            max=max_,
            until=until,
            when=when,
            steps=steps,
            path=path,
            until_tail=_until_tail(until, steps),
        )

    def leaf(self, name: str, opts: Mapping[Any, Any], path: str) -> RoleStep | CodeStep | None:
        if self.roles.is_role(name):
            return self.role_step(name, self.roles.roles[name], opts, path)
        if self.roles.is_code(name):
            return self.code_step(name, self.roles.code_steps[name], opts, path)
        self.add(
            "unknown_step",
            f"unknown step {name!r} — known steps: {', '.join(self.roles.known_steps())}",
            path,
        )
        return None

    def override(self, key: str, value: object, path: str) -> str | None:
        if value is None:
            return None
        if key == "harness":
            try:
                if not isinstance(value, str):
                    raise ValueError(value)
                return canonical(value)  # aliases are stored under their canonical name
            except ValueError:
                self.add(
                    "unknown_harness",
                    f"unknown harness {value!r}, available: {', '.join(HARNESS_NAMES)}",
                    path,
                )
                return None
        elif key == "thinking":
            if value not in THINKING_LEVELS:
                self.add(
                    "invalid_thinking",
                    f"thinking {value!r} is not one of {', '.join(THINKING_LEVELS)}",
                    path,
                )
                return None
        elif not isinstance(value, str) or not value.strip():
            self.add("invalid_model", f"model must be a non-empty string, got {value!r}", path)
            return None
        return str(value).strip()

    def agent(self, value: object, path: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            self.add("invalid_agent", f"agent must be a non-empty roster name, got {value!r}", path)
            return None
        return value.strip()

    def step_names(self, value: object, path: str) -> tuple[str, ...] | None:
        """A step name or a list of them, registered for the reference check."""
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            self.add("invalid_input", "input must be a step name or a list of step names", path)
            return None
        self.inputs.extend((v, path) for v in value)
        return tuple(value)

    def step_inputs(
        self, raw: object, path: str
    ) -> tuple[tuple[str, ...], tuple[tuple[str, tuple[str, ...]], ...]]:
        """``input:`` as a list (``previous_envelope``) or a ``{variable: steps}`` mapping.

        In the mapping, ``previous_envelope`` keeps its meaning and every other
        name becomes its own ``{{name}}`` prompt variable holding the latest
        result of the listed steps.
        """
        if raw is None:
            return (), ()
        if not isinstance(raw, Mapping):
            names = self.step_names(raw, path)
            return (names or ()), ()
        inputs: tuple[str, ...] = ()
        variables: list[tuple[str, tuple[str, ...]]] = []
        for key, value in raw.items():
            vpath = f"{path}.{key}"
            if not isinstance(key, str) or not ID_RE.match(key):
                self.add(
                    "invalid_input", f"input variable {key!r} must match {ID_RE.pattern}", vpath
                )
                continue
            if key in RESERVED_VARIABLES:
                self.add(
                    "invalid_input",
                    f"input variable {key!r} is set by the engine and cannot be an input",
                    vpath,
                )
                continue
            names = self.step_names(value, vpath)
            if names is None:
                continue
            if key == PREVIOUS_VARIABLE:
                inputs = names
            else:
                variables.append((key, names))
        return inputs, tuple(variables)

    def role_step(
        self, name: str, role: RoleDef, opts: Mapping[Any, Any], path: str
    ) -> RoleStep | None:
        for key in opts:
            if key not in _ROLE_OPTS:
                self.add(
                    "unknown_key", f"unknown option {key!r} for role {name!r}", f"{path}.{key}"
                )
        values = {k: self.override(k, opts.get(k), f"{path}.{k}") for k in _OVERRIDES}
        agent = self.agent(opts.get("agent"), f"{path}.agent")
        if agent is not None:
            role = dataclasses.replace(role, agent=agent)
        phase = self.phase_id(opts.get("id"), name, f"{path}.id")
        description = self.description(
            phase, opts.get("description"), role.description, f"{path}.description"
        )
        when = self.condition(opts.get("when"), f"{path}.when")
        inputs, variables = self.step_inputs(opts.get("input"), f"{path}.input")
        self.namespace[name] = self.roles.result_fields(name)
        coverage = opts.get("coverage")
        if coverage is not None and role.output_type_name != TEST_PLAN_TYPE:
            self.add(
                "unknown_key",
                f"`coverage` is an option of test plan steps, not of {name!r}",
                f"{path}.coverage",
            )
            coverage = None
        elif coverage is not None and coverage not in PLAN_COVERAGES:
            self.add(
                "invalid_coverage",
                f"coverage {coverage!r} is not one of {', '.join(PLAN_COVERAGES)}",
                f"{path}.coverage",
            )
            coverage = None
        return RoleStep(
            name=name,
            role=role,
            phase_id=phase,
            description=description,
            path=path,
            harness=values["harness"],
            model=values["model"],
            thinking=values["thinking"],
            agent=agent,
            when=when,
            inputs=inputs,
            variables=variables,
            coverage=coverage,
        )

    def code_step(
        self, name: str, spec: CodeStepDef, opts: Mapping[Any, Any], path: str
    ) -> CodeStep | None:
        allowed = _COMMAND_OPTS if name == "command" else _CODE_OPTS
        for key in opts:
            if key in _OVERRIDES or key == "agent":
                self.add(
                    "override_on_code_step",
                    f"{name!r} is deterministic code — it has no {key} to set",
                    f"{path}.{key}",
                )
            elif key not in allowed:
                self.add(
                    "unknown_key", f"unknown option {key!r} for code step {name!r}", f"{path}.{key}"
                )
        ok = True
        key = name
        argv: tuple[str, ...] = ()
        timeout = DEFAULT_COMMAND_TIMEOUT
        if name == "command":
            raw_id = opts.get("id")
            if raw_id is None:
                self.add(
                    "missing_id", "a command needs an `id` to read its result by", f"{path}.id"
                )
                ok = False
            elif not isinstance(raw_id, str) or not ID_RE.match(raw_id):
                self.add("invalid_id", f"id {raw_id!r} must match {ID_RE.pattern}", f"{path}.id")
                ok = False
            elif self.roles.is_role(raw_id) or self.roles.is_code(raw_id):
                self.add(
                    "invalid_id", f"command id {raw_id!r} collides with a step name", f"{path}.id"
                )
                ok = False
            elif raw_id in self.command_ids:
                self.add(
                    "duplicate_id",
                    f"command id {raw_id!r} is already used at {self.command_ids[raw_id]}",
                    f"{path}.id",
                )
                ok = False
            else:
                key = raw_id
                self.command_ids[raw_id] = path
            raw_argv = opts.get("argv")
            if (
                not isinstance(raw_argv, list)
                or not raw_argv
                or not all(isinstance(a, str) and a for a in raw_argv)
            ):
                self.add(
                    "missing_argv",
                    "a command needs `argv`, a non-empty list of strings",
                    f"{path}.argv",
                )
                ok = False
            else:
                argv = tuple(raw_argv)
            raw_timeout = opts.get("timeout", DEFAULT_COMMAND_TIMEOUT)
            if not isinstance(raw_timeout, int) or isinstance(raw_timeout, bool) or raw_timeout < 1:
                self.add(
                    "invalid_timeout",
                    "timeout must be an integer >= 1 (seconds)",
                    f"{path}.timeout",
                )
            else:
                timeout = raw_timeout
        phase = self.phase_id(opts.get("id"), name, f"{path}.id") if ok else key
        description = self.description(
            phase, opts.get("description"), spec.description, f"{path}.description"
        )
        when = self.condition(opts.get("when"), f"{path}.when")
        if not ok:
            return None
        self.namespace[key] = self.roles.result_fields(name)
        return CodeStep(
            name=name,
            action=name,
            key=key,
            phase_id=phase,
            owner=spec.owner,
            description=description,
            path=path,
            argv=argv,
            timeout=timeout,
            when=when,
        )

    def check_refs(self) -> None:
        known = ", ".join(sorted(self.namespace)) or "none"
        for condition, path in self.conditions:
            for ref in refs(condition.node):
                if ref.step not in self.namespace:
                    self.add(
                        "unknown_ref",
                        f"`{condition.source}`: no step {ref.step!r} in this workflow "
                        f"(steps: {known})",
                        path,
                    )
                elif ref.field not in self.namespace[ref.step]:
                    fields = ", ".join(sorted(self.namespace[ref.step]))
                    self.add(
                        "unknown_field",
                        f"`{condition.source}`: {ref.step!r} has no field {ref.field!r} "
                        f"(fields: {fields})",
                        path,
                    )
        for name, path in self.inputs:
            if name not in self.namespace:
                self.add(
                    "unknown_ref",
                    f"input {name!r} is not a step in this workflow (steps: {known})",
                    path,
                )

    def legacy_plan(self, steps: tuple[Step, ...]) -> tuple[tuple[Step, ...], bool]:
        """An older workflow (no test plan step at all): a ``test_plan`` before its first test.

        Returns the steps and whether one was added. Workflows written before 3.0 ran
        a configured test command; they keep working with the tester's checks.
        """
        role = self.roles.roles.get(TEST_PLAN_STEP)
        if role is None or role.output_type_name != TEST_PLAN_TYPE:
            return steps, False
        if any(
            isinstance(s, RoleStep) and s.role.output_type_name == TEST_PLAN_TYPE
            for s in walk(steps)
        ):
            return steps, False

        def insert(items: tuple[Step, ...]) -> tuple[tuple[Step, ...], bool]:
            out: list[Step] = []
            for index, step in enumerate(items):
                if isinstance(step, Repeat):
                    body, done = insert(step.steps)
                    if done:
                        changed = dataclasses.replace(
                            step, steps=body, until_tail=_until_tail(step.until, body)
                        )
                        return (*out, changed, *items[index + 1 :]), True
                elif isinstance(step, CodeStep) and step.action == "test":
                    plan = RoleStep(
                        name=TEST_PLAN_STEP,
                        role=role,
                        phase_id=TEST_PLAN_STEP,
                        description=role.description,
                        path=step.path,
                    )
                    return (*out, plan, *items[index:]), True
                out.append(step)
            return tuple(out), False

        result, added = insert(steps)
        if added:
            self.namespace[TEST_PLAN_STEP] = self.roles.result_fields(TEST_PLAN_STEP)
        return result, added

    def check_test_plans(self, steps: Sequence[Step]) -> None:
        """Every ``test`` runs the latest test plan, so a test plan step must come first."""
        planned = False
        for step in walk(steps):
            if isinstance(step, RoleStep) and step.role.output_type_name == TEST_PLAN_TYPE:
                planned = True
            elif isinstance(step, CodeStep) and step.action == "test" and not planned:
                self.add(
                    "test_without_plan",
                    "a test step runs the checks of a test plan; put a `test_plan` step before it",
                    step.path,
                )

    def workflow(self, data: object, source: Path | None) -> Workflow | None:
        if not isinstance(data, Mapping):
            self.add("not_a_mapping", "a workflow must be a YAML mapping", "")
            return None
        for key in data:
            if key not in _TOP_KEYS:
                self.add("unknown_key", f"unknown top-level key {key!r}", str(key))
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            self.add("missing_name", "a workflow needs a non-empty `name`", "name")
            name = ""
        description = self.description(
            name or "workflow", data.get("description", ""), "", "description"
        )
        raw_steps = data.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            self.add("missing_steps", "a workflow needs a non-empty `steps` list", "steps")
        steps = self.steps(raw_steps, "steps")
        accept = self.condition(data.get("accept"), "accept")
        self.check_refs()
        steps, added = self.legacy_plan(steps)
        self.check_test_plans(steps)
        if self.issues:
            return None
        warnings = (
            (
                f"workflow {name.strip()!r} has no test_plan step: one was added before its "
                "first test (add test_plan steps to the YAML to plan the checks again after "
                "fixes and revisions)",
            )
            if added
            else ()
        )
        return Workflow(
            name=name.strip(),
            description=description,
            steps=steps,
            accept=accept,
            source=source,
            warnings=warnings,
        )


def parse_workflow(data: object, roles: RoleRegistry, source: Path | None = None) -> Workflow:
    """Build a workflow from parsed YAML; raise ``WorkflowError`` with every problem."""
    parser = _Parser(roles)
    workflow = parser.workflow(data, source)
    if workflow is None:
        raise WorkflowError(parser.issues)
    return workflow


def load_workflow(path: Path, roles: RoleRegistry | None = None) -> Workflow:
    """Read and validate a workflow file. Nothing runs; every problem is raised at once."""
    try:
        text = packagedata.read_text(path)
    except OSError as error:
        raise WorkflowError([Issue("missing_file", str(error), "")]) from error
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise WorkflowError([Issue("invalid_yaml", str(error), "")]) from error
    return parse_workflow(data, roles if roles is not None else load_roles(), path)


def outline(steps: Sequence[Step]) -> list[dict[str, Any]]:
    """A flat description of every step, for the CLI and the future editor."""
    rows: list[dict[str, Any]] = []
    for step in steps:
        row: dict[str, Any]
        if isinstance(step, Repeat):
            row = {
                "path": step.path,
                "kind": "repeat",
                "max": step.max,
                "until": step.until.source if step.until else None,
                "when": step.when.source if step.when else None,
            }
            rows.append({k: v for k, v in row.items() if v is not None})
            rows.extend(outline(step.steps))
            continue
        if isinstance(step, RoleStep):
            row = {
                "path": step.path,
                "step": step.name,
                "kind": "agent",
                "phase": step.phase_id,
                "agent": step.role.agent,
                "owner": step.role.agent,
                "harness": step.harness,
                "model": step.model,
                "thinking": step.thinking,
                "when": step.when.source if step.when else None,
            }
        else:
            row = {
                "path": step.path,
                "step": step.name,
                "kind": "code",
                "phase": step.phase_id,
                "owner": step.owner,
                "when": step.when.source if step.when else None,
            }
        rows.append({k: v for k, v in row.items() if v is not None})
    return rows
