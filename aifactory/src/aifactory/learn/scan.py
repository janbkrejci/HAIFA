"""``factory learn scan``: the agent ``learner`` groups repeated objections into lessons.

The objections of every task run (``collect``) go to the read-only agent ``learner``
(library seed; prompts overridden in ``.factory/prompts/learner/``) with the lessons a
person rejected. It works like ``backlog propose``: in an isolated clone at the base
commit, with no writes, its own trace under ``.factory/data/learn/<job>/``. It answers
``LessonsOutput``: per lesson a short rule, where the rule belongs (``CLAUDE.md``,
``AGENTS.md``, a ``skill`` of the repo or the ``prompt`` of a role) and the ids of the
objections it groups. A lesson naming an unknown objection goes back to the agent once.

The code then counts the occurrences (the distinct runs of the objections) and drops a
lesson seen in one run only, one whose rule a person settled (accepted or rejected; the
agent gets them as ``rejected_lessons`` and ``accepted_lessons``), and one whose
objections all belong to a settled lesson. The rest is saved as ``proposed`` in
``learn_lessons`` (``store``);
``factory learn dismiss`` rejects one for good and ``factory learn accept`` (``accept``)
turns one into a backlog task. With objections from fewer than two runs no agent runs at
all.

The agent also gets the accepted lessons (``accepted_lessons``): objections that repeat one
of them go into a lesson with its id in ``accepted`` (or its rule, or some of its
objections). Such a lesson is never proposed; its objections are added to the accepted
lesson (``repeats``), so the dashboard can count how often the mistake came back after
the lesson's pull request was merged (``view``).
"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aifactory.backlog import TaskEditError
from aifactory.config import load_local, load_run_config
from aifactory.engine import agents
from aifactory.engine.data_types import AgentCall, EnvelopeBase, PhaseParams
from aifactory.engine.runner import Run
from aifactory.engine.tracer import Tracer
from aifactory.failure import AgentReportedFail, InvalidOutput
from aifactory.harness import canonical, install
from aifactory.harness.check import check_harness
from aifactory.harness.settings import effective_override
from aifactory.learn.collect import Objection, collect
from aifactory.learn.store import (
    ACCEPTED,
    REJECTED,
    LessonStore,
    StoredLesson,
    lesson_id,
    normalize,
)
from aifactory.run.guard import TaskWriteGuard
from aifactory.run.scope import TaskScope
from aifactory.run.task import _main_ignored, apply_agents_override, prepare_cfg
from aifactory.workflow.propose import _isolated

install()

LEARNER_AGENT = "learner"
CORRECTIONS = 1
MIN_RUNS = 2
TARGETS = ("CLAUDE.md", "AGENTS.md", "skill", "prompt")
_MAX_OBJECTIONS = 400
_SNIPPET_LIMIT = 300


class ProposedLesson(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule: str = Field(min_length=1, max_length=500, description="the rule, short and imperative")
    target: Literal["CLAUDE.md", "AGENTS.md", "skill", "prompt"] = Field(
        description="where the rule belongs"
    )
    target_detail: str = Field(
        default="",
        max_length=200,
        description="the skill name for 'skill', the role or agent for 'prompt', else ''",
    )
    complaints: list[str] = Field(
        min_length=1, description="ids of the objections (c1, c2, ...) this lesson groups"
    )
    accepted: str = Field(
        default="",
        max_length=40,
        description="the id of the accepted lesson these objections repeat, else ''",
    )


class LessonsOutput(EnvelopeBase):
    model_config = ConfigDict(extra="forbid")
    lessons: list[ProposedLesson] = Field(default_factory=list, max_length=50)


def parse_since(value: str | None) -> str | None:
    """``--since`` as an ISO timestamp in UTC (a date: its midnight), comparable with the trace."""
    if value is None or not value.strip():
        return None
    text = value.strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        pass
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise TaskEditError(
            "invalid_value", f"--since: {value!r} is not a date (YYYY-MM-DD) or ISO timestamp"
        ) from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="milliseconds")


def trace_db(repo: Path) -> Path:
    return load_local(repo).trace_db_path(repo)


def context(objections: list[Objection], settled: list[StoredLesson]) -> dict[str, Any]:
    """What the agent gets: the objections by short id, the settled rules, the schema."""
    return {
        "objections": [
            {
                "id": f"c{n}",
                "run_id": o.run_id,
                "task_id": o.task_id,
                "source": o.source,
                "agent": o.agent,
                "text": o.text,
            }
            for n, o in enumerate(objections, 1)
        ],
        "rejected_lessons": [
            {"id": r.lesson_id, "rule": r.rule} for r in settled if r.state == REJECTED
        ],
        "accepted_lessons": [
            {"id": r.lesson_id, "rule": r.rule} for r in settled if r.state == ACCEPTED
        ],
        "targets": {
            "CLAUDE.md": "instructions for Claude Code in the repo root",
            "AGENTS.md": "instructions for every coding agent in the repo root",
            "skill": "a skill of the repo (target_detail: its name)",
            "prompt": "the prompt of a role or agent (target_detail: its name)",
        },
        "min_runs": MIN_RUNS,
        "output_schema": LessonsOutput.model_json_schema(),
    }


def _ask_learner(repo: Path, payload: dict[str, Any], known: set[str]) -> LessonsOutput:
    """One call of the agent ``learner`` (one correction for unknown objection ids)."""
    job_id = f"learn-{secrets.token_hex(4)}"
    rc = load_run_config(repo)
    rc = apply_agents_override(rc, effective_override({}, None))
    with _isolated(repo, rc.commit, None) as isolated:
        runtime = repo / ".factory/data/learn" / job_id
        runtime.mkdir(parents=True, exist_ok=True)
        cfg = prepare_cfg(repo, rc, runtime / "prompts")
        if not any(a.name == LEARNER_AGENT for a in cfg.agents):
            raise TaskEditError(
                "agent_unavailable",
                f"agent '{LEARNER_AGENT}' is missing from the roster and the library; "
                "run 'factory library seed' to take it from the seed",
            )
        agent = agents.resolve(cfg, LEARNER_AGENT)
        from aifactory.harness.settings import ensure_enabled

        try:
            ensure_enabled(agent.coding_agent)
        except ValueError as exc:
            raise TaskEditError("agent_unavailable", str(exc)) from exc
        status = check_harness(canonical(agent.coding_agent))
        if not status.ok:
            raise TaskEditError(
                "agent_unavailable", f"learner harness unavailable: {status.name}: {status.error}"
            )
        agent.writes = []
        agents.validate(cfg, [agent.name])
        cfg.defaults.data_dir = str(runtime)
        cfg.observability.db = str(runtime / "trace.db")
        tracer = Tracer(cfg.observability.db, runtime / "events.jsonl")

        def ids_known(envelope: EnvelopeBase, run: Any) -> list[str]:
            if envelope.status != "success":
                return []
            assert isinstance(envelope, LessonsOutput)
            return [
                f"lesson '{lesson.rule}': unknown objection id '{cid}'"
                for lesson in envelope.lessons
                for cid in lesson.complaints
                if cid not in known
            ]

        ok = False
        try:
            tracer.session_start(job_id, "learn-scan")
            run = Run(cfg, job_id, tracer, "learn-scan")
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
                        name="learn-scan",
                        kind="agent",
                        owner=agent.name,
                        description="Group repeated objections of runs into lessons",
                        retries=CORRECTIONS,
                    )
                ) as ph:
                    envelope = ph.call(
                        AgentCall(
                            prompt=json.dumps(payload, ensure_ascii=False, indent=2),
                            output_type=LessonsOutput,
                            gates=[ids_known],
                        )
                    )
            except AgentReportedFail as exc:
                raise TaskEditError(
                    "learn_failed", f"the learner gave up: {exc}", exit_code=1
                ) from exc
            except InvalidOutput as exc:
                raise TaskEditError(
                    "lessons_invalid",
                    "the lessons are invalid even after one correction; nothing was saved",
                    exit_code=1,
                ) from exc
            ok = True
            return LessonsOutput.model_validate(envelope.model_dump())
        finally:
            try:
                tracer.session_finish(job_id, ok=ok)
            finally:
                tracer.conn.close()


def _snippet(o: Objection) -> dict[str, str]:
    text = o.text if len(o.text) <= _SNIPPET_LIMIT else o.text[: _SNIPPET_LIMIT - 1] + "…"
    return {
        "run_id": o.run_id,
        "task_id": o.task_id,
        "source": o.source,
        "phase": o.phase,
        "text": text,
        "created_at": o.created_at,
    }


def _blocked(rule: str, keys: set[str], rejected: list[StoredLesson]) -> bool:
    """A settled rule, or objections that all belong to a settled lesson."""
    return any(
        normalize(r.rule) == normalize(rule) or (r.complaints and keys <= set(r.complaints))
        for r in rejected
    )


def _repeated(
    lesson: ProposedLesson, keys: set[str], settled: list[StoredLesson]
) -> StoredLesson | None:
    """The accepted lesson ``lesson`` repeats: by its id, its rule or shared objections."""
    accepted = [s for s in settled if s.state == ACCEPTED]
    for match in (
        lambda a: a.lesson_id == lesson.accepted.strip(),
        lambda a: normalize(a.rule) == normalize(lesson.rule),
        lambda a: bool(keys & set(a.complaints)),
    ):
        found = next((a for a in accepted if match(a)), None)
        if found is not None:
            return found
    return None


def repeats_of(
    output: LessonsOutput, by_id: dict[str, Objection], settled: list[StoredLesson]
) -> dict[str, list[Objection]]:
    """The objections of each accepted lesson the agent found again, by lesson id."""
    result: dict[str, list[Objection]] = {}
    for lesson in output.lessons:
        found = [by_id[c] for c in dict.fromkeys(lesson.complaints) if c in by_id]
        accepted = _repeated(lesson, {o.key for o in found}, settled) if found else None
        if accepted is not None:
            known = {o.key for o in result.setdefault(accepted.lesson_id, [])}
            result[accepted.lesson_id] += [o for o in found if o.key not in known]
    return result


def lessons_of(
    output: LessonsOutput, by_id: dict[str, Objection], rejected: list[StoredLesson]
) -> list[dict[str, Any]]:
    """The lessons worth proposing, most occurrences first, as JSON data."""
    merged: dict[str, dict[str, Any]] = {}
    for lesson in output.lessons:
        found = [by_id[c] for c in dict.fromkeys(lesson.complaints) if c in by_id]
        keys = {o.key for o in found}
        if not found or _blocked(lesson.rule, keys, rejected):
            continue
        if _repeated(lesson, keys, rejected) is not None:
            continue
        lid = lesson_id(lesson.rule)
        entry = merged.setdefault(
            lid,
            {
                "id": lid,
                "rule": lesson.rule.strip(),
                "target": lesson.target,
                "target_detail": lesson.target_detail.strip(),
                "objections": [],
            },
        )
        known = {o.key for o in entry["objections"]}
        entry["objections"].extend(o for o in found if o.key not in known)
    result: list[dict[str, Any]] = []
    for entry in merged.values():
        found = entry.pop("objections")
        runs: dict[str, str] = {}
        for o in found:
            runs.setdefault(o.run_id, o.task_id)
        if len(runs) < MIN_RUNS:
            continue
        result.append(
            {
                **entry,
                "occurrences": len(runs),
                "runs": [{"run_id": r, "task_id": t} for r, t in runs.items()],
                "complaints": [_snippet(o) for o in found],
                "keys": [o.key for o in found],
            }
        )
    result.sort(key=lambda lesson: (-lesson["occurrences"], lesson["id"]))
    return result


def scan(repo: Path, since: str | None = None) -> dict[str, Any]:
    """Collect the objections, let the learner group them, save and return the lessons."""
    since_iso = parse_since(since)
    db = trace_db(repo)
    objections = collect(db, since_iso)[-_MAX_OBJECTIONS:]
    runs = {o.run_id for o in objections}
    lessons: list[dict[str, Any]] = []
    repeats: list[dict[str, Any]] = []
    if len(runs) >= MIN_RUNS:
        store = LessonStore(db)
        try:
            rejected = store.settled()
            by_id = {f"c{n}": o for n, o in enumerate(objections, 1)}
            output = _ask_learner(repo, context(objections, rejected), set(by_id))
            lessons = lessons_of(output, by_id, rejected)
            for lesson in lessons:
                store.save_proposed(
                    StoredLesson(
                        lesson_id=lesson["id"],
                        rule=lesson["rule"],
                        target=lesson["target"],
                        target_detail=lesson["target_detail"],
                        complaints=lesson["keys"],
                        runs=[r["run_id"] for r in lesson["runs"]],
                    )
                )
            for lid, found in repeats_of(output, by_id, rejected).items():
                added = store.add_repeats(lid, [o.key for o in found], [o.run_id for o in found])
                repeats.append({"id": lid, "added": added})
        finally:
            store.close()
    for lesson in lessons:
        lesson.pop("keys")
    return {
        "since": since_iso,
        "objections": len(objections),
        "runs": len(runs),
        "lessons": lessons,
        "repeats": repeats,
    }


def dismiss(repo: Path, lesson: str, reason: str | None = None) -> dict[str, Any]:
    store = LessonStore(trace_db(repo))
    try:
        stored = store.reject(lesson.strip(), reason)
    finally:
        store.close()
    return {"id": stored.lesson_id, "rule": stored.rule, "state": stored.state, "reason": reason}


def _where(lesson: dict[str, Any]) -> str:
    detail = lesson["target_detail"]
    return f"{lesson['target']} ({detail})" if detail else lesson["target"]


def format_scan(data: dict[str, Any]) -> str:
    """The lessons for the terminal."""
    head = f"{data['objections']} objection(s) in {data['runs']} run(s)"
    if data["since"]:
        head += f" since {data['since']}"
    if not data["lessons"]:
        return f"{head}\nno objection repeats across runs; no lesson to propose"
    lines = [f"{head}: {len(data['lessons'])} lesson(s)"]
    for lesson in data["lessons"]:
        lines += [
            "",
            f"{lesson['id']}  {lesson['occurrences']} run(s)  -> {_where(lesson)}",
            f"  {lesson['rule']}",
            "  runs: " + ", ".join(f"{r['run_id']} ({r['task_id']})" for r in lesson["runs"]),
        ]
        lines += [f"  - [{c['source']} {c['run_id']}] {c['text']}" for c in lesson["complaints"]]
    lines += [
        "",
        "adopt a lesson with 'factory learn accept ID' (a backlog task), "
        "reject one for good with 'factory learn dismiss ID'",
    ]
    return "\n".join(lines)
