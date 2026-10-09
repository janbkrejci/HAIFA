"""`run_workflow(test_command=...)`: every `test` step runs it, as a real subprocess."""

from __future__ import annotations

import shlex
import sys

from workflow_fakes import (
    EngineEnv,
    workflow,
    workflow_env_fixture,  # noqa: F401  (pytest fixture)
)

from aifactory.engine import data_types as dt
from aifactory.engine import quality as engine_quality
from aifactory.engine import session
from aifactory.workflow import run_workflow

TEXT = """\
name: t
description: A workflow written only to exercise the test step
steps:
  - test
  - test: {id: retest}
accept: test.passed
"""


def test_test_command_passes(workflow_env: EngineEnv) -> None:
    argv = [sys.executable, "-c", "raise SystemExit(0)"]
    result = run_workflow(workflow(TEXT), "do it", workflow_env.cfg, test_command=argv)
    assert result.results["test"]["passed"] is True
    assert [name for name, _, _ in result.phases] == ["request", "test", "retest"]
    assert result.accepted is True


def test_test_command_nonzero_fails(workflow_env: EngineEnv) -> None:
    argv = [sys.executable, "-c", "raise SystemExit(3)"]
    result = run_workflow(workflow(TEXT), "do it", workflow_env.cfg, test_command=argv)
    assert result.results["test"]["passed"] is False
    assert f"`{shlex.join(argv)}` exited 3" in result.results["test"]["failures"][0]
    assert result.accepted is False


def test_default_test_command_is_just_test(workflow_env: EngineEnv) -> None:
    run = session.ensure(workflow_env.cfg, "t0000001")
    params = dt.PhaseParams(name="test", kind="code", owner="quality", description="Run tests")
    with run.phase(params):
        check = engine_quality.test(run)
    run.finish(accepted=True)
    assert check.command == "just test"


def test_invalid_utf8_child_output_records_failure(workflow_env: EngineEnv) -> None:
    argv = [
        sys.executable,
        "-c",
        "import os; os.write(1, bytes([0xed])); os.write(2, bytes([0xed])); raise SystemExit(3)",
    ]
    result = run_workflow(workflow(TEXT), "do it", workflow_env.cfg, test_command=argv)
    assert result.accepted is False
    assert result.results["test"]["passed"] is False
    assert f"`{shlex.join(argv)}` exited 3" in result.results["test"]["failures"][0]
    logs = list(workflow_env.repo.parent.rglob("command.log"))
    assert logs
    assert all("exit: 3" in p.read_text(encoding="utf-8") for p in logs)
    assert all("\ufffd" in p.read_text(encoding="utf-8") for p in logs)
