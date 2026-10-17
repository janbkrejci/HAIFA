"""The project's quota chain (``quota_switch``): switch along it and return when a limit is back.

Fake harnesses only: a harness "runs out" when its fake raises ``QuotaExhausted`` (as the
adapters do). No test calls a model.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from run_repo import SPEC, T01, Script, commit_all, fake_env, make_run_repo, ok, write

from aifactory import failure
from aifactory.backlog import Task, load_backlog
from aifactory.config import load_run_config
from aifactory.run import TaskRunStore, run_task
from aifactory.run.fallback import SWITCH_KEY, harness_switches
from aifactory.run.quota_chain import (
    ProjectChain,
    next_harness,
    primary_harness,
    project_chain,
    start_harness,
)
from aifactory.run.store import FAILED, SUCCEEDED

AGENTS = (
    "defaults:\n  harness: codex\n  model: gpt-6.1-sol\n{fallback}"
    "agents:\n  - name: planner\n  - name: builder\n  - name: tester\n  - name: documenter\n"
)
PROJECT = "backlog/M01-core/index.md"


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


def _repo(
    tmp_path: Path, chain: str = "[claude, pi]", back: bool = False, fallback: str = ""
) -> Path:
    repo = make_run_repo(tmp_path / "repo", "codex")
    write(repo, ".factory/agents.yaml", AGENTS.format(fallback=fallback))
    write(
        repo,
        PROJECT,
        "---\nid: M01\ntitle: Core\nworkflow: plan-commit\n"
        f"quota_switch: {chain}\nquota_switch_back: {'true' if back else 'false'}\n---\n\n"
        "Jádro.\n",
    )
    commit_all(repo, "project with a quota chain")
    return repo


def _store(repo: Path) -> TaskRunStore:
    return TaskRunStore(repo / ".factory" / "trace.db")


def _out(harness: str) -> Callable[[Path], None]:
    def effect(wt: Path) -> None:
        raise failure.QuotaExhausted(harness, "You've hit your usage limit")

    return effect


def _plan(wt: Path) -> None:
    write(wt, SPEC, "# spec\n")


def _planned(script: Script, *effects: Callable[[Path], None]) -> None:
    script.on("planner", *effects)
    envelopes = [ok() for _ in effects[:-1]]
    script.add("planner", *envelopes, ok(artifacts=[SPEC], commit_message="Add schema spec"))


def _harnesses(script: Script) -> list[str]:
    return [c.harness for c in script.calls if c.agent == "planner"]


def _iso(when: datetime) -> str:
    return when.isoformat(timespec="milliseconds")


def test_chain_switches_in_order(tmp_path: Path, script: Script) -> None:
    repo = _repo(tmp_path)
    _planned(script, _out("codex"), _out("claude"), _plan)

    result = run_task(repo, T01)

    assert result.run.state == SUCCEEDED, result.run.error
    assert _harnesses(script) == ["codex", "claude", "pi"]
    switches = [r[SWITCH_KEY] for r in result.run.retry_list()]
    assert [(s["from"]["harness"], s["to"]["harness"]) for s in switches] == [
        ("codex", "claude"),
        ("claude", "pi"),
    ]
    assert all("quota_switch" in s["source"] and s["auto"] for s in switches)
    assert result.pr is not None
    lines = [line for line in result.pr.body.splitlines() if "quota_switch" in line]
    assert len(lines) == 2
    assert "codex/gpt-6.1-sol → claude (quota" in lines[0]
    assert "claude/claude-opus-5-5 → pi (quota" in lines[1]
    store = _store(repo)
    try:
        # the project stays on pi; codex and claude are out until their reset time
        assert store.project_position("M01") == "pi"
        assert not store.quota_available("codex")
        assert not store.quota_available("claude")
        assert store.quota_available("pi")
    finally:
        store.close()


def test_whole_chain_exhausted_fails_quota(tmp_path: Path, script: Script) -> None:
    repo = _repo(tmp_path)
    script.on("planner", _out("codex"), _out("claude"), _out("pi"))
    script.add("planner", ok(), ok(), ok())

    result = run_task(repo, T01)

    assert result.run.state == FAILED
    assert result.run.failure_kind == failure.QUOTA
    assert _harnesses(script) == ["codex", "claude", "pi"]
    assert len(result.run.retry_list()) == 2
    assert any("chain of project M01 exhausted" in w for w in result.warnings)


def _set_state(repo: Path, position: str, claude_retry_at: datetime) -> None:
    store = _store(repo)
    try:
        store.set_project_position("M01", position)
        store.mark_quota("claude", "limit", _iso(claude_retry_at))
    finally:
        store.close()


def test_return_when_limit_is_back(tmp_path: Path, script: Script) -> None:
    repo = _repo(tmp_path, back=True)
    _set_state(repo, "pi", datetime.now(UTC) - timedelta(minutes=5))
    _planned(script, _plan)

    result = run_task(repo, T01)

    assert result.run.state == SUCCEEDED, result.run.error
    assert _harnesses(script) == ["claude"]
    start = result.run.harness_start_dict()
    assert start is not None
    assert (start["reason"], start["from"]["harness"], start["to"]["harness"]) == (
        "quota_return",
        "pi",
        "claude",
    )
    assert "harness=claude" in (result.run.note or "")
    assert result.pr is not None
    assert f"běh {result.run.run_id}, start: pi → claude" in result.pr.body
    assert "návrat (limit obnoven)" in result.pr.body
    store = _store(repo)
    try:
        assert store.project_position("M01") == "claude"
        assert store.quota_retry_at("claude") is None  # the run on it succeeded
    finally:
        store.close()


def test_return_to_the_primary_clears_the_position(tmp_path: Path, script: Script) -> None:
    repo = _repo(tmp_path, back=True)
    _set_state(repo, "claude", datetime.now(UTC) + timedelta(hours=2))
    _planned(script, _plan)

    result = run_task(repo, T01)

    assert _harnesses(script) == ["codex"]
    start = result.run.harness_start_dict()
    assert start is not None and start["to"]["harness"] == "codex"
    store = _store(repo)
    try:
        assert store.project_position("M01") is None
    finally:
        store.close()


def test_without_return_stays_on_current(tmp_path: Path, script: Script) -> None:
    repo = _repo(tmp_path, back=False)
    _set_state(repo, "pi", datetime.now(UTC) - timedelta(minutes=5))
    _planned(script, _plan)

    result = run_task(repo, T01)

    assert result.run.state == SUCCEEDED, result.run.error
    assert _harnesses(script) == ["pi"]
    start = result.run.harness_start_dict()
    assert start is not None
    assert (start["reason"], start["from"]["harness"], start["to"]["harness"]) == (
        "quota",
        "codex",
        "pi",
    )
    store = _store(repo)
    try:
        assert store.project_position("M01") == "pi"
    finally:
        store.close()


def test_pr_lists_the_start_switch_before_the_retry_switches(
    tmp_path: Path, script: Script
) -> None:
    repo = _repo(tmp_path, back=False)
    _set_state(repo, "claude", datetime.now(UTC) - timedelta(minutes=5))
    _planned(script, _out("claude"), _plan)

    result = run_task(repo, T01)

    assert result.run.state == SUCCEEDED, result.run.error
    assert _harnesses(script) == ["claude", "pi"]
    lines = harness_switches([result.run])
    run_id = result.run.run_id
    assert len(lines) == 2
    assert lines[0].startswith(f"běh {run_id}, start: codex → claude (quota")
    assert lines[1].startswith(f"běh {run_id}, pokus 2: claude")
    assert "→ pi (quota" in lines[1]
    assert result.pr is not None
    body = result.pr.body
    assert body.index(lines[0]) < body.index(lines[1])


def test_return_waits_while_quota_still_out(tmp_path: Path, script: Script) -> None:
    repo = _repo(tmp_path, back=True)
    _set_state(repo, "pi", datetime.now(UTC) + timedelta(hours=2))
    _planned(script, _plan)

    result = run_task(repo, T01)

    assert _harnesses(script) == ["pi"]
    start = result.run.harness_start_dict()
    assert start is not None and start["reason"] == "quota"


def test_project_chain_wins_over_agents_fallback(tmp_path: Path, script: Script) -> None:
    repo = _repo(tmp_path, chain="[claude]", fallback="  fallback:\n    harness: pi\n")
    _planned(script, _out("codex"), _plan)

    result = run_task(repo, T01)

    assert result.run.state == SUCCEEDED, result.run.error
    assert _harnesses(script) == ["codex", "claude"]
    (retry,) = result.run.retry_list()
    assert retry[SWITCH_KEY]["source"] == "projekt M01 (quota_switch)"


def test_skips_harness_without_quota(tmp_path: Path, script: Script) -> None:
    repo = _repo(tmp_path)
    store = _store(repo)
    try:
        store.mark_quota("claude", "limit", _iso(datetime.now(UTC) + timedelta(hours=2)))
    finally:
        store.close()
    _planned(script, _out("codex"), _plan)

    result = run_task(repo, T01)

    assert result.run.state == SUCCEEDED, result.run.error
    assert _harnesses(script) == ["codex", "pi"]


def test_without_a_chain_nothing_changes(tmp_path: Path, script: Script) -> None:
    repo = _repo(tmp_path, chain="[]")
    script.on("planner", _out("codex"))
    script.add("planner", ok())

    result = run_task(repo, T01)

    assert result.run.failure_kind == failure.QUOTA
    assert _harnesses(script) == ["codex"]
    assert result.run.harness_start_dict() is None
    store = _store(repo)
    try:
        assert not store.quota_available("codex")  # recorded even without a switch
    finally:
        store.close()


# ── the chain logic on its own ───────────────────────────────────────────────


def test_project_chain_reads_the_inherited_keys(tmp_path: Path) -> None:
    repo = _repo(tmp_path, chain="[claude_code, codex, pi, pi]", back=True)
    rc = load_run_config(repo)
    task = load_backlog(repo, rc.config.settings).by_id[T01]
    assert isinstance(task, Task)
    assert primary_harness(task, rc) == "codex"
    pc = project_chain(task, "codex")
    assert pc == ProjectChain("M01", ("codex", "claude", "pi"), True)
    assert project_chain(task, None) is None


def test_start_and_next_harness(tmp_path: Path) -> None:
    store = TaskRunStore(tmp_path / "trace.db")
    try:
        pc = ProjectChain("P", ("codex", "claude", "pi"), True)
        now = datetime.now(UTC)
        assert start_harness(store, pc, now).harness == "codex"
        store.set_project_position("P", "unknown")
        assert start_harness(store, pc, now).position is None  # a stale place is dropped
        store.set_project_position("P", "pi")
        start = start_harness(store, pc, now)
        assert (start.harness, start.reason, start.position) == ("claude", "quota_return", "claude")
        store.mark_quota("claude", None, _iso(now + timedelta(minutes=10)))
        start = start_harness(store, pc, now)
        assert (start.harness, start.reason) == ("pi", "quota")
        no_back = ProjectChain("P", pc.chain, False)
        assert start_harness(store, no_back, now + timedelta(hours=1)).harness == "pi"

        assert next_harness(store, pc, "codex", {"codex"}, now) == "pi"  # claude is out
        assert next_harness(store, pc, "codex", {"codex"}, now + timedelta(hours=1)) == "claude"
        assert next_harness(store, pc, "pi", {"pi"}, now) is None
        assert next_harness(store, pc, "other", {"other", "codex"}, now) == "pi"
        store.clear_quota("claude")
        assert store.quota_available("claude", now)
        store.set_project_position("P", None)
        assert store.project_position("P") is None
    finally:
        store.close()
