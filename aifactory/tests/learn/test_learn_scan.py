"""``factory learn scan`` and ``reject`` over a fixture trace DB, with a fake harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aifactory.cli import main
from aifactory.learn.collect import collect
from aifactory.learn.store import REJECTED, LessonStore
from learn_fixture import fake_learner, make_learn_repo

TESTS_RULE = "Add a test for every new CLI command."


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_learn_repo(tmp_path)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> tuple[list[Any], list[dict[str, Any]]]:
    return fake_learner(monkeypatch)


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
    args = ["learn", "dismiss", lesson["id"], "--reason", "known", "--repo", str(repo), "--json"]
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
    assert data == {
        "since": "2026-10-03",
        "objections": 2,
        "runs": 1,
        "lessons": [],
        "repeats": [],
    }
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
    assert main(["learn", "dismiss", "L00000000", "--repo", str(repo), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "unknown_lesson"
