"""Deterministic lint, typecheck, build, and test blocks.

A known command is not a judgement call. Anything whose invocation you can write
down belongs here as code — it runs in milliseconds, costs nothing, and returns
the same answer every time. Agents are for the parts that need reading and
deciding.

╔══════════════════════════════════════════════════════════════════════════════╗
║  REPLACE THE PLACEHOLDER COMMANDS BELOW.                                     ║
║                                                                              ║
║  test, typecheck and build default to `just test` / `just typecheck` /        ║
║  `just build`. That is a GUESS about your repo: it is right if you keep a     ║
║  justfile with those recipes, and wrong everywhere else — a missing `just`    ║
║  exits 127, and a recipe of the same name doing something else goes green     ║
║  without testing anything. Check these three before you trust a test phase.   ║
║                                                                              ║
║  lint still ships as an `echo` that exits 0 and announces it is fake.         ║
║                                                                              ║
║  For each block: write the real argv, e.g.                                    ║
║      argv=["bun", "test", "apps/web/server.test.ts"]                         ║
║      argv=["uv", "run", "pytest", "-q"]                                      ║
║      argv=["npm", "run", "lint"]                                             ║
║  Delete the blocks you don't need, and drop them from run_quality()'s list.   ║
║                                                                              ║
║  Two rules when you write the real command:                                  ║
║    1. argv LIST, never a shell string — no quoting bugs, no shell injection.  ║
║    2. Call binaries by BARE NAME. These blocks inherit the operator's         ║
║       environment (see utils.operator_env), so `bun`, `uv`, `pytest` resolve  ║
║       exactly as they do in their terminal. Never hard-code an absolute path  ║
║       like /Users/you/.bun/bin/bun — that bakes your machine into the trace.  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import contextlib
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

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


def _placeholder(name: str) -> list[str]:
    """A command that does nothing and admits it. Replace every call to this."""
    return ["echo", f"PLACEHOLDER {name}: edit adws/adw_modules/quality.py and "
                    f"replace this echo with the real {name} command"]


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
                        stderr = f"\nTimed out: exceeded the time limit of {spec.timeout_seconds}s."
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


def test(run) -> QualityCheckResult:
    """Run the project's test suite. The highest-value block to wire up first.

    aifactory: with ``run.test_slots`` (a ``slots.TestSlots``) the command first waits
    for a machine-wide slot; the wait is traced (``test_slot`` events) and is not part
    of the time limit, which starts when the command does.
    """
    slots = getattr(run, "test_slots", None)
    if slots is None:
        return _test(run)

    def waiting(wait) -> None:
        _slot_event(run, {"state": "waiting", "ahead": wait.ahead, "holding": wait.holding,
                          "queued_before": wait.queued_before, "slots": wait.slots})
        run.console.note(f"test: waiting for a test slot ({wait.ahead} run(s) ahead, "
                         f"{wait.slots} slot(s))")

    with slots.hold(waiting) as lease:
        _slot_event(run, {"state": "acquired", "slot": lease.slot, "slots": slots.slots,
                          "waited_seconds": round(lease.waited_seconds, 3)})
        return _test(run)


def _test(run) -> QualityCheckResult:  # aifactory: the command itself, inside a slot
    return _run(QualityCheckSpec(
        name="test",
        area="backend",
        operation="build",
        # aifactory 2.9: a task run sets run.test_argv (task `test`, index.md `test`,
        # test_command); without it the step keeps the old default.
        argv=list(getattr(run, "test_argv", None) or ["just", "test"]),
        # aifactory: run.test_timeout (task, index.md, config.yaml), else 600 s.
        timeout_seconds=getattr(run, "test_timeout", None) or DEFAULT_TEST_TIMEOUT,
    ), run)


def lint(run) -> QualityCheckResult:
    return _run(QualityCheckSpec(
        name="lint",
        area="backend",
        operation="lint",
        argv=_placeholder("lint"),        # e.g. ["bun", "x", "oxlint@1.36.0", "src"]
    ), run)


def typecheck(run) -> QualityCheckResult:
    return _run(QualityCheckSpec(
        name="typecheck",
        area="backend",
        operation="typecheck",
        argv=["just", "typecheck"],       # or e.g. ["bun", "x", "tsc", "--noEmit"]
    ), run)


def build(run) -> QualityCheckResult:
    output_dir = _check_dir(run, "build") / "bundle"
    return _run(QualityCheckSpec(
        name="build",
        area="backend",
        operation="build",
        argv=["just", "build"],           # or e.g. ["bun", "build", "src/index.ts", "--outdir", str(output_dir)]
    ), run)


def run_tests(run) -> QualityResult:
    """The test suite alone, as a QualityResult — the deterministic test phase.

    This is what replaces a `tester` agent once the command is written down. An
    agent rediscovering the runner on every run costs a fortune to learn what a
    subprocess already knows; the repair loop is unchanged, because a failure
    still reaches the builder through `as_envelope` below.
    """
    # aifactory 2.15: the HAIFA legacy recipe uses the same executor in-process,
    # preserving policy evidence and holding only one test slot for the entire plan.
    if (getattr(run, "test_argv", None) == ["just", "check-scoped"] and
            (Path(run.repo_root) / "aifactory/tests/select_checks.py").is_file()):
        from aifactory.testing.executor import execute
        return execute(run, ["uv", "run", "--project", "aifactory", "python",
                             "aifactory/tests/select_checks.py"], ["just", "check"], True,
                       warn_full_check=True)
    check = test(run)
    failures = ([] if check.passed else
                [f"{check.name}: `{check.command}` exited {check.returncode}\n"
                 f"{check.output_tail}".rstrip()])
    return QualityResult(passed=check.passed, checks=[check], failures=failures,
                         artifacts=[check.output_artifact])


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


def run_quality(run) -> QualityResult:
    """Run every block and collect ALL failures — one pass tells you everything.

    Ordering contract for the caller: a failing block does NOT fail the phase.
    The runner did its job; the CODE is what failed. Hand this result to the
    builder and let the bounded repair loop decide the run's fate.
    """
    blocks: list[Callable] = [
        test,
        lint,
        typecheck,
        build,
    ]
    checks = [block(run) for block in blocks]
    # A failure is the command, its exit code, and what it actually printed —
    # everything a builder needs to repair without opening a log or being told
    # what the error "means" by a parser that guessed.
    failures = [
        f"{check.name}: `{check.command}` exited {check.returncode}\n{check.output_tail}".rstrip()
        for check in checks if not check.passed
    ]
    return QualityResult(
        passed=not failures,
        checks=checks,
        failures=failures,
        artifacts=[check.output_artifact for check in checks],
    )
