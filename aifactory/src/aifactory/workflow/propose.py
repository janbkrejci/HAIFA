"""``factory backlog propose``: a read-only agent turns an intent into a backlog proposal.

The agent ``proposer`` (library seed; its prompts are overridden in
``.factory/prompts/proposer/``) works like workflow advice (``workflow.adaptive``): in an
isolated clone checked out at the base commit, with no writes. It returns a typed
``BacklogProposalOutput``: a new step of the project ``--project`` with its tasks, or new
tasks of the existing step ``--step``. Without either (``Target()``, automatic placement)
the agent also chooses where the tasks go: an existing step, a new step of an existing
project, or a new project with a new step; ``resolve`` turns its answer into the placement.
The proposal is validated against the backlog of the working tree like ``factory task add``
(``backlog.add_batch``) plus the workflow catalog and the blocking rules of ``propose_check``
(``Hotovo znamená``, no dependency cycle). An invalid proposal goes back to the agent once (a
gate correction in the same session); a second invalid one fails with ``proposal_invalid``
and nothing is written. The other findings of ``propose_check`` (writes) go back to the
agent in the same single correction; those left after it are returned in ``findings`` and
shown in the preview. Only ``apply=True`` writes, and never commits.

The dashboard (``web.intent``) keeps a proposal open: ``run_proposer`` with a ``workdir``
keeps the isolated clone (the agent's conversation is bound to its directory) and a
``Refinement`` continues the same agent session with the person's note and the proposal as
they edited it (``edited``: tasks removed, titles and bodies changed).
"""

from __future__ import annotations

import json
import secrets
import subprocess
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aifactory import backlog as core
from aifactory import yamlload
from aifactory.backlog import Issue, NewTask, TaskEditError
from aifactory.backlog.derived import harness_values
from aifactory.config import load_run_config
from aifactory.engine import agents
from aifactory.engine.data_types import AgentCall, EnvelopeBase, PhaseParams
from aifactory.engine.runner import Run
from aifactory.engine.tracer import Tracer
from aifactory.failure import AgentReportedFail, InvalidOutput
from aifactory.harness import canonical, install
from aifactory.harness.check import check_harness
from aifactory.harness.settings import context_binding, ensure_enabled
from aifactory.providers.git import PARALLEL_CHECKOUT
from aifactory.run.errors import TaskRunError
from aifactory.run.guard import TaskWriteGuard
from aifactory.run.scope import TaskScope
from aifactory.run.task import _main_ignored, apply_agents_override, prepare_cfg
from aifactory.workflow import DEFAULT_WORKFLOWS_DIR, propose_check
from aifactory.workflow.adaptive import advice_dir
from aifactory.workflow.propose_check import DONE_HEADING, Candidate, Finding

install()

PROPOSER_AGENT = "proposer"
# One correction: the agent gets an invalid proposal back once.
CORRECTIONS = 1
_BODY_LIMIT = 4000
_CONTEXT_LIMIT = 120_000


class ProposedStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=40, description="short code, e.g. S03")
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=20_000, description="goal of the step")


class ProposedProject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=40, description="short code, e.g. P02")
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=20_000, description="goal of the project")


class ProposedTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=40, description="short code, e.g. T01")
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(
        min_length=1,
        max_length=40_000,
        description=f"the assignment, ending with a section '{DONE_HEADING}:'",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="full ids of existing tasks, or codes/ids of tasks of this proposal",
    )
    writes: list[str] = Field(default_factory=list, description="paths the task may change")
    workflow: str = Field(min_length=1, description="a workflow from the catalog")


class BacklogProposalOutput(EnvelopeBase):
    model_config = ConfigDict(extra="forbid")
    step: ProposedStep | None = Field(
        default=None,
        description="the new step (target is a project, or auto placement in a new step); "
        "null for an existing step",
    )
    tasks: list[ProposedTask] = Field(min_length=1, max_length=50)
    project: ProposedProject | None = Field(
        default=None,
        description="auto placement only: the new project of the new step; null otherwise",
    )
    existing_project: str | None = Field(
        default=None,
        description="auto placement only: id of the existing project of the new step",
    )
    existing_step: str | None = Field(
        default=None,
        description="auto placement only: id of the existing step the tasks go to",
    )
    placement_reason: str = Field(
        default="",
        max_length=1000,
        description="auto placement only: one sentence why the tasks go there",
    )


@dataclass
class Target:
    """Where the proposal goes: a new step of ``project``, the existing ``step``, or, with
    neither, wherever the agent places it (``auto``)."""

    project: str | None = None
    step: str | None = None

    @property
    def auto(self) -> bool:
        return self.project is None and self.step is None


@dataclass(frozen=True)
class Placement:
    """The real place of a proposal: the existing ``step``, or a new step ``new_step`` of the
    existing ``project`` or of the new project ``new_project``."""

    step: str | None = None
    project: str | None = None
    new_step: ProposedStep | None = None
    new_project: ProposedProject | None = None

    @property
    def project_id(self) -> str | None:
        if self.project is not None:
            return self.project
        if self.new_project is not None:
            return self.new_project.code.strip()
        return None

    @property
    def step_id(self) -> str | None:
        if self.step is not None:
            return self.step
        if self.new_step is None:
            return None
        code = self.new_step.code.strip()
        project = self.project_id
        if project and code.startswith(f"{project}-"):
            return code
        return f"{project}-{code}" if project else code


def resolve(proposal: BacklogProposalOutput, target: Target) -> Placement:
    """Where ``proposal`` goes: the target of ``--project``/``--step``, or the agent's choice
    in automatic placement. An inconsistent choice resolves as far as it can; ``plan``
    reports it."""
    if target.step is not None:
        return Placement(step=target.step)
    if target.project is not None:
        return Placement(project=target.project, new_step=proposal.step)
    if proposal.existing_step is not None:
        return Placement(step=proposal.existing_step.strip())
    if proposal.existing_project is not None:
        return Placement(project=proposal.existing_project.strip(), new_step=proposal.step)
    return Placement(new_step=proposal.step, new_project=proposal.project)


def workflow_catalog(repo: Path) -> dict[str, dict[str, Any]]:
    """Every workflow a task can name: the package defaults, the library and the repo's."""
    catalog: dict[str, dict[str, Any]] = {
        p.stem: yamlload.safe_load(p.read_text(encoding="utf-8"))
        for p in DEFAULT_WORKFLOWS_DIR.glob("*.yaml")
    }
    catalog.update(load_run_config(repo).config.workflows)
    return catalog


def _check_target(backlog: core.Backlog, target: Target) -> None:
    if target.project is not None and target.step is not None:
        raise TaskEditError("conflicting_options", "give either --project or --step, not both")
    if target.auto:
        return
    levels = backlog.settings.levels
    if target.step is not None:
        node = backlog.by_id.get(target.step)
        if not isinstance(node, core.Container) or node.level != levels[-2]:
            raise TaskEditError("unknown_step", f"unknown {levels[-2]} '{target.step}'")
    else:
        node = backlog.by_id.get(target.project or "")
        if not isinstance(node, core.Container) or levels.index(node.level) != len(levels) - 3:
            raise TaskEditError(
                "unknown_container", f"no container of {levels[-2]}s '{target.project}'"
            )


def _is_step(backlog: core.Backlog, node_id: str) -> bool:
    node = backlog.by_id.get(node_id)
    return isinstance(node, core.Container) and node.level == backlog.settings.levels[-2]


def _is_project(backlog: core.Backlog, node_id: str) -> bool:
    levels = backlog.settings.levels
    node = backlog.by_id.get(node_id)
    return isinstance(node, core.Container) and levels.index(node.level) == len(levels) - 3


def placement_problems(
    backlog: core.Backlog, proposal: BacklogProposalOutput, target: Target
) -> list[Issue]:
    """What is wrong with the placement fields of ``proposal`` for ``target``."""
    if not target.auto:
        given = [
            name
            for name in ("project", "existing_project", "existing_step")
            if getattr(proposal, name) is not None
        ]
        return [
            Issue("invalid_value", f"{name} must be null with --project or --step", "")
            for name in given
        ]
    levels = backlog.settings.levels
    problems: list[Issue] = []

    def bad(code: str, message: str, node_id: str | None = None) -> None:
        problems.append(Issue(code, message, "", node_id))

    if (proposal.existing_step is None) == (proposal.step is None):
        bad("invalid_value", "give exactly one of existing_step and step")
        return problems
    if proposal.existing_step is not None:
        step = proposal.existing_step.strip()
        if not _is_step(backlog, step):
            bad("unknown_step", f"unknown {levels[-2]} '{step}'", step)
        if proposal.project is not None or proposal.existing_project is not None:
            bad("invalid_value", "project and existing_project must be null with existing_step")
        return problems
    if len(levels) < 3:
        bad(
            "invalid_value",
            f"this backlog has no {levels[0]} level above its {levels[-2]}s "
            f"(levels {', '.join(levels)}); choose an existing_step",
        )
        return problems
    if (proposal.existing_project is None) == (proposal.project is None):
        bad("invalid_value", "a new step needs exactly one of existing_project and project")
        return problems
    if proposal.existing_project is not None:
        project = proposal.existing_project.strip()
        if not _is_project(backlog, project):
            bad("unknown_container", f"no container of {levels[-2]}s '{project}'", project)
    elif len(levels) != 3:
        bad(
            "invalid_value",
            f"a new {levels[0]} needs the levels project, step, task "
            f"(this backlog has {', '.join(levels)}); choose an existing_project",
        )
    return problems


def _clip(text: str) -> str:
    return text if len(text) <= _BODY_LIMIT else text[:_BODY_LIMIT] + "\n[truncated]"


def context(repo: Path, intent: str, target: Target) -> dict[str, Any]:
    """What the agent gets: the intent, the target, the backlog and the workflow catalog."""
    if not intent.strip():
        raise TaskEditError("invalid_value", "the intent must not be empty")
    backlog = core.load_for_edit(repo)
    _check_target(backlog, target)
    tasks = [
        {
            "id": t.id,
            "title": t.title,
            "status": core.derived_state(backlog, t),
            "step": t.parent.id,
            "depends_on": t.depends_on,
        }
        for t in core.iter_tasks(backlog)
    ]
    containers = [
        {"id": c.id, "title": c.title, "level": c.level, "path": c.path}
        for c in core.iter_containers(backlog.containers)
    ]
    catalog = {
        name: {"description": (data or {}).get("description", "")}
        for name, data in sorted(workflow_catalog(repo).items())
    }
    payload: dict[str, Any] = {
        "intent": intent.strip(),
        "target": {"kind": "auto"},
        "target_container": None,
        "levels": backlog.settings.levels,
        "containers": containers,
        "tasks": tasks,
        "workflows": catalog,
        "output_schema": BacklogProposalOutput.model_json_schema(),
    }

    def size() -> int:
        return len(json.dumps(payload, ensure_ascii=False).encode())

    if target.auto:
        payload["containers"] = [
            {**item, "body": _clip(c.body)}
            for item, c in zip(containers, core.iter_containers(backlog.containers), strict=True)
        ]
        if size() > _CONTEXT_LIMIT:
            payload["containers"] = containers
            payload["context_notes"] = [
                "project and step bodies omitted; read their index.md files"
            ]
        return payload
    focus = backlog.by_id[target.step or target.project or ""]
    assert isinstance(focus, core.Container)
    focus_tasks = [
        {"id": t.id, "title": t.title, "path": t.path, "body": _clip(t.body)}
        for c in [focus, *core.iter_containers(focus.children)]
        for t in c.tasks
    ]
    payload["target"] = (
        {"kind": "existing_step", "step": focus.id}
        if target.step
        else {"kind": "new_step", "project": focus.id}
    )
    payload["target_container"] = {
        "id": focus.id,
        "title": focus.title,
        "path": focus.path,
        "body": _clip(focus.body),
        "defaults": focus.defaults,
        "tasks": focus_tasks,
    }
    if size() > _CONTEXT_LIMIT:
        payload["target_container"]["tasks"] = [
            {k: v for k, v in t.items() if k != "body"} for t in focus_tasks
        ]
        payload["context_notes"] = ["task bodies omitted; read the task files"]
    return payload


def _batch(proposal: BacklogProposalOutput) -> list[NewTask]:
    return [
        NewTask(
            code=t.code,
            title=t.title,
            body=t.body,
            workflow=t.workflow,
            writes=list(t.writes),
            depends_on=list(t.depends_on),
        )
        for t in proposal.tasks
    ]


def plan(
    repo: Path,
    proposal: BacklogProposalOutput,
    target: Target,
    catalog: dict[str, Any],
    *,
    write: bool = False,
) -> core.BatchResult:
    """Validate ``proposal`` against the backlog and the catalog; write it with ``write``.

    Raises ``TaskEditError`` ``backlog_invalid`` with every problem in ``issues``.
    """
    problems = placement_problems(core.load_for_edit(repo), proposal, target)
    # an automatic placement that does not resolve leaves add_batch nothing to check
    unplaced = target.auto and bool(problems)
    if target.auto and not proposal.placement_reason.strip():
        problems.append(
            Issue(
                "invalid_value", "placement_reason must say in one sentence why it goes there", ""
            )
        )
    if target.step is not None and proposal.step is not None:
        problems.append(Issue("invalid_value", "step must be null for an existing step", ""))
    if target.project is not None and proposal.step is None:
        problems.append(Issue("invalid_value", "a new step needs 'step'", ""))
    for task in proposal.tasks:
        if task.workflow not in catalog:
            problems.append(
                Issue(
                    "unknown_workflow",
                    f"task '{task.code}': unknown workflow '{task.workflow}', "
                    f"choose one of {', '.join(sorted(catalog))}",
                    "",
                    task.code,
                )
            )
    blocking = [f for f in review(repo, proposal, target) if f.blocking]
    problems.extend(Issue(f.rule, f.message, "", f.task) for f in blocking)
    cycles = any(f.rule == propose_check.CYCLE for f in blocking)
    place = resolve(proposal, target)
    step = place.new_step
    new_project = place.new_project
    result: core.BatchResult | None = None
    try:
        if not unplaced:
            result = core.add_batch(
                repo,
                _batch(proposal),
                step=place.step,
                project=place.project,
                step_code=step.code if step else None,
                step_title=step.title if step else None,
                step_body=step.body if step else "",
                project_code=new_project.code if new_project else None,
                project_title=new_project.title if new_project else None,
                project_body=new_project.body if new_project else "",
                write=write and not problems,
            )
    except TaskEditError as exc:
        issues = exc.issues or [Issue(exc.code, exc.message, exc.path or "", exc.id)]
        # a cycle among the proposed tasks is already reported by the check
        problems.extend(i for i in issues if not (cycles and i.code == propose_check.CYCLE))
        result = None
    if problems or result is None:
        raise TaskEditError(
            "backlog_invalid",
            f"proposal rejected: {len(problems)} problem(s)",
            exit_code=1,
            issues=problems,
        )
    return result


def _step_id(proposal: BacklogProposalOutput, target: Target) -> str | None:
    return resolve(proposal, target).step_id


def candidates(proposal: BacklogProposalOutput, target: Target) -> list[Candidate]:
    """The proposed tasks for ``propose_check``: dependencies on tasks of the proposal (by
    code or full id) by their code, the rest as given."""
    step_id = _step_id(proposal, target)
    codes = {t.code.strip() for t in proposal.tasks}
    aliases = {code: code for code in codes}
    if step_id:
        aliases.update({f"{step_id}-{code}": code for code in codes})

    def ref(dep: str) -> str:
        return aliases.get(dep.strip(), dep.strip())

    return [
        Candidate(
            key=t.code.strip(),
            body=t.body,
            writes=tuple(w for w in t.writes if w.strip()),
            depends_on=tuple(ref(d) for d in t.depends_on),
        )
        for t in proposal.tasks
    ]


def closed_paths(repo: Path) -> list[str]:
    """What no run may change: ``protected_files`` (config and roster) and the backlog."""
    config = load_run_config(repo).config
    settings = config.settings
    paths = [
        *config.agents.defaults.protected_files,
        *settings.protected_files,
        *settings.backlog_patterns,
    ]
    return list(dict.fromkeys(paths))


def review(repo: Path, proposal: BacklogProposalOutput, target: Target) -> list[Finding]:
    """Every finding of ``propose_check`` on the proposal, blocking ones first."""
    return propose_check.check(candidates(proposal, target), repo, closed_paths(repo))


def _message(issue: Issue) -> str:
    where = f" ({issue.path})" if issue.path else ""
    return f"{issue.code}: {issue.message}{where}"


@dataclass
class Refinement:
    """A note of the person on ``proposal`` (the proposal as they have it now)."""

    note: str
    proposal: BacklogProposalOutput


def refinement_prompt(intent: str, target: Target, refinement: Refinement) -> str:
    """The continuation turn: the note and the current proposal, in the same session."""
    if not refinement.note.strip():
        raise TaskEditError("invalid_value", "the note must not be empty")
    if target.auto:
        where: dict[str, Any] = {"kind": "auto"}
        placement = [
            "",
            "The placement is yours (automatic placement). If the note asks for another "
            "place (e.g. 'put it into HAIFA-S03' or 'make it a new project'), change "
            "existing_step, step, existing_project and project accordingly and update "
            "placement_reason; otherwise keep the placement.",
        ]
    else:
        where = (
            {"kind": "existing_step", "step": target.step}
            if target.step
            else {"kind": "new_step", "project": target.project}
        )
        placement = []
    current = refinement.proposal.model_dump(mode="json")
    return "\n".join(
        [
            "## Continuation",
            "",
            "The person reviewed your proposal and asks for a change. The context of the "
            "first message (backlog, workflow catalog, output_schema) still applies.",
            "",
            f"Intent: {intent.strip()}",
            f"Target: {json.dumps(where)}",
            *placement,
            "",
            "Their note:",
            "",
            refinement.note.strip(),
            "",
            "The proposal as they have it now. They may have removed tasks or edited titles "
            "and bodies; keep their edits unless the note asks otherwise:",
            "",
            json.dumps(current, ensure_ascii=False, indent=2),
            "",
            "Answer with the whole revised proposal: ONLY the JSON object matching "
            "BacklogProposalOutput.",
        ]
    )


def edited(
    proposal: BacklogProposalOutput, target: Target, tasks: Sequence[dict[str, Any]]
) -> BacklogProposalOutput:
    """``proposal`` with only the tasks in ``tasks`` (by ``code``, in their order) and their
    edited ``title`` and ``body``. Dependencies on a removed task of the proposal go too."""
    by_code = {t.code.strip(): t for t in proposal.tasks}
    kept: list[ProposedTask] = []
    for item in tasks:
        code = item.get("code") if isinstance(item, dict) else None
        if not isinstance(code, str) or code.strip() not in by_code:
            raise TaskEditError("invalid_value", f"unknown task code {code!r} of the proposal")
        changes = {k: item[k] for k in ("title", "body") if isinstance(item.get(k), str)}
        kept.append(by_code[code.strip()].model_copy(update=changes))
    if not kept:
        raise TaskEditError("invalid_value", "the proposal needs at least one task")
    removed = set(by_code) - {t.code.strip() for t in kept}
    step_id = _step_id(proposal, target)
    gone = removed | ({f"{step_id}-{code}" for code in removed} if step_id else set())
    data = proposal.model_dump()
    data["tasks"] = [
        {**t.model_dump(), "depends_on": [d for d in t.depends_on if d.strip() not in gone]}
        for t in kept
    ]
    return BacklogProposalOutput.model_validate(data)


@contextmanager
def _isolated(repo: Path, commit: str, workdir: Path | None) -> Iterator[Path]:
    """The clone the agent works in: temporary, or kept in ``workdir`` between turns."""

    def clone(isolated: Path) -> None:
        # --shared borrows the objects; the clone lives only for this proposal.
        subprocess.run(
            ["git", "clone", "--quiet", "--no-checkout", "--shared", str(repo), str(isolated)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(isolated),
                *PARALLEL_CHECKOUT,
                "checkout",
                "--quiet",
                "--detach",
                commit,
            ],
            check=True,
            capture_output=True,
        )

    if workdir is not None:
        isolated = workdir / "repo"
        if not (isolated / ".git").exists():
            clone(isolated)
        yield isolated
        return
    with advice_dir() as tmp:
        isolated = tmp / "repo"
        clone(isolated)
        yield isolated


def propose(
    repo: Path, intent: str, target: Target, *, apply: bool = False, job_id: str | None = None
) -> dict[str, Any]:
    """Run the proposer, validate (one correction), and return the proposal as JSON data."""
    proposal, result, remaining = run_proposer(repo, intent, target, apply=apply, job_id=job_id)
    return to_json(proposal, result, target, remaining)


def run_proposer(
    repo: Path,
    intent: str,
    target: Target,
    *,
    apply: bool = False,
    job_id: str | None = None,
    workdir: Path | None = None,
    refinement: Refinement | None = None,
    on_agent: Callable[[dict[str, str]], None] | None = None,
) -> tuple[BacklogProposalOutput, core.BatchResult, list[Finding]]:
    """One turn of the proposer: the first proposal, or a ``refinement`` of it in the same
    session (``job_id`` and ``workdir`` of the first turn)."""
    payload = context(repo, intent, target)
    prompt = (
        refinement_prompt(intent, target, refinement)
        if refinement is not None
        else json.dumps(payload, ensure_ascii=False, indent=2)
    )
    catalog = workflow_catalog(repo)
    job_id = job_id or f"propose-{secrets.token_hex(4)}"
    rc = load_run_config(repo)
    runtime = repo / ".factory/data/backlog-propose" / job_id
    snapshot = runtime / "agent.json"
    try:
        if refinement is not None and snapshot.exists():
            binding = json.loads(snapshot.read_text(encoding="utf-8"))
        else:
            backlog = core.load_for_edit(repo)
            node = backlog.by_id.get(target.step or target.project or "")
            binding = context_binding(harness_values(node) if node is not None else {})
        rc = apply_agents_override(rc, binding)
    except ValueError as exc:
        raise TaskEditError("agent_unavailable", str(exc)) from exc
    except TaskRunError as exc:
        raise TaskEditError(exc.code, exc.message) from exc
    with _isolated(repo, rc.commit, workdir) as isolated:
        runtime.mkdir(parents=True, exist_ok=True)
        cfg = prepare_cfg(repo, rc, runtime / "prompts")
        if not any(a.name == PROPOSER_AGENT for a in cfg.agents):
            raise TaskEditError(
                "agent_unavailable",
                f"agent '{PROPOSER_AGENT}' is missing from the roster and the library; "
                "run 'factory library seed' to take it from the seed",
            )
        agent = agents.resolve(cfg, PROPOSER_AGENT)
        try:
            ensure_enabled(agent.coding_agent)
        except ValueError as exc:
            raise TaskEditError("agent_unavailable", str(exc)) from exc
        status = check_harness(canonical(agent.coding_agent))
        if not status.ok:
            raise TaskEditError(
                "agent_unavailable",
                f"proposer harness unavailable: {status.name}: {status.error}",
            )
        selection = {
            "harness": canonical(agent.coding_agent),
            "model": agent.model,
            "thinking": agent.thinking,
        }
        snapshot.write_text(json.dumps(selection), encoding="utf-8")
        if on_agent is not None:
            on_agent(dict(selection))
        agent.writes = []
        agents.validate(cfg, [agent.name])
        cfg.defaults.data_dir = str(runtime)
        cfg.observability.db = str(runtime / "trace.db")
        tracer = Tracer(cfg.observability.db, runtime / "events.jsonl")
        accepted: list[core.BatchResult] = []
        last: list[Issue] = []
        remaining: list[Finding] = []
        attempts = [0]

        def proposal_valid(envelope: EnvelopeBase, run: Any) -> list[str]:
            if envelope.status != "success":
                return []
            assert isinstance(envelope, BacklogProposalOutput)
            attempts[0] += 1
            try:
                result = plan(repo, envelope, target, catalog)
            except TaskEditError as exc:
                last[:] = exc.issues
                return [_message(i) for i in exc.issues]
            findings = [f for f in review(repo, envelope, target) if not f.blocking]
            if findings and attempts[0] <= CORRECTIONS:
                # the one correction also covers the quality findings
                return [f"{f.rule}: {f.message}" for f in findings]
            accepted[:] = [result]
            remaining[:] = findings
            return []

        ok = False
        try:
            tracer.session_start(job_id, "backlog-propose")
            run = Run(cfg, job_id, tracer, "backlog-propose")
            run.repo_root = isolated
            run.agent_environment = {
                "HAIFA_RUN_ID": job_id,
                "CLAUDE_SAFE_MODE": "1",
                "CODEX_SAFE_MODE": "1",
                "PI_SAFE_MODE": "1",
            }
            run.write_guard = TaskWriteGuard(
                repo,
                isolated,
                TaskScope(job_id, (), ()),
                (*_main_ignored(repo, rc.config.settings.worktrees_dir, cfg), ".factory/data/"),
            )
            try:
                with run.phase(
                    PhaseParams(
                        name="backlog-propose",
                        kind="agent",
                        owner=agent.name,
                        description="Propose a backlog step and tasks from the intent",
                        retries=CORRECTIONS,
                    )
                ) as ph:
                    envelope = ph.call(
                        AgentCall(
                            prompt=prompt,
                            output_type=BacklogProposalOutput,
                            gates=[proposal_valid],
                        )
                    )
            except AgentReportedFail as exc:
                raise TaskEditError(
                    "proposal_failed", f"the proposer gave up: {exc}", exit_code=1
                ) from exc
            except InvalidOutput as exc:
                raise TaskEditError(
                    "proposal_invalid",
                    "the proposal is invalid even after one correction; nothing was written",
                    exit_code=1,
                    issues=last,
                ) from exc
            proposal = BacklogProposalOutput.model_validate(envelope.model_dump())
            result = plan(repo, proposal, target, catalog, write=True) if apply else accepted[0]
            ok = True
            return proposal, result, list(remaining)
        finally:
            try:
                tracer.session_finish(job_id, ok=ok)
            finally:
                tracer.conn.close()


def to_json(
    proposal: BacklogProposalOutput,
    result: core.BatchResult,
    target: Target,
    findings: list[Finding] | None = None,
) -> dict[str, Any]:
    step_id = _step_id(proposal, target)

    def task_id(code: str) -> str:
        return f"{step_id}-{code}" if step_id else code

    project = (
        {
            "id": result.project_id,
            "title": result.project_title,
            "body": result.project_body,
            "path": result.project_path,
            "new": result.new_project,
        }
        if result.project_id
        else None
    )
    return {
        "summary": proposal.summary,
        "applied": result.written,
        "project": project,
        "placement_reason": proposal.placement_reason.strip(),
        "target": {"project": result.project_id or None, "step": result.step_id},
        "step": {
            "id": result.step_id,
            "title": result.step_title,
            "body": result.step_body,
            "path": result.step_path,
            "new": result.new_step,
        },
        "tasks": [
            {
                "id": t.id,
                "code": t.id[len(step_id) + 1 :] if step_id else t.id,
                "title": t.title,
                "body": t.body,
                "workflow": t.workflow,
                "writes": t.writes or [],
                "depends_on": t.depends_on,
                "path": t.path,
            }
            for t in result.tasks
        ],
        "files": result.files,
        "findings": [{**f.to_json(), "task": task_id(f.task)} for f in (findings or [])],
    }


def _indent(text: str, prefix: str) -> list[str]:
    return [prefix + line if line.strip() else "" for line in text.splitlines()]


def format_preview(data: dict[str, Any]) -> str:
    """The tree (project ->) step -> tasks with their texts and the reason of the placement,
    for the terminal."""
    lines: list[str] = []
    project = data.get("project")
    if project:
        state = "new" if project["new"] else "existing"
        lines.append(f"{project['id']} ({state}) {project['title']}  [{project['path']}]")
        if project["new"] and project["body"]:
            lines += _indent(project["body"], "  ")
    if data.get("placement_reason"):
        lines.append(f"placement: {data['placement_reason']}")
    step = data["step"]
    state = "new" if step["new"] else "existing"
    lines.append(f"{step['id']} ({state}) {step['title']}  [{step['path']}]")
    if step["new"] and step["body"]:
        lines += _indent(step["body"], "  ")
    for task in data["tasks"]:
        lines.append("")
        lines.append(f"  {task['id']} {task['title']}")
        lines.append(f"    workflow: {task['workflow']}")
        lines.append(f"    writes: {', '.join(task['writes']) or '-'}")
        lines.append(f"    depends_on: {', '.join(task['depends_on']) or '-'}")
        lines.append("")
        lines += _indent(task["body"], "    ")
    findings = data.get("findings") or []
    if findings:
        lines += ["", f"findings of the quality check ({len(findings)}):"]
        lines += [f"  - [{f['rule']}] {f['task']}: {f['message']}" for f in findings]
    return "\n".join(lines)
