"""Bounded trace invalidations, including updates/deletes of historical rows.

Readers falling behind the retained journal request a full refresh. No task or run
payload is duplicated here, and writers update it in their existing transaction.
"""

from __future__ import annotations

import sqlite3

RETAIN = 1000


def install(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS trace_changes ("
        "seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, run_id TEXT)"
    )
    for table, key in (("task_runs", "run_id"), ("task_prs", None)):
        for operation in ("INSERT", "UPDATE", "DELETE"):
            row = "OLD" if operation == "DELETE" else "NEW"
            run_id = f"{row}.{key}" if key else "NULL"
            conn.execute(
                f"CREATE TRIGGER IF NOT EXISTS trace_changes_{table}_{operation.lower()} "
                f"AFTER {operation} ON {table} BEGIN "
                "INSERT INTO trace_changes(task_id, run_id) "
                f"VALUES ({row}.task_id, {run_id}); "
                f"DELETE FROM trace_changes WHERE seq <= last_insert_rowid() - {RETAIN}; END"
            )
