"""Auto-continue: after a successful run, start the next ready task (D10, Q9).

``run_chain`` runs one task with ``run_task`` and, when the run succeeded and
opened its pull request, picks the next task with ``select_next`` and runs it,
until nothing more can start or a run fails.

``--auto`` (``auto=True``) holds for the whole chain: it continues after every
successful run and may start any task. Otherwise ``auto_continue: true`` inherited
by a task (task, step or project ``index.md``) decides both ways: the chain continues
only after a task that has it (else ``stop == "disabled"``) and starts only tasks
that have it. So with ``auto_continue: true`` on step S01 only, the chain runs the
tasks of S01 and stops; a task of a step with auto-continue off is never started by
a chain.

The next task is taken from the kanban's manual queue first (``task_queue`` in the
trace DB, ``store.QueuePrefs``), then from the same step, then from the rest of the
same project, both in backlog order, only ``status: todo``. A task excluded from
auto-continue in the kanban is never started by a chain (``excluded``), with
``--auto`` too; started by hand it runs. A task whose
dependencies are only waiting in open (not merged) pull requests is skipped
(``waits_on_pr``) and the chain goes on with what can run; after ``task
approve`` the operator starts the skipped task again. A task without a
workflow (effective ``workflow`` unset or ``null``) is never started: it is
skipped as ``no_workflow`` ("bez workflow") and the chain goes on. The chain never
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

Parallel runs (``max_parallel_runs`` in ``.factory/config.yaml``, default 1): with 1
the chain runs one task after another as described above, with no other check. Above
1 the chain keeps up to that many runs going at once, each a separate process
(``members.ProcessRunner``, ``factory task run --member``): after the first task it
fills the free slots with the next ready tasks and refills a slot whenever a run
ends. A task starts only when its effective ``writes`` do not overlap (on path
prefixes, ``scope.paths_overlap``) the ``writes`` of any running run (of this chain or
not) nor the files changed by any open, unmerged PR (``gitops.pr_changed_files``;
when they cannot be read, the PR's task's ``writes``, else everything). Otherwise it
is skipped as ``writes_overlap`` (which run or PR, which paths) and the chain tries
the next one. A task whose ``writes`` cover the whole repo or a whole package
(``scope.is_wide``, e.g. ``aifactory/``) runs alone: it does not start while anything
runs, and nothing starts while it runs (``exclusive``); ``ChainResult.exclusive``
lists such tasks. A failed run stops the filling (``stop == "failed"``); runs already
going are left to finish. With ``auto_merge`` the member process merges its own PR
(under the store's merge lock); a PR it did not merge stops the filling as above.

Every chain that goes on has a row in ``task_chains`` (``store.TaskChainRow``): its
runs, the skipped tasks of the last selection with their reasons, the exclusive tasks
and, at the end, the stop. The row is written from the start when the chain can go on
then (``--auto``, or ``auto_continue: true`` on its first task in base), otherwise from
the moment it does go on (auto-continue committed to base during the run). A run that
never goes on is a single run, it gets no row. The dashboard shows the rows
(``/api/chains``). A failure to write a row never affects the chain.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import sqlite3
import sys
import tempfile
from collections.abc import Callable, Collection, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from aifactory.backlog import Backlog, Task, effective, has_workflow, load_backlog, unmet
from aifactory.backlog.derived import ancestors, descendant_tasks
from aifactory.config import ConfigError
from aifactory.engine.utils import now_iso
from aifactory.providers import GitProvider
from aifactory.run import gitops
from aifactory.run import task as task_mod
from aifactory.run.errors import TaskRunError
from aifactory.run.members import ChainRunner, ProcessRunner
from aifactory.run.scope import effective_task_writes, is_wide, overlaps
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
    "no_workflow",
    "waits_on_pr",
    "blocked",
    "in_review",
    "running",
    "cannot_start",
    "writes_overlap",
    "exclusive",
    "excluded",
)
EXCLUDED_DETAIL = "vyloučeno z auto continue v kanbanu"
NO_WORKFLOW_DETAIL = "bez workflow"
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
) -> Selection:
    """The first startable candidate after `after`, and every candidate that was skipped.

    ``conflict`` (parallel chains, ``Occupancy``) is asked only about a candidate that
    could start otherwise, until one is chosen; a ``Skip`` it returns is recorded and the
    next candidate is tried. With ``require_auto_continue`` (a chain without ``--auto``)
    a candidate without ``auto_continue: true`` is left out, not reported as skipped.
    ``prefs`` (the kanban's queue, ``TaskRunStore.queue_prefs``) orders the candidates
    and excludes tasks: an excluded task is skipped as ``excluded``, with ``--auto`` too.
    """
    prefs = prefs or QueuePrefs()
    chosen: Task | None = None
    skipped: list[Skip] = []
    for task in candidates(after, prefs.order):
        if task.id in exclude:
            continue
        if require_auto_continue and not auto_continue_enabled(task):
            continue
        if task.id in prefs.excluded:
            skipped.append(Skip(task.id, "excluded", EXCLUDED_DETAIL))
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
        return cls(runs, prs, root)

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
        for pr, paths, known in self.prs:
            if pr.task_id == task.id:
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

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.runs)

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
                }
                for r in self.runs
            ],
            "stop": self.stop,
            "waiting": [s.to_json() for s in self.waiting],
            "max_parallel_runs": self.max_parallel,
            "exclusive": list(self.exclusive),
            "chain_id": self.chain_id,
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
        )
        self._write(lambda store: store.start_chain(row))
        self.started = self.db is not None

    def update(self, **fields: object) -> None:
        if self.started:
            self._write(lambda store: store.update_chain(self.chain_id, **fields))  # type: ignore[arg-type]

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


def _max_parallel(repo: Path) -> int:
    try:
        return task_mod._load(gitops.main_root(repo)).config.settings.max_parallel_runs
    except (TaskRunError, ConfigError, OSError):
        return 1  # the run itself reports the problem


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
) -> ChainResult:
    """Run `task_id`, then (auto-continue) the next ready tasks.

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
    )


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
        )
    except TaskRunError:
        record.abort()
        raise
    except BaseException:
        record.update(state=ABORTED)
        raise
    chain.chain_id = record.chain_id if record.started else None
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
) -> ChainResult:
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
    exclude = {task_id}
    start_skips: list[Skip] = []
    last = first
    while True:
        if not last.ok or last.pr is None:
            return ChainResult(runs, STOP_FAILED)
        with tempfile.TemporaryDirectory(prefix="factory-chain-") as tmp:
            backlog = _base_backlog(repo, Path(tmp))
            after = backlog.by_id.get(last.run.task_id)
            if not isinstance(after, Task):
                return ChainResult(runs, STOP_DISABLED)
            cont = auto or auto_continue_enabled(after)
            if cont and not record.started:
                record.go_on(last.trace_db)
                record.update(run_ids=[r.run.run_id for r in runs])
            merged = False
            if last.auto_merge is None and auto_merge_enabled(after):
                # Local import: aifactory.review imports aifactory.run.
                from aifactory.review.automerge import try_auto_merge

                last.auto_merge = try_auto_merge(repo, last, after, provider=provider)
                if not last.auto_merge.merged and last.auto_merge.code == "conflict":
                    # one auto-resolve (whole suite, reviewed resolution), then merge
                    from aifactory.review.automerge import resolve_and_merge

                    resolved, last.auto_merge = resolve_and_merge(
                        repo, last, after, provider=provider, code=code
                    )
                    if resolved is not None:
                        runs.append(resolved)
                if not last.auto_merge.merged:
                    return ChainResult(runs, STOP_NOT_MERGED if cont else STOP_DISABLED)
                merged = True
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
) -> ChainResult:
    """Up to `max_parallel` runs at once, none overlapping another's writes or an open PR."""
    main = gitops.main_root(repo)
    db = task_mod._load(main).local.trace_db_path(main)
    files_of = pr_files
    if files_of is None:

        def files_of(pr: TaskPrRow) -> list[str] | None:
            return gitops.pr_changed_files(main, pr.base, pr.branch, pr.base_sha)

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

    def fill(after_id: str) -> None:
        nonlocal last_skips
        while len(runner.active()) < max_parallel and halt is None:
            with _fresh_backlog(repo) as backlog:
                after = backlog.by_id.get(after_id)
                if not isinstance(after, Task):
                    return
                store = TaskRunStore(db)
                try:
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
                    )
                finally:
                    store.close()
            last_skips = selection.skipped
            nxt = selection.next
            if nxt is None:
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

    try:
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
            result = runner.wait_any()
            if result.run.run_id not in order:
                order.append(result.run.run_id)
            results[result.run.run_id] = result
            resolved = result.resolve_run
            if resolved is not None:  # the member's auto-resolve run belongs to the chain
                if resolved.run.run_id not in order:
                    order.insert(order.index(result.run.run_id) + 1, resolved.run.run_id)
                results[resolved.run.run_id] = resolved
            save()
            if halt is not None:
                continue
            if not result.ok or result.pr is None:
                halt = STOP_FAILED
                continue
            with _fresh_backlog(repo) as backlog:
                found = backlog.by_id.get(result.run.task_id)
                after = found if isinstance(found, Task) else None
            if after is None:
                last_cont = False
                continue
            cont = auto or auto_continue_enabled(after)
            last_cont = cont
            if cont and not record.started:
                record.go_on()
                save()
            merge = result.auto_merge
            if auto_merge_enabled(after) and (merge is None or not merge.merged):
                halt = STOP_NOT_MERGED if cont else STOP_DISABLED
                continue
            if cont:
                fill(after.id)
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
    )
