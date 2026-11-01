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

``--all`` (``scan(..., all_repos=True)``) reads the objections of every repo registered
in the dashboard (``sources.collect_all``, keys prefixed ``<repo_id>:``); the learner still
runs in an isolated clone of the repo the scan runs in. The agent gets the registered repos
(``repos``) and names the target repo of every lesson (``repo``): the repo whose
conventions or code the rule is about, or the factory repo for a shortcoming of the factory
itself, the only repo where the target ``seed`` (a role prompt in the library seed) is
allowed. Each lesson is saved in the store of its target repo with the ids of the repos its
objections came from (``origin``); the settled lessons come from the stores of every repo.
Without ``--all`` the lessons name the repo the scan runs in (its registry id, '' when it
is not registered) and the context carries no repos.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import replace
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
from aifactory.home import haifa_home
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
TARGETS = ("CLAUDE.md", "AGENTS.md", "skill", "prompt", "seed")
_MAX_OBJECTIONS = 400
_SNIPPET_LIMIT = 300


class ProposedLesson(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule: str = Field(min_length=1, max_length=500, description="the rule, short and imperative")
    target: Literal["CLAUDE.md", "AGENTS.md", "skill", "prompt", "seed"] = Field(
        description="where the rule belongs"
    )
    target_detail: str = Field(
        default="",
        max_length=200,
        description="the skill name for 'skill', the role or agent for 'prompt' or 'seed', else ''",
    )
    repo: str = Field(
        default="",
        max_length=100,
        description="id of the registered repo the rule belongs to (from 'repos'); "
        "'' without repos",
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


def _own_id(repo: Path) -> str:
    """The registry id of ``repo``, '' when the dashboard does not know it."""
    from aifactory.web.registry import Registry, same_repo  # aifactory.web imports this module

    state, _warnings = Registry(haifa_home()).snapshot()
    return next((e.id for e in state.repos if same_repo(e.path, repo)), "")


def _factory_id() -> str:
    """The registry id of the factory repo, '' when there is none."""
    # learn.sources imports aifactory.web, which imports this module
    from aifactory.learn.sources import factory_repo

    entry = factory_repo()
    return entry.id if entry is not None else ""


SEED_TARGET = (
    "the prompt of a role in the seed of the HAIFA library (target_detail: the role name); "
    "only for the repo with is_factory"
)
REPO_RULE = (
    "Set repo of every lesson to the id of the repo the rule belongs to. A rule about the "
    "conventions or code of one repo belongs to that repo. A shortcoming of the factory "
    "itself (how a role or agent behaves, a role prompt that fails in several repos) belongs "
    "to the repo with is_factory; target 'seed' is only allowed there."
)


def context(
    objections: list[Objection],
    settled: list[StoredLesson],
    repos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """What the agent gets: the objections by short id, the settled rules, the schema.

    ``repos`` (id, name, is_factory of every registered repo) only with ``--all``: then
    every objection names its repo and the agent learns where a rule belongs.
    """
    items: list[dict[str, Any]] = []
    for n, o in enumerate(objections, 1):
        item: dict[str, Any] = {
            "id": f"c{n}",
            "run_id": o.run_id,
            "task_id": o.task_id,
            "source": o.source,
            "agent": o.agent,
            "text": o.text,
        }
        if repos is not None:
            item["repo"] = o.repo
        items.append(item)
    data: dict[str, Any] = {
        "objections": items,
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
    if repos is not None:
        data["targets"]["seed"] = SEED_TARGET
        data["repos"] = repos
        data["repo_rule"] = REPO_RULE
    return data


def repo_problems(
    output: LessonsOutput,
    target_of: Callable[[ProposedLesson], str],
    repos: set[str] | None,
    factory: str,
) -> list[str]:
    """Lessons naming an unknown repo, or the target ``seed`` outside the factory repo."""
    problems: list[str] = []
    for lesson in output.lessons:
        target = target_of(lesson)
        if repos is not None and target not in repos:
            problems.append(
                f"lesson '{lesson.rule}': unknown repo id '{lesson.repo}' "
                f"(repos: {', '.join(sorted(repos))})"
            )
        if lesson.target == "seed" and (not factory or target != factory):
            where = f"the factory repo '{factory}'" if factory else "there is no factory repo"
            problems.append(f"lesson '{lesson.rule}': target 'seed' is only for {where}")
    return problems


def _ask_learner(
    repo: Path,
    payload: dict[str, Any],
    known: set[str],
    repos: set[str] | None = None,
    own: str = "",
    factory: str = "",
) -> LessonsOutput:
    """One call of the agent ``learner`` (one correction for unknown objection ids).

    ``repos`` are the ids a lesson may name with ``--all``; without it every lesson
    belongs to ``own``. The target ``seed`` is for the repo ``factory`` only.
    """
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

        def repos_known(envelope: EnvelopeBase, run: Any) -> list[str]:
            if envelope.status != "success":
                return []
            assert isinstance(envelope, LessonsOutput)
            return repo_problems(envelope, _target_repo(repos, own), repos, factory)

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
                            gates=[ids_known, repos_known],
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


def _target_repo(repos: set[str] | None, own: str) -> Callable[[ProposedLesson], str]:
    """The target repo of a lesson: its ``repo`` with ``--all``, else ``own``."""
    if repos is None:
        return lambda lesson: own
    return lambda lesson: lesson.repo.strip()


def _snippet(o: Objection) -> dict[str, str]:
    text = o.text if len(o.text) <= _SNIPPET_LIMIT else o.text[: _SNIPPET_LIMIT - 1] + "…"
    snippet = {
        "run_id": o.run_id,
        "task_id": o.task_id,
        "source": o.source,
        "phase": o.phase,
        "text": text,
        "created_at": o.created_at,
    }
    if o.repo:
        snippet["repo"] = o.repo
    return snippet


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
    output: LessonsOutput,
    by_id: dict[str, Objection],
    rejected: list[StoredLesson],
    target_of: Callable[[ProposedLesson], str] = lambda lesson: "",
) -> list[dict[str, Any]]:
    """The lessons worth proposing, most occurrences first, as JSON data.

    ``target_of`` gives the repo a lesson belongs to; runs are distinct per repo.
    """
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for lesson in output.lessons:
        found = [by_id[c] for c in dict.fromkeys(lesson.complaints) if c in by_id]
        keys = {o.key for o in found}
        if not found or _blocked(lesson.rule, keys, rejected):
            continue
        if _repeated(lesson, keys, rejected) is not None:
            continue
        lid = lesson_id(lesson.rule)
        target_repo = target_of(lesson)
        entry = merged.setdefault(
            (target_repo, lid),
            {
                "id": lid,
                "rule": lesson.rule.strip(),
                "target": lesson.target,
                "target_detail": lesson.target_detail.strip(),
                "repo": target_repo,
                "objections": [],
            },
        )
        known = {o.key for o in entry["objections"]}
        entry["objections"].extend(o for o in found if o.key not in known)
    result: list[dict[str, Any]] = []
    for entry in merged.values():
        found = entry.pop("objections")
        runs: dict[tuple[str, str], str] = {}
        for o in found:
            runs.setdefault((o.repo, o.run_id), o.task_id)
        if len(runs) < MIN_RUNS:
            continue
        origin = sorted({o.repo for o in found if o.repo})
        result.append(
            {
                **entry,
                "origin": origin,
                "origin_repos": len(origin) or 1,
                "occurrences": len(runs),
                "runs": [
                    {"run_id": r, "task_id": t, **({"repo": repo} if repo else {})}
                    for (repo, r), t in runs.items()
                ],
                "complaints": [_snippet(o) for o in found],
                "keys": [o.key for o in found],
            }
        )
    result.sort(key=lambda lesson: (-lesson["occurrences"], lesson["id"]))
    return result


def _stored(lesson: dict[str, Any]) -> StoredLesson:
    return StoredLesson(
        lesson_id=lesson["id"],
        rule=lesson["rule"],
        target=lesson["target"],
        target_detail=lesson["target_detail"],
        complaints=lesson["keys"],
        runs=list(dict.fromkeys(r["run_id"] for r in lesson["runs"])),
        origin=lesson["origin"],
    )


def scan(repo: Path, since: str | None = None, all_repos: bool = False) -> dict[str, Any]:
    """Collect the objections, let the learner group them, save and return the lessons.

    ``all_repos`` reads the objections of every registered repo and saves each lesson in
    the trace DB of its target repo (the result then has ``all``, ``repos``, ``warnings``).
    """
    if all_repos:
        return _scan_all(repo, since)
    since_iso = parse_since(since)
    db = trace_db(repo)
    objections = collect(db, since_iso)[-_MAX_OBJECTIONS:]
    runs = {(o.repo, o.run_id) for o in objections}
    lessons: list[dict[str, Any]] = []
    repeats: list[dict[str, Any]] = []
    if len(runs) >= MIN_RUNS:
        store = LessonStore(db)
        try:
            rejected = store.settled()
            by_id = {f"c{n}": o for n, o in enumerate(objections, 1)}
            own = _own_id(repo)
            output = _ask_learner(
                repo, context(objections, rejected), set(by_id), None, own, _factory_id()
            )
            lessons = lessons_of(output, by_id, rejected, _target_repo(None, own))
            for lesson in lessons:
                store.save_proposed(_stored(lesson))
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


def _scan_all(repo: Path, since: str | None) -> dict[str, Any]:
    """``scan --all``: objections of every registered repo, lessons into their target repo."""
    from aifactory.learn.sources import _split, collect_all, registered_repos

    since_iso = parse_since(since)
    sources, warnings = registered_repos()
    collected, more = collect_all(since_iso)
    warnings += more
    objections = collected[-_MAX_OBJECTIONS:]
    runs = {(o.repo, o.run_id) for o in objections}
    lessons: list[dict[str, Any]] = []
    repeats: list[dict[str, Any]] = []
    stores: dict[str, LessonStore] = {}
    try:
        if len(runs) >= MIN_RUNS:
            known_ids = {s.id for s in sources}
            settled: list[StoredLesson] = []
            owner: dict[str, str] = {}
            for source in sources:
                try:
                    stores[source.id] = LessonStore(source.trace_db)
                    found_settled = stores[source.id].settled()
                except (sqlite3.Error, OSError) as exc:
                    broken = stores.pop(source.id, None)
                    if broken is not None:
                        broken.close()
                    warnings.append(f"{source.id}: cannot read the lessons: {exc}; skipped")
                    continue
                for stored_lesson in found_settled:
                    keys = [
                        k if _split(k, known_ids)[0] else f"{source.id}:{k}"
                        for k in stored_lesson.complaints
                    ]
                    settled.append(replace(stored_lesson, complaints=keys))
                    owner.setdefault(stored_lesson.lesson_id, source.id)
            factory = _factory_id()
            repos_ctx = [
                {"id": s.id, "name": s.name, "is_factory": s.id == factory}
                for s in sources
                if s.id in stores
            ]
            allowed = set(stores)
            by_id = {f"c{n}": o for n, o in enumerate(objections, 1)}
            output = _ask_learner(
                repo,
                context(objections, settled, repos_ctx),
                set(by_id),
                allowed,
                _own_id(repo),
                factory,
            )
            lessons = lessons_of(output, by_id, settled, _target_repo(allowed, ""))
            for lesson in lessons:
                stores[lesson["repo"]].save_proposed(_stored(lesson))
            for lid, found_repeats in repeats_of(output, by_id, settled).items():
                added = stores[owner[lid]].add_repeats(
                    lid, [o.key for o in found_repeats], [o.run_id for o in found_repeats]
                )
                repeats.append({"id": lid, "added": added, "repo": owner[lid]})
    finally:
        for store in stores.values():
            store.close()
    for lesson in lessons:
        lesson.pop("keys")
    return {
        "since": since_iso,
        "all": True,
        "objections": len(objections),
        "runs": len(runs),
        "repos": len({o.repo for o in objections}),
        "lessons": lessons,
        "repeats": repeats,
        "warnings": warnings,
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


def _run(item: dict[str, Any]) -> str:
    """A run id, prefixed with its repo when it has one (``--all``)."""
    return f"{item['repo']}:{item['run_id']}" if item.get("repo") else str(item["run_id"])


def format_scan(data: dict[str, Any]) -> str:
    """The lessons for the terminal."""
    head = f"{data['objections']} objection(s) in {data['runs']} run(s)"
    if data.get("all"):
        head += f" of {data['repos']} repo(s)"
    if data["since"]:
        head += f" since {data['since']}"
    if not data["lessons"]:
        return f"{head}\nno objection repeats across runs; no lesson to propose"
    lines = [f"{head}: {len(data['lessons'])} lesson(s)"]
    for lesson in data["lessons"]:
        lines += [
            "",
            f"{lesson['id']}  {lesson['occurrences']} run(s)  -> {_where(lesson)}"
            + (
                f"  in {lesson['repo']} (objections from {lesson['origin_repos']} repo(s))"
                if data.get("all")
                else ""
            ),
            f"  {lesson['rule']}",
            "  runs: " + ", ".join(f"{_run(r)} ({r['task_id']})" for r in lesson["runs"]),
        ]
        lines += [f"  - [{c['source']} {_run(c)}] {c['text']}" for c in lesson["complaints"]]
    lines += [
        "",
        "adopt a lesson with 'factory learn accept ID' (a backlog task), "
        "reject one for good with 'factory learn dismiss ID'",
    ]
    return "\n".join(lines)
