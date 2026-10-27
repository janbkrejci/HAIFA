"""The dashboard guide: read-only conversations about every registered repository.

A thread lives in ``$HAIFA_HOME/assistant/threads/<id>/``: ``thread.json`` (messages, the
harness, model, thinking and session), ``sessions/`` (the harness's own session state),
``work/`` (the agent's working directory, outside every repository) and ``turns/NNN/``
(raw output and the write guard's backups of one answer).

The harness, model and thinking use the task's inherited T69 context binding when created
with ``screen.task`` (or the current task of ``screen.run``) in a registered repository.
Repo-only and absent context use the computer's harness settings; an unresolved binding
uses the library agent ``guide`` defaults. The choice then obeys the guide harness limit
below. A thread keeps the choice it was created with, so every message continues the same
harness session (``claude --resume``, ``codex exec resume``, pi ``--session-id``) like a
retried run.

The agent may run one command only, ``./guide`` in ``work/`` (``assistant_gate.py``): the
allowlisted read-only ``factory`` commands with ``--json`` and read-only SQL on the trace
DBs. claude runs with ``--permission-mode dontAsk`` and allow rules for that command
(``AgentRequest.allowed_commands``). codex (its read-only sandbox still reads any file, e.g. a
repository's ``.env``) and pi (no command limit at all) cannot enforce that limit, so the guide
runs on claude only: a codex or pi selection falls back to claude, and without an enabled
claude (or for a thread created on codex or pi) the guide refuses with ``harness_unavailable``.
Threads created in a repository are restricted to that repository; threads created on the
dashboard can read all registered repositories. Checkout changes during an answer are
reported without rolling them back: they may belong to a concurrent editor or factory run.

The first message of a session carries the context: ``factory --skill``, the guide chapters
and the registered repositories. Every message may carry the screen the user is looking at
(``screen: {repo, task, run}``). Values of ``.env`` files and secret-looking environment
variables are redacted from everything sent to the agent (``assistant_gate.redact``).

Instead of a change the guide may propose one: a fenced ``haifa-action`` block with a JSON
object of one of ``ACTION_FIELDS`` (create or edit a task, run a task, retry a run, approve a
PR, cancel a task, follow up a done task). The answer keeps the validated proposals in
``actions`` (``status: proposed``) and drops the blocks from its text. The guide never
executes a proposal: the panel shows it as a card and, when the user confirms it, calls the
dashboard's own write API (the same endpoints and guards as the manual action), then
reports the outcome with ``record_action``. The outcome is a message of the thread
(``role: action``) and goes to the agent with the next message.

``delete`` removes a thread for good: from memory and its whole folder on disk. A thread the
guide is answering in is refused (``busy``) so the running answer cannot write it back.
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
from aifactory.workflow.adaptive import remove_tree

GUIDE_AGENT = "guide"
GUIDE_COMMAND = "./guide"
THREAD_ID = re.compile(r"^[a-f0-9]{12}$")
SCREEN_KEYS = ("repo", "task", "run")
MAX_TEXT = 20_000
MAX_SCREEN = 200
MAX_TURNS = 2
MAX_ACTIONS = 5
ACTION_FENCE = re.compile(r"^```haifa-action[ \t]*\r?\n(.*?)^```[ \t]*$", re.S | re.M)
ACTION_STATES = ("done", "failed", "dismissed")
# The fields of each proposal kind: name -> (type, required). ``repo`` is always required.
ACTION_FIELDS: dict[str, dict[str, tuple[type, bool]]] = {
    "create_task": {
        "step": (str, True),
        "title": (str, True),
        "body": (str, False),
        "writes": (list, False),
        "workflow": (str, False),
        "depends_on": (list, False),
    },
    "edit_task": {
        "task": (str, True),
        "title": (str, False),
        "body": (str, False),
        "writes": (list, False),
        "workflow": (str, False),
    },
    "run_task": {"task": (str, True), "note": (str, False)},
    "retry_run": {"run": (str, True), "note": (str, False)},
    "approve_pr": {"task": (str, True)},
    "cancel_task": {"task": (str, True)},
    "follow_up": {
        "task": (str, True),
        "body": (str, True),
        "title": (str, False),
        "run": (bool, False),
    },
}
ACTION_LONG = ("body", "note")
# Harnesses that enforce the ``./guide`` command limit (claude's dontAsk allow rules).
GUIDE_HARNESSES = ("claude",)

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
    repo_id: str | None = None
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
            "repo_id": self.repo_id,
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
            "repo_id": self.repo_id,
            "harness": self.harness,
            "model": self.model,
            "thinking": self.thinking,
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


def unlimited_message(harness: str) -> str:
    return (
        f"the guide cannot run on {harness}: it cannot limit the agent to the {GUIDE_COMMAND} "
        f"command (it could read .env files of the repositories); the guide needs claude"
    )


def claude_fallback(selected: str) -> dict[str, str]:
    """The claude selection replacing a harness without the guide's command limit."""
    try:
        selection = harness_settings.effective_override({}, {"harness": "claude"})
    except ValueError as exc:
        raise AssistantError(
            "harness_unavailable", f"{unlimited_message(selected)}: {exc}", 409
        ) from exc
    if not harness_settings.read():
        defaults = guide_defaults()
        if defaults["harness"] == "claude":
            return defaults
    return selection


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


def results_text(results: list[str]) -> str:
    if not results:
        return ""
    lines = ["## Outcome of your proposed actions (the user decided)"]
    lines += [f"- {item}" for item in results]
    return "\n".join(lines)


def user_prompt(
    text: str,
    screen: dict[str, str],
    repos: list[tuple[str, Path]],
    *,
    context: bool,
    results: list[str] | None = None,
) -> str:
    parts = [context_text(repos)] if context else []
    shown = screen_text(screen, repos)
    if shown:
        parts.append(shown)
    outcome = results_text(results or [])
    if outcome:
        parts.append(outcome)
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
    return text.strip(), parse_screen(body.get("screen"))


def parse_screen(raw: Any) -> dict[str, str]:
    """Validate the shared screen shape; existence is checked only at thread creation."""
    if raw is None:
        return {}
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
        if value.strip():
            screen[key] = value.strip()
    return screen


# ── proposed actions ─────────────────────────────────────────────────────────────────────


def _action(raw: Any, repo_ids: set[str]) -> dict[str, Any]:
    """One validated proposal; ``ValueError`` with the reason when it is not valid."""
    if not isinstance(raw, dict):
        raise ValueError("the block is not a JSON object")
    kind = raw.get("kind")
    if kind not in ACTION_FIELDS:
        raise ValueError(f"unknown kind {kind!r}")
    fields = ACTION_FIELDS[kind]
    unknown = sorted(set(raw) - set(fields) - {"kind", "repo", "reason"})
    if unknown:
        raise ValueError(f"{kind}: unknown fields {', '.join(unknown)}")
    repo = raw.get("repo")
    if not isinstance(repo, str) or repo not in repo_ids:
        raise ValueError(f"{kind}: repo {repo!r} is not a registered repository id")
    action: dict[str, Any] = {"id": uuid.uuid4().hex[:12], "kind": kind, "repo": repo}
    for name, (expected, required) in fields.items():
        value = raw.get(name)
        if value is None:
            if required:
                raise ValueError(f"{kind}: {name} is required")
            continue
        if expected is bool:
            if not isinstance(value, bool):
                raise ValueError(f"{kind}: {name} must be true or false")
            action[name] = value
            continue
        if expected is list:
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item.strip() and len(item) <= MAX_SCREEN for item in value
            ):
                raise ValueError(f"{kind}: {name} must be a list of strings")
            action[name] = [item.strip() for item in value]
            continue
        limit = MAX_TEXT if name in ACTION_LONG else MAX_SCREEN
        one_line = name not in ACTION_LONG
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > limit
            or (one_line and "\n" in value)
        ):
            raise ValueError(f"{kind}: {name} must be a non-empty string")
        action[name] = value if name == "body" else value.strip()
    if kind == "edit_task" and not any(
        k in action for k in ("title", "body", "writes", "workflow")
    ):
        raise ValueError("edit_task: nothing to change (title, body, writes or workflow)")
    reason = raw.get("reason")
    if isinstance(reason, str) and reason.strip():
        action["reason"] = reason.strip()[: MAX_SCREEN * 5]
    action["status"] = "proposed"
    return action


def parse_actions(text: str, repo_ids: set[str]) -> tuple[str, list[dict[str, Any]]]:
    """The answer without its ``haifa-action`` blocks and the valid proposals in them.

    A block that is not a valid proposal is replaced by a note with the reason, so the user
    sees that the guide proposed something the dashboard cannot offer.
    """
    actions: list[dict[str, Any]] = []

    def replace(match: re.Match[str]) -> str:
        try:
            if len(actions) >= MAX_ACTIONS:
                raise ValueError(f"more than {MAX_ACTIONS} proposals in one answer")
            actions.append(_action(json.loads(match.group(1)), repo_ids))
            return ""
        except ValueError as exc:  # json.JSONDecodeError is a ValueError
            return f"> Návrh akce nejde nabídnout: {str(exc)[:300]}\n"

    cleaned = ACTION_FENCE.sub(replace, text)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip(), actions


def action_label(action: dict[str, Any]) -> str:
    """``edit_task P01-S01-T01 in alpha``: what a proposal does, for the agent."""
    target = action.get("task") or action.get("run") or action.get("title") or ""
    return f"{action['kind']} {target} in {action['repo']}".replace("  ", " ")


def parse_outcome(body: dict[str, Any]) -> tuple[str, str]:
    """``(status, message)`` of a reported outcome; ``AssistantError`` when malformed."""
    unknown = sorted(set(body) - {"status", "message"})
    if unknown:
        raise AssistantError("usage_error", f"unknown keys: {', '.join(unknown)}")
    status = body.get("status")
    if status not in ACTION_STATES:
        raise AssistantError("usage_error", f"status must be one of {', '.join(ACTION_STATES)}")
    message = body.get("message") or ""
    if not isinstance(message, str) or len(message) > MAX_TEXT:
        raise AssistantError("usage_error", "message must be a string")
    return status, message.strip()


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


def prepare_workdir(work: Path, home: Path, repo_id: str | None = None) -> None:
    """An empty git repository with only the ``guide`` script (the guard needs a commit)."""
    import sys

    script = work / "guide"
    content = (
        "#!/bin/sh\n"
        f"HAIFA_HOME={_sh_quote(str(home))} "
        f"HAIFA_GUIDE_REPO={_sh_quote(repo_id or '')} exec {_sh_quote(sys.executable)} "
        '-m aifactory.web.assistant_gate "$@"\n'
    )
    if (work / ".git").is_dir() and script.is_file():
        if script.read_text(encoding="utf-8") == content:
            return
    work.mkdir(parents=True, exist_ok=True)
    script.write_text(content, encoding="utf-8", newline="\n")
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
    """Observe checkout changes without overwriting concurrent work."""

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
        self.guards = [
            TaskWriteGuard(path, work, TaskScope(run_id, (), ()), main_ignored(path))
            for _, path in repos
            if (path / ".git").exists()
        ]
        self.before: list[Any] = []

    def snapshot(self) -> None:
        self.before = [guard.snapshot(self.run) for guard in self.guards]

    def enforce(self) -> list[str]:
        """Changed checkouts; a snapshot cannot identify which process wrote them."""
        from aifactory.run import backup

        problems: list[str] = []
        for guard, before in zip(self.guards, self.before, strict=True):
            paths = backup.verify(before["main_backup"], guard.main_ignored)
            if paths:
                problems.append(f"{guard.main_root}: {', '.join(paths)}")
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
                if "repo_id" not in data:
                    first = next((m for m in thread.messages if m.get("role") == "user"), {})
                    thread.repo_id = first.get("screen", {}).get("repo")
                    if thread.repo_id:
                        # Old sessions may contain context from other repositories.
                        thread.session_id = f"guide-{thread.id}-{uuid.uuid4().hex[:6]}"
                        thread.context_sent = False
                    self._save(thread)
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

    def _context_values(self, screen: dict[str, str]) -> dict[str, object]:
        """Resolve registered context read-only, using a run's current backlog task."""
        from aifactory import backlog
        from aifactory.backlog.derived import harness_values
        from aifactory.config import ConfigError
        from aifactory.web.overview import _trace_view
        from aifactory.web.repos import trace_db_of

        repo_id = screen.get("repo")
        task_id = screen.get("task")
        run_id = screen.get("run")
        if not repo_id:
            if task_id or run_id:
                raise AssistantError(
                    "usage_error", "screen.task and screen.run require screen.repo"
                )
            return {}
        repo = dict(self.repos()).get(repo_id)
        if repo is None:
            raise AssistantError("usage_error", f"unknown repository {repo_id!r}")
        if run_id:
            trace, errors = _trace_view(trace_db_of(repo))
            if errors:
                raise AssistantError("usage_error", "; ".join(errors))
            run = next((r for r in trace.runs if r["run_id"] == run_id), None) if trace else None
            if run is None:
                raise AssistantError("usage_error", f"unknown run {run_id!r}")
            if task_id and task_id != run["task_id"]:
                raise AssistantError("usage_error", "screen.task does not match screen.run")
            task_id = run["task_id"]
            if not task_id:
                raise AssistantError("usage_error", "screen.run has no task")
        if not task_id:
            return {}
        try:
            task = backlog.find_task(backlog.load_backlog(repo, create_missing=False), task_id)
        except (backlog.TaskEditError, ConfigError, OSError, ValueError) as exc:
            raise AssistantError("usage_error", str(exc)) from exc
        return harness_values(task)

    def create(self, body: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(body) - {"title", "screen"})
        if unknown:
            raise AssistantError("usage_error", f"unknown keys: {', '.join(unknown)}")
        title = body.get("title") or ""
        if not isinstance(title, str) or len(title) > 200:
            raise AssistantError("usage_error", "title must be a string of at most 200 characters")
        screen = parse_screen(body.get("screen"))
        values = self._context_values(screen)
        try:
            selection = harness_settings.context_binding(values)
        except ValueError as exc:
            raise AssistantError("harness_unavailable", str(exc), 409) from exc
        if not selection.get("harness"):
            selection = guide_defaults()
        if canonical(selection["harness"]) not in GUIDE_HARNESSES:
            selection = claude_fallback(selection["harness"])
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
            repo_id=screen.get("repo"),
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
            if thread.repo_id and screen.get("repo") not in (None, thread.repo_id):
                raise AssistantError(
                    "usage_error",
                    f"Toto vlákno je omezené na repozitář {thread.repo_id}. Založ nové vlákno.",
                )
            if self.closed:
                raise AssistantError("busy", "the dashboard is stopping", 409)
            if thread.busy:
                raise AssistantError("busy", "the guide is still answering in this thread", 409)
            if sum(t.busy for t in self.threads.values()) >= MAX_TURNS:
                raise AssistantError("busy", "the guide is busy; try again shortly", 409)
            results = self._unsent_results(thread)
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
            self.pool.submit(self._answer, thread, text, screen, results)
            return {"thread": thread.summary(), "message": message, "seq": thread.seq}

    def delete(self, thread_id: str) -> dict[str, Any]:
        """Remove the thread from memory and its folder from disk; refused while it answers."""
        with self.lock:
            thread = self._thread(thread_id)
            if thread.busy:
                raise AssistantError("busy", "the guide is still answering in this thread", 409)
            folder = self.root / thread.id
            if folder.exists():
                try:
                    remove_tree(folder)
                except OSError as exc:
                    raise AssistantError(
                        "delete_failed", f"cannot delete the thread: {exc}", 500
                    ) from exc
            from aifactory.harness.agent_dirs import remove_agent_dirs

            remove_agent_dirs(folder / "work")
            del self.threads[thread.id]
            self.changed.notify_all()
            return {"deleted": thread.id}

    def _unsent_results(self, thread: Thread) -> list[str]:
        """The action outcomes since the last user message (the agent has not seen them)."""
        results: list[str] = []
        for message in reversed(thread.messages):
            if message.get("role") == "user":
                break
            if message.get("role") == "action":
                results.append(str(message.get("text") or ""))
        return list(reversed(results))

    def record_action(self, thread_id: str, action_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """The outcome of a proposal the user executed (or dismissed) in the panel.

        Records only: the write itself went through the dashboard's own API. The outcome is
        a message of the thread and goes to the agent with the next message.
        """
        status, text = parse_outcome(body)
        with self.lock:
            thread = self._thread(thread_id)
            found = None
            for message in thread.messages:
                for action in message.get("actions") or []:
                    if action.get("id") == action_id:
                        found = action
            if found is None:
                raise AssistantError("unknown_action", f"unknown action {action_id!r}", 404)
            if found.get("status") != "proposed":
                raise AssistantError(
                    "action_decided", f"the action is already {found.get('status')}", 409
                )
            now = _now()
            found["status"] = status
            found["outcome"] = {"message": text, "at": now}
            verdict = {"done": "executed", "failed": "failed", "dismissed": "dismissed"}[status]
            note: dict[str, Any] = {
                "id": uuid.uuid4().hex[:12],
                "role": "action",
                "action_id": action_id,
                "kind": found["kind"],
                "status": status,
                "text": f"{action_label(found)}: {verdict}" + (f": {text}" if text else ""),
                "at": now,
            }
            thread.messages.append(note)
            thread.updated_at = now
            self._save(thread)
            return {"action": dict(found), "message": note}

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

    def _answer(
        self, thread: Thread, text: str, screen: dict[str, str], results: list[str]
    ) -> None:
        reply: dict[str, Any] = {"id": uuid.uuid4().hex[:12], "role": "assistant", "text": ""}
        try:
            reply.update(self._turn(thread, text, screen, results))
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

    def _turn(
        self, thread: Thread, text: str, screen: dict[str, str], results: list[str]
    ) -> dict[str, Any]:
        from aifactory.engine.agents import _missing_session
        from aifactory.engine.data_types import AgentRequest
        from aifactory.engine.utils import agent_environment

        if thread.harness not in GUIDE_HARNESSES:
            raise AssistantError("harness_unavailable", unlimited_message(thread.harness), 409)
        try:
            harness_settings.ensure_enabled(thread.harness)
        except ValueError as exc:
            raise AssistantError("harness_unavailable", str(exc), 409) from exc
        repos = [(rid, path) for rid, path in self.repos() if path.is_dir()]
        if thread.repo_id:
            repos = [(rid, path) for rid, path in repos if rid == thread.repo_id]
            if not repos:
                raise AssistantError("usage_error", f"unknown repository {thread.repo_id!r}")
        folder = self.root / thread.id
        work = folder / "work"
        prepare_workdir(work, self.home, thread.repo_id)
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
            prompt = user_prompt(text, screen, repos, context=context, results=results)
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
                "repositories_changed",
                "Během odpovědi se změnily repozitáře. Změny byly zachovány; "
                "nelze určit, který proces je provedl. Zopakuj dotaz:\n" + "\n".join(problems),
            )
        if failure is not None:
            raise failure
        assert result is not None
        if result.returncode != 0 and not result.text:
            raise AssistantError("agent_failed", f"agent exited {result.returncode}")
        thread.context_sent = True
        answer, actions = parse_actions(
            gate.redact(result.text, hidden), {repo_id for repo_id, _ in repos}
        )
        reply: dict[str, Any] = {
            "text": answer,
            "usage": {"tokens": result.tokens, "cost_usd": result.cost},
        }
        if actions:
            reply["actions"] = actions
        return reply
