"""Rules of the quality check of a backlog proposal (``workflow.propose_check``)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from aifactory.workflow import propose_check as qc
from aifactory.workflow.propose_check import Candidate

DONE = "\n\nHotovo znamená:\n- testy projdou"


def task(
    key: str,
    body: str = "Udělej to.",
    *,
    writes: Sequence[str] = ("src/",),
    depends_on: Sequence[str] = (),
) -> Candidate:
    return Candidate(key=key, body=body + DONE, writes=tuple(writes), depends_on=tuple(depends_on))


@pytest.fixture
def root(tmp_path: Path) -> Path:
    for name in ("src/app/model.py", "src/app/cli.py", "docs/guide.md", "justfile"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")
    return tmp_path


# -- Hotovo znamená --


def test_done_section_required() -> None:
    ok = task("T01")
    missing = Candidate(key="T02", body="Bez kritérií.")
    findings = qc.check_done([ok, missing])
    assert [(f.rule, f.task) for f in findings] == [(qc.MISSING_DONE, "T02")]
    assert findings[0].blocking


def test_done_section_is_case_insensitive() -> None:
    assert qc.check_done([Candidate(key="T01", body="x\n\nHOTOVO ZNAMENÁ:\n- y")]) == []


# -- cycles --


def test_cycle_found_once() -> None:
    tasks = [
        task("T01", depends_on=["T03"]),
        task("T02", depends_on=["T01"]),
        task("T03", depends_on=["T02", "P01-S01-T01"]),
    ]
    findings = qc.check_cycles(tasks)
    assert len(findings) == 1
    assert findings[0].rule == qc.CYCLE and findings[0].blocking
    assert "T01 -> T03 -> T02 -> T01" in findings[0].message


def test_no_cycle_in_a_chain_or_on_outside_ids() -> None:
    tasks = [
        task("T01", depends_on=["P01-S01-T01"]),
        task("T02", depends_on=["T01"]),
        task("T03", depends_on=["T01", "T02"]),
    ]
    assert qc.check_cycles(tasks) == []


def test_self_reference_is_a_cycle() -> None:
    findings = qc.check_cycles([task("T01", depends_on=["T01"])])
    assert [f.rule for f in findings] == [qc.CYCLE]


# -- writes cover the named files --


def test_named_paths(root: Path) -> None:
    body = (
        "Uprav `src/app/model.py`, přidej `src/app/export.py` a `justfile:`. "
        "Spusť `just test`, `--apply`, `https://x.y/z`, `src/*.py`, `<id>`, "
        "`backlog/edit` a `nowhere/new.py`. Viz `docs/`."
    )
    assert qc.named_paths(body, root) == [
        "src/app/model.py",
        "src/app/export.py",
        "justfile",
        "docs/",
    ]


def test_coverage_reports_unnamed_files(root: Path) -> None:
    body = "Uprav `src/app/model.py`, `docs/guide.md` a `justfile`."
    covered = task("T01", body, writes=["src/app/", "docs/*.md", "justfile"])
    partial = task("T02", body, writes=["src/app/model.py"])
    empty = task("T03", body, writes=[])
    findings = qc.check_coverage([covered, partial, empty], root)
    assert [(f.rule, f.task) for f in findings] == [
        (qc.WRITES_UNCOVERED, "T02"),
        (qc.WRITES_UNCOVERED, "T03"),
    ]
    assert "docs/guide.md, justfile" in findings[0].message
    assert "src/app/model.py" not in findings[0].message
    assert not findings[0].blocking


def test_coverage_of_a_directory_and_closed_paths(root: Path) -> None:
    (root / ".factory").mkdir()
    body = "Práce v `src/app/`; přepis jde do `.factory/`."
    inside = task("T01", body, writes=["src/app/model.py"])
    assert qc.check_coverage([inside], root, closed=[".factory/"]) == []
    outside = task("T02", body, writes=["docs/"])
    findings = qc.check_coverage([outside], root, closed=[".factory/"])
    assert len(findings) == 1 and "src/app/" in findings[0].message
    assert ".factory/" not in findings[0].message


# -- writes outside protected_files and the backlog --


def test_closed_writes() -> None:
    closed = [".factory/", "factory/backlog", "adws/adw_*.py"]
    tasks = [
        task("T01", writes=["src/", "**"]),
        task("T02", writes=[".factory/workflows/x.yaml"]),
        task("T03", writes=["factory/backlog/P01/"]),
        task("T04", writes=["factory/"]),
        task("T05", writes=["factory/docs/x.md", "adws/adw_run.py"]),
    ]
    findings = qc.check_closed(tasks, closed)
    assert [(f.rule, f.task) for f in findings] == [
        (qc.WRITES_CLOSED, "T02"),
        (qc.WRITES_CLOSED, "T03"),
        (qc.WRITES_CLOSED, "T04"),
        (qc.WRITES_CLOSED, "T05"),
    ]
    assert "adws/adw_run.py" in findings[-1].message
    assert not findings[0].blocking


# -- no overlap of tasks that can run at the same time --


def test_overlap_of_independent_tasks() -> None:
    tasks = [
        task("T01", writes=["src/app/"]),
        task("T02", writes=["src/app/cli.py"]),
        task("T03", writes=["docs/"]),
    ]
    findings = qc.check_overlap(tasks)
    assert [(f.rule, f.task) for f in findings] == [(qc.WRITES_OVERLAP, "T02")]
    assert "'T01' and 'T02'" in findings[0].message
    assert "src/app/ ~ src/app/cli.py" in findings[0].message
    assert not findings[0].blocking


def test_no_overlap_finding_with_a_dependency_path() -> None:
    tasks = [
        task("T01", writes=["src/"]),
        task("T02", writes=["docs/"], depends_on=["T01"]),
        task("T03", writes=["src/app/"], depends_on=["T02"]),  # transitively after T01
        task("T04", writes=["src/application/"]),  # no common path with src/app
    ]
    findings = qc.check_overlap(tasks)
    assert [(f.task, f.message.split("(")[1]) for f in findings] == [
        ("T04", "src/ ~ src/application/); add a dependency or split the writes"),
    ]


def test_check_puts_blocking_findings_first(root: Path) -> None:
    tasks = [
        task("T01", "Uprav `docs/guide.md`.", writes=["src/"]),
        Candidate(key="T02", body="nic", writes=("src/",)),
    ]
    rules = [f.rule for f in qc.check(tasks, root, closed=[".factory/"])]
    assert rules == [qc.MISSING_DONE, qc.WRITES_UNCOVERED, qc.WRITES_OVERLAP]
