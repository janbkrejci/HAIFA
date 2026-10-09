"""Claude Code interface — the second coding agent, alongside Pi.

Runs `claude -p --output-format stream-json --verbose` and tails its JSONL
stdout line by line, forwarding each event to a callback WHILE the agent works
— the same streaming contract `agent_pi` provides, so the runner, tracer and
visualizer never learn which harness produced a phase.

Three differences from pi are structural, not cosmetic, and every one of them
is handled here so the rest of the factory stays harness-agnostic:

1. **Session ids must be UUIDs.** SSSF mints readable ids
   (`sssf-<adw>-<agent>-<rand>`); claude accepts `--session-id <uuid>` only. A
   uuid5 of the SSSF id is derived instead of a random one, so the SAME logical
   agent always maps to the same claude conversation and `--resume` rejoins the
   context window that `--session-id` created.

2. **Create and continue are different flags.** pi's `--session-id` creates or
   continues; claude creates with `--session-id` and continues with `--resume`,
   and passing `--session-id` twice fails. Which one applies is recorded in a
   state file next to the session, so a re-entered run (`--adw-id`) resumes
   rather than colliding.

3. **Usage is reported cumulatively per session, not per turn.** claude's
   `result` event carries the conversation's running totals, so a phase that
   sends three times (prompt, JSON retry, gate correction) would triple-count
   if those totals were summed. The same state file holds the previous
   cumulative reading and every run reports the DELTA — which is what a turn
   actually cost.

MCP servers are off by default (`--strict-mcp-config` with no `--mcp-config`).
This is a cost decision with measured numbers behind it: a machine with the
usual MCP roster loaded prices a trivial Opus turn at ~$0.79 because ~67k
tokens of tool definitions enter the prompt; the same turn without them is
~$0.02. Set `CLAUDE_MCP_CONFIG` to a config file when an agent genuinely needs
MCP tools.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from .data_types import AgentRequest, AgentResult
from .utils import now_iso, operator_env

CLAUDE_PATH = os.environ.get("CLAUDE_CODE_PATH", "claude")

# Claude Code has no unattended mode of its own: with --print it either asks
# the host to answer permission prompts or denies silently, and either way the
# phase stalls or half-runs. `bypassPermissions` is the setting that matches
# what pi already does — and it is safe HERE for the same reason pi's total
# freedom is: `adw_modules/permissions.py` snapshots the tree before the call
# and rolls back anything the agent wrote outside its `writes:` list.
PERMISSION_MODE = os.environ.get("CLAUDE_PERMISSION_MODE", "bypassPermissions")
MCP_CONFIG = os.environ.get("CLAUDE_MCP_CONFIG", "")

# A factory agent is defined by ITS system.md and ITS tool list, not by whatever
# the operator's own Claude Code happens to load. --safe-mode drops CLAUDE.md,
# hooks, plugins, skills and custom agents while leaving auth, model, tools and
# permissions untouched: measured here, an unisolated run fired the operator's
# SessionStart hooks and carried 116 slash commands into the prompt — a hook
# that tells Claude how to talk is a hook that can corrupt an envelope.
SAFE_MODE = os.environ.get("CLAUDE_SAFE_MODE", "1") not in ("0", "false", "no")

RESULT_SNIPPET_CHARS = 20_000   # tool output rides along whole; clip only guards pathological cases
ARG_VALUE_CHARS = 20_000        # args too — the UI scrolls, it must not be handed cut-off data
LABEL_CHARS = 80                # "Bash: <command>" shown as the event name

PRIMARY_ARGS = ("command", "path", "file_path", "pattern", "query", "url", "prompt")

# The config speaks pi's tool vocabulary so one roster can drive both harnesses.
# A name already in claude's CamelCase form passes through untouched, which is
# how an agent reaches a tool pi has no equivalent for (Task, WebSearch, Skill).
TOOL_MAP = {
    "read": "Read",
    "bash": "Bash",
    "edit": "Edit",
    "write": "Write",
    "grep": "Grep",
    "find": "Glob",
    "ls": "Glob",          # claude has no LS tool; Glob is the listing primitive
}

# pi's thinking levels map onto claude's --effort. claude has no "off": the
# floor is `low`, so disabling thinking is expressed as the cheapest setting
# rather than silently dropped.
EFFORT_MAP = {
    "off": "low", "minimal": "low", "low": "low",
    "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "max",
}

# Aliases claude resolves to the current model of that family.
MODEL_ALIASES = ("opus", "sonnet", "haiku", "fable", "default", "opusplan")

# Fallback ceilings, used only until the first turn reports the real one:
# claude's `modelUsage` carries the authoritative contextWindow per model, so
# this table exists for the pre-run trace row, not for the context bar.
CONTEXT_WINDOWS = {
    "claude-opus-5": 1_000_000,
    "claude-fable-5-1": 1_000_000,
    "claude-sonnet-5": 1_000_000,
    "claude-haiku-4-5-20251001": 200_000,
}
DEFAULT_CONTEXT_WINDOW = 200_000


def resolve_model(pattern: str) -> tuple[str, str]:
    """Resolve a config model pattern to an explicit ``(provider, model_id)``.

    Deliberately offline. pi resolves against a local catalog it can list;
    claude has no `--list-models`, and probing the API to validate a config
    would turn fail-fast validation into a network call. Accepted forms:
    ``opus``, ``claude-opus-5``, ``anthropic/claude-opus-5``.
    """
    candidate = pattern.split("/", 1)[1] if pattern.startswith("anthropic/") else pattern
    if "/" in candidate:
        raise ValueError(f"model {pattern!r} is not a Claude Code model — use an alias "
                         f"({', '.join(MODEL_ALIASES)}), a full id (claude-opus-5), or "
                         "anthropic/<id>")
    if candidate in MODEL_ALIASES or candidate.startswith("claude-"):
        return "anthropic", candidate
    raise ValueError(f"model {pattern!r} is not a Claude Code model — use an alias "
                     f"({', '.join(MODEL_ALIASES)}) or a claude-* id")


def context_window(provider: str, model_id: str) -> int:
    """The model's context ceiling, before the first turn reports the real one."""
    if model_id in CONTEXT_WINDOWS:
        return CONTEXT_WINDOWS[model_id]
    for known, window in CONTEXT_WINDOWS.items():
        if model_id in MODEL_ALIASES and known.startswith(f"claude-{model_id}"):
            return window
    return DEFAULT_CONTEXT_WINDOW


def session_uuid(session_id: str) -> str:
    """The claude conversation id for an SSSF session id — stable, not random.

    Derived, not stored-and-looked-up: a run that re-enters an existing
    `--adw-id` must land on the same conversation even if the state file was
    wiped, and uuid5 makes that a pure function of the name.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"sssf://claude-code/{session_id}"))


def _text_of(message: dict) -> str:
    """Join the text blocks of an anthropic message."""
    return "".join(block.get("text", "") for block in message.get("content", []) or []
                   if isinstance(block, dict) and block.get("type") == "text")


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _label(tool: str, args: dict) -> str:
    """One-line human name for a tool call: `Bash: ls -la src`."""
    value = next((args[key] for key in PRIMARY_ARGS
                  if isinstance(args.get(key), str) and args[key].strip()), "")
    if not value:
        value = next((v for v in args.values() if isinstance(v, str) and v.strip()), "")
    value = " ".join(str(value).split())
    return f"{tool}: {_clip(value, LABEL_CHARS)}" if value else tool


def _result_text(block: dict) -> str:
    """Tool results arrive as a string or as anthropic content blocks."""
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content
                       if isinstance(part, dict) and part.get("type") == "text")
    return ""


def _occupancy(usage: dict) -> int:
    """Tokens occupying the window after a turn.

    Everything the model was sent plus what it produced: fresh input, the
    cached prefix it read, the prefix it wrote to cache, and its own output.
    Cache reads count — a cached prompt is still prompt.
    """
    return int((usage.get("input_tokens") or 0)
               + (usage.get("cache_read_input_tokens") or 0)
               + (usage.get("cache_creation_input_tokens") or 0)
               + (usage.get("output_tokens") or 0))


class ToolCallTracker:
    """Folds claude's tool stream into ONE normalized record per completed call.

    claude announces a call as a `tool_use` block on an assistant message and
    reports it as a `tool_result` block on the following user message. Only the
    result knows whether it worked, so that is where a record is emitted — one
    trace event per real tool call, the moment it returns, in the exact shape
    `agent_pi.ToolCallTracker` emits.
    """

    def __init__(self) -> None:
        self._open: dict[str, dict] = {}

    def observe(self, event: dict) -> Optional[dict]:
        """Returns the record for a finished tool call, else None."""
        etype = event.get("type", "")
        message = event.get("message", {}) or {}
        if etype == "assistant":
            for block in message.get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    self._announce(block.get("id"), block.get("name"), block.get("input"))
            return None
        if etype != "user":
            return None

        for block in message.get("content", []) or []:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            call_id = str(block.get("tool_use_id") or "")
            opened = self._open.pop(call_id, {})
            tool = str(opened.get("tool") or "tool")
            args = opened.get("args") or {}
            record = {
                "tool": tool,
                "tool_call_id": call_id,
                "args": {key: _clip(value, ARG_VALUE_CHARS) if isinstance(value, str) else value
                         for key, value in args.items()},
                "ok": not block.get("is_error", False),
                "label": _label(tool, args),
            }
            result_text = _result_text(block)
            if result_text:
                record["result_snippet"] = _clip(result_text, RESULT_SNIPPET_CHARS)
            record["ended_at"] = now_iso()
            if opened.get("clock"):
                record["duration_ms"] = int((time.monotonic() - opened["clock"]) * 1000)
            if opened.get("started_at"):
                record["started_at"] = opened["started_at"]
            return record           # one result per user message in practice
        return None

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


class _SessionState:
    """What this interface has to remember between turns of one conversation.

    Two facts, both of which claude gives no way to ask for: whether the
    conversation exists yet (create vs resume), and the cumulative usage the
    last turn reported (so this turn can be charged its delta).
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            self.data = json.loads(path.read_text())
        except (OSError, ValueError):
            self.data = {}

    @property
    def started(self) -> bool:
        return bool(self.data.get("started"))

    def totals(self) -> dict:
        return self.data.get("totals") or {}

    def save(self, totals: dict) -> None:
        self.data.update({"started": True, "totals": totals, "updated_at": now_iso()})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2))


def _tools_for(tools: Optional[list[str]]) -> list[str]:
    """Translate the roster's tool list into claude's built-in tool names."""
    if not tools:
        return []
    named, seen = [], set()
    for tool in tools:
        mapped = TOOL_MAP.get(tool, tool)      # unknown names pass through as-is
        if mapped not in seen:
            seen.add(mapped)
            named.append(mapped)
    return named


def _delta(current: dict, previous: dict) -> dict:
    """This turn's usage: the session's running totals minus the last reading."""
    return {key: max(0, int(current.get(key) or 0) - int(previous.get(key) or 0))
            for key in ("inputTokens", "outputTokens", "cacheReadInputTokens",
                        "cacheCreationInputTokens", "thinkingTokens")}


def _model_totals(result_event: dict) -> tuple[dict, int]:
    """Fold claude's per-model usage map into one totals dict plus the window."""
    totals = {"inputTokens": 0, "outputTokens": 0, "cacheReadInputTokens": 0,
              "cacheCreationInputTokens": 0, "thinkingTokens": 0, "costUSD": 0.0}
    window = 0
    for model in (result_event.get("modelUsage") or {}).values():
        for key in totals:
            totals[key] += model.get(key) or 0
        window = max(window, int(model.get("contextWindow") or 0))
    totals["costUSD"] = float(result_event.get("total_cost_usd")
                              or totals["costUSD"] or 0.0)
    return totals, window


def run(request: AgentRequest, on_event: Optional[Callable[[dict], None]] = None,
        on_spawn: Optional[Callable[[int], None]] = None,
        on_exit: Optional[Callable[[int], None]] = None,
        on_wait: Optional[Callable[[int, int, str], None]] = None) -> AgentResult:
    """Run one non-interactive Claude Code turn.

    `on_spawn(pid)` and `on_exit(pid)` bracket the child process so the caller
    can record it as killable — a hung coding agent is otherwise a pid you have
    to hunt for in `ps` while the run sits there.

    `on_wait` is part of the interface both harnesses answer to and goes unused
    here: claude waits out its own rate limits inside the process it was given,
    so there is no pause for this layer to announce.
    """
    provider, model_id = resolve_model(request.model)
    conversation = session_uuid(request.session_id)
    state = _SessionState(Path(request.session_dir) / f"{conversation}.state.json")

    cmd = [
        CLAUDE_PATH, "-p", "--output-format", "stream-json", "--verbose",
        "--model", model_id,
        "--effort", EFFORT_MAP.get(request.thinking, "medium"),
        "--permission-mode", PERMISSION_MODE,
        "--permission-prompts", "none",   # nobody is at the keyboard; never wait for one
        "--system-prompt", request.system_prompt,
    ]
    # Create the conversation once, rejoin it every time after — the whole
    # reason a gate correction keeps the agent's context instead of restarting.
    cmd += ["--resume", conversation] if state.started else ["--session-id", conversation]
    tools = _tools_for(request.tools)
    if tools:
        cmd += ["--tools", ",".join(tools)]
    if MCP_CONFIG:
        # Asking for MCP servers is asking for customization, which is exactly
        # what safe mode removes — so the two are mutually exclusive by design.
        cmd += ["--mcp-config", MCP_CONFIG, "--strict-mcp-config"]
    else:
        cmd.append("--strict-mcp-config")     # no MCP roster in the prompt, by default
        if SAFE_MODE:
            cmd.append("--safe-mode")
    cmd.append(request.prompt)

    raw_path = Path(request.raw_output_path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    result = AgentResult(session_id=request.session_id,
                         context_window=context_window(provider, model_id))
    totals, window, turn_cost = {}, 0, 0.0
    # Only a conversation claude actually opened may be resumed: marking a
    # failed spawn as started would make every later turn `--resume` an id
    # that does not exist.
    created = False
    # stdin is DEVNULL for the same reason pi's is: the prompt travels in argv,
    # and an inherited stdin lets the child wait forever for input that is
    # never coming.
    process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, bufsize=1, cwd=request.cwd,
                               env=operator_env())
    if on_spawn:
        on_spawn(process.pid)
    with raw_path.open("a") as raw:
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
            etype = event.get("type")
            if etype == "system" and event.get("subtype") == "init":
                created = True
            elif etype == "assistant":
                message = event.get("message", {}) or {}
                text = _text_of(message)
                if text:
                    result.text = text       # last assistant message wins
                occupancy = _occupancy(message.get("usage", {}) or {})
                if occupancy:
                    result.context_tokens = occupancy
            elif etype == "result":
                totals, window = _model_totals(event)
                if event.get("is_error"):
                    result.text = result.text or str(event.get("result") or "")
                elif event.get("result"):
                    result.text = str(event.get("result"))
            if on_event:
                on_event(event)

    stderr = process.stderr.read() if process.stderr else ""
    result.returncode = process.wait()
    if on_exit:
        on_exit(process.pid)

    if totals:
        previous = state.totals()
        turn = _delta(totals, previous)
        turn_cost = max(0.0, float(totals.get("costUSD") or 0.0)
                        - float(previous.get("costUSD") or 0.0))
        state.save(totals)
        # Re-shaped into pi's usage vocabulary so UsageBreakdown.add_turn stays
        # the one place token accounting lives. claude prices a turn as a
        # single number, so only the total cost is claimed — inventing a
        # per-component split would make the trace look more precise than it is.
        spent = {"input": turn["inputTokens"], "output": turn["outputTokens"],
                 "cacheRead": turn["cacheReadInputTokens"],
                 "cacheWrite": turn["cacheCreationInputTokens"],
                 "reasoning": turn["thinkingTokens"],
                 "cost": {"total": turn_cost}}
        billed = sum(turn[key] for key in ("inputTokens", "outputTokens",
                                           "cacheReadInputTokens",
                                           "cacheCreationInputTokens"))
        result.tokens += billed
        result.usage.add_turn(spent, billed)
        result.cost += turn_cost
    elif created:
        state.save(state.totals())           # a turn that errored still opened the session
    if window:
        result.context_window = window       # what the model actually reported

    if result.returncode != 0 and not result.text:
        raise RuntimeError(f"claude exited {result.returncode}: {stderr.strip()[-800:]}")
    return result
