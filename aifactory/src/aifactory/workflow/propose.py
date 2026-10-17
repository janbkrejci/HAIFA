"""``factory backlog propose``: a read-only agent turns an intent into a backlog proposal.

The agent ``proposer`` (library seed; its prompts are overridden in
``.factory/prompts/proposer/``) works like workflow advice (``workflow.adaptive``): in an
isolated clone checked out at the base commit, with no writes. It returns a typed
``BacklogProposalOutput``: a new step of the project ``--project`` with its tasks, or new
tasks of the existing step ``--step``. The proposal is validated against the backlog of the
working tree like ``factory task add`` (``backlog.add_batch``) plus the workflow catalog and
the blocking rules of ``propose_check`` (``Hotovo znamená``, no dependency cycle). An invalid
proposal goes back to the agent once (a gate correction in the same session); a second
invalid one fails with ``proposal_invalid`` and nothing is written. The other findings of
``propose_check`` (writes) go back to the agent in the same single correction; those left
after it are returned in ``findings`` and shown in the preview. Only ``apply=True`` writes,
and never commits.
"""

from __future__ import annotations

import json
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aifactory import backlog as core
from aifactory import yamlload
from aifactory.backlog import Issue, NewTask, TaskEditError
from aifactory.config import load_run_config
from aifactory.engine import agents
from aifactory.engine.data_types import AgentCall, EnvelopeBase, PhaseParams
from aifactory.engine.runner import Run
from aifactory.engine.tracer import Tracer
from aifactory.failure import AgentReportedFail, InvalidOutput
from aifactory.harness import canonical, install
from aifactory.harness.check import check_harness
from aifactory.providers.git import PARALLEL_CHECKOUT
from aifactory.run.guard import TaskWriteGuard
from aifactory.run.scope import TaskScope
from aifactory.run.task import _main_ignored, prepare_cfg
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
        default=None, description="the new step (target is a project); null for a step"
    )
    tasks: list[ProposedTask] = Field(min_length=1, max_length=50)


@dataclass
class Target:
    """Where the proposal goes: a new step of ``project``, or the existing ``step``."""

    project: str | None = None
    step: str | None = None


def workflow_catalog(repo: Path) -> dict[str, dict[str, Any]]:
    """Every workflow a task can name: the package defaults, the library and the repo's."""
    catalog: dict[str, dict[str, Any]] = {
        p.stem: yamlload.safe_load(p.read_text(encoding="utf-8"))
        for p in DEFAULT_WORKFLOWS_DIR.glob("*.yaml")
    }
    catalog.update(load_run_config(repo).config.workflows)
    return catalog


def _check_target(backlog: core.Backlog, target: Target) -> None:
    if (target.project is None) == (target.step is None):
        raise TaskEditError("conflicting_options", "give either --project or --step")
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


def _clip(text: str) -> str:
    return text if len(text) <= _BODY_LIMIT else text[:_BODY_LIMIT] + "\n[truncated]"


def context(repo: Path, intent: str, target: Target) -> dict[str, Any]:
    """What the agent gets: the intent, the target, the backlog and the workflow catalog."""
    if not intent.strip():
        raise TaskEditError("invalid_value", "the intent must not be empty")
    backlog = core.load_for_edit(repo)
    _check_target(backlog, target)
    focus = backlog.by_id[target.step or target.project or ""]
    assert isinstance(focus, core.Container)
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
    focus_tasks = [
        {"id": t.id, "title": t.title, "path": t.path, "body": _clip(t.body)}
        for c in [focus, *core.iter_containers(focus.children)]
        for t in c.tasks
    ]
    catalog = {
        name: {"description": (data or {}).get("description", "")}
        for name, data in sorted(workflow_catalog(repo).items())
    }
    payload: dict[str, Any] = {
        "intent": intent.strip(),
        "target": (
            {"kind": "existing_step", "step": focus.id}
            if target.step
            else {"kind": "new_step", "project": focus.id}
        ),
        "target_container": {
            "id": focus.id,
            "title": focus.title,
            "path": focus.path,
            "body": _clip(focus.body),
            "defaults": focus.defaults,
            "tasks": focus_tasks,
        },
        "levels": backlog.settings.levels,
        "containers": containers,
        "tasks": tasks,
        "workflows": catalog,
        "output_schema": BacklogProposalOutput.model_json_schema(),
    }
    if len(json.dumps(payload, ensure_ascii=False).encode()) > _CONTEXT_LIMIT:
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
    problems: list[Issue] = []
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
    step = proposal.step
    try:
        result = core.add_batch(
            repo,
            _batch(proposal),
            step=target.step,
            project=target.project,
            step_code=step.code if step else None,
            step_title=step.title if step else None,
            step_body=step.body if step else "",
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
    if target.step is not None:
        return target.step
    if proposal.step is None or target.project is None:
        return None
    return f"{target.project}-{proposal.step.code.strip()}"


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


def propose(
    repo: Path, intent: str, target: Target, *, apply: bool = False, job_id: str | None = None
) -> dict[str, Any]:
    """Run the proposer, validate (one correction), and return the proposal as JSON data."""
    payload = context(repo, intent, target)
    catalog = workflow_catalog(repo)
    job_id = job_id or f"propose-{secrets.token_hex(4)}"
    rc = load_run_config(repo)
    with advice_dir() as tmp:
        isolated = tmp / "repo"
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
                rc.commit,
            ],
            check=True,
            capture_output=True,
        )
        runtime = repo / ".factory/data/backlog-propose" / job_id
        runtime.mkdir(parents=True, exist_ok=True)
        cfg = prepare_cfg(repo, rc, runtime / "prompts")
        if not any(a.name == PROPOSER_AGENT for a in cfg.agents):
            raise TaskEditError(
                "agent_unavailable",
                f"agent '{PROPOSER_AGENT}' is missing from the roster and the library; "
                "run 'factory library seed' to take it from the seed",
            )
        agent = agents.resolve(cfg, PROPOSER_AGENT)
        from aifactory.harness.settings import ensure_enabled

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
                            prompt=json.dumps(payload, ensure_ascii=False, indent=2),
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
            return to_json(proposal, result, target, remaining)
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

    return {
        "summary": proposal.summary,
        "applied": result.written,
        "project": target.project,
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
    """The tree step -> tasks with their texts, for the terminal."""
    step = data["step"]
    state = "new" if step["new"] else "existing"
    lines = [f"{step['id']} ({state}) {step['title']}  [{step['path']}]"]
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
