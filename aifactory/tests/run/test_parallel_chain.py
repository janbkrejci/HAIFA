"""Parallel auto-continue (``max_parallel_runs``): `run_chain` with a fake runner.

The runner double claims and finishes rows in the real trace DB and saves open PRs, so
the chain's selection (``Occupancy``) sees them like real runs. No model, no network.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from run_repo import Script, commit_all, fake_env, make_run_repo, ok, write

from aifactory.backlog import Task, load_backlog
from aifactory.engine.utils import now_iso
from aifactory.review.automerge import AutoMergeResult
from aifactory.run import (
    STOP_EXHAUSTED,
    STOP_FAILED,
    STOP_NOT_MERGED,
    Skip,
    TaskPrRow,
    TaskRunError,
    TaskRunResult,
    TaskRunRow,
    TaskRunStore,
    run_chain,
    select_next,
)
from aifactory.run.store import FAILED, SUCCEEDED

CORE = "backlog/M01-core"
STEP = "S01-model"
T01, T02, T03, T04 = "M01-S01-T01", "M01-S01-T02", "M01-S01-T03", "M01-S01-T04"


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def setup_tasks(
    repo: Path,
    tasks: list[tuple[str, str]],
    *,
    step_extra: str = "auto_continue: true\n",
    config: str | None = None,
) -> None:
    """S01 holds `tasks` (id, writes) in order, the step without own writes."""
    shutil.rmtree(repo / CORE / STEP)
    write(repo, f"{CORE}/{STEP}/index.md", f"---\nid: M01-S01\ntitle: Model\n{step_extra}---\n")
    for task_id, writes in tasks:
        write(
            repo,
            f"{CORE}/{STEP}/{task_id}.md",
            f"---\nid: {task_id}\ntitle: Task {task_id}\nstatus: todo\nwrites: [{writes}]\n---\n\n"
            f"Do {task_id}.\n",
        )
    if config is not None:
        write(repo, ".factory/config.yaml", config)
    commit_all(repo, "parallel backlog")


def _db(repo: Path) -> Path:
    return repo / ".factory" / "trace.db"


def _pr(task_id: str, url: str | None = None) -> TaskPrRow:
    now = str(now_iso())
    branch = f"factory/{task_id}-1"
    return TaskPrRow(
        branch,
        task_id,
        "local",
        "1",
        url or f"URL-{task_id}",
        "main",
        "0",
        "t",
        "",
        "open",
        now,
        now,
    )


class FakeRunner:
    """Claims a `running` row on start; `wait_any` finishes one (FIFO unless `order`)."""

    def __init__(
        self,
        repo: Path,
        *,
        fail: tuple[str, ...] = (),
        merge: dict[str, AutoMergeResult] | None = None,
        order: list[str] | None = None,
        resolve: dict[str, bool] | None = None,
    ) -> None:
        self.db = _db(repo)
        self.resolve = resolve or {}
        self.fail = fail
        self.merge = merge or {}
        self.order = list(order or [])
        self.rows: dict[str, TaskRunRow] = {}
        self.events: list[tuple[str, str]] = []
        self.max_active = 0
        self.active_at_start: dict[str, int] = {}
        self.skips_seen: list[list[dict[str, object]]] = []

    def _store(self) -> TaskRunStore:
        return TaskRunStore(self.db)

    def active(self) -> list[str]:
        return list(self.rows)

    def start(
        self,
        task_id: str,
        *,
        note: str | None = None,
        force: bool = False,
        started_by: str = "manual",
        agents_override: dict[str, str] | None = None,
    ) -> TaskRunRow:
        row = TaskRunRow(
            run_id=f"r-{task_id}",
            task_id=task_id,
            branch=f"factory/{task_id}-1",
            worktree="wt",
            base="main",
            base_sha="0",
            head_sha=None,
            state="running",
            started_at=str(now_iso()),
            pid=os.getpid(),
            started_by=started_by,
        )
        store = self._store()
        try:
            store.claim(row)
        finally:
            store.close()
        self.active_at_start[task_id] = len(self.rows)
        self.rows[task_id] = row
        self.events.append(("start", task_id))
        self.max_active = max(self.max_active, len(self.rows))
        return row

    def wait_any(self) -> TaskRunResult:
        store = self._store()
        try:
            chains = store.chains()
            if chains:
                self.skips_seen.append(chains[0].skipped_list())
            task_id = next((t for t in self.order if t in self.rows), next(iter(self.rows)))
            if task_id in self.order:
                self.order.remove(task_id)
            row = self.rows.pop(task_id)
            failed = task_id in self.fail
            store.finish(
                row.run_id, FAILED if failed else SUCCEEDED, "abc", "boom" if failed else None
            )
            pr = None
            if not failed:
                pr = _pr(task_id)
                store.save_pr(pr)
            final = store.get(row.run_id)
            assert final is not None
            resolve_run = None
            if task_id in self.resolve:  # the member's auto-resolve run (cli `--member`)
                rrow = replace(row, run_id=f"r-{task_id}-resolve")
                store.claim(rrow)
                state = SUCCEEDED if self.resolve[task_id] else FAILED
                store.finish(rrow.run_id, state, "abd", None)
                got = store.get(rrow.run_id)
                assert got is not None
                resolve_run = TaskRunResult(
                    run=got, workflow_run=None, warnings=(), trace_db=self.db, pr=pr
                )
        finally:
            store.close()
        self.events.append(("end", task_id))
        return TaskRunResult(
            run=final,
            workflow_run=None,
            warnings=(),
            trace_db=self.db,
            pr=pr,
            auto_merge=self.merge.get(task_id),
            resolve_run=resolve_run,
        )


class ExplodingRunner:
    def start(
        self,
        task_id: str,
        *,
        note: str | None = None,
        force: bool = False,
        started_by: str = "manual",
        agents_override: dict[str, str] | None = None,
    ) -> TaskRunRow:
        raise AssertionError("the sequential chain must not use a runner")

    def wait_any(self) -> TaskRunResult:
        raise AssertionError("the sequential chain must not use a runner")

    def active(self) -> list[str]:
        raise AssertionError("the sequential chain must not use a runner")


def no_files(pr: TaskPrRow) -> list[str] | None:
    return []


def started(runner: FakeRunner) -> list[str]:
    return [t for kind, t in runner.events if kind == "start"]


# ── limit and refill ─────────────────────────────────────────────────────────


def test_limit_is_never_exceeded(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/"), (T03, "src/c/"), (T04, "src/d/")])
    runner = FakeRunner(repo)
    chain = run_chain(repo, T01, max_parallel=2, runner=runner, pr_files=no_files)
    assert runner.max_active == 2
    assert started(runner) == [T01, T02, T03, T04]
    assert [r.run.started_by for r in chain.runs] == ["manual", *["auto-continue"] * 3]
    assert [r.run.task_id for r in chain.runs] == [T01, T02, T03, T04]
    assert chain.ok
    assert (chain.stop, chain.waiting) == (STOP_EXHAUSTED, [])
    assert chain.max_parallel == 2
    assert chain.exclusive == []
    data = chain.to_json()
    assert data["max_parallel_runs"] == 2 and data["chain_id"] == chain.chain_id


def test_slot_is_refilled_after_a_run_ends(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/"), (T03, "src/c/")])
    runner = FakeRunner(repo)
    chain = run_chain(repo, T01, max_parallel=2, runner=runner, pr_files=no_files)
    assert runner.events == [
        ("start", T01),
        ("start", T02),
        ("end", T01),
        ("start", T03),
        ("end", T02),
        ("end", T03),
    ]
    assert chain.stop == STOP_EXHAUSTED
    store = TaskRunStore(_db(repo))
    try:
        (row,) = store.chains()
    finally:
        store.close()
    assert (row.chain_id, row.state, row.stop) == (chain.chain_id, "finished", STOP_EXHAUSTED)
    assert row.run_id_list() == [f"r-{t}" for t in (T01, T02, T03)]
    assert row.max_parallel == 2


def test_without_auto_continue_only_the_first_runs(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/")], step_extra="")
    runner = FakeRunner(repo)
    chain = run_chain(repo, T01, max_parallel=3, runner=runner, pr_files=no_files)
    assert started(runner) == [T01]
    assert chain.stop == "disabled"
    assert chain.chain_id is None
    store = TaskRunStore(_db(repo))
    try:
        assert store.conn.execute("SELECT COUNT(*) FROM task_chains").fetchone()[0] == 0
    finally:
        store.close()


def test_auto_continue_committed_during_the_first_run_records_the_chain(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/")], step_extra="")
    runner = FakeRunner(repo)
    real_wait = runner.wait_any
    switched: list[bool] = []

    def wait_then_switch_on() -> TaskRunResult:
        result = real_wait()
        if not switched:
            switched.append(True)
            write(
                repo,
                f"{CORE}/{STEP}/index.md",
                "---\nid: M01-S01\ntitle: Model\nauto_continue: true\n---\n",
            )
            commit_all(repo, "auto-continue on")
        return result

    runner.wait_any = wait_then_switch_on  # type: ignore[method-assign]
    chain = run_chain(repo, T01, max_parallel=3, runner=runner, pr_files=no_files)
    assert started(runner) == [T01, T02]
    assert chain.chain_id is not None
    store = TaskRunStore(_db(repo))
    try:
        (row,) = store.chains()
    finally:
        store.close()
    assert row.chain_id == chain.chain_id
    assert row.run_id_list() == [f"r-{T01}", f"r-{T02}"]


S02_T01 = "M01-S02-T01"


def setup_step_off(repo: Path) -> None:
    """S01 (auto-continue on) with T01 and T02, then step S02 without it and its task."""
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/")])
    write(repo, f"{CORE}/S02-other/index.md", "---\nid: M01-S02\ntitle: Other\n---\n")
    write(
        repo,
        f"{CORE}/S02-other/{S02_T01}.md",
        f"---\nid: {S02_T01}\ntitle: Other\nstatus: todo\nwrites: [src/c/]\n---\n\nDo it.\n",
    )
    commit_all(repo, "a step without auto-continue")


def test_a_step_with_auto_continue_off_is_not_started(repo: Path) -> None:
    setup_step_off(repo)
    runner = FakeRunner(repo)
    chain = run_chain(repo, T01, max_parallel=3, runner=runner, pr_files=no_files)
    assert started(runner) == [T01, T02]
    assert (chain.stop, chain.waiting) == (STOP_EXHAUSTED, [])


def test_auto_flag_starts_a_step_with_auto_continue_off(repo: Path) -> None:
    setup_step_off(repo)
    runner = FakeRunner(repo)
    chain = run_chain(repo, T01, auto=True, max_parallel=3, runner=runner, pr_files=no_files)
    assert started(runner) == [T01, T02, S02_T01]
    assert chain.stop == STOP_EXHAUSTED


# ── overlaps ─────────────────────────────────────────────────────────────────


def test_overlap_with_a_running_run_is_skipped(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/app/"), (T02, "src/app/sub/"), (T03, "src/other/")])
    runner = FakeRunner(repo, order=[T03, T01])
    chain = run_chain(repo, T01, max_parallel=3, runner=runner, pr_files=no_files)
    # T03 ran alongside T01; T02 only after T01 ended
    assert runner.events[:2] == [("start", T01), ("start", T03)]
    assert runner.events.index(("start", T02)) > runner.events.index(("end", T01))
    skips = [Skip(**s) for seen in runner.skips_seen for s in seen]  # type: ignore[arg-type]
    overlap = [s for s in skips if s.task_id == T02]
    assert overlap and overlap[0].reason == "writes_overlap"
    assert f"r-{T01}" in overlap[0].detail and T01 in overlap[0].detail
    assert "src/app/" in overlap[0].detail
    assert overlap[0].waits_on == [T01]
    assert chain.stop == STOP_EXHAUSTED


def test_overlap_with_an_open_pr_is_skipped(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/other/"), (T03, "src/b/")])
    store = TaskRunStore(_db(repo))
    try:
        store.save_pr(_pr("M09-S01-T01", url="https://example.test/pr/7"))
    finally:
        store.close()

    def files(pr: TaskPrRow) -> list[str] | None:
        return ["src/other/x.py"] if pr.task_id == "M09-S01-T01" else []

    runner = FakeRunner(repo)
    chain = run_chain(repo, T01, max_parallel=3, runner=runner, pr_files=files)
    assert started(runner) == [T01, T03]
    assert chain.stop == STOP_EXHAUSTED
    (skip,) = chain.waiting
    assert (skip.task_id, skip.reason) == (T02, "writes_overlap")
    assert "https://example.test/pr/7" in skip.detail
    assert "src/other/x.py" in skip.detail
    assert skip.waits_on == ["M09-S01-T01"]


def test_unknown_pr_files_fall_back_to_the_task_writes(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/a/deep/"), (T03, "src/b/")])
    runner = FakeRunner(repo)
    # T01's PR files cannot be read: its writes src/a/ stand for them
    chain = run_chain(repo, T01, max_parallel=2, runner=runner, pr_files=lambda pr: None)
    assert T02 not in started(runner)
    (skip,) = chain.waiting
    assert (skip.task_id, skip.reason) == (T02, "writes_overlap")
    assert "soubory PR nelze zjistit" in skip.detail


# ── wide writes ──────────────────────────────────────────────────────────────


def test_wide_task_runs_alone(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/"), (T03, "src/b/")])
    runner = FakeRunner(repo)
    chain = run_chain(repo, T01, max_parallel=3, runner=runner, pr_files=no_files)
    assert started(runner) == [T01, T03, T02]
    assert runner.active_at_start[T02] == 0  # nothing ran alongside it
    assert chain.exclusive == [T02]
    skips = [s for seen in runner.skips_seen for s in seen]
    assert any(s["task_id"] == T02 and s["reason"] == "exclusive" for s in skips)


def test_nothing_runs_alongside_a_wide_task(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/, justfile"), (T02, "lib/a/"), (T03, "lib/b/")])
    runner = FakeRunner(repo)
    chain = run_chain(repo, T01, max_parallel=3, runner=runner, pr_files=no_files)
    assert runner.events[:2] == [("start", T01), ("end", T01)]
    assert chain.exclusive == [T01]
    first = runner.skips_seen[0]
    assert {(s["task_id"], s["reason"]) for s in first} == {(T02, "exclusive"), (T03, "exclusive")}
    assert all("souběžně nic jiného" in str(s["detail"]) for s in first)


# ── stops ────────────────────────────────────────────────────────────────────


def test_failure_stops_filling_and_lets_active_runs_finish(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/"), (T03, "src/c/"), (T04, "src/d/")])
    runner = FakeRunner(repo, fail=(T02,))
    chain = run_chain(repo, T01, max_parallel=2, runner=runner, pr_files=no_files)
    assert started(runner) == [T01, T02, T03]
    assert [r.run.task_id for r in chain.runs] == [T01, T02, T03]
    assert [r.ok for r in chain.runs] == [True, False, True]
    assert chain.stop == STOP_FAILED
    assert not chain.ok


def test_unmerged_pr_stops_filling(repo: Path) -> None:
    setup_tasks(
        repo,
        [(T01, "src/a/"), (T02, "src/b/"), (T03, "src/c/")],
        step_extra="auto_continue: true\nauto_merge: true\n",
    )
    refused = AutoMergeResult(False, "no_review", "no review ran", "URL")
    runner = FakeRunner(repo, merge={T01: refused})
    chain = run_chain(repo, T01, max_parallel=2, runner=runner, pr_files=no_files)
    assert started(runner) == [T01, T02]
    assert chain.stop == STOP_NOT_MERGED


def test_member_resolve_run_belongs_to_the_chain(repo: Path) -> None:
    setup_tasks(
        repo,
        [(T01, "src/a/"), (T02, "src/b/")],
        step_extra="auto_continue: true\nauto_merge: true\n",
    )
    merged = AutoMergeResult(True, None, None, "URL", "f" * 40)
    runner = FakeRunner(repo, merge={T01: merged, T02: merged}, resolve={T01: True}, order=[T01])
    chain = run_chain(repo, T01, max_parallel=2, runner=runner, pr_files=no_files)
    ids = [r.run.run_id for r in chain.runs]
    assert ids[:2] == [f"r-{T01}", f"r-{T01}-resolve"]
    assert f"r-{T02}" in ids
    assert chain.stop == STOP_EXHAUSTED
    store = TaskRunStore(_db(repo))
    try:
        chains = store.chains()
        assert chains and chains[0].run_id_list() == ids
    finally:
        store.close()


def test_member_rejected_resolution_stops_the_chain(repo: Path) -> None:
    setup_tasks(
        repo,
        [(T01, "src/a/"), (T02, "src/b/"), (T03, "src/c/")],
        step_extra="auto_continue: true\nauto_merge: true\n",
    )
    rejected = AutoMergeResult(False, "resolve_failed", "auto-resolve run ended failed", "URL")
    runner = FakeRunner(repo, merge={T01: rejected}, resolve={T01: False}, order=[T01])
    chain = run_chain(repo, T01, max_parallel=2, runner=runner, pr_files=no_files)
    assert started(runner) == [T01, T02]
    assert chain.stop == STOP_NOT_MERGED
    assert f"r-{T01}-resolve" in [r.run.run_id for r in chain.runs]


def test_first_start_error_propagates_and_leaves_no_chain(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/")])

    class Refusing(FakeRunner):
        def start(
            self,
            task_id: str,
            *,
            note: str | None = None,
            force: bool = False,
            started_by: str = "manual",
            agents_override: dict[str, str] | None = None,
        ) -> TaskRunRow:
            raise TaskRunError("unmet_dependencies", "no")

    with pytest.raises(TaskRunError):
        run_chain(repo, T01, max_parallel=2, runner=Refusing(repo), pr_files=no_files)
    store = TaskRunStore(_db(repo))
    try:
        assert store.chains() == []
    finally:
        store.close()


def test_later_start_error_is_cannot_start(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/"), (T03, "src/c/")])

    class Picky(FakeRunner):
        def start(
            self,
            task_id: str,
            *,
            note: str | None = None,
            force: bool = False,
            started_by: str = "manual",
            agents_override: dict[str, str] | None = None,
        ) -> TaskRunRow:
            if task_id == T02:
                raise TaskRunError("no_writes", "nothing to write")
            return super().start(task_id, note=note, force=force, started_by=started_by)

    runner = Picky(repo)
    chain = run_chain(repo, T01, max_parallel=3, runner=runner, pr_files=no_files)
    assert started(runner) == [T01, T03]
    assert [(s.task_id, s.reason) for s in chain.waiting] == [(T02, "cannot_start")]


def test_max_parallel_is_read_from_the_config(repo: Path) -> None:
    setup_tasks(
        repo,
        [(T01, "src/a/"), (T02, "src/b/"), (T03, "src/c/")],
        config="base: main\nmax_parallel_runs: 2\n",
    )
    runner = FakeRunner(repo)
    chain = run_chain(repo, T01, runner=runner, pr_files=no_files)
    assert chain.max_parallel == 2
    assert runner.max_active == 2


# ── max_parallel_runs: 1 is the chain of today ───────────────────────────────


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


def build(script: Script, name: str) -> None:
    rel = f"src/app/{name}.py"
    script.on("planner", lambda wt: write(wt, rel, f"NAME = {name!r}\n"))
    script.add("planner", ok(artifacts=[], changed_files=[rel], commit_message=f"Add {name}"))


def test_one_parallel_run_is_the_sequential_chain(repo: Path, script: Script) -> None:
    # every task writes src/app/ and the PRs stay open: no overlap check applies
    setup_tasks(
        repo,
        [(T01, "src/app/"), (T02, "src/app/"), (T03, "src/app/")],
        config="base: main\nmax_parallel_runs: 1\n",
    )
    for name in ("one", "two", "three"):
        build(script, name)

    def explode(pr: TaskPrRow) -> list[str] | None:
        raise AssertionError("no PR files in the sequential chain")

    chain = run_chain(repo, T01, runner=ExplodingRunner(), pr_files=explode)
    assert [r.run.task_id for r in chain.runs] == [T01, T02, T03]
    assert chain.ok, [(r.run.error, r.pr_error) for r in chain.runs]
    assert (chain.stop, chain.waiting) == (STOP_EXHAUSTED, [])
    assert chain.max_parallel == 1
    store = TaskRunStore(_db(repo))
    try:
        (row,) = store.chains()
    finally:
        store.close()
    assert (row.state, row.stop, row.max_parallel) == ("finished", STOP_EXHAUSTED, 1)
    assert row.run_id_list() == [r.run.run_id for r in chain.runs]


# ── select_next with a conflict ──────────────────────────────────────────────


def test_select_next_asks_conflict_only_for_startable_tasks(repo: Path) -> None:
    shutil.rmtree(repo / CORE / STEP)
    write(
        repo, f"{CORE}/{STEP}/index.md", "---\nid: M01-S01\ntitle: Model\nwrites: [src/app/]\n---\n"
    )
    for task_id, extra in (
        (T01, ""),
        (T02, "workflow: null\n"),
        (T03, ""),
        (T04, ""),
    ):
        write(
            repo,
            f"{CORE}/{STEP}/{task_id}.md",
            f"---\nid: {task_id}\ntitle: T\nstatus: todo\n{extra}---\n\nDo.\n",
        )
    backlog = load_backlog(repo)
    after = backlog.by_id[T01]
    assert isinstance(after, Task)
    asked: list[str] = []

    def conflict(task: Task) -> Skip | None:
        asked.append(task.id)
        return Skip(task.id, "writes_overlap", "busy") if task.id == T03 else None

    none: Callable[[str], None] = lambda _tid: None  # noqa: E731
    sel = select_next(backlog, after, open_pr=none, running=none, conflict=conflict)
    assert sel.next is not None and sel.next.id == T04
    assert asked == [T03, T04]
    assert [(s.task_id, s.reason) for s in sel.skipped] == [
        (T02, "no_workflow"),
        (T03, "writes_overlap"),
    ]
    sel = select_next(backlog, after, open_pr=none, running=none)
    assert sel.next is not None and sel.next.id == T03


# ── kanban queue ─────────────────────────────────────────────────────────────


def test_fill_follows_the_kanban_order_and_skips_excluded(repo: Path) -> None:
    setup_tasks(repo, [(T01, "src/a/"), (T02, "src/b/"), (T03, "src/c/"), (T04, "src/d/")])
    store = TaskRunStore(_db(repo))
    try:
        store.set_queue_order([T04, T02])
        store.set_excluded(T03, True)
    finally:
        store.close()
    runner = FakeRunner(repo)
    chain = run_chain(repo, T01, max_parallel=2, runner=runner, pr_files=no_files)
    assert started(runner) == [T01, T04, T02]
    assert [(s.task_id, s.reason) for s in chain.waiting] == [(T03, "excluded")]
