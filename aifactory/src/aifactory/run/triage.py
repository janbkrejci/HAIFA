"""Read-only follow-up recommendations; applying them belongs to the caller.

Only task bodies are bounded (6,000 characters including the ellipsis). No task
or follow-up is omitted. Scope containment is deliberately conservative; semantic
relatedness and preservation of the original assignment remain agent judgments.
"""

from __future__ import annotations

import json
import re
import secrets
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aifactory.backlog import Backlog, effective_writes, is_human, iter_tasks
from aifactory.backlog.derived import ancestors
from aifactory.config import load_run_config
from aifactory.engine import agents
from aifactory.engine.data_types import AgentCall, EnvelopeBase, PhaseParams
from aifactory.engine.runner import Run
from aifactory.engine.tracer import Tracer
from aifactory.harness import canonical, install
from aifactory.harness.check import check_harness
from aifactory.harness.settings import ensure_enabled
from aifactory.run.followups import Reported
from aifactory.run.guard import TaskWriteGuard
from aifactory.run.scope import TaskScope, matches
from aifactory.run.task import _main_ignored, prepare_cfg
from aifactory.workflow.propose import _isolated

install()

BODY_LIMIT = 6000


class TriageUnavailable(RuntimeError):
    """Triage could not produce validated recommendations; nothing was applied."""


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    follow_up_id: str = Field(min_length=1)
    action: Literal["covered", "extend", "decide", "new"]
    reason: str = Field(min_length=1, description="One sentence explaining the decision")
    task_id: str | None = Field(default=None, min_length=1)
    addition: str | None = Field(default=None, min_length=1)
    proposal: str | None = Field(default=None, min_length=1)
    addition_writes: list[str] | None = None

    @model_validator(mode="after")
    def action_fields(self) -> Self:
        if (self.task_id is not None) != (self.action != "new"):
            raise ValueError("task_id is required only for covered/extend/decide")
        if (self.addition is not None) != (self.action == "extend"):
            raise ValueError("addition is required only for extend")
        if (self.addition_writes is not None) != (self.action == "extend"):
            raise ValueError("addition_writes is required only for extend")
        if (self.proposal is not None) != (self.action == "decide"):
            raise ValueError("proposal is required only for decide")
        return self


class TriageOutput(EnvelopeBase):
    model_config = ConfigDict(extra="forbid")
    decisions: list[Decision] = Field(default_factory=list)


def context(reported: Sequence[Reported], backlog: Backlog) -> dict[str, Any]:
    """Pure, serializable input, preserving stored todo status and inherited scope."""
    tasks = []
    for task in iter_tasks(backlog):
        if task.status != "todo":
            continue
        step = next((c for c in ancestors(task) if c.level == "step"), task.parent)
        truncated = len(task.body) > BODY_LIMIT
        tasks.append(
            {
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "path": task.path,
                "step": {"id": step.id, "title": step.title},
                "body": task.body[: BODY_LIMIT - 1] + "…" if truncated else task.body,
                "body_truncated": truncated,
                "writes": effective_writes(task),
                "assignee": "human" if is_human(task) else "agent",
            }
        )
    return {
        "follow_ups": [
            {
                "id": f"f{n}",
                "title": r.title,
                "reason": r.reason,
                "details": r.details,
                "blocks_task": r.blocks_task,
                "writes": list(r.writes) if r.writes is not None else None,
                "for_human": r.for_human,
            }
            for n, r in enumerate(reported, 1)
        ],
        "backlog": tasks,
        "output_schema": TriageOutput.model_json_schema(),
    }


def _safe_path(value: str) -> str | None:
    value = value.strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    if (
        not value
        or value.startswith(("/", "~"))
        or ":" in value
        or any(p in ("..", ".", "") for p in value.rstrip("/").split("/"))
    ):
        return None
    return value


def _contained(required: str, allowed: str) -> bool:
    """Prove containment, never infer it merely from overlapping glob prefixes."""
    need, scope = _safe_path(required), _safe_path(allowed)
    if need is None or scope is None:
        return False
    if need == scope or scope == "**":
        return True
    wildcard = any(c in need for c in "*?[")
    scope_wildcard = any(c in scope for c in "*?[")
    if not scope_wildcard:
        base = scope.rstrip("/")
        return need.rstrip("/") == base or need.startswith(base + "/")
    if wildcard or need.endswith("/"):
        return False
    return matches(need, scope)


def _named_paths(text: str) -> list[str]:
    """Supplementary syntactic evidence, not natural-language scope inference.

    Backticked single path tokens and slash-containing bare tokens are treated
    conservatively as work paths. URLs and commands are not path evidence.
    """
    text = re.sub(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s`]+", "", text)
    tokens = re.findall(
        r"`([^`\n]+)`|(?<![\w/\\])((?:[A-Za-z]:)?[.\w*?\[\]/\\-]*[/\\][.\w*?\[\]/\\-]+)",
        text,
    )
    result = []
    for quoted, bare in tokens:
        token = (quoted or bare).rstrip(".,;:)")
        if not token or any(c.isspace() for c in token) or "://" in token or token.startswith("-"):
            continue
        if "/" in token or "\\" in token or re.search(r"\.[a-zA-Z][a-zA-Z0-9]*$", token):
            result.append(token)
    return result


def _violations(output: TriageOutput, reported: Sequence[Reported], backlog: Backlog) -> list[str]:
    if output.status != "success":
        return []
    expected = {f"f{n}": r for n, r in enumerate(reported, 1)}
    counts = Counter(d.follow_up_id for d in output.decisions)
    errors = [
        f"{fid}: expected exactly one decision, got {counts[fid]}"
        for fid in expected
        if counts[fid] != 1
    ]
    errors += [f"{fid}: unknown follow-up id" for fid in counts if fid not in expected]
    tasks = {t.id: t for t in iter_tasks(backlog)}
    for decision in output.decisions:
        label = f"{decision.follow_up_id} ({decision.action}, task {decision.task_id})"
        if decision.action == "new":
            continue
        task = tasks.get(decision.task_id or "")
        if task is None or task.status != "todo":
            errors.append(f"{label}: target must be a known todo task")
            continue
        if decision.action != "extend":
            continue
        report = expected.get(decision.follow_up_id)
        if report is None:
            continue
        if is_human(task) or report.for_human:
            errors.append(f"{label}: cannot extend a human task or redirect human-only work")
        evidence = decision.addition_writes or []
        if not evidence and report.writes != ():
            errors.append(
                f"{label}: addition_writes must identify required paths; empty evidence is "
                "allowed only for explicitly read-only reported writes=[]"
            )
        scope = effective_writes(task)
        required = [*(report.writes or ()), *evidence, *_named_paths(decision.addition or "")]
        for path in dict.fromkeys(required):
            if not any(_contained(path, allowed) for allowed in scope):
                errors.append(f"{label}: extend path {path!r} is outside target writes {scope}")
        for path in _named_paths(decision.addition or ""):
            if not any(_contained(path, declared) for declared in evidence):
                errors.append(f"{label}: addition path {path!r} lacks addition_writes evidence")
    return errors


def ask_triager(repo: Path, reported: Sequence[Reported], backlog: Backlog) -> list[Decision]:
    """Recommend handling, or raise TriageUnavailable after one semantic correction."""
    if not reported:
        return []
    if not any(t.status == "todo" for t in iter_tasks(backlog)):
        return [
            Decision(follow_up_id=f"f{n}", action="new", reason="No todo task covers this work.")
            for n, _ in enumerate(reported, 1)
        ]
    try:
        return _invoke(repo, reported, backlog)
    except TriageUnavailable:
        raise
    except Exception as exc:
        raise TriageUnavailable(f"Triager unavailable: {exc}") from exc


def _invoke(repo: Path, reported: Sequence[Reported], backlog: Backlog) -> list[Decision]:
    job_id = f"triage-{secrets.token_hex(4)}"
    rc = load_run_config(repo)
    with _isolated(repo, rc.commit, None) as isolated:
        runtime = repo / ".factory/data/triage" / job_id
        runtime.mkdir(parents=True, exist_ok=True)
        try:
            cfg = prepare_cfg(repo, rc, runtime / "prompts")
            if not any(a.name == "triager" for a in cfg.agents):
                raise TriageUnavailable(
                    "Agent 'triager' missing from roster/library; run 'factory library seed'"
                )
            agent = agents.resolve(cfg, "triager")
            agent.writes = []
            agents.validate(cfg, [agent.name])
        except SystemExit as exc:
            raise TriageUnavailable(f"Invalid triager configuration: {exc}") from exc
        ensure_enabled(agent.coding_agent)
        status = check_harness(canonical(agent.coding_agent))
        if not status.ok:
            raise TriageUnavailable(f"Triager harness unavailable: {status.name}: {status.error}")
        cfg.defaults.data_dir = str(runtime)
        cfg.observability.db = str(runtime / "trace.db")
        tracer = Tracer(cfg.observability.db, runtime / "events.jsonl")

        def gate(envelope: EnvelopeBase, run: Any) -> list[str]:
            assert isinstance(envelope, TriageOutput)
            return _violations(envelope, reported, backlog)

        ok = False
        try:
            tracer.session_start(job_id, "triage")
            run = Run(cfg, job_id, tracer, "triage")
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
            with run.phase(
                PhaseParams(
                    name="triage",
                    kind="agent",
                    owner=agent.name,
                    description="Compare reported follow-ups with todo backlog tasks",
                    retries=1,
                )
            ) as phase:
                envelope = phase.call(
                    AgentCall(
                        prompt=json.dumps(context(reported, backlog), ensure_ascii=False, indent=2),
                        output_type=TriageOutput,
                        gates=[gate],
                    )
                )
            output = TriageOutput.model_validate(envelope.model_dump())
            errors = _violations(output, reported, backlog)
            if output.status != "success" or errors:
                raise TriageUnavailable(f"Triager failed: {output.summary}; {'; '.join(errors)}")
            by_id = {d.follow_up_id: d for d in output.decisions}
            decisions = [by_id[f"f{n}"] for n, _ in enumerate(reported, 1)]
            ok = True
            return decisions
        finally:
            try:
                tracer.session_finish(job_id, ok=ok)
            finally:
                tracer.conn.close()
