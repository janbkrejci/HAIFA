"""``factory harness check``: is each harness CLI on PATH, and which version."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

from aifactory.engine import data_types as dt
from aifactory.engine.utils import operator_env
from aifactory.harness import CLI_BINARIES, HARNESSES, canonical


@dataclass
class HarnessStatus:
    name: str
    binary: str
    path: str | None = None
    version: str | None = None
    error: str | None = None
    agents: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.path and self.version and not self.error)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def binary_name(name: str) -> str:
    """The CLI of harness `name`: its override variable (``CODEX_PATH``...), else the default."""
    env_var, default = CLI_BINARIES[name]
    return os.environ.get(env_var) or default


def installed_path(name: str) -> str | None:
    """Where the CLI of harness `name` is on PATH, or None; the CLI is not run."""
    return shutil.which(binary_name(name))


def check_harness(name: str, agents: Iterable[str] = ()) -> HarnessStatus:
    """Locate the harness binary and ask it for ``--version``."""
    binary = binary_name(name)
    status = HarnessStatus(name=name, binary=binary, agents=list(agents))
    path = installed_path(name)
    if path is None:
        status.error = "not on PATH"
        return status
    status.path = path
    try:
        proc = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            env=operator_env(),
            check=False,
            encoding="utf-8",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        status.error = f"--version failed: {exc}"
        return status
    version = _first_line(proc.stdout or "") or _first_line(proc.stderr or "")
    if proc.returncode != 0:
        status.error = f"--version exited {proc.returncode}: {version}".rstrip(": ")
        return status
    status.version = version or None
    if not version:
        status.error = "--version printed nothing"
    return status


def harnesses_in_config(cfg: dt.SSSFConfig) -> dict[str, list[str]]:
    """Canonical harness -> names of the agents using it, in ``HARNESSES`` order."""
    used: dict[str, list[str]] = {}
    for agent in cfg.agents:
        used.setdefault(canonical(str(agent.coding_agent)), []).append(agent.name)
    return {name: used[name] for name in HARNESSES if name in used}


def check_all(cfg: dt.SSSFConfig | None = None) -> list[HarnessStatus]:
    """Check the harnesses ``cfg`` uses, or every harness without a config."""
    if cfg is None:
        return [check_harness(name) for name in HARNESSES]
    return [check_harness(name, agents) for name, agents in harnesses_in_config(cfg).items()]
