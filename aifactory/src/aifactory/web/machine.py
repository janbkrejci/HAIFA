"""Global machine checks: cached reads, explicit and server scheduled refreshes.

The view keeps only actionable findings (see ``web.factory.actionable_findings``) and
drops the info ``harness_missing`` of a harness no registered repository uses;
``missing_harnesses`` still names every missing harness.
"""

from __future__ import annotations

import copy
import tempfile
import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aifactory.check import Machine, Probe, SystemMachine, run_check
from aifactory.check.context import CheckContext
from aifactory.config.errors import ConfigError
from aifactory.harness import CLI_BINARIES, HARNESSES
from aifactory.harness.check import HarnessStatus, harnesses_in_config
from aifactory.harness.settings import read as read_harness_settings
from aifactory.harness.settings import test_failed
from aifactory.providers import git
from aifactory.web.factory import actionable_findings, is_actionable

_clock = time.monotonic


@dataclass
class GlobalState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    checks: dict[bool, tuple[float, dict[str, Any], bool, str]] = field(default_factory=dict)
    cache_lock: threading.Lock = field(default_factory=threading.Lock)
    harness_catalog: dict[str, Any] | None = None
    harness_lock: threading.Lock = field(default_factory=threading.Lock)

    def invalidate(self) -> None:
        with self.cache_lock:
            self.checks.clear()
        with self.harness_lock:
            self.harness_catalog = None

    def harnesses(self, home: Path, *, fresh: bool = False) -> dict[str, Any]:
        from aifactory.harness.settings import catalog

        with self.harness_lock:
            if self.harness_catalog is None or fresh:
                self.harness_catalog = catalog(home)
            return copy.deepcopy(self.harness_catalog)


@dataclass
class HomeMachine:
    """Delegate probes while binding both environment APIs to the dashboard home."""

    delegate: Machine
    home_dir: Path

    def environment(self) -> Mapping[str, str]:
        return {**self.delegate.environment(), "HAIFA_HOME": str(self.home_dir)}

    def env(self, name: str) -> str | None:
        return str(self.home_dir) if name == "HAIFA_HOME" else self.delegate.env(name)

    def which(self, program: str) -> str | None:
        choices = read_harness_settings(self.home_dir)
        if choices and any(
            not choices.harnesses[name].enabled and program == (self.delegate.env(env) or binary)
            for name, (env, binary) in CLI_BINARIES.items()
        ):
            return None
        return self.delegate.which(program)

    def run(
        self, argv: Sequence[str], timeout: float = 15, cwd: Path | None = None
    ) -> Probe | None:
        return self.delegate.run(argv, timeout, cwd)

    def harness(self, name: str, agents: Iterable[str]) -> HarnessStatus:
        choices = read_harness_settings(self.home_dir)
        if choices and not choices.harnesses[name].enabled:
            return HarnessStatus(name, CLI_BINARIES[name][1], error="disabled on this computer")
        return self.delegate.harness(name, agents)

    def home(self) -> Path:
        return self.delegate.home()

    def platform(self) -> str:
        return self.delegate.platform()

    def file_mode(self, path: Path) -> int | None:
        return self.delegate.file_mode(path)


def _registered(home: Path) -> list[Any]:
    """The registered repositories of ``home``; none when the registry is missing or bad."""
    from aifactory.web.registry import RepoError, parse_registry, registry_path

    path = registry_path(home)
    try:
        return list(parse_registry(path.read_text(encoding="utf-8"), str(path))[0].repos)
    except (OSError, UnicodeError, RepoError):
        return []


def outside_repo() -> Path:
    """Find an existing path outside git, even when HAIFA_HOME is in a repo.

    The process's working directory is never used: it may have been deleted since the
    dashboard started (``os.getcwd()`` then fails without naming any file).
    """
    temp = Path(tempfile.gettempdir())
    for path in (temp, Path(temp.anchor)):
        if git.run_bytes(path, ["rev-parse", "--show-toplevel"]).returncode != 0:
            return path
    raise RuntimeError("no outside-repository path available for machine check")


def check_view(
    home: Path, state: GlobalState, *, offline: bool, fresh: bool, machine: Machine | None
) -> tuple[dict[str, Any], bool, str]:
    with state.cache_lock:
        entry = state.checks.get(offline)
        cached = entry is not None and not fresh
        if cached:
            assert entry is not None
            _, data, ok, message = entry
        else:
            report = run_check(
                outside_repo(),
                offline=offline,
                require_repo=False,
                machine=HomeMachine(machine or SystemMachine(), home),
            )
            errors = report.errors()
            message = f"{len(errors)} error(s): {', '.join(dict.fromkeys(f.code for f in errors))}"
            ok = report.ok
            data = {**report.to_json(), "checked_at": datetime.now(UTC).isoformat()}
            state.checks[offline] = (_clock(), data, ok, message)
        view = {**copy.deepcopy(data), "cached": cached}
    # Registry changes must be visible even while the machine probes are cached.
    counts = dict.fromkeys(HARNESSES, 0)
    repos = _registered(home)
    adapter = HomeMachine(machine or SystemMachine(), home)
    for repo in repos:
        try:
            context = CheckContext(
                Path(repo.path), offline=True, machine=adapter, require_repo=False
            )
            roster = context.roster
            if roster is not None:
                for name in harnesses_in_config(roster):
                    counts[name] += 1
        except (ConfigError, OSError):
            continue
    view["harness_repos"] = counts
    # Which harnesses are missing stays known (the roster editor and getting started use
    # it), even when the info finding of a harness no repository uses is not shown.
    missing = [
        name
        for name in HARNESSES
        if any(
            f["code"] == "harness_missing" and f["message"].startswith(f"harness {name} ")
            for f in view["findings"]
        )
    ]
    view["missing_harnesses"] = missing
    choices = read_harness_settings(home)
    if choices:
        for name, choice in choices.harnesses.items():
            if choice.enabled and test_failed(name, choice.model, home):
                view["findings"].append(
                    {
                        "code": "harness_test_failed",
                        "scope": "machine",
                        "severity": "error",
                        "message": f"{name} / {choice.model}: test harnessu selhal.",
                        "fix": "V nastavení harnessů oprav přihlášení nebo model. "
                        "Spusť Test znovu, případně harness vypni.",
                        "action": None,
                    }
                )
                ok = False
        if not ok:
            view["ok"] = False
            rendered_errors = [f for f in view["findings"] if f["severity"] == "error"]
            message = f"{len(rendered_errors)} error(s): " + ", ".join(
                dict.fromkeys(f["code"] for f in rendered_errors)
            )
    return actionable_findings(view, lambda f: _needed(f, counts)), ok, message


def _needed(finding: Mapping[str, Any], counts: Mapping[str, int]) -> bool:
    """Actionable, and not the info about a missing harness no registered repo uses."""
    if finding["code"] == "harness_missing" and finding["severity"] == "info":
        if any(
            finding["message"].startswith(f"harness {name} ") and not counts.get(name)
            for name in HARNESSES
        ):
            return False
    return is_actionable(finding)
