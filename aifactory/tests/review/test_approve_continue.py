"""Operator approval resumes a not-merged chain once; no live services or models."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from aifactory.cli import main
from aifactory.config import load_run_config
from aifactory.providers import CHECKS_NONE, ChecksStatus, PrStatus
from aifactory.providers.local import LocalProvider
from aifactory.review import approve_task
from aifactory.run import continue_after_merge, run_chain
from aifactory.run import task as task_mod
from aifactory.run.store import MERGED_BY_AUTO

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))

from run_repo import Script, commit_all, fake_env, make_run_repo  # noqa: E402,I001
from test_auto_continue import (  # noqa: E402
    CORE,
    OTHER,
    T01,
    T02,
    T03,
    _other_project,
    _store,
    build,
    ids,
    runs_of,
    setup_chain,
)


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    repo = make_run_repo(tmp_path / "repo")
    setup_chain(repo, step_auto=True, t02_depends=True)
    path = repo / CORE / "S01-model/index.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("writes:", "auto_merge: true\nwrites:"),
        encoding="utf-8",
    )
    commit_all(repo, "enable auto-merge without a review phase")
    return repo


def provider_for(repo: Path, monkeypatch: pytest.MonkeyPatch) -> LocalProvider:
    provider = LocalProvider(repo, load_run_config(repo).config.settings)
    monkeypatch.setattr(provider, "checks", Mock(return_value=ChecksStatus(CHECKS_NONE)))
    return provider


def stopped_chain(repo: Path, script: Script, *, auto: bool = False) -> str:
    build(script, "one")
    chain = run_chain(repo, T01, auto=auto)
    assert ids(chain) == [T01]
    assert chain.stop == "not_merged"
    assert chain.runs[0].auto_merge is not None
    assert chain.runs[0].auto_merge.code == "no_review_phase"
    assert chain.chain_id is not None
    return chain.chain_id


@pytest.mark.parametrize("auto", [False, True])
def test_approve_resumes_once_from_merged_base(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch, auto: bool
) -> None:
    if auto:
        path = repo / CORE / "S01-model/index.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace("auto_continue: true", "auto_continue: false"),
            encoding="utf-8",
        )
        commit_all(repo, "only --auto enables continuation")
    _other_project(repo)
    commit_all(repo, "another project stays outside the chain")
    chain_id = stopped_chain(repo, script, auto=auto)
    store = _store(repo)
    try:
        store.set_queue_order([OTHER, T02])
    finally:
        store.close()
    build(script, "two")
    real = task_mod.run_task

    def start(*args: Any, **kwargs: Any) -> task_mod.TaskRunResult:
        # Simulate a competing approval while the continuation is starting.
        assert continue_after_merge(repo, T01) is None
        return real(*args, **kwargs)

    run = Mock(side_effect=start)
    monkeypatch.setattr(task_mod, "run_task", run)
    result = approve_task(repo, T01, provider=provider_for(repo, monkeypatch))
    assert result.chain is not None and ids(result.chain) == [T02]
    assert result.chain.stop == "not_merged"
    second = result.chain.runs[0].run
    assert second.started_by == "auto-continue"
    assert second.base_sha == result.base_sha
    assert result.to_json()["chain"] == result.chain.to_json()
    assert run.call_count == 1 and runs_of(repo, OTHER) == []
    assert continue_after_merge(repo, T01) is None
    store = _store(repo)
    try:
        row = store.get_chain(chain_id)
        assert row is not None and row.continued_at is not None and row.auto == int(auto)
    finally:
        store.close()


@pytest.mark.parametrize("reason", ["failed", "exhausted", "disabled", "running", "off"])
def test_approve_does_not_resume_ineligible_chain(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    chain_id = stopped_chain(repo, script)
    store = _store(repo)
    try:
        if reason == "running":
            store.update_chain(chain_id, state="running")
        elif reason != "off":
            store.update_chain(chain_id, stop=reason)
    finally:
        store.close()
    if reason == "off":
        path = repo / CORE / "S01-model/index.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace("auto_continue: true", "auto_continue: false"),
            encoding="utf-8",
        )
        commit_all(repo, "disable continuation in base")
    run = Mock(side_effect=AssertionError("must not start another task"))
    monkeypatch.setattr(task_mod, "run_task", run)
    result = approve_task(repo, T01, provider=provider_for(repo, monkeypatch))
    assert result.chain is None and result.to_json()["chain"] is None
    run.assert_not_called()


def test_auto_merge_approval_never_resumes(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    stopped_chain(repo, script)
    run = Mock(side_effect=AssertionError("auto-merge chain continues by itself"))
    monkeypatch.setattr(task_mod, "run_task", run)
    result = approve_task(
        repo, T01, merged_by=MERGED_BY_AUTO, provider=provider_for(repo, monkeypatch)
    )
    assert result.chain is None
    run.assert_not_called()


@pytest.mark.parametrize("blocked_by", ["slot", "overlap"])
def test_continuation_respects_slots_and_writes(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch, blocked_by: str
) -> None:
    chain_id = stopped_chain(repo, script)
    store = _store(repo)
    try:
        pr = store.latest_pr(T01)
        assert pr is not None
        store.save_pr(replace(pr, task_id=T03, branch="factory/other", pr_id="other", url="other"))
        if blocked_by == "overlap":
            store.conn.execute(
                "UPDATE task_chains SET max_parallel = 2 WHERE chain_id = ?", (chain_id,)
            )
    finally:
        store.close()
    # Keep the synthetic PR open during approve's cleanup and report its file scope.
    from aifactory.run import queue

    monkeypatch.setattr(queue, "_pr_files_default", lambda _: lambda pr: ["src/app/two.py"])
    provider = provider_for(repo, monkeypatch)
    real_status = provider.status
    monkeypatch.setattr(
        provider, "status", lambda pr: real_status(pr) if pr.id != "other" else PrStatus("open")
    )
    run = Mock(side_effect=AssertionError("occupied tasks must not start"))
    monkeypatch.setattr(task_mod, "run_task", run)
    result = approve_task(repo, T01, provider=provider)
    assert result.chain is not None and result.chain.runs == []
    assert (T02, "no_slot" if blocked_by == "slot" else "writes_overlap") in [
        (skip.task_id, skip.reason) for skip in result.chain.waiting
    ]
    run.assert_not_called()


@pytest.mark.parametrize("as_json", [False, True])
def test_approve_cli_prints_continued_chain(
    repo: Path, script: Script, capsys: pytest.CaptureFixture[str], as_json: bool
) -> None:
    stopped_chain(repo, script)
    build(script, "two")
    args = ["task", "approve", T01, "--repo", str(repo)]
    capsys.readouterr()  # Discard narration from the preparatory chain run.
    assert main([*args, "--json"] if as_json else args) == 0
    out = capsys.readouterr().out
    if as_json:
        data = json.loads(out)
        assert data["ok"] is True
        assert data["data"]["chain"]["runs"][0]["run"]["task_id"] == T02
        assert data["data"]["chain"]["stop"] == "not_merged"
    else:
        assert "merged " in out and T02 in out
        assert "auto-continue: stopped (not_merged)" in out


def test_continuation_claim_is_atomic_across_connections(repo: Path, script: Script) -> None:
    chain_id = stopped_chain(repo, script)

    def claim(_: int) -> bool:
        store = _store(repo)
        try:
            return store.claim_chain_continuation(chain_id)
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, range(2))) == [False, True]


@pytest.mark.parametrize("selection", ["queued", "excluded", "cannot_start"])
def test_approve_uses_queue_preferences_and_skips_unstartable_tasks(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch, selection: str
) -> None:
    if selection == "cannot_start":
        path = repo / CORE / "S01-model" / f"{T02}.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace("status: todo", "status: todo\nwrites: []"),
            encoding="utf-8",
        )
        commit_all(repo, "task without writes")
    stopped_chain(repo, script)
    store = _store(repo)
    try:
        if selection == "queued":
            store.set_queue_order([T03, T02])
        elif selection == "excluded":
            store.set_excluded(T02, True)
    finally:
        store.close()
    build(script, "three")
    result = approve_task(repo, T01, provider=provider_for(repo, monkeypatch))
    assert result.chain is not None and ids(result.chain) == [T03]
    if selection == "cannot_start":
        assert any(s.task_id == T02 and s.reason == "cannot_start" for s in result.chain.waiting)
