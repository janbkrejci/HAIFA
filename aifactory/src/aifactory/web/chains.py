"""Auto-continue chains for the dashboard's Runs screen (``GET /api/chains``).

A chain is a row of ``task_chains`` (``run.store.TaskChainRow``, written by
``run.queue.run_chain``). ``list_chains`` returns the running chains and the newest
ended ones with all their runs, the number of running runs, the free slots of a running
chain (``max_parallel`` minus running), the tasks the last selection skipped with their
reasons and the tasks that ran alone (wide ``writes``). A run shows its result: state and
error from ``task_runs``, its pull request and what auto-merge did from ``task_prs``. A
sequential chain records a run when it ends, so the run going on in the chain's process
is added from ``task_runs``. ``dismiss_chain`` erases an ended chain (its runs stay). A
repository without a trace DB gets no chains (the DB is not created).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aifactory.config.settings import CONFIG_FILE, parse_project_settings
from aifactory.run import gitops
from aifactory.run.errors import TaskRunError
from aifactory.run.store import RUNNING, TaskChainRow, TaskRunRow, TaskRunStore
from aifactory.run.task import existing_store

JsonDict = dict[str, Any]
CHAINS_LIMIT = 10


def _max_parallel_runs(repo: Path) -> int | None:
    """``max_parallel_runs`` of ``.factory/config.yaml`` in the main checkout (None if invalid)."""
    try:
        root = gitops.main_root(repo)
    except TaskRunError:
        root = repo
    path = root / CONFIG_FILE
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else None
    except OSError:
        return None
    settings = parse_project_settings(text, CONFIG_FILE, [])
    return settings.max_parallel_runs if settings is not None else None


def _run_json(store: TaskRunStore, run_id: str, row: TaskRunRow | None) -> JsonDict:
    pr = store.pr_for_branch(row.branch) if row is not None else None
    return {
        "run_id": run_id,
        "task_id": row.task_id if row is not None else None,
        "state": row.state if row is not None else None,
        "workflow": row.workflow if row is not None else None,
        "error": row.error if row is not None else None,
        "pause": row.pause if row is not None and row.state == RUNNING else None,
        "pr": None
        if pr is None
        else {
            "url": pr.url,
            "pr_id": pr.pr_id,
            "state": pr.state,
            "merged_by": pr.merged_by,
            "auto_merge_error": pr.auto_merge_error,
        },
    }


def _unrecorded_ids(store: TaskRunStore, chain: TaskChainRow, recorded: list[str]) -> list[str]:
    """Runs going on in a running chain's own process (a sequential chain) not recorded yet."""
    if chain.state != RUNNING or chain.pid is None:
        return []
    rows = store.conn.execute(
        "SELECT run_id FROM task_runs WHERE state = ? AND pid = ? ORDER BY started_at, rowid",
        (RUNNING, chain.pid),
    ).fetchall()
    return [str(r[0]) for r in rows if r[0] not in recorded]


def _chain_json(store: TaskRunStore, chain: TaskChainRow) -> JsonDict:
    recorded = chain.run_id_list()
    ids = [*recorded, *_unrecorded_ids(store, chain, recorded)]
    runs = [_run_json(store, run_id, store.get(run_id)) for run_id in ids]
    running = sum(1 for r in runs if r["state"] == RUNNING)
    live = chain.state == RUNNING
    return {
        "chain_id": chain.chain_id,
        "task_id": chain.task_id,
        "state": chain.state,
        "stop": chain.stop,
        "max_parallel": chain.max_parallel,
        "started_at": chain.started_at,
        "updated_at": chain.updated_at,
        "ended_at": chain.ended_at,
        "runs": runs,
        "running": running,
        "free_slots": max(0, chain.max_parallel - running) if live else 0,
        "skipped": chain.skipped_list(),
        "exclusive": chain.exclusive_list(),
    }


def dismiss_chain(repo: Path, chain_id: str) -> JsonDict:
    """Erase an ended chain (``chain_running`` while it runs); its runs stay."""
    store = existing_store(repo)
    if store is None:
        raise TaskRunError("unknown_chain", f"no chain {chain_id}")
    try:
        if not store.dismiss_chain(chain_id):
            raise TaskRunError("unknown_chain", f"no chain {chain_id}")
    finally:
        store.close()
    return {"dismissed": chain_id}


def list_chains(repo: Path, limit: int = CHAINS_LIMIT) -> tuple[JsonDict, list[str]]:
    """``{max_parallel_runs, chains}``: running chains first, then the newest ended ones."""
    data: JsonDict = {"max_parallel_runs": _max_parallel_runs(repo), "chains": []}
    store = existing_store(repo)
    if store is None:
        return data, []
    try:
        data["chains"] = [_chain_json(store, c) for c in store.chains(limit)]
    finally:
        store.close()
    return data, []
