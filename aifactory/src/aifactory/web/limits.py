"""Session limits of the subscriptions behind the harnesses, for the dashboard's topbar.

``GET /api/repos/{id}/limits`` lists, for every harness the repository uses and every harness
available on this machine (``claude``, ``codex``; ``pi`` has no subscription limits), its
5-hour and weekly windows: how much is used and when the window resets. The global
``GET /api/limits`` lists only the available ones. A harness whose limits cannot be read
carries an ``error`` and no windows; the endpoint itself never fails because of one provider.

- Claude: the OAuth usage endpoint of the subscription Claude Code is logged in with. The
  token is read from the macOS keychain (``Claude Code-credentials``) and from
  ``~/.claude/.credentials.json``; expired tokens are skipped (only expired ones: an error
  without a request), the one expiring last wins. It is sent nowhere but
  ``api.anthropic.com``. HTTP 429 keeps the answer cached for ``Retry-After`` seconds.
- Codex: live ``account/rateLimits/read`` through app-server stdio. Session logs are
  an explicitly stale fallback; expired Codex windows are discarded.

Answers are cached for ``ttl`` seconds, so polling clients do not hammer the endpoint.
The last measured windows of every harness are kept in the dashboard's memory
(``measured_at``): a failed read returns them with ``stale`` and the ``error`` of the
failed read (expired Codex windows are removed). A harness never measured has
no windows and its ``error``. Nothing is written to the HAIFA home: tests of every run
check that it does not change while they run.
"""

from __future__ import annotations

import json
import math
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import yaml

from aifactory.harness import canonical
from aifactory.harness.codex import CODEX_PATH, launch_command

LIMITED_HARNESSES = ("claude", "codex")
LABELS = {"claude": "Claude", "codex": "Codex"}
WINDOW_LABELS = {"5h": "5h", "1w": "1w"}

CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_KEYCHAIN_SERVICE = "Claude Code-credentials"
CODEX_FILES_SCANNED = 20
CODEX_RPC_TIMEOUT = 8.0

Fetch = Callable[[str, dict[str, str]], Any]


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
            visit(yaml.safe_load(path.read_text(encoding="utf-8")))
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


# --- Claude -------------------------------------------------------------------------------


def _claude_token_candidates() -> list[str]:
    """Credential JSON texts Claude Code may be logged in with: keychain first, then the file.

    The keychain (macOS) is where Claude Code keeps a refreshed token; the file
    ``$CLAUDE_CONFIG_DIR|~/.claude/.credentials.json`` may hold an older, expired one.
    """
    found: list[str] = []
    if sys.platform == "darwin":
        try:
            proc = subprocess.run(
                ["security", "find-generic-password", "-s", CLAUDE_KEYCHAIN_SERVICE, "-w"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                encoding="utf-8",
            )
        except (OSError, subprocess.SubprocessError):
            proc = None
        if proc is not None and proc.returncode == 0 and proc.stdout.strip():
            found.append(proc.stdout.strip())
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    path = Path(config_dir) if config_dir else Path.home() / ".claude"
    try:
        found.append((path / ".credentials.json").read_text(encoding="utf-8"))
    except OSError:
        pass
    return found


TokenState = tuple[str, str | None]
"""``("ok", token)``, ``("expired", None)`` or ``("missing", None)``."""


def claude_token_state(now: Callable[[], float] = time.time) -> TokenState:
    """The best OAuth access token of the candidates, or why there is none.

    Candidates whose ``claudeAiOauth.expiresAt`` (ms) passed are dropped; of the rest the one
    expiring last wins, a candidate without ``expiresAt`` counts as valid with the lowest
    priority. Only expired candidates: ``expired``; none readable: ``missing``.
    """
    current_ms = now() * 1000
    best: tuple[float, str] | None = None
    expired = False
    for text in _claude_token_candidates():
        try:
            oauth = json.loads(text)["claudeAiOauth"]
            token = oauth["accessToken"]
        except (ValueError, KeyError, TypeError):
            continue
        if not isinstance(token, str) or not token:
            continue
        expires = oauth.get("expiresAt") if isinstance(oauth, dict) else None
        if isinstance(expires, int | float) and not isinstance(expires, bool):
            if expires <= current_ms:
                expired = True
                continue
            rank = float(expires)
        else:
            rank = float("-inf")
        if best is None or rank > best[0]:
            best = (rank, token)
    if best is not None:
        return "ok", best[1]
    return ("expired", None) if expired else ("missing", None)


def claude_token(now: Callable[[], float] = time.time) -> str | None:
    """The OAuth access token Claude Code is logged in with, or None."""
    return claude_token_state(now)[1]


def _retry_after(error: urllib.error.HTTPError) -> float | None:
    """Seconds from the ``Retry-After`` header (seconds or an HTTP date), or None."""
    headers = error.headers
    raw = headers.get("Retry-After") if headers is not None else None
    if not raw:
        return None
    raw = str(raw).strip()
    try:
        seconds = float(raw)
    except ValueError:
        try:
            at = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        seconds = (at - datetime.now(UTC)).total_seconds()
    return max(0.0, seconds)


def _http_get_json(url: str, headers: dict[str, str]) -> Any:
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=8) as response:  # noqa: S310 - fixed https URL
        return json.loads(response.read().decode("utf-8"))


def claude_limits(
    state: Callable[[], TokenState] = claude_token_state, fetch: Fetch = _http_get_json
) -> dict[str, Any]:
    entry: dict[str, Any] = {"harness": "claude", "label": LABELS["claude"], "windows": []}
    status, access = state()
    if status == "expired":
        entry["error"] = "přihlášení Claude Code vypršelo, spusť claude"
        return entry
    if access is None:
        entry["error"] = "Claude Code není přihlášený k předplatnému"
        return entry
    headers = {
        "Authorization": f"Bearer {access}",
        "anthropic-beta": "oauth-2025-04-20",
        "Content-Type": "application/json",
        "User-Agent": "haifa-dashboard",
    }
    try:
        data = fetch(CLAUDE_USAGE_URL, headers)
    except urllib.error.HTTPError as error:
        if error.code == 429:
            entry["rate_limited"] = True
            wait = _retry_after(error)
            if wait is None:
                entry["error"] = "Claude usage API omezuje dotazy, zkus to později"
            else:
                minutes = max(1, math.ceil(wait / 60))
                entry["error"] = f"Claude usage API omezuje dotazy, zkus za {minutes} min"
                entry["retry_after"] = wait
        elif error.code == 401:
            entry["error"] = "přihlášení Claude Code vypršelo, spusť claude"
        else:
            entry["error"] = f"HTTP {error.code}"
        return entry
    except (OSError, ValueError) as error:
        entry["error"] = f"limity nejsou dostupné: {error}"
        return entry
    for window_id, key in (("5h", "five_hour"), ("1w", "seven_day")):
        window = data.get(key) if isinstance(data, dict) else None
        if isinstance(window, dict) and isinstance(window.get("utilization"), int | float):
            resets = window.get("resets_at")
            entry["windows"].append(
                _window(
                    window_id, window["utilization"], resets if isinstance(resets, str) else None
                )
            )
    entry["error"] = None if entry["windows"] else "odpověď neobsahuje limity"
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
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
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
    used = raw.get("usedPercent", raw.get("used_percent"))
    if not isinstance(used, int | float):
        return None
    minutes = raw.get("windowDurationMins", raw.get("window_minutes"))
    if minutes not in (300, 10080):
        return None
    window_id = "5h" if minutes == 300 else "1w"
    resets = raw.get("resetsAt", raw.get("resets_at"))
    resets_iso = None
    if isinstance(resets, int | float):
        if resets <= now:
            return None
        try:
            resets_iso = datetime.fromtimestamp(resets).astimezone().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    return window_id, _window(window_id, used, resets_iso)


def codex_rate_limits(timeout: float = CODEX_RPC_TIMEOUT) -> dict[str, Any]:
    """Bounded, read-only RPC. Never request account credentials or start a turn.

    0.160.0 app-server has no --ignore-user-config flag (exec does). MCP is
    disabled with an override; no threads are opened. stderr is discarded to
    avoid leaking account/config details into dashboard error messages.
    """
    process = subprocess.Popen(
        launch_command(
            [
                CODEX_PATH,
                "app-server",
                "--stdio",
                "-c",
                "mcp_servers={}",
                "-c",
                "analytics.enabled=false",
            ]
        ),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        bufsize=1,
        cwd=Path.home(),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    messages: queue.Queue[str | None] = queue.Queue()
    deadline = time.monotonic() + timeout

    def read() -> None:
        try:
            assert process.stdout is not None
            for line in process.stdout:
                messages.put(line)
        finally:
            messages.put(None)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()

    def send(message: dict[str, Any]) -> None:
        assert process.stdin is not None
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    def response(request_id: int) -> dict[str, Any]:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Codex app-server timeout")
            try:
                line = messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError("Codex app-server timeout") from exc
            if line is None:
                raise ValueError("Codex app-server closed before responding")
            message = json.loads(line)
            if not isinstance(message, dict) or message.get("id") != request_id:
                continue
            if "error" in message or not isinstance(message.get("result"), dict):
                raise ValueError("Codex subscription limits unavailable; check codex login")
            return dict(message["result"])

    try:
        send(
            {
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {"name": "haifa_dashboard", "version": "1.0"},
                },
            }
        )
        response(1)
        send({"method": "initialized"})
        send({"id": 2, "method": "account/rateLimits/read"})
        return response(2)
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)
        reader.join(timeout=1)
        for pipe in (process.stdin, process.stdout):
            if pipe is not None:
                pipe.close()


def _codex_windows(limits: dict[str, Any], now: float) -> list[dict[str, Any]]:
    windows: dict[str, dict[str, Any]] = {}
    for key in ("primary", "secondary"):
        parsed = _codex_window(limits.get(key), now)
        if parsed is not None:
            windows.setdefault(parsed[0], parsed[1])
    return [windows[w] for w in ("5h", "1w") if w in windows]


def codex_limits(
    sessions: Callable[[], Path] = codex_sessions_dir,
    now: Callable[[], float] = time.time,
    rpc: Callable[[], dict[str, Any]] = codex_rate_limits,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"harness": "codex", "label": LABELS["codex"], "windows": []}
    try:
        data = rpc()
        buckets = data.get("rateLimitsByLimitId")
        limits = buckets.get("codex") if isinstance(buckets, dict) else None
        if not isinstance(limits, dict):
            limits = data.get("rateLimits")
            if isinstance(limits, dict) and limits.get("limitId") not in (None, "codex"):
                limits = None
        if isinstance(limits, dict):
            entry["windows"] = _codex_windows(limits, now())
        if entry["windows"]:
            entry["error"] = None
            return entry
        entry["error"] = "Codex: odpověď neobsahuje aktuální 5h/týdenní limity"
    except (OSError, ValueError, subprocess.SubprocessError):
        entry["error"] = "Codex limity nedostupné; ověřte codex login a instalaci app-server"
    best: tuple[str, dict[str, Any]] | None = None
    for path in _newest_files(sessions(), CODEX_FILES_SCANNED):
        found = _last_rate_limits(path)
        if found is not None and (best is None or found[0] > best[0]):
            best = found
    if best is None:
        return entry
    entry["windows"] = _codex_windows(best[1], now())
    if entry["windows"]:
        entry.update(stale=True, measured_at=best[0], source="session-log")
    return entry


# --- availability ------------------------------------------------------------------------


def available_harnesses(
    token_state: Callable[[], TokenState] = claude_token_state,
    which: Callable[[str], str | None] = shutil.which,
    sessions: Callable[[], Path] = codex_sessions_dir,
) -> list[str]:
    """Harnesses with limits usable on this machine, whatever any repository's roster says.

    Claude: a credential (even an expired one) or the ``claude`` CLI. Codex: the CLI
    (``CODEX_PATH`` or ``codex``) or its login/session files that ``codex_limits`` reads.
    """
    found: list[str] = []
    if token_state()[0] != "missing" or which("claude"):
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

READERS: dict[str, Callable[[], dict[str, Any]]] = {
    "claude": claude_limits,
    "codex": codex_limits,
}


def _passed(resets_at: str | None, now: datetime) -> bool:
    if not resets_at:
        return False
    try:
        at = datetime.fromisoformat(resets_at)
    except ValueError:
        return False
    if at.tzinfo is None:
        at = at.astimezone()
    return at <= now


def _stale(last: dict[str, Any], error: str | None, now: datetime) -> dict[str, Any]:
    """Last measured windows; expired Codex windows cannot imply available capacity."""
    windows = [
        _window(w["id"], 0.0, None) if _passed(w.get("resets_at"), now) else dict(w)
        for w in last.get("windows", [])
        if last.get("harness") != "codex" or not _passed(w.get("resets_at"), now)
    ]
    return {**last, "windows": windows, "error": error, "stale": True}


class LimitsSource:
    """Reads the limits of the shown harnesses, at most once per ``ttl`` seconds.

    Shown are the harnesses a repository uses plus those ``available`` on this machine (default:
    ``available_harnesses`` with the real readers, none with injected ``readers``), so
    switching a roster does not hide the other subscription. A reader answering with
    HTTP 429 starts a five-minute cooldown, doubling on repeated failures up to one hour;
    a longer ``retry_after`` always wins. Concurrent requests share one provider read.
    `last_file` gives a file that keeps the last measured windows across restarts; by
    default (None) they stay in memory only.
    """

    def __init__(
        self,
        readers: dict[str, Callable[[], dict[str, Any]]] | None = None,
        ttl: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        last_file: Callable[[], Path | None] = lambda: None,
        now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
        available: Callable[[], list[str]] | None = None,
        enabled: Callable[[str], bool] = lambda _: True,
    ) -> None:
        self.readers = READERS if readers is None else readers
        if available is None:
            available = available_harnesses if readers is None else list
        self.available = available
        self.enabled = enabled
        self.ttl = ttl
        self.clock = clock
        self.now = now
        self._last_file = last_file
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, float, dict[str, Any]]] = {}
        self._available: tuple[float, list[str]] | None = None
        self._last: dict[str, dict[str, Any]] | None = None
        self._read_locks = {name: threading.Lock() for name in self.readers}
        self._rate_failures: dict[str, int] = {}

    def _last_measured(self) -> dict[str, dict[str, Any]]:
        """The last measured entry per harness, read from the file on first use."""
        if self._last is None:
            self._last = {}
            path = self._last_file()
            if path is not None:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    data = None
                if isinstance(data, dict):
                    self._last = {
                        k: v for k, v in data.items() if isinstance(v, dict) and v.get("windows")
                    }
        return self._last

    def _remember(self, harness: str, entry: dict[str, Any]) -> None:
        last = self._last_measured()
        last[harness] = entry
        path = self._last_file()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(last, ensure_ascii=False), encoding="utf-8", newline="\n")
            tmp.replace(path)
        except OSError:
            pass  # remembered in memory only

    def _read(self, harness: str) -> dict[str, Any]:
        # A cold cache shared by several tabs must issue only one provider request.
        with self._read_locks[harness]:
            return self._read_once(harness)

    def _read_once(self, harness: str) -> dict[str, Any]:
        with self._lock:
            cached = self._cache.get(harness)
            if cached is not None and self.clock() - cached[0] < cached[1]:
                return cached[2]
        try:
            entry = self.readers[harness]()
        except Exception as error:  # noqa: BLE001 - one provider must not break the topbar
            entry = {
                "harness": harness,
                "label": LABELS.get(harness, harness),
                "windows": [],
                "error": str(error),
            }
        retry = entry.get("retry_after")
        hold = max(self.ttl, float(retry)) if isinstance(retry, int | float) else self.ttl
        if entry.get("rate_limited") or isinstance(retry, int | float):
            failures = self._rate_failures.get(harness, 0) + 1
            self._rate_failures[harness] = failures
            hold = max(hold, min(3600.0, 300.0 * 2 ** min(failures - 1, 4)))
            if harness == "claude" and entry.get("rate_limited"):
                entry = {
                    **entry,
                    "retry_after": hold,
                    "error": "Claude usage API omezuje dotazy, "
                    f"další dotaz nejdříve za {math.ceil(hold / 60)} min",
                }
        elif not entry.get("error"):
            self._rate_failures[harness] = 0
        with self._lock:
            if entry.get("windows") and not entry.get("error"):
                entry = {**entry, "measured_at": self.now().isoformat(), "stale": False}
                self._remember(harness, entry)
            else:
                last = self._last_measured().get(harness)
                if last is not None and not entry.get("windows"):
                    entry = _stale(last, entry.get("error"), self.now())
            self._cache[harness] = (self.clock(), hold, entry)
        return entry

    def _available_now(self) -> list[str]:
        """``available()``, cached for ``ttl`` seconds (it may ask the keychain)."""
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

    def get(self, repo: Path | None) -> dict[str, Any]:
        """Providers of the harnesses ``repo`` uses (if given) and of those available here."""
        shown = set(self._available_now())
        if repo is not None:
            shown.update(used_harnesses(repo))
        harnesses = [
            h for h in LIMITED_HARNESSES if h in shown and h in self.readers and self.enabled(h)
        ]
        return {"providers": [self._read(h) for h in harnesses]}
