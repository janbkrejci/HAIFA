"""Journal of base moves made by factory commands, so a run's guard can tell them apart.

Several task runs may work at the same time. While an agent phase of run A is
going on, a factory command (``task approve`` of run B, ``backlog commit``,
``config commit``, ``config pull``) may fast-forward ``base`` that is checked
out in the main checkout. Without more information the guard of run A would
blame its agent for the moved ``HEAD``.

Every factory command that moves a base appends one JSON line to
``<git common dir>/haifa/base-moves.jsonl`` *after* the ref moved: the ref, the
old and new commit, the index tree of the checkout that has the base checked
out, and ``run`` — the value of ``HAIFA_RUN_ID`` in the process that moved it.
A task run sets ``HAIFA_RUN_ID`` to its run id while its workflow runs; agents
inherit it, and so does every ``factory`` command an agent starts. The guard
accepts a moved ``HEAD`` only when the journal entries written during the phase
chain from the ``HEAD`` before the phase to the ``HEAD`` now and none of them
carries its own run id.

Known limit: an agent that appends a forged entry with a foreign ``run`` to the
journal fools the guard (like a write to a gitignored path does).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from aifactory.run import backup, gitops

RUN_ENV = "HAIFA_RUN_ID"
"""Environment variable holding the id of the task run a process belongs to."""


@dataclass(frozen=True)
class BaseMove:
    ref: str
    old: str
    new: str
    run: str | None
    index_tree: str | None
    command: str


def journal(root: Path) -> Path | None:
    """Path of the journal in the git common dir of `root` (None outside a repo)."""
    common = gitops.common_dir(root)
    return None if common is None else common / "haifa" / "base-moves.jsonl"


def offset(root: Path) -> int:
    """Current size of the journal in bytes (0 when it does not exist)."""
    path = journal(root)
    if path is None:
        return 0
    try:
        return path.stat().st_size
    except OSError:
        return 0


def record(
    root: Path, ref: str, old: str, new: str, *, checkout: Path | None, command: str
) -> None:
    """Append one move of `ref`; never raises (the journal must not break a command)."""
    try:
        path = journal(root)
        if path is None:
            return
        move = BaseMove(
            ref=ref,
            old=old,
            new=new,
            run=os.environ.get(RUN_ENV) or None,
            index_tree=backup.index_tree(checkout) if checkout is not None else None,
            command=command,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(asdict(move)) + "\n"
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)
    except (OSError, RuntimeError, ValueError):
        return


def _parse(line: str) -> BaseMove | None:
    try:
        data = json.loads(line)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    ref, old, new = data.get("ref"), data.get("old"), data.get("new")
    if not (isinstance(ref, str) and isinstance(old, str) and isinstance(new, str)):
        return None
    run = data.get("run")
    tree = data.get("index_tree")
    command = data.get("command")
    return BaseMove(
        ref=ref,
        old=old,
        new=new,
        run=run if isinstance(run, str) and run else None,
        index_tree=tree if isinstance(tree, str) and tree else None,
        command=command if isinstance(command, str) else "",
    )


def moves_since(root: Path, start: int) -> list[BaseMove]:
    """Every readable entry written at or after byte `start`."""
    path = journal(root)
    if path is None:
        return []
    try:
        with path.open("rb") as fh:
            fh.seek(max(start, 0))
            data = fh.read()
    except OSError:
        return []
    moves: list[BaseMove] = []
    for raw in data.decode("utf-8", errors="replace").splitlines():
        move = _parse(raw) if raw.strip() else None
        if move is not None:
            moves.append(move)
    return moves


def _chain(
    moves: Sequence[BaseMove], ref: str, start: str, end: str, own_run: str | None
) -> tuple[BaseMove | None, bool]:
    """(last link of the chain start→end, whether a link is the own run's)."""
    candidates = [m for m in moves if m.ref == ref]
    used: set[int] = set()
    cur = start
    for _ in range(len(candidates)):
        found = next((i for i, m in enumerate(candidates) if i not in used and m.old == cur), None)
        if found is None:
            return None, False
        used.add(found)
        move = candidates[found]
        if own_run is not None and move.run == own_run:
            return None, True
        cur = move.new
        if cur == end:
            return move, False
    return None, False


def factory_chain(
    moves: Sequence[BaseMove], ref: str, start: str, end: str, own_run: str | None
) -> BaseMove | None:
    """Last entry of a chain of foreign moves of `ref` from `start` to `end`, else None."""
    return _chain(moves, ref, start, end, own_run)[0]


def wait_for_chain(
    root: Path,
    start_offset: int,
    ref: str,
    start: str,
    end: str,
    own_run: str | None,
    *,
    tries: int = 10,
    delay: float = 0.1,
) -> BaseMove | None:
    """Like ``factory_chain`` over the journal; waits briefly for a link still being written."""
    for attempt in range(max(tries, 1)):
        move, own = _chain(moves_since(root, start_offset), ref, start, end, own_run)
        if move is not None or own:
            return move
        if attempt + 1 < tries:
            time.sleep(delay)
    return None
