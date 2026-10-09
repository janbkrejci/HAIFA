"""Codex interface: the third coding agent, alongside pi and Claude Code (D13).

Runs ``codex exec --json`` and tails its JSONL stdout line by line, forwarding
each event to a callback while the agent works. It has the same streaming
contract as ``aifactory.engine.agent_cc`` and ``aifactory.engine.agent_pi``, so the
runner, tracer and visualizer never learn which harness produced a phase.

How the Codex CLI (checked against codex-cli 0.160.0) is driven:

- **System prompt.** It is passed as ``-c developer_instructions=<TOML string>``.
  ``json.dumps`` of a string is also a valid TOML basic string. It is not passed
  as ``model_instructions_file``, which would replace Codex's built-in
  instructions, including how to use its own tools. ``-c`` lasts for one
  process only, so the instructions are sent on every turn.
- **Create and continue are different commands.** The first turn is
  ``codex exec``. A correction turn (invalid JSON, failed gates) goes to the
  same thread through ``codex exec resume <thread_id>``. The thread id arrives
  in the ``thread.started`` event and is written to a state file in
  ``session_dir`` as soon as it arrives, so only a thread Codex actually opened
  is ever resumed.
- **Working directory.** ``resume`` accepts neither ``-C`` nor ``-s``. The
  first turn gets ``-C <cwd>``, and both turns run with ``Popen(cwd=cwd)``. The
  sandbox is set through ``-c sandbox_mode=...``, which works for both.
- **Permissions.** The default is ``--dangerously-bypass-approvals-and-sandbox``,
  the counterpart of ``bypassPermissions`` in ``agent_cc``: nobody is there to
  answer an approval prompt. This adapter neither grants nor restricts writes.
  ``writes:`` is enforced by ``aifactory/engine/permissions.py`` from the git diff,
  independently of the harness.
- **Usage.** ``turn.completed.usage`` is treated as the thread's running total,
  so a resumed turn is charged its delta against the stored reading. If any
  component goes down (a fresh counter), the reading is taken as it came.
  Codex reports no cost, so cost stays 0.0 rather than being invented.
- ``request.tools`` is ignored: Codex has no tool allowlist.
  ``request.disallowed_commands`` is ignored too: ``codex exec`` has no flag to
  forbid a shell command (``SUPPORTS_DISALLOWED_COMMANDS``), which HAIFA reports
  at ``factory check`` and when a run starts.
  ``request.extensions`` is ignored: ``agents.validate`` refuses
  ``harness_engineering`` for every harness except pi.
- **Repo instructions.** Codex runs as if started from the CLI in the repo: it
  reads the repo's AGENTS.md and discovers ``.agents/skills/`` natively, while
  the agent's role stays in ``developer_instructions``. ``--ignore-user-config``
  keeps the operator's ``$CODEX_HOME/config.toml`` (MCP servers, profiles,
  hooks) out of every run; auth still comes from ``CODEX_HOME``. Codex has no
  switch for ``~/.codex/AGENTS.md``, ``AGENTS.override.md``, ``~/.codex/skills``
  or ``~/.agents/skills``; ``factory check`` reports them as
  ``codex_not_isolated``. ``CODEX_SAFE_MODE=1`` also drops the repo's AGENTS.md
  (``project_doc_max_bytes=0``) for full isolation.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aifactory.engine.data_types import AgentRequest, AgentResult
from aifactory.engine.utils import env_flag, now_iso, operator_env

Event = dict[str, Any]

CODEX_PATH = os.environ.get("CODEX_PATH", "codex")
# "" -> --dangerously-bypass-approvals-and-sandbox. Otherwise one of
# read-only | workspace-write | danger-full-access, passed as -c sandbox_mode.
CODEX_SANDBOX = os.environ.get("CODEX_SANDBOX", "")


def launch_command(command: list[str]) -> list[str]:
    """Use the native executable behind npm's Windows shim, without a cmd shell.

    CreateProcess does not resolve bare npm commands. Passing prompts through
    codex.cmd also reinterprets quotes and shell metacharacters. The official
    npm distribution supplies the native binary in the supported package layouts.
    CODEX_PATH may point directly to an executable for other installations.
    """
    if os.name != "nt":
        return command
    resolved = shutil.which(command[0])
    if not resolved:
        return command  # Popen reports the missing CLI through its normal error path.
    shim = Path(resolved)
    if shim.suffix.lower() not in (".cmd", ".bat", ".ps1"):
        return [resolved, *command[1:]]
    machine = os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get(
        "PROCESSOR_ARCHITECTURE", ""
    )
    architecture = "arm64" if machine.lower() == "arm64" else "x64"
    target = "aarch64" if architecture == "arm64" else "x86_64"
    relative = Path("vendor") / f"{target}-pc-windows-msvc" / "bin" / "codex.exe"
    packages = shim.parent / "node_modules" / "@openai"
    for package in (
        packages / "codex" / "node_modules" / "@openai" / f"codex-win32-{architecture}",
        packages / f"codex-win32-{architecture}",
        packages / "codex",
    ):
        executable = package / relative
        if executable.is_file():
            return [str(executable), *command[1:]]
    raise OSError(
        "Codex npm native executable missing; reinstall Codex or set CODEX_PATH to codex.exe"
    )


def safe_mode() -> bool:
    """CODEX_SAFE_MODE=1: full isolation, the repo's AGENTS.md is not read either.

    Read at call time; the default is repo-native loading.
    """
    return env_flag("CODEX_SAFE_MODE")


# No per-command deny list in `codex exec` (see the module docstring).
SUPPORTS_DISALLOWED_COMMANDS = False

RESULT_SNIPPET_CHARS = 20_000
ARG_VALUE_CHARS = 20_000
LABEL_CHARS = 80
PRIMARY_ARGS = ("command", "path", "file_path", "pattern", "query", "url", "prompt")

# pi's thinking levels mapped onto Codex's model_reasoning_effort.
EFFORT_MAP = {
    "off": "minimal",
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "max": "xhigh",
}

# Fallback ceilings for the pre-run trace row; Codex does not report occupancy.
CONTEXT_WINDOWS = {
    "gpt-6.1-sol": 1_050_000,
    "gpt-5.5": 272_000,
    "gpt-5.5-codex": 272_000,
    "gpt-5": 272_000,
    "gpt-5-codex": 272_000,
}
DEFAULT_CONTEXT_WINDOW = 272_000

_CLAUDE_ALIASES = ("opus", "sonnet", "haiku", "fable", "opusplan")
_USAGE_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")


def resolve_model(pattern: str) -> tuple[str, str]:
    """Resolve a config model to ``("openai", model_id)``, offline.

    Accepted forms: ``gpt-5.5`` and ``openai/gpt-5.5``. This only checks that the
    model makes sense for Codex; the harness is never derived from it.
    """
    if not pattern.strip():
        raise ValueError("model is empty, Codex needs a model id such as gpt-5.5")
    candidate = pattern.split("/", 1)[1] if pattern.startswith("openai/") else pattern
    if (
        not candidate
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", candidate) is None
        or "/" in candidate
        or candidate.startswith("claude-")
        or candidate in _CLAUDE_ALIASES
    ):
        raise ValueError(
            f"model {pattern!r} is not a Codex model, use an OpenAI model id "
            "(gpt-5.5) or openai/<id>"
        )
    return "openai", candidate


def context_window(provider: str, model_id: str) -> int:
    """The model's context ceiling (fallback table; Codex reports none)."""
    return CONTEXT_WINDOWS.get(model_id, DEFAULT_CONTEXT_WINDOW)


def reasoning_effort(model: str, thinking: str) -> str:
    """Preserve legacy effort mapping; GPT-6.1-Sol supports low through max."""
    _, model_id = resolve_model(model)
    from aifactory.harness.thinking import codex_levels

    if thinking in codex_levels(model):
        return "none" if thinking == "off" else thinking
    if thinking not in EFFORT_MAP:
        raise ValueError(f"unknown Codex thinking level {thinking!r}")
    if model_id == "gpt-6.1-sol":
        if thinking in ("off", "minimal"):
            raise ValueError("gpt-6.1-sol supports low, medium, high, xhigh and max")
        return thinking
    return EFFORT_MAP[thinking]


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _label(tool: str, args: dict[str, Any]) -> str:
    """One-line human name for a tool call: ``bash: ls -la src``."""
    value: Any = next(
        (args[key] for key in PRIMARY_ARGS if isinstance(args.get(key), str) and args[key].strip()),
        "",
    )
    if not value:
        value = next((v for v in args.values() if isinstance(v, str) and v.strip()), "")
    value = " ".join(str(value).split())
    return f"{tool}: {_clip(value, LABEL_CHARS)}" if value else tool


def _mcp_text(item: Event) -> str:
    result = item.get("result")
    if isinstance(result, dict):
        parts = [
            str(part.get("text", ""))
            for part in result.get("content") or []
            if isinstance(part, dict) and part.get("text")
        ]
        if parts:
            return "".join(parts)
    error = item.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or "")
    return ""


def _describe(item: Event) -> tuple[str, dict[str, Any], bool, str] | None:
    """``(tool, args, ok, result_text)`` for a tool item, None for anything else."""
    itype = item.get("type")
    status = item.get("status")
    if itype == "command_execution":
        ok = status == "completed" and item.get("exit_code") in (0, None)
        return (
            "bash",
            {"command": item.get("command", "")},
            ok,
            str(item.get("aggregated_output") or ""),
        )
    if itype == "file_change":
        changes = item.get("changes") or []
        paths = [c for c in changes if isinstance(c, dict)]
        args: dict[str, Any] = {
            "path": paths[0].get("path", "") if paths else "",
            "changes": changes,
        }
        text = "\n".join(f"{c.get('kind', '')} {c.get('path', '')}" for c in paths)
        return "edit", args, status == "completed", text
    if itype == "mcp_tool_call":
        tool = f"{item.get('server', '')}.{item.get('tool', '')}"
        raw_args = item.get("arguments")
        mcp_args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
        ok = status == "completed" and not item.get("error")
        return tool, mcp_args, ok, _mcp_text(item)
    if itype == "web_search":
        return "web_search", {"query": item.get("query", "")}, True, ""
    return None


class ToolCallTracker:
    """Folds Codex's item stream into ONE normalized record per completed tool call.

    Codex announces a tool item with ``item.started`` and reports it with
    ``item.completed``. The record has the exact shape ``agent_cc`` and
    ``agent_pi`` emit, with tool names in pi's lowercase vocabulary.
    """

    def __init__(self) -> None:
        self._open: dict[str, dict[str, Any]] = {}

    def observe(self, event: Event) -> dict[str, Any] | None:
        """Returns the record for a finished tool call, else None."""
        etype = event.get("type", "")
        item = event.get("item")
        if not isinstance(item, dict):
            return None
        described = _describe(item)
        if described is None:
            return None
        tool, args, ok, result_text = described
        call_id = str(item.get("id") or "")
        if etype in ("item.started", "item.updated"):
            self._announce(call_id, tool, args)
            return None
        if etype != "item.completed":
            return None
        opened = self._open.pop(call_id, {})
        record: dict[str, Any] = {
            "tool": tool,
            "tool_call_id": call_id,
            "args": {
                key: _clip(value, ARG_VALUE_CHARS) if isinstance(value, str) else value
                for key, value in args.items()
            },
            "ok": ok,
            "label": _label(tool, args),
        }
        if result_text:
            record["result_snippet"] = _clip(result_text, RESULT_SNIPPET_CHARS)
        record["ended_at"] = now_iso()
        if opened.get("clock"):
            record["duration_ms"] = int((time.monotonic() - opened["clock"]) * 1000)
        if opened.get("started_at"):
            record["started_at"] = opened["started_at"]
        return record

    def _announce(self, call_id: str, tool: str, args: dict[str, Any]) -> None:
        """First sighting starts the clock; a later sighting only fills gaps."""
        if not call_id:
            return
        known = self._open.get(call_id, {})
        self._open[call_id] = {
            "tool": tool or known.get("tool", ""),
            "args": args or known.get("args", {}),
            "started_at": known.get("started_at") or now_iso(),
            "clock": known.get("clock") or time.monotonic(),
        }


class _SessionState:
    """The Codex thread id of this session and the last cumulative usage reading."""

    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            data = {}
        self.data: dict[str, Any] = data if isinstance(data, dict) else {}

    @property
    def thread_id(self) -> str:
        return str(self.data.get("thread_id") or "")

    def totals(self) -> dict[str, int]:
        totals = self.data.get("totals")
        return dict(totals) if isinstance(totals, dict) else {}

    def save(self, *, thread_id: str | None = None, totals: dict[str, int] | None = None) -> None:
        if thread_id:
            self.data["thread_id"] = thread_id
        if totals is not None:
            self.data["totals"] = totals
        self.data["updated_at"] = now_iso()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8", newline="\n")


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name) or "session"


def state_path(request: AgentRequest) -> Path:
    """Where the Codex state of ``request.session_id`` is kept."""
    return Path(request.session_dir) / f"{_safe(request.session_id)}.codex.json"


def _sandbox_args() -> list[str]:
    if not CODEX_SANDBOX:
        return ["--dangerously-bypass-approvals-and-sandbox"]
    return [
        "-c",
        f"sandbox_mode={json.dumps(CODEX_SANDBOX)}",
        "-c",
        'approval_policy="never"',
    ]


def build_command(request: AgentRequest, thread_id: str = "") -> list[str]:
    """argv for one turn: ``codex exec`` or, with a thread id, ``codex exec resume``."""
    _, model_id = resolve_model(request.model)
    effort = reasoning_effort(request.model, request.thinking)
    common = [
        "--json",
        "-m",
        model_id,
        "-c",
        f"model_reasoning_effort={json.dumps(effort)}",
        "-c",
        f"developer_instructions={json.dumps(request.system_prompt)}",
        "--skip-git-repo-check",
        "--ignore-user-config",  # never the operator's config.toml, in either mode
        *_sandbox_args(),
    ]
    if safe_mode():
        common += ["-c", "project_doc_max_bytes=0"]
    if thread_id:
        return [CODEX_PATH, "exec", "resume", *common, "--", thread_id, request.prompt]
    return [CODEX_PATH, "exec", *common, "-C", str(request.cwd), "--", request.prompt]


def _turn_usage(current: dict[str, int], previous: dict[str, int]) -> dict[str, int]:
    """This turn's usage: delta against the last reading, unless a counter went down."""
    if previous and all(current[key] >= int(previous.get(key) or 0) for key in _USAGE_KEYS):
        return {key: current[key] - int(previous.get(key) or 0) for key in _USAGE_KEYS}
    return dict(current)


def run(
    request: AgentRequest,
    on_event: Callable[[Event], None] | None = None,
    on_spawn: Callable[[int], None] | None = None,
    on_exit: Callable[[int], None] | None = None,
    on_wait: Callable[[int, int, str], None] | None = None,
) -> AgentResult:
    """Run one non-interactive Codex turn and return an ``AgentResult``.

    ``on_spawn(pid)`` and ``on_exit(pid)`` bracket the child process. ``on_wait``
    is part of the shared interface and goes unused: Codex waits out its own
    rate limits inside the process.
    """
    provider, model_id = resolve_model(request.model)
    state = _SessionState(state_path(request))
    cmd = build_command(request, state.thread_id)

    raw_path = Path(request.raw_output_path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    result = AgentResult(
        session_id=request.session_id, context_window=context_window(provider, model_id)
    )
    usage: dict[str, int] = {}
    last_error = ""
    # stdin is DEVNULL: the prompt travels in argv, and an inherited stdin lets
    # the child wait for input that is never coming.
    process = subprocess.Popen(
        launch_command(cmd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=request.cwd,
        env=operator_env(),
        encoding="utf-8",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    if on_spawn:
        on_spawn(process.pid)
    with raw_path.open("a", encoding="utf-8", newline="\n") as raw:
        assert process.stdout is not None
        for line in process.stdout:
            raw.write(line)
            raw.flush()
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            etype = event.get("type")
            if etype == "thread.started" and event.get("thread_id"):
                state.save(thread_id=str(event["thread_id"]))
            elif etype == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message" and item.get("text"):
                    result.text = str(item["text"])  # last agent message wins
            elif etype == "turn.completed":
                raw_usage = event.get("usage") or {}
                usage = {key: int(raw_usage.get(key) or 0) for key in _USAGE_KEYS}
            elif etype == "turn.failed":
                last_error = str((event.get("error") or {}).get("message") or "")
            elif etype == "error":
                last_error = str(event.get("message") or "")
            if on_event:
                on_event(event)

    stderr = process.stderr.read() if process.stderr else ""
    result.returncode = process.wait()
    if on_exit:
        on_exit(process.pid)

    if usage:
        turn = _turn_usage(usage, state.totals())
        state.save(totals=usage)
        spent = {
            "input": max(0, turn["input_tokens"] - turn["cached_input_tokens"]),
            "output": turn["output_tokens"],
            "cacheRead": turn["cached_input_tokens"],
            "cacheWrite": 0,
            "reasoning": turn["reasoning_output_tokens"],
            "cost": {"total": 0.0},
        }
        billed = turn["input_tokens"] + turn["output_tokens"]
        result.tokens += billed
        result.usage.add_turn(spent, billed)

    if result.returncode != 0 and not result.text:
        detail = (last_error or stderr).strip()[-800:]
        raise RuntimeError(f"codex exited {result.returncode}: {detail}")
    return result
