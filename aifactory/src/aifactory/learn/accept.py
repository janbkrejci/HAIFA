"""``factory learn accept``: a lesson becomes a backlog task that changes the repo's rules.

The factory never writes a rule itself. Accepting a lesson files a task in the ``LEARN``
step of the repo's project (the step is created when it is missing) with workflow
``build-review``, ``writes`` on the target of the lesson only (``CLAUDE.md``,
``AGENTS.md``, the skill's directories, the role's prompt override or, for ``seed``, the
role's prompt in the library seed) and the rule with its evidence (the objections of the
runs, each with its repo) as its assignment. The task then runs the ordinary way up to a
pull request.

The objections are read with ``sources.resolve_objections``: a key prefixed
``<repo_id>:`` is looked up in the trace DB of that registered repo, one without a prefix
in the repo the lesson is in. The task is filed in the backlog of that repo (the target
repo). The project is ``--project``, else the one of the target repo's tasks whose runs
objected (the most of them; tasks of other repos are ignored), else the only project of
the backlog. The task carries the marker
``<!-- factory: lesson=<id> -->``; accepting the lesson again finds it and files nothing
new. The backlog is written in the main checkout and committed to ``base``; a commit that
fails leaves the task written and is reported as a warning.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aifactory.backlog import (
    Backlog,
    Container,
    Task,
    TaskEditError,
    add_container,
    add_task,
    commit_backlog,
    find_container,
    load_for_edit,
)
from aifactory.backlog.edit import compose_id
from aifactory.home import haifa_home
from aifactory.learn.collect import Objection
from aifactory.learn.scan import trace_db
from aifactory.learn.store import LessonStore, StoredLesson

LEARN_CODE = "LEARN"
LEARN_TITLE = "Lekce z běhů"
LEARN_BODY = (
    "Úpravy pravidel repa (CLAUDE.md, AGENTS.md, skilly, prompty rolí) podle lekcí z "
    "výtek, které se opakovaly v bězích. Tasky sem zakládá `factory learn accept`."
)
WORKFLOW = "build-review"
SEED_AGENTS = "aifactory/src/aifactory/seed/agents"
_TITLE_LIMIT = 90
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def lesson_marker(lesson_id: str) -> str:
    return f"<!-- factory: lesson={lesson_id} -->"


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def _name(detail: str) -> str:
    """The skill or role name of ``target_detail`` when it is a safe path segment."""
    name = detail.strip().strip("/")
    return name if _NAME.match(name) and ".." not in name else ""


def target_writes(target: str, detail: str = "") -> list[str]:
    """The paths the task may change: the rules file of the lesson's target only."""
    name = _name(detail)
    if target == "skill":
        suffix = f"{name}/" if name else ""
        return [f".claude/skills/{suffix}", f".agents/skills/{suffix}"]
    if target == "prompt":
        return [f".factory/prompts/{name}/" if name else ".factory/prompts/"]
    if target == "seed":
        return [f"{SEED_AGENTS}/{name}/" if name else f"{SEED_AGENTS}/"]
    return [target]


def _where(target: str, detail: str) -> str:
    name = _name(detail)
    if target == "skill":
        place = f"`.claude/skills/{name}/`" if name else "`.claude/skills/`"
        return f"skillu {name or 'repa'} ({place})"
    if target == "prompt":
        if not name:
            return "promptu role (`.factory/prompts/`)"
        return f"promptu role {name} (`.factory/prompts/{name}/`)"
    if target == "seed":
        if not name:
            return f"promptu role v semínku knihovny (`{SEED_AGENTS}/`)"
        return f"promptu role {name} v semínku knihovny (`{SEED_AGENTS}/{name}/`)"
    return f"`{target}`"


def _title(rule: str) -> str:
    text = "Lekce: " + " ".join(rule.split())
    return text if len(text) <= _TITLE_LIMIT else text[: _TITLE_LIMIT - 1].rstrip() + "…"


def _repo(o: Objection) -> str:
    return f"repo `{o.repo}`, " if o.repo else ""


def _evidence(lesson: StoredLesson, objections: list[Objection]) -> list[str]:
    if objections:
        return [
            f"- {_repo(o)}běh `{o.run_id}`, task `{o.task_id}` ({o.source}): {o.text}"
            for o in objections
        ]
    return [f"- běh `{run}`" for run in lesson.runs]


def task_body(lesson: StoredLesson, objections: list[Objection]) -> str:
    where = _where(lesson.target, lesson.target_detail)
    runs = len({(o.repo, o.run_id) for o in objections} or set(lesson.runs))
    lines = [
        f"Zapiš do {where} pravidlo z lekce `{lesson.lesson_id}`, kterou factory našla "
        "ve výtkách opakovaných v bězích:",
        "",
        f"> {' '.join(lesson.rule.split())}",
        "",
        "Pravidlo formuluj stručně, zařaď ho tam, kam v souboru patří, a nenech ho "
        "odporovat tomu, co tam už je. Jiné soubory neměň.",
    ]
    if lesson.target == "skill":
        lines.append(
            "Skill uprav v `.claude/skills/` a kopii v `.agents/skills/` srovnej příkazem "
            "`factory skills sync`."
        )
    if lesson.target == "seed":
        lines.append(
            "Po merge se změna do knihovny dostane příkazem `factory library seed` nebo "
            "novou verzí HAIFA."
        )
    lines += [
        "",
        "Hotovo znamená:",
        f"- Pravidlo je v {where}.",
        "",
        "### Důkazy",
        "",
        f"Výtky z {runs} běhů, ze kterých lekce vznikla:",
        "",
        *_evidence(lesson, objections),
        "",
        lesson_marker(lesson.lesson_id),
    ]
    return "\n".join(lines) + "\n"


def _project(backlog: Backlog, tasks: list[str], project_id: str | None) -> Container | None:
    """The project the LEARN step belongs to (``None``: the backlog has no projects)."""
    if project_id is not None:
        return find_container(backlog, project_id.strip())
    counts: Counter[str] = Counter()
    found: dict[str, Container | None] = {}
    for task_id in tasks:
        node = backlog.by_id.get(task_id)
        if isinstance(node, Task):
            parent = node.parent.parent
            key = (parent.id or "") if parent is not None else ""
            counts[key] += 1
            found[key] = parent
    if counts:
        return found[counts.most_common(1)[0][0]]
    levels = backlog.settings.levels
    if len(levels) <= 2:
        return None
    projects = [c for c in backlog.containers if c.level == levels[0]]
    if len(projects) == 1:
        return projects[0]
    names = ", ".join(str(p.id) for p in projects) or "none"
    raise TaskEditError(
        "project_required",
        f"the project cannot be told from the lesson's runs; give --project (projects: {names})",
    )


def _learn_step(project: Container | None, roots: list[Container]) -> Container | None:
    children = project.children if project is not None else roots
    wanted = compose_id(project.id if project is not None else None, LEARN_CODE)
    for child in children:
        if child.id == wanted or _norm(child.title or "") == _norm(LEARN_TITLE):
            return child
    return None


def _existing(backlog: Backlog, lesson: StoredLesson) -> Task | None:
    if lesson.task_id:
        node = backlog.by_id.get(lesson.task_id)
        if isinstance(node, Task):
            return node
    marker = lesson_marker(lesson.lesson_id)
    for node in backlog.by_id.values():
        if isinstance(node, Task) and marker in node.body:
            return node
    return None


def _repo_id(repo: Path) -> str:
    """The registry id of ``repo``, '' when the dashboard does not know it."""
    # aifactory.web imports the learn package
    from aifactory.web.registry import Registry, same_repo

    state, _warnings = Registry(haifa_home()).snapshot()
    return next((e.id for e in state.repos if same_repo(e.path, repo)), "")


def _own_tasks(objections: list[Objection], repo: Path) -> list[str]:
    """The tasks of the objections from ``repo`` itself, in order, without repeats."""
    own = _repo_id(repo)
    return list(dict.fromkeys(o.task_id for o in objections if o.repo == own))


@dataclass
class Accepted:
    lesson: StoredLesson
    task: Task
    existed: bool = False
    step_created: bool = False
    committed: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.lesson.lesson_id,
            "rule": self.lesson.rule,
            "target": self.lesson.target,
            "target_detail": self.lesson.target_detail,
            "state": self.lesson.state,
            "task": {
                "id": self.task.id,
                "title": self.task.title,
                "path": self.task.path,
                "step": self.task.parent.id,
                "workflow": WORKFLOW,
                "writes": target_writes(self.lesson.target, self.lesson.target_detail),
            },
            "existed": self.existed,
            "step_created": self.step_created,
            "committed": self.committed,
        }


def accept(repo: Path, lesson_id: str, project_id: str | None = None) -> Accepted:
    """File the lesson as a task in the project's LEARN step, commit it, mark it accepted."""
    db = trace_db(repo)
    store = LessonStore(db)
    try:
        lesson = store.get(lesson_id.strip())
        backlog = load_for_edit(repo)
        found = _existing(backlog, lesson)
        if found is not None:
            stored = store.accept(lesson.lesson_id, found.id)
            return Accepted(stored, found, existed=True)
        from aifactory.learn.sources import resolve_objections  # imports aifactory.web

        objections = resolve_objections(lesson.complaints, repo)
        tasks = _own_tasks(objections, repo)
        project = _project(backlog, tasks, project_id)
        step = _learn_step(project, backlog.containers)
        step_created = False
        if step is None:
            added = add_container(
                repo,
                project.id if project is not None else None,
                LEARN_CODE,
                LEARN_TITLE,
                body=LEARN_BODY,
            )
            step, step_created = added.container, True
        assert step.id is not None
        backlog = load_for_edit(repo)
        result = add_task(
            repo,
            step.id,
            _title(lesson.rule),
            workflow=WORKFLOW,
            writes=target_writes(lesson.target, lesson.target_detail),
            related=[t for t in tasks if isinstance(backlog.by_id.get(t), Task)] or None,
            body=task_body(lesson, objections),
        )
        outcome = Accepted(lesson, result.task, step_created=step_created)
        try:
            done = commit_backlog(repo, f"{result.task.id}: lekce {lesson.lesson_id}")
            outcome.committed = done.committed
            outcome.warnings += list(done.warnings)
        except TaskEditError as exc:
            outcome.warnings.append(
                f"the task is written but not committed: {exc.code}: {exc.message}"
            )
        outcome.lesson = store.accept(lesson.lesson_id, result.task.id)
        return outcome
    finally:
        store.close()


def format_accepted(outcome: Accepted) -> str:
    data = outcome.to_json()
    task = data["task"]
    verb = "is already" if outcome.existed else "became"
    lines = [
        f"lesson {data['id']} {verb} task {task['id']}: {task['title']}",
        f"  {task['path']}",
        f"  workflow {task['workflow']}, writes {', '.join(task['writes'])}",
    ]
    if not outcome.existed:
        lines.append(
            "  committed to base; run it with 'factory task run'"
            if outcome.committed
            else "  not committed; commit it with 'factory backlog commit'"
        )
    return "\n".join(lines)
