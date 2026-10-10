"""`run_workflow(test_timeout=...)`: the shared time limit of every `test` step, real subprocess."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import pytest
from workflow_fakes import (
    EngineEnv,
    plan_envelope,
    workflow,
    workflow_env_fixture,  # noqa: F401  (pytest fixture)
)

from aifactory.engine import data_types as dt
from aifactory.engine import quality as engine_quality
from aifactory.engine import session
from aifactory.testing.executor import execute
from aifactory.workflow import run_workflow

TEXT = """\
name: t
description: A workflow written only to exercise the test step
steps:
  - test_plan
  - test
accept: test.passed
"""

SLEEP = [sys.executable, "-c", "import time; time.sleep(30)"]
OK = [sys.executable, "-c", "raise SystemExit(0)"]


def test_exceeded_timeout_fails_the_step(workflow_env: EngineEnv) -> None:
    workflow_env.script.add("tester", plan_envelope(*SLEEP))
    result = run_workflow(workflow(TEXT), "do it", workflow_env.cfg, test_timeout=1)
    assert result.results["test"]["passed"] is False
    assert "exceeded the time limit of" in result.results["test"]["failures"][0]
    assert result.accepted is False


def test_within_timeout_passes(workflow_env: EngineEnv) -> None:
    workflow_env.script.add("tester", plan_envelope(*OK))
    result = run_workflow(workflow(TEXT), "do it", workflow_env.cfg, test_timeout=5)
    assert result.results["test"]["passed"] is True
    assert result.results["test"]["test_plan"]["executed"] == 1
    assert result.accepted is True


@pytest.mark.parametrize(("limit", "expected"), [(None, 600), (7, 7)])
def test_test_step_timeout(
    workflow_env: EngineEnv, monkeypatch: pytest.MonkeyPatch, limit: int | None, expected: int
) -> None:
    seen: list[int] = []
    real = engine_quality._run

    def spy(spec: dt.QualityCheckSpec, run: Any) -> dt.QualityCheckResult:
        seen.append(spec.timeout_seconds)
        return real(spec, run)

    monkeypatch.setattr(engine_quality, "_run", spy)
    run = session.ensure(workflow_env.cfg, "t0000002")
    run.test_timeout = limit
    plan = dt.TestPlanOutput.model_validate(plan_envelope(*OK))
    params = dt.PhaseParams(name="test", kind="code", owner="quality", description="Run tests")
    with run.phase(params):
        result = execute(run, plan)
    run.finish(accepted=True)
    assert result.passed is True
    # The shared budget: the first check gets what is left of the limit.
    assert len(seen) == 1
    assert expected - 1 < seen[0] <= expected


def test_timeout_with_partial_output_is_text(workflow_env: EngineEnv) -> None:
    """TimeoutExpired carries bytes even with text=True; it used to raise TypeError."""
    argv = [
        sys.executable,
        "-c",
        "import sys, time; print('partial out', flush=True); "
        "sys.stderr.write('partial err\\n'); sys.stderr.flush(); time.sleep(30)",
    ]
    run = session.ensure(workflow_env.cfg, "t0000003")
    params = dt.PhaseParams(name="test", kind="code", owner="quality", description="Run tests")
    with run.phase(params):
        check = engine_quality._run(
            dt.QualityCheckSpec(
                name="x", area="backend", operation="build", argv=argv, timeout_seconds=1
            ),
            run,
        )
    run.finish(accepted=False)
    assert check.returncode == 124
    assert check.passed is False
    assert "partial out" in check.output_tail
    assert "partial err" in check.output_tail
    assert "exceeded the time limit of 1s" in check.output_tail


def test_timeout_stops_descendant_processes(workflow_env: EngineEnv, tmp_path: Path) -> None:
    heartbeat = tmp_path / "child.heartbeat"
    child = (
        "import time; from pathlib import Path\n"
        f"path = Path({str(heartbeat)!r})\n"
        "while True:\n    path.write_text(str(time.monotonic_ns()))\n    time.sleep(0.05)"
    )
    parent = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(30)"
    )
    run = session.ensure(workflow_env.cfg, "t0000004")
    params = dt.PhaseParams(name="test", kind="code", owner="quality", description="Run tests")
    with run.phase(params):
        check = engine_quality._run(
            dt.QualityCheckSpec(
                name="tree",
                area="backend",
                operation="build",
                argv=[sys.executable, "-c", parent],
                timeout_seconds=2,
            ),
            run,
        )
    run.finish(accepted=False)
    assert check.returncode == 124
    assert heartbeat.is_file(), "the child must have started before the timeout"
    # A killed orphan can remain a zombie on POSIX until init reaps it. Its heartbeat
    # still proves that it stopped executing, without treating a zombie as a live worker.
    before = heartbeat.read_bytes()
    time.sleep(0.3)
    assert heartbeat.read_bytes() == before, "timed-out checks must stop their descendants"
