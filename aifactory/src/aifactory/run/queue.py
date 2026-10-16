"""Auto-continue: after a successful run, start the next ready task (D10, Q9).

``run_chain`` runs one task with ``run_task`` and, when the run succeeded and
opened its pull request, picks the next task with ``select_next`` and runs it,
until nothing more can start or a run fails.

A run that failed because its task turned out blocked (an agent reported
``blocked_by`` or a follow-up with ``blocks_task``; ``task.run_blockers``) does not
stop the chain when it would go on after that task (the same rule as after a
success). The blocked task stays unfinished without a PR and is reported as a
``blocked`` skip; the next task is chosen by ``select_next`` with the blockers filed
during that run (``blockers_of``) first, under the same checks as any candidate; when
none of them can start, the usual order follows. Any other failure stops the chain
(``stop == "failed"``), and so does a blocked run that would not go on.

``--auto`` (``auto=True``) holds for the whole chain: it continues after every
successful run and may start any task. Otherwise ``auto_continue: true`` inherited
by a task (task, step or project ``index.md``) decides both ways: the chain continues
only after a task that has it (else ``stop == "disabled"``) and starts only tasks
that have it. So with ``auto_continue: true`` on step S01 only, the chain runs the
tasks of S01 and stops; a task of a step with auto-continue off is never started by
a chain.

The next task is always one of the same project (the root container of the backlog),
also when the kanban's queue holds tasks of other projects. It is taken from the
kanban's manual queue first (``task_queue`` in the
trace DB, ``store.QueuePrefs``), then from the same step, then from the rest of the
same project, both in backlog order, only ``status: todo``. A task excluded from
auto-continue in the kanban is never started by a chain (``excluded``), with
``--auto`` too; started by hand it runs. A task whose
dependencies are only waiting in open (not merged) pull requests is skipped
(``waits_on_pr``) and the chain goes on with what can run; after ``task
approve`` the operator starts the skipped task again. A task without a
workflow (effective ``workflow`` unset or ``null``) is never started: it is
skipped as ``no_workflow`` ("bez workflow") and the chain goes on. A person's task
(``assignee: human``) is skipped as ``human_task``. The chain never
waits: when nothing can start it stops (``stop == "exhausted"``) and reports what it
waits on.

The chain merges only through ``auto_merge: true`` inherited by the finished
task: ``review.automerge.try_auto_merge`` approves and merges its PR when every
condition holds (succeeded run, a review phase whose last review approved, a
clean merge, no red checks). With ``auto_merge`` on the next task is started only
after that merge, from the base that holds it; a PR that was not merged stops
the chain (``stop == "not_merged"``, or ``disabled`` when it would not continue
anyway) and waits for ``factory task approve``. A PR in conflict is first resolved once
(``review.automerge.resolve_and_merge``) and merged when that resolve succeeds.

Parallel runs (``max_parallel_runs`` in ``.factory/config.yaml``, default 1): with 1 the
chain runs one task after another as described above, with no other check. Above 1 the
chain keeps up to that many slots taken in the repository, each run a separate process
(``members.ProcessRunner``, ``factory task run --member``): after the first task it
fills the free slots with the next ready tasks and refills a slot whenever one frees. A
slot (``Slots``) is taken by a task with a live run (of this chain, of other chains, a
single run) and by a task whose PR is open and unmerged (waiting for review); a task
with both counts once. The slot frees when the PR is merged or closed, or when the run
ends without a PR (failed, blocked, stopped). When PRs waiting for review hold the free
slots, the next ready task is skipped as ``no_slot`` (which PRs and runs hold them). The
same counting limits ``start_factory`` (the Overview's "Spustit továrnu") and the
``free_slots`` of the dashboard. A task starts only when its effective ``writes`` do not
overlap (on path prefixes, ``scope.paths_overlap``) the ``writes`` of any running run
(of this chain or not) nor the files changed by any open, unmerged PR
(``gitops.pr_changed_files``; when they cannot be read, the PR's task's ``writes``, else
everything). Otherwise it is skipped as ``writes_overlap`` (which run or PR, which
paths) and the chain tries the next one. A task whose ``writes`` cover the whole repo or
a whole package (``scope.is_wide``, e.g. ``aifactory/``) runs alone: it does not start
while anything runs, and nothing starts while it runs (``exclusive``);
``ChainResult.exclusive`` lists such tasks. A failed run stops the filling (``stop ==
"failed"``); runs already going are left to finish. A blocked run refills its slot as
described above. With ``auto_merge`` the member process merges its own PR (under the
store's merge lock); a PR it did not merge stops the filling as above.

Every chain that goes on has a row in ``task_chains`` (``store.TaskChainRow``): its
runs, the skipped tasks of the last selection with their reasons, the exclusive tasks
and, at the end, the stop. The row is written from the start when the chain can go on
then (``--auto``, or ``auto_continue: true`` on its first task in base), otherwise from
the moment it does go on (auto-continue committed to base during the run). A run that
never goes on is a single run, it gets no row. The dashboard shows the rows
(``/api/chains``). A failure to write a row never affects the chain.

A failed run of a chain that goes on is healed by its kind before the chain stops
(``heal.py``, switched off by ``auto_heal: false``): a ``process_gone`` run is retried
once, a ``nothing_to_do`` run with the agent's reason closes its task without changes
and the chain goes on as after a run that changed nothing; a ``quota`` run has already
continued on the fallback harness inside the run. Every such action is an event of the
chain (``task_chains.events``, ``ChainResult.events``). Any other failure stops the chain
as described above.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import sqlite3
import sys
import tempfile
from collections.abc import Callable, Collection, Iterable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from aifactory.backlog import (
    Backlog,
    Task,
    effective,
    has_workflow,
    is_human,
    iter_tasks,
    load_backlog,
    unmet,
)
from aifactory.backlog.derived import ancestors, descendant_tasks
from aifactory.config import ConfigError
from aifactory.engine.utils import now_iso
from aifactory.providers import GitProvider
from aifactory.run import gitops
from aifactory.run import heal as heal_mod
from aifactory.run import task as task_mod
from aifactory.run.errors import TaskRunError
from aifactory.run.followups import follow_up_marker
from aifactory.run.members import ChainRunner, ProcessRunner
from aifactory.run.scope import effective_task_writes, is_wide, overlaps
from aifactory.run.stack import stack_tip, stacked_on, unmet_ids
from aifactory.run.store import (
    ABORTED,
    CHAIN_FINISHED,
    RUNNING,
    STARTED_AUTO_CONTINUE,
    QueuePrefs,
    TaskChainRow,
    TaskPrRow,
    TaskRunRow,
    TaskRunStore,
)
from aifactory.workflow import CodeRunner

STOP_FAILED, STOP_EXHAUSTED, STOP_DISABLED = "failed", "exhausted", "disabled"
STOP_NOT_MERGED = "not_merged"
STOP_REASONS: tuple[str, ...] = (STOP_FAILED, STOP_EXHAUSTED, STOP_DISABLED, STOP_NOT_MERGED)
SKIP_REASONS: tuple[str, ...] = (
    "human_task",
    "no_workflow",
    "waits_on_pr",
    "blocked",
    "in_review",
    "running",
    "cannot_start",
    "writes_overlap",
    "exclusive",
    "excluded",
    "no_slot",
)
EXCLUDED_DETAIL = "vyloučeno z auto continue v kanbanu"
NO_WORKFLOW_DETAIL = "bez workflow"
HUMAN_TASK_DETAIL = "pro člověka"
_HARD_REASONS = ("unknown", "cancelled", "empty")


@dataclass
class Skip:
    """A task the chain did not start, and why."""

    task_id: str
    reason: str  # one of SKIP_REASONS
    detail: str
    waits_on: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "reason": self.reason,
            "detail": self.detail,
            "waits_on": list(self.waits_on),
        }


@dataclass(frozen=True)
class Slots:
    """Who holds the repository's parallel slots: live runs and PRs waiting for review.

    ``running``: tasks with a live run (or a started chain member). ``in_review``: tasks
    with an open, unmerged PR and no live run. A task counts once, also when it has a
    live run (a resolve, a retry) and an open PR at the same time. A PR that a live run or
    another open PR is stacked on (``stacked_prs``) holds no slot of its own: the stack
    takes one, and the first task stacked on a PR takes over that PR's slot (``yields_to``).
    """

    running: tuple[str, ...] = ()
    in_review: tuple[str, ...] = ()

    @classmethod
    def count(cls, running: Iterable[str], open_pr_tasks: Iterable[str]) -> Slots:
        live = tuple(dict.fromkeys(running))
        review = tuple(t for t in dict.fromkeys(open_pr_tasks) if t not in live)
        return cls(live, review)

    @classmethod
    def of(cls, store: TaskRunStore, members: Iterable[str] = ()) -> Slots:
        """The slots taken in `store`'s repository, plus the started `members` of a chain."""
        runs = store.live_runs()
        prs = store.open_prs()
        live = [*members, *(row.task_id for row in runs)]
        bases = {row.stacked_on for row in runs if row.stacked_on}
        bases |= {base for pr in prs if (base := stacked_on(store, pr.branch))}
        return cls.count(live, (pr.task_id for pr in prs if pr.branch not in bases))

    def yields_to(self, dependencies: Iterable[str]) -> bool:
        """A task stacked on one of these PRs takes over its slot (nobody stacks on it yet)."""
        return any(dep in self.in_review for dep in dependencies)

    @property
    def taken(self) -> int:
        return len(self.running) + len(self.in_review)

    def free(self, limit: int) -> int:
        return max(0, limit - self.taken)

    def skip(self, task_id: str) -> Skip:
        """`task_id` did not start: no free slot, PRs waiting for review hold some (``no_slot``)."""
        detail = f"žádný volný slot: PR čekající na review ({', '.join(self.in_review)})"
        if self.running:
            detail += f", běží ({', '.join(self.running)})"
        return Skip(task_id, "no_slot", detail, list(self.in_review))


@dataclass
class Selection:
    next: Task | None
    skipped: list[Skip]


def auto_continue_enabled(task: Task) -> bool:
    return effective(task).get("auto_continue") is True


def auto_merge_enabled(task: Task) -> bool:
    """``auto_merge: true`` inherited by `task` (task, step or project)."""
    return effective(task).get("auto_merge") is True


def candidates(after: Task, order: Sequence[str] = ()) -> list[Task]:
    """`todo` tasks of `after`'s project: first those in `order` (the kanban's manual
    queue), then the rest of `after`'s step, then the rest of the project, in backlog order.

    The manual order wins over "same step first"; ids in `order` outside the project
    (or not `todo`) are ignored.
    """
    step = after.parent
    project = ancestors(after)[-1]
    pool: list[Task] = []
    seen = {after.id}
    for task in [*descendant_tasks(step), *descendant_tasks(project)]:
        if task.id in seen:
            continue
        seen.add(task.id)
        if task.status == "todo":
            pool.append(task)
    rank = {task_id: i for i, task_id in enumerate(order)}
    ranked = sorted((t for t in pool if t.id in rank), key=lambda t: rank[t.id])
    return [*ranked, *(t for t in pool if t.id not in rank)]


def select_next(
    backlog: Backlog,
    after: Task,
    *,
    open_pr: Callable[[str], TaskPrRow | None],
    running: Callable[[str], TaskRunRow | None],
    exclude: Collection[str] = frozenset(),
    conflict: Callable[[Task], Skip | None] | None = None,
    require_auto_continue: bool = False,
    prefs: QueuePrefs | None = None,
    prefer: Sequence[str] = (),
    stack: Stacker | None = None,
) -> Selection:
    """The first startable candidate after `after`, and every candidate that was skipped.

    ``conflict`` (parallel chains, ``Occupancy``) is asked only about a candidate that
    could start otherwise, until one is chosen; a ``Skip`` it returns is recorded and the
    next candidate is tried. With ``require_auto_continue`` (a chain without ``--auto``)
    a candidate without ``auto_continue: true`` is left out, not reported as skipped.
    ``prefs`` (the kanban's queue, ``TaskRunStore.queue_prefs``) orders the candidates
    and excludes tasks: an excluded task is skipped as ``excluded``, with ``--auto`` too.
    ``prefer`` (the blockers of a blocked `after`, ``blockers_of``) goes before the
    kanban's queue; like the queue, ids outside `after`'s project are ignored.
    """
    prefs = prefs or QueuePrefs()
    return _select(
        candidates(after, [*prefer, *prefs.order]),
        backlog,
        open_pr=open_pr,
        running=running,
        exclude=exclude,
        conflict=conflict,
        require_auto_continue=require_auto_continue,
        prefs=prefs,
        stack=stack,
    )


def blockers_of(backlog: Backlog, blocked: Task, ids: Sequence[str]) -> list[str]:
    """Of `ids` (``task.run_blockers``), the follow-ups the factory filed for `blocked`.

    Only tasks of `blocked`'s project that carry its follow-up marker count: the blockers
    that came up during its run. Other ids (an existing task in ``blocked_by``, a
    placeholder of a follow-up that was not filed) are left to the usual selection.
    """
    project = ancestors(blocked)[-1]
    marker = follow_up_marker(blocked.id)
    found: list[str] = []
    for task_id in ids:
        node = backlog.by_id.get(task_id)
        if (
            isinstance(node, Task)
            and marker in node.body
            and ancestors(node)[-1] is project
            and task_id not in found
        ):
            found.append(task_id)
    return found


def _blocked_skip(task: Task, ids: Sequence[str]) -> Skip:
    return Skip(task.id, "blocked", f"během běhu zablokován: {', '.join(ids)}", list(ids))


def repo_candidates(backlog: Backlog, order: Sequence[str] = ()) -> list[Task]:
    """Every `todo` task of the backlog: first those in `order` (the kanban's manual
    queue), then the rest in backlog order (project by project)."""
    pool = [task for task in iter_tasks(backlog) if task.status == "todo"]
    rank = {task_id: i for i, task_id in enumerate(order)}
    ranked = sorted((t for t in pool if t.id in rank), key=lambda t: rank[t.id])
    return [*ranked, *(t for t in pool if t.id not in rank)]


def select_ready(
    backlog: Backlog,
    *,
    open_pr: Callable[[str], TaskPrRow | None],
    running: Callable[[str], TaskRunRow | None],
    exclude: Collection[str] = frozenset(),
    conflict: Callable[[Task], Skip | None] | None = None,
    prefs: QueuePrefs | None = None,
    stack: Stacker | None = None,
) -> Selection:
    """The first startable task of the whole backlog (the Overview's "Spustit továrnu").

    The same checks as ``select_next`` over ``repo_candidates``; ``auto_continue`` is not
    required (a start by hand), a task excluded in the kanban is skipped as ``excluded``.
    """
    prefs = prefs or QueuePrefs()
    return _select(
        repo_candidates(backlog, prefs.order),
        backlog,
        open_pr=open_pr,
        running=running,
        exclude=exclude,
        conflict=conflict,
        require_auto_continue=False,
        prefs=prefs,
        stack=stack,
    )


def _select(
    pool: Sequence[Task],
    backlog: Backlog,
    *,
    open_pr: Callable[[str], TaskPrRow | None],
    running: Callable[[str], TaskRunRow | None],
    exclude: Collection[str],
    conflict: Callable[[Task], Skip | None] | None,
    require_auto_continue: bool,
    prefs: QueuePrefs,
    stack: Stacker | None = None,
) -> Selection:
    """The first startable task of `pool` and every task of it that was skipped.

    With `stack` (``stacked_prs``) a task whose dependencies all wait in open PRs that
    one branch holds starts stacked on it instead of waiting (``waits_on_pr``).
    """
    chosen: Task | None = None
    skipped: list[Skip] = []
    for task in pool:
        if task.id in exclude:
            continue
        if require_auto_continue and not auto_continue_enabled(task):
            continue
        if task.id in prefs.excluded:
            skipped.append(Skip(task.id, "excluded", EXCLUDED_DETAIL))
            continue
        if is_human(task):
            skipped.append(Skip(task.id, "human_task", HUMAN_TASK_DETAIL))
            continue
        if not has_workflow(task):
            skipped.append(Skip(task.id, "no_workflow", NO_WORKFLOW_DETAIL))
            continue
        busy = running(task.id)
        if busy is not None:
            skipped.append(Skip(task.id, "running", f"run {busy.run_id} on {busy.branch}"))
            continue
        own = open_pr(task.id)
        if own is not None:
            skipped.append(Skip(task.id, "in_review", f"PR {own.url}"))
            continue
        missing = unmet(backlog, task)
        if missing:
            waits: list[str] = []
            hard = False
            for u in missing:
                ids = list(u.missing) if u.missing else [u.id]
                hard = hard or u.reason in _HARD_REASONS
                waits.extend(i for i in ids if i not in waits)
            prs = {i: open_pr(i) for i in waits}
            found = {i: pr for i, pr in prs.items() if pr is not None}
            stackable = not hard and len(found) == len(prs) and stack is not None and stack(found)
            if not stackable:
                if hard or any(pr is None for pr in prs.values()):
                    detail = ", ".join(
                        f"{u.id} ({u.reason}"
                        + (f": {', '.join(u.missing)}" if u.missing and u.missing != [u.id] else "")
                        + ")"
                        for u in missing
                    )
                    skipped.append(Skip(task.id, "blocked", detail, waits))
                else:
                    detail = ", ".join(f"{i} (PR {pr.url})" for i, pr in prs.items() if pr)
                    skipped.append(Skip(task.id, "waits_on_pr", detail, waits))
                continue
        if chosen is None:
            clash = conflict(task) if conflict is not None else None
            if clash is not None:
                skipped.append(clash)
                continue
            chosen = task
    return Selection(chosen, skipped)


_MAX_PATHS = 5
UNKNOWN_FILES = "soubory PR nelze zjistit"


def _paths_text(paths: list[str]) -> str:
    shown = ", ".join(paths[:_MAX_PATHS])
    return shown + (", …" if len(paths) > _MAX_PATHS else "")


def _writes_text(writes: Collection[str]) -> str:
    return ", ".join(w or "(celé repo)" for w in writes)


@dataclass
class Occupancy:
    """What runs and what waits in open PRs: the ``conflict`` of a parallel chain's selection.

    ``runs``: every live run with its task's effective ``writes`` (``("",)``, the whole
    repo, when the task is not in the backlog). ``prs``: every open PR with the files it
    changes (``None`` when unknown: then its task's ``writes``, else the whole repo).
    """

    runs: list[tuple[TaskRunRow, tuple[str, ...]]]
    prs: list[tuple[TaskPrRow, list[str], bool]]  # (pr, paths, files known)
    root: Path | None = None
    # the backlog the selection reads: a task never waits for the PRs of its dependencies,
    # it waits for them as dependencies or stacks on them (``stacked_prs``)
    backlog: Backlog | None = None

    @classmethod
    def build(
        cls,
        backlog: Backlog,
        store: TaskRunStore,
        root: Path,
        pr_files: Callable[[TaskPrRow], list[str] | None],
    ) -> Occupancy:
        def writes_of(task_id: str) -> tuple[str, ...] | None:
            node = backlog.by_id.get(task_id)
            if not isinstance(node, Task):
                return None
            return effective_task_writes(node) or None

        runs = [(row, writes_of(row.task_id) or ("",)) for row in store.live_runs()]
        prs: list[tuple[TaskPrRow, list[str], bool]] = []
        for pr in store.open_prs():
            files = pr_files(pr)
            if files is not None:
                prs.append((pr, files, True))
            else:
                prs.append((pr, list(writes_of(pr.task_id) or ("",)), False))
        return cls(runs, prs, root, backlog)

    def _wide(self, writes: Collection[str]) -> list[str]:
        return is_wide(writes, self.root)

    def __call__(self, task: Task) -> Skip | None:
        writes = effective_task_writes(task)
        if not writes:
            return None  # run_task refuses it (no_writes): reported as cannot_start
        wide = self._wide(writes)
        if wide and self.runs:
            running = ", ".join(f"{row.task_id} {row.run_id}" for row, _ in self.runs)
            return Skip(
                task.id,
                "exclusive",
                f"writes {_writes_text(wide)} pokrývají celý balíček/repo; běží jen samostatně "
                f"(běží: {running})",
                [row.task_id for row, _ in self.runs],
            )
        for row, run_writes in self.runs:
            run_wide = self._wide(run_writes)
            if run_wide:
                return Skip(
                    task.id,
                    "exclusive",
                    f"běží {row.task_id} ({row.run_id}) se širokými writes "
                    f"{_writes_text(run_wide)}; souběžně nic jiného",
                    [row.task_id],
                )
        details: list[str] = []
        waits: list[str] = []
        for row, run_writes in self.runs:
            hit = overlaps(writes, run_writes)
            if hit:
                details.append(f"běh {row.run_id} ({row.task_id}): {_paths_text(hit)}")
                waits.append(row.task_id)
        deps = set(unmet_ids(self.backlog, task) or ()) if self.backlog is not None else set()
        for pr, paths, known in self.prs:
            if pr.task_id == task.id or pr.task_id in deps:
                continue
            hit = overlaps(writes, paths)
            if hit:
                text = _paths_text(hit) if known else f"{UNKNOWN_FILES}, writes {_paths_text(hit)}"
                details.append(f"PR {pr.url} ({pr.task_id}): {text}")
                if pr.task_id not in waits:
                    waits.append(pr.task_id)
        if details:
            return Skip(task.id, "writes_overlap", "; ".join(details), waits)
        return None


@dataclass
class ChainResult:
    runs: list[task_mod.TaskRunResult]  # in start order: runs[0] is the first task
    stop: str
    waiting: list[Skip] = field(default_factory=list)
    max_parallel: int = 1
    exclusive: list[str] = field(default_factory=list)  # tasks that ran alone (wide writes)
    chain_id: str | None = None
    # the chain's automatic actions after a failure (``heal.HealEvent.to_json()``)
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.ok or r.closed_by_heal for r in self.runs)

    def to_json(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "runs": [
                {
                    "ok": r.ok,
                    "run": r.run.to_json(),
                    "pr": r.pr.to_json() if r.pr is not None else None,
                    "pr_error": r.pr_error,
                    "auto_merge": r.auto_merge.to_json() if r.auto_merge is not None else None,
                    "follow_ups": r.follow_ups.to_json() if r.follow_ups is not None else None,
                }
                for r in self.runs
            ],
            "stop": self.stop,
            "waiting": [s.to_json() for s in self.waiting],
            "max_parallel_runs": self.max_parallel,
            "exclusive": list(self.exclusive),
            "chain_id": self.chain_id,
            "events": list(self.events),
        }


def _base_backlog(repo: Path, dest: Path) -> Backlog:
    main = gitops.main_root(repo)
    rc = task_mod._load(main)
    settings = rc.config.settings
    try:
        gitops.extract_backlog(main, rc.commit, settings.backlog_patterns, dest)
    except (OSError, RuntimeError) as exc:
        raise TaskRunError("invalid_config", f"cannot read the backlog: {exc}") from exc
    return load_backlog(dest, settings)


@contextlib.contextmanager
def _fresh_backlog(repo: Path) -> Iterator[Backlog]:
    with tempfile.TemporaryDirectory(prefix="factory-chain-") as tmp:
        yield _base_backlog(repo, Path(tmp))


class _ChainRecord:
    """The chain's row in ``task_chains``; a failing write only warns on stderr.

    ``enabled=False`` (a run that cannot go on) never writes a row.
    """

    def __init__(
        self, db: Path | None, task_id: str, max_parallel: int, *, enabled: bool = True
    ) -> None:
        self.db = db
        self.task_id = task_id
        self.max_parallel = max_parallel
        self.enabled = enabled
        self.chain_id = secrets.token_hex(4)
        self.started = False
        self.events: list[dict[str, Any]] = []

    def _write(self, action: Callable[[TaskRunStore], None]) -> None:
        if self.db is None:
            return
        try:
            store = TaskRunStore(self.db)
            try:
                action(store)
            finally:
                store.close()
        except (sqlite3.Error, TaskRunError, OSError) as exc:
            print(f"warning: chain {self.chain_id}: cannot record: {exc}", file=sys.stderr)

    def go_on(self, db: Path | None = None) -> None:
        """The chain goes on after all (auto-continue switched on meanwhile): write its row."""
        self.enabled = True
        self.start(db)

    def start(self, db: Path | None = None) -> None:
        if self.started or not self.enabled:
            return
        if db is not None:
            self.db = db
        now = str(now_iso())
        row = TaskChainRow(
            chain_id=self.chain_id,
            task_id=self.task_id,
            pid=os.getpid(),
            max_parallel=self.max_parallel,
            state=RUNNING,
            started_at=now,
            updated_at=now,
            events=json.dumps(self.events, ensure_ascii=False),
        )
        self._write(lambda store: store.start_chain(row))
        self.started = self.db is not None

    def update(self, **fields: object) -> None:
        if self.started:
            self._write(lambda store: store.update_chain(self.chain_id, **fields))  # type: ignore[arg-type]

    def event(self, event: heal_mod.HealEvent) -> None:
        """Record an automatic action (once per run, action and time)."""
        data = event.to_json()
        key = (data["run_id"], data["action"], data["at"])
        if any((e["run_id"], e["action"], e["at"]) == key for e in self.events):
            return
        self.events.append(data)
        self.update(events=list(self.events))

    def finish(self, stop: str, runs: list[str], skipped: list[Skip], exclusive: list[str]) -> None:
        self.update(
            run_ids=runs,
            skipped=[s.to_json() for s in skipped],
            exclusive=exclusive,
            state=CHAIN_FINISHED,
            stop=stop,
        )

    def abort(self) -> None:
        if self.started:
            self._write(lambda store: store.delete_chain(self.chain_id))


def _trace_db(repo: Path) -> Path | None:
    try:
        main = gitops.main_root(repo)
        return task_mod._load(main).local.trace_db_path(main)
    except (TaskRunError, ConfigError, OSError):
        return None


def _first_task(repo: Path, task_id: str) -> Task | None:
    """`task_id` in the backlog of base; None when it is not there or cannot be read."""
    try:
        with _fresh_backlog(repo) as backlog:
            node = backlog.by_id.get(task_id)
    except (TaskRunError, ConfigError, OSError):
        return None  # the run itself reports the problem
    return node if isinstance(node, Task) else None


Stacker = Callable[[dict[str, TaskPrRow]], bool]
"""Whether a task can stack on these open PRs of its dependencies (``run/stack.py``)."""


def stacker(main: Path) -> Stacker | None:
    """With ``stacked_prs`` in the config: the ``stack`` check of the selection."""
    try:
        enabled = task_mod._load(main).config.settings.stacked_prs
    except (TaskRunError, ConfigError, OSError):
        return None
    if not enabled:
        return None
    return lambda prs: stack_tip(main, prs) is not None


WAITS_FOR_STACK = "waits_for_stack"
"""A stacked PR's auto-merge waits for the PR it builds on (``review/stack.py``)."""


def _waits_for_stack(merge: object) -> bool:
    """A stacked PR waits for its dependency's merge: the chain goes on (``run/stack.py``)."""
    return getattr(merge, "code", None) == WAITS_FOR_STACK


def _max_parallel(repo: Path) -> int:
    try:
        return task_mod._load(gitops.main_root(repo)).config.settings.max_parallel_runs
    except (TaskRunError, ConfigError, OSError):
        return 1  # the run itself reports the problem


def _pr_files_default(main: Path) -> Callable[[TaskPrRow], list[str] | None]:
    """The files an open PR changes, read in the main checkout (``gitops.pr_changed_files``)."""

    def files_of(pr: TaskPrRow) -> list[str] | None:
        return gitops.pr_changed_files(main, pr.base, pr.branch, pr.base_sha)

    return files_of


@dataclass
class FactoryStart:
    """What ``start_factory`` started: claimed rows, or task ids whose claim was not seen yet."""

    max_parallel: int
    running: int  # tasks with a live run before the start
    free_slots: int  # max(0, max_parallel - running - len(in_review))
    in_review: list[str] = field(default_factory=list)  # tasks holding a slot with an open PR
    started: list[TaskRunRow | str] = field(default_factory=list)
    skipped: list[Skip] = field(default_factory=list)

    def to_json(self) -> dict[str, object]:
        return {
            "max_parallel_runs": self.max_parallel,
            "running": self.running,
            "in_review": list(self.in_review),
            "free_slots": self.free_slots,
            "started": [
                {"task_id": s, "run_id": None}
                if isinstance(s, str)
                else {"task_id": s.task_id, "run_id": s.run_id}
                for s in self.started
            ],
            "skipped": [s.to_json() for s in self.skipped],
        }


@dataclass
class _Pending:
    """A ``conflict`` that adds the started but not yet claimed tasks to an ``Occupancy``."""

    occupancy: Occupancy
    pending: list[tuple[str, tuple[str, ...]]]

    def __call__(self, task: Task) -> Skip | None:
        clash = self.occupancy(task)
        if clash is not None:
            return clash
        writes = effective_task_writes(task)
        if not writes:
            return None
        root = self.occupancy.root
        for task_id, other in self.pending:
            if is_wide(writes, root) or is_wide(other, root):
                return Skip(
                    task.id,
                    "exclusive",
                    f"spouští se {task_id}; široké writes běží jen samostatně",
                    [task_id],
                )
            hit = overlaps(writes, other)
            if hit:
                return Skip(
                    task.id,
                    "writes_overlap",
                    f"spouští se {task_id}: {_paths_text(hit)}",
                    [task_id],
                )
        return None


def start_factory(
    repo: Path,
    start: Callable[[str], TaskRunRow | None],
    *,
    max_parallel: int | None = None,
    pr_files: Callable[[TaskPrRow], list[str] | None] | None = None,
) -> FactoryStart:
    """Start ready tasks of the whole repository, as many as there are free parallel slots.

    The Overview's "Spustit továrnu": the tasks are chosen like auto-continue does
    (``select_ready``: the kanban's queue first, excluded tasks, dependencies, open PRs
    and write collisions with running runs, open PRs and the tasks started just before)
    and each is started with `start` (``factory task run ID`` as a separate process; it
    then continues according to its inherited ``auto_continue``). At most
    ``max_parallel_runs`` minus the taken slots (``Slots``: tasks with a live run or an
    open PR waiting for review, each once) are started. When PRs waiting for review hold
    a slot the next ready task that found none is skipped as ``no_slot``. A task `start`
    refuses with a ``TaskRunError`` is skipped as ``cannot_start`` and the next one is
    tried. A missing trace DB is not created here.
    """
    main = gitops.main_root(repo)
    limit = max_parallel if max_parallel is not None else _max_parallel(repo)
    db = task_mod._load(main).local.trace_db_path(main)
    files_of = pr_files if pr_files is not None else _pr_files_default(main)

    def taken() -> Slots:
        if not db.is_file():
            return Slots()
        store = TaskRunStore(db)
        try:
            return Slots.of(store)
        finally:
            store.close()

    slots = taken()
    result = FactoryStart(
        limit, len(slots.running), slots.free(limit), in_review=list(slots.in_review)
    )
    exclude: set[str] = set()
    pending: list[tuple[str, tuple[str, ...]]] = []
    start_skips: list[Skip] = []
    last_skips: list[Skip] = []
    while True:
        full = len(result.started) >= result.free_slots
        if full and not slots.in_review:
            break
        deps: list[str] = []
        with _fresh_backlog(repo) as backlog:
            if db.is_file():
                store = TaskRunStore(db)
                try:
                    occupancy = Occupancy.build(backlog, store, main, files_of)
                    selection = select_ready(
                        backlog,
                        open_pr=store.open_pr,
                        running=store.running,
                        exclude=exclude,
                        conflict=_Pending(occupancy, pending),
                        prefs=store.queue_prefs(),
                        stack=stacker(main),
                    )
                    if selection.next is not None:
                        deps = unmet_ids(backlog, selection.next) or []
                finally:
                    store.close()
            else:
                selection = select_ready(
                    backlog,
                    open_pr=lambda _: None,
                    running=lambda _: None,
                    exclude=exclude,
                    conflict=_Pending(Occupancy([], [], main), pending),
                )
        last_skips = selection.skipped
        nxt = selection.next
        if nxt is None:
            break
        if full and not slots.yields_to(deps):
            # PRs waiting for review hold the slot this task would take
            last_skips = [*last_skips, slots.skip(nxt.id)]
            break
        if full:  # stacked on a PR: it takes that PR's slot, once
            slots = replace(slots, in_review=tuple(t for t in slots.in_review if t not in deps))
        exclude.add(nxt.id)
        try:
            row = start(nxt.id)
        except TaskRunError as exc:
            start_skips.append(Skip(nxt.id, "cannot_start", f"{exc.code}: {exc.message}"))
            continue
        if row is None:
            pending.append((nxt.id, effective_task_writes(nxt) or ("",)))
            result.started.append(nxt.id)
        else:
            result.started.append(row)
    result.skipped = [*start_skips, *last_skips]
    return result


def _failed(result: task_mod.TaskRunResult) -> bool:
    """Whether the chain cannot go on after `result` as after a success."""
    if result.closed_by_heal:
        return False
    return not result.ok or (result.pr is None and not result.done_without_pr)


def _note_switch(record: _ChainRecord, result: task_mod.TaskRunResult, since: str) -> None:
    """Record the automatic quota fallback of `result` (started during the chain)."""
    event = heal_mod.switch_event(result, since)
    if event is not None:
        record.event(event)


def _heal_in_chain(
    repo: Path,
    result: task_mod.TaskRunResult,
    *,
    auto: bool,
    record: _ChainRecord,
    healed: set[str],
    since: str,
    code: CodeRunner | None,
    provider: GitProvider | None,
) -> tuple[task_mod.TaskRunResult, bool]:
    """The newest result of the failed `result` after healing it, and whether to go on.

    Only a chain that would go on after the task heals it, each run once.
    """
    if result.run.run_id in healed:
        return result, False
    with _fresh_backlog(repo) as backlog:
        task = backlog.by_id.get(result.run.task_id)
    if not isinstance(task, Task) or not (auto or auto_continue_enabled(task)):
        return result, False
    healed.add(result.run.run_id)
    healing = heal_mod.heal(repo, result, task, code=code, provider=provider)
    if healing is None:
        return result, False
    if not record.started:
        record.go_on(result.trace_db)
    record.event(healing.event)
    newest = healing.result if healing.result is not None else result
    _note_switch(record, newest, since)
    return newest, healing.goes_on


def run_chain(
    repo: Path,
    task_id: str,
    *,
    auto: bool = False,
    note: str | None = None,
    force: bool = False,
    code: CodeRunner | None = None,
    provider: GitProvider | None = None,
    max_parallel: int | None = None,
    runner: ChainRunner | None = None,
    pr_files: Callable[[TaskPrRow], list[str] | None] | None = None,
    agents_override: dict[str, str] | None = None,
    first_run: Callable[[], task_mod.TaskRunResult] | None = None,
) -> ChainResult:
    """Run `task_id`, then (auto-continue) the next ready tasks.

    ``first_run`` replaces the first ``run_task`` of `task_id` (``retry_chain``: the
    retry's attempt); it runs in this process, also in a parallel chain.

    ``agents_override`` (``task run --harness/--model/--thinking``) applies to the first
    run only; the rest of the chain runs on the roster.

    A finished task with ``auto_merge`` has its PR merged by ``try_auto_merge``
    before anything else starts; nothing else is ever approved or merged.
    A `TaskRunError` of the first run propagates; a later task that cannot start
    is reported as a ``cannot_start`` skip and the chain tries the next one.

    ``max_parallel`` (default: ``max_parallel_runs`` of the config) above 1 runs the
    chain in parallel through `runner` (default ``ProcessRunner``); `pr_files` gives the
    files of an open PR (default ``gitops.pr_changed_files`` in the main checkout).
    `code` and `provider` apply to the sequential chain only.
    """
    limit = max_parallel if max_parallel is not None else _max_parallel(repo)
    if limit <= 1:
        return _run_sequential(
            repo,
            task_id,
            auto=auto,
            note=note,
            force=force,
            code=code,
            provider=provider,
            agents_override=agents_override,
            first_run=first_run,
        )
    return _run_parallel(
        repo,
        task_id,
        auto=auto,
        note=note,
        force=force,
        max_parallel=limit,
        runner=runner if runner is not None else ProcessRunner(repo),
        pr_files=pr_files,
        agents_override=agents_override,
        first_run=first_run,
        code=code,
    )


def retry_chain(
    repo: Path,
    task_id: str,
    *,
    run_id: str | None = None,
    note: str | None = None,
    from_phase: str | None = None,
    auto: bool = False,
    code: CodeRunner | None = None,
    provider: GitProvider | None = None,
    max_parallel: int | None = None,
    runner: ChainRunner | None = None,
    pr_files: Callable[[TaskPrRow], list[str] | None] | None = None,
    agents_override: dict[str, str] | None = None,
) -> ChainResult:
    """``factory task retry``: the retry of a run, then auto-merge and auto-continue.

    ``agents_override`` continues the run on another harness (``retry_run``).

    After a successful attempt the chain goes on exactly as after ``run_chain``: the
    PR is merged with ``auto_merge`` and the next ready task starts with ``--auto``
    (`auto`) or ``auto_continue``, in the kanban's queue order. A `TaskRunError` of
    the retry propagates.
    """
    # Local import and module attribute: a patched `retry_run` applies here too.
    from aifactory.run import retry as retry_mod

    def first() -> task_mod.TaskRunResult:
        return retry_mod.retry_run(
            repo,
            task_id,
            run_id=run_id,
            note=note,
            from_phase=from_phase,
            code=code,
            provider=provider,
            agents_override=agents_override,
        )

    return run_chain(
        repo,
        task_id,
        auto=auto,
        code=code,
        provider=provider,
        max_parallel=max_parallel,
        runner=runner,
        pr_files=pr_files,
        first_run=first,
    )


def member_auto_merge(
    repo: Path, result: task_mod.TaskRunResult, *, code: CodeRunner | None = None
) -> task_mod.TaskRunResult:
    """Auto-merge of a finished run of a parallel chain, under the merge lock.

    A PR in conflict is resolved once (``resolve_and_merge``) outside the lock and merged
    under it, as the sequential chain does; the resolve run is ``result.resolve_run``.
    Nothing happens without ``auto_merge: true`` on the task in base.
    """
    if not result.ok or result.pr is None:
        return result
    with _fresh_backlog(repo) as backlog:
        task = backlog.by_id.get(result.run.task_id)
        if not isinstance(task, Task) or not auto_merge_enabled(task):
            return result
        # Local import: aifactory.review imports aifactory.run.
        from aifactory.review.automerge import resolve_and_merge, try_auto_merge

        store = TaskRunStore(result.trace_db)
        try:
            with store.merge_lock():
                result.auto_merge = try_auto_merge(repo, result, task, code=code)
            if not result.auto_merge.merged and result.auto_merge.code == "conflict":
                result.resolve_run, result.auto_merge = resolve_and_merge(
                    repo, result, task, code=code, merge_lock=store.merge_lock
                )
        finally:
            store.close()
    return result


def _run_sequential(
    repo: Path,
    task_id: str,
    *,
    auto: bool,
    note: str | None,
    force: bool,
    code: CodeRunner | None,
    provider: GitProvider | None,
    agents_override: dict[str, str] | None = None,
    first_run: Callable[[], task_mod.TaskRunResult] | None = None,
) -> ChainResult:
    """One run after another (``max_parallel_runs: 1``)."""
    db = _trace_db(repo)
    first = _first_task(repo, task_id)
    goes_on = auto or (first is not None and auto_continue_enabled(first))
    record = _ChainRecord(db, task_id, 1, enabled=goes_on)
    if db is not None and db.is_file():
        record.start()
    try:
        chain = _sequential(
            repo,
            task_id,
            auto=auto,
            note=note,
            force=force,
            code=code,
            provider=provider,
            record=record,
            agents_override=agents_override,
            first_run=first_run,
        )
    except TaskRunError:
        record.abort()
        raise
    except BaseException:
        record.update(state=ABORTED)
        raise
    chain.chain_id = record.chain_id if record.started else None
    chain.events = list(record.events)
    record.finish(chain.stop, [r.run.run_id for r in chain.runs], chain.waiting, [])
    return chain


def _sequential(
    repo: Path,
    task_id: str,
    *,
    auto: bool,
    note: str | None,
    force: bool,
    code: CodeRunner | None,
    provider: GitProvider | None,
    record: _ChainRecord,
    agents_override: dict[str, str] | None = None,
    first_run: Callable[[], task_mod.TaskRunResult] | None = None,
) -> ChainResult:
    since = str(now_iso())
    if first_run is not None:
        first = first_run()
    else:
        # Through the module attribute, so a patched `run_task` applies to the whole chain.
        first = task_mod.run_task(
            repo,
            task_id,
            note=note,
            force=force,
            code=code,
            provider=provider,
            agents_override=agents_override,
        )
    runs = [first]
    record.start(first.trace_db)
    record.update(run_ids=[first.run.run_id])
    _note_switch(record, first, since)
    exclude = {task_id}
    start_skips: list[Skip] = []
    healed: set[str] = set()
    last = first
    while True:
        blocked: list[str] | None = None
        if _failed(last):
            blocked = task_mod.run_blockers(last.run)
            if blocked is None:
                fixed, goes_on = _heal_in_chain(
                    repo,
                    last,
                    auto=auto,
                    record=record,
                    healed=healed,
                    since=since,
                    code=code,
                    provider=provider,
                )
                runs[runs.index(last)] = fixed
                if not goes_on:
                    return ChainResult(runs, STOP_FAILED)
                record.update(run_ids=[r.run.run_id for r in runs])
                last = fixed
                continue
        prefer: list[str] = []
        with tempfile.TemporaryDirectory(prefix="factory-chain-") as tmp:
            backlog = _base_backlog(repo, Path(tmp))
            after = backlog.by_id.get(last.run.task_id)
            if not isinstance(after, Task):
                return ChainResult(runs, STOP_FAILED if blocked is not None else STOP_DISABLED)
            cont = auto or auto_continue_enabled(after)
            if blocked is not None:
                # blocked during its run: no PR, no merge; on with its blockers first
                if not cont:
                    return ChainResult(runs, STOP_FAILED)
                prefer = blockers_of(backlog, after, blocked)
                start_skips.append(_blocked_skip(after, blocked))
            if cont and not record.started:
                record.go_on(last.trace_db)
                record.update(run_ids=[r.run.run_id for r in runs])
            merged = False
            if (
                blocked is None
                and not last.closed_by_heal
                and last.auto_merge is None
                and auto_merge_enabled(after)
            ):
                # Local import: aifactory.review imports aifactory.run.
                from aifactory.review.automerge import try_auto_merge

                last.auto_merge = try_auto_merge(repo, last, after, provider=provider, code=code)
                if not last.auto_merge.merged and last.auto_merge.code == "conflict":
                    # one auto-resolve (whole suite, reviewed resolution), then merge
                    from aifactory.review.automerge import resolve_and_merge

                    resolved, last.auto_merge = resolve_and_merge(
                        repo, last, after, provider=provider, code=code
                    )
                    if resolved is not None:
                        runs.append(resolved)
                if not last.auto_merge.merged and not _waits_for_stack(last.auto_merge):
                    return ChainResult(runs, STOP_NOT_MERGED if cont else STOP_DISABLED)
                merged = last.auto_merge.merged
            if not cont:
                return ChainResult(runs, STOP_DISABLED)
            if merged:  # base moved: the next task starts from the merged change
                fresh = Path(tmp) / "merged"
                fresh.mkdir()
                backlog = _base_backlog(repo, fresh)
                found = backlog.by_id.get(last.run.task_id)
                if not isinstance(found, Task):
                    return ChainResult(runs, STOP_DISABLED)
                after = found
            store = TaskRunStore(last.trace_db)
            try:
                selection = select_next(
                    backlog,
                    after,
                    open_pr=store.open_pr,
                    running=store.running,
                    exclude=exclude,
                    require_auto_continue=not auto,
                    prefs=store.queue_prefs(),
                    prefer=prefer,
                    stack=stacker(gitops.main_root(repo)),
                )
            finally:
                store.close()
        nxt = selection.next
        if nxt is None:
            return ChainResult(runs, STOP_EXHAUSTED, [*start_skips, *selection.skipped])
        exclude.add(nxt.id)
        try:
            result = task_mod.run_task(
                repo, nxt.id, code=code, provider=provider, started_by=STARTED_AUTO_CONTINUE
            )
        except TaskRunError as exc:
            # Nothing was started (a race with another process, no writes, ...): try the next one.
            start_skips.append(Skip(nxt.id, "cannot_start", f"{exc.code}: {exc.message}"))
            continue
        runs.append(result)
        record.update(run_ids=[r.run.run_id for r in runs])
        _note_switch(record, result, since)
        last = result


def _run_parallel(
    repo: Path,
    task_id: str,
    *,
    auto: bool,
    note: str | None,
    force: bool,
    max_parallel: int,
    runner: ChainRunner,
    pr_files: Callable[[TaskPrRow], list[str] | None] | None,
    agents_override: dict[str, str] | None = None,
    first_run: Callable[[], task_mod.TaskRunResult] | None = None,
    code: CodeRunner | None = None,
) -> ChainResult:
    """Up to `max_parallel` runs at once, none overlapping another's writes or an open PR.

    With `first_run` (a retry) the first run runs in this process, merges like a member
    (``member_auto_merge``, `code` reaches its resolve run) and only then the chain fills.
    """
    main = gitops.main_root(repo)
    db = task_mod._load(main).local.trace_db_path(main)
    files_of = pr_files if pr_files is not None else _pr_files_default(main)
    first_task = _first_task(repo, task_id)
    goes_on = first_task is not None and (auto or auto_continue_enabled(first_task))
    record = _ChainRecord(db, task_id, max_parallel, enabled=goes_on)
    record.start()
    order: list[str] = []  # run ids in start order
    results: dict[str, task_mod.TaskRunResult] = {}
    exclude: set[str] = {task_id}
    start_skips: list[Skip] = []
    last_skips: list[Skip] = []
    exclusive: list[str] = []
    halt: str | None = None
    last_cont = True
    healed: set[str] = set()
    since = str(now_iso())

    def save(**extra: object) -> None:
        record.update(
            run_ids=list(order),
            skipped=[s.to_json() for s in [*start_skips, *last_skips]],
            exclusive=list(exclusive),
            **extra,
        )

    def started(task: Task | None, row: TaskRunRow) -> None:
        order.append(row.run_id)
        if task is not None and is_wide(effective_task_writes(task), main):
            exclusive.append(task.id)
        save()

    def fill(after_id: str, prefer: Sequence[str] = ()) -> None:
        nonlocal last_skips
        while halt is None:
            if len(runner.active()) >= max_parallel:
                return
            with _fresh_backlog(repo) as backlog:
                after = backlog.by_id.get(after_id)
                if not isinstance(after, Task):
                    return
                store = TaskRunStore(db)
                try:
                    # Runs of other chains, single runs and PRs waiting for review take
                    # slots of the repo too.
                    slots = Slots.of(store, runner.active())
                    full = slots.taken >= max_parallel
                    if full and not slots.in_review:
                        save()
                        return
                    occupancy = Occupancy.build(backlog, store, main, files_of)
                    selection = select_next(
                        backlog,
                        after,
                        open_pr=store.open_pr,
                        running=store.running,
                        exclude=exclude,
                        conflict=occupancy,
                        require_auto_continue=not auto,
                        prefs=store.queue_prefs(),
                        prefer=prefer,
                        stack=stacker(main),
                    )
                    deps = unmet_ids(backlog, selection.next) or [] if selection.next else []
                finally:
                    store.close()
            last_skips = selection.skipped
            nxt = selection.next
            if nxt is None:
                save()
                return
            if full and not slots.yields_to(deps):
                # PRs waiting for review hold the slot this task would take
                last_skips = [*last_skips, slots.skip(nxt.id)]
                save()
                return
            exclude.add(nxt.id)
            try:
                row = runner.start(nxt.id, started_by=STARTED_AUTO_CONTINUE)
            except TaskRunError as exc:
                start_skips.append(Skip(nxt.id, "cannot_start", f"{exc.code}: {exc.message}"))
                save()
                continue
            started(nxt, row)

    def finished(result: task_mod.TaskRunResult) -> None:
        nonlocal halt, last_cont
        if result.run.run_id not in order:
            order.append(result.run.run_id)
        results[result.run.run_id] = result
        resolved = result.resolve_run
        if resolved is not None:  # the member's auto-resolve run belongs to the chain
            if resolved.run.run_id not in order:
                order.insert(order.index(result.run.run_id) + 1, resolved.run.run_id)
            results[resolved.run.run_id] = resolved
        save()
        _note_switch(record, result, since)
        if halt is not None:
            return
        blocked: list[str] | None = None
        if _failed(result):
            blocked = task_mod.run_blockers(result.run)
            if blocked is None:
                # a retry runs in this process, like the first run of a retry chain
                fixed, goes_on = _heal_in_chain(
                    repo,
                    result,
                    auto=auto,
                    record=record,
                    healed=healed,
                    since=since,
                    code=code,
                    provider=None,
                )
                results[fixed.run.run_id] = fixed
                if not goes_on:
                    halt = STOP_FAILED
                    return
                if not fixed.closed_by_heal:
                    fixed = member_auto_merge(repo, fixed, code=code)
                finished(fixed)
                return
        prefer: list[str] = []
        with _fresh_backlog(repo) as backlog:
            found = backlog.by_id.get(result.run.task_id)
            after = found if isinstance(found, Task) else None
            if after is not None and blocked is not None:
                prefer = blockers_of(backlog, after, blocked)
        if after is None:
            if blocked is not None:
                halt = STOP_FAILED
            else:
                last_cont = False
            return
        cont = auto or auto_continue_enabled(after)
        if blocked is not None:
            # blocked during its run: no PR, no merge; on with its blockers first
            if not cont:
                halt = STOP_FAILED
                return
            start_skips.append(_blocked_skip(after, blocked))
            last_cont = True
            if not record.started:
                record.go_on()
            save()
            fill(after.id, prefer)
            return
        last_cont = cont
        if cont and not record.started:
            record.go_on()
            save()
        merge = result.auto_merge
        closed = result.closed_by_heal
        if not closed and auto_merge_enabled(after) and (merge is None or not merge.merged):
            if merge is None or not _waits_for_stack(merge):
                halt = STOP_NOT_MERGED if cont else STOP_DISABLED
                return
        if cont:
            fill(after.id)

    try:
        if first_run is not None:
            try:
                first = first_run()
            except TaskRunError:
                record.abort()
                raise
            started(first_task, first.run)
            finished(member_auto_merge(repo, first, code=code))
        else:
            try:
                first_row = runner.start(
                    task_id, note=note, force=force, agents_override=agents_override
                )
            except TaskRunError:
                record.abort()
                raise
            started(first_task, first_row)
            if goes_on:
                fill(task_id)
        while runner.active():
            finished(runner.wait_any())
    except BaseException:
        record.update(state=ABORTED)
        raise
    runs = [results[rid] for rid in order if rid in results]
    waiting: list[Skip] = []
    if halt is not None:
        stop = halt
    elif not last_cont:
        stop = STOP_DISABLED
    else:
        stop, waiting = STOP_EXHAUSTED, [*start_skips, *last_skips]
    record.finish(stop, [r.run.run_id for r in runs], [*start_skips, *last_skips], exclusive)
    return ChainResult(
        runs,
        stop,
        waiting,
        max_parallel=max_parallel,
        exclusive=exclusive,
        chain_id=record.chain_id if record.started else None,
        events=list(record.events),
    )
