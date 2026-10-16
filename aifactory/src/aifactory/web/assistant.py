"""The dashboard guide: read-only conversations about every registered repository.

A thread lives in ``$HAIFA_HOME/assistant/threads/<id>/``: ``thread.json`` (messages, the
harness, model and session), ``sessions/`` (the harness's own session state), ``work/`` (the
agent's working directory, outside every repository) and ``turns/NNN/`` (raw output and
the write guard's backups of one answer).

The harness and model come from the computer's harness settings (``harness_settings``, as
for the task advisor), else from the library agent ``guide``; a thread keeps the choice it
was created with, so every message continues the same harness session (``claude --resume``,
``codex exec resume``, pi ``--session-id``) like a retried run.

The agent may run one command only, ``./guide`` in ``work/`` (``assistant_gate.py``): the
allowlisted read-only ``factory`` commands with ``--json`` and read-only SQL on the trace
DBs. claude runs with ``--permission-mode dontAsk`` and allow rules for that command, codex
in its read-only sandbox (``AgentRequest.allowed_commands``). Whatever the harness, every
registered repository's main checkout is guarded like a task run's main checkout
(``run.guard.TaskWriteGuard`` with ``writes: []``): a write is undone and the answer fails.

The first message of a session carries the context: ``factory --skill``, the guide chapters
and the registered repositories. Every message may carry the screen the user is looking at
(``screen: {repo, task, run}``). Values of ``.env`` files and secret-looking environment
variables are redacted from everything sent to the agent (``assistant_gate.redact``).
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from aifactory import guide as guide_chapters
from aifactory.harness import canonical
from aifactory.harness import load as load_harness
from aifactory.harness import settings as harness_settings
from aifactory.web import assistant_gate as gate
from aifactory.web.workflow_advice import Cancellation

GUIDE_AGENT = "guide"
GUIDE_COMMAND = "./guide"
THREAD_ID = re.compile(r"^[a-f0-9]{12}$")
SCREEN_KEYS = ("repo", "task", "run")
MAX_TEXT = 20_000
MAX_SCREEN = 200
MAX_TURNS = 2

ReposSource = Callable[[], list[tuple[str, Path]]]


class AssistantError(Exception):
    """A guide request that cannot be served: ``code`` and an HTTP ``status``."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class Thread:
    id: str
    harness: str
    model: str
    thinking: str
    session_id: str
    created_at: str
    updated_at: str
    title: str = ""
    context_sent: bool = False
    messages: list[dict[str, Any]] = field(default_factory=list)
    # in memory: the events of the current answer, for the stream
    busy: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)
    seq: int = 0

    def stored(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "harness": self.harness,
            "model": self.model,
            "thinking": self.thinking,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "context_sent": self.context_sent,
            "messages": self.messages,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "harness": self.harness,
            "model": self.model,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": len(self.messages),
            "busy": self.busy,
        }

    def detail(self) -> dict[str, Any]:
        return {**self.summary(), "messages": list(self.messages), "seq": self.seq}


# ── prompt and context ───────────────────────────────────────────────────────────────────


def guide_system_template(home: Path) -> str:
    """``system.md`` of the library agent ``guide`` (the library HEAD, else the seed)."""
    try:
        from aifactory.library.inherit import library_snapshot

        item = library_snapshot({"HAIFA_HOME": str(home)}).agents.get(GUIDE_AGENT)
        found = item.file("system.md") if item is not None else None
        if found is not None:
            return found.data.decode("utf-8")
    except Exception:  # noqa: BLE001 - a broken library falls back to the seed
        pass
    from aifactory.library.seed import SEED_DIR

    return (SEED_DIR / "agents" / GUIDE_AGENT / "system.md").read_text(encoding="utf-8")


def guide_defaults() -> dict[str, str]:
    """Harness, model and thinking of the seed agent ``guide``."""
    from aifactory.library.load import load_library_item
    from aifactory.library.seed import SEED_DIR

    item = load_library_item(SEED_DIR, "agent", GUIDE_AGENT)
    defaults = item.defaults
    return {
        "harness": (defaults.harness if defaults and defaults.harness else "claude"),
        "model": (defaults.model if defaults and defaults.model else ""),
        "thinking": (defaults.thinking if defaults and defaults.thinking else "medium"),
    }


def repos_text(repos: list[tuple[str, Path]]) -> str:
    if not repos:
        return "(no repository is registered)"
    return "\n".join(f"- `{repo_id}`: {path}" for repo_id, path in repos)


def system_prompt(home: Path, repos: list[tuple[str, Path]]) -> str:
    text = guide_system_template(home)
    for key, value in {
        "guide_command": GUIDE_COMMAND,
        "allowed_commands": gate.allowed_label(),
        "repos": repos_text(repos),
    }.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def context_text(repos: list[tuple[str, Path]]) -> str:
    """The reference sent with the first message of a session."""
    from aifactory.skill.render import render_skill

    parts = [
        "# Context",
        "## Registered repositories",
        repos_text(repos),
        "## The factory CLI (`factory --skill`)",
        render_skill(),
        "## The HAIFA guide",
    ]
    for chapter in guide_chapters.chapters():
        parts.append(f"### Chapter `{chapter.id}`\n\n{chapter.markdown}")
    return "\n\n".join(parts)


def screen_text(screen: dict[str, str], repos: list[tuple[str, Path]]) -> str:
    if not screen:
        return ""
    paths = dict(repos)
    lines = ["## Screen the user is looking at"]
    labels = {"repo": "repository", "task": "task", "run": "run"}
    for key in SCREEN_KEYS:
        value = screen.get(key)
        if not value:
            continue
        if key == "repo" and value in paths:
            lines.append(f"- {labels[key]}: `{value}` ({paths[value]})")
        else:
            lines.append(f"- {labels[key]}: `{value}`")
    return "\n".join(lines)


def user_prompt(
    text: str, screen: dict[str, str], repos: list[tuple[str, Path]], *, context: bool
) -> str:
    parts = [context_text(repos)] if context else []
    shown = screen_text(screen, repos)
    if shown:
        parts.append(shown)
    parts.append(f"## Message\n\n{text}")
    return "\n\n".join(parts)


def parse_message(body: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """``(text, screen)`` of a message request; ``AssistantError`` when it is malformed."""
    unknown = sorted(set(body) - {"text", "screen"})
    if unknown:
        raise AssistantError("usage_error", f"unknown keys: {', '.join(unknown)}")
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        raise AssistantError("usage_error", "text must be a non-empty string")
    if len(text) > MAX_TEXT:
        raise AssistantError("usage_error", f"text is longer than {MAX_TEXT} characters")
    raw = body.get("screen") or {}
    if not isinstance(raw, dict):
        raise AssistantError("usage_error", "screen must be an object")
    extra = sorted(set(raw) - set(SCREEN_KEYS))
    if extra:
        raise AssistantError("usage_error", f"unknown screen keys: {', '.join(extra)}")
    screen: dict[str, str] = {}
    for key in SCREEN_KEYS:
        value = raw.get(key)
        if value is None or value == "":
            continue
        if not isinstance(value, str) or len(value) > MAX_SCREEN or "\n" in value:
            raise AssistantError("usage_error", f"screen.{key} must be a short one-line string")
        screen[key] = value.strip()
    return text.strip(), screen


# ── the working directory and the write guard ────────────────────────────────────────────


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=HAIFA guide",
            "-c",
            "user.email=guide@haifa.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def prepare_workdir(work: Path, home: Path) -> None:
    """An empty git repository with only the ``guide`` script (the guard needs a commit)."""
    import sys

    script = work / "guide"
    if (work / ".git").is_dir() and script.is_file():
        return
    work.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "#!/bin/sh\n"
        f"HAIFA_HOME={_sh_quote(str(home))} exec {_sh_quote(sys.executable)} "
        '-m aifactory.web.assistant_gate "$@"\n',
        encoding="utf-8",
        newline="\n",
    )
    script.chmod(0o755)
    if not (work / ".git").is_dir():
        _git(work, "init", "-q")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "--allow-empty", "-m", "guide")


def main_ignored(root: Path) -> tuple[str, ...]:
    """What the guard skips in a repository: worktrees, run data and the trace DB."""
    from aifactory.config.settings import CONFIG_FILE, load_local, parse_project_settings

    worktrees = ".factory/worktrees"
    try:
        config = root / CONFIG_FILE
        text = config.read_text(encoding="utf-8") if config.is_file() else None
        settings = parse_project_settings(text, str(config), [])
        if settings is not None:
            worktrees = settings.worktrees_dir
    except OSError:
        pass
    ignored = [worktrees.strip("/").removeprefix("./") + "/", ".factory/data/"]
    try:
        db = load_local(root).trace_db_path(root)
        relative = db.resolve().relative_to(root.resolve()).as_posix()
        ignored += [relative + suffix for suffix in ("", "-wal", "-shm", "-journal")]
    except Exception:  # noqa: BLE001 - a remote or outside DB needs no entry
        ignored += [".factory/trace.db" + s for s in ("", "-wal", "-shm", "-journal")]
    return tuple(ignored)


class RepoGuard:
    """Every registered repository's main checkout must be unchanged after an answer."""

    def __init__(self, repos: list[tuple[str, Path]], work: Path, turn: Path, run_id: str):
        from aifactory.run.guard import TaskWriteGuard
        from aifactory.run.scope import TaskScope

        self.run = SimpleNamespace(
            session_dir=turn,
            repo_root=work,
            adw_id=run_id,
            current_agent=SimpleNamespace(name=GUIDE_AGENT),
            cfg=SimpleNamespace(
                defaults=SimpleNamespace(data_dir=".guide-data", protected_files=[])
            ),
        )
        self.agent = SimpleNamespace(name=GUIDE_AGENT, writes=[])
        self.guards = [
            TaskWriteGuard(path, work, TaskScope(run_id, (), ()), main_ignored(path))
            for _, path in repos
            if (path / ".git").exists()
        ]
        self.before: list[Any] = []

    def snapshot(self) -> None:
        self.before = [guard.snapshot(self.run) for guard in self.guards]

    def enforce(self) -> list[str]:
        """What the agent wrote (already undone); empty when nothing."""
        from aifactory.engine.permissions import PermissionBreach

        problems: list[str] = []
        for guard, before in zip(self.guards, self.before, strict=True):
            try:
                guard.enforce(self.run, None, self.agent, before)
            except PermissionBreach as breach:
                problems.append(str(breach))
        return problems


# ── the manager ──────────────────────────────────────────────────────────────────────────


def _text_of(event: dict[str, Any]) -> str:
    """Assistant text in one harness event (claude, codex), else empty."""
    if event.get("type") == "assistant":
        content = (event.get("message") or {}).get("content") or []
        return "".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    item = event.get("item")
    if event.get("type") == "item.completed" and isinstance(item, dict):
        if item.get("type") == "agent_message":
            return str(item.get("text") or "")
    return ""


class AssistantManager:
    """Threads of the guide and their answers, run on a small worker pool."""

    def __init__(self, home: Path, repos: ReposSource) -> None:
        self.home = home
        self.repos = repos
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.threads: dict[str, Thread] = {}
        self.pool = ThreadPoolExecutor(max_workers=MAX_TURNS, thread_name_prefix="assistant")
        self.cancelled = Cancellation()
        self.closed = False
        self._loaded = False

    @property
    def root(self) -> Path:
        return self.home / "assistant" / "threads"

    # persistence

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.root.is_dir():
            return
        for path in self.root.glob("*/thread.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                thread = Thread(**{k: data[k] for k in Thread.__dataclass_fields__ if k in data})
            except (OSError, ValueError, TypeError, KeyError):
                continue
            if THREAD_ID.match(thread.id) and thread.id == path.parent.name:
                self.threads[thread.id] = thread

    def _save(self, thread: Thread) -> None:
        folder = self.root / thread.id
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / "thread.json.tmp"
        temporary.write_text(
            json.dumps(thread.stored(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(folder / "thread.json")

    def _thread(self, thread_id: str) -> Thread:
        self._load()
        thread = self.threads.get(thread_id) if THREAD_ID.match(thread_id) else None
        if thread is None:
            raise AssistantError("unknown_thread", f"unknown thread {thread_id!r}", 404)
        return thread

    def _emit(self, thread: Thread, kind: str, data: dict[str, Any]) -> None:
        with self.lock:
            thread.seq += 1
            thread.events.append({"seq": thread.seq, "type": kind, "data": data})
            self.changed.notify_all()

    # API

    def summaries(self) -> list[dict[str, Any]]:
        with self.lock:
            self._load()
            items = sorted(self.threads.values(), key=lambda t: t.updated_at, reverse=True)
            return [t.summary() for t in items]

    def get(self, thread_id: str) -> dict[str, Any]:
        with self.lock:
            return self._thread(thread_id).detail()

    def create(self, body: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(body) - {"title"})
        if unknown:
            raise AssistantError("usage_error", f"unknown keys: {', '.join(unknown)}")
        title = body.get("title") or ""
        if not isinstance(title, str) or len(title) > 200:
            raise AssistantError("usage_error", "title must be a string of at most 200 characters")
        try:
            selection = harness_settings.effective_override({}, None)
        except ValueError as exc:
            raise AssistantError("harness_unavailable", str(exc), 409) from exc
        if not selection.get("harness"):
            selection = guide_defaults()
        harness = canonical(selection["harness"])
        thread_id = uuid.uuid4().hex[:12]
        now = _now()
        thread = Thread(
            id=thread_id,
            harness=harness,
            model=selection.get("model", ""),
            thinking=selection.get("thinking") or "medium",
            session_id=f"guide-{thread_id}",
            created_at=now,
            updated_at=now,
            title=title.strip(),
        )
        with self.lock:
            self._load()
            self.threads[thread_id] = thread
            self._save(thread)
            return thread.detail()

    def send(self, thread_id: str, body: dict[str, Any]) -> dict[str, Any]:
        text, screen = parse_message(body)
        with self.lock:
            thread = self._thread(thread_id)
            if self.closed:
                raise AssistantError("busy", "the dashboard is stopping", 409)
            if thread.busy:
                raise AssistantError("busy", "the guide is still answering in this thread", 409)
            if sum(t.busy for t in self.threads.values()) >= MAX_TURNS:
                raise AssistantError("busy", "the guide is busy; try again shortly", 409)
            message: dict[str, Any] = {
                "id": uuid.uuid4().hex[:12],
                "role": "user",
                "text": text,
                "screen": screen,
                "at": _now(),
            }
            thread.messages.append(message)
            thread.title = thread.title or text.splitlines()[0][:80]
            thread.updated_at = message["at"]
            thread.busy = True
            thread.events = []
            self._save(thread)
            self._emit(thread, "start", {"message_id": message["id"]})
            self.pool.submit(self._answer, thread, text, screen)
            return {"thread": thread.summary(), "message": message, "seq": thread.seq}

    def wait(self, thread_id: str, after: int, timeout: float) -> tuple[list[dict[str, Any]], bool]:
        """Events after ``after`` (waiting up to ``timeout`` for one) and whether it is busy."""
        deadline = time.monotonic() + timeout
        with self.lock:
            thread = self._thread(thread_id)
            while True:
                events = [e for e in thread.events if e["seq"] > after]
                left = deadline - time.monotonic()
                if events or not thread.busy or left <= 0 or self.closed:
                    return events, thread.busy
                self.changed.wait(left)

    def close(self) -> None:
        with self.lock:
            self.closed = True
            self.changed.notify_all()
        self.cancelled.set()
        self.pool.shutdown(wait=False, cancel_futures=True)

    # one answer

    def _answer(self, thread: Thread, text: str, screen: dict[str, str]) -> None:
        reply: dict[str, Any] = {"id": uuid.uuid4().hex[:12], "role": "assistant", "text": ""}
        try:
            reply.update(self._turn(thread, text, screen))
        except AssistantError as exc:
            reply["error"] = exc.message
        except Exception as exc:  # noqa: BLE001 - every failure is the answer's error
            reply["error"] = f"{type(exc).__name__}: {str(exc)[:800]}"
        reply["at"] = _now()
        with self.lock:
            thread.messages.append(reply)
            thread.updated_at = reply["at"]
            thread.busy = False
            self._save(thread)
            if "error" in reply:
                self._emit(thread, "error", {"message": reply})
            else:
                self._emit(thread, "done", {"message": reply})

    def _turn(self, thread: Thread, text: str, screen: dict[str, str]) -> dict[str, Any]:
        from aifactory.engine.agents import _missing_session
        from aifactory.engine.data_types import AgentRequest
        from aifactory.engine.utils import agent_environment

        try:
            harness_settings.ensure_enabled(thread.harness)
        except ValueError as exc:
            raise AssistantError("harness_unavailable", str(exc), 409) from exc
        repos = [(rid, path) for rid, path in self.repos() if path.is_dir()]
        folder = self.root / thread.id
        work = folder / "work"
        prepare_workdir(work, self.home)
        turn = folder / "turns" / f"{sum(m['role'] == 'user' for m in thread.messages):03d}"
        turn.mkdir(parents=True, exist_ok=True)
        hidden = gate.secrets([path for _, path in repos], self.home)
        system = gate.redact(system_prompt(self.home, repos), hidden)
        run_id = f"guide-{thread.id}"
        harness = load_harness(thread.harness)
        tracker = harness.ToolCallTracker()

        def on_event(event: dict[str, Any]) -> None:
            said = _text_of(event)
            if said:
                self._emit(thread, "text", {"text": gate.redact(said, hidden)})
            record = tracker.observe(event)
            if record is not None:
                self._emit(thread, "tool", {"label": gate.redact(str(record["label"]), hidden)})

        def request(session_id: str, context: bool) -> Any:
            prompt = user_prompt(text, screen, repos, context=context)
            return AgentRequest(
                prompt=gate.redact(prompt, hidden),
                system_prompt=system,
                model=thread.model,
                thinking=thread.thinking,
                session_id=session_id,
                session_dir=str((folder / "sessions").resolve()),
                raw_output_path=str((turn / "raw_output.jsonl").resolve()),
                tools=["bash"],
                allowed_commands=[GUIDE_COMMAND, f"{GUIDE_COMMAND} *"],
                cwd=str(work),
            )

        guard = RepoGuard(repos, work, turn, run_id)
        guard.snapshot()
        environment = {
            "HAIFA_RUN_ID": run_id,
            "HAIFA_HOME": str(self.home),
            "CLAUDE_SAFE_MODE": "1",
            "CODEX_SAFE_MODE": "1",
            "PI_SAFE_MODE": "1",
        }
        failure: BaseException | None = None
        result = None
        try:
            with agent_environment(environment):
                calls = {
                    "on_event": on_event,
                    "on_spawn": self.cancelled.register,
                    "on_exit": self.cancelled.unregister,
                }
                try:
                    result = harness.run(
                        request(thread.session_id, not thread.context_sent), **calls
                    )
                    if result.returncode != 0 and _missing_session(result.text):
                        raise RuntimeError(result.text)
                except RuntimeError as exc:
                    if not thread.context_sent or not _missing_session(str(exc)):
                        raise
                    # The harness lost the conversation: a new session with the context.
                    thread.session_id = f"guide-{thread.id}-{uuid.uuid4().hex[:6]}"
                    result = harness.run(request(thread.session_id, True), **calls)
        except BaseException as exc:  # noqa: BLE001 - the guard still runs
            failure = exc
        problems = guard.enforce()
        if problems:
            raise AssistantError(
                "writes_violation",
                "Průvodce se pokusil zapsat do repozitáře, změny byly vráceny:\n"
                + "\n".join(problems),
            )
        if failure is not None:
            raise failure
        assert result is not None
        if result.returncode != 0 and not result.text:
            raise AssistantError("agent_failed", f"agent exited {result.returncode}")
        thread.context_sent = True
        return {
            "text": gate.redact(result.text, hidden),
            "usage": {"tokens": result.tokens, "cost_usd": result.cost},
        }
