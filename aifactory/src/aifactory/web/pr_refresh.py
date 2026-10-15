"""Background refresh of open task PRs from the provider for the dashboard.

A task PR merged or closed outside factory (``gh pr merge``, the hosting's web UI) stays
``open`` in ``task_prs`` until something asks the provider. The Overview, the kanban and the
queue read only ``task_prs``, so the dashboard refreshes the state of open task and sync PRs
of every registered repository every ``PR_REFRESH_INTERVAL`` seconds with
``aifactory.review.sync.refresh_prs`` (no fetch, worktree, commit or PR). ``GET /api/overview``
stays read-only and never calls the provider itself. A repository without a trace DB is
skipped and no trace DB is created; one broken repository never stops the others.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path

from aifactory import database
from aifactory.config import ConfigError
from aifactory.review import sync as review_sync
from aifactory.review.errors import ReviewError
from aifactory.review.sync import SyncResult
from aifactory.run.errors import TaskRunError
from aifactory.run.gitops import repo_layout
from aifactory.web.registry import Registry
from aifactory.web.repos import trace_db_of

PR_REFRESH_INTERVAL = 120.0  # s, background refresh of open task PRs from the provider

log = logging.getLogger(__name__)


def _default_refresh(root: Path) -> SyncResult:
    return review_sync.refresh_prs(root)  # looked up at call time: tests monkeypatch it


def refresh_registered(
    registry: Registry,
    *,
    refresh: Callable[[Path], SyncResult] | None = None,
) -> list[str]:
    """Refresh open task PRs of every registered repository that has a trace DB; warnings."""
    run = refresh if refresh is not None else _default_refresh
    state, _ = registry.snapshot()
    warnings: list[str] = []
    for entry in state.repos:
        path = Path(entry.path)
        if not path.is_dir():
            continue
        layout = repo_layout(path)
        if layout is None or layout.toplevel is None:
            continue
        root = layout.toplevel
        if not database.available(trace_db_of(root)):
            continue
        try:
            result = run(root)
        except (ReviewError, TaskRunError, ConfigError, OSError, sqlite3.Error) as exc:
            warnings.append(f"{entry.id}: {exc}")
            continue
        warnings += [f"{entry.id}: {warning}" for warning in result.warnings]
    for warning in warnings:
        log.warning("PR refresh: %s", warning)
    return warnings
