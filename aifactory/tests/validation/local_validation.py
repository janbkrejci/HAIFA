"""One local validation run (`just validate --remote local`) split across several tests.

`LocalValidation` prepares the sandbox and the `Context` the way `runner.main` does
and runs single scenarios (or single F2 stages) on demand, writing their results to
disk like the runner. A test that asks for a scenario that builds on others
(`PREREQUISITES`: they share `ctx.state` and the sandbox) first runs those that have
not run yet, and a test of a stage first runs the earlier stages, so every test also
passes alone.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from validation.context import Context
from validation.f2 import F2_STAGES, F2Run
from validation.results import ScenarioResult
from validation.safety import Owned
from validation.sandbox import setup_local
from validation.scenarios import (
    R2_STAGES,
    R3_STAGES,
    RESOLVE_STAGES,
    R2Run,
    R3Run,
    ResolveRun,
)

from fake_exe import make_executable
from validation import runner

HIDDEN_ENV_KEYS = ("HAIFA_SANDBOX_REPO", "HAIFA_VALIDATE_FAKE", "HAIFA_VALIDATE_HIDDEN")


def tripwire(directory: Path, marker: Path) -> Path:
    """An executable that records it ran and fails: stands in for claude, codex, pi and gh."""
    script = directory / "tripwire"
    script.write_text(
        f'#!/bin/sh\necho "$0 $*" >> "{marker}"\nexit 97\n', encoding="utf-8", newline="\n"
    )
    return make_executable(script)


@contextmanager
def validation_env(directory: Path) -> Iterator[Path]:
    """The environment of the validation tests; yields the tripwire's marker file.

    Validation workers copy `os.environ`, so they get the tripwire too.
    """
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / "real-harness-reached"
    wire = tripwire(directory, marker)
    with pytest.MonkeyPatch.context() as mp:
        for key in ("AIFACTORY_GH", "CODEX_PATH", "CLAUDE_CODE_PATH", "PI_PATH"):
            mp.setenv(key, str(wire))
        mp.setenv("UV_NO_SYNC", "1")  # do not rebuild the venv other test workers are using
        for key in HIDDEN_ENV_KEYS:
            mp.delenv(key, raising=False)
        yield marker


def checks(data: dict[str, Any]) -> dict[str, bool]:
    items = data["checks"]
    assert isinstance(items, list)
    return {str(c["name"]): bool(c["ok"]) for c in items}


def result_checks(res: ScenarioResult) -> dict[str, bool]:
    return {c.name: c.ok for c in res.checks}


# the scenarios each one needs to have run before it on the same sandbox (``ctx.state``
# and the base branch; see the docstring of validation.scenarios). R2 -> RESOLVE and
# R1, R10 -> R3 -> R4 are independent of each other, so they may use two sandboxes.
PREREQUISITES: dict[str, tuple[str, ...]] = {
    "R1": (),
    "R10": (),
    "R2": (),
    "RESOLVE": ("R2",),
    "R3": ("R1", "R10"),
    "R4": ("R1", "R10", "R3"),
    "R5": (),
    "B1": (),
    "F2": (),
}

Stage = Callable[[Context, Any], bool]
# scenarios split into stages (one CLI step each): stages and the state they share
STAGED: dict[str, tuple[tuple[tuple[str, Stage], ...], Callable[[ScenarioResult], Any]]] = {
    "R2": (R2_STAGES, R2Run),
    "RESOLVE": (RESOLVE_STAGES, ResolveRun),
    "R3": (R3_STAGES, R3Run),
    "F2": (F2_STAGES, F2Run),
}


class LocalValidation:
    """One local validation run split into tests: sandbox, Context and results on disk."""

    def __init__(self, root: Path, roster: Path | None = None) -> None:
        (root / "work").mkdir(parents=True)
        owned = Owned()
        self.workdir = owned.add(root / "work")
        self.out = root / "results"
        sandbox = setup_local(self.workdir, roster)
        self.ctx = runner.make_context("local", sandbox, self.workdir, owned, r5_samples=3)
        self.done: dict[str, ScenarioResult] = {}
        self._states: dict[str, Any] = {}
        self._stages: dict[str, dict[str, bool]] = {}

    def _write(self) -> None:
        runner.write_results(self.ctx, self.out, list(self.done.values()))

    def _load(self, name: str) -> dict[str, Any]:
        data = json.loads((self.out / f"{name}.json").read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        return data

    def _run(self, name: str) -> None:
        for before in PREREQUISITES[name]:
            if before not in self.done:
                self._run(before)
        if name in self.done:
            return
        if name in STAGED:
            self.stage(name, STAGED[name][0][-1][0])
        else:
            (result,) = runner.run_scenarios(self.ctx, [name], self.out)
            self.done[name] = result

    def scenario(self, name: str) -> dict[str, Any]:
        """Run `name` (after the scenarios it needs) and return its result JSON."""
        self._run(name)
        self._write()
        return self._load(name)

    def stage(self, name: str, stage: str) -> Any:
        """Run the staged scenario `name` up to and including `stage`; return its state.

        A scenario stops at the first stage that returns False, like the scenario
        function itself; a later stage then fails the test that asks for it. After
        the last stage the result is finished and written like the runner does.
        """
        for before in PREREQUISITES[name]:
            if before not in self.done:
                self._run(before)
        stages, make_state = STAGED[name]
        names = [n for n, _ in stages]
        state = self._states.setdefault(name, make_state(ScenarioResult(name, "local")))
        ran = self._stages.setdefault(name, {})
        for step, func in stages[: names.index(stage) + 1]:
            if step in ran:
                continue
            stopped = [n for n, ok in ran.items() if not ok]
            assert not stopped, (name, stopped, state.res.checks, state.res.observations)
            ran[step] = func(self.ctx, state)
        if stage == names[-1] and name not in self.done:
            self.done[name] = state.res.finish()
            self._write()
        return state

    def stage_ok(self, name: str, stage: str) -> bool:
        return self._stages.get(name, {}).get(stage) is True
