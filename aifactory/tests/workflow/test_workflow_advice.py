from __future__ import annotations

import json
import signal
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from advice_fixture import make_repo, output
from aifactory.engine import agents
from aifactory.engine.data_types import AgentResult
from aifactory.harness.check import HarnessStatus
from aifactory.web.backlog import UsageError
from aifactory.workflow.adaptive import WorkflowRecommendationOutput, context, recommend, validate


def test_context_and_committed_catalog(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    (repo / ".factory/workflows/unpublished.yaml").write_text("name: unpublished\nsteps: [plan]")
    ctx = context(
        repo,
        None,
        {
            "step": "P01-S01",
            "title": "Draft",
            "body": "Unsaved body",
            "depends_on": ["P01-S01-T01"],
        },
    )
    assert ctx["draft"]["body"] == "Unsaved body"
    assert ctx["relations"][0]["body"].strip() == "Full task body"
    assert ctx["parents"][0]["title"] == "Step"
    assert ctx["effective"]["writes"] == ["src/"]
    assert "unpublished" not in ctx["catalog"]
    assert ctx["catalog"]["plan"]["steps"] == ["plan"]
    assert validate(repo, WorkflowRecommendationOutput.model_validate(output()), ctx["catalog"])[
        "outline"
    ]
    assert validate(
        repo,
        WorkflowRecommendationOutput.model_validate(output("research", new=True)),
        ctx["catalog"],
    )


@pytest.mark.parametrize(
    "change",
    [
        {"workflow_name": "../escape"},
        {"workflow_name": "Unknown"},
        {"workflow_name": "missing"},
        {"reason": " "},
        {"status": "fail"},
        {"decision": "new", "workflow_yaml": "name: plan\nsteps: [plan]"},
        {
            "decision": "new",
            "workflow_name": "research",
            "workflow_yaml": "name: different\nsteps: [plan]",
        },
        {"decision": "new", "workflow_name": "research", "workflow_yaml": "[invalid"},
        {
            "decision": "new",
            "workflow_name": "research",
            "workflow_yaml": "name: research\nsteps: [unknown]",
        },
        {
            "decision": "new",
            "workflow_name": "research",
            "workflow_yaml": "name: research\nsteps:\n - plan:\n     agent: unknown",
        },
        {
            "decision": "new",
            "workflow_name": "research",
            "workflow_yaml": "name: research\nsteps:\n - repeat:\n     steps: [plan]",
        },
        {"unexpected": "field"},
        {
            "decision": "new",
            "workflow_name": "research",
            "workflow_yaml": "name: research\nsteps: [plan]\naccept: __import__('os')\n",
        },
    ],
)
def test_invalid_output_never_writes(tmp_path: Path, change: dict[str, Any]) -> None:
    repo = make_repo(tmp_path / "repo")
    ctx = context(repo, "P01-S01-T01", {})
    import yaml

    from aifactory.workflow.model import WorkflowError

    with pytest.raises((UsageError, ValidationError, WorkflowError, yaml.YAMLError)):
        validate(
            repo,
            WorkflowRecommendationOutput.model_validate({**output(), **change}),
            ctx["catalog"],
        )
    assert not (repo / ".factory/workflows/research.yaml").exists()


def test_engine_lifecycle_in_thread(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path / "repo")
    seen: list[Any] = []
    module = agents.INTERFACES["claude"]
    monkeypatch.setattr(
        "aifactory.workflow.adaptive.check_harness",
        lambda name: HarnessStatus(name, "fake", "fake", "1"),
    )

    def run(request: Any, **kwargs: Any) -> AgentResult:
        seen.append(request)
        assert Path(request.cwd) != repo
        assert "Original task" not in request.prompt
        assert "workflow_yaml" in request.system_prompt
        assert json.loads(request.prompt)["draft"]["title"] == "First"
        return AgentResult(text=json.dumps(output()), returncode=0)

    monkeypatch.setattr(module, "run", run)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("process-wide mutation")

    monkeypatch.setattr(signal, "signal", forbidden)
    monkeypatch.setattr("os.chdir", forbidden)
    with ThreadPoolExecutor(1) as pool:
        result = pool.submit(
            recommend, repo, context(repo, "P01-S01-T01", {}), "test-advice", threading.Event()
        ).result()
    assert result["workflow_name"] == "plan"
    import sqlite3

    with sqlite3.connect(repo / ".factory/data/workflow-advice/test-advice/trace.db") as db:
        status, ended = db.execute("SELECT status, ended_at FROM sessions").fetchone()
        assert status == "success"
        assert ended
    assert seen[0].model == "sonnet"
    assert not Path(seen[0].cwd).exists()
    assert (repo / "backlog/P01/S01/P01-S01-T01-first.md").read_text().endswith("Full task body\n")


def test_environment_is_scoped_to_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    from aifactory.engine.utils import agent_environment, env_flag, operator_env

    before = dict(os.environ)
    barrier = threading.Barrier(2)

    def worker(identifier: str) -> str:
        with agent_environment({"HAIFA_RUN_ID": identifier, "PI_SAFE_MODE": "1"}):
            barrier.wait(timeout=5)
            assert env_flag("PI_SAFE_MODE")
            return operator_env()["HAIFA_RUN_ID"]

    with ThreadPoolExecutor(2) as pool:
        one = pool.submit(worker, "one")
        two = pool.submit(worker, "two")
        assert (one.result(), two.result()) == ("one", "two")
    assert dict(os.environ) == before
    assert operator_env().get("HAIFA_RUN_ID") == before.get("HAIFA_RUN_ID")


def test_domain_module_imports_without_dashboard_initialization(tmp_path: Path) -> None:
    import subprocess
    import sys

    done = subprocess.run(
        [
            sys.executable,
            "-c",
            "from aifactory.workflow.adaptive import WorkflowRecommendationOutput",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr


@pytest.mark.parametrize(
    "failure", ["exception", "cancel-before", "cancel-after", "invalid", "write"]
)
def test_failed_recommendation_finishes_trace_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    import sqlite3

    from aifactory.engine.permissions import PermissionBreach

    repo = make_repo(tmp_path / "repo")
    cancelled = threading.Event()
    isolated: list[Path] = []
    task_path = repo / "backlog/P01/S01/P01-S01-T01-first.md"
    original = task_path.read_bytes()
    monkeypatch.setattr(
        "aifactory.workflow.adaptive.check_harness",
        lambda name: HarnessStatus(name, "fake", "fake", "1"),
    )

    def run(request: Any, **kwargs: Any) -> AgentResult:
        isolated.append(Path(request.cwd))
        if failure == "exception":
            raise RuntimeError("injected harness exception")
        if failure == "cancel-after":
            cancelled.set()
        if failure == "write":
            (Path(request.cwd) / "forbidden.txt").write_text("unapproved")
            task_path.write_text("unapproved main write")
        result = {**output(), "workflow_name": "missing"} if failure == "invalid" else output()
        return AgentResult(text=json.dumps(result), returncode=0)

    monkeypatch.setattr(agents.INTERFACES["claude"], "run", run)
    if failure == "cancel-before":
        cancelled.set()
    expected = (
        PermissionBreach
        if failure == "write"
        else RuntimeError
        if failure == "exception"
        else UsageError
    )
    with pytest.raises(expected):
        recommend(repo, context(repo, "P01-S01-T01", {}), "failed-advice", cancelled)
    with sqlite3.connect(repo / ".factory/data/workflow-advice/failed-advice/trace.db") as db:
        status, ended = db.execute("SELECT status, ended_at FROM sessions").fetchone()
        assert status == "fail"
        assert ended
    assert all(not path.exists() for path in isolated)
    assert task_path.read_bytes() == original


def test_missing_planner_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aifactory.config import load_run_config
    from aifactory.workflow import adaptive

    repo = make_repo(tmp_path / "repo")
    ctx = context(repo, "P01-S01-T01", {})
    rc = load_run_config(repo, ctx["commit"])
    rc.config.roles.roles.pop("plan")
    monkeypatch.setattr(adaptive, "load_run_config", lambda *args: rc)
    with pytest.raises(UsageError, match="plan role is missing"):
        recommend(repo, ctx, "missing-planner", threading.Event())


def test_missing_planner_agent_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aifactory.config import load_run_config
    from aifactory.run.task import prepare_cfg

    repo = make_repo(tmp_path / "repo")
    ctx = context(repo, "P01-S01-T01", {})
    cfg = prepare_cfg(repo, load_run_config(repo), repo / ".factory/data/test-prompts")
    cfg.agents = [agent for agent in cfg.agents if agent.name != "planner"]
    monkeypatch.setattr("aifactory.workflow.adaptive.prepare_cfg", lambda *args: cfg)
    with pytest.raises(UsageError, match="plan agent 'planner' is missing"):
        recommend(repo, ctx, "missing-agent", threading.Event())
