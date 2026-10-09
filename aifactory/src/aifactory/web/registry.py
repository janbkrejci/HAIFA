"""The dashboard's repository registry: ``dashboard.yaml`` in the HAIFA home (D22).

The file holds the dashboard port and the repositories it serves, nothing else::

    version: 1
    port: 4700
    repos:
      - {id: haifa, name: HAIFA, path: /abs/path/HAIFA, added_at: "2026-10-04T10:00:00+00:00"}

``.factory/``, the backlog and the trace DB stay in each repository; adding or removing a
repository writes nothing into it. The home directory is created with mode 0700 and the
file with mode 0600.

Writes hold ``flock`` on ``dashboard.lock`` next to the file, re-read the file under the
lock, change the raw mapping (unknown keys, top-level or per entry, are kept) and replace
the file atomically (temporary file in the same directory, ``os.replace``). A file that
does not parse is never overwritten: writes fail with ``registry_invalid`` until it is
fixed by hand. Reads (``Registry.snapshot``) reload the file when its mtime, size or inode
changes; a broken file keeps the last valid state and returns a warning.

Ids are slugs of the folder name (``[a-z0-9-]{1,32}``), made unique with ``-2``, ``-3``
and never changed afterwards. ``inspect`` is reserved (``POST /api/repos/inspect``). A
repository is registered once: the same real path or the same device and inode of its
root counts as a duplicate. Only the dashboard reads this file.
"""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from aifactory import oscompat
from aifactory.config.settings import DEFAULT_PORT

REGISTRY_FILE = "dashboard.yaml"
LOCK_FILE = "dashboard.lock"
REGISTRY_VERSION = 1
MAX_ID = 32
ID_RE = re.compile(r"^[a-z0-9-]{1,32}$")
RESERVED_IDS = frozenset({"inspect"})

JsonDict = dict[str, Any]


class RepoError(Exception):
    """A registry or repository problem with an error ``code`` and extra ``data``."""

    def __init__(self, code: str, message: str, *, data: JsonDict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data: JsonDict = dict(data or {})


@dataclass(frozen=True)
class RepoEntry:
    """One registered repository."""

    id: str
    name: str
    path: str
    added_at: str

    def to_json(self) -> JsonDict:
        return {"id": self.id, "name": self.name, "path": self.path, "added_at": self.added_at}


@dataclass(frozen=True)
class RegistryState:
    """The validated content of ``dashboard.yaml``."""

    version: int
    port: int
    repos: tuple[RepoEntry, ...]

    def by_id(self, repo_id: str) -> RepoEntry | None:
        return next((e for e in self.repos if e.id == repo_id), None)


EMPTY = RegistryState(version=REGISTRY_VERSION, port=DEFAULT_PORT, repos=())


def registry_path(home: Path) -> Path:
    return home / REGISTRY_FILE


def ensure_home(home: Path) -> Path:
    """The home directory, created with mode 0700 when missing."""
    if not home.is_dir():
        home.mkdir(parents=True, exist_ok=True)
        os.chmod(home, 0o700)
    return home


def slugify(name: str) -> str:
    """``name`` as an id: lowercase ``[a-z0-9-]``, at most 32 characters, never empty."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    slug = slug[:MAX_ID].strip("-")
    return slug or "repo"


def unique_id(base: str, taken: set[str] | frozenset[str]) -> str:
    """``base``, else ``base-2``, ``base-3``, … (cut to fit 32), not in ``taken`` or reserved."""
    used = set(taken) | RESERVED_IDS
    if base not in used:
        return base
    n = 2
    while True:
        suffix = f"-{n}"
        candidate = base[: MAX_ID - len(suffix)].rstrip("-") + suffix
        if candidate not in used:
            return candidate
        n += 1


def same_repo(a: Path | str, b: Path | str) -> bool:
    """The same folder: equal real paths, or both exist with the same device and inode."""
    if os.path.realpath(a) == os.path.realpath(b):
        return True
    try:
        sa, sb = os.stat(a), os.stat(b)
    except OSError:
        return False
    return (sa.st_dev, sa.st_ino) == (sb.st_dev, sb.st_ino)


def _invalid(label: str, problem: str) -> RepoError:
    return RepoError("registry_invalid", f"{label}: {problem}", data={"path": label})


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_registry(text: str | None, label: str) -> tuple[RegistryState, JsonDict]:
    """The validated state and the raw mapping; ``registry_invalid`` when it is broken."""
    if text is None or not text.strip():
        return EMPTY, {}
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise _invalid(label, f"invalid YAML: {exc}") from None
    if raw is None:
        return EMPTY, {}
    if not isinstance(raw, dict):
        raise _invalid(label, f"must be a mapping, got {type(raw).__name__}")
    version = raw.get("version", REGISTRY_VERSION)
    if not _is_int(version):
        raise _invalid(label, "version must be an integer")
    port = raw.get("port", DEFAULT_PORT)
    if not _is_int(port) or not 1 <= port <= 65535:
        raise _invalid(label, "port must be an integer from 1 to 65535")
    items = raw.get("repos", [])
    if items is None:
        items = []
    if not isinstance(items, list):
        raise _invalid(label, "repos must be a list")
    entries: list[RepoEntry] = []
    seen: set[str] = set()
    for n, item in enumerate(items):
        where = f"repos[{n}]"
        if not isinstance(item, dict):
            raise _invalid(label, f"{where} must be a mapping")
        repo_id = item.get("id")
        if not isinstance(repo_id, str) or not ID_RE.match(repo_id):
            raise _invalid(label, f"{where}.id must match [a-z0-9-]{{1,32}}")
        if repo_id in seen:
            raise _invalid(label, f"{where}.id {repo_id!r} is used twice")
        seen.add(repo_id)
        path = item.get("path")
        if not isinstance(path, str) or not os.path.isabs(path):
            raise _invalid(label, f"{where}.path must be an absolute path")
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise _invalid(label, f"{where}.name must be a non-empty string")
        added = item.get("added_at")
        if isinstance(added, datetime):
            added = added.isoformat()
        if not isinstance(added, str) or not added:
            raise _invalid(label, f"{where}.added_at must be a timestamp")
        entries.append(RepoEntry(id=repo_id, name=name, path=path, added_at=added))
    return RegistryState(version=version, port=port, repos=tuple(entries)), raw


Stamp = tuple[int, int, int]


class Registry:
    """``dashboard.yaml`` in ``home``: cached reads, locked atomic writes."""

    def __init__(self, home: Path) -> None:
        self.home = home
        self.path = registry_path(home)
        self._lock = threading.Lock()
        self._stamp: Stamp | None = None
        self._state: RegistryState = EMPTY
        self._warning: str | None = None

    def _file_stamp(self) -> Stamp | None:
        try:
            st = self.path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size, st.st_ino)

    def _read_text(self) -> str | None:
        try:
            return self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def snapshot(self) -> tuple[RegistryState, list[str]]:
        """The current state and warnings; reloaded when the file changed."""
        with self._lock:
            stamp = self._file_stamp()
            if stamp is None:
                self._stamp, self._state, self._warning = None, EMPTY, None
                return self._state, []
            if stamp != self._stamp:
                self._stamp = stamp
                try:
                    state, _raw = parse_registry(self._read_text(), str(self.path))
                except (RepoError, OSError) as exc:
                    problem = exc.message if isinstance(exc, RepoError) else str(exc)
                    self._warning = f"{problem}; the dashboard keeps the last valid registry"
                else:
                    self._state, self._warning = state, None
            return self._state, ([self._warning] if self._warning else [])

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        ensure_home(self.home)
        fd = os.open(self.home / LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            oscompat.lock(fd, blocking=True)
            try:
                yield
            finally:
                oscompat.unlock(fd)
        finally:
            os.close(fd)

    def _write(self, raw: JsonDict) -> None:
        text = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, default_flow_style=False)
        fd, tmp = tempfile.mkstemp(prefix=f".{REGISTRY_FILE}.", suffix=".tmp", dir=self.home)
        try:
            oscompat.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _mutate(self, fn: Callable[[JsonDict, RegistryState], bool]) -> RegistryState:
        """Apply ``fn`` to the raw mapping under the lock; write when it returns True."""
        with self._locked():
            state, raw = parse_registry(self._read_text(), str(self.path))
            raw = dict(raw)
            if fn(raw, state):
                out: JsonDict = {
                    "version": raw.pop("version", REGISTRY_VERSION),
                    "port": raw.pop("port", state.port),
                    "repos": raw.pop("repos", None) or [],
                }
                out.update(raw)  # unknown keys stay
                self._write(out)
        return self.snapshot()[0]

    def add(
        self,
        root: Path,
        *,
        now: datetime | None = None,
        check: Callable[[RegistryState], None] | None = None,
    ) -> tuple[RepoEntry, bool]:
        """Register the repository at ``root`` (vetted); ``(entry, created)``, idempotent.

        ``check`` runs under the lock against the current entries before a new one is
        added and may raise ``RepoError`` (the trace DB check).
        """
        result: list[tuple[RepoEntry, bool]] = []

        def change(raw: JsonDict, state: RegistryState) -> bool:
            for entry in state.repos:
                if same_repo(entry.path, root):
                    result.append((entry, False))
                    return False
            if check is not None:
                check(state)
            repo_id = unique_id(slugify(root.name), {e.id for e in state.repos})
            stamp = (now or datetime.now(UTC)).isoformat(timespec="seconds")
            entry = RepoEntry(id=repo_id, name=root.name, path=str(root), added_at=stamp)
            repos = raw.get("repos")
            items = list(repos) if isinstance(repos, list) else []
            items.append(entry.to_json())
            raw["repos"] = items
            result.append((entry, True))
            return True

        self._mutate(change)
        return result[0]

    def remove(self, repo_id: str) -> RepoEntry | None:
        """Drop the entry ``repo_id`` (nothing else); None when there is none."""
        removed: list[RepoEntry] = []

        def change(raw: JsonDict, state: RegistryState) -> bool:
            entry = state.by_id(repo_id)
            if entry is None:
                return False
            items = raw.get("repos") or []
            raw["repos"] = [
                i for i in items if not (isinstance(i, dict) and i.get("id") == repo_id)
            ]
            removed.append(entry)
            return True

        self._mutate(change)
        return removed[0] if removed else None

    def set_port(self, port: int) -> RegistryState:
        """Store the dashboard port (used from the next start)."""

        def change(raw: JsonDict, state: RegistryState) -> bool:
            raw["port"] = port
            return True

        return self._mutate(change)
