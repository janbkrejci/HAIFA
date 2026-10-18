"""Auto-continue (D10, Q9): `run_chain` and `task run --auto`, fake harnesses, provider local."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from run_repo import Script, commit_all, fake_env, git, make_run_repo, ok, write

from aifactory.backlog import Task, load_backlog
from aifactory.cli import main
from aifactory.review import approve_task
from aifactory.run import (
    STOP_DISABLED,
    STOP_EXHAUSTED,
    STOP_FAILED,
    ChainResult,
    Skip,
    TaskPrRow,
    TaskRunError,
    TaskRunRow,
    TaskRunStore,
    run_chain,
    run_task,
    select_next,
)
from aifactory.run import task as task_mod
from aifactory.run.queue import SKIP_REASONS, blockers_of
from aifactory.run.store import QueuePrefs
from cli_json import read_envelope

Capsys = pytest.CaptureFixture[str]
T01, T02, T03 = "M01-S01-T01", "M01-S01-T02", "M01-S01-T03"
S02_T01 = "M01-S02-T01"
CORE = "backlog/M01-core"


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


def _task(
    repo: Path,
    step: str,
    task_id: str,
    *,
    depends_on: list[str] | None = None,
    extra: str = "",
) -> None:
    deps = f"depends_on: [{', '.join(depends_on)}]\n" if depends_on else ""
    write(
        repo,
        f"{CORE}/{step}/{task_id}.md",
        f"---\nid: {task_id}\ntitle: Task {task_id}\nstatus: todo\n{deps}{extra}---\n\n"
        f"Do {task_id}.\n",
    )


def _index(repo: Path, step: str, step_id: str, extra: str = "") -> None:
    write(repo, f"{CORE}/{step}/index.md", f"---\nid: {step_id}\ntitle: {step}\n{extra}---\n")


def setup_chain(
    repo: Path,
    *,
    step_auto: bool = False,
    module_auto: bool = False,
    t02_depends: bool = False,
    t02_extra: str = "",
    s02_writes: str | None = None,
) -> None:
    """S01 holds T01..T03 (all writing src/app/); optionally a step S02 with one task."""
    s01 = repo / CORE / "S01-model"
    shutil.rmtree(s01)
    auto = "auto_continue: true\n" if step_auto else ""
    _index(repo, "S01-model", "M01-S01", f"writes: [src/app/]\n{auto}")
    _task(repo, "S01-model", T01)
    _task(repo, "S01-model", T02, depends_on=[T01] if t02_depends else None, extra=t02_extra)
    _task(repo, "S01-model", T03)
    if s02_writes is not None:
        _index(repo, "S02-other", "M01-S02", s02_writes)
        _task(repo, "S02-other", S02_T01)
    if module_auto:
        write(
            repo,
            f"{CORE}/index.md",
            "---\nid: M01\ntitle: Core\nworkflow: plan-commit\nauto_continue: true\n---\n",
        )
    commit_all(repo, "chain backlog")


def build(script: Script, name: str, path: str | None = None) -> None:
    """One planner call: writes `path` (default src/app/<name>.py) and succeeds."""
    rel = path or f"src/app/{name}.py"
    script.on("planner", lambda wt: write(wt, rel, f"NAME = {name!r}\n"))
    script.add("planner", ok(artifacts=[], changed_files=[rel], commit_message=f"Add {name}"))


def _store(repo: Path) -> TaskRunStore:
    return TaskRunStore(repo / ".factory" / "trace.db")


def runs_of(repo: Path, task_id: str) -> list[TaskRunRow]:
    store = _store(repo)
    try:
        return store.for_task(task_id)
    finally:
        store.close()


def open_pr(repo: Path, task_id: str) -> TaskPrRow | None:
    store = _store(repo)
    try:
        return store.open_pr(task_id)
    finally:
        store.close()


def ids(chain: ChainResult) -> list[str]:
    return [r.run.task_id for r in chain.runs]


# ── chains ───────────────────────────────────────────────────────────────────


def test_three_independent_tasks_run_in_order(repo: Path, script: Script) -> None:
    setup_chain(repo, step_auto=True)
    main_before = git(repo, "rev-parse", "main")
    for name in ("one", "two", "three"):
        build(script, name)
    chain = run_chain(repo, T01)
    assert ids(chain) == [T01, T02, T03]
    assert all(r.ok for r in chain.runs), [(r.run.error, r.pr_error) for r in chain.runs]
    assert chain.ok
    assert (chain.stop, chain.waiting) == (STOP_EXHAUSTED, [])
    assert chain.chain_id is not None and chain_rows(repo) == 1
    # the operator started the first run, the chain the others
    assert [r.run.started_by for r in chain.runs] == ["manual", "auto-continue", "auto-continue"]
    assert [r.started_by for r in runs_of(repo, T02)] == ["auto-continue"]
    for tid in (T01, T02, T03):
        assert open_pr(repo, tid) is not None
    # Never approved nor merged: base is untouched, every task is still todo there.
    assert git(repo, "rev-parse", "main") == main_before
    backlog = load_backlog(repo)
    for tid in (T01, T02, T03):
        node = backlog.by_id[tid]
        assert isinstance(node, Task) and node.status == "todo"


def chain_rows(repo: Path) -> int:
    store = _store(repo)
    try:
        return int(store.conn.execute("SELECT COUNT(*) FROM task_chains").fetchone()[0])
    finally:
        store.close()


def test_without_auto_one_run_only(repo: Path, script: Script) -> None:
    setup_chain(repo)
    build(script, "one")
    chain = run_chain(repo, T01)
    assert ids(chain) == [T01]
    assert chain.ok
    assert chain.stop == STOP_DISABLED
    assert runs_of(repo, T02) == []
    # a single run is not a chain: no row, the dashboard shows no chain
    assert (chain.chain_id, chain_rows(repo)) == (None, 0)


def test_auto_continue_committed_during_the_first_run_records_the_chain(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Off in base at the start, on when the first run ends: the chain goes on with a row."""
    setup_chain(repo)
    for name in ("one", "two", "three"):
        build(script, name)
    real = task_mod.run_task
    switched: list[bool] = []

    def run_then_switch_on(*args: Any, **kwargs: Any) -> task_mod.TaskRunResult:
        result = real(*args, **kwargs)
        if not switched:
            switched.append(True)
            _index(repo, "S01-model", "M01-S01", "writes: [src/app/]\nauto_continue: true\n")
            commit_all(repo, "auto-continue on")
        return result

    monkeypatch.setattr(task_mod, "run_task", run_then_switch_on)
    chain = run_chain(repo, T01)
    assert ids(chain) == [T01, T02, T03]
    assert chain.chain_id is not None and chain_rows(repo) == 1
    store = _store(repo)
    try:
        row = store.get_chain(chain.chain_id)
    finally:
        store.close()
    assert row is not None and row.run_id_list() == [r.run.run_id for r in chain.runs]


def test_auto_flag_continues(repo: Path, script: Script) -> None:
    setup_chain(repo)
    for name in ("one", "two", "three"):
        build(script, name)
    chain = run_chain(repo, T01, auto=True)
    assert ids(chain) == [T01, T02, T03]
    assert chain.stop == STOP_EXHAUSTED


def test_module_switch_continues_across_steps(repo: Path, script: Script) -> None:
    setup_chain(repo, module_auto=True, s02_writes="writes: [src/other/]\n")
    for name in ("one", "two", "three"):
        build(script, name)
    build(script, "other", "src/other/other.py")
    chain = run_chain(repo, T01)
    assert ids(chain) == [T01, T02, T03, S02_T01]
    assert chain.ok, [(r.run.error, r.pr_error) for r in chain.runs]
    assert chain.stop == STOP_EXHAUSTED


def test_step_switch_keeps_the_chain_in_its_step(repo: Path, script: Script) -> None:
    """auto_continue on S01 only: the chain never starts the task of S02."""
    setup_chain(repo, step_auto=True, s02_writes="writes: [src/other/]\n")
    for name in ("one", "two", "three"):
        build(script, name)
    chain = run_chain(repo, T01)
    assert ids(chain) == [T01, T02, T03]
    assert (chain.stop, chain.waiting) == (STOP_EXHAUSTED, [])
    assert runs_of(repo, S02_T01) == []


def test_step_switched_off_is_passed_by(repo: Path, script: Script) -> None:
    """auto_continue on the project, off on S02: the chain does not start S02's task."""
    setup_chain(repo, module_auto=True, s02_writes="writes: [src/other/]\nauto_continue: false\n")
    for name in ("one", "two", "three"):
        build(script, name)
    chain = run_chain(repo, T01)
    assert ids(chain) == [T01, T02, T03]
    assert (chain.stop, chain.waiting) == (STOP_EXHAUSTED, [])
    assert runs_of(repo, S02_T01) == []


def test_dependent_task_stacks_on_the_open_pr(repo: Path, script: Script) -> None:
    write(repo, ".factory/config.yaml", "base: main\ndocs_root: .\nstacked_prs: true\n")
    setup_chain(repo, t02_depends=True)
    for name in ("one", "two", "three"):
        build(script, name)
    chain = run_chain(repo, T01, auto=True)
    assert ids(chain) == [T01, T02, T03]
    assert chain.ok and chain.waiting == []
    [stacked] = runs_of(repo, T02)
    assert stacked.stacked_on == runs_of(repo, T01)[0].branch


def test_dependent_task_skipped_until_approve(repo: Path, script: Script) -> None:
    setup_chain(repo, t02_depends=True)
    main_before = git(repo, "rev-parse", "main")
    build(script, "one")
    build(script, "three")
    chain = run_chain(repo, T01, auto=True)
    assert ids(chain) == [T01, T03]
    assert chain.ok and chain.stop == STOP_EXHAUSTED
    pr01 = open_pr(repo, T01)
    assert pr01 is not None
    assert chain.waiting == [Skip(T02, "waits_on_pr", f"{T01} (PR {pr01.url})", [T01])]
    assert runs_of(repo, T02) == []
    assert git(repo, "rev-parse", "main") == main_before
    with pytest.raises(TaskRunError) as info:
        run_task(repo, T02)
    assert info.value.code == "unmet_dependencies"

    approve_task(repo, T01)  # the operator, not the chain
    build(script, "two")
    chain = run_chain(repo, T02, auto=True)
    assert ids(chain) == [T02]
    assert chain.ok and chain.stop == STOP_EXHAUSTED
    assert [(s.task_id, s.reason) for s in chain.waiting] == [(T03, "in_review")]


def test_failure_stops_chain(repo: Path, script: Script, capsys: Capsys) -> None:
    setup_chain(repo)
    build(script, "one")
    build(script, "two", path="README.md")  # outside writes: the run fails
    build(script, "three")
    code = main(["task", "run", T01, "--repo", str(repo), "--auto", "--json"])
    env = read_envelope(capsys)
    assert code == 1
    assert env["ok"] is False
    assert env["error"]["code"] == "run_failed"
    data = env["data"]
    assert data["run"]["task_id"] == T01
    runs = data["chain"]["runs"]
    assert [r["run"]["task_id"] for r in runs] == [T01, T02]
    assert [r["ok"] for r in runs] == [True, False]
    assert data["chain"]["stop"] == STOP_FAILED
    assert runs_of(repo, T03) == []


def test_task_that_cannot_start_is_reported(repo: Path, script: Script) -> None:
    setup_chain(repo, s02_writes="writes: []\n")  # S02 has no writes: its task cannot start
    for name in ("one", "two", "three"):
        build(script, name)
    chain = run_chain(repo, T01, auto=True)
    assert ids(chain) == [T01, T02, T03]
    assert chain.stop == STOP_EXHAUSTED
    assert [(s.task_id, s.reason) for s in chain.waiting] == [(S02_T01, "cannot_start")]
    assert chain.waiting[0].detail.startswith("no_writes:")


def test_task_without_workflow_is_skipped(repo: Path, script: Script) -> None:
    setup_chain(repo, t02_extra="workflow: null\n")
    build(script, "one")
    build(script, "three")
    chain = run_chain(repo, T01, auto=True)
    assert ids(chain) == [T01, T03]
    assert chain.ok and chain.stop == STOP_EXHAUSTED
    assert chain.waiting == [Skip(T02, "no_workflow", "bez workflow")]
    assert runs_of(repo, T02) == []


def test_persons_task_is_skipped(repo: Path, script: Script) -> None:
    setup_chain(repo, t02_extra="assignee: human\n")
    build(script, "one")
    build(script, "three")
    chain = run_chain(repo, T01, auto=True)
    assert ids(chain) == [T01, T03]
    assert chain.waiting == [Skip(T02, "human_task", "pro člověka")]
    assert runs_of(repo, T02) == []


def test_step_without_workflow_is_skipped(repo: Path, script: Script) -> None:
    # The module has `workflow: plan-commit`; `null` on the step wins for its tasks.
    setup_chain(repo, s02_writes="writes: [src/other/]\nworkflow: null\n")
    for name in ("one", "two", "three"):
        build(script, name)
    chain = run_chain(repo, T01, auto=True)
    assert ids(chain) == [T01, T02, T03]
    assert chain.stop == STOP_EXHAUSTED
    assert chain.waiting == [Skip(S02_T01, "no_workflow", "bez workflow")]
    assert runs_of(repo, S02_T01) == []


def test_first_run_error_propagates(repo: Path, script: Script) -> None:
    setup_chain(repo)
    with pytest.raises(TaskRunError) as info:
        run_chain(repo, "M01-S01-T99", auto=True)
    assert info.value.code == "unknown_task"


def test_select_next_rules(repo: Path) -> None:
    shutil.rmtree(repo / CORE / "S01-model")
    _index(repo, "S01-model", "M01-S01", "writes: [src/app/]\n")
    _index(repo, "S02-other", "M01-S02", "writes: [src/other/]\n")
    _task(repo, "S02-other", S02_T01)  # another step of the module: comes last
    _task(repo, "S01-model", T01)
    _task(repo, "S01-model", T02, depends_on=[T01])  # T01 has a PR -> waits_on_pr
    _task(repo, "S01-model", T03, depends_on=["M01-S01-T09"])  # T09 no PR -> blocked
    _task(repo, "S01-model", "M01-S01-T04")  # own PR -> in_review
    _task(repo, "S01-model", "M01-S01-T05")  # running
    _task(repo, "S01-model", "M01-S01-T06", extra="workflow: null\n")  # no workflow
    _task(repo, "S01-model", "M01-S01-T09")  # ready, the first startable one
    backlog = load_backlog(repo)
    after = backlog.by_id[T01]
    assert isinstance(after, Task)
    pr = TaskPrRow("b", "x", "local", "b", "URL", "main", "0", "t", "", "open", "", "")
    prs = {T01: pr, "M01-S01-T04": pr}
    row = TaskRunRow("r1", "M01-S01-T05", "br", "wt", "main", "0", None, "running", "")

    def running(tid: str) -> TaskRunRow | None:
        return row if tid == "M01-S01-T05" else None

    sel = select_next(backlog, after, open_pr=prs.get, running=running)
    assert sel.next is not None and sel.next.id == "M01-S01-T09"
    assert [(s.task_id, s.reason) for s in sel.skipped] == [
        (T02, "waits_on_pr"),
        (T03, "blocked"),
        ("M01-S01-T04", "in_review"),
        ("M01-S01-T05", "running"),
        ("M01-S01-T06", "no_workflow"),
    ]
    assert sel.skipped[0].waits_on == [T01]
    assert sel.skipped[-1].detail == "bez workflow"
    sel = select_next(backlog, after, open_pr=prs.get, running=running, exclude={"M01-S01-T09"})
    assert sel.next is not None and sel.next.id == S02_T01
    # without --auto only tasks with auto_continue: true are candidates; none has it here
    sel = select_next(backlog, after, open_pr=prs.get, running=running, require_auto_continue=True)
    assert (sel.next, sel.skipped) == (None, [])


# ── CLI ──────────────────────────────────────────────────────────────────────


def test_cli_auto_json(repo: Path, script: Script, capsys: Capsys) -> None:
    setup_chain(repo)
    for name in ("one", "two", "three"):
        build(script, name)
    code = main(["task", "run", T01, "--repo", str(repo), "--auto", "--json"])
    env = read_envelope(capsys)
    assert code == 0, env
    assert env["ok"] is True
    data = env["data"]
    assert data["run"]["task_id"] == T01
    assert data["pr"] is not None and data["pr_error"] is None
    assert [r["run"]["task_id"] for r in data["chain"]["runs"]] == [T01, T02, T03]
    assert data["chain"]["stop"] == STOP_EXHAUSTED
    assert data["chain"]["waiting"] == []


def test_cli_without_auto_json_has_chain(repo: Path, script: Script, capsys: Capsys) -> None:
    setup_chain(repo)
    build(script, "one")
    code = main(["task", "run", T01, "--repo", str(repo), "--json"])
    data = read_envelope(capsys)["data"]
    assert code == 0, data
    assert [r["run"]["task_id"] for r in data["chain"]["runs"]] == [T01]
    assert data["chain"]["stop"] == STOP_DISABLED


def test_cli_auto_text_reports_waiting(repo: Path, script: Script, capsys: Capsys) -> None:
    setup_chain(repo, t02_depends=True)
    build(script, "one")
    build(script, "three")
    code = main(["task", "run", T01, "--repo", str(repo), "--auto"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "auto-continue: stopped (exhausted)" in out
    assert f"waiting: {T02} waits_on_pr: {T01} (PR " in out


def test_cli_auto_text_reports_task_without_workflow(
    repo: Path, script: Script, capsys: Capsys
) -> None:
    setup_chain(repo, t02_extra="workflow: null\n")
    build(script, "one")
    build(script, "three")
    code = main(["task", "run", T01, "--repo", str(repo), "--auto"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert f"waiting: {T02} no_workflow: bez workflow" in out


# ── kanban queue: order and exclusion ────────────────────────────────────────


def _queue_backlog(repo: Path) -> Any:
    shutil.rmtree(repo / CORE / "S01-model")
    _index(repo, "S01-model", "M01-S01", "writes: [src/app/]\n")
    _index(repo, "S02-other", "M01-S02", "writes: [src/other/]\n")
    _task(repo, "S01-model", T01)
    _task(repo, "S01-model", T02)
    _task(repo, "S01-model", T03)
    _task(repo, "S02-other", S02_T01)
    return load_backlog(repo)


def _none(_tid: str) -> None:
    return None


def test_select_next_takes_the_kanban_order_across_steps(repo: Path) -> None:
    backlog = _queue_backlog(repo)
    after = backlog.by_id[T01]
    assert isinstance(after, Task)
    prefs = QueuePrefs(order=(S02_T01, T03))
    sel = select_next(backlog, after, open_pr=_none, running=_none, prefs=prefs)
    assert sel.next is not None and sel.next.id == S02_T01
    sel = select_next(backlog, after, open_pr=_none, running=_none, exclude={S02_T01}, prefs=prefs)
    assert sel.next is not None and sel.next.id == T03
    # unranked tasks follow in backlog order; unknown ids in the order are ignored
    prefs = QueuePrefs(order=("M09-S01-T01", T03))
    sel = select_next(backlog, after, open_pr=_none, running=_none, exclude={T03}, prefs=prefs)
    assert sel.next is not None and sel.next.id == T02


def test_select_next_skips_an_excluded_task_with_auto_too(repo: Path) -> None:
    backlog = _queue_backlog(repo)
    after = backlog.by_id[T01]
    assert isinstance(after, Task)
    prefs = QueuePrefs(excluded=frozenset({T02}))
    sel = select_next(
        backlog, after, open_pr=_none, running=_none, require_auto_continue=False, prefs=prefs
    )
    assert sel.next is not None and sel.next.id == T03
    assert [(s.task_id, s.reason) for s in sel.skipped] == [(T02, "excluded")]
    assert "excluded" in SKIP_REASONS


def test_chain_runs_in_the_kanban_order(repo: Path, script: Script) -> None:
    setup_chain(repo, step_auto=True)
    store = _store(repo)
    try:
        store.set_queue_order([T03, T02])
    finally:
        store.close()
    for name in ("one", "three", "two"):
        build(script, name)
    chain = run_chain(repo, T01)
    assert ids(chain) == [T01, T03, T02]
    assert chain.stop == STOP_EXHAUSTED


def test_chain_never_starts_an_excluded_task(repo: Path, script: Script) -> None:
    setup_chain(repo)
    store = _store(repo)
    try:
        store.set_excluded(T02, True)
    finally:
        store.close()
    for name in ("one", "three"):
        build(script, name)
    chain = run_chain(repo, T01, auto=True)
    assert ids(chain) == [T01, T03]
    assert runs_of(repo, T02) == []
    assert [(s.task_id, s.reason) for s in chain.waiting] == [(T02, "excluded")]


def test_an_excluded_task_still_runs_by_hand(repo: Path, script: Script) -> None:
    setup_chain(repo)
    store = _store(repo)
    try:
        store.set_excluded(T01, True)
    finally:
        store.close()
    build(script, "one")
    result = run_task(repo, T01)
    assert result.ok


# ── a run blocked during its course (HAIFA-REFINEMENT-T34) ───────────────────

BLOCKER = "M01-TODO-T01"
OTHER = "M02-S01-T01"


def _todo_step(repo: Path, extra: str) -> None:
    """The project's TODO step (followups.TODO_CODE) the blocker is filed into."""
    write(repo, f"{CORE}/TODO/index.md", f"---\nid: M01-TODO\ntitle: TODO\n{extra}---\n")


def blocked_build(script: Script, name: str) -> None:
    """One planner call that writes a file and reports a follow-up that blocks the task."""
    rel = f"src/app/{name}.py"
    script.on("planner", lambda wt: write(wt, rel, f"NAME = {name!r}\n"))
    blocker = {
        "title": "Blokující práce",
        "reason": "chybí předpoklad",
        "details": "Doplnit předpoklad.",
        "blocks_task": True,
    }
    script.add(
        "planner",
        ok(artifacts=[], changed_files=[rel], commit_message=f"Add {name}", follow_ups=[blocker]),
    )


def test_blocked_task_continues_with_its_blocker(repo: Path, script: Script) -> None:
    setup_chain(repo, module_auto=True)
    _todo_step(repo, "writes: [src/todo/]\n")
    commit_all(repo, "todo step")
    blocked_build(script, "one")
    build(script, "blocker", path="src/todo/blocker.py")
    build(script, "two")
    build(script, "three")
    chain = run_chain(repo, T01)
    first = chain.runs[0]
    assert first.run.state == "failed" and first.pr is None
    assert task_mod.run_blockers(first.run) == [BLOCKER]
    # a blocked run is the failure kind blocked, its blockers in the detail
    assert first.run.shown_failure_kind == "blocked"
    assert first.run.failure_detail_dict() == {"blockers": [BLOCKER]}
    # the blocker goes before the rest of the step, then the usual order
    assert ids(chain) == [T01, BLOCKER, T02, T03]
    assert chain.stop == STOP_EXHAUSTED
    assert [r.ok for r in chain.runs] == [False, True, True, True]
    assert (T01, "blocked") in [(s.task_id, s.reason) for s in chain.waiting]
    assert open_pr(repo, T01) is None


def test_blocked_task_without_startable_blocker_takes_the_next(repo: Path, script: Script) -> None:
    setup_chain(repo, module_auto=True)
    _todo_step(repo, "writes: [src/todo/]\nworkflow: null\n")  # the blocker cannot run
    commit_all(repo, "todo step")
    blocked_build(script, "one")
    build(script, "two")
    build(script, "three")
    chain = run_chain(repo, T01)
    assert ids(chain) == [T01, T02, T03]
    assert chain.stop == STOP_EXHAUSTED
    reasons = [(s.task_id, s.reason) for s in chain.waiting]
    assert (T01, "blocked") in reasons and (BLOCKER, "no_workflow") in reasons
    assert runs_of(repo, BLOCKER) == []


def test_blocked_task_with_nothing_else_is_exhausted(repo: Path, script: Script) -> None:
    setup_chain(repo, module_auto=True)
    _todo_step(repo, "writes: [src/todo/]\nworkflow: null\n")
    commit_all(repo, "todo step")
    store = _store(repo)
    try:
        store.set_excluded(T02, True)
        store.set_excluded(T03, True)
    finally:
        store.close()
    blocked_build(script, "one")
    chain = run_chain(repo, T01)
    assert ids(chain) == [T01]
    assert chain.stop == STOP_EXHAUSTED
    assert (T01, "blocked") in [(s.task_id, s.reason) for s in chain.waiting]


def test_blocked_task_without_auto_continue_stops(repo: Path, script: Script) -> None:
    setup_chain(repo)
    _todo_step(repo, "writes: [src/todo/]\n")
    commit_all(repo, "todo step")
    blocked_build(script, "one")
    chain = run_chain(repo, T01)
    assert ids(chain) == [T01]
    assert chain.stop == STOP_FAILED
    assert runs_of(repo, BLOCKER) == [] and runs_of(repo, T02) == []


def test_blocked_task_with_auto_flag_continues(repo: Path, script: Script) -> None:
    setup_chain(repo)
    _todo_step(repo, "writes: [src/todo/]\n")
    commit_all(repo, "todo step")
    blocked_build(script, "one")
    build(script, "blocker", path="src/todo/blocker.py")
    build(script, "two")
    build(script, "three")
    chain = run_chain(repo, T01, auto=True)
    assert ids(chain) == [T01, BLOCKER, T02, T03]
    assert chain.stop == STOP_EXHAUSTED


def test_other_failure_still_stops_the_chain(repo: Path, script: Script) -> None:
    setup_chain(repo, module_auto=True)
    build(script, "one", path="README.md")  # outside writes: the run fails, not blocked
    chain = run_chain(repo, T01)
    assert ids(chain) == [T01]
    assert task_mod.run_blockers(chain.runs[0].run) is None
    assert chain.runs[0].run.shown_failure_kind != "blocked"
    assert chain.stop == STOP_FAILED


def test_run_blockers_reads_the_error() -> None:
    row = TaskRunRow("r", T01, "b", "wt", "main", "0", None, "failed", "now")
    assert task_mod.run_blockers(row) is None
    reason = task_mod.blocked_reason(T01, ["A-T01", "B-T02"])
    blocked = TaskRunRow(
        "r", T01, "b", "wt", "main", "0", None, "failed", "now", error=f"{reason}; boom"
    )
    assert task_mod.run_blockers(blocked) == ["A-T01", "B-T02"]
    succeeded = TaskRunRow("r", T01, "b", "wt", "main", "0", None, "succeeded", "now", error=reason)
    assert task_mod.run_blockers(succeeded) is None


def _other_project(repo: Path) -> None:
    write(
        repo,
        "backlog/M02-other/index.md",
        "---\nid: M02\ntitle: Other\nworkflow: plan-commit\nauto_continue: true\n---\n",
    )
    write(
        repo,
        "backlog/M02-other/S01-x/index.md",
        "---\nid: M02-S01\ntitle: X\nwrites: [src/other/]\n---\n",
    )
    write(
        repo,
        f"backlog/M02-other/S01-x/{OTHER}.md",
        f"---\nid: {OTHER}\ntitle: Other\nstatus: todo\n---\n\nDo it.\n",
    )


def test_chain_never_starts_a_queued_task_of_another_project(repo: Path, script: Script) -> None:
    setup_chain(repo, module_auto=True)
    _other_project(repo)
    commit_all(repo, "other project")
    store = _store(repo)
    try:
        store.set_queue_order([OTHER, T03])
    finally:
        store.close()
    for name in ("one", "three", "two"):
        build(script, name)
    chain = run_chain(repo, T01, auto=True)
    assert ids(chain) == [T01, T03, T02]
    assert runs_of(repo, OTHER) == []


def test_blockers_of_keeps_only_follow_ups_of_the_project(repo: Path) -> None:
    _other_project(repo)
    _todo_step(repo, "")
    marker = "<!-- factory: follow-up-of=" + T01 + " -->"
    write(
        repo,
        f"{CORE}/TODO/{BLOCKER}.md",
        f"---\nid: {BLOCKER}\ntitle: B\nstatus: todo\n---\n\nB.\n\n{marker}\n",
    )
    body = (repo / f"backlog/M02-other/S01-x/{OTHER}.md").read_text(encoding="utf-8")
    write(repo, f"backlog/M02-other/S01-x/{OTHER}.md", body + f"\n{marker}\n")
    backlog = load_backlog(repo)
    after = backlog.by_id[T01]
    assert isinstance(after, Task)
    found = blockers_of(backlog, after, [OTHER, T02, BLOCKER, "(neuložený task: X)", BLOCKER])
    assert found == [BLOCKER]
    # even preferred, a task of another project is never selected
    sel = select_next(backlog, after, open_pr=_none, running=_none, prefer=[OTHER])
    assert sel.next is not None and sel.next.id != OTHER
