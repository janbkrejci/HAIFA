"""Journal of backlog writes made by factory commands, so a run's guard can tell them apart.

Several task runs may work at the same time. While an agent phase of run A is
going on, the operator may add or edit tasks through the factory (``task add``,
``task edit``, ``task link``, ``backlog auto-continue``, ``backlog auto-merge``;
from the CLI or the
dashboard). Those commands write files of the main checkout; without more
information the guard of run A would blame its agent, undo the write and fail
the run.

Every such write appends one JSON line to
``<git common dir>/haifa/main-writes.jsonl`` *after* the file was replaced: the
checkout and path, the sha256 of the content before (``None`` when the file did
not exist) and after the write, the mode of the file and ``run`` — the value of
``HAIFA_RUN_ID`` in the writing process. The written content itself is kept by
digest under ``<git common dir>/haifa/main-writes/<sha256>`` so the guard can put
it back when the agent overwrites it. A task run sets ``HAIFA_RUN_ID`` while its
workflow runs; agents inherit it, and so does every ``factory`` command an agent
starts, so an entry carrying the run's own id counts as a write of the agent.

Known limit: an agent that appends a forged entry with a foreign ``run`` to the
journal (and stores a matching blob) fools the guard, like with ``basemoves.py``.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from aifactory.run import backup, gitops
from aifactory.run.basemoves import RUN_ENV


@dataclass(frozen=True)
class MainWrite:
    checkout: str
    path: str
    old: str | None
    new: str
    mode: int
    run: str | None
    command: str


@dataclass
class Accepted:
    """What the foreign factory writes of a phase explain."""

    states: dict[str, tuple[bytes, int]] = field(default_factory=dict)
    """Path → content and mode the factory left there."""
    agent_first: list[str] = field(default_factory=list)
    """Paths someone else changed before a factory write replaced them."""


def _common_dir(root: Path) -> Path | None:
    common = gitops.common_dir(root)
    return None if common is None else common / "haifa"


def journal(root: Path) -> Path | None:
    """Path of the journal in the git common dir of `root` (None outside a repo)."""
    base = _common_dir(root)
    return None if base is None else base / "main-writes.jsonl"


def _blobs(root: Path) -> Path | None:
    base = _common_dir(root)
    return None if base is None else base / "main-writes"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def offset(root: Path) -> int:
    """Current size of the journal in bytes (0 when it does not exist)."""
    path = journal(root)
    if path is None:
        return 0
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _store(blobs: Path, digest: str, data: bytes) -> None:
    target = blobs / digest
    if target.is_file():
        return
    blobs.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=blobs, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, target)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def record(
    root: Path, path: str, old: bytes | None, new: bytes, *, mode: int, command: str
) -> None:
    """Append one factory write of `path` in checkout `root`; never raises."""
    try:
        target = journal(root)
        blobs = _blobs(root)
        if target is None or blobs is None:
            return
        digest = _sha(new)
        _store(blobs, digest, new)
        entry = MainWrite(
            checkout=str(root.resolve()),
            path=Path(path).as_posix(),
            old=_sha(old) if old is not None else None,
            new=digest,
            mode=mode & 0o777,
            run=os.environ.get(RUN_ENV) or None,
            command=command,
        )
        line = (json.dumps(asdict(entry)) + "\n").encode("utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
    except (OSError, RuntimeError, ValueError):
        return


def _parse(line: str) -> MainWrite | None:
    try:
        data = json.loads(line)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    checkout, path, new = data.get("checkout"), data.get("path"), data.get("new")
    if not (isinstance(checkout, str) and isinstance(path, str) and isinstance(new, str)):
        return None
    old = data.get("old")
    if old is not None and not isinstance(old, str):
        return None
    mode = data.get("mode")
    run = data.get("run")
    command = data.get("command")
    return MainWrite(
        checkout=checkout,
        path=path,
        old=old,
        new=new,
        mode=mode if isinstance(mode, int) and not isinstance(mode, bool) else 0,
        run=run if isinstance(run, str) and run else None,
        command=command if isinstance(command, str) else "",
    )


def writes_since(root: Path, start: int) -> list[MainWrite]:
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
    writes: list[MainWrite] = []
    for raw in data.decode("utf-8", errors="replace").splitlines():
        write = _parse(raw) if raw.strip() else None
        if write is not None:
            writes.append(write)
    return writes


def content(root: Path, digest: str) -> bytes | None:
    """The stored content with sha256 `digest` (None when missing or corrupt)."""
    blobs = _blobs(root)
    if blobs is None or not digest or "/" in digest or digest.startswith("."):
        return None
    try:
        data = (blobs / digest).read_bytes()
    except OSError:
        return None
    return data if _sha(data) == digest else None


def _foreign(root: Path, writes: Sequence[MainWrite], own_run: str | None) -> list[MainWrite]:
    here = root.resolve()
    return [w for w in writes if Path(w.checkout) == here and (own_run is None or w.run != own_run)]


def accept(
    root: Path,
    writes: Sequence[MainWrite],
    expected: Callable[[str], backup.FileState],
    own_run: str | None,
) -> Accepted:
    """Chain the foreign writes of every path from its `expected` state before the phase.

    A write whose content is already the expected one is skipped (the backup
    caught it, or it changed nothing). A write whose ``old`` is not the state
    known so far means someone else changed the file first: the path is listed
    in ``agent_first``. The last foreign write of a path decides its state.
    """
    result = Accepted()
    by_path: dict[str, list[MainWrite]] = {}
    for w in _foreign(root, writes, own_run):
        by_path.setdefault(w.path, []).append(w)
    for path, chain in by_path.items():
        state = expected(path)
        cur: str | None = None if state.kind == "absent" else state.digest
        last: MainWrite | None = None
        for w in chain:
            if w.new == cur:
                continue
            if w.old != cur and path not in result.agent_first:
                result.agent_first.append(path)
            cur = w.new
            last = w
        if last is None:
            continue
        data = content(root, last.new)
        if data is None:
            result.agent_first = [p for p in result.agent_first if p != path]
            continue
        result.states[path] = (data, last.mode)
    return result


def wait_for_writes(
    root: Path,
    start: int,
    paths_off: Sequence[str],
    *,
    tries: int = 10,
    delay: float = 0.1,
) -> list[MainWrite]:
    """The journal since `start`; waits briefly while a path of `paths_off` has no entry.

    A factory command writes the file first and the journal line right after, so
    a write that just happened may not be journaled yet. Only waits when there is
    any path without an entry; the caller decides which entries it accepts.
    """
    writes = writes_since(root, start)
    wanted = {p for p in paths_off if p != backup.INDEX}
    for _ in range(max(tries, 1) - 1):
        if wanted <= {w.path for w in writes}:
            break
        time.sleep(delay)
        writes = writes_since(root, start)
    return writes
