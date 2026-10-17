"""A scan adds repeats to an accepted lesson; ``view`` counts them before and after its merge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from learn_fixture import add_objection, fake_learner, make_learn_repo, merge_pr
from test_learn_accept import _accept
from test_learn_scan import TESTS_LESSON, TESTS_RULE, _context, _lessons, _scan

from aifactory.learn.store import ACCEPTED, PROPOSED, LessonStore
from aifactory.learn.view import lessons


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_learn_repo(tmp_path)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> tuple[list[Any], list[dict[str, Any]]]:
    return fake_learner(monkeypatch)


def test_view_lists_proposed_lesson_with_its_runs(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert lessons(repo) == []
    _, answers = fake
    answers.append(_lessons(TESTS_LESSON))
    _scan(capsys, repo)
    [lesson] = lessons(repo)
    assert lesson["state"] == PROPOSED and lesson["rule"] == TESTS_RULE
    assert lesson["occurrences"] == 2
    assert [r["run_id"] for r in lesson["runs"]] == ["run-a", "run-b"]
    assert [c["run_id"] for c in lesson["complaints"]] == ["run-a", "run-b"]
    assert lesson["pr"] is None and lesson["effect"] is None


def test_repeats_after_merge_count_as_after(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    seen, answers = fake
    answers.append(_lessons(TESTS_LESSON))
    [proposed] = _scan(capsys, repo)["lessons"]
    task_id = _accept(capsys, repo, proposed["id"])["task"]["id"]

    [accepted] = lessons(repo)
    assert accepted["state"] == ACCEPTED and accepted["task_id"] == task_id
    assert accepted["effect"] is None  # no merged PR yet

    merge_pr(repo, task_id, "2026-10-07T10:00:00.000+00:00")
    add_objection(
        repo,
        "run-d",
        "P01-S01-T04",
        "No test for the new command.",
        "2026-10-08T10:00:00.000+00:00",
    )
    # the agent puts the new objection (c4) under the accepted lesson, reworded
    answers[:] = [
        _lessons(
            {
                "rule": "Test every new command.",
                "target": "AGENTS.md",
                "complaints": ["c4"],
                "accepted": proposed["id"],
            }
        )
    ]
    data = _scan(capsys, repo)
    assert data["lessons"] == []
    assert data["repeats"] == [{"id": proposed["id"], "added": 1}]
    context = _context(seen[-1])
    assert context["accepted_lessons"] == [{"id": proposed["id"], "rule": TESTS_RULE}]
    assert context["rejected_lessons"] == []

    [lesson] = lessons(repo)
    assert lesson["occurrences"] == 3
    assert lesson["pr"]["url"].endswith(task_id)
    assert lesson["effect"] == {
        "merged_at": "2026-10-07T10:00:00.000+00:00",
        "before": {"runs": 2, "objections": 2},
        "after": {"runs": 1, "objections": 1},
    }

    # the same repeat found again adds nothing
    data = _scan(capsys, repo)
    assert data["repeats"] == [{"id": proposed["id"], "added": 0}]
    store = LessonStore(repo / ".factory/trace.db")
    try:
        assert len(store.get(proposed["id"]).complaints) == 3
    finally:
        store.close()


def test_objections_shared_with_accepted_lesson_are_a_repeat(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    _, answers = fake
    answers.append(_lessons(TESTS_LESSON))
    [proposed] = _scan(capsys, repo)["lessons"]
    _accept(capsys, repo, proposed["id"])
    add_objection(repo, "run-d", "P01-S01-T04", "Untested command.", "2026-10-08T10:00:00.000Z")
    # a new rule over an old objection (c1) and the new one (c4): not proposed, a repeat
    answers[:] = [
        _lessons({"rule": "Cover commands.", "target": "AGENTS.md", "complaints": ["c1", "c4"]})
    ]
    data = _scan(capsys, repo)
    assert data["lessons"] == []
    assert data["repeats"] == [{"id": proposed["id"], "added": 1}]
