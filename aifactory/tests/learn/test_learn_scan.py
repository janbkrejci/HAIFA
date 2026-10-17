"""``factory learn scan`` and ``reject`` over a fixture trace DB, with a fake harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from advice_fixture import make_repo
from aifactory.cli import main
from aifactory.engine import agents
from aifactory.engine.data_types import AgentResult
from aifactory.engine.tracer import Tracer
from aifactory.harness.check import HarnessStatus
from aifactory.learn.collect import collect
from aifactory.learn.store import REJECTED, LessonStore
from aifactory.run.store import TaskRunStore

TESTS_RULE = "Add a test for every new CLI command."


def _run(db: Any, run_id: str, task_id: str) -> None:
    db.execute(
        "INSERT INTO task_runs (run_id, task_id, branch, worktree, base, base_sha, state, "
        "started_at) VALUES (?,?,?,?,?,?,?,?)",
        (run_id, task_id, f"b-{run_id}", "/wt", "main", "0" * 40, "succeeded", "2026-10-01"),
    )
    db.execute("INSERT INTO sessions (adw_id, status) VALUES (?, 'success')", (run_id,))


def _envelope(
    db: Any,
    run_id: str,
    phase: str,
    agent: str,
    output_type: str,
    payload: dict[str, Any],
    created_at: str,
    *,
    valid: bool = True,
) -> None:
    phase_id = f"{run_id}-{phase}"
    db.execute(
        "INSERT OR IGNORE INTO phases (phase_id, adw_id, name) VALUES (?,?,?)",
        (phase_id, run_id, phase),
    )
    db.execute(
        "INSERT INTO envelopes (envelope_id, adw_id, phase_id, agent, output_type, "
        "payload_json, valid, attempt, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            f"env-{run_id}-{phase}-{created_at}",
            run_id,
            phase_id,
            agent,
            output_type,
            json.dumps({"status": "success", "summary": "", **payload}),
            int(valid),
            1,
            created_at,
        ),
    )


def _review(*blocking: str, approved: bool = False) -> dict[str, Any]:
    return {"approved": approved, "blocking": list(blocking), "findings": []}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = make_repo(tmp_path / "repo")
    db_path = root / ".factory/trace.db"
    TaskRunStore(db_path).close()
    tracer = Tracer(db_path, tmp_path / "events.jsonl")
    db = tracer.conn
    _run(db, "run-a", "P01-S01-T01")
    _run(db, "run-b", "P01-S01-T02")
    _run(db, "run-c", "P01-S01-T03")
    # c1: run-a, review
    _envelope(
        db,
        "run-a",
        "review",
        "reviewer",
        "ReviewOutput",
        _review("The new CLI command has no test."),
        "2026-10-02T10:00:00.000+00:00",
    )
    # an invalid attempt counts for nothing
    _envelope(
        db,
        "run-a",
        "review",
        "reviewer",
        "ReviewOutput",
        _review("garbage"),
        "2026-10-02T10:00:01.000+00:00",
        valid=False,
    )
    # c2: run-b, review (an unmet finding); c3: run-b, test triage
    _envelope(
        db,
        "run-b",
        "review",
        "reviewer",
        "ReviewOutput",
        {
            "approved": False,
            "blocking": [],
            "findings": [
                {"requirement": "tests", "met": False, "evidence": "no test for 'factory x'"},
                {"requirement": "docs", "met": True, "evidence": "README"},
            ],
        },
        "2026-10-05T10:00:00.000+00:00",
    )
    _envelope(
        db,
        "run-b",
        "test_plan_triage",
        "tester",
        "TestPlanOutput",
        {"coverage": "none", "reason": "ruff failed on unused import", "failure_cause": "code"},
        "2026-10-05T11:00:00.000+00:00",
    )
    # run-c approves: no objection
    _envelope(
        db,
        "run-c",
        "review",
        "reviewer",
        "ReviewOutput",
        _review(approved=True),
        "2026-10-06T10:00:00.000+00:00",
    )
    tracer.conn.close()
    return root


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> tuple[list[Any], list[dict[str, Any]]]:
    """The requests the fake harness saw, and the answers it gives in order."""
    seen: list[Any] = []
    answers: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "aifactory.learn.scan.check_harness", lambda name: HarnessStatus(name, "fake", "fake", "1")
    )

    def run(request: Any, **kwargs: Any) -> AgentResult:
        seen.append(request)
        answer = answers[min(len(seen), len(answers)) - 1]
        return AgentResult(text=json.dumps(answer), returncode=0)

    monkeypatch.setattr(agents.INTERFACES["claude"], "run", run)
    return seen, answers


def _lessons(*lessons: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "summary": "lessons", "lessons": list(lessons)}


TESTS_LESSON = {"rule": TESTS_RULE, "target": "AGENTS.md", "complaints": ["c1", "c2"]}
LINT_LESSON = {
    "rule": "Run ruff before reporting.",
    "target": "prompt",
    "target_detail": "builder",
    "complaints": ["c3"],
}


def _context(request: Any) -> dict[str, Any]:
    data, _ = json.JSONDecoder().raw_decode(request.prompt[request.prompt.index("{") :])
    assert isinstance(data, dict)
    return data


def _scan(capsys: pytest.CaptureFixture[str], repo: Path, *extra: str) -> dict[str, Any]:
    assert main(["learn", "scan", "--repo", str(repo), "--json", *extra]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["ok"] is True
    data = envelope["data"]
    assert isinstance(data, dict)
    return data


def test_collect_reads_objections_of_task_runs(repo: Path) -> None:
    found = collect(repo / ".factory/trace.db")
    assert [(o.run_id, o.source, o.text) for o in found] == [
        ("run-a", "review", "The new CLI command has no test."),
        ("run-b", "review", "tests: no test for 'factory x'"),
        ("run-b", "test_triage", "[code] ruff failed on unused import"),
    ]
    assert found[0].task_id == "P01-S01-T01"
    assert [o.run_id for o in collect(repo / ".factory/trace.db", "2026-10-03")] == [
        "run-b",
        "run-b",
    ]


def test_scan_proposes_repeated_objection_only(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    seen, answers = fake
    answers.append(_lessons(TESTS_LESSON, LINT_LESSON))
    data = _scan(capsys, repo)
    assert data["objections"] == 3 and data["runs"] == 2
    [lesson] = data["lessons"]  # the lint lesson comes from one run only
    assert lesson["rule"] == TESTS_RULE
    assert lesson["target"] == "AGENTS.md"
    assert lesson["occurrences"] == 2
    assert lesson["runs"] == [
        {"run_id": "run-a", "task_id": "P01-S01-T01"},
        {"run_id": "run-b", "task_id": "P01-S01-T02"},
    ]
    assert [c["text"] for c in lesson["complaints"]] == [
        "The new CLI command has no test.",
        "tests: no test for 'factory x'",
    ]
    context = _context(seen[0])
    assert [o["id"] for o in context["objections"]] == ["c1", "c2", "c3"]
    assert context["objections"][2]["source"] == "test_triage"
    assert context["rejected_lessons"] == []
    assert context["output_schema"]["title"] == "LessonsOutput"
    assert "Learner Agent" in seen[0].system_prompt
    assert Path(seen[0].cwd) != repo

    assert main(["learn", "scan", "--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert f"{lesson['id']}  2 run(s)  -> AGENTS.md" in out
    assert TESTS_RULE in out
    assert "run-a (P01-S01-T01), run-b (P01-S01-T02)" in out
    assert "[review run-a] The new CLI command has no test." in out
    assert "Run ruff" not in out


def test_rejected_lesson_is_not_offered_again(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    seen, answers = fake
    answers.append(_lessons(TESTS_LESSON))
    [lesson] = _scan(capsys, repo)["lessons"]
    args = ["learn", "reject", lesson["id"], "--reason", "known", "--repo", str(repo), "--json"]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["data"]["state"] == REJECTED
    store = LessonStore(repo / ".factory/trace.db")
    assert [(s.lesson_id, s.state, s.reason) for s in store.all()] == [
        (lesson["id"], REJECTED, "known")
    ]
    store.close()

    # the same rule, and a reworded rule over the same objections: neither comes back
    answers[:] = [_lessons(TESTS_LESSON, {**TESTS_LESSON, "rule": "Test new CLI commands."})]
    assert _scan(capsys, repo)["lessons"] == []
    assert _context(seen[-1])["rejected_lessons"] == [{"id": lesson["id"], "rule": TESTS_RULE}]


def test_since_leaves_one_run_and_no_agent(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    seen, _ = fake
    data = _scan(capsys, repo, "--since", "2026-10-03")
    assert data == {"since": "2026-10-03", "objections": 2, "runs": 1, "lessons": []}
    assert seen == []
    assert main(["learn", "scan", "--repo", str(repo), "--since", "2026-10-03"]) == 0
    assert "no lesson to propose" in capsys.readouterr().out


def test_unknown_objection_id_is_corrected_once(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    seen, answers = fake
    answers += [_lessons({**TESTS_LESSON, "complaints": ["c1", "c9"]}), _lessons(TESTS_LESSON)]
    [lesson] = _scan(capsys, repo)["lessons"]
    assert lesson["occurrences"] == 2
    assert len(seen) == 2 and "c9" in seen[1].prompt


def test_bad_since_and_unknown_lesson(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["learn", "scan", "--repo", str(repo), "--since", "yesterday", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_value"
    assert main(["learn", "reject", "L00000000", "--repo", str(repo), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "unknown_lesson"
