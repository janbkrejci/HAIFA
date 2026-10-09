"""Share Markdown backlog files with optimistic conflict detection and a local mirror."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from aifactory.backlog.roots import backlog_roots, owning_root
from aifactory.config.settings import ProjectSettings, load_local
from aifactory.database import connect, is_remote


def _path(root: Path) -> Path | None:
    # Validation copies are deliberately local; they have no Git checkout.
    if not (root / ".git").exists():
        return None
    path = load_local(root).trace_db_path(root)
    return path if is_remote(path) else None


def _snapshot(conn: sqlite3.Connection) -> dict[str, str]:
    conn.execute("CREATE TABLE IF NOT EXISTS haifa_backlog (path TEXT PRIMARY KEY, text TEXT)")
    return dict(conn.execute("SELECT path, text FROM haifa_backlog").fetchall())


def _baseline(path: Path) -> Path:
    return path.with_suffix(".backlog.json")


def _save(path: Path, files: dict[str, str]) -> None:
    target = _baseline(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(files, ensure_ascii=False), encoding="utf-8")
    temporary.replace(target)


def _synchronize(root: Path, settings: ProjectSettings) -> None:
    """Merge local edits and remote changes, rejecting edits to the same file."""
    path = _path(root)
    if path is None:
        return
    from aifactory.backlog.edit import TaskEditError, _atomic_write, _guard
    from aifactory.backlog.model import Backlog
    from aifactory.run import mainwrites

    local = {
        file.relative_to(root).as_posix(): file.read_text(encoding="utf-8")
        for directory in backlog_roots(root, settings)
        for file in (root / directory).rglob("*.md")
        if file.is_file()
    }
    previous = json.loads(_baseline(path).read_text()) if _baseline(path).is_file() else None
    conn = connect(path, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        remote = _snapshot(conn)
        if not remote:
            for rel, text in local.items():
                conn.execute("INSERT INTO haifa_backlog VALUES (?, ?)", (rel, text))
            remote = dict(local)
        elif previous is None and any(local.get(rel) != text for rel, text in remote.items()):
            from aifactory.run.gitops import read_git

            dirty = read_git(
                root,
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                *backlog_roots(root, settings),
            )
            if dirty:
                raise TaskEditError(
                    "remote_backlog_conflict",
                    "preserve or commit local backlog edits before joining the team database",
                )
        elif previous is not None:
            # A file present in the baseline but removed locally is a conflict rather
            # than an implicit team-wide delete. Git pulls need explicit reconciliation.
            for rel in set(previous) | set(local):
                before, here, there = previous.get(rel), local.get(rel), remote.get(rel)
                if here == before or here == there:
                    continue
                if there != before or here is None:
                    raise TaskEditError(
                        "remote_backlog_conflict",
                        f"backlog conflict in {rel}; preserve your edit and reconcile",
                        path=rel,
                    )
                conn.execute("INSERT OR REPLACE INTO haifa_backlog VALUES (?, ?)", (rel, here))
                remote[rel] = here
        conn.execute("COMMIT")
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    for rel, text in remote.items():
        if owning_root(rel, settings) is None:
            raise TaskEditError(
                "outside_backlog", f"remote backlog path outside configured roots: {rel}"
            )
        target = _guard(root, Backlog(root, settings), rel)
        if target.is_file() and target.read_text(encoding="utf-8") == text:
            continue
        old = target.read_bytes() if target.is_file() else None
        _atomic_write(target, text, rel)
        mainwrites.record(
            root,
            rel,
            old,
            target.read_bytes(),
            mode=target.stat().st_mode & 0o777,
            command="backlog remote sync",
        )
    _save(path, remote)


def _publish(root: Path, changes: dict[str, str]) -> None:
    """Atomically publish validated CLI/dashboard edits against the loaded snapshot."""
    path = _path(root)
    if path is None:
        return
    from aifactory.backlog.edit import TaskEditError

    previous = json.loads(_baseline(path).read_text(encoding="utf-8"))
    conn = connect(path, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        remote = _snapshot(conn)
        if remote != previous:
            raise TaskEditError(
                "remote_backlog_conflict", "backlog changed remotely; reload and retry"
            )
        for rel, text in changes.items():
            conn.execute("INSERT OR REPLACE INTO haifa_backlog VALUES (?, ?)", (rel, text))
            remote[rel] = text
        conn.execute("COMMIT")
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def synchronize(root: Path, settings: ProjectSettings) -> None:
    path = _path(root)
    if path is not None:
        from aifactory.run.store import _path_lock

        path.parent.mkdir(parents=True, exist_ok=True)
        with _path_lock(path.with_suffix(".backlog.lock")).hold(30):
            _synchronize(root, settings)


def publish(root: Path, changes: dict[str, str]) -> None:
    path = _path(root)
    if path is not None:
        from aifactory.run.store import _path_lock

        path.parent.mkdir(parents=True, exist_ok=True)
        with _path_lock(path.with_suffix(".backlog.lock")).hold(30):
            _publish(root, changes)
