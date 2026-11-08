"""Read-only follow-up recommendations; applying them belongs to the caller.

Backlog candidates are prioritized and bounded by a serialized context budget.
Follow-ups are preserved; oversized fixed input fails before invoking the model.
Scope containment is deliberately conservative; semantic relatedness and
preservation of the original assignment remain agent judgments.
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

from aifactory.backlog import Backlog, Container, effective_writes, is_human, iter_tasks
from aifactory.backlog.derived import ancestors, descendant_tasks, harness_values
from aifactory.config import load_run_config
from aifactory.engine import agents
from aifactory.engine.data_types import AgentCall, EnvelopeBase, PhaseParams
from aifactory.engine.runner import Run
from aifactory.engine.tracer import Tracer
from aifactory.harness import canonical, install
from aifactory.harness.check import check_harness
from aifactory.harness.settings import context_binding, ensure_enabled
from aifactory.run.followups import Reported, _for_human
from aifactory.run.guard import TaskWriteGuard
from aifactory.run.scope import TaskScope, matches
from aifactory.run.task import _main_ignored, apply_agents_override, prepare_cfg
from aifactory.workflow.propose import _isolated

install()

BODY_LIMIT = 6000
# Characters of JSON sent here, including follow-ups and schema; allows room for system prompts.
CONTEXT_LIMIT = 120_000


class TriageUnavailable(RuntimeError):
    """Triage could not produce validated recommendations; nothing was applied."""


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    follow_up_id: str = Field(min_length=1)
    action: Literal["covered", "extend", "decide", "new"]
    reason: str = Field(min_length=1, description="One sentence explaining the decision")
    task_id: str | None = Field(default=None, min_length=1)
    target_follow_up_id: str | None = Field(default=None, min_length=1)
    addition: str | None = Field(default=None, min_length=1)
    proposal: str | None = Field(default=None, min_length=1)
    addition_writes: list[str] | None = None

    @model_validator(mode="after")
    def action_fields(self) -> Self:
        if self.target_follow_up_id is not None:
            if self.action != "covered" or self.task_id is not None:
                raise ValueError("target_follow_up_id is allowed only for covered without task_id")
        elif (self.task_id is not None) != (self.action != "new"):
            raise ValueError(
                "task_id is required for covered/extend/decide without a follow-up target"
            )
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


def context(
    reported: Sequence[Reported], backlog: Backlog, *, task_id: str | None = None
) -> dict[str, Any]:
    """Pure, serializable input, preserving stored todo status and inherited scope."""
    source = backlog.by_id.get(task_id or "")
    project = next((c for c in ancestors(source) if c.level == "project"), None) if source else None
    candidates = [t for t in iter_tasks(backlog) if t.status == "todo"]
    local = {
        t.id for t in candidates if project is not None and any(c is project for c in ancestors(t))
    }
    dependencies: set[str] = set()
    pending = list(local)
    while pending:
        node = backlog.by_id.get(pending.pop())
        if node is None:
            continue
        targets = (
            [t.id for t in descendant_tasks(node)]
            if isinstance(node, Container)
            else node.depends_on
        )
        for target in targets:
            if target not in dependencies:
                dependencies.add(target)
                pending.append(target)
    candidates.sort(key=lambda t: 0 if t.id in local else 1 if t.id in dependencies else 2)
    tasks: list[dict[str, Any]] = []
    for task in candidates:
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
    payload: dict[str, Any] = {
        "follow_ups": [
            {
                "id": f"f{n}",
                "title": r.title,
                "reason": r.reason,
                "details": r.details,
                **({"severity": r.severity} if r.severity is not None else {}),
                "blocks_task": r.blocks_task,
                "writes": list(r.writes) if r.writes is not None else None,
                "for_human": _for_human(r, backlog.settings),
            }
            for n, r in enumerate(reported, 1)
        ],
        "backlog": tasks,
        "backlog_truncated": any(t["body_truncated"] for t in tasks),
        "output_schema": TriageOutput.model_json_schema(),
    }
    size = len(_context_json(payload))
    if size <= CONTEXT_LIMIT:
        return payload
    payload["backlog_truncated"] = True
    size = len(_context_json(payload))

    def entry_size(entry: dict[str, Any]) -> int:
        # Match indentation of an entry nested in the backlog array.
        return len(json.dumps([entry], ensure_ascii=False, indent=2).replace("\n", "\n  "))

    for entry in reversed(tasks):
        if size <= CONTEXT_LIMIT:
            break
        original_size = entry_size(entry)
        body = entry["body"]
        entry["body_truncated"] = True
        entry["body"] = ""
        available = CONTEXT_LIMIT - (size - original_size + entry_size(entry))
        if available > 0:
            low, high = 0, len(body)
            while low < high:
                mid = (low + high + 1) // 2
                if len(json.dumps(body[:mid] + "…", ensure_ascii=False)) - 2 <= available:
                    low = mid
                else:
                    high = mid - 1
            entry["body"] = body[:low] + "…" if low else ""
        size += entry_size(entry) - original_size
        if size > CONTEXT_LIMIT:
            previous_size = entry_size(entry)
            minimal = {"id": entry["id"], "title": entry["title"]}
            entry.clear()
            entry.update(minimal)
            size += entry_size(entry) - previous_size
    while tasks and size > CONTEXT_LIMIT:
        tasks.pop()
        size = len(_context_json(payload))
    if size > CONTEXT_LIMIT:
        raise TriageUnavailable("Triager context exceeds budget even without backlog candidates")
    return payload


def _context_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


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


def _follow_up_roots(
    decisions: Sequence[Decision], reported: Sequence[Reported], backlog: Backlog
) -> tuple[dict[str, str], list[str]]:
    """Resolve same-run coverage iteratively; never apply a partial invalid graph."""
    reports = {f"f{n}": r for n, r in enumerate(reported, 1)}
    edges = {
        d.follow_up_id: d.target_follow_up_id
        for d in decisions
        if d.target_follow_up_id is not None
    }
    errors = []
    for source, target in edges.items():
        if source not in reports or target not in reports:
            errors.append(f"{source}: unknown follow-up target {target}")
        elif _for_human(reports[source], backlog.settings) != _for_human(
            reports[target], backlog.settings
        ):
            errors.append(f"{source}: follow-up target {target} has a different human assignment")
    roots: dict[str, str] = {}
    for source in reports:
        path: list[str] = []
        seen: set[str] = set()
        current = source
        while current in edges and current not in roots and current not in seen:
            seen.add(current)
            path.append(current)
            current = edges[current]
        if current in seen:
            errors.append(f"{source}: follow-up coverage cycle")
            continue
        root = roots.get(current, current)
        roots[source] = root
        for member in path:
            roots[member] = root
    return roots, errors


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
    _, graph_errors = _follow_up_roots(output.decisions, reported, backlog)
    errors += graph_errors
    tasks = {t.id: t for t in iter_tasks(backlog)}
    for decision in output.decisions:
        label = f"{decision.follow_up_id} ({decision.action}, task {decision.task_id})"
        if decision.action == "new" or decision.target_follow_up_id is not None:
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


def ask_triager(
    repo: Path,
    reported: Sequence[Reported],
    backlog: Backlog,
    *,
    task_id: str | None = None,
    binding: dict[str, str] | None = None,
) -> list[Decision]:
    """Recommend handling, or raise TriageUnavailable after one semantic correction."""
    if not reported:
        return []
    if len(reported) == 1 and not any(t.status == "todo" for t in iter_tasks(backlog)):
        return [
            Decision(follow_up_id=f"f{n}", action="new", reason="No todo task covers this work.")
            for n, _ in enumerate(reported, 1)
        ]
    try:
        return _invoke(repo, reported, backlog, task_id=task_id, binding=binding)
    except TriageUnavailable:
        raise
    except Exception as exc:
        raise TriageUnavailable(f"Triager unavailable: {exc}") from exc


def _invoke(
    repo: Path,
    reported: Sequence[Reported],
    backlog: Backlog,
    *,
    task_id: str | None = None,
    binding: dict[str, str] | None = None,
) -> list[Decision]:
    job_id = f"triage-{secrets.token_hex(4)}"
    rc = load_run_config(repo)
    if binding is None and task_id is not None:
        task = next((t for t in iter_tasks(backlog) if t.id == task_id), None)
        if task is None:
            raise TriageUnavailable(f"Unknown source task: {task_id}")
        binding = context_binding(harness_values(task))
    rc = apply_agents_override(rc, binding)
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
                    description="Compare follow-ups with each other and todo backlog tasks",
                    retries=1,
                )
            ) as phase:
                try:
                    envelope = phase.call(
                        AgentCall(
                            prompt=_context_json(context(reported, backlog, task_id=task_id)),
                            output_type=TriageOutput,
                            gates=[gate],
                        )
                    )
                    output = TriageOutput.model_validate(envelope.model_dump())
                    errors = _violations(output, reported, backlog)
                    if output.status != "success" or errors:
                        raise TriageUnavailable(
                            f"Triager failed: {output.summary}; {'; '.join(errors)}"
                        )
                except Exception as exc:
                    row = tracer.conn.execute(
                        "SELECT payload_json FROM envelopes WHERE phase_id=? AND valid=0 "
                        "ORDER BY rowid DESC LIMIT 1",
                        (phase.phase.phase_id,),
                    ).fetchone()
                    response = json.loads(row[0]).get("raw", "") if row else ""
                    phase.log(error=str(exc), model_response=response)
                    raise TriageUnavailable(
                        f"Triager failed; model response: {response[:700]}; reason: {exc}"
                    ) from exc
            by_id = {d.follow_up_id: d for d in output.decisions}
            decisions = [by_id[f"f{n}"] for n, _ in enumerate(reported, 1)]
            ok = True
            return decisions
        finally:
            try:
                tracer.session_finish(job_id, ok=ok)
            finally:
                tracer.conn.close()
