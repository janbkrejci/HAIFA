"""End to end: `just validate --remote local` passes without network or models.

One test runs `just validate` itself (B1, which needs no other scenario); the other
scenarios run one per test (the longer ones one stage per test) on shared sandboxes
(`local_validation.LocalValidation`), the way the runner runs them. Each sandbox's
tests form one xdist group, so they stay on one worker in file order: R1, R10 -> R3
-> R4 (and R5), R2 -> RESOLVE, and F2.
"""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from local_validation import LocalValidation, checks, result_checks, validation_env

HAIFA_ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.skipif(shutil.which("just") is None, reason="just is not on PATH")

CHAIN_GROUP = pytest.mark.xdist_group(name="validation-chain")
R2_GROUP = pytest.mark.xdist_group(name="validation-r2")
F2_GROUP = pytest.mark.xdist_group(name="validation-f2")


def _assert_passed(out: Path, name: str, data: dict[str, Any]) -> None:
    failed = [c for c in data["checks"] if not c["ok"]]
    assert data["outcome"] == "passed", (name, failed, data["observations"])
    assert data["remote"] == "local"
    evidence = data["evidence"]
    assert isinstance(evidence, dict)
    if name not in ("R5",):
        assert evidence["run_ids"], name
        assert evidence["trace"]["sessions"], name
    trace = evidence["trace"]
    for rel in [trace["db"], *trace["sessions"], *trace["files"]]:
        assert (out / rel).exists(), (name, rel)


@pytest.fixture(scope="module")
def marker(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    with validation_env(tmp_path_factory.mktemp("validation-env")) as path:
        yield path


@pytest.fixture(scope="module")
def chain(tmp_path_factory: pytest.TempPathFactory, marker: Path) -> LocalValidation:
    return LocalValidation(tmp_path_factory.mktemp("validation-chain"))


@pytest.fixture(scope="module")
def r2(tmp_path_factory: pytest.TempPathFactory, marker: Path) -> LocalValidation:
    return LocalValidation(tmp_path_factory.mktemp("validation-r2"))


@pytest.fixture(scope="module")
def f2(tmp_path_factory: pytest.TempPathFactory, marker: Path) -> LocalValidation:
    return LocalValidation(tmp_path_factory.mktemp("validation-f2"))


# ── just validate itself ─────────────────────────────────────────────────────


def test_just_validate_local_b1(tmp_path: Path, marker: Path) -> None:
    results = tmp_path / "results"
    work = tmp_path / "work"
    proc = subprocess.run(
        [
            "just",
            "validate",
            "--remote",
            "local",
            "--only",
            "B1",
            "--results-dir",
            str(results),
            "--workdir",
            str(work),
        ],
        cwd=HAIFA_ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr[-4000:]
    today = datetime.date.today().isoformat()
    runs = list((results / today).glob("local-*"))
    assert len(runs) == 1, runs
    out = runs[0]
    assert not work.exists()  # created by the run, so deleted by it

    b1 = json.loads((out / "B1.json").read_text(encoding="utf-8"))
    _assert_passed(out, "B1", b1)
    assert checks(b1)["write_reverted"] is True
    assert checks(b1)["run_failed"] is True
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["remote"] == "local"
    assert summary["results"] == {"B1": "passed"}
    assert summary["workdir_kept"] is False
    assert (out / "logs").is_dir()
    assert not marker.exists(), marker.read_text(encoding="utf-8")


# ── R1, R10 -> R3 -> R4 (and R5) on one sandbox ────────────────────────────


def _review_round(data: dict[str, Any], name: str) -> None:
    found = checks(data)
    assert found["review_1_rejected"] and found["revise_ran"], name
    assert found["review_2_approved"] and found["review_rule_in_prompt"], name


def _stage(run: LocalValidation, name: str, stage: str, *expected: str) -> Any:
    """Run one stage of a staged scenario; it must go on and pass the `expected` checks."""
    state = run.stage(name, stage)
    found = result_checks(state.res)
    assert run.stage_ok(name, stage), (name, stage, state.res.checks, state.res.observations)
    for check in expected:
        assert found.get(check) is True, (name, check, state.res.checks)
    return state


@CHAIN_GROUP
def test_r1(chain: LocalValidation, marker: Path) -> None:
    data = chain.scenario("R1")
    _assert_passed(chain.out, "R1", data)
    _review_round(data, "R1")
    assert "revise_1" in data["measurements"]["phases"]
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@CHAIN_GROUP
def test_r10(chain: LocalValidation, marker: Path) -> None:
    data = chain.scenario("R10")
    _assert_passed(chain.out, "R10", data)
    assert checks(data)["test_failed_first"] is True
    assert checks(data)["hidden_test_failed_first"] is True
    assert checks(data)["hidden_unseen_by_agents"] is True
    assert data["measurements"]["repair_rounds"] >= 1
    _review_round(data, "R10")
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@CHAIN_GROUP
def test_r3_dependency(chain: LocalValidation, marker: Path) -> None:
    _stage(chain, "R3", "dependency", "dependency_blocks")
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@CHAIN_GROUP
def test_r3_approve(chain: LocalValidation, marker: Path) -> None:
    _stage(chain, "R3", "approve", "approve_ok", "done_in_base_after_approve")
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@CHAIN_GROUP
def test_r3_approve_show(chain: LocalValidation, marker: Path) -> None:
    _stage(chain, "R3", "approve_show", "pr_merged")
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@CHAIN_GROUP
def test_r3_merge_outside(chain: LocalValidation, marker: Path) -> None:
    _stage(
        chain,
        "R3",
        "merge_outside",
        "status_before_sync",
        "sync_pr_opened",
        "base_untouched_by_sync",
        "done_in_base_after_sync",
    )
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@CHAIN_GROUP
def test_r3_first_run(chain: LocalValidation, marker: Path) -> None:
    state = _stage(chain, "R3", "first_run")
    assert state.first is not None and state.first.ok, state.first
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@CHAIN_GROUP
def test_r3_return(chain: LocalValidation, marker: Path) -> None:
    _stage(chain, "R3", "return", "return_new_run", "pr_updated", "base_unchanged_after_return")
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@CHAIN_GROUP
def test_r3_close(chain: LocalValidation, marker: Path) -> None:
    _stage(chain, "R3", "close", "approve_refused")
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@CHAIN_GROUP
def test_r3_close_sync(chain: LocalValidation, marker: Path) -> None:
    _stage(chain, "R3", "close_sync", "sync_ignores_closed", "base_unchanged_after_close")
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@CHAIN_GROUP
def test_r3(chain: LocalValidation, marker: Path) -> None:
    _assert_passed(chain.out, "R3", chain.scenario("R3"))
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@CHAIN_GROUP
def test_r4(chain: LocalValidation, marker: Path) -> None:
    _assert_passed(chain.out, "R4", chain.scenario("R4"))
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@CHAIN_GROUP
def test_r5(chain: LocalValidation, marker: Path) -> None:
    # R5 needs no other scenario; it runs after R4 on the same sandbox, as in the runner
    _assert_passed(chain.out, "R5", chain.scenario("R5"))
    assert not marker.exists(), marker.read_text(encoding="utf-8")


# ── R2 -> RESOLVE on their own sandbox ──────────────────────────────────────


@R2_GROUP
def test_r2_runs(r2: LocalValidation, marker: Path) -> None:
    state = _stage(
        r2,
        "R2",
        "runs",
        "both_runs_ok",
        "runs_overlapped",
        "both_prs_opened",
        "distinct_worktrees",
        "shared_file_touched",
    )
    assert state.res.measurements["overlap_s"] > 0
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@R2_GROUP
def test_r2(r2: LocalValidation, marker: Path) -> None:
    data = r2.scenario("R2")
    _assert_passed(r2.out, "R2", data)
    assert data["measurements"]["overlap_s"] > 0
    assert checks(data)["first_merged"] is True
    assert checks(data)["second_reports_conflict"] is True
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@R2_GROUP
def test_resolve_run(r2: LocalValidation, marker: Path) -> None:
    _stage(r2, "RESOLVE", "resolve", "resolve_ok", "resolve_phase_ran", "no_conflict_markers")
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@R2_GROUP
def test_resolve(r2: LocalValidation, marker: Path) -> None:
    data = r2.scenario("RESOLVE")
    _assert_passed(r2.out, "RESOLVE", data)
    assert checks(data)["both_prs_merged"] is True
    assert checks(data)["resolve_phase_ran"] is True
    assert checks(data)["second_merged"] is True
    assert checks(data)["base_has_both"] is True
    assert not marker.exists(), marker.read_text(encoding="utf-8")


# ── F2, stage by stage ───────────────────────────────────────────────────────


@F2_GROUP
def test_f2_backlog_start(f2: LocalValidation, marker: Path) -> None:
    state = _stage(f2, "F2", "backlog_start")
    assert [task for task, _ in state.adds] == ["M03-S01-T01", "M03-S01-T02"]
    assert all(cmd.ok for _, cmd in state.adds), [cmd.brief() for _, cmd in state.adds]
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@F2_GROUP
def test_f2_backlog_add(f2: LocalValidation, marker: Path) -> None:
    state = _stage(f2, "F2", "backlog_add")
    assert len(state.adds) == 5
    assert all(cmd.ok for _, cmd in state.adds), [cmd.brief() for _, cmd in state.adds]
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@F2_GROUP
def test_f2_backlog(f2: LocalValidation, marker: Path) -> None:
    _stage(f2, "F2", "backlog", "backlog_created")
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@F2_GROUP
def test_f2_parallel(f2: LocalValidation, marker: Path) -> None:
    state = _stage(f2, "F2", "parallel", "parallel_runs_ok", "runs_overlapped")
    assert state.res.measurements["overlap_s"] > 0
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@F2_GROUP
def test_f2_approve_parallel(f2: LocalValidation, marker: Path) -> None:
    _stage(f2, "F2", "approve_parallel", "parallel_approved")
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@F2_GROUP
def test_f2_auto_chain(f2: LocalValidation, marker: Path) -> None:
    state = _stage(f2, "F2", "auto_chain", "auto_chain")
    chain = state.res.measurements["auto_chain"]
    assert chain["tasks"] == ["M04-S01-T02", "M04-S01-T03"]
    assert chain["stop"] == "exhausted"
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@F2_GROUP
def test_f2_last_run(f2: LocalValidation, marker: Path) -> None:
    _stage(f2, "F2", "last_run", "last_run_ok")
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@F2_GROUP
def test_f2_approve_chain(f2: LocalValidation, marker: Path) -> None:
    state = _stage(f2, "F2", "approve_chain")
    assert [task for task, _ in state.approvals] == ["M04-S01-T02", "M04-S01-T03"]
    assert all(cmd.ok for _, cmd in state.approvals), [c.brief() for _, c in state.approvals]
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@F2_GROUP
def test_f2_approve_rest(f2: LocalValidation, marker: Path) -> None:
    _stage(f2, "F2", "approve_rest", "all_approved")
    assert not marker.exists(), marker.read_text(encoding="utf-8")


@F2_GROUP
def test_f2_final(f2: LocalValidation, marker: Path) -> None:
    _stage(
        f2,
        "F2",
        "final",
        "five_prs_merged",
        "all_done_in_base",
        "no_write_outside_worktree",
        "no_leftover_worktrees",
        "backlog_check_ok",
        "base_suite_green",
    )
    data = f2.scenario("F2")
    _assert_passed(f2.out, "F2", data)
    found = checks(data)
    for name in (
        "backlog_created",
        "parallel_runs_ok",
        "runs_overlapped",
        "auto_chain",
        "five_prs_merged",
        "all_done_in_base",
        "no_write_outside_worktree",
        "no_leftover_worktrees",
        "backlog_check_ok",
        "base_suite_green",
    ):
        assert found[name] is True, name
    assert data["measurements"]["overlap_s"] > 0
    chain = data["measurements"]["auto_chain"]
    assert chain["tasks"] == ["M04-S01-T02", "M04-S01-T03"]
    assert chain["stop"] == "exhausted"
    evidence = data["evidence"]
    assert len(evidence["run_ids"]) == 5
    assert [p["state"] for p in evidence["prs"]] == ["merged"] * 5
    assert not marker.exists(), marker.read_text(encoding="utf-8")
