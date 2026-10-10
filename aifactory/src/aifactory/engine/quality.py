"""Deterministic command runner for the test and command steps.

A known command is not a judgement call: it runs as a subprocess, costs nothing,
and returns the same answer every time.

aifactory 3.0: the lint/typecheck/build/test placeholder blocks are gone. The
`test` step runs the checks a tester agent chose (aifactory.testing.executor),
a `command` step runs its own argv; both go through `_run` below.

Two rules for every argv: a LIST, never a shell string, and binaries by BARE
NAME (the operator's environment resolves them, see utils.operator_env).
"""

from __future__ import annotations

import contextlib
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

from aifactory import oscompat

from .data_types import (EventRecord, QualityCheckResult, QualityCheckSpec, QualityResult,
                         VerifyOutput)
from .utils import now_iso, operator_env

# How much of a failing command's output rides back inside the envelope. Enough
# for a builder to act on without opening the artifact; bounded so a runaway
# stack trace can't swamp the next agent's context.
TAIL_CHARS = 4_000

# aifactory: default time limit (s) of the test step; run.test_timeout overrides it.
DEFAULT_TEST_TIMEOUT = 600
# aifactory: trace event (type log) of the test step's wait for a slot (engine.slots).
TEST_SLOT_EVENT = "test_slot"


def _text(value: str | bytes | None) -> str:  # aifactory
    """Decode captured binary output, including partial output from timed-out commands."""
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def _check_dir(run, name: str) -> Path:
    seq = run.phases[-1].seq if run.phases else 0
    path = run.context_handoff_dir / "quality" / f"{seq:02d}_{name}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run(spec: QualityCheckSpec, run) -> QualityCheckResult:
    phase = run.phases[-1]
    output_dir = _check_dir(run, spec.name)
    output_artifact = output_dir / "command.log"
    command = shlex.join(spec.argv)
    env = operator_env()             # the engineer's own shell environment

    run.console.note(f"quality {spec.name}: {command}")
    started_at = now_iso()
    clock = time.monotonic()
    stdout = ""
    stderr = ""
    try:
        # aifactory 2.14: files let us wait for the command's actual exit, not EOF
        # on pipes inherited by background helpers (e.g. check-scoped cleanup).
        # Keep partial output on timeout without waiting for those helpers either.
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                # aifactory 2.14: own the process group so a timed-out test cannot
                # leave pytest workers running against a deleted temporary directory.
                with subprocess.Popen(
                    spec.argv,
                    cwd=run.repo_root,
                    env=env,
                    stdout=out,
                    stderr=err,
                    start_new_session=True,
                    creationflags=oscompat.NEW_GROUP,
                ) as process:
                    try:
                        returncode = process.wait(timeout=spec.timeout_seconds)
                    except subprocess.TimeoutExpired:
                        with contextlib.suppress(ProcessLookupError):
                            oscompat.kill_group(process.pid, force=True)
                        if process.poll() is None:
                            process.kill()
                        process.wait()
                        returncode = 124
                        stderr = f"\nTimed out: exceeded the time limit of {spec.timeout_seconds:g}s."  # aifactory 3.0: a shared budget leaves fractions
            finally:
                out.seek(0)
                stdout = _text(out.read())
                err.seek(0)
                stderr = _text(err.read()) + stderr
    except OSError as error:
        # A missing binary lands here as exit 127 with the real message — no
        # pre-flight probe needed, and none wanted.
        returncode = 127
        stderr = str(error)

    duration = time.monotonic() - clock
    output_artifact.write_text(
        f"$ {command}\nexit: {returncode}\nduration_seconds: {duration:.3f}\n"
        f"\n--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}\n", encoding="utf-8", newline="\n"
    )
    passed = returncode == 0
    run.tracer.event(EventRecord(
        adw_id=run.adw_id,
        phase_id=phase.phase_id,
        type="tool_call",
        name=f"quality:{spec.name}",
        payload={
            "area": spec.area,
            "operation": spec.operation,
            "command": command,
            "returncode": returncode,
            "passed": passed,
            "timeout_seconds": spec.timeout_seconds,  # aifactory
            "output_artifact": str(output_artifact),
        },
        started_at=started_at,
        ended_at=now_iso(),
    ))
    run.console.note(
        f"quality {spec.name}: {'passed' if passed else 'failed'} "
        f"(exit {returncode}, {duration:.1f}s)"
    )
    return QualityCheckResult(
        name=spec.name,
        area=spec.area,
        operation=spec.operation,
        command=command,
        returncode=returncode,
        passed=passed,
        duration_seconds=duration,
        output_artifact=str(output_artifact),
        output_tail=(stdout + stderr)[-TAIL_CHARS:],
    )


# ── Blocks ────────────────────────────────────────────────────────────────────
# Replace every argv below. See the banner at the top of this file.

def _slot_event(run, payload: dict) -> None:  # aifactory
    phase = run.phases[-1]
    run.tracer.event(EventRecord(adw_id=run.adw_id, phase_id=phase.phase_id,
                                 type="log", name=TEST_SLOT_EVENT, payload=payload))


def as_envelope(result: QualityResult, what: str) -> VerifyOutput:
    """Wrap a deterministic result so an agent can be handed it directly.

    Agents hand each other typed envelopes; code blocks return QualityResult.
    This is the adapter, so a failing lint or test run flows back into the
    builder through exactly the same door an agent's report would — the ADW
    script is the only thing that knows the difference.
    """
    return VerifyOutput(
        status="success" if result.passed else "fail",
        summary=(f"{what}: {result.test_plan.coverage}; {result.test_plan.executed} executed; "
                 f"{result.test_plan.reason}" if result.test_plan and result.passed else
                 f"{what}: all {len(result.checks)} check(s) passed" if result.passed
                 else f"{what}: {len(result.failures)} of {len(result.checks)} check(s) failed"),
        artifacts=result.artifacts,
        notes_for_next_agent=("" if result.passed else
                              "Fix every failure below. The output is verbatim from the "
                              "command — trust it over any summary."),
        passed=result.passed,
        failures=result.failures,
        test_plan=result.test_plan,  # aifactory 2.15: preserve selection evidence
    )
