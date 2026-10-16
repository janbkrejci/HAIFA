"""Self-healing of an auto-continue chain (``run.heal``): the safe action by failure kind.

Fake harnesses only, provider local. ``quota`` continues on the fallback harness,
``process_gone`` is retried once, ``nothing_to_do`` with a reason closes its task; every
action is a chain event. ``auto_heal: false`` switches all of them off.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from run_repo import Script, commit_all, fake_env, make_run_repo, ok, write

from aifactory import failure
from aifactory.backlog import Task, load_backlog
from aifactory.engine.utils import now_iso
from aifactory.run import (
    STOP_EXHAUSTED,
    STOP_FAILED,
    ChainResult,
    TaskPrRow,
    TaskRunRow,
    TaskRunStore,
    run_chain,
)
from aifactory.run import task as task_mod
from aifactory.run.heal import (
    ACTION_CLOSE,
    ACTION_FALLBACK,
    ACTION_RETRY,
    auto_heal_enabled,
    switch_text,
)
from aifactory.run.store import ABORTED, FAILED, SUCCEEDED

T01, T02 = "M01-S01-T01", "M01-S01-T02"
STEP = "backlog/M01-core/S01-model"
AGENTS = (
    "defaults:\n  harness: codex\n  model: gpt-6.1-sol\n"
    "  fallback:\n    harness: claude\n    model: claude-opus-5-5\n"
    "agents:\n  - name: planner\n  - name: builder\n  - name: tester\n  - name: documenter\n"
)


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


def _repo(tmp_path: Path, *, harness: str = "claude", heal: bool | None = None) -> Path:
    """T01 and T02 (independent) in step S01 with auto-continue on."""
    repo = make_run_repo(tmp_path / "repo", harness)
    flag = "" if heal is None else f"auto_heal: {'true' if heal else 'false'}\n"
    write(
        repo,
        f"{STEP}/index.md",
        f"---\nid: M01-S01\ntitle: Model\nwrites: [src/app/]\nauto_continue: true\n{flag}---\n",
    )
    write(
        repo,
        f"{STEP}/M01-S01-T02-loader.md",
        f"---\nid: {T02}\ntitle: Loader\nstatus: todo\n---\n\n## Zadání\nNačíst data.\n",
    )
    if harness == "codex":
        write(repo, ".factory/agents.yaml", AGENTS)
    commit_all(repo, "chain backlog")
    return repo


def _build(script: Script, name: str) -> None:
    rel = f"src/app/{name}.py"
    script.on("planner", lambda wt: write(wt, rel, f"NAME = {name!r}\n"))
    script.add("planner", ok(artifacts=[], changed_files=[rel], commit_message=f"Add {name}"))


def _crash(wt: Path) -> None:
    raise RuntimeError("the harness crashed")


def _exhausted(wt: Path) -> None:
    raise failure.QuotaExhausted("codex", "You've hit your usage limit")


def _nothing_to_do(script: Script, summary: str) -> None:
    script.on("planner", lambda wt: None)
    script.add("planner", {"status": "fail", "summary": summary, "fail_kind": "nothing_to_do"})


def _status(repo: Path, task_id: str) -> str:
    task = load_backlog(repo).by_id[task_id]
    assert isinstance(task, Task)
    return task.status


def _chain_events(repo: Path) -> list[dict[str, Any]]:
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        rows = store.chains()
    finally:
        store.close()
    assert len(rows) == 1
    return rows[0].event_list()


def _ids(chain: ChainResult) -> list[str]:
    return [r.run.task_id for r in chain.runs]


def _process_dies_once(monkeypatch: pytest.MonkeyPatch, repo: Path) -> None:
    """The first run of T01 ends as if its process had died (reaped as process_gone)."""
    real = task_mod.run_task
    done: list[bool] = []

    def run(*args: Any, **kwargs: Any) -> task_mod.TaskRunResult:
        result = real(*args, **kwargs)
        if done or result.run.task_id != T01:
            return result
        done.append(True)
        store = TaskRunStore(result.trace_db)
        try:
            store.conn.execute(
                "UPDATE task_runs SET state = ?, failure_kind = ?, failure_detail = ? "
                "WHERE run_id = ?",
                (ABORTED, failure.PROCESS_GONE, json.dumps({"pid": 1}), result.run.run_id),
            )
            row = store.get(result.run.run_id)
        finally:
            store.close()
        assert row is not None
        return replace(result, run=row)

    monkeypatch.setattr(task_mod, "run_task", run)


# ── quota ────────────────────────────────────────────────────────────────────


def test_quota_continues_on_the_fallback_and_the_chain_goes_on(
    tmp_path: Path, script: Script
) -> None:
    repo = _repo(tmp_path, harness="codex")
    script.on("planner", _exhausted, lambda wt: write(wt, "src/app/one.py", "ONE = 1\n"))
    script.add("planner", ok(), ok(artifacts=[], changed_files=["src/app/one.py"]))
    _build(script, "two")

    chain = run_chain(repo, T01)

    assert _ids(chain) == [T01, T02]
    assert chain.ok and chain.stop == STOP_EXHAUSTED
    assert [c.harness for c in script.calls if c.agent == "planner"] == ["codex", "claude", "codex"]
    (event,) = chain.events
    assert (event["action"], event["failure_kind"], event["ok"]) == (ACTION_FALLBACK, "quota", True)
    assert event["text"] == "Factory pokračovala na Claude Code po vyčerpání kvóty Codexu"
    assert (event["task_id"], event["run_id"]) == (T01, chain.runs[0].run.run_id)
    assert _chain_events(repo) == chain.events


def test_quota_without_auto_heal_does_not_switch(tmp_path: Path, script: Script) -> None:
    repo = _repo(tmp_path, harness="codex", heal=False)
    script.on("planner", _exhausted)
    script.add("planner", ok())

    chain = run_chain(repo, T01)

    assert _ids(chain) == [T01] and chain.stop == STOP_FAILED
    assert chain.runs[0].run.failure_kind == failure.QUOTA
    assert [c.harness for c in script.calls if c.agent == "planner"] == ["codex"]
    assert chain.events == []
    assert any("auto_heal is off" in w for w in chain.runs[0].warnings)


# ── process_gone ─────────────────────────────────────────────────────────────


def test_process_gone_is_retried_once_and_the_chain_goes_on(
    tmp_path: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    script.on("planner", _crash)
    script.add("planner", ok())
    _build(script, "one")
    _build(script, "two")
    _process_dies_once(monkeypatch, repo)

    chain = run_chain(repo, T01)

    assert _ids(chain) == [T01, T02]
    assert chain.ok and chain.stop == STOP_EXHAUSTED
    first = chain.runs[0].run
    assert first.state == SUCCEEDED and len(first.retry_list()) == 1
    (event,) = chain.events
    assert (event["action"], event["failure_kind"], event["ok"]) == (
        ACTION_RETRY,
        failure.PROCESS_GONE,
        True,
    )
    assert event["text"] == f"Factory zopakovala běh {first.run_id} po pádu procesu"
    assert _chain_events(repo) == chain.events


def test_process_gone_retry_that_fails_stops_the_chain(
    tmp_path: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    script.on("planner", _crash, _crash)
    script.add("planner", ok(), ok())
    _process_dies_once(monkeypatch, repo)

    chain = run_chain(repo, T01)

    assert _ids(chain) == [T01] and chain.stop == STOP_FAILED
    assert chain.runs[0].run.state == FAILED
    assert len(chain.runs[0].run.retry_list()) == 1  # retried once, not again
    (event,) = chain.events
    assert (event["action"], event["ok"]) == (ACTION_RETRY, False)
    assert "opakování selhalo" in event["text"]


def test_process_gone_without_auto_heal_is_not_retried(
    tmp_path: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path, heal=False)
    script.on("planner", _crash)
    script.add("planner", ok())
    _process_dies_once(monkeypatch, repo)

    chain = run_chain(repo, T01)

    assert _ids(chain) == [T01] and chain.stop == STOP_FAILED
    assert chain.runs[0].run.state == ABORTED
    assert chain.runs[0].run.retry_list() == []
    assert chain.events == [] and _chain_events(repo) == []


# ── nothing_to_do ────────────────────────────────────────────────────────────


def test_nothing_to_do_with_a_reason_closes_the_task_and_goes_on(
    tmp_path: Path, script: Script
) -> None:
    repo = _repo(tmp_path)
    _nothing_to_do(script, "the schema is in base already (commit abc1234)")
    _build(script, "two")

    chain = run_chain(repo, T01)

    assert _ids(chain) == [T01, T02]
    assert chain.ok and chain.stop == STOP_EXHAUSTED
    assert chain.runs[0].closed_by_heal and chain.runs[0].pr is None
    assert _status(repo, T01) == "done"
    task = load_backlog(repo).by_id[T01]
    assert isinstance(task, Task) and "bez změn" in task.body
    (event,) = chain.events
    assert (event["action"], event["failure_kind"], event["ok"]) == (
        ACTION_CLOSE,
        failure.NOTHING_TO_DO,
        True,
    )
    assert event["text"].startswith(f"Factory uzavřela task {T01} jako hotový bez změn: ")
    assert "abc1234" in event["text"]


def test_nothing_to_do_without_a_reason_is_left_to_the_operator(
    tmp_path: Path, script: Script
) -> None:
    repo = _repo(tmp_path)
    _nothing_to_do(script, "")

    chain = run_chain(repo, T01)

    assert _ids(chain) == [T01] and chain.stop == STOP_FAILED
    assert _status(repo, T01) == "todo"
    assert chain.events == []


def test_nothing_to_do_without_auto_heal_stops_the_chain(tmp_path: Path, script: Script) -> None:
    repo = _repo(tmp_path, heal=False)
    _nothing_to_do(script, "only the front matter must change")

    chain = run_chain(repo, T01)

    assert _ids(chain) == [T01] and chain.stop == STOP_FAILED
    assert not chain.ok
    assert _status(repo, T01) == "todo"
    assert chain.events == []


# ── other kinds, settings and texts ──────────────────────────────────────────


def test_other_failure_is_left_to_the_operator(tmp_path: Path, script: Script) -> None:
    repo = _repo(tmp_path)
    script.on("planner", _crash)
    script.add("planner", ok())

    chain = run_chain(repo, T01)

    assert _ids(chain) == [T01] and chain.stop == STOP_FAILED
    assert chain.runs[0].run.retry_list() == []
    assert chain.events == []


def test_auto_heal_is_inherited_and_on_by_default(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    task = load_backlog(repo).by_id[T01]
    assert isinstance(task, Task) and auto_heal_enabled(task)
    off = _repo(tmp_path / "off", heal=False)
    task = load_backlog(off).by_id[T01]
    assert isinstance(task, Task) and not auto_heal_enabled(task)


def test_switch_text_names_the_harnesses() -> None:
    record = {"from": {"harness": "codex"}, "to": {"harness": "claude"}}
    assert switch_text(record) == "Factory pokračovala na Claude Code po vyčerpání kvóty Codexu"
    other = {"from": {"harness": "claude"}, "to": {"harness": "pi"}}
    assert switch_text(other) == "Factory pokračovala na pi po vyčerpání kvóty Claude Code"


# ── parallel chain (max_parallel_runs above 1) ───────────────────────────────


class _Runner:
    """Claims a `running` row on start; `wait_any` ends the oldest run as `endings` say.

    A run without an ending succeeds with a merged PR (its slot frees).
    """

    def __init__(self, repo: Path, endings: dict[str, tuple[str, str, dict[str, Any]]]) -> None:
        self.db = repo / ".factory" / "trace.db"
        self.endings = endings
        self.rows: dict[str, TaskRunRow] = {}
        self.started: list[str] = []

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
        store = TaskRunStore(self.db)
        try:
            store.claim(row)
        finally:
            store.close()
        self.rows[task_id] = row
        self.started.append(task_id)
        return row

    def wait_any(self) -> task_mod.TaskRunResult:
        task_id = next(iter(self.rows))
        row = self.rows.pop(task_id)
        ending = self.endings.pop(task_id, None)
        return _end(self.db, row, ending)


def _end(
    db: Path, row: TaskRunRow, ending: tuple[str, str, dict[str, Any]] | None
) -> task_mod.TaskRunResult:
    store = TaskRunStore(db)
    try:
        pr = None
        if ending is None:
            store.finish(row.run_id, SUCCEEDED, "abc", None)
            now = str(now_iso())
            pr = TaskPrRow(
                row.branch, row.task_id, "local", "1", f"URL-{row.task_id}", "main", "0", "t",
                "", "merged", now, now, merged_at=now,
            )  # fmt: skip
            store.save_pr(pr)
        else:
            state, kind, detail = ending
            store.finish(row.run_id, FAILED, "abc", "boom", kind, detail)
            if state == ABORTED:
                store.conn.execute(
                    "UPDATE task_runs SET state = ? WHERE run_id = ?", (ABORTED, row.run_id)
                )
        final = store.get(row.run_id)
    finally:
        store.close()
    assert final is not None
    return task_mod.TaskRunResult(run=final, workflow_run=None, warnings=(), trace_db=db, pr=pr)


def _parallel_repo(tmp_path: Path, heal: bool | None = None) -> Path:
    repo = _repo(tmp_path, heal=heal)
    write(repo, ".factory/config.yaml", "base: main\ndocs_root: .\nmax_parallel_runs: 2\n")
    commit_all(repo, "two slots")
    return repo


def test_parallel_chain_retries_a_dead_member_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.run import retry as retry_mod

    repo = _parallel_repo(tmp_path)
    runner = _Runner(repo, {T01: (ABORTED, failure.PROCESS_GONE, {"pid": 1})})
    retried: list[str] = []

    def fake_retry(repo_: Path, task_id: str, **kwargs: Any) -> task_mod.TaskRunResult:
        retried.append(str(kwargs.get("run_id")))
        store = TaskRunStore(runner.db)
        try:
            row = store.reclaim(str(kwargs["run_id"]), os.getpid(), {"started_at": now_iso()})
        finally:
            store.close()
        return _end(runner.db, row, None)

    monkeypatch.setattr(retry_mod, "retry_run", fake_retry)

    chain = run_chain(repo, T01, runner=runner, pr_files=lambda pr: [])

    assert retried == [f"r-{T01}"]
    assert sorted(_ids(chain)) == [T01, T02] and chain.stop == STOP_EXHAUSTED
    assert chain.ok
    (event,) = chain.events
    assert (event["action"], event["ok"]) == (ACTION_RETRY, True)
    assert _chain_events(repo) == chain.events


def test_parallel_chain_closes_nothing_to_do(tmp_path: Path) -> None:
    detail = {"agent": "builder", "summary": "done in abc1234", "fail_kind": "nothing_to_do"}
    repo = _parallel_repo(tmp_path)
    runner = _Runner(repo, {T01: (FAILED, failure.NOTHING_TO_DO, detail)})

    chain = run_chain(repo, T01, runner=runner, pr_files=lambda pr: [])

    assert sorted(_ids(chain)) == [T01, T02] and chain.stop == STOP_EXHAUSTED
    assert _status(repo, T01) == "done"
    (event,) = chain.events
    assert (event["action"], event["ok"]) == (ACTION_CLOSE, True)


def test_parallel_chain_without_auto_heal_stops(tmp_path: Path) -> None:
    detail = {"agent": "builder", "summary": "done in abc1234", "fail_kind": "nothing_to_do"}
    repo = _parallel_repo(tmp_path, heal=False)
    runner = _Runner(repo, {T01: (FAILED, failure.NOTHING_TO_DO, detail)})

    chain = run_chain(repo, T01, runner=runner, pr_files=lambda pr: [])

    assert chain.stop == STOP_FAILED
    assert _status(repo, T01) == "todo"
    assert chain.events == []
