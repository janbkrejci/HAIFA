"""Fakes for running YAML workflows without a model: scripted harnesses and code steps."""

from __future__ import annotations

import json
import signal
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

import repo_templates
from aifactory import harness
from aifactory.engine import data_types as dt
from aifactory.engine.role_registry import load_roles
from aifactory.harness.config import SSSFConfig, load_config
from aifactory.workflow import CodeStep, RebuildOutput, Workflow, parse_workflow

AGENTS = ("planner", "builder", "reviewer", "documenter", "scout")
HARNESS_NAMES = ("claude", "codex", "pi")
PREV_START = "PREV<<"
PREV_END = ">>PREV"


@dataclass(frozen=True)
class Call:
    harness: str
    agent: str
    model: str
    thinking: str
    prompt: str
    cwd: str = ""
    system: str = ""

    def previous(self) -> str:
        """The rendered ``{{previous_envelope}}`` exactly as the agent received it."""
        start = self.prompt.index(PREV_START) + len(PREV_START)
        return self.prompt[start : self.prompt.index(PREV_END)]


@dataclass
class Script:
    """Envelopes each agent will return, in order, and every call made."""

    queue: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    calls: list[Call] = field(default_factory=list)
    effects: dict[str, list[Callable[[Path], object]]] = field(default_factory=dict)

    def add(self, agent: str, *envelopes: dict[str, Any]) -> None:
        self.queue.setdefault(agent, []).extend(envelopes)

    def on(self, agent: str, *effects: Callable[[Path], object]) -> None:
        """What the agent does to its working directory, one effect per call, in order."""
        self.effects.setdefault(agent, []).extend(effects)


class _Tracker:
    def observe(self, event: dict[str, Any]) -> None:
        return None


class FakeHarness:
    """Stands in for a harness module in ``agents.INTERFACES``."""

    ToolCallTracker = _Tracker

    def __init__(self, name: str, script: Script) -> None:
        self.name = name
        self.script = script
        self.reject_models = False

    def resolve_model(self, pattern: str) -> tuple[str, str]:
        if self.reject_models:
            raise ValueError(f"{self.name}: no model matches {pattern!r}")
        return ("fake", pattern)

    def context_window(self, *args: Any) -> int:
        return 0

    def run(
        self,
        request: Any,
        on_event: Callable[..., Any] | None = None,
        on_wait: Callable[..., Any] | None = None,
        on_spawn: Callable[..., Any] | None = None,
        on_exit: Callable[..., Any] | None = None,
    ) -> dt.AgentResult:
        agent = Path(request.session_dir).parent.name
        self.script.calls.append(
            Call(
                self.name,
                agent,
                str(request.model),
                str(request.thinking),
                str(request.prompt),
                str(request.cwd or ""),
                str(request.system_prompt or ""),
            )
        )
        queue = self.script.queue.get(agent) or []
        if not queue:
            raise AssertionError(f"no scripted envelope left for {agent!r}")
        envelope = queue.pop(0)
        effects = self.script.effects.get(agent) or []
        if effects:
            effects.pop(0)(Path(request.cwd))
        return dt.AgentResult(
            text=json.dumps(envelope), returncode=0, session_id=request.session_id
        )


class FakeCodeRunner:
    """Deterministic steps with scripted outcomes; nothing touches git or a shell."""

    def __init__(self, test_results: list[bool]) -> None:
        self.test_results = list(test_results)
        self.commits: list[str] = []
        self.commands: list[tuple[str, ...]] = []
        self.rebuilds: list[list[str]] = []

    def _result(self, passed: bool, what: str) -> dt.QualityResult:
        failures = [] if passed else [f"{what}: failed"]
        return dt.QualityResult(passed=passed, checks=[], failures=failures, artifacts=[])

    def test(self, run: Any) -> Any:
        if not self.test_results:
            raise AssertionError("no scripted test result left")
        return self._result(self.test_results.pop(0), "test")

    def quality(self, run: Any) -> Any:
        return self._result(True, "quality")

    def commit(self, run: Any, message: str) -> str:
        self.commits.append(message)
        return "abc1234"

    def changes(self, run: Any, base: str) -> Any:
        ref = dt.BaseRef(ref=base, commit=base, reason="scripted")
        return dt.ChangeSet(base=ref, files=["x.py"], insertions=1)

    def command(self, run: Any, step: CodeStep) -> Any:
        self.commands.append(step.argv)
        return self._result(True, step.key)

    def rebase(self, run: Any) -> Any:
        raise AssertionError("no scripted rebase")

    def rebuild(self, run: Any, files: list[str]) -> Any:
        self.rebuilds.append(list(files))
        return RebuildOutput(status="success", summary="no generated output in conflict")

    def baseline(self) -> str:
        return "0" * 40


def ok(**fields: Any) -> dict[str, Any]:
    """A successful envelope with the given extra fields."""
    return {"status": "success", "summary": "done", **fields}


def workflow(text: str) -> Workflow:
    """A workflow from a YAML string, against the packaged role registry."""
    return parse_workflow(yaml.safe_load(text), load_roles())


def _no_real_harness(name: str) -> Callable[..., Any]:
    def run(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"a test reached the real {name!r} harness")

    return run


def install_fake_harnesses(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Script, dict[str, FakeHarness]]:
    """Register a ``FakeHarness`` for claude, codex and pi (and ``claude_code``)."""
    agents = harness.install()
    script = Script()
    fakes = {name: FakeHarness(name, script) for name in HARNESS_NAMES}
    # Safety net first: any real adapter that still gets reached fails loudly
    # instead of spawning a CLI and spending money on a model. Model resolution
    # (used by the override check) goes to the fake too, so pi needs no catalog.
    for name in HARNESS_NAMES:
        module = harness.load(name)
        monkeypatch.setattr(module, "run", _no_real_harness(name))
        monkeypatch.setattr(module, "resolve_model", fakes[name].resolve_model)
    for name, fake in fakes.items():
        monkeypatch.setitem(agents.INTERFACES, name, fake)
    monkeypatch.setitem(agents.INTERFACES, "claude_code", fakes["claude"])
    return script, fakes


@dataclass
class EngineEnv:
    cfg: SSSFConfig
    agents: Any
    script: Script
    fakes: dict[str, FakeHarness]
    repo: Path


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def build_engine_repo(repo: Path) -> None:
    """The throwaway repo every engine test starts from: one commit with README.md."""
    repo_templates.build(repo, "workflow-engine", _build_engine_repo)


def _build_engine_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("fixture\n", encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")


def make_engine_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[EngineEnv]:
    repo = tmp_path / "repo"
    build_engine_repo(repo)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("ENGINEER_NAME", "tester")

    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "system.md").write_text("system\n", encoding="utf-8", newline="\n")
    (prompts / "user.md").write_text(
        f"{{{{prompt}}}}\n{PREV_START}{{{{previous_envelope}}}}{PREV_END}\n",
        encoding="utf-8",
        newline="\n",
    )
    data = tmp_path / "data"
    roster = [
        {
            "name": name,
            "harness": "claude",
            "model": "sonnet",
            "thinking": "medium",
            "prompt_engineering": {
                "system": str(prompts / "system.md"),
                "user": str(prompts / "user.md"),
            },
        }
        for name in AGENTS
    ]
    config = {
        "defaults": {"data_dir": str(data)},
        "observability": {"db": str(data / "sssf.db")},
        "agents": roster,
    }
    path = tmp_path / "agents.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8", newline="\n")
    cfg = load_config(path)

    agents = harness.install()
    script, fakes = install_fake_harnesses(monkeypatch)

    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        yield EngineEnv(cfg=cfg, agents=agents, script=script, fakes=fakes, repo=repo)
    finally:
        for sig, handler in saved.items():
            signal.signal(sig, handler)


@pytest.fixture(name="workflow_env")
def workflow_env_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[EngineEnv]:
    """Import into a test module (tests/ has no shared conftest) to get ``workflow_env``."""
    yield from make_engine_env(tmp_path, monkeypatch)


# ── a repo with .factory/ for the CLI tests ─────────────────────────────────

FACTORY_AGENTS_YAML = """\
defaults:
  harness: claude
  model: sonnet
agents:
  - name: planner
    model: opus
  - name: builder
"""

FACTORY_FILES = {
    ".factory/config.yaml": "base: main\ntest_command: [pytest, -q]\n",
    ".factory/agents.yaml": FACTORY_AGENTS_YAML,
    ".factory/prompts/planner/system.md": "You are the planner.\n",
    ".factory/prompts/planner/user.md": "Plan this: {{prompt}}\n",
    ".factory/prompts/builder/system.md": "You are the builder.\n",
    ".factory/prompts/builder/user.md": "Build this: {{prompt}}\n",
}


def make_factory_repo(path: Path) -> Path:
    """A git repo whose working tree has a sample ``.factory/`` (planner and builder only)."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    for rel, text in FACTORY_FILES.items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    return path
