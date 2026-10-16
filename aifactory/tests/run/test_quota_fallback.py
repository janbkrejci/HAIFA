"""Quota fallback: a run whose harness runs out of quota continues once on the fallback.

Fake harnesses only: the codex fake raises ``QuotaExhausted`` (as the adapter does), the
claude fake finishes. No test calls a model.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from run_repo import SPEC, T01, Script, commit_all, fake_env, make_run_repo, ok, write

from aifactory import failure
from aifactory.config import load_run_config
from aifactory.harness.fallback import Fallback
from aifactory.review.prbody import pr_body
from aifactory.run import TaskRunStore, run_task
from aifactory.run.fallback import SWITCH_KEY, configured_fallback, harness_switches
from aifactory.run.retry import retry_run
from aifactory.run.store import FAILED, SUCCEEDED
from cli_json import run_json

AGENTS = (
    "defaults:\n  harness: codex\n  model: gpt-6.1-sol\n{fallback}"
    "agents:\n  - name: planner\n{own}  - name: builder\n  - name: tester\n"
    "  - name: documenter\n"
)
CLAUDE = "  fallback:\n    harness: claude\n    model: claude-opus-5-5\n"


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


def _repo(tmp_path: Path, fallback: str = "", own: str = "") -> Path:
    repo = make_run_repo(tmp_path / "repo", "codex")
    write(repo, ".factory/agents.yaml", AGENTS.format(fallback=fallback, own=own))
    commit_all(repo, "roster with a fallback")
    return repo


def _exhausted(wt: Path) -> None:
    raise failure.QuotaExhausted("codex", "You've hit your usage limit")


def _plan(wt: Path) -> None:
    write(wt, SPEC, "# spec\n")


def _events(repo: Path, run_id: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(repo / ".factory" / "trace.db")
    try:
        rows = conn.execute(
            "SELECT payload_json FROM events WHERE adw_id = ? AND type = 'log'", (run_id,)
        ).fetchall()
    finally:
        conn.close()
    return [json.loads(r[0]) for r in rows]


def test_quota_continues_on_the_fallback_harness(tmp_path: Path, script: Script) -> None:
    repo = _repo(tmp_path, fallback=CLAUDE)
    script.on("planner", _exhausted, _plan)
    script.add("planner", ok(), ok(artifacts=[SPEC], commit_message="Add schema spec"))

    result = run_task(repo, T01)

    assert result.run.state == SUCCEEDED, result.run.error
    planner = [c for c in script.calls if c.agent == "planner"]
    assert [c.harness for c in planner] == ["codex", "claude"]
    assert planner[1].model == "claude-opus-5-5"
    # the fallback agent starts a new session and is told where the run stands
    assert "## Continuation" in planner[1].prompt
    assert "codex/gpt-6.1-sol → claude/claude-opus-5-5" in planner[1].prompt
    assert planner[1].session != planner[0].session
    # the switch is in the run's retries, its events and its note
    (retry,) = result.run.retry_list()
    switch = retry[SWITCH_KEY]
    assert switch["from"]["harness"] == "codex"
    assert switch["to"] == {"harness": "claude", "model": "claude-opus-5-5"}
    assert (switch["reason"], switch["auto"], switch["agent"]) == ("quota", True, "planner")
    assert switch["source"] == "agents.yaml (defaults)"
    logged = [e[SWITCH_KEY] for e in _events(repo, result.run.run_id) if SWITCH_KEY in e]
    assert logged and "codex/gpt-6.1-sol → claude/claude-opus-5-5" in logged[0]
    assert "harness=claude" in (result.run.note or "")
    assert any("quota: switched" in w for w in result.warnings)
    # and in the PR body
    assert result.pr is not None
    assert "### Přepnutí harnessu" in result.pr.body
    assert "codex/gpt-6.1-sol → claude/claude-opus-5-5" in result.pr.body


def test_without_a_fallback_the_run_stays_failed_with_quota(tmp_path: Path, script: Script) -> None:
    repo = _repo(tmp_path)
    script.on("planner", _exhausted)
    script.add("planner", ok())

    result = run_task(repo, T01)

    assert result.run.state == FAILED
    assert result.run.failure_kind == failure.QUOTA
    assert result.run.retry_list() == []
    assert [c.harness for c in script.calls if c.agent == "planner"] == ["codex"]


def test_a_failing_fallback_is_tried_once(tmp_path: Path, script: Script) -> None:
    repo = _repo(tmp_path, fallback=CLAUDE)

    def claude_exhausted(wt: Path) -> None:
        raise failure.QuotaExhausted("claude", "out of extra usage")

    script.on("planner", _exhausted, claude_exhausted)
    script.add("planner", ok(), ok())

    result = run_task(repo, T01)

    assert result.run.state == FAILED
    assert result.run.failure_kind == failure.QUOTA
    assert [c.harness for c in script.calls if c.agent == "planner"] == ["codex", "claude"]
    assert len(result.run.retry_list()) == 1
    # a manual retry now runs on claude, the harness of the switch: it does not switch back
    script.on("planner", claude_exhausted)
    script.add("planner", ok())
    again = retry_run(repo, T01)
    assert again.run.failure_kind == failure.QUOTA
    assert [c.harness for c in script.calls if c.agent == "planner"][-1] == "claude"
    assert len(again.run.retry_list()) == 2
    assert SWITCH_KEY not in again.run.retry_list()[-1]


def test_an_operator_switch_is_recorded(
    tmp_path: Path, script: Script, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    script.on("planner", _exhausted, _plan)
    script.add("planner", ok(), ok(artifacts=[SPEC], commit_message="Add schema spec"))
    failed = run_task(repo, T01)
    assert failed.run.failure_kind == failure.QUOTA
    capsys.readouterr()

    argv = ["task", "retry", T01, "--harness", "pi", "--model", "x/y"]
    code, data = run_json(capsys, [*argv, "--json", "--repo", str(repo)])

    assert code == 0, data
    assert [c.harness for c in script.calls if c.agent == "planner"] == ["codex", "pi"]
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        row = store.get(failed.run.run_id)
        assert row is not None and row.state == SUCCEEDED
        switch = row.retry_list()[-1][SWITCH_KEY]
        lines = harness_switches(store.runs_on_branch(row.branch))
    finally:
        store.close()
    assert switch["auto"] is False and switch["to"]["harness"] == "pi"
    assert lines == [
        f"běh {row.run_id}, pokus 2: codex/gpt-6.1-sol → pi/x/y (quota, operátor, agent planner)"
    ]


def test_local_fallback_wins_over_agents_yaml(tmp_path: Path, script: Script) -> None:
    own = "    fallback: {harness: pi, model: a/b}\n"
    repo = _repo(tmp_path, fallback=CLAUDE, own=own)
    rc = load_run_config(repo)
    assert configured_fallback(rc, "planner") == (
        Fallback(harness="pi", model="a/b"),
        "agents.yaml (agent)",
    )
    assert configured_fallback(rc, "builder") == (
        Fallback(harness="claude", model="claude-opus-5-5"),
        "agents.yaml (defaults)",
    )
    write(repo, ".factory/local.yaml", "fallback:\n  harness: claude_code\n")
    rc = load_run_config(repo)
    assert configured_fallback(rc, "planner") == (Fallback(harness="claude"), "local.yaml")


def test_pr_body_lists_switches() -> None:
    from types import SimpleNamespace

    task = SimpleNamespace(id=T01, title="Schema")
    body = pr_body(task, [], None, Path("/nowhere.db"), "b", switches=["a → b (quota)"])  # type: ignore[arg-type]
    assert "### Přepnutí harnessu\n\n- a → b (quota)" in body
