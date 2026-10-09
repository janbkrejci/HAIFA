"""Fakes for driving the ported sssf engine without a model or a real coding-agent CLI.

The ``engine_env`` fixture runs the engine against a temp repo and a fake harness.
"""

from __future__ import annotations

import json
import signal
import sqlite3
import subprocess
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

import repo_templates
from aifactory.engine import agent_cc, agent_pi, agents, session
from aifactory.engine.data_types import (
    AgentCall,
    AgentResult,
    EnvelopeBase,
    GenericOutput,
    PhaseParams,
    SSSFConfig,
)
from aifactory.engine.runner import Run

FAKE_CHILD_PID = 424242


def ok(**fields: Any) -> dict[str, Any]:
    """A valid success envelope, with any extra or overriding fields."""
    return {"status": "success", "summary": "done", **fields}


@dataclass(frozen=True)
class Call:
    agent: str
    session_id: str
    prompt: str
    cwd: str


@dataclass
class Script:
    """Raw response texts each agent returns, in order, and every call made."""

    queue: dict[str, list[str]] = field(default_factory=dict)
    effects: dict[str, list[Callable[[Path], object]]] = field(default_factory=dict)
    calls: list[Call] = field(default_factory=list)

    def add(self, agent: str, *texts: str) -> None:
        self.queue.setdefault(agent, []).extend(texts)

    def add_ok(self, agent: str, **fields: Any) -> None:
        self.add(agent, json.dumps(ok(**fields)))

    def on(self, agent: str, *effects: Callable[[Path], object]) -> None:
        """What the agent does to its working directory, one effect per call, in order."""
        self.effects.setdefault(agent, []).extend(effects)


class _Tracker:
    def observe(self, event: dict[str, Any]) -> None:
        return None


class FakeHarness:
    """Stands in for a harness module in ``agents.INTERFACES``."""

    ToolCallTracker = _Tracker

    def __init__(self, script: Script) -> None:
        self.script = script
        self.pid = FAKE_CHILD_PID
        self.during: Callable[[], None] | None = None

    def resolve_model(self, pattern: str) -> tuple[str, str]:
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
    ) -> AgentResult:
        agent = Path(request.session_dir).parent.name
        self.script.calls.append(
            Call(agent, str(request.session_id), str(request.prompt), str(request.cwd))
        )
        queue = self.script.queue.get(agent) or []
        if not queue:
            raise AssertionError(f"no scripted response left for {agent!r}")
        text = queue.pop(0)
        if on_spawn is not None:
            on_spawn(self.pid)
        effects = self.script.effects.get(agent) or []
        if effects:
            effects.pop(0)(Path(request.cwd))
        if self.during is not None:
            self.during()
        if on_exit is not None:
            on_exit(self.pid)
        return AgentResult(text=text, returncode=0, session_id=request.session_id)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def build_repo(repo: Path) -> None:
    """A git repo with one commit: ``README.md`` and ``protected.md``."""
    repo_templates.build(repo, "engine", _build_repo)


def _build_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "tester@example.com")
    _git(repo, "config", "user.name", "tester")
    (repo / "README.md").write_text("readme\n", encoding="utf-8", newline="\n")
    (repo / "protected.md").write_text("protected\n", encoding="utf-8", newline="\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")


@dataclass
class EngineEnv:
    cfg: SSSFConfig
    script: Script
    fake: FakeHarness
    repo: Path
    data_dir: Path
    db_path: Path


def start(env: EngineEnv, adw_id: str = "t0000001") -> Run:
    run = session.ensure(env.cfg, adw_id)
    assert isinstance(run, Run)
    return run


def rows(db: Path, sql: str, *args: object) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(db)
    try:
        return list(conn.execute(sql, args).fetchall())
    finally:
        conn.close()


def agent_phase(
    run: Run,
    owner: str,
    *,
    retries: int = 0,
    gates: Sequence[Callable[..., Any]] = (),
    output_type: type[EnvelopeBase] = GenericOutput,
    prompt: str = "do it",
) -> EnvelopeBase:
    """Open one agent phase owned by ``owner`` and make its single agent call."""
    params = PhaseParams(
        name=owner,
        kind="agent",
        owner=owner,
        description=f"Run the {owner} agent for the test",
        retries=retries,
    )
    with run.phase(params) as ph:
        envelope = ph.call(AgentCall(output_type=output_type, prompt=prompt, gates=list(gates)))
    assert isinstance(envelope, EnvelopeBase)
    return envelope


def event_names(db: Path, adw_id: str, kind: str) -> list[str]:
    return [str(r[0]) for r in rows(db, _EVENTS_BY_TYPE, adw_id, kind)]


def _is_console_line(kind: str, payload: dict[str, Any]) -> bool:
    """The console mirrors every printed line into ``events`` as a ``log``."""
    return kind == "log" and set(payload) == {"message", "level"}


def events_of(
    db: Path, phase_id: str, *, console: bool = False
) -> list[tuple[str, str, dict[str, Any]]]:
    """``(type, name, payload)`` for every event of a phase, in insertion order.

    Console mirror lines are left out unless ``console`` is true.
    """
    found = rows(
        db,
        "SELECT type, name, payload_json FROM events WHERE phase_id=? ORDER BY rowid",
        phase_id,
    )
    events = [(str(t), str(n), json.loads(p)) for t, n, p in found]
    return [e for e in events if console or not _is_console_line(e[0], e[2])]


def types_of(events: Iterable[tuple[str, str, dict[str, Any]]]) -> list[str]:
    return [t for t, _, _ in events]


_EVENTS_BY_TYPE = "SELECT name FROM events WHERE adw_id=? AND type=? ORDER BY rowid"


def _no_real_harness(name: str) -> Any:
    def run(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"a test reached the real {name!r} harness")

    return run


@pytest.fixture(name="engine_env")
def engine_env_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[EngineEnv]:
    """Import into a test module to get ``engine_env``: the engine against a temp repo."""
    repo = tmp_path / "repo"
    build_repo(repo)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("ENGINEER_NAME", "tester")

    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "system.md").write_text("system\n", encoding="utf-8", newline="\n")
    (prompts / "user.md").write_text("{{prompt}}\n", encoding="utf-8", newline="\n")
    engineering = {"system": str(prompts / "system.md"), "user": str(prompts / "user.md")}

    data_dir = tmp_path / "data"
    db_path = data_dir / "sssf.db"
    agent_writes: dict[str, list[str] | None] = {
        "builder": ["allowed/**"],
        "free": None,
        "keyholder": ["protected.md"],
        "reader": [],
    }
    roster: list[dict[str, Any]] = []
    for name, writes in agent_writes.items():
        entry: dict[str, Any] = {"name": name, "model": "sonnet", "prompt_engineering": engineering}
        if writes is not None:
            entry["writes"] = writes
        roster.append(entry)
    config = {
        "defaults": {
            "data_dir": str(data_dir),
            "protected_files": ["protected.md"],
            "coding_agent": "claude_code",
        },
        "observability": {"db": str(db_path)},
        "agents": roster,
    }
    config_path = tmp_path / "sssf.config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8", newline="\n")
    cfg = agents.load_config(str(config_path))

    script = Script()
    fake = FakeHarness(script)
    monkeypatch.setattr(agent_cc, "run", _no_real_harness("claude_code"))
    monkeypatch.setattr(agent_pi, "run", _no_real_harness("pi"))
    monkeypatch.setitem(agents.INTERFACES, "claude_code", fake)
    monkeypatch.setitem(agents.INTERFACES, "pi", fake)

    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        yield EngineEnv(cfg, script, fake, repo, data_dir, db_path)
    finally:
        for sig, handler in saved.items():
            signal.signal(sig, handler)
