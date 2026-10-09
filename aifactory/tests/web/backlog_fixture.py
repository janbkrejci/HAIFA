"""A committed git repo with a two-module backlog for the Backlog API tests.

``M01`` (workflow ``plan-build``) has ``M01-S01`` with T01 done, T02 ready (depends on
T01), T03 blocked (depends on T02) and T04 cancelled. ``M02`` (no workflow) has
``M02-S01`` with T01 (no workflow: ``todo``), T02 and T03 (workflow ``plan``). The indexes
keep a legacy ``owner``, which is ignored. With ``with_trace`` the trace DB (written after
the commit) has a running run of ``M02-S01-T02`` and a finished run with an open PR of
``M02-S01-T03``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from web_repo import git_repo

from aifactory.run.store import TaskPrRow, TaskRunRow, TaskRunStore

M01 = "M01"
M02 = "M02"
S1 = "M01-S01"
S2 = "M02-S01"
A1 = "M01-S01-T01"
A2 = "M01-S01-T02"
A3 = "M01-S01-T03"
A4 = "M01-S01-T04"
B1 = "M02-S01-T01"
B2 = "M02-S01-T02"
B3 = "M02-S01-T03"


def _task(task_id: str, title: str, status: str = "todo", extra: str = "") -> str:
    return (
        f"---\nid: {task_id}\ntitle: {title}\nstatus: {status}\n{extra}---\n\n"
        f"## Zadání\nZadání {title}.\n"
    )


def _default_files() -> dict[str, str]:
    m1 = "backlog/M01-core/S01-model"
    m2 = "backlog/M02-web/S01-ui"
    return {
        "backlog/M01-core/index.md": (
            "---\nid: M01\ntitle: Core\nowner: alice\nworkflow: plan-build\n---\n"
        ),
        f"{m1}/index.md": "---\nid: M01-S01\ntitle: Model\n---\n",
        f"{m1}/{A1}-schema.md": _task(A1, "Schema", "done"),
        f"{m1}/{A2}-loader.md": _task(A2, "Loader", extra=f"depends_on: [{A1}]\n"),
        f"{m1}/{A3}-writer.md": _task(A3, "Writer", extra=f"depends_on: [{A2}]\n"),
        f"{m1}/{A4}-legacy.md": _task(A4, "Legacy", "cancelled"),
        "backlog/M02-web/index.md": "---\nid: M02\ntitle: Web\nowner: bob\n---\n",
        f"{m2}/index.md": "---\nid: M02-S01\ntitle: UI\n---\n",
        f"{m2}/{B1}-layout.md": _task(B1, "Layout"),
        f"{m2}/{B2}-tree.md": _task(B2, "Tree", extra="workflow: plan\n"),
        f"{m2}/{B3}-kanban.md": _task(B3, "Kanban", extra="workflow: plan\n"),
    }


def _area_files() -> dict[str, str]:
    return {
        "backlog/A1/index.md": "---\nid: A1\ntitle: Area one\nowner: carol\n---\n",
        "backlog/A1/A1-T01-first.md": _task("A1-T01", "First", extra="workflow: plan\n"),
        "backlog/A1/A1-T02-second.md": _task("A1-T02", "Second", extra="depends_on: [A1-T01]\n"),
    }


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout


def _run(run_id: str, task_id: str, state: str, day: int) -> TaskRunRow:
    return TaskRunRow(
        run_id=run_id,
        task_id=task_id,
        branch=f"factory/{task_id}-1",
        worktree=f"/tmp/wt/{run_id}",
        base="main",
        base_sha="0" * 40,
        head_sha=None,
        state=state,
        started_at=f"2026-01-0{day}T10:00:00+00:00",
        pid=os.getpid(),
        workflow="plan",
    )


def _write_trace(root: Path) -> None:
    store = TaskRunStore(root / ".factory" / "trace.db")
    store.claim(_run("r-b2", B2, "running", 2))
    store.claim(_run("r-b3", B3, "running", 1))
    store.finish("r-b3", "succeeded", "a" * 40, None)
    store.save_pr(
        TaskPrRow(
            branch=f"factory/{B3}-1",
            task_id=B3,
            provider="local",
            pr_id="3",
            url="https://example.test/pr/3",
            base="main",
            base_sha="0" * 40,
            title="Kanban",
            body="",
            state="open",
            created_at="2026-01-01T10:05:00+00:00",
            updated_at="2026-01-01T10:05:00+00:00",
        )
    )
    store.close()


def make_backlog_repo(
    path: Path, *, levels: list[str] | None = None, with_trace: bool = False
) -> Path:
    """The repo at ``path`` with one commit; ``levels=[area, task]`` uses a flat backlog."""
    root = git_repo(path)
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.com")
    levels = levels or ["module", "step", "task"]
    files = _area_files() if len(levels) == 2 else _default_files()
    files[".factory/config.yaml"] = (
        f"base: main\nlevels: [{', '.join(levels)}]\nbacklog_dir: backlog\n"
    )
    files[".factory/workflows/custom-flow.yaml"] = "name: custom-flow\nsteps: [plan]\n"
    files[".gitignore"] = ".factory/trace.db*\n"
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    if with_trace:
        _write_trace(root)
    return root
