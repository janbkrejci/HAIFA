"""Repos with a backlog and a trace DB for the ``/api/overview`` tests (no model, no network).

``make_overview_repo`` builds a repo with six tasks: ``T_RUN`` running (live pid, phase
``build`` attempt 2, cost 0.42), ``T_REV`` with an open PR, ``T_FAIL`` whose newest run
failed, ``T_DONE`` (failed, but ``done``), ``T_CANC`` (aborted, but ``cancelled``) and
``T_DEAD`` running under a pid that has ended. The fixture may use ``TaskRunStore``; the
overview never does.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from multi_repo import AGENTS, commit_all, init_repo, write

from aifactory.engine.tracer import SCHEMA
from aifactory.run.store import TaskPrRow, TaskRunRow, TaskRunStore
from aifactory.web.registry import Registry

T_RUN = "M01-S01-T01"
T_REV = "M01-S01-T02"
T_FAIL = "M01-S01-T03"
T_DONE = "M01-S01-T04"
T_CANC = "M01-S01-T05"
T_DEAD = "M01-S01-T06"

TITLES = {
    T_RUN: ("Runner", "todo"),
    T_REV: ("Reviewed", "todo"),
    T_FAIL: ("Failing", "todo"),
    T_DONE: ("Finished", "done"),
    T_CANC: ("Dropped", "cancelled"),
    T_DEAD: ("Orphan", "todo"),
}

PR_URL = "https://example.test/pr/7"


def _backlog(root: Path) -> None:
    write(
        root, "backlog/M01-core/index.md", "---\nid: M01\ntitle: Core\nworkflow: plan-commit\n---\n"
    )
    write(
        root,
        "backlog/M01-core/S01-model/index.md",
        "---\nid: M01-S01\ntitle: Model\nwrites: [src/app/]\n---\n",
    )
    for task_id, (title, status) in TITLES.items():
        write(
            root,
            f"backlog/M01-core/S01-model/{task_id}-{title.lower()}.md",
            f"---\nid: {task_id}\ntitle: {title}\nstatus: {status}\n---\n\n## Zadání\n{title}.\n",
        )


def make_installed_repo(path: Path, *, config: str = "base: main\n") -> Path:
    """A git repo on ``main`` with committed ``.factory/`` config and the backlog; no trace DB."""
    root = init_repo(path)
    write(root, ".factory/config.yaml", config)
    write(root, ".factory/agents.yaml", AGENTS)
    write(root, ".factory/prompts/builder/system.md", "You build.\n")
    write(root, ".factory/prompts/builder/user.md", "Build it.\n")
    write(root, ".gitignore", ".factory/trace.db*\n")
    _backlog(root)
    commit_all(root, "factory")
    return root


def _row(run_id: str, task_id: str, day: int, pid: int | None) -> TaskRunRow:
    return TaskRunRow(
        run_id=run_id,
        task_id=task_id,
        branch=f"factory/{task_id}-{run_id}",
        worktree=f"/tmp/wt/{run_id}",
        base="main",
        base_sha="0" * 40,
        head_sha=None,
        state="running",
        started_at=f"2026-01-{day:02d}T10:00:00+00:00",
        pid=pid,
        workflow="build-test-review",
    )


def _ended(store: TaskRunStore, run_id: str, state: str, error: str | None, day: int) -> None:
    store.finish(run_id, state, None, error)
    store.conn.execute(
        "UPDATE task_runs SET ended_at = ? WHERE run_id = ?",
        (f"2026-01-{day:02d}T11:00:00+00:00", run_id),
    )


def make_overview_repo(path: Path, *, live_pid: int, dead_pid: int, prefix: str = "") -> Path:
    """An installed repo with the trace DB described in the module docstring."""
    root = make_installed_repo(path)
    db = root / ".factory" / "trace.db"
    store = TaskRunStore(db)
    p = prefix
    store.claim(_row(f"{p}r-rev", T_REV, 1, live_pid))
    _ended(store, f"{p}r-rev", "succeeded", None, 1)
    store.save_pr(
        TaskPrRow(
            branch=f"factory/{T_REV}-{p}r-rev",
            task_id=T_REV,
            provider="local",
            pr_id="7",
            url=PR_URL,
            base="main",
            base_sha="0" * 40,
            title="Reviewed",
            body="",
            state="open",
            created_at="2026-01-01T11:00:00+00:00",
            updated_at="2026-01-01T11:00:00+00:00",
        )
    )
    store.claim(_row(f"{p}r-fail-old", T_FAIL, 2, live_pid))
    _ended(store, f"{p}r-fail-old", "succeeded", None, 2)
    store.claim(_row(f"{p}r-fail", T_FAIL, 3, live_pid))
    _ended(store, f"{p}r-fail", "failed", "accept not met", 3)
    store.claim(_row(f"{p}r-done", T_DONE, 4, live_pid))
    _ended(store, f"{p}r-done", "failed", "boom", 4)
    store.claim(_row(f"{p}r-canc", T_CANC, 5, live_pid))
    _ended(store, f"{p}r-canc", "aborted", "stopped", 5)
    store.claim(_row(f"{p}r-dead", T_DEAD, 6, dead_pid))
    store.claim(_row(f"{p}r-run", T_RUN, 7, live_pid))
    store.close()

    conn = sqlite3.connect(str(db), isolation_level=None)
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO sessions (adw_id, adw_name, status, engineer, started_at, total_tokens, "
        "total_cost) VALUES (?, 'factory', 'running', 'tester', ?, 1200, 0.42)",
        (f"{p}r-run", "2026-01-07T10:00:00+00:00"),
    )
    for phase_id, seq, name, status, attempt in (
        ("p2", 2, "build", "running", 2),
        ("p1", 1, "plan", "success", 1),
    ):
        conn.execute(
            "INSERT INTO phases (phase_id, adw_id, seq, name, kind, owner, status, attempt, "
            "retries, started_at) VALUES (?, ?, ?, ?, 'agent', 'builder', ?, ?, 2, ?)",
            (
                f"{p}{phase_id}",
                f"{p}r-run",
                seq,
                name,
                status,
                attempt,
                f"2026-01-07T10:0{seq}:00+00:00",
            ),
        )
    conn.close()
    return root


def dead_pid() -> int:
    """The pid of a process that has already ended."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def register(home: Path, *roots: Path) -> Registry:
    registry = Registry(home)
    for root in roots:
        registry.add(root)
    return registry
