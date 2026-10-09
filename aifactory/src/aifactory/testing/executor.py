"""Select cheaply, validate conservatively, execute through the quality runner."""

from __future__ import annotations

import argparse
import contextlib
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

from aifactory import oscompat
from aifactory.engine import quality
from aifactory.engine.data_types import QualityCheckSpec, QualityResult
from aifactory.engine.utils import operator_env
from aifactory.testing.context import capture, docs_only, git
from aifactory.testing.model import Check, Evidence, Plan


@contextlib.contextmanager
def full_environment(enabled: bool) -> Any:
    saved = os.environ.get("HAIFA_TEST_TIER")
    try:
        if enabled:
            os.environ["HAIFA_TEST_TIER"] = "full"
        yield
    finally:
        if saved is None:
            os.environ.pop("HAIFA_TEST_TIER", None)
        else:
            os.environ["HAIFA_TEST_TIER"] = saved


@contextlib.contextmanager
def pytest_environment(enabled: bool) -> Any:
    """Fresh basetemp for checks, with deletion detached from the test budget."""
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


def full_check_hint(run: Any) -> None:
    """The same age reminder for CLI and in-process HAIFA workflow checks."""
    root = Path(run.repo_root)
    try:
        state = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
        stamp = state / "haifa/full-check-green"
        count = int(git(root, "rev-list", "--count", f"{stamp.read_text().strip()}..main"))
    except (OSError, ValueError, subprocess.SubprocessError):
        count = 16
    if count > 15:
        run.console.note("hint: run just full-check (last full verification is old or unknown)")


def execute(
    run: Any,
    selector: list[str],
    full_argv: list[str] | None = None,
    allow_skip: bool = False,
    defer_to: str | None = None,
    *,
    warn_full_check: bool = False,
) -> QualityResult:
    fallback = full_argv or list(getattr(run, "test_argv", None) or ["just", "test"])
    timeout = getattr(run, "test_timeout", None) or quality.DEFAULT_TEST_TIMEOUT
    forced = os.environ.get("HAIFA_TEST_TIER") == "full" or bool(
        getattr(run, "test_force_full", False)
    )
    output = quality._check_dir(run, "test_plan")
    diagnostic = output / "selector.log"
    diagnostic.write_text("", encoding="utf-8")
    fallback_reason = None
    coverage: Literal["full", "scoped", "none", "deferred", "legacy"] = (
        "full" if full_argv else "legacy"
    )
    try:
        if forced:
            plan = Plan(
                coverage="full",
                reason="forced full verification",
                checks=[Check(name="test", argv=fallback)],
            )
        else:
            ctx = capture(
                Path(run.repo_root),
                getattr(run, "test_baseline", None) or os.environ.get("HAIFA_TEST_BASE"),
                fallback,
                timeout,
                forced,
                defer_to,
            )
            with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
                with subprocess.Popen(
                    selector,
                    cwd=run.repo_root,
                    env=operator_env(),
                    stdin=subprocess.PIPE,
                    stdout=out,
                    stderr=err,
                    start_new_session=True,
                    creationflags=oscompat.NEW_GROUP,
                ) as proc:
                    try:
                        proc.communicate(ctx.model_dump_json().encode(), timeout=min(30, timeout))
                    except subprocess.TimeoutExpired:
                        with contextlib.suppress(ProcessLookupError):
                            oscompat.kill_group(proc.pid, force=True)
                        proc.kill()
                        proc.wait()
                        raise ValueError("selector timed out") from None
                    finally:
                        err.seek(0)
                        diagnostic.write_bytes(err.read(1024 * 1024))
                if proc.returncode:
                    raise ValueError(f"selector exited {proc.returncode}")
                if out.tell() > 1024 * 1024:
                    raise ValueError("selector output exceeds 1 MiB")
                out.seek(0)
                plan = Plan.model_validate_json(out.read())
            if plan.coverage == "none" and not (allow_skip and docs_only(ctx.changed_paths)):
                raise ValueError("skip requires allow_skip and a documentation-only diff")
            if plan.coverage == "deferred" and not defer_to:
                raise ValueError("deferred requires a validated defer_to")
            coverage = plan.coverage
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        fallback_reason = str(exc)
        with diagnostic.open("a", encoding="utf-8") as log:
            log.write(f"\nfallback: {exc}\n")
        plan = Plan(
            coverage="full",
            reason="selector failed; using fallback",
            checks=[Check(name="test", argv=fallback)],
        )
    artifact = output / "plan.json"
    artifact.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    run.console.note(f"test coverage: {coverage} ({plan.reason})")
    checks = []
    budget_failure: str | None = None
    slots = getattr(run, "test_slots", None)
    with (
        full_environment(forced or fallback_reason is not None),
        pytest_environment(bool(plan.checks)),
        (
            slots.hold(lambda wait: quality._slot_event(run, {"state": "waiting"}))
            if slots and plan.checks
            else contextlib.nullcontext()
        ) as lease,
    ):
        if lease is not None:
            quality._slot_event(
                run,
                {
                    "state": "acquired",
                    "slot": lease.slot,
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
                with diagnostic.open("a", encoding="utf-8") as log:
                    log.write(f"\n{budget_failure}\n")
                run.console.note(budget_failure)
                break
            spec = QualityCheckSpec(
                name=check.name,
                area="backend",
                operation="build",
                argv=check.argv,
                timeout_seconds=timeout,
            )
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
    if warn_full_check:
        full_check_hint(run)
    evidence = Evidence(
        coverage=coverage,
        reason=plan.reason,
        executed=len(checks),
        defer_to=defer_to if coverage != "full" else None,
        fallback_reason=fallback_reason,
    )
    return QualityResult(
        passed=not failures,
        checks=checks,
        failures=failures,
        artifacts=[str(artifact), str(diagnostic)] + [c.output_artifact for c in checks],
        test_plan=evidence,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selector-script", required=True)
    parser.add_argument("--fallback", nargs="+", default=["just", "check"])
    parser.add_argument("--allow-docs-skip", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="haifa-pytest-") as tmp:
        run = SimpleNamespace(
            repo_root=Path.cwd(),
            context_handoff_dir=Path(tmp),
            phases=[SimpleNamespace(seq=0, phase_id="cli")],
            adw_id="cli",
            console=SimpleNamespace(note=print),
            tracer=SimpleNamespace(event=lambda event: None),
        )
        result = execute(
            run,
            ["uv", "run", "--project", "aifactory", "python", args.selector_script],
            args.fallback,
            args.allow_docs_skip,
            warn_full_check=True,
        )
        for check in result.checks:
            print(Path(check.output_artifact).read_text())
        return next(
            (c.returncode for c in result.checks if not c.passed), 0 if result.passed else 124
        )


if __name__ == "__main__":
    raise SystemExit(main())
