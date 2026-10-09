"""The dashboard's Review screen: open task PRs, a PR's detail, approve, return and resolve.

On request the list also has the done task PRs (merged and closed, newest first); they
are read only and the provider is not asked about them.

Reads the open pull requests from ``task_prs`` in the trace DB (a missing trace DB is not
created), the title and project (top level) of each task from the backlog of the main checkout, the
mergeability from the git provider and the costs, gates, tests and the reviewer's verdict
from the trace. Listing never writes the provider state into ``task_prs``; the actions do,
through the core functions.

The actions call the same functions as ``factory task approve|return|resolve``
(``aifactory.review.approve_task``, ``return_task``, ``resolve_task``), looked up on the
module at call time. Approve is quick and synchronous; return and resolve start a run, so
the server starts them as a separate process ``factory task return|resolve``
(``launcher.py``) after checking the request.

Approve does not send an approve review to the hosting yet (OB3): it commits
``status: done`` and merges. The data says so in ``approve_review_sent`` and
``approve_note``.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aifactory.review as review_core
from aifactory import backlog as core
from aifactory import database
from aifactory.backlog import Backlog, Container, Task
from aifactory.config import ConfigError, RunConfig, load_run_config
from aifactory.engine.tracer import BUSY_TIMEOUT
from aifactory.providers import OPEN, UNKNOWN, GitProvider, ProviderError, get_provider
from aifactory.review.errors import ReviewError
from aifactory.review.prbody import branch_cost, run_checks, run_cost
from aifactory.run import gitops
from aifactory.run.errors import TaskRunError
from aifactory.run.store import SUCCEEDED, TaskPrRow, TaskRunRow, TaskRunStore
from aifactory.run.task import existing_store
from aifactory.web.backlog import UsageError
from aifactory.web.launcher import Launcher

JsonDict = dict[str, Any]

APPROVE_NOTE = (
    "Schválení zatím neposílá approve review v hostingu (OB3): "
    "rovnou přidá commit se status: done a PR merguje."
)

PATCH_LIMIT = 200_000
"""Characters of one file's patch; a longer patch is cut (``truncated``)."""
DIFF_LIMIT = 2_000_000
"""Characters of all patches; files past it come without a patch (``truncated``)."""

RETURN_KEYS = ("note",)
RESOLVE_KEYS: tuple[str, ...] = ()

_STATUS = {"A": "added", "M": "modified", "D": "deleted", "R": "renamed", "C": "added"}


@dataclass
class _Ctx:
    main: Path
    rc: RunConfig
    store: TaskRunStore | None
    provider: GitProvider | None
    backlog: Backlog | None
    warnings: list[str] = field(default_factory=list)


@contextlib.contextmanager
def _context(repo: Path) -> Iterator[_Ctx]:
    main = gitops.main_root(repo)
    try:
        rc = load_run_config(main)
    except ConfigError as exc:
        raise TaskRunError("invalid_config", str(exc)) from exc
    warnings: list[str] = []
    try:
        backlog: Backlog | None = core.load_for_edit(main)
    except (core.TaskEditError, ConfigError, OSError, ValueError) as exc:
        backlog = None
        warnings.append(f"task titles and projects are not shown: {exc}")
    provider: GitProvider | None
    try:
        provider = get_provider(rc.config.settings, main)
    except ProviderError as exc:
        provider = None
        warnings.append(f"mergeability is not known: {exc.code}: {exc.message}")
    store = existing_store(main)
    try:
        yield _Ctx(main, rc, store, provider, backlog, warnings)
    finally:
        if store is not None:
            store.close()


def _task(ctx: _Ctx, task_id: str) -> Task | None:
    if ctx.backlog is None:
        return None
    node = ctx.backlog.by_id.get(task_id)
    return node if isinstance(node, Task) else None


def _project_id(task: Task | None) -> str | None:
    """The id of the top container (the first of ``levels``, e.g. the project) above `task`."""
    if task is None:
        return None
    node: Container | None = task.parent
    top: Container | None = None
    while node is not None:
        if node.id is not None:
            top = node
        node = node.parent
    return None if top is None else top.id


@dataclass
class _Status:
    state: str | None
    mergeability: str


def _status(ctx: _Ctx, row: TaskPrRow) -> _Status:
    """The provider's view of `row`; ``task_prs`` is not written."""
    if row.state != OPEN:
        return _Status(row.state, UNKNOWN)
    if ctx.provider is None:
        return _Status(None, UNKNOWN)
    try:
        status = ctx.provider.status(row.request())
    except ProviderError as exc:
        ctx.warnings.append(f"PR {row.url}: {exc.code}: {exc.message}")
        return _Status(None, UNKNOWN)
    except (RuntimeError, OSError) as exc:
        ctx.warnings.append(f"PR {row.url}: {exc}")
        return _Status(None, UNKNOWN)
    mergeability = status.mergeability if status.state == OPEN else UNKNOWN
    return _Status(status.state, mergeability)


def _running(store: TaskRunStore, task_id: str) -> JsonDict | None:
    row = store.running(task_id)
    if row is None:
        return None
    return {"run_id": row.run_id, "workflow": row.workflow, "started_at": row.started_at}


def _pr_summary(ctx: _Ctx, store: TaskRunStore, row: TaskPrRow) -> JsonDict:
    task = _task(ctx, row.task_id)
    status = _status(ctx, row)
    running = _running(store, row.task_id)
    runs = store.runs_on_branch(row.branch)
    cost, tokens = branch_cost(store.db_path, [r.run_id for r in runs])
    last = runs[0] if runs else None
    return {
        "task_id": row.task_id,
        "task_title": None if task is None else task.title,
        "project_id": _project_id(task),
        "provider_state": status.state,
        "mergeability": status.mergeability,
        "running_run": running,
        "awaiting_review": status.state == OPEN and running is None,
        "cost": cost,
        "tokens": tokens,
        "runs": len(runs),
        "last_run": None
        if last is None
        else {
            "run_id": last.run_id,
            "state": last.state,
            "workflow": last.workflow,
            "ended_at": last.ended_at,
        },
        "_row": row,
    }


def _done_list(ctx: _Ctx, store: TaskRunStore, seen: set[str]) -> list[JsonDict]:
    """Merged and closed PRs, one per task without an open PR, newest first."""
    done: list[JsonDict] = []
    for row in store.done_prs():  # newest first
        if row.task_id in seen:
            continue
        seen.add(row.task_id)
        task = _task(ctx, row.task_id)
        cost, tokens = branch_cost(
            store.db_path, [r.run_id for r in store.runs_on_branch(row.branch)]
        )
        pr = row.to_json()
        pr.pop("body", None)
        done.append(
            {
                "task_id": row.task_id,
                "task_title": None if task is None else task.title,
                "project_id": _project_id(task),
                "provider_state": row.state,
                "done_at": row.merged_at or row.updated_at,
                "cost": cost,
                "tokens": tokens,
                "pr": pr,
            }
        )
    return done


def review_list(repo: Path, include_done: bool = False) -> tuple[JsonDict, list[str]]:
    """Open task PRs with mergeability and costs; with `include_done` also ``done``."""
    with _context(repo) as ctx:
        items: list[JsonDict] = []
        store = ctx.store
        seen: set[str] = set()
        if store is not None:
            for row in store.open_prs():  # newest first
                if row.task_id in seen:
                    continue
                seen.add(row.task_id)
                items.append(_pr_summary(ctx, store, row))
        items.sort(key=lambda i: i["_row"].created_at, reverse=True)
        items.sort(key=lambda i: not i["awaiting_review"])
        prs: list[JsonDict] = []
        for item in items:
            row = item.pop("_row")
            pr = row.to_json()
            pr.pop("body", None)
            prs.append({**item, "pr": pr})
        data: JsonDict = {
            "prs": prs,
            "provider": ctx.rc.config.settings.git_provider,
            "levels": list(ctx.rc.config.settings.levels),
            "approve_review_sent": False,
            "approve_note": APPROVE_NOTE,
        }
        if include_done:
            data["done"] = [] if store is None else _done_list(ctx, store, seen)
        return data, ctx.warnings


# ── diff ─────────────────────────────────────────────────────────────────────


def _git(main: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=main,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _fields(text: str) -> list[str]:
    parts = text.split("\0")
    return parts[:-1] if parts and parts[-1] == "" else parts


def _name_status(text: str) -> list[tuple[str, str, str | None]]:
    """``(status, path, old_path)`` per file of ``git diff --name-status -z``."""
    parts = _fields(text)
    out: list[tuple[str, str, str | None]] = []
    i = 0
    while i < len(parts):
        code = parts[i]
        if code[:1] in ("R", "C") and i + 2 < len(parts):
            out.append((_STATUS.get(code[:1], "modified"), parts[i + 2], parts[i + 1]))
            i += 3
        elif i + 1 < len(parts):
            out.append((_STATUS.get(code[:1], "modified"), parts[i + 1], None))
            i += 2
        else:
            break
    return out


def _numstat(text: str) -> list[tuple[int | None, int | None]]:
    """``(additions, deletions)`` per file of ``git diff --numstat -z`` (None when binary)."""
    parts = _fields(text)
    out: list[tuple[int | None, int | None]] = []
    i = 0
    while i < len(parts):
        head = parts[i].split("\t")
        if len(head) < 3:
            break
        added, deleted, path = head[0], head[1], head[2]
        out.append(
            (
                None if added == "-" else int(added),
                None if deleted == "-" else int(deleted),
            )
        )
        i += 1 if path else 3  # a rename: "a\td\t\0old\0new\0"
    return out


def _patches(text: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.startswith("diff --git ") and current:
            chunks.append("".join(current))
            current = []
        current.append(line)
    if current:
        chunks.append("".join(current))
    return chunks


def _empty_diff(base: str, merge_base: str | None) -> JsonDict:
    return {
        "base": base,
        "merge_base": merge_base,
        "stat": {"files": 0, "additions": 0, "deletions": 0},
        "files": [],
    }


def _diff(main: Path, base: str, branch: str, warnings: list[str]) -> JsonDict:
    """The PR's changes: ``merge-base(base, branch)..branch``, per file."""
    tip = f"refs/heads/{branch}"
    try:
        merge_base = _git(main, "merge-base", f"refs/heads/{base}", tip).strip()
    except RuntimeError as exc:
        warnings.append(f"diff is not shown: {exc}")
        return _empty_diff(base, None)
    try:
        names = _name_status(_git(main, "diff", "--name-status", "-z", "-M", merge_base, tip))
        counts = _numstat(_git(main, "diff", "--numstat", "-z", "-M", merge_base, tip))
        patches = _patches(_git(main, "diff", "--patch", "-M", "--no-color", merge_base, tip))
    except RuntimeError as exc:
        warnings.append(f"diff is not shown: {exc}")
        return _empty_diff(base, merge_base)
    if len(patches) != len(names):
        warnings.append("diff patches do not match the file list; patches are not shown")
        patches = []
    files: list[JsonDict] = []
    used = 0
    additions = deletions = 0
    for i, (status, path, old_path) in enumerate(names):
        added, deleted = counts[i] if i < len(counts) else (0, 0)
        binary = added is None or deleted is None
        additions += added or 0
        deletions += deleted or 0
        patch = patches[i] if i < len(patches) else ""
        truncated = False
        if used >= DIFF_LIMIT:
            patch, truncated = "", True
        elif len(patch) > PATCH_LIMIT:
            patch, truncated = patch[:PATCH_LIMIT], True
        used += len(patch)
        files.append(
            {
                "path": path,
                "old_path": old_path,
                "status": status,
                "additions": added or 0,
                "deletions": deleted or 0,
                "binary": binary,
                "patch": patch,
                "truncated": truncated,
            }
        )
    return {
        "base": base,
        "merge_base": merge_base,
        "stat": {"files": len(files), "additions": additions, "deletions": deletions},
        "files": files,
    }


# ── reviewer's verdict ───────────────────────────────────────────────────────


def _review_verdict(trace_db: Path, run_ids: list[str]) -> JsonDict | None:
    """The newest reviewer envelope (a payload with a bool ``approved``) of `run_ids`."""
    if not run_ids or not database.available(trace_db):
        return None
    conn = database.connect(f"file:{trace_db}?mode=ro", uri=True, timeout=BUSY_TIMEOUT)
    try:
        marks = ", ".join("?" for _ in run_ids)
        try:
            rows = conn.execute(
                "SELECT agent, payload_json, created_at, adw_id FROM envelopes "
                f"WHERE adw_id IN ({marks}) ORDER BY created_at DESC, rowid DESC",
                tuple(run_ids),
            ).fetchall()
        except sqlite3.OperationalError:
            return None
    finally:
        conn.close()
    for agent, payload_json, created_at, adw_id in rows:
        try:
            payload = json.loads(payload_json) if payload_json else None
        except ValueError:
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("approved"), bool):
            continue
        findings = payload.get("findings")
        blocking = payload.get("blocking")
        return {
            "approved": payload["approved"],
            "summary": str(payload.get("summary") or ""),
            "blocking": [str(b) for b in blocking] if isinstance(blocking, list) else [],
            "findings": [f for f in findings if isinstance(f, dict)]
            if isinstance(findings, list)
            else [],
            "agent": agent,
            "run_id": adw_id,
            "created_at": created_at,
        }
    return None


# ── detail ───────────────────────────────────────────────────────────────────


def _checks(trace_db: Path, runs: list[TaskRunRow]) -> list[JsonDict]:
    """Gates and tests of the newest succeeded run on the branch (else the newest run)."""
    if not runs:
        return []
    run = next((r for r in runs if r.state == SUCCEEDED), runs[0])
    return [
        {
            "kind": c.kind,
            "name": c.name,
            "phase": c.phase,
            "passed": c.passed,
            "detail": c.detail,
            "run_id": run.run_id,
        }
        for c in run_checks(trace_db, run.run_id)
    ]


def _run_json(trace_db: Path, run: TaskRunRow) -> JsonDict:
    cost, tokens = run_cost(trace_db, run.run_id)
    return {
        "run_id": run.run_id,
        "workflow": run.workflow,
        "state": run.state,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "note": run.note,
        "error": run.error,
        "cost": cost,
        "tokens": tokens,
    }


def review_detail(repo: Path, task_id: str) -> tuple[JsonDict, list[str]]:
    """The task's newest PR: body, diff per file, gates and tests, verdict, runs, actions."""
    with _context(repo) as ctx:
        store = ctx.store
        row = None if store is None else store.latest_pr(task_id)
        if store is None or row is None:
            raise ReviewError("no_pr", f"task {task_id} has no pull request, run it first")
        summary = _pr_summary(ctx, store, row)
        summary.pop("_row")
        summary.pop("last_run")
        summary.pop("runs")
        runs = store.runs_on_branch(row.branch)  # newest first
        trace_db = store.db_path
        state, running = summary["provider_state"], summary["running_run"]
        can_act = state == OPEN and running is None
        data: JsonDict = {
            **summary,
            "pr": row.to_json(),
            "levels": list(ctx.rc.config.settings.levels),
            "runs": [_run_json(trace_db, r) for r in runs],
            "diff": _diff(ctx.main, row.base, row.branch, ctx.warnings),
            "checks": _checks(trace_db, runs),
            "review": _review_verdict(trace_db, [r.run_id for r in runs]),
            "actions": {
                "approve": can_act and summary["mergeability"] != "conflict",
                "return": can_act,
                "resolve": can_act,
            },
            "approve_review_sent": False,
            "approve_note": APPROVE_NOTE,
        }
        return data, ctx.warnings


# ── actions ──────────────────────────────────────────────────────────────────


def _check_keys(body: JsonDict, allowed: tuple[str, ...]) -> None:
    for key in body:
        if key not in allowed:
            listed = ", ".join(allowed) or "none"
            raise UsageError(f"unknown field '{key}', allowed: {listed}")


def approve(repo: Path, task_id: str) -> tuple[JsonDict, list[str]]:
    """``factory task approve``: the done commit and the merge (no approve review, OB3)."""
    result = review_core.approve_task(repo, task_id)
    data: JsonDict = {
        **result.to_json(),
        "approve_review_sent": False,
        "approve_note": APPROVE_NOTE,
    }
    return data, list(result.warnings)


def _started(task_id: str, action: str, row: TaskRunRow | None) -> tuple[JsonDict, list[str]]:
    data: JsonDict = {
        "task_id": task_id,
        "action": action,
        "run": None if row is None else row.to_json(),
        "pending": row is None,
    }
    return data, []


def start_return(
    repo: Path, task_id: str, body: JsonDict, launcher: Launcher
) -> tuple[JsonDict, list[str]]:
    """``factory task return --note``: a new run on the PR branch, as a separate process."""
    _check_keys(body, RETURN_KEYS)
    note = body.get("note")
    if note is not None and not isinstance(note, str):
        raise UsageError("'note' must be a string")
    text = note or ""
    if not text.strip():
        raise ReviewError("missing_note", "returning a PR needs a note with what to change")

    row = launcher.start_return(repo, task_id, text)
    return _started(task_id, "return", row)


def start_resolve(
    repo: Path, task_id: str, body: JsonDict, launcher: Launcher
) -> tuple[JsonDict, list[str]]:
    """``factory task resolve``: the ``resolve`` workflow on the PR branch, as a process."""
    _check_keys(body, RESOLVE_KEYS)
    row = launcher.start_resolve(repo, task_id)
    return _started(task_id, "resolve", row)
