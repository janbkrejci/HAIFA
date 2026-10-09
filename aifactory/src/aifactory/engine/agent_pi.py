"""Pi coding agent interface — v1's only coding agent.

Runs `pi -p --mode json` and tails its JSONL stdout line by line, forwarding
each event to a callback WHILE the agent works (the streaming crack, solved
by construction). `--session-id` creates-or-continues, so running and
continuing an agent are the same call: same session id = same context window.

aifactory: pi runs as if started from the CLI in the repo. It reads the repo's
AGENTS.md and CLAUDE.md natively and gets `.agents/skills/` explicitly; an
unattended `-p` run would skip project skills without trust, so the factory
grants it with `--approve`. The operator's personal skills (`~/.pi/agent/skills`,
`~/.agents/skills`), discovered extensions and prompt templates are left out
(`--no-skills`, `--no-extensions`, `--no-prompt-templates`; explicit `-e` and
`--skill` still load). pi cannot drop the global context files in
`~/.pi/agent` (AGENTS.md, CLAUDE.md, APPEND_SYSTEM.md) without dropping the
repo's too; `factory check` reports them as `pi_not_isolated`. The agent's role
stays in `--system-prompt`. `PI_SAFE_MODE=1` restores full isolation.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

from .data_types import PiRequest, PiResult
from .utils import env_flag, now_iso, operator_env

PI_PATH = os.environ.get("PI_PATH", "pi")

# pi has no way to forbid a shell command: `disallowed_commands` is not passed
# on, and HAIFA reports that at `factory check` and when a run starts.
SUPPORTS_DISALLOWED_COMMANDS = False

# aifactory: where codex and pi find the repo's skills (a copy of .claude/skills).
REPO_SKILLS_DIR = (".agents", "skills")


def safe_mode() -> bool:
    """aifactory: PI_SAFE_MODE=1 asks for full isolation; read at call time."""
    return env_flag("PI_SAFE_MODE")


def isolation_args(cwd: str) -> list[str]:
    """aifactory: pi flags for repo-native loading, or full isolation under PI_SAFE_MODE=1."""
    if safe_mode():
        return ["--no-approve", "--no-context-files", "--no-skills",
                "--no-extensions", "--no-prompt-templates"]
    args = ["--approve",              # project trust: unattended -p would skip .agents/skills
            "--no-skills",            # drops ~/.pi/agent/skills and ~/.agents/skills ...
            "--no-extensions",        # ... personal/discovered extensions (explicit -e still load)
            "--no-prompt-templates"]
    skills = Path(cwd).joinpath(*REPO_SKILLS_DIR)
    if skills.is_dir():
        args += ["--skill", str(skills.resolve())]   # ... and loads the repo's skills explicitly
    return args


# Providers throttle, and free tiers throttle hard: a handful of requests a
# minute is enough to earn a 429 with no body. pi retries a few times of its
# own accord, in quick succession, and then reports the failure as an
# assistant turn with no text — which reaches the ADW as "never produced valid
# JSON", blaming the model for what the provider refused to run. pi's retries
# are fast because they are meant for a blip; these are slow because they are
# meant for a quota window.
TRANSIENT_MARKERS = ("429", "500", "502", "503", "504", "529",
                     "rate limit", "overloaded", "too many requests")
TRANSIENT_BACKOFF = (5, 20, 60)   # seconds; one entry per retry, in order
MODELS_JSON = os.environ.get("PI_MODELS_PATH",
                             str(Path.home() / ".pi" / "agent" / "models.json"))

RESULT_SNIPPET_CHARS = 20_000   # tool output rides along whole; clip only guards pathological cases
ARG_VALUE_CHARS = 20_000        # args too — the UI scrolls, it must not be handed cut-off data
LABEL_CHARS = 80                # "bash: <command>" shown as the event name

# The arg that identifies a call at a glance, in the order tools tend to use.
PRIMARY_ARGS = ("command", "path", "file_path", "pattern", "query", "url")


def _count(value: str) -> int:
    """Parse pi's compact model-list counts (`272K`, `1.0M`)."""
    suffixes = {"K": 1_000, "M": 1_000_000}
    suffix = value[-1:].upper()
    if suffix in suffixes:
        return int(float(value[:-1]) * suffixes[suffix])
    return int(value)


@lru_cache(maxsize=1)
def _pi_catalog() -> list[tuple[str, str, int]]:
    """Read pi's merged catalog, including built-in providers and custom models."""
    try:
        result = subprocess.run(
            [PI_PATH, "--list-models"], capture_output=True, text=True,
            timeout=30, env=operator_env(), check=False, encoding="utf-8",
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    rows = []
    for line in result.stdout.splitlines()[1:]:
        columns = line.split()
        if len(columns) < 3:
            continue
        try:
            rows.append((columns[0], columns[1], _count(columns[2])))
        except ValueError:
            continue
    return rows


def resolve_model(pattern: str) -> tuple[str, str]:
    """Resolve a model pattern to an explicit ``(provider, model_id)`` pair.

    Pi's catalog merges built-in models with ``~/.pi/agent/models.json``. Using
    that same merged view lets SSSF target direct providers such as
    ``openai/gpt-5.6-terra`` without re-registering built-in models locally.
    """
    catalog = [(provider, model_id) for provider, model_id, _ in _pi_catalog()]
    if "/" in pattern:
        provider, model_id = pattern.split("/", 1)
        if (provider, model_id) in catalog:
            return provider, model_id
    matches = [(provider, model_id) for provider, model_id in catalog
               if pattern == model_id or pattern in model_id]
    exact = [match for match in matches
             if match[1] == pattern or match[1].endswith("/" + pattern)]
    if len(exact) == 1:
        return exact[0]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"model pattern {pattern!r} not found in pi --list-models — "
                         "authenticate/register it or fix the config")
    raise ValueError(f"model pattern {pattern!r} is ambiguous: {matches}")


def _context_tokens(usage: dict) -> int:
    """Tokens occupying the window after a turn.

    Mirrors pi's own `calculateContextTokens` (coding-agent
    `core/compaction/compaction.ts`), which is what pi compacts against and
    shows in its footer: prefer the provider's `totalTokens`, else sum the
    parts. Cache reads count — cached prompt is still prompt.
    """
    total = usage.get("totalTokens") or 0
    if total:
        return int(total)
    return int(sum(usage.get(part) or 0
                   for part in ("input", "output", "cacheRead", "cacheWrite")))


def context_window(provider: str, model_id: str) -> int:
    """The model's context ceiling from pi's merged model catalog.

    `models.json` is the CUSTOM half of that catalog and does not have to
    exist: a pi that only uses built-in providers never writes one. Reading it
    unguarded turned a missing file into a crash at the first spawn, on a
    machine where the very next line — pi's own listed catalog — had the
    answer. Absent or unreadable, fall through to it.
    """
    try:
        registry = json.loads(Path(MODELS_JSON).read_text())
    except (OSError, ValueError):
        registry = {}
    for model in registry.get("providers", {}).get(provider, {}).get("models", []):
        if model.get("id") == model_id:
            return int(model.get("contextWindow") or 0)
    for listed_provider, listed_model, window in _pi_catalog():
        if listed_provider == provider and listed_model == model_id:
            return window
    return 0


def _text_of(container: dict) -> str:
    """Join the text blocks of anything pi shapes as {content: [...]} — a
    message or a tool result."""
    return "".join(part.get("text", "") for part in container.get("content", []) or []
                   if isinstance(part, dict) and part.get("type") == "text")


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _label(tool: str, args: dict) -> str:
    """One-line human name for a tool call: `bash: ls -la src`."""
    value = next((args[key] for key in PRIMARY_ARGS
                  if isinstance(args.get(key), str) and args[key].strip()), "")
    if not value:
        value = next((v for v in args.values() if isinstance(v, str) and v.strip()), "")
    value = " ".join(str(value).split())
    return f"{tool}: {_clip(value, LABEL_CHARS)}" if value else tool


class ToolCallTracker:
    """Folds pi's tool stream into ONE normalized record per completed call.

    pi announces a call as a `toolCall` content block, then emits
    tool_execution_start / _update / _end for it. Only the end carries the
    result, so that is where a record is emitted — one trace event per real
    tool call, the moment it returns, instead of three shapeless ones.

    The record carries the call's real span (`started_at`/`ended_at`), which the
    tracer writes to columns so the UI can lay tool calls on a time axis without
    parsing every payload.
    """

    def __init__(self) -> None:
        self._open: dict[str, dict] = {}

    def observe(self, event: dict) -> Optional[dict]:
        """Returns the record for a finished tool call, else None."""
        etype = event.get("type", "")
        if etype == "message_end":
            for block in event.get("message", {}).get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "toolCall":
                    self._announce(block.get("id"), block.get("name"),
                                   block.get("arguments"))
            return None
        if etype == "tool_execution_start":
            self._announce(event.get("toolCallId"), event.get("toolName"),
                           event.get("args"))
            return None
        if etype != "tool_execution_end":
            return None

        call_id = str(event.get("toolCallId") or "")
        opened = self._open.pop(call_id, {})
        tool = str(event.get("toolName") or opened.get("tool") or "tool")
        args = event.get("args") or opened.get("args") or {}
        record = {
            "tool": tool,
            "tool_call_id": call_id,
            "args": {key: _clip(value, ARG_VALUE_CHARS) if isinstance(value, str) else value
                     for key, value in args.items()},
            "ok": not event.get("isError", False),
            "label": _label(tool, args),
        }
        result_text = _text_of(event.get("result") or {})
        if result_text:
            record["result_snippet"] = _clip(result_text, RESULT_SNIPPET_CHARS)
        record["ended_at"] = now_iso()
        if opened.get("clock"):
            record["duration_ms"] = int((time.monotonic() - opened["clock"]) * 1000)
        if opened.get("started_at"):
            record["started_at"] = opened["started_at"]
        return record

    def _announce(self, call_id, tool, args) -> None:
        """First sighting starts the clock; a later sighting only fills gaps."""
        if not call_id:
            return
        known = self._open.get(str(call_id), {})
        self._open[str(call_id)] = {
            "tool": tool or known.get("tool", ""),
            "args": args or known.get("args", {}),
            "started_at": known.get("started_at") or now_iso(),   # wall clock, for the row
            "clock": known.get("clock") or time.monotonic(),      # monotonic, for duration
        }


def _is_transient(error: str) -> bool:
    """Did the PROVIDER refuse this turn, rather than the model failing it?"""
    lowered = (error or "").lower()
    return any(marker in lowered for marker in TRANSIENT_MARKERS)


def run(request: PiRequest, on_event: Optional[Callable[[dict], None]] = None,
        on_spawn: Optional[Callable[[int], None]] = None,
        on_exit: Optional[Callable[[int], None]] = None,
        on_wait: Optional[Callable[[int, int, str], None]] = None) -> PiResult:
    """Run one non-interactive pi turn, waiting out a throttling provider.

    Only a turn that produced NO text is retried, and only when the provider
    said something transient: a model that answered badly is the gate system's
    problem, not this one's, and re-sending it would cost a second answer to
    the same prompt.
    """
    for attempt, pause in enumerate(TRANSIENT_BACKOFF + (0,), start=1):
        result, error = _attempt(request, on_event, on_spawn, on_exit)
        if result.text or not _is_transient(error):
            return result
        if not pause:
            raise RuntimeError(
                f"pi could not reach the provider for {request.model} after "
                f"{attempt} attempts — last error: {error.strip()[:300]}")
        if on_wait:
            on_wait(attempt, pause, error)
        time.sleep(pause)
    raise AssertionError("unreachable")     # the loop always returns or raises


def _attempt(request: PiRequest, on_event: Optional[Callable[[dict], None]] = None,
             on_spawn: Optional[Callable[[int], None]] = None,
             on_exit: Optional[Callable[[int], None]] = None) -> tuple[PiResult, str]:
    """One spawn of pi: the result, plus the provider error it ended on (if any).

    `on_spawn(pid)` and `on_exit(pid)` bracket the child process so the caller
    can record it as killable — a hung coding agent is otherwise a pid you have
    to hunt for in `ps` while the run sits there.
    """
    provider, model_id = resolve_model(request.model)
    cmd = [
        PI_PATH, "-p", "--mode", "json",
        "--provider", provider, "--model", model_id,
        "--thinking", request.thinking,
        "--session-id", request.session_id,
        "--session-dir", request.session_dir,
        "--system-prompt", request.system_prompt,
        *isolation_args(request.cwd),     # aifactory: repo-native instructions and skills
    ]
    if request.tools:
        cmd += ["--tools", ",".join(request.tools)]
    for extension in request.extensions:
        cmd += ["-e", extension]
    cmd.append(request.prompt)

    raw_path = Path(request.raw_output_path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    result = PiResult(session_id=request.session_id,
                      context_window=context_window(provider, model_id))
    last_error = ""
    # stdin is DEVNULL, deliberately. The prompt travels in argv, so the child
    # never needs stdin — but inheriting the parent's means pi sees a non-TTY
    # and can sit forever waiting for piped input that will never arrive or
    # EOF. That failure is silent and total: no request goes out, no bytes come
    # back, and the ADW blocks on a read loop with nothing to read. Observed as
    # a run that sat idle at 0% CPU with an empty raw_output.jsonl.
    process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, bufsize=1, cwd=request.cwd,
                               env=operator_env(), encoding="utf-8")
    if on_spawn:
        on_spawn(process.pid)
    with raw_path.open("a", encoding="utf-8", newline="\n") as raw:
        assert process.stdout is not None
        for line in process.stdout:
            raw.write(line)
            raw.flush()                      # events land on disk as they happen
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "message_end":
                message = event.get("message", {})
                if message.get("role") == "assistant":
                    if message.get("stopReason") == "error":
                        last_error = str(message.get("errorMessage") or "")
                    text = _text_of(message)
                    if text:
                        result.text = text   # last assistant message wins
                    usage = message.get("usage", {}) or {}
                    turn = _context_tokens(usage)
                    result.tokens += turn
                    result.usage.add_turn(usage, turn)
                    # Occupancy is read off the last VALID assistant turn, the
                    # way pi does it — an aborted or errored turn reports usage
                    # you can't trust, so it must not overwrite a good reading.
                    if turn and message.get("stopReason") not in ("aborted", "error"):
                        result.context_tokens = turn
                    result.cost += (usage.get("cost", {}) or {}).get("total", 0.0) or 0.0
            if on_event:
                on_event(event)

    stderr = process.stderr.read() if process.stderr else ""
    result.returncode = process.wait()
    if on_exit:
        on_exit(process.pid)
    if result.returncode != 0 and not result.text and not _is_transient(last_error):
        raise RuntimeError(f"pi exited {result.returncode}: {stderr.strip()[-800:]}")
    return result, last_error or (stderr.strip() if result.returncode else "")
