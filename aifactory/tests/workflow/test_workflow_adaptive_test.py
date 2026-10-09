"""Real selector and check processes; no live agents or services."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError
from workflow_fakes import workflow, workflow_env_fixture  # noqa: F401

from aifactory.testing.context import capture
from aifactory.testing.executor import execute
from aifactory.testing.model import Plan
from aifactory.workflow import WorkflowError


def repo(tmp_path: Path) -> Any:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "--allow-empty",
            "-qm",
            "initial",
        ],
        check=True,
    )
    base = (
        subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"]).decode().strip()
    )
    return SimpleNamespace(
        repo_root=tmp_path,
        test_baseline=base,
        context_handoff_dir=tmp_path.parent / (tmp_path.name + "-logs"),
        phases=[SimpleNamespace(seq=1, phase_id="test")],
        adw_id="test",
        console=SimpleNamespace(note=lambda msg: None),
        tracer=SimpleNamespace(event=lambda event: None),
        test_timeout=4,
    )


def selector(plan: dict[str, Any]) -> list[str]:
    return [sys.executable, "-c", f"print({json.dumps(plan)!r})"]


def plan(*codes: str, coverage: str = "scoped") -> dict[str, Any]:
    return {
        "version": 1,
        "coverage": coverage,
        "reason": "test policy",
        "checks": [
            {"name": f"check{i}", "argv": [sys.executable, "-c", code]}
            for i, code in enumerate(codes)
        ],
    }


class Slots:
    def __init__(self) -> None:
        self.count = 0

    @contextmanager
    def hold(self, waiting: Any) -> Iterator[None]:
        self.count += 1
        yield


def test_sequential_checks_worktree_and_single_slot(tmp_path: Path) -> None:
    run = repo(tmp_path)
    run.test_slots = Slots()
    result = execute(
        run,
        selector(plan("from pathlib import Path; Path('ran').write_text('yes')", "print('error')")),
    )
    assert result.test_plan is not None
    assert result.passed and result.test_plan.executed == 2
    assert (tmp_path / "ran").read_text() == "yes"
    assert run.test_slots.count == 1


def test_failed_check_stops_without_fallback(tmp_path: Path) -> None:
    run = repo(tmp_path)
    result = execute(
        run,
        selector(plan("raise SystemExit(3)", "raise SystemExit(0)")),
        [sys.executable, "-c", "raise SystemExit(0)"],
    )
    assert not result.passed and len(result.checks) == 1
    assert result.checks[0].returncode == 3
    assert result.test_plan is not None
    assert result.test_plan.fallback_reason is None


@pytest.mark.parametrize(
    "code", ["print('bad json')", "raise SystemExit(2)", "import time; time.sleep(3)"]
)
def test_bad_selector_falls_back(tmp_path: Path, code: str) -> None:
    run = repo(tmp_path)
    run.test_timeout = 1
    result = execute(run, [sys.executable, "-c", code], [sys.executable, "-c", "print('fallback')"])
    assert result.test_plan is not None
    assert result.passed and result.test_plan.coverage == "full"
    assert result.test_plan is not None
    assert result.test_plan.fallback_reason
    assert result.test_plan is not None
    assert result.test_plan.executed == 1


def test_docs_skip_no_slot_and_force_full(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = repo(tmp_path)
    run.test_slots = Slots()
    (tmp_path / "README.md").write_text("docs")
    selected = selector(plan(coverage="none"))
    result = execute(run, selected, allow_skip=True)
    assert result.passed and not result.checks and run.test_slots.count == 0
    monkeypatch.setenv("HAIFA_TEST_TIER", "full")
    result = execute(run, selected, [sys.executable, "-c", "raise SystemExit(0)"], True)
    assert result.test_plan is not None
    assert result.passed and result.test_plan.coverage == "full" and len(result.checks) == 1


def test_code_skip_is_rejected_and_defer_explicit(tmp_path: Path) -> None:
    run = repo(tmp_path)
    (tmp_path / "module.py").write_text("pass")
    fallback = [sys.executable, "-c", "raise SystemExit(0)"]
    result = execute(run, selector(plan(coverage="none")), fallback, True)
    assert result.test_plan is not None
    assert result.test_plan.fallback_reason
    result = execute(run, selector(plan(coverage="deferred")), fallback)
    assert result.test_plan is not None
    assert result.test_plan.fallback_reason
    result = execute(run, selector(plan(coverage="deferred")), fallback, defer_to="TASK-2")
    assert result.test_plan is not None
    assert result.test_plan.coverage == "deferred" and not result.checks
    assert result.test_plan is not None
    assert result.test_plan.defer_to == "TASK-2"


def test_common_timeout(tmp_path: Path) -> None:
    run = repo(tmp_path)
    run.test_timeout = 1
    result = execute(
        run, selector(plan("import time; time.sleep(.6)", "import time; time.sleep(.6)"))
    )
    assert not result.passed and result.checks[-1].returncode == 124


def test_context_includes_committed_staged_untracked_and_rename(tmp_path: Path) -> None:
    run = repo(tmp_path)

    def commit(label: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(tmp_path),
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                "commit",
                "-qm",
                label,
            ],
            check=True,
        )

    (tmp_path / "deleted.py").write_text("delete me")
    commit("base")
    run.test_baseline = (
        subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"]).decode().strip()
    )
    (tmp_path / "old name.py").write_text("old")
    commit("builder")
    (tmp_path / "plan.md").write_text("planner output")
    commit("planner")
    (tmp_path / "old name.py").rename(tmp_path / "new name.py")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    (tmp_path / "new name.py").write_text("unstaged")
    (tmp_path / "deleted.py").unlink()
    (tmp_path / "untracked.py").write_text("new")
    ctx = capture(tmp_path, run.test_baseline, ["test"], 5)
    assert ctx.changed_paths == [
        "deleted.py",
        "new name.py",
        "old name.py",
        "plan.md",
        "untracked.py",
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"checks": []},
        {"coverage": "none"},
        {"extra": 3},
        {"version": 2},
        {"version": True},
        {"checks": [{"name": "x", "argv": []}]},
        {"checks": [{"name": "x", "argv": ["test"], "timeout": True}]},
        {"checks": [{"name": "x", "argv": ["test"]}] * 2},
    ],
)
def test_strict_plan(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Plan.model_validate({**plan("pass"), **change})


@pytest.mark.parametrize(
    "options",
    [
        "{selector: []}",
        "{full_argv: [test]}",
        "{selector: [test], allow_skip: 1}",
        "{selector: [test], defer_to: T}",
    ],
)
def test_parser_rejects_invalid_policy(options: str) -> None:
    with pytest.raises(WorkflowError):
        workflow(f"name: t\ndescription: Verify the current change\nsteps:\n  - test: {options}\n")


def test_retest_reselects_and_failure_reaches_fix(workflow_env: Any) -> None:
    import yaml
    from workflow_fakes import ok

    from aifactory.workflow import run_workflow

    selected = [
        sys.executable,
        "-c",
        """
import json
from pathlib import Path
context = json.load(__import__('sys').stdin)
code = 'raise SystemExit(0)' if Path('fixed.py').exists() else 'raise SystemExit(3)'
print(json.dumps({'version': 1, 'coverage': 'scoped', 'reason': str(context['changed_paths']),
                 'checks': [{'name': 'target',
                             'argv': [__import__('sys').executable, '-c', code]}]}))
""",
    ]
    text = yaml.safe_dump(
        {
            "name": "adaptive",
            "description": "Retest after each repair",
            "steps": [
                {
                    "repeat": {"max": 2, "until": "test.passed"},
                    "steps": [{"test": {"selector": selected}}, "fix"],
                }
            ],
            "accept": "test.passed",
        }
    )
    workflow_env.script.add("builder", ok(summary="fixed", changed_files=["fixed.py"]))
    workflow_env.script.on("builder", lambda root: (root / "fixed.py").write_text("pass"))
    result = run_workflow(workflow(text), "fix it", workflow_env.cfg, repo_root=workflow_env.repo)
    assert result.accepted
    assert result.results["test"]["test_plan"]["executed"] == 1
    assert len(workflow_env.script.calls) == 1
    assert "fixed.py" in result.results["test"]["test_plan"]["reason"]


def test_standalone_deferral_requires_resolver(workflow_env: Any) -> None:
    from aifactory.workflow import run_workflow

    with pytest.raises(WorkflowError, match="invalid_test_deferral"):
        run_workflow(
            workflow("""name: t
description: Verify the change with an aggregate task
steps:
  - test: {selector: [selector], full_argv: [just, check], defer_to: T2}
"""),
            "do it",
            workflow_env.cfg,
        )


def test_pr_discloses_zero_checks() -> None:
    from aifactory.review.prbody import _tests
    from aifactory.workflow.interpreter import WorkflowRun

    result = WorkflowRun(
        0,
        True,
        "t",
        results={
            "test": {
                "passed": True,
                "test_plan": {"coverage": "deferred", "executed": 0, "defer_to": "T2"},
            }
        },
    )
    assert "odloženo na T2 (0 kontrol)" in _tests(result)[0]
    assert "prošly" not in _tests(result)[0]


def test_exhausted_budget_does_not_start_next_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.engine import quality
    from aifactory.testing import executor

    run = repo(tmp_path)
    run.test_timeout = 1
    clock = iter([0.0, 0.25, 1.1])
    monkeypatch.setattr(executor, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    limits: list[float] = []
    original = quality._run

    def observed(spec: Any, running: Any) -> Any:
        limits.append(spec.timeout_seconds)
        return original(spec, running)

    monkeypatch.setattr(quality, "_run", observed)
    result = execute(
        run,
        selector(
            plan("print('first')", "from pathlib import Path; Path('must-not-start').touch()")
        ),
    )
    assert limits == [0.75]
    assert not (tmp_path / "must-not-start").exists()
    assert not result.passed and "shared time limit" in result.failures[0]
    assert result.test_plan is not None and result.test_plan.executed == 1
    assert len(result.checks) == 1 and result.checks[0].passed
    monkeypatch.setattr(executor, "execute", lambda *args, **kwargs: result)
    monkeypatch.setattr(sys, "argv", ["executor", "--selector-script", "unused"])
    assert executor.main() == 124


@pytest.mark.parametrize("coverage", ["scoped", "none", "deferred"])
def test_force_full_overrides_every_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, coverage: str
) -> None:
    run = repo(tmp_path)
    (tmp_path / "README.md").write_text("docs")
    monkeypatch.setenv("HAIFA_TEST_TIER", "full")
    selected = plan("raise SystemExit(9)") if coverage == "scoped" else plan(coverage=coverage)
    result = execute(
        run, selector(selected), [sys.executable, "-c", "print('full')"], True, "AGGREGATE"
    )
    assert result.passed and len(result.checks) == 1
    assert result.test_plan is not None
    assert result.test_plan.coverage == "full" and result.test_plan.defer_to is None
    assert "full" in result.checks[0].output_tail


@pytest.mark.parametrize("problem", ["invalid-baseline", "missing-main", "git-failure"])
def test_context_failure_runs_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, problem: str
) -> None:
    from aifactory.testing import context

    run = repo(tmp_path)
    if problem == "invalid-baseline":
        run.test_baseline = "not-a-commit"
    elif problem == "missing-main":
        run.test_baseline = None
        monkeypatch.delenv("HAIFA_TEST_BASE", raising=False)
    else:

        def broken_git(*args: Any) -> str:
            raise subprocess.CalledProcessError(3, ["git"])

        monkeypatch.setattr(context, "git", broken_git)
    result = execute(
        run,
        [sys.executable, "-c", "from pathlib import Path; Path('selector-ran').touch()"],
        [sys.executable, "-c", "print('fallback')"],
    )
    assert result.passed and result.test_plan is not None
    assert result.test_plan.fallback_reason and result.test_plan.coverage == "full"
    assert not (tmp_path / "selector-ran").exists()
    assert "fallback" in result.checks[0].output_tail


@pytest.mark.parametrize("coverage", ["scoped", "none"])
def test_legacy_workflow_check_reports_full_check_age(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, coverage: str
) -> None:
    from aifactory.engine import quality
    from aifactory.testing import executor

    run = repo(tmp_path)
    script = tmp_path / "aifactory/tests/select_checks.py"
    script.parent.mkdir(parents=True)
    script.write_text("# selector placeholder")
    (tmp_path / ".git/info").mkdir(exist_ok=True)
    (tmp_path / ".git/info/exclude").write_text("aifactory/\n")
    run.test_argv = ["just", "check-scoped"]
    messages: list[str] = []
    run.console = SimpleNamespace(note=messages.append)
    original = executor.execute
    selected = plan("pass") if coverage == "scoped" else plan(coverage="none")

    def local_selector(running: Any, argv: list[str], *args: Any, **kwargs: Any) -> Any:
        return original(running, selector(selected), *args, **kwargs)

    monkeypatch.setattr(executor, "execute", local_selector)
    result = quality.run_tests(run)
    assert result.passed
    assert any("hint: run just full-check" in message for message in messages)
    assert not (tmp_path / ".git/haifa/full-check-green").exists()


@pytest.mark.parametrize("coverage", ["none", "scoped", "deferred"])
def test_pr_and_trace_preserve_policy(tmp_path: Path, coverage: str) -> None:
    import sqlite3

    from aifactory.review.prbody import _tests, run_checks
    from aifactory.workflow.interpreter import WorkflowRun

    metadata = {
        "coverage": coverage,
        "reason": "policy",
        "executed": 1 if coverage == "scoped" else 0,
        "defer_to": None if coverage == "none" else "T2",
    }
    wf = WorkflowRun(0, True, "run", results={"test": {"passed": True, "test_plan": metadata}})
    line = _tests(wf)[0]
    if coverage == "none":
        assert "neprovedeno" in line and "prošly" not in line
    else:
        assert "T2" in line
        assert ("cílené ověření" if coverage == "scoped" else "0 kontrol") in line
    database = tmp_path / "trace.db"
    with sqlite3.connect(database) as db:
        db.executescript("""
CREATE TABLE phases (name TEXT, phase_id TEXT, adw_id TEXT, kind TEXT, seq INTEGER);
CREATE TABLE gate_results (phase_id TEXT, gate TEXT, passed INTEGER, violations_json TEXT,
                          adw_id TEXT, id INTEGER);
CREATE TABLE events (phase_id TEXT, type TEXT, payload_json TEXT, started_at TEXT);
INSERT INTO phases VALUES ('test', 'phase', 'run', 'code', 1);
""")
        db.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?)",
            (
                "phase",
                "log",
                json.dumps({"passed": True, "checks": "0/0", "test_plan": metadata}),
                "now",
            ),
        )
    checks = run_checks(database, "run")
    assert len(checks) == 1 and checks[0].passed
    assert coverage in checks[0].detail
    assert str(metadata["executed"]) in checks[0].detail
    if coverage != "none":
        assert "T2" in checks[0].detail
