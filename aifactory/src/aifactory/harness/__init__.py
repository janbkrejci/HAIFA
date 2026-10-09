"""Harness registry: the coding agents a HAIFA agent names explicitly (D13).

Every harness is a module with the same interface as ``aifactory.engine.agent_cc``:
``run(request, on_event, on_spawn, on_exit, on_wait) -> AgentResult``,
``resolve_model``, ``context_window`` and ``ToolCallTracker``. The harness is
written on the agent (``harness: claude | codex | pi``); it is never inferred
from the model name.

``install()`` registers the adapters into ``aifactory.engine.agents.INTERFACES``.
The engine itself is left untouched: ``writes:`` stays with
``aifactory.engine.permissions``, which checks the git diff independently of
the harness.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any, Literal

# canonical name -> adapter module
HARNESSES: dict[str, str] = {
    "claude": "aifactory.engine.agent_cc",
    "codex": "aifactory.harness.codex",
    "pi": "aifactory.engine.agent_pi",
}
# kept for sssf configs and engine code that still write `claude_code`
ALIASES: dict[str, str] = {"claude_code": "claude"}
# name -> (env variable overriding the binary, default binary)
CLI_BINARIES: dict[str, tuple[str, str]] = {
    "claude": ("CLAUDE_CODE_PATH", "claude"),
    "codex": ("CODEX_PATH", "codex"),
    "pi": ("PI_PATH", "pi"),
}
REQUIRED_API = ("run", "resolve_model", "context_window", "ToolCallTracker")
HarnessName = Literal["claude", "codex", "pi"]


def canonical(name: str) -> str:
    """The canonical harness name for ``name`` (resolves aliases)."""
    resolved = ALIASES.get(name, name)
    if resolved not in HARNESSES:
        available = sorted([*HARNESSES, *ALIASES])
        raise ValueError(f"unknown harness {name!r}, available: {available}")
    return resolved


def load(name: str) -> ModuleType:
    """Import the adapter module for a harness name or alias."""
    return importlib.import_module(HARNESSES[canonical(name)])


def check_interface(module: ModuleType) -> list[str]:
    """Attributes of the shared harness interface that ``module`` lacks."""
    return [attr for attr in REQUIRED_API if not hasattr(module, attr)]


def supports_disallowed_commands(name: str) -> bool:
    """Can harness ``name`` forbid shell commands (``disallowed_commands``)?

    Read from the adapter's ``SUPPORTS_DISALLOWED_COMMANDS``; an adapter that
    does not declare it cannot.
    """
    return bool(getattr(load(name), "SUPPORTS_DISALLOWED_COMMANDS", False))


def unenforced_disallowed(agent: Any) -> str | None:
    """Why ``agent``'s ``disallowed_commands`` will not hold, or None when they will.

    ``agent`` is a roster agent (``coding_agent``, ``disallowed_commands``),
    possibly with a step override already applied.
    """
    commands = [c for c in getattr(agent, "disallowed_commands", None) or [] if str(c).strip()]
    if not commands:
        return None
    name = canonical(str(agent.coding_agent))
    if supports_disallowed_commands(name):
        return None
    listed = ", ".join(f"`{c}`" for c in commands)
    return (
        f"agent {agent.name!r}: harness {name!r} cannot forbid commands, "
        f"disallowed_commands ({listed}) are not enforced"
    )


def install() -> ModuleType:
    """Register every harness into ``agents.INTERFACES``; return ``agents``.

    Idempotent, and only missing keys are filled: a caller (or a test) that put
    its own module on a key keeps it.
    """
    from aifactory.engine import agents

    for name in [*HARNESSES, *ALIASES]:
        module = load(name)
        missing = check_interface(module)
        if missing:
            raise RuntimeError(f"harness {name!r} ({module.__name__}) lacks {missing}")
        agents.INTERFACES.setdefault(name, module)
    return agents
