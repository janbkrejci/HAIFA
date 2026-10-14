"""Session limits of the subscriptions behind the harnesses, for the dashboard's topbar.

``GET /api/repos/{id}/limits`` lists, for every harness the repository uses and every harness
available on this machine (``claude``, ``codex``; ``pi`` has no subscription limits), its
5-hour and weekly windows: how much is used and when the window resets. The global
``GET /api/limits`` lists only the available ones. A harness whose limits cannot be read
carries an ``error`` and no windows; the endpoint itself never fails because of one provider.

The limits come only from the interactions with the harnesses, never from a request of
their own: every value is the last one a harness reported (``measured_at``).

- Claude: the last ``rate_limit_event`` in the stream-json output of an agent of a HAIFA
  run (``<repo>/.factory/data/sessions/<run>/<agent>/raw_output.jsonl``) of the
  registered repositories. ``measured_at`` is the time the output file was last written.
- Codex: the last ``rate_limits`` of a token count in Codex's own session logs
  (``$CODEX_HOME/sessions``), written by every Codex session on this machine.

A window whose reset time passed is shown as unused (Claude) or dropped (Codex). Answers
are cached for ``ttl`` seconds. Nothing is written anywhere.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from aifactory import yamlload
from aifactory.harness import canonical
from aifactory.harness.codex import CODEX_PATH

LIMITED_HARNESSES = ("claude", "codex")
LABELS = {"claude": "Claude", "codex": "Codex"}
WINDOW_LABELS = {"5h": "5h", "1w": "1w"}

CODEX_FILES_SCANNED = 20
CLAUDE_FILES_SCANNED = 20
SESSIONS_DIR = Path(".factory") / "data" / "sessions"

Reader = Callable[[list[Path]], dict[str, Any]]


def used_harnesses(repo: Path) -> list[str]:
    """Harnesses with limits named in ``.factory/agents.yaml`` and the workflows, in order."""
    found: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("harness", "coding_agent") and isinstance(value, str):
                    try:
                        found.add(canonical(value))
                    except ValueError:
                        pass
                else:
                    visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    factory = repo / ".factory"
    files = [factory / "agents.yaml"]
    workflows = factory / "workflows"
    if workflows.is_dir():
        files += sorted(workflows.glob("*.y*ml"))
    for path in files:
        try:
            visit(yamlload.safe_load(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            continue
    return [name for name in LIMITED_HARNESSES if name in found]


def _window(window_id: str, used: float, resets_at: str | None) -> dict[str, Any]:
    used = max(0.0, min(100.0, float(used)))
    return {
        "id": window_id,
        "label": WINDOW_LABELS[window_id],
        "used": used,
        "left": 100.0 - used,
        "resets_at": resets_at,
    }


def _iso(epoch: float) -> str | None:
    try:
        return datetime.fromtimestamp(epoch).astimezone().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _reversed_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[::-1]
    except OSError:
        return []


# --- Claude -------------------------------------------------------------------------------


def _claude_outputs(roots: Iterable[Path], limit: int) -> list[Path]:
    """The agent outputs of HAIFA runs in ``roots``, last written first, at most ``limit``."""
    found: list[tuple[float, Path]] = []
    for root in dict.fromkeys(roots):
        for path in (root / SESSIONS_DIR).glob("*/*/raw_output.jsonl"):
            try:
                found.append((path.stat().st_mtime, path))
            except OSError:
                continue
    found.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in found[:limit]]


def _last_claude_windows(path: Path) -> dict[str, Any] | None:
    """``unifiedWindows`` of the last ``rate_limit_event`` in ``path``."""
    for line in _reversed_lines(path):
        if '"rate_limit_event"' not in line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        info = event.get("rate_limit_info") if isinstance(event, dict) else None
        windows = info.get("unifiedWindows") if isinstance(info, dict) else None
        if isinstance(windows, dict) and windows:
            return windows
    return None


def _claude_window(window_id: str, raw: Any, now: float) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    used = raw.get("utilization")
    if not isinstance(used, int | float) or isinstance(used, bool):
        return None
    resets = raw.get("resetsAt")
    if isinstance(resets, int | float) and not isinstance(resets, bool):
        if resets <= now:
            return _window(window_id, 0.0, None)  # the window reset since then
        return _window(window_id, used * 100, _iso(resets))
    return _window(window_id, used * 100, None)


def claude_limits(roots: list[Path], now: Callable[[], float] = time.time) -> dict[str, Any]:
    entry: dict[str, Any] = {"harness": "claude", "label": LABELS["claude"], "windows": []}
    for path in _claude_outputs(roots, CLAUDE_FILES_SCANNED):
        raw = _last_claude_windows(path)
        if raw is None:
            continue
        current = now()
        windows = [
            _claude_window(window_id, raw.get(key), current)
            for window_id, key in (("5h", "five_hour"), ("1w", "seven_day"))
        ]
        entry["windows"] = [w for w in windows if w is not None]
        if entry["windows"]:
            try:
                entry["measured_at"] = _iso(path.stat().st_mtime)
            except OSError:
                entry["measured_at"] = None
            entry["error"] = None
            return entry
    entry["error"] = "zatím žádný běh s Claude neukázal limity"
    return entry


# --- Codex --------------------------------------------------------------------------------


def codex_sessions_dir() -> Path:
    home = os.environ.get("CODEX_HOME")
    return (Path(home) if home else Path.home() / ".codex") / "sessions"


def _newest_files(root: Path, limit: int) -> Iterator[Path]:
    """Session logs, newest day first, at most ``limit`` of them."""
    count = 0

    def dirs(path: Path) -> list[Path]:
        try:
            return sorted((p for p in path.iterdir() if p.is_dir()), reverse=True)
        except OSError:
            return []

    for year in dirs(root):
        for month in dirs(year):
            for day in dirs(month):
                try:
                    files = sorted(
                        day.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
                    )
                except OSError:
                    continue
                for path in files:
                    yield path
                    count += 1
                    if count >= limit:
                        return


def _last_rate_limits(path: Path) -> tuple[str, dict[str, Any]] | None:
    """The timestamp and ``rate_limits`` of the last token count with a window in ``path``."""
    for line in _reversed_lines(path):
        if '"rate_limits"' not in line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        payload = event.get("payload") if isinstance(event, dict) else None
        limits = payload.get("rate_limits") if isinstance(payload, dict) else None
        if not isinstance(limits, dict):
            continue
        if limits.get("limit_id") not in (None, "codex"):
            continue
        if isinstance(limits.get("primary"), dict) or isinstance(limits.get("secondary"), dict):
            return str(event.get("timestamp") or ""), limits
    return None


def _codex_window(raw: Any, now: float) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(raw, dict):
        return None
    used = raw.get("used_percent")
    if not isinstance(used, int | float):
        return None
    minutes = raw.get("window_minutes")
    if minutes not in (300, 10080):
        return None
    window_id = "5h" if minutes == 300 else "1w"
    resets = raw.get("resets_at")
    resets_iso = None
    if isinstance(resets, int | float):
        if resets <= now:
            return None
        resets_iso = _iso(resets)
        if resets_iso is None:
            return None
    return window_id, _window(window_id, used, resets_iso)


def _codex_windows(limits: dict[str, Any], now: float) -> list[dict[str, Any]]:
    windows: dict[str, dict[str, Any]] = {}
    for key in ("primary", "secondary"):
        parsed = _codex_window(limits.get(key), now)
        if parsed is not None:
            windows.setdefault(parsed[0], parsed[1])
    return [windows[w] for w in ("5h", "1w") if w in windows]


def _local_iso(timestamp: str) -> str | None:
    try:
        at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return at.astimezone().isoformat()


def codex_limits(
    roots: list[Path] | None = None,
    sessions: Callable[[], Path] = codex_sessions_dir,
    now: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """``roots`` is unused: Codex keeps its session logs in its own home."""
    entry: dict[str, Any] = {"harness": "codex", "label": LABELS["codex"], "windows": []}
    best: tuple[str, dict[str, Any]] | None = None
    for path in _newest_files(sessions(), CODEX_FILES_SCANNED):
        found = _last_rate_limits(path)
        if found is not None and (best is None or found[0] > best[0]):
            best = found
    if best is not None:
        entry["windows"] = _codex_windows(best[1], now())
    if entry["windows"]:
        entry["measured_at"] = _local_iso(best[0]) if best is not None else None
        entry["error"] = None
    elif best is None:
        entry["error"] = "zatím žádné sezení Codexu neukázalo limity"
    else:
        entry["error"] = "okna z posledního sezení Codexu už vypršela"
    return entry


# --- availability ------------------------------------------------------------------------


def available_harnesses(
    which: Callable[[str], str | None] = shutil.which,
    sessions: Callable[[], Path] = codex_sessions_dir,
) -> list[str]:
    """Harnesses with limits usable on this machine, whatever any repository's roster says.

    Claude: the ``claude`` CLI. Codex: the CLI (``CODEX_PATH`` or ``codex``) or its
    login/session files that ``codex_limits`` reads.
    """
    found: list[str] = []
    if which("claude"):
        found.append("claude")
    codex_dir = sessions().parent
    if (
        which(CODEX_PATH)
        or which("codex")
        or (codex_dir / "auth.json").is_file()
        or sessions().is_dir()
    ):
        found.append("codex")
    return found


# --- cache --------------------------------------------------------------------------------

READERS: dict[str, Reader] = {
    "claude": claude_limits,
    "codex": codex_limits,
}


class LimitsSource:
    """Reads the limits of the shown harnesses, at most once per ``ttl`` seconds.

    Shown are the harnesses a repository uses plus those ``available`` on this machine (default:
    ``available_harnesses`` with the real readers, none with injected ``readers``), so
    switching a roster does not hide the other subscription. ``roots`` gives the registered
    repositories whose HAIFA runs the Claude reader searches; the repository asked about is
    searched too.
    """

    def __init__(
        self,
        readers: dict[str, Reader] | None = None,
        ttl: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        available: Callable[[], list[str]] | None = None,
        enabled: Callable[[str], bool] = lambda _: True,
        roots: Callable[[], list[Path]] = list,
    ) -> None:
        self.readers = READERS if readers is None else readers
        if available is None:
            available = available_harnesses if readers is None else list
        self.available = available
        self.enabled = enabled
        self.roots = roots
        self.ttl = ttl
        self.clock = clock
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, tuple[Path, ...]], tuple[float, dict[str, Any]]] = {}
        self._available: tuple[float, list[str]] | None = None

    def _read(self, harness: str, roots: list[Path]) -> dict[str, Any]:
        key = (harness, tuple(roots))
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and self.clock() - cached[0] < self.ttl:
                return cached[1]
        try:
            entry = self.readers[harness](roots)
        except Exception as error:  # noqa: BLE001 - one provider must not break the topbar
            entry = {
                "harness": harness,
                "label": LABELS.get(harness, harness),
                "windows": [],
                "error": str(error),
            }
        with self._lock:
            self._cache[key] = (self.clock(), entry)
        return entry

    def _available_now(self) -> list[str]:
        """``available()``, cached for ``ttl`` seconds."""
        with self._lock:
            if self._available is not None and self.clock() - self._available[0] < self.ttl:
                return self._available[1]
        try:
            found = list(self.available())
        except Exception:  # noqa: BLE001 - detection must not break the topbar
            found = []
        with self._lock:
            self._available = (self.clock(), found)
        return found

    def _roots(self, repo: Path | None) -> list[Path]:
        try:
            roots = [Path(p).resolve() for p in self.roots()]
        except Exception:  # noqa: BLE001 - an unreadable registry must not break the topbar
            roots = []
        if repo is not None:
            roots.append(repo.resolve())
        return sorted(set(roots))

    def get(self, repo: Path | None) -> dict[str, Any]:
        """Providers of the harnesses ``repo`` uses (if given) and of those available here."""
        shown = set(self._available_now())
        if repo is not None:
            shown.update(used_harnesses(repo))
        harnesses = [
            h for h in LIMITED_HARNESSES if h in shown and h in self.readers and self.enabled(h)
        ]
        roots = self._roots(repo)
        return {"providers": [self._read(h, roots) for h in harnesses]}
