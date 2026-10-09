"""The `command` code step: argv from the workflow, `passed` from the exit code."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import pytest
from workflow_fakes import (
    EngineEnv,
    FakeCodeRunner,
    ok,
    workflow,
    workflow_env_fixture,  # noqa: F401  (pytest fixture)
)

from aifactory.engine import data_types as dt
from aifactory.engine import session
from aifactory.workflow import CodeStep, EngineCodeRunner, run_workflow

HEADER = "name: t\ndescription: A workflow written only to exercise the command step\n"


def _step(*argv: str, timeout: int = 60) -> CodeStep:
    return CodeStep(
        name="command",
        action="command",
        key="suite",
        phase_id="suite",
        owner="quality",
        description="Run the suite as a plain command",
        path="steps[0].command",
        argv=argv,
        timeout=timeout,
    )


def _command(env: EngineEnv, step: CodeStep, adw_id: str) -> Any:
    run = session.ensure(env.cfg, adw_id)
    params = dt.PhaseParams(
        name=step.phase_id, kind="code", owner=step.owner, description=step.description
    )
    with run.phase(params):
        result = EngineCodeRunner().command(run, step)
    run.finish(accepted=True)
    return result


def test_command_uses_argv_and_result_is_read_by_id(workflow_env: EngineEnv) -> None:
    text = (
        HEADER
        + """\
steps:
  - command: {id: dotnet_test, argv: [dotnet, test, --no-build]}
accept: dotnet_test.passed
"""
    )
    code = FakeCodeRunner([])
    result = run_workflow(workflow(text), "do it", workflow_env.cfg, code=code)
    assert code.commands == [("dotnet", "test", "--no-build")]
    assert result.results["dotnet_test"]["passed"] is True
    assert result.results["dotnet_test"]["ran"] is True
    assert [name for name, _, _ in result.phases] == ["request", "dotnet_test"]
    assert result.accepted is True


def test_exit_zero_passes(workflow_env: EngineEnv) -> None:
    result = _command(workflow_env, _step(sys.executable, "-c", "raise SystemExit(0)"), "c0000001")
    assert result.passed is True
    assert result.failures == []
    assert result.checks[0].returncode == 0


def test_nonzero_exit_fails(workflow_env: EngineEnv) -> None:
    result = _command(workflow_env, _step(sys.executable, "-c", "raise SystemExit(3)"), "c0000002")
    assert result.passed is False
    assert result.checks[0].returncode == 3
    assert "exited 3" in result.failures[0]


def test_missing_binary_fails_with_127(workflow_env: EngineEnv) -> None:
    result = _command(workflow_env, _step("no-such-binary-for-haifa-tests"), "c0000003")
    assert result.passed is False
    assert result.checks[0].returncode == 127


@pytest.mark.parametrize("exit_code", [0, 3, None])
def test_background_child_output_handles_do_not_delay_command_exit(
    workflow_env: EngineEnv, tmp_path: Path, exit_code: int | None
) -> None:
    release = tmp_path / "release"
    done = tmp_path / "done"
    child = (
        "import pathlib, time; "
        f"release = pathlib.Path({str(release)!r}); done = pathlib.Path({str(done)!r}); "
        "deadline = time.monotonic() + 10\n"
        "while not release.exists() and time.monotonic() < deadline: time.sleep(0.02)\n"
        "done.touch()\n"
    )
    parent = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}], stdin=subprocess.DEVNULL); "
        "print('parent stdout', flush=True); "
        "print('parent stderr', file=sys.stderr, flush=True); "
        + ("time.sleep(30)" if exit_code is None else f"sys.exit({exit_code})")
    )
    try:
        result = _command(workflow_env, _step(sys.executable, "-c", parent, timeout=2), "c0000004")
        assert result.checks[0].returncode == (124 if exit_code is None else exit_code)
        assert result.passed is (exit_code == 0)
        assert not done.exists(), "command waited for the background child to close output handles"
        log = Path(result.checks[0].output_artifact).read_text(encoding="utf-8")
        assert "parent stdout" in log
        assert "parent stderr" in log
        assert ("Timed out:" in log) is (exit_code is None)
    finally:
        release.touch()
        if exit_code is None:
            # A timeout now terminates the whole process tree; only normally exited
            # commands leave their background helper alive to finish independently.
            time.sleep(0.2)
            assert not done.exists(), "a timed-out command left its child running"
        else:
            deadline = time.monotonic() + 15
            while not done.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert done.exists(), "background child did not exit"


class _RealCommand(FakeCodeRunner):
    """Scripted everything, except `command`, which really runs."""

    def command(self, run: Any, step: CodeStep) -> Any:
        self.commands.append(step.argv)
        return EngineCodeRunner().command(run, step)


def test_command_drives_a_repair_loop(workflow_env: EngineEnv) -> None:
    # The suite fails until the fixer creates `fixed`; the loop stops at the green run.
    check = "import pathlib, sys; sys.exit(0 if pathlib.Path('fixed').exists() else 1)"
    text = (
        HEADER
        + f"""\
steps:
  - repeat: {{max: 2, until: suite.passed}}
    steps:
      - command: {{id: suite, argv: [{sys.executable!r}, -c, {check!r}]}}
      - fix
accept: suite.passed
"""
    )
    workflow_env.script.add("builder", ok(summary="fixed", changed_files=["fixed"]))

    def fix(cwd: Path) -> None:
        (cwd / "fixed").write_text("x\n", encoding="utf-8", newline="\n")

    workflow_env.script.on("builder", fix)
    code = _RealCommand([])
    result = run_workflow(workflow(text), "do it", workflow_env.cfg, code=code)
    assert [name for name, _, _ in result.phases] == ["request", "suite_1", "fix_1", "suite_2"]
    assert (result.exit_code, result.accepted) == (0, True)
    assert len(code.commands) == 2
    assert '"passed": false' in workflow_env.script.calls[0].previous()
