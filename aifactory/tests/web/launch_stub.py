"""A stand-in for the run process the dashboard starts (``test_web_launcher``; not a test).

Run as ``python launch_stub.py task run|return|resolve ID --repo ROOT --json [...]``. The
behaviour per task comes from the JSON file named by ``$HAIFA_LAUNCH_STUB``
(``{task_id: {"mode": ..., "code": ..., "message": ..., "delay": ...}}``; a missing task is
``claim-wait``). First it records ``<control>.<task_id>.<pid>.json`` (argv, cwd, session,
pid and parent pid, stdin, ``HAIFA_HOME``; no session on Windows). Modes:

- ``claim-wait``: claims a ``running`` row with its own pid and sleeps until killed;
- ``claim-exit``: claims, finishes ``succeeded`` and prints an ok envelope;
- ``fail``: prints a failing envelope with ``code`` and ``message`` and exits 2;
- ``garbage``: prints no envelope, a few lines with ``STUB-TAIL-MARKER`` to stderr, exits 3.

``already_running`` from the claim is printed as a failing envelope (exit 2).
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aifactory.run.errors import TaskRunError
from aifactory.run.store import RUNNING, SUCCEEDED, TaskRunRow, TaskRunStore
from aifactory.skill import envelope_fail, envelope_ok

STUB_ENV = "HAIFA_LAUNCH_STUB"
TAIL_MARKER = "STUB-TAIL-MARKER"
MAX_WAIT_S = 120.0


def _option(argv: list[str], name: str) -> str | None:
    for i, arg in enumerate(argv):
        if arg == name and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith(name + "="):
            return arg[len(name) + 1 :]
    return None


def _print(envelope: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(envelope, indent=2) + "\n")
    sys.stdout.flush()


def _claim(repo: Path, task_id: str, action: str, note: str | None) -> TaskRunStore:
    store = TaskRunStore(repo / ".factory" / "trace.db")
    run_id = uuid.uuid4().hex[:8]
    store.claim(
        TaskRunRow(
            run_id=run_id,
            task_id=task_id,
            branch=f"factory/{task_id}-x",
            worktree="",
            base="main",
            base_sha="0" * 40,
            head_sha=None,
            state=RUNNING,
            started_at=datetime.now(UTC).isoformat(timespec="seconds"),
            pid=os.getpid(),
            workflow=action,
            note=note,
        )
    )
    return store


def main(argv: list[str]) -> int:
    action, task_id = argv[1], argv[2]
    repo = Path(_option(argv, "--repo") or ".")
    note = _option(argv, "--note")
    control = Path(os.environ[STUB_ENV])
    plan: dict[str, Any] = json.loads(control.read_text(encoding="utf-8")).get(task_id) or {}
    sid: int | None = None  # Windows has no sessions
    if sys.platform != "win32":
        sid = os.getsid(0)
    record = {
        "argv": argv,
        "cwd": os.getcwd(),
        "sid": sid,
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "stdin": sys.stdin.read(),
        "haifa_home": os.environ.get("HAIFA_HOME"),
    }
    out = control.with_name(f"{control.name}.{task_id}.{os.getpid()}.json")
    out.write_text(json.dumps(record), encoding="utf-8", newline="\n")
    mode = str(plan.get("mode") or "claim-wait")
    time.sleep(float(plan.get("delay") or 0))
    if mode == "fail":
        _print(envelope_fail(str(plan["code"]), str(plan["message"])))
        return 2
    if mode == "garbage":
        print("not json")
        print(f"line one\nline two\n{TAIL_MARKER}", file=sys.stderr)
        return 3
    try:
        store = _claim(repo, task_id, action, note)
    except TaskRunError as exc:
        _print(envelope_fail(exc.code, exc.message))
        return 2
    try:
        if mode == "claim-exit":
            row = store.for_task(task_id)[0]
            store.finish(row.run_id, SUCCEEDED, None, None)
            _print(envelope_ok({"run_id": row.run_id}))
            return 0
    finally:
        store.close()
    deadline = time.monotonic() + MAX_WAIT_S
    while time.monotonic() < deadline:
        time.sleep(0.1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
