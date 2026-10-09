"""R1/R10 verdicts: ``failed`` when a real check failed, ``inconclusive`` only for a roster gap.

A stub ``Context`` stands in for the sandbox; no model, no ``factory`` command.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from validation.context import Cmd
from validation.fake_scripts import REVIEW_RULE_MARKER
from validation.hidden import HIDDEN_CLASS
from validation.results import FAILED, INCONCLUSIVE
from validation.scenarios import FORCED_REVIEW_HAPPY, r1, r10

CLAUDE_ONLY = {
    "plan": "claude",
    "build": "claude",
    "review": "claude",
    "revise": "claude",
    "fix": "claude",
    "document": "claude",
}
RUN_ID = "run-1"


class StubContext:
    """What ``r1``/``r10`` call on ``Context``, answered from fixed data."""

    def __init__(self, tmp: Path, *, ok: bool, phases: list[str], local: bool = False) -> None:
        self.remote = "local" if local else "github"
        self.local = local
        self.harnesses = dict(CLAUDE_ONLY)
        self.state: dict[str, Any] = {}
        self.repo = tmp
        self.tmp = tmp
        self.ok = ok
        self.names = phases
        prompt = tmp / RUN_ID / "reviewer" / "prompts" / "user.md"
        prompt.parent.mkdir(parents=True)
        prompt.write_text(f"rule: {REVIEW_RULE_MARKER}\n", encoding="utf-8", newline="\n")

    def catch_up_base(self) -> None:
        return None

    def run_task(self, task: str, variant: str | None = None) -> Cmd:
        state = "succeeded" if self.ok else "failed"
        run = {"run_id": RUN_ID, "state": state, "head_sha": "", "error": None}
        pr = {"url": "https://example.test/pr/1"} if self.ok else {}
        return Cmd(
            argv=["factory", "run", task],
            code=0 if self.ok else 1,
            data={"ok": self.ok, "data": {"run": run, "pr": pr}},
            log=self.tmp / "log",
        )

    def reference(self, res: Any, cmd: Cmd) -> str | None:
        run_id = cmd.run.get("run_id")
        if run_id:
            res.add_run(str(run_id))
        return run_id

    def add_pr(self, res: Any, task: str, pr: dict[str, Any]) -> None:
        return None

    def phases(self, run_id: str) -> list[dict[str, Any]]:
        return [{"name": n, "status": "success"} for n in self.names]

    def phase_rows(self, run_id: str) -> dict[str, dict[str, Any]]:
        return {n: {"status": "success"} for n in self.names}

    def agent_starts(self, run_id: str) -> list[dict[str, Any]]:
        return [
            {"phase": n, "coding_agent": "claude", "session_id": "s1"}
            for n in self.names
            if n in ("plan", "build", "fix_1", "review_1", "revise_1", "review_2", "document")
        ]

    def session_usage(self, run_id: str) -> dict[str, Any]:
        return {"total_tokens": 1, "total_cost": 0.0}

    def phase_tokens(self, run_id: str) -> dict[str, int]:
        return {"build": 1}

    def task_run(self, run_id: str) -> dict[str, Any]:
        return {}

    def test_output(self, run_id: str, phase: str) -> str:
        return f"FAILED {HIDDEN_CLASS}" if phase == "test_1" else ""

    def test_passed(self, run_id: str, phase: str) -> bool:
        return phase != "test_1"

    def session_dir(self, run_id: str) -> Path:
        return self.tmp / run_id

    def envelope(self, run_id: str, phase: str) -> dict[str, Any]:
        envelopes: dict[str, dict[str, Any]] = {
            "review_1": {"approved": False, "blocking": ["x"]},
            "review_2": {"approved": True},
        }
        return envelopes.get(phase, {})


R10_PHASES = [
    "request", "plan", "commit_plan", "build", "test_1", "fix_1", "test_2",
    "review_1", "revise_1", "review_2", "retest", "commit_build", "changes",
    "document", "commit_docs",
]  # fmt: skip


def check(res: Any, name: str) -> bool:
    return bool(next(c.ok for c in res.checks if c.name == name))


def test_r10_failed_run_without_fix_round_is_failed(tmp_path: Path) -> None:
    ctx = StubContext(tmp_path, ok=False, phases=["request", "plan"])
    res = r10(ctx)  # type: ignore[arg-type]
    assert res.outcome == FAILED
    assert check(res, "run_ok") is False


def test_r10_only_missing_codex_is_inconclusive(tmp_path: Path) -> None:
    ctx = StubContext(tmp_path, ok=True, phases=R10_PHASES)
    res = r10(ctx)  # type: ignore[arg-type]
    assert all(c.ok for c in res.checks), res.checks
    assert res.outcome == INCONCLUSIVE


def test_r10_successful_run_without_fix_round_stays_inconclusive(tmp_path: Path) -> None:
    ctx = StubContext(tmp_path, ok=True, phases=list(FORCED_REVIEW_HAPPY))
    res = r10(ctx)  # type: ignore[arg-type]
    assert res.outcome == INCONCLUSIVE


def test_r1_failed_run_is_failed(tmp_path: Path) -> None:
    ctx = StubContext(tmp_path, ok=False, phases=list(FORCED_REVIEW_HAPPY), local=True)
    res = r1(ctx)  # type: ignore[arg-type]
    assert res.outcome == FAILED
    assert check(res, "run_ok") is False


def test_r1_only_missing_harnesses_is_inconclusive(tmp_path: Path) -> None:
    ctx = StubContext(tmp_path, ok=True, phases=list(FORCED_REVIEW_HAPPY), local=True)
    res = r1(ctx)  # type: ignore[arg-type]
    assert all(c.ok for c in res.checks), res.checks
    assert res.outcome == INCONCLUSIVE
