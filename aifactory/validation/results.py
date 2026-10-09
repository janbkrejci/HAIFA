"""Scenario results: the JSON each scenario writes and the run summary.

Outcome rule (prošel / selhal / pozorování):

* ``passed``: every check of the scenario is ok;
* ``failed``: at least one check is not ok, or the scenario raised;
* ``inconclusive``: set explicitly by a scenario only when the verification
  could not be done at all, e.g. a real model passed the tests at once so no
  repair round ran, or a scenario this one builds on did not run or failed.
  Its checks and observations say why.

Observations are free text of what was seen, including the limits of
aifactory. They never change the outcome.
"""

from __future__ import annotations

import datetime
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PASSED, FAILED, INCONCLUSIVE = "passed", "failed", "inconclusive"
OUTCOMES = (PASSED, FAILED, INCONCLUSIVE)

RISKS: dict[str, str] = {
    "R1": "YAML workflow nevyjádří logiku dnešních ADW",
    "R2": "Paralelní běhy mění stejné soubory a PR kolidují",
    "R3": "Stav done přes merge PR nesedí s realitou (zavřený PR, merge mimo dashboard, squash)",
    "R4": "Běh nevidí necommitnutou změnu promptu z dashboardu",
    "R5": "Worktree na běh je drahý (disk a čas)",
    "R10": "Codex má jiný proud událostí a jiné obnovení session; opravná kola ztratí kontext",
    "RESOLVE": "Konflikt dvou PR nejde vyřešit bez ruční práce",
    "B1": "Agent zapíše mimo worktree do hlavního checkoutu",
    "F2": "Akceptace F2: 5 úkolů z CLI (2 paralelně, auto-continue) po mergnutý PR a done v base",
}


def now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass
class ScenarioResult:
    scenario: str
    remote: str
    checks: list[Check] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    run_ids: list[str] = field(default_factory=list)
    prs: list[dict[str, Any]] = field(default_factory=list)
    commits: list[str] = field(default_factory=list)
    trace_sessions: list[str] = field(default_factory=list)
    trace_files: list[str] = field(default_factory=list)
    measurements: dict[str, Any] = field(default_factory=dict)
    forced: str | None = None  # an explicit outcome (inconclusive, or failed on an error)
    started_at: str = field(default_factory=now_iso)
    ended_at: str = ""
    _clock: float = field(default_factory=time.monotonic, repr=False)
    duration_s: float = 0.0

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append(Check(name, bool(ok), detail))
        return bool(ok)

    def observe(self, text: str) -> None:
        self.observations.append(text)

    def inconclusive(self, why: str) -> ScenarioResult:
        self.forced = INCONCLUSIVE
        self.observe(why)
        return self

    def add_run(self, run_id: str | None) -> None:
        if run_id and run_id not in self.run_ids:
            self.run_ids.append(run_id)

    def finish(self) -> ScenarioResult:
        self.ended_at = now_iso()
        self.duration_s = round(time.monotonic() - self._clock, 3)
        return self

    @property
    def outcome(self) -> str:
        if self.forced is not None:
            return self.forced
        if not self.checks:
            return INCONCLUSIVE
        return PASSED if all(c.ok for c in self.checks) else FAILED

    def to_json(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "risk": RISKS.get(self.scenario, ""),
            "remote": self.remote,
            "outcome": self.outcome,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_s": self.duration_s,
            "checks": [c.to_json() for c in self.checks],
            "observations": list(self.observations),
            "evidence": {
                "run_ids": list(self.run_ids),
                "prs": list(self.prs),
                "commits": list(self.commits),
                "trace": {
                    "db": "trace/sssf.db",
                    "sessions": list(self.trace_sessions),
                    "files": list(self.trace_files),
                },
            },
            "measurements": dict(self.measurements),
        }


def output_dir(results_dir: Path, remote: str, when: datetime.datetime | None = None) -> Path:
    """``<results>/<YYYY-MM-DD>/<remote>-<HHMMSS>/`` (not created)."""
    moment = when or datetime.datetime.now()
    return results_dir / moment.strftime("%Y-%m-%d") / f"{remote}-{moment.strftime('%H%M%S')}"


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return path


def write_result(out: Path, result: ScenarioResult) -> Path:
    return write_json(out / f"{result.scenario}.json", result.to_json())
