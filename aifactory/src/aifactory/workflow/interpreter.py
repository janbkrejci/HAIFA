"""Run a loaded workflow over the engine's own primitives.

Role steps go through ``run.phase`` / ``ph.call`` with the step's harness, model
and thinking override applied for that one phase (``step_override``). Code steps
(``test``, ``command``, ``commit``, ``changes``, ``rebase``, ``rebuild``) go
through a ``CodeRunner``, which tests swap for a fake. ``rebase``
reads its target from the prompt variable ``rebase_onto`` (``factory task
resolve``). ``rebuild`` rebuilds the generated outputs
(``run_workflow(generated=...)``) that contain a file the latest ``rebase``
result reports as conflicted.
Every ``test`` step runs the checks of the latest test plan (a role step whose
output is ``TestPlanOutput``; the parser requires one before any ``test``) under
the shared time limit ``run.test_timeout`` (``run_workflow(test_timeout=...)``),
else 600 s. Role steps get ``{{baseline}}``, the commit the run started from, so
a tester can diff the whole change, and ``{{previous_test_plan}}``, the latest
test plan (``(none)`` before the first), which a new plan must keep or say why
it drops a check (gate ``plan_keeps_checks``).

A red ``test`` goes to the tester first (phase ``triage``, ``{{failed_test}}`` set):
``failure_cause: plan`` means the checks themselves were wrong (a bad path, an
unknown option, no tests collected); the corrected plan replaces the old one and
the test runs again, which is no repair round and never reaches the builder. At
most ``MAX_PLAN_REPAIRS`` corrections per run, then the run stops. ``code`` leaves
the red result for the builder.

Inputs of a role step: ``{{previous_envelope}}`` is the latest result of the
steps in ``input:`` (any step without it). An ``input:`` mapping adds further
``{{name}}`` variables, each the latest result of its own steps. Every role step
also gets ``{{test_result}}``: the latest ``test`` step (passed, command, log
path, and whether code changed after it) unless ``input:`` names it otherwise.

``repeat`` semantics: ``until`` is evaluated after every body step that ran and
ends the loop the moment it holds. In the last iteration the loop also ends
right after the body item that produces the result ``until`` reads
(``Repeat.until_tail``): with ``[test, fix]`` and ``until: test.passed`` a third
failing test is not followed by ``fix_3``, and with ``[review, revise]`` a last
rejection is not followed by ``revise_2``. This deliberately differs from
``adw_simple_sdlc.py``, which still runs a fix after the last failing test.

``phase_gate`` (``run_workflow(phase_gate=...)``) is called before every role and code
phase, outside of it: a task run passes ``run.pause.PauseGate``, which waits there while
the run is paused (``factory task pause``). A phase that started always runs to its end.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from aifactory import harness as harness_registry
from aifactory.engine import changes as engine_changes
from aifactory.engine import data_types as dt
from aifactory.engine import git_helper, session
from aifactory.engine import quality as engine_quality
from aifactory.engine.role_registry import RAN_FIELD, Issue
from aifactory.harness.override import effective_agent, step_override
from aifactory.workflow.check import check_agents
from aifactory.workflow.conditions import truthy
from aifactory.workflow.model import CodeStep, Repeat, RoleStep, Step, Workflow, WorkflowError, walk
from aifactory.workflow.rebase import rebase_onto
from aifactory.workflow.rebuild import Generated, rebuild_generated

__all__ = [
    "REQUEST_DESCRIPTION",
    "CodeRunner",
    "EngineCodeRunner",
    "StepRecord",
    "WorkflowRun",
    "preflight",
    "run_workflow",
    "unenforced_restrictions",
]

PhaseKind = Literal["engineer", "agent", "code"]
REQUEST_DESCRIPTION = "Capture the incoming ask and the workflow chosen to answer it"
TEST_RESULT_VARIABLE = "test_result"
BASELINE_VARIABLE = "baseline"
PREVIOUS_PLAN_VARIABLE = "previous_test_plan"
FAILED_TEST_VARIABLE = "failed_test"
TRIAGE_PHASE = "triage"
TRIAGE_DESCRIPTION = (
    "Decide whether the failed checks are wrong themselves or caught a fault in the code"
)
MAX_PLAN_REPAIRS = 2
NO_INPUT = "(none)"


class CodeRunner(Protocol):
    """The deterministic side of a run. Swapped for a fake in tests."""

    def test(self, run: Any, plan: Any) -> Any: ...  # TestPlanOutput -> QualityResult
    def commit(self, run: Any, message: str) -> str: ...
    def changes(self, run: Any, base: str) -> Any: ...  # -> ChangeSet
    def command(self, run: Any, step: CodeStep) -> Any: ...  # -> QualityResult
    def rebase(self, run: Any) -> Any: ...  # -> RebaseOutput
    def rebuild(self, run: Any, files: list[str]) -> Any: ...  # -> RebuildOutput
    def baseline(self) -> str: ...


class EngineCodeRunner:
    """Code steps through the vendored engine: quality, git_helper and changes."""

    def test(self, run: Any, plan: Any) -> Any:
        from aifactory.testing.executor import execute

        return execute(run, plan)

    def commit(self, run: Any, message: str) -> str:
        return str(git_helper.commit_all(message))

    def changes(self, run: Any, base: str) -> Any:
        return engine_changes.capture(run, dt.ChangeCapture(base=base))

    def command(self, run: Any, step: CodeStep) -> Any:
        """Run ``step.argv``; ``passed`` is exit code 0 (timeout: 124, missing binary: 127)."""
        spec = dt.QualityCheckSpec(
            name=step.key,
            area="backend",
            operation="build",
            argv=list(step.argv),
            timeout_seconds=step.timeout,
        )
        check = engine_quality._run(spec, run)
        failures = (
            []
            if check.passed
            else [
                f"{check.name}: `{check.command}` exited {check.returncode}\n"
                f"{check.output_tail}".rstrip()
            ]
        )
        return dt.QualityResult(
            passed=check.passed,
            checks=[check],
            failures=failures,
            artifacts=[check.output_artifact],
        )

    def rebase(self, run: Any) -> Any:
        """Rebase the run's checkout onto the prompt variable ``rebase_onto``."""
        onto = (getattr(run, "prompt_variables", None) or {}).get("rebase_onto")
        if not onto:
            raise RuntimeError(
                "the rebase step needs a target: run the resolve workflow through "
                "`factory task resolve`"
            )
        return rebase_onto(Path(run.repo_root), str(onto))

    def rebuild(self, run: Any, files: list[str]) -> Any:
        """Rebuild the run's generated outputs (``run.generated``) that contain one of `files`."""
        outputs: tuple[Generated, ...] = tuple(getattr(run, "generated", None) or ())

        def build(output: Generated) -> str | None:
            spec = dt.QualityCheckSpec(
                name="rebuild",
                area="frontend",
                operation="build",
                argv=list(output.argv),
                timeout_seconds=output.timeout,
            )
            check = engine_quality._run(spec, run)
            if check.passed:
                return None
            return f"`{check.command}` exited {check.returncode}\n{check.output_tail}".rstrip()

        return rebuild_generated(Path(run.repo_root), outputs, files, build)

    def baseline(self) -> str:
        return str(git_helper.rev("HEAD")) if git_helper.is_repo() else ""


@dataclass
class StepRecord:
    phase: str
    step: str
    kind: str
    owner: str
    harness: str | None = None
    model: str | None = None
    thinking: str | None = None


@dataclass
class WorkflowRun:
    exit_code: int
    accepted: bool
    adw_id: str
    records: list[StepRecord] = field(default_factory=list)
    envelopes: dict[str, Any] = field(default_factory=dict)
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    phases: list[tuple[str, str, str]] = field(default_factory=list)  # (name, kind, owner)
    warnings: list[str] = field(default_factory=list)
    history: list[tuple[str, Any]] = field(default_factory=list)  # (key, envelope), oldest first


def unenforced_restrictions(workflow: Workflow, cfg: dt.SSSFConfig) -> list[str]:
    """Agents whose ``disallowed_commands`` their (step's) harness cannot enforce."""
    roster = {agent.name: agent for agent in cfg.agents}
    problems: list[str] = []
    for step in walk(workflow.steps):
        if not isinstance(step, RoleStep) or step.role.agent not in roster:
            continue
        agent = effective_agent(roster[step.role.agent], step.override)
        problem = harness_registry.unenforced_disallowed(agent)
        if problem is not None and problem not in problems:
            problems.append(problem)
    return problems


def preflight(workflow: Workflow, cfg: dt.SSSFConfig) -> None:
    """Check every (agent, harness, model, thinking) the workflow will use, before anything runs."""
    agents = harness_registry.install()
    issues = check_agents(workflow, cfg)
    failed = {issue.path for issue in issues}
    roster = {agent.name: agent for agent in cfg.agents}
    seen: set[tuple[str, str | None, str | None, str | None]] = set()
    for step in walk(workflow.steps):
        if not isinstance(step, RoleStep) or step.path in failed:
            continue
        key = (step.role.agent, step.harness, step.model, step.thinking)
        if key in seen or step.role.agent not in roster:
            continue
        seen.add(key)
        probe = cfg.model_copy(deep=True)
        probe.agents = [
            effective_agent(a, step.override) if a.name == step.role.agent else a
            for a in probe.agents
        ]
        try:
            from aifactory.harness.settings import ensure_enabled

            effective = next(a for a in probe.agents if a.name == step.role.agent)
            ensure_enabled(str(effective.coding_agent))
            agents.validate(probe, [step.role.agent])
        except (SystemExit, ValueError) as error:
            issues.append(Issue("invalid_agent", str(error), step.path))
    if issues:
        raise WorkflowError(issues)


class _Interpreter:
    def __init__(
        self,
        workflow: Workflow,
        prompt: str,
        run: Any,
        code: CodeRunner,
        label: str | None = None,
        gate: Callable[[], None] | None = None,
    ) -> None:
        self.workflow = workflow
        self.gate = gate
        self.label = label
        self.prompt = prompt
        self.run = run
        self.code = code
        self.baseline = ""
        self.results: dict[str, dict[str, Any]] = {}
        self.envelopes: dict[str, Any] = {}
        self.history: list[tuple[str, Any]] = []  # (key, envelope), oldest first
        # history index -> what a test/command step ran (passed, command, log)
        self.reports: dict[int, dict[str, Any]] = {}
        self.test_keys = tuple(
            dict.fromkeys(
                leaf.key
                for leaf in walk(workflow.steps)
                if isinstance(leaf, CodeStep) and leaf.action == "test"
            )
        )
        self.records: list[StepRecord] = []
        self.used: set[str] = set()
        self.plan_step: RoleStep | None = None  # the latest test plan step, for triage
        self.failed_test = ""  # the red test a triage call judges
        self.red_test: dict[str, Any] | None = None
        self.plan_repairs = 0

    # -- helpers --

    def phase_name(self, base: str, suffix: tuple[int, ...]) -> str:
        name = base + "".join(f"_{i}" for i in suffix)
        if name in self.used:
            n = 2
            while f"{name}_{n}" in self.used:
                n += 1
            name = f"{name}_{n}"
        self.used.add(name)
        return name

    def params(
        self, name: str, kind: PhaseKind, owner: str, description: str, retries: int = 0
    ) -> dt.PhaseParams:
        return dt.PhaseParams(
            name=name, kind=kind, owner=owner, description=description, retries=retries
        )

    def store(self, key: str, envelope: Any) -> None:
        self.envelopes[key] = envelope
        self.history.append((key, envelope))
        self.results[key] = {**envelope.model_dump(), RAN_FIELD: True}

    def previous(self, inputs: tuple[str, ...]) -> Any:
        for key, envelope in reversed(self.history):
            if not inputs or key in inputs:
                return envelope
        return None

    def latest(self, keys: tuple[str, ...]) -> int | None:
        """History index of the latest result of one of ``keys``."""
        for index in range(len(self.history) - 1, -1, -1):
            if self.history[index][0] in keys:
                return index
        return None

    def render_input(self, keys: tuple[str, ...]) -> str:
        """The latest result of ``keys`` as a prompt variable; ``(none)`` before any ran.

        A test or command result reads as its report (passed, command,
        log); ``code_changed_since`` tells whether an agent changed code after it.
        """
        index = self.latest(keys)
        if index is None:
            return NO_INPUT
        if index in self.reports:
            report = dict(self.reports[index])
            report["code_changed_since"] = any(
                "changed_files" in type(envelope).model_fields
                for _, envelope in self.history[index + 1 :]
            )
            return json.dumps(report, indent=2)
        return str(self.history[index][1].model_dump_json(indent=2))

    def variables(self, step: RoleStep) -> dict[str, str]:
        """Extra prompt variables of a role step: ``test_result``, then its ``input:`` mapping."""
        variables = {
            TEST_RESULT_VARIABLE: self.render_input(self.test_keys),
            BASELINE_VARIABLE: self.baseline or NO_INPUT,
            PREVIOUS_PLAN_VARIABLE: self.latest_plan_json(),
            FAILED_TEST_VARIABLE: self.failed_test or NO_INPUT,
        }
        for name, keys in step.variables:
            variables[name] = self.render_input(keys)
        return variables

    def report(self, phase: str, key: str, result: Any) -> dict[str, Any]:
        """What a test-like step ran: passed, the command(s), the log path(s)."""
        checks = list(getattr(result, "checks", None) or [])
        commands = [str(check.command) for check in checks]
        logs = [str(check.output_artifact) for check in checks if check.output_artifact]
        logs += [str(a) for a in getattr(result, "artifacts", None) or [] if str(a) not in logs]
        return {
            "step": key,
            "phase": phase,
            "passed": bool(result.passed),
            "command": "; ".join(commands) or None,
            "log": logs[0] if len(logs) == 1 else (logs or None),
            "failures": len(getattr(result, "failures", None) or []),
            **({"test_plan": result.test_plan.model_dump()} if result.test_plan else {}),
        }

    def latest_plan(self) -> Any:
        """The latest tester result, or None before any test plan ran."""
        for _, envelope in reversed(self.history):
            if isinstance(envelope, dt.TestPlanOutput):
                return envelope
        return None

    def latest_plan_json(self) -> str:
        plan = self.latest_plan()
        if plan is None:
            return NO_INPUT
        return str(plan.model_dump_json(indent=2, include={"coverage", "reason", "checks"}))

    def test_plan(self) -> Any:
        """The latest tester result; the parser guarantees a test plan step precedes a test."""
        plan = self.latest_plan()
        if plan is None:
            raise RuntimeError("no test plan ran before this test step — nothing to run")
        return plan

    def commit_message(self) -> str:
        """The words of the latest agent whose work product is a commit (plan, build, docs)."""
        for _, envelope in reversed(self.history):
            if "commit_message" in type(envelope).model_fields:
                return str(envelope.commit_message) or self.fallback_message(envelope.summary)
        last = self.previous(())
        summary = last.summary if last is not None else self.workflow.name
        return self.fallback_message(str(summary))

    def fallback_message(self, summary: str) -> str:
        """``<label>: <summary>`` for a task run (the run id stays in the trace), else sssf's."""
        if self.label:
            return f"{self.label}: {summary}"
        return f"sssf({self.run.adw_id}): {summary}"

    # -- execution --

    def execute(self, steps: Sequence[Step], suffix: tuple[int, ...] = ()) -> None:
        for step in steps:
            self.dispatch(step, suffix)

    def dispatch(self, step: Step, suffix: tuple[int, ...]) -> bool:
        """Run one step unless its ``when`` is false; return whether it ran."""
        if not truthy(step.when, self.results):
            return False
        if isinstance(step, Repeat):
            self.loop(step, suffix)
        elif isinstance(step, RoleStep):
            self.role(step, suffix)
        else:
            self.code_step(step, suffix)
        return True

    def loop(self, step: Repeat, suffix: tuple[int, ...]) -> None:
        """Run the body up to ``max`` times; see the module docstring for ``until``."""
        for i in range(1, step.max + 1):
            last = i == step.max
            for index, inner in enumerate(step.steps):
                ran = self.dispatch(inner, (*suffix, i))
                # `until` is checked after every step of the body, which is what
                # makes test_1 -> fix_1 -> test_2 stop the moment test_2 is green.
                if ran and step.until is not None and truthy(step.until, self.results):
                    return
                # Last round: stop at the check itself. What follows it would repair
                # work that nothing verifies any more (no fix_3, no revise_2).
                if last and step.until_tail is not None and index == step.until_tail:
                    return

    def before_phase(self) -> None:
        """The phase boundary: wait here while the run is paused."""
        if self.gate is not None:
            self.gate()

    def role(self, step: RoleStep, suffix: tuple[int, ...], *, keep: bool = True) -> Any:
        """Run one agent phase; ``keep=False`` leaves its envelope out of the results."""
        self.before_phase()
        if step.role.output_type is dt.TestPlanOutput and step.phase_id != TRIAGE_PHASE:
            self.plan_step = step
        name = self.phase_name(step.phase_id, suffix)
        role = step.role
        previous = self.previous(step.inputs)
        self.run.previous_test_plan = self.latest_plan()  # for the plan_keeps_checks gate
        with step_override(self.run.cfg, role.agent, step.override) as agent:
            params = self.params(name, "agent", role.agent, step.description, role.retries)
            with self.run.phase(params) as ph:
                ph.log(harness=agent.coding_agent, model=agent.model, thinking=agent.thinking)
                self.records.append(
                    StepRecord(
                        name,
                        step.name,
                        "agent",
                        role.agent,
                        str(agent.coding_agent),
                        agent.model,
                        agent.thinking,
                    )
                )
                envelope = ph.call(
                    dt.AgentCall(
                        output_type=role.output_type,
                        prompt=self.prompt,
                        previous=previous,
                        gates=list(role.gates),
                        variables=self.variables(step),
                    )
                )
        if keep:
            self.store(step.key, envelope)
        return envelope

    def triage(self, step: CodeStep, suffix: tuple[int, ...], report: dict[str, Any]) -> bool:
        """Ask the tester whether a red ``test`` is the plan's fault; True after a plan repair.

        A corrected plan replaces the old one and the test runs again: not a repair
        round, nothing reaches the builder. After ``MAX_PLAN_REPAIRS`` corrected plans
        that still fail by their own fault the run stops.
        """
        if self.plan_step is None:
            return False
        check = dataclasses.replace(
            self.plan_step,
            phase_id=TRIAGE_PHASE,
            description=TRIAGE_DESCRIPTION,
            when=None,
            inputs=(),
            variables=(),
        )
        self.failed_test = json.dumps(report, indent=2)
        try:
            envelope = self.role(check, suffix, keep=False)
        finally:
            self.failed_test = ""
        if envelope.failure_cause != "plan":
            return False
        if self.plan_repairs >= MAX_PLAN_REPAIRS:
            raise RuntimeError(
                f"the test plan still cannot run after {MAX_PLAN_REPAIRS} corrections: "
                f"{envelope.reason}"
            )
        self.plan_repairs += 1
        self.store(self.plan_step.key, envelope)
        return True

    def code_step(self, step: CodeStep, suffix: tuple[int, ...]) -> None:
        self.run_code_step(step, suffix)
        while step.action == "test" and self.red_test is not None:
            report, self.red_test = self.red_test, None
            if not self.triage(step, suffix, report):
                break
            self.run_code_step(step, suffix)

    def run_code_step(self, step: CodeStep, suffix: tuple[int, ...]) -> None:
        self.before_phase()
        name = self.phase_name(step.phase_id, suffix)
        self.records.append(StepRecord(name, step.name, "code", step.owner))
        with self.run.phase(self.params(name, "code", step.owner, step.description)) as ph:
            if step.action in ("test", "command"):
                if step.action == "test":
                    result, what = self.code.test(self.run, self.test_plan()), "tests"
                else:
                    result, what = self.code.command(self.run, step), step.key
                passed = sum(1 for check in result.checks if check.passed)
                ph.log(
                    passed=result.passed,
                    test_plan=(result.test_plan.model_dump() if result.test_plan else None),
                    checks=f"{passed}/{len(result.checks)}",
                    artifacts=", ".join(result.artifacts),
                )
                report = self.report(name, step.key, result)
                self.reports[len(self.history)] = report
                self.store(step.key, engine_quality.as_envelope(result, what))
                if step.action == "test" and not result.passed:
                    self.red_test = report
            elif step.action == "commit":
                message = self.commit_message()
                # "" means the tree was already clean — a real outcome, not a failure.
                sha = self.code.commit(self.run, message)
                ph.log(sha=sha, message=message, committed=bool(sha))
                self.results[step.key] = {
                    "sha": sha,
                    "committed": bool(sha),
                    "message": message,
                    RAN_FIELD: True,
                }
            elif step.action == "changes":
                cs = self.code.changes(self.run, self.baseline or "HEAD")
                ph.log(
                    base=f"{cs.base.label} @ {cs.base.commit[:7]}",
                    reason=cs.base.reason,
                    files=len(cs.files) + len(cs.untracked),
                    lines=f"+{cs.insertions} -{cs.deletions}",
                    diff=cs.diff_path,
                )
                if cs.empty:
                    raise RuntimeError(
                        f"nothing changed since {cs.base.label} ({cs.base.reason}) — "
                        "there is nothing to document."
                    )
                self.store(step.key, engine_changes.as_envelope(cs))
            elif step.action == "rebase":
                rebased = self.code.rebase(self.run)
                ph.log(
                    onto=str(rebased.onto)[:7],
                    clean=rebased.clean,
                    conflict=rebased.conflict,
                    files=", ".join(rebased.files),
                )
                self.store(step.key, rebased)
            elif step.action == "rebuild":
                conflicted = (self.results.get("rebase") or {}).get("files") or []
                rebuilt = self.code.rebuild(self.run, [str(f) for f in conflicted])
                ph.log(
                    built=", ".join(rebuilt.built) or "nothing",
                    files=len(rebuilt.files),
                )
                self.store(step.key, rebuilt)
            else:  # pragma: no cover - the registry only admits CODE_ACTIONS
                raise RuntimeError(f"unknown code action {step.action!r}")


def run_workflow(
    workflow: Workflow,
    prompt: str,
    cfg: Any,
    *,
    code: CodeRunner | None = None,
    adw_id: str | None = None,
    repo_root: Path | None = None,
    write_guard: Any = None,
    prompt_variables: Mapping[str, str] | None = None,
    label: str | None = None,
    test_timeout: int | None = None,
    generated: Sequence[Generated] = (),
    test_slots: Any = None,
    phase_gate: Callable[[], None] | None = None,
) -> WorkflowRun:
    """Run a loaded workflow through the engine. Phase errors propagate, as in a Python ADW.

    A task run passes ``repo_root`` (its worktree, where agents are spawned),
    ``write_guard`` (checks every agent phase instead of ``permissions``),
    ``prompt_variables`` (extra ``{{...}}`` values for the agent prompts) and
    ``label`` (the task id, used in the fallback commit message),
    ``test_timeout`` (time limit in seconds of every ``test`` step; default 600) and
    ``generated`` (the outputs a ``rebuild`` step may rebuild; default none) and
    ``test_slots`` (an ``engine.slots.TestSlots`` every ``test`` step waits for; the wait
    does not count into ``test_timeout``; None means no wait) and
    ``phase_gate`` (called before every role and code phase; see the module docstring).
    """
    preflight(workflow, cfg)
    warnings = [*workflow.warnings, *unenforced_restrictions(workflow, cfg)]
    runner: CodeRunner = code if code is not None else EngineCodeRunner()
    run = session.ensure(cfg, adw_id)
    if repo_root is not None:
        run.repo_root = Path(repo_root).resolve()
    run.write_guard = write_guard
    run.prompt_variables = dict(prompt_variables or {})
    run.test_timeout = test_timeout
    run.generated = tuple(generated)
    run.test_slots = test_slots
    interp = _Interpreter(workflow, prompt, run, runner, label, phase_gate)
    interp.baseline = runner.baseline()  # pinned before this run commits anything
    run.console.note(f"workflow: {workflow.name}")
    request = interp.params("request", "engineer", run.engineer, REQUEST_DESCRIPTION)
    interp.used.add("request")
    with run.phase(request) as ph:
        ph.log(input=prompt, workflow=workflow.name, baseline=interp.baseline[:7])
        for warning in warnings:
            # The harness cannot forbid these commands: say so before any agent runs.
            ph.log(warning=warning)
    interp.execute(workflow.steps)
    accepted = truthy(workflow.accept, interp.results)
    reason = f"accept `{workflow.accept.source}` was not met" if workflow.accept else ""
    exit_code = int(run.finish(accepted=accepted, reason=reason))
    return WorkflowRun(
        exit_code=exit_code,
        accepted=accepted,
        adw_id=str(run.adw_id),
        records=interp.records,
        envelopes=interp.envelopes,
        results=interp.results,
        phases=[(p.params.name, p.params.kind, p.params.owner) for p in run.phases],
        warnings=warnings,
        history=list(interp.history),
    )
