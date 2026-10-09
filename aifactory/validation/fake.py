"""Scripted fake harness: no CLI is spawned, no model is called.

``install(script)`` registers the real adapters first (``harness.install``),
then replaces each adapter's ``run`` with a guard that raises and its
``resolve_model`` with the fake's, and finally puts a ``FakeHarness`` into
``agents.INTERFACES`` for ``claude``, ``codex``, ``pi`` and the ``claude_code``
alias (the pattern of ``tests/workflow/workflow_fakes.py``). ``harness.install``
never replaces an entry that is already registered, so the fakes stay for the
whole process.

A script is JSON: ``{"agents": {"<agent>": [{"envelope": {...}, "edits":
[...]}, ...]}}``. Each call of an agent takes the entry at the position given by
the number of calls of that agent already recorded in ``<script>.calls.jsonl``,
applies its edits and returns the envelope, so a second process with the same
script continues with the next entry. Concurrent processes on one script are not
supported. Every call is appended to ``<script>.calls.jsonl`` and to the agent's
``raw_output_path``.

Optional ``wait_for_file`` (absolute path) holds a recorded call until released;
``wait_timeout_s`` defaults to 120 seconds and must be finite and positive.

Edits: ``{"path": p, "write": text}``, ``{"path": p, "append": text}`` or
``{"path": p, "replace": [old, new]}`` (``old`` must occur). A relative ``path``
is relative to the working directory the engine gave the agent (its worktree);
an absolute one is written exactly there (B1 writes into the main checkout).

``@output`` (``OUTPUT``) in an edit ``path`` or anywhere in the envelope stands
for the output path the agent's rendered prompt names: the first backticked
relative ``.md`` path in its ``## Task`` section (``output_path``). The fake
takes the name from the prompt the way a model would, so a prompt whose name
the task run's write guard rejects fails validation too.
"""

from __future__ import annotations

import copy
import json
import math
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

HARNESS_NAMES = ("claude", "codex", "pi")
REAL_HARNESS_MESSAGE = "validation: real harness reached"
OUTPUT = "@output"

_SPAN = re.compile(r"`([^`\n]+)`")
_PLACEHOLDER = re.compile(r"<([^<>]+)>")


class RealHarnessReached(RuntimeError):
    pass


def apply_edits(cwd: Path, edits: list[dict[str, Any]]) -> list[str]:
    changed: list[str] = []
    for edit in edits:
        rel = str(edit["path"])
        path = Path(rel) if Path(rel).is_absolute() else cwd / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if "write" in edit:
            path.write_text(str(edit["write"]), encoding="utf-8", newline="\n")
        elif "append" in edit:
            old = path.read_text(encoding="utf-8") if path.exists() else ""
            path.write_text(old + str(edit["append"]), encoding="utf-8", newline="\n")
        elif "replace" in edit:
            before, after = edit["replace"]
            text = path.read_text(encoding="utf-8")
            if before not in text:
                raise ValueError(f"fake edit: {before!r} not found in {rel}")
            path.write_text(text.replace(before, after, 1), encoding="utf-8", newline="\n")
        else:
            raise ValueError(f"fake edit without write/append/replace: {edit}")
        changed.append(rel)
    return changed


def output_path(prompt: str, adw_id: str) -> str:
    """The repo output path the prompt's ``## Task`` section tells the agent to write.

    The first backticked relative ``.md`` path wins; paths under
    ``<context_handoff_dir>`` are skipped. A placeholder such as <adw_id> is
    filled in with the session id, any other placeholder with its own name in
    kebab-case, as an agent following the prompt literally would.
    """
    lines = prompt.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == "## Task"]
    if not starts:
        raise ValueError("validation fake: the prompt has no '## Task' section")
    task = "\n".join(lines[starts[-1] + 1 :])
    for span in _SPAN.findall(task):
        if (
            not span.endswith(".md")
            or "/" not in span
            or " " in span
            or '"' in span
            or span.startswith(("/", ".", "<context_handoff_dir>"))
        ):
            continue
        return _PLACEHOLDER.sub(lambda m: _fill(m.group(1), adw_id), span)
    raise ValueError("validation fake: no output path in the prompt")


def _fill(name: str, adw_id: str) -> str:
    if name == "adw_id":
        return adw_id
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _uses_output(value: Any) -> bool:
    if isinstance(value, str):
        return OUTPUT in value
    if isinstance(value, list):
        return any(_uses_output(v) for v in value)
    if isinstance(value, dict):
        return any(_uses_output(v) for v in value.values())
    return False


def _substitute(value: Any, output: str) -> Any:
    if isinstance(value, str):
        return value.replace(OUTPUT, output)
    if isinstance(value, list):
        return [_substitute(v, output) for v in value]
    if isinstance(value, dict):
        return {k: _substitute(v, output) for k, v in value.items()}
    return value


class _Tracker:
    def observe(self, event: dict[str, Any]) -> None:
        return None


class FakeHarness:
    """Stands in for a harness module in ``agents.INTERFACES``."""

    ToolCallTracker = _Tracker

    def __init__(
        self,
        name: str,
        script: dict[str, Any],
        script_path: Path,
        taken: dict[str, int] | None = None,
    ) -> None:
        self.name = name
        self.script = script
        self.calls_path = script_path.with_name(script_path.name + ".calls.jsonl")
        self._local: dict[str, int] = {} if taken is None else taken

    def _recorded(self, agent: str) -> int:
        """Calls of `agent` already recorded in ``calls.jsonl`` (by any process)."""
        try:
            lines = self.calls_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return 0
        count = 0
        for line in lines:
            try:
                call = json.loads(line)
            except ValueError:
                continue
            if isinstance(call, dict) and call.get("agent") == agent:
                count += 1
        return count

    def resolve_model(self, pattern: str) -> tuple[str, str]:
        return ("fake", pattern)

    def context_window(self, *args: Any) -> int:
        return 0

    def run(
        self,
        request: Any,
        on_event: Callable[..., Any] | None = None,
        on_wait: Callable[..., Any] | None = None,
        on_spawn: Callable[..., Any] | None = None,
        on_exit: Callable[..., Any] | None = None,
    ) -> Any:
        from aifactory.engine.data_types import AgentResult

        agent = Path(request.session_dir).parent.name
        queue = self.script.setdefault("agents", {}).get(agent) or []
        taken = max(self._recorded(agent), self._local.get(agent, 0))
        if taken >= len(queue):
            raise RuntimeError(f"validation fake: no scripted entry left for {agent!r}")
        self._local[agent] = taken + 1
        entry = copy.deepcopy(queue[taken])
        output: str | None = None
        if _uses_output(entry):
            adw_id = Path(request.session_dir).parent.parent.name
            output = output_path(str(request.prompt or ""), adw_id)
            entry = _substitute(entry, output)
        from aifactory.engine.utils import operator_env
        from validation.hidden import HIDDEN_ENV, HIDDEN_TARGET

        cwd = Path(request.cwd or ".")
        hidden_file = (cwd / HIDDEN_TARGET).exists()
        hidden_env = HIDDEN_ENV in operator_env()
        changed = apply_edits(cwd, list(entry.get("edits") or []))
        call = {
            "harness": self.name,
            "agent": agent,
            "model": request.model,
            "thinking": request.thinking,
            "cwd": str(cwd),
            "session_id": request.session_id,
            "changed": changed,
            "output": output,
            "hidden_file": hidden_file,  # the hidden test must never be visible to an agent
            "hidden_env": hidden_env,
        }
        with self.calls_path.open("a", encoding="utf-8", newline="\n") as out:
            out.write(json.dumps(call) + "\n")
        raw = Path(request.raw_output_path)
        raw.parent.mkdir(parents=True, exist_ok=True)
        with raw.open("a", encoding="utf-8", newline="\n") as out:
            out.write(json.dumps({"type": "validation.fake", **call}) + "\n")
        if "wait_for_file" in entry:
            release = Path(entry["wait_for_file"])
            timeout = float(entry.get("wait_timeout_s", 120))
            if not release.is_absolute() or not math.isfinite(timeout) or timeout <= 0:
                raise ValueError("validation fake: gate needs an absolute path and finite timeout")
            deadline = time.monotonic() + timeout
            while not release.exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"validation fake: timed out waiting for {release}")
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        envelope = entry.get("envelope") or {"status": "success", "summary": "done"}
        return AgentResult(text=json.dumps(envelope), returncode=0, session_id=request.session_id)


def _guard(name: str) -> Callable[..., Any]:
    def run(*args: Any, **kwargs: Any) -> Any:
        raise RealHarnessReached(f"{REAL_HARNESS_MESSAGE}: {name}")

    return run


def install(script_path: Path) -> dict[str, FakeHarness]:
    """Swap every harness for a fake reading `script_path`; the real adapters raise."""
    from aifactory import harness

    agents = harness.install()
    script = json.loads(script_path.read_text(encoding="utf-8"))
    taken: dict[str, int] = {}
    fakes = {name: FakeHarness(name, script, script_path, taken) for name in HARNESS_NAMES}
    for name in HARNESS_NAMES:
        module = harness.load(name)
        setattr(module, "run", _guard(name))  # noqa: B010
        setattr(module, "resolve_model", fakes[name].resolve_model)  # noqa: B010
    for name, fake in fakes.items():
        agents.INTERFACES[name] = fake
    agents.INTERFACES["claude_code"] = fakes["claude"]
    return fakes
