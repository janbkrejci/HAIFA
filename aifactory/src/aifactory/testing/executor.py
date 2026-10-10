"""Run the checks of a tester agent's plan through the quality runner."""

from __future__ import annotations

import contextlib
import os
import shlex
import subprocess
import sys
import tempfile
import time
from typing import Any

from aifactory import oscompat
from aifactory.engine import quality
from aifactory.engine.data_types import QualityCheckSpec, QualityResult, TestPlanOutput
from aifactory.testing.model import Evidence


@contextlib.contextmanager
def pytest_environment(enabled: bool) -> Any:
    """Fresh pytest basetemp for the checks, with deletion detached from the time limit."""
    if not enabled:
        yield
        return
    directory = tempfile.mkdtemp(prefix="haifa-pytest-")
    saved = os.environ.get("PYTEST_ADDOPTS")
    try:
        os.environ["PYTEST_ADDOPTS"] = (saved or "") + " --basetemp=" + shlex.quote(directory)
        yield
    finally:
        if saved is None:
            os.environ.pop("PYTEST_ADDOPTS", None)
        else:
            os.environ["PYTEST_ADDOPTS"] = saved
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import shutil,sys; shutil.rmtree(sys.argv[1], ignore_errors=True)",
                directory,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            creationflags=oscompat.NEW_GROUP,
        )


def execute(run: Any, plan: TestPlanOutput) -> QualityResult:
    """Run ``plan.checks`` in order under one shared time limit; stop at the first failure.

    The limit is ``run.test_timeout`` (else 600 s); a check's own ``timeout`` can only
    shorten it. With ``run.test_slots`` the checks wait for one machine-wide slot first.
    """
    timeout = getattr(run, "test_timeout", None) or quality.DEFAULT_TEST_TIMEOUT
    output = quality._check_dir(run, "test_plan")
    artifact = output / "plan.json"
    artifact.write_text(
        plan.model_dump_json(indent=2, include={"coverage", "reason", "checks"}), encoding="utf-8"
    )
    run.console.note(f"test coverage: {plan.coverage} ({plan.reason})")
    checks = []
    budget_failure: str | None = None
    slots = getattr(run, "test_slots", None)

    def waiting(wait: Any) -> None:
        quality._slot_event(
            run,
            {
                "state": "waiting",
                "ahead": wait.ahead,
                "holding": wait.holding,
                "queued_before": wait.queued_before,
                "slots": wait.slots,
            },
        )
        run.console.note(
            f"test: waiting for a test slot ({wait.ahead} run(s) ahead, {wait.slots} slot(s))"
        )

    with (
        pytest_environment(bool(plan.checks)),
        slots.hold(waiting) if slots and plan.checks else contextlib.nullcontext() as lease,
    ):
        if lease is not None:
            quality._slot_event(
                run,
                {
                    "state": "acquired",
                    "slot": lease.slot,
                    "slots": getattr(slots, "slots", None),
                    "waited_seconds": round(lease.waited_seconds, 3),
                },
            )
        started = time.monotonic()
        for check in plan.checks:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                budget_failure = (
                    f"test: shared time limit of {timeout}s exhausted before {check.name}; "
                    "command was not started (timeout exit 124)"
                )
                run.console.note(budget_failure)
                break
            spec = QualityCheckSpec(
                name=check.name,
                area="backend",
                operation="build",
                argv=check.argv,
                timeout_seconds=timeout,
            )
            # one shared budget: the remaining time may be fractional
            spec.timeout_seconds = min(check.timeout or timeout, remaining)  # type: ignore[assignment]
            result = quality._run(spec, run)
            checks.append(result)
            if not result.passed:
                break
    failures = [
        f"{c.name}: `{c.command}` exited {c.returncode}\n{c.output_tail}"
        for c in checks
        if not c.passed
    ]
    if budget_failure is not None:
        failures.append(budget_failure)
    evidence = Evidence(
        coverage=plan.coverage,
        reason=plan.reason,
        executed=len(checks),
        commands=[shlex.join(c.argv) for c in plan.checks],
        dropped=list(plan.dropped),
    )
    return QualityResult(
        passed=not failures,
        checks=checks,
        failures=failures,
        artifacts=[str(artifact)] + [c.output_artifact for c in checks],
        test_plan=evidence,
    )
