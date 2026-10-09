"""The F3 acceptance test's repo, fake-harness script and ``factory obs`` server (not fixtures).

The repo has ``.factory/`` (provider ``local``, workflow ``plan-commit``) and a backlog
with one module and one step but no task: the test creates the tasks in the browser.
The server is the real ``factory obs`` started through ``validation.worker``, which
installs the fake harness of ``validation.fake`` first; ``claude``, ``codex``, ``pi``
and ``gh`` point at a tripwire, so no model and no hosting is ever reached. The server
gets its own ``HAIFA_HOME`` (a temporary directory): ``factory obs --repo`` registers the
repo in its ``dashboard.yaml`` and the dashboard starts every run as a separate process
(again through ``validation.worker``) and writes its envelope and output to ``logs/``
there. The repo's API is under ``/api/repos/<id>/`` (``ObsServer.api``).
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import yaml

from aifactory import oscompat
from aifactory.web.registry import REGISTRY_FILE, same_repo

AIFACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AIFACTORY / "tests" / "run"))

from run_repo import files as run_repo_files  # noqa: E402

__all__ = [
    "T01",
    "T02",
    "ObsServer",
    "api_get",
    "fake_script",
    "git",
    "log_tail",
    "make_f3_repo",
    "obs_server",
    "run_logs_tail",
    "run_state",
    "runs_report",
    "task_runs",
    "tripwire",
    "wait_for",
]

T01 = "M01-S01-T01"
T02 = "M01-S01-T02"
STEP = "M01-S01"
HEALTH_TIMEOUT_S = 20.0
API_TIMEOUT_S = 10.0
REMOVED_ENV = ("HAIFA_SANDBOX_REPO", "HAIFA_VALIDATE_HIDDEN", "HAIFA_VALIDATE_FAKE")
TRIPWIRE_ENV = ("AIFACTORY_GH", "CODEX_PATH", "CLAUDE_CODE_PATH", "PI_PATH")
T = TypeVar("T")
GITIGNORE = (
    ".factory/local.yaml\n.factory/trace.db*\n.factory/worktrees/\n.factory/data/\n__pycache__/\n"
)


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return proc.stdout.strip()


def make_f3_repo(path: Path) -> Path:
    """A git repo on ``main`` (no remote) with ``.factory/`` and an empty step ``M01-S01``."""
    content = {
        rel: text
        for rel, text in run_repo_files("claude").items()
        if not rel.startswith("backlog/M01-core/S01-model/M01-S01-T")
    }
    content[".factory/config.yaml"] = "base: main\ngit_provider: local\n"
    content[".gitignore"] = GITIGNORE
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "commit.gpgsign", "false")
    for rel, text in content.items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "init")
    return path.resolve()


def _planner_call(name: str, value: int) -> dict[str, Any]:
    rel = f"src/app/{name}.py"
    return {
        "envelope": {
            "status": "success",
            "summary": f"add {rel}",
            "artifacts": [],
            "changed_files": [rel],
            "commit_message": f"Add {name}",
        },
        "edits": [{"path": rel, "write": f"{name.upper()} = {value}\n"}],
    }


def fake_script(path: Path) -> Path:
    """One planner call per run: the first writes ``src/app/first.py``, the second ``second.py``."""
    script = {"agents": {"planner": [_planner_call("first", 1), _planner_call("second", 2)]}}
    path.write_text(json.dumps(script, indent=2), encoding="utf-8", newline="\n")
    return path


def tripwire(directory: Path) -> tuple[Path, Path]:
    """An executable that records it ran and fails; returns (tripwire, marker file).

    Offline version/login/catalog probes and the limits RPC never call a model;
    allow these explicitly while recording any model/hosting command.
    """
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / "real-harness-reached"
    script = directory / "tripwire"
    script.write_text(
        '#!/bin/sh\ncase "$*" in\n'
        '"--version"|"auth status"|"login status") echo "test CLI 1.0"; exit 0 ;;\n'
        '"--list-models") echo "provider model context"; echo "openai gpt-5.5 272K"; exit 0 ;;\n'
        '"app-server --stdio "*) exit 0 ;;\nesac\n'
        f'echo "$0 $*" >> "{marker}"\nexit 97\n',
        encoding="utf-8",
        newline="\n",
    )
    script.chmod(0o755)
    return script, marker


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def log_tail(log: Path, lines: int = 80) -> str:
    if not log.is_file():
        return "(no server log)"
    text = log.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(text[-lines:])


def run_logs_tail(home: Path, lines: int = 60) -> str:
    """The tail of the newest outputs of the run processes in ``<home>/logs``."""
    logs = home / "logs"
    found = sorted(logs.glob("*.log"), key=lambda p: p.stat().st_mtime) if logs.is_dir() else []
    if not found:
        return "(no run logs)"
    parts = []
    for path in found[-2:]:
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
        parts.append(f"--- {path.name}\n" + "\n".join(text[-lines:]))
    return "\n".join(parts)


def _server_env(script: Path, wire: Path, home: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key in REMOVED_ENV:
        env.pop(key, None)
    env["HAIFA_HOME"] = str(home)
    env["HAIFA_UPDATE_REPO"] = ""  # Tests never query the real GitHub release API.
    env["HAIFA_VALIDATE_FAKE"] = str(script)
    old = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(AIFACTORY) + (os.pathsep + old if old else "")
    env["UV_NO_SYNC"] = "1"
    env["ENGINEER_NAME"] = "tester"
    for key in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        env[key] = "Test"
    for key in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        env[key] = "test@example.com"
    for key in TRIPWIRE_ENV:
        env[key] = str(wire)
    return env


def _healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=2) as response:
            return int(response.status) == 200
    except (urllib.error.URLError, OSError):
        return False


@dataclass(frozen=True)
class ObsServer:
    """A running ``factory obs``: its base URL and the id of the repo in its registry."""

    url: str
    repo_id: str

    @property
    def api(self) -> str:
        """The base URL of the repo's API (``/api/repos/<id>``)."""
        if not self.repo_id:
            raise ValueError("empty dashboard has no repo API")
        return f"{self.url}/api/repos/{urllib.parse.quote(self.repo_id)}"


def registered_id(home: Path, repo: Path) -> str:
    """The id of ``repo`` in ``<home>/dashboard.yaml``."""
    data = yaml.safe_load((home / REGISTRY_FILE).read_text(encoding="utf-8"))
    for entry in data.get("repos") or []:
        if same_repo(entry["path"], repo):
            return str(entry["id"])
    raise AssertionError(f"{repo} is not in the registry of {home}: {data}")


@contextlib.contextmanager
def obs_server(
    repo: Path | None, script: Path, wire: Path, log: Path, home: Path
) -> Iterator[ObsServer]:
    """``factory obs`` over the fake harness; omit ``repo`` for an empty dashboard.

    On exit the server gets SIGINT (Windows: it is terminated) and every run still
    ``running`` in the trace DB is killed, so a failed test leaves no run process behind.
    """
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    argv = [
        sys.executable,
        "-m",
        "validation.worker",
        "obs",
        *(["--repo", str(repo)] if repo is not None else []),
        "--port",
        str(port),
        "--no-open",
    ]
    with log.open("w", encoding="utf-8", newline="\n") as out:
        # stdout goes to a file: the engine prints there and a full pipe would stall the server
        proc = subprocess.Popen(
            argv,
            cwd=AIFACTORY,
            env=_server_env(script, wire, home),
            stdout=out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + HEALTH_TIMEOUT_S
            while not _healthy(url):
                if proc.poll() is not None:
                    raise AssertionError(
                        f"factory obs exited with {proc.returncode}:\n{log_tail(log)}"
                    )
                if time.monotonic() > deadline:
                    raise AssertionError(f"factory obs did not start on {url}:\n{log_tail(log)}")
                time.sleep(0.2)
            yield ObsServer(url, registered_id(home, repo) if repo is not None else "")
        finally:
            repos = {repo} if repo is not None else set()
            with contextlib.suppress(OSError, ValueError, yaml.YAMLError):
                data = yaml.safe_load((home / REGISTRY_FILE).read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("repos"), list):
                    for entry in data["repos"]:
                        if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                            repos.add(Path(entry["path"]))
            if proc.poll() is None:
                if sys.platform == "win32":  # no SIGINT for another process on Windows
                    proc.terminate()
                else:
                    proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(10)
            for registered in repos:
                _kill_running_runs(registered)


def _kill_running_runs(repo: Path) -> None:
    db = repo / ".factory" / "trace.db"
    if not db.is_file():
        return
    try:
        conn = sqlite3.connect(str(db))
        try:
            rows = conn.execute("SELECT pid FROM task_runs WHERE state = 'running'").fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return
    for (pid,) in rows:
        if isinstance(pid, int) and pid > 0 and pid != os.getpid():
            with contextlib.suppress(ProcessLookupError, PermissionError):
                oscompat.kill(pid, force=True)


def api_get(url: str, path: str) -> dict[str, Any]:
    """``data`` of a successful envelope of ``url + path``; AssertionError otherwise.

    Plain urllib, not Playwright: these requests go only to the test's server and are not
    counted as aborted browser requests.
    """
    try:
        with urllib.request.urlopen(f"{url}{path}", timeout=API_TIMEOUT_S) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"GET {path}: HTTP {exc.code}: {body}") from exc
    envelope = json.loads(raw)
    if not isinstance(envelope, dict) or envelope.get("ok") is not True:
        raise AssertionError(f"GET {path}: {raw}")
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise AssertionError(f"GET {path}: no data: {raw}")
    return data


def task_runs(api: str, task_id: str) -> list[dict[str, Any]]:
    """Runs of one task, newest first (``GET <api>/runs?task=``; ``api`` is ``ObsServer.api``)."""
    return list(api_get(api, f"/runs?task={urllib.parse.quote(task_id)}")["runs"])


def run_state(api: str, run_id: str) -> dict[str, Any]:
    """``run`` of ``GET <api>/runs/{id}``; the detail reaps a dead ``running`` row (``aborted``)."""
    run = api_get(api, f"/runs/{urllib.parse.quote(run_id)}")["run"]
    assert isinstance(run, dict), run
    return run


def wait_for(
    check: Callable[[], T | None],
    timeout_s: float,
    what: str,
    report: Callable[[], str],
    interval_s: float = 0.25,
) -> T:
    """Poll ``check`` until it returns a value other than None.

    An error of ``check`` (API not answering under load) does not end the wait; the last
    one is part of the failure message, together with ``report()``.
    """
    deadline = time.monotonic() + timeout_s
    last_error = ""
    while True:
        try:
            value = check()
        except (AssertionError, urllib.error.URLError, OSError, ValueError) as exc:
            last_error = f"last check error: {exc}\n"
        else:
            if value is not None:
                return value
        if time.monotonic() > deadline:
            raise AssertionError(f"{what}: not within {timeout_s:.0f} s\n{last_error}{report()}")
        time.sleep(interval_s)


def _run_line(run: dict[str, Any]) -> str:
    phases = ", ".join(f"{p.get('name')}={p.get('status')}" for p in run.get("phases") or [])
    pr = run.get("pr")
    return (
        f"{run.get('run_id')} task={run.get('task_id')} state={run.get('state')} "
        f"started={run.get('started_at')} ended={run.get('ended_at')} "
        f"pr={pr.get('pr_id') if isinstance(pr, dict) else None} "
        f"error={run.get('error')!r}\n    phases: {phases or '(none)'}"
    )


def runs_report(api: str, task_id: str | None) -> str:
    """The runs of ``task_id`` (all runs when None) as the API sees them; never raises."""
    head = f"--- runs from API ({task_id or 'all tasks'})"
    try:
        if task_id is None:
            runs = list(api_get(api, "/runs")["runs"])
        else:
            runs = task_runs(api, task_id)
        if not runs:
            return f"{head}\n(no runs)"
        lines = [_run_line(r) for r in runs]
        newest = run_state(api, str(runs[0]["run_id"]))
        lines.append(f"newest run now (detail): {_run_line(newest)}")
        return head + "\n" + "\n".join(lines)
    except Exception as exc:  # noqa: BLE001 - diagnostics must not hide the real failure
        return f"{head}\n(API unavailable: {exc})"
