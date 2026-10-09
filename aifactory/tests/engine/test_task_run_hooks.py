"""aifactory 2.9 hooks in the engine: artifact location, enforce on failure, write guard, vars."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from engine_fakes import EngineEnv, agent_phase, engine_env_fixture, start  # noqa: F401

from aifactory.engine import agents, gates, permissions
from aifactory.engine.data_types import EnvelopeBase, GateCheck, GateReport
from aifactory.engine.runner import Run


def _envelope(*artifacts: str) -> EnvelopeBase:
    return EnvelopeBase(status="success", artifacts=list(artifacts))


def test_artifacts_exist_only_inside_worktree_or_session(tmp_path: Path) -> None:
    worktree = tmp_path / "wt"
    session = tmp_path / "data" / "sessions" / "r1"
    elsewhere = tmp_path / "main"
    for folder in (worktree / "specs", session, elsewhere):
        folder.mkdir(parents=True)
    (worktree / "specs" / "a.md").write_text("a\n", encoding="utf-8", newline="\n")
    (session / "plan.md").write_text("p\n", encoding="utf-8", newline="\n")
    (elsewhere / "b.md").write_text("b\n", encoding="utf-8", newline="\n")
    (tmp_path / "x.md").write_text("x\n", encoding="utf-8", newline="\n")
    run = SimpleNamespace(repo_root=worktree, session_dir=session)

    report = gates.artifacts_exist(
        _envelope("specs/a.md", str(session / "plan.md"), str(elsewhere / "b.md"), "../x.md"),
        run,
    )

    assert [c.ok for c in report.checks] == [True, True, False, False]
    assert "outside" in report.checks[2].note
    assert "outside" in report.checks[3].note
    missing = gates.artifacts_exist(_envelope("specs/none.md"), run)
    assert missing.violations and "does not exist" in missing.checks[0].note


def _never(envelope: EnvelopeBase, run: Run) -> GateReport:
    return GateReport(checks=[GateCheck(item="never", ok=False)])


def test_breach_is_rolled_back_when_the_gate_fails(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)
    env.script.on(
        "builder", lambda cwd: (cwd / "b.txt").write_text("stray\n", encoding="utf-8", newline="\n")
    )
    env.script.add_ok("builder")

    with pytest.raises(permissions.PermissionBreach) as exc:
        agent_phase(run, "builder", gates=[_never])

    assert "b.txt" in str(exc.value)
    assert isinstance(exc.value.__cause__, agents.GateFailure)
    assert not (env.repo / "b.txt").exists()


def test_gate_failure_without_breach_keeps_its_error(engine_env: EngineEnv) -> None:
    env = engine_env
    run = start(env)
    env.script.add_ok("builder")
    with pytest.raises(agents.GateFailure):
        agent_phase(run, "builder", gates=[_never])


class _RecordingGuard:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def snapshot(self, run: Any) -> dict[str, str]:
        self.calls.append("snapshot")
        return {}

    def enforce(self, run: Any, phase: Any, agent: Any, before: Any) -> list[str]:
        self.calls.append("enforce")
        return []


def test_run_write_guard_replaces_permissions(
    engine_env: EngineEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = engine_env
    run = start(env)
    guard = _RecordingGuard()
    run.write_guard = guard

    def forbidden(*args: Any) -> Any:
        raise AssertionError("permissions module used despite run.write_guard")

    monkeypatch.setattr(permissions, "snapshot", forbidden)
    monkeypatch.setattr(permissions, "enforce", forbidden)
    env.script.on(
        "reader",
        lambda cwd: (cwd / "anything.txt").write_text("x\n", encoding="utf-8", newline="\n"),
    )
    env.script.add_ok("reader")

    agent_phase(run, "reader")

    assert guard.calls == ["snapshot", "enforce"]


def test_prompt_variables_are_rendered(engine_env: EngineEnv, tmp_path: Path) -> None:
    env = engine_env
    user = tmp_path / "prompts" / "user.md"
    user.write_text(
        "{{prompt}} spec={{spec_path}} task={{task_id}}\n", encoding="utf-8", newline="\n"
    )
    run = start(env)
    run.prompt_variables = {"spec_path": "specs/T1-x.md", "task_id": "T1", "prompt": "ignored"}
    env.script.add_ok("free")

    agent_phase(run, "free", prompt="do it")

    assert env.script.calls[0].prompt.strip() == "do it spec=specs/T1-x.md task=T1"
