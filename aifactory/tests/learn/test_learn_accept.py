"""``factory learn accept`` and ``dismiss``: a lesson becomes a backlog task or is rejected."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_learn_scan import TESTS_LESSON, TESTS_RULE, _lessons, _scan

from advice_fixture import git
from aifactory.backlog import Task, check_backlog, load_backlog
from aifactory.cli import main
from aifactory.learn.accept import WORKFLOW, lesson_marker, target_writes
from aifactory.learn.collect import collect
from aifactory.learn.sources import FACTORY_REPO_ENV
from aifactory.learn.store import ACCEPTED, REJECTED, LessonStore, StoredLesson
from learn_fixture import fake_learner, make_learn_repo, register_learn_repos


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_learn_repo(tmp_path)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> tuple[list[Any], list[dict[str, Any]]]:
    return fake_learner(monkeypatch)


def _accept(capsys: pytest.CaptureFixture[str], repo: Path, *args: str) -> dict[str, Any]:
    assert main(["learn", "accept", *args, "--repo", str(repo), "--json"]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["ok"] is True
    data = envelope["data"]
    assert isinstance(data, dict)
    return data


def _store(repo: Path) -> list[StoredLesson]:
    store = LessonStore(repo / ".factory/trace.db")
    try:
        return store.all()
    finally:
        store.close()


def test_accept_files_a_task_that_changes_the_rules(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    _, answers = fake
    answers.append(_lessons(TESTS_LESSON))
    [lesson] = _scan(capsys, repo)["lessons"]
    rules_before = git(repo, "ls-files", "AGENTS.md", "CLAUDE.md")

    data = _accept(capsys, repo, lesson["id"])
    task = data["task"]
    assert data["state"] == ACCEPTED and data["existed"] is False
    assert data["step_created"] is True and data["committed"] is True
    assert task["id"] == "P01-LEARN-T01" and task["step"] == "P01-LEARN"
    assert task["workflow"] == WORKFLOW == "build-review"
    assert task["writes"] == ["AGENTS.md"]

    backlog = load_backlog(repo)
    assert check_backlog(backlog) == []
    node = backlog.by_id[task["id"]]
    assert isinstance(node, Task)
    assert node.status == "todo"
    assert node.own["workflow"] == "build-review"
    assert node.writes == ["AGENTS.md"]
    assert node.related == ["P01-S01-T01"]  # P01-S01-T02 is not in the backlog
    assert node.parent.parent is not None and node.parent.parent.id == "P01"
    assert TESTS_RULE in node.body and "`AGENTS.md`" in node.body
    assert "Důkazy" in node.body
    assert "běh `run-a`, task `P01-S01-T01` (review): The new CLI command has no test." in (
        node.body
    )
    assert "tests: no test for 'factory x'" in node.body
    assert lesson_marker(lesson["id"]) in node.body
    # committed to base; the factory itself writes no rule
    assert git(repo, "status", "--porcelain", "--", "backlog") == ""
    assert task["id"] in git(repo, "log", "-1", "--format=%s")
    assert git(repo, "ls-files", "AGENTS.md", "CLAUDE.md") == rules_before == ""
    assert [(s.lesson_id, s.state, s.task_id) for s in _store(repo)] == [
        (lesson["id"], ACCEPTED, task["id"])
    ]

    # accepting again shows the same task and files nothing new
    again = _accept(capsys, repo, lesson["id"])
    assert again["existed"] is True and again["task"]["id"] == task["id"]
    learn_step = repo / "backlog/P01" / Path(node.path).parent.name
    assert len(list(learn_step.glob("P01-LEARN-T*.md"))) == 1

    assert main(["learn", "accept", lesson["id"], "--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert f"lesson {lesson['id']} is already task {task['id']}" in out
    assert "workflow build-review, writes AGENTS.md" in out

    # an accepted lesson is not offered again
    answers[:] = [_lessons(TESTS_LESSON)]
    assert _scan(capsys, repo)["lessons"] == []


def test_dismiss_rejects_and_accept_needs_a_known_lesson(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    _, answers = fake
    answers.append(_lessons(TESTS_LESSON))
    [lesson] = _scan(capsys, repo)["lessons"]
    assert main(["learn", "dismiss", lesson["id"], "--repo", str(repo)]) == 0
    assert capsys.readouterr().out.strip() == f"dismissed {lesson['id']}: {TESTS_RULE}"
    assert [(s.state, s.task_id) for s in _store(repo)] == [(REJECTED, None)]
    assert not list(repo.glob("backlog/P01/LEARN-*"))

    for command in ("accept", "dismiss"):
        assert main(["learn", command, "L00000000", "--repo", str(repo), "--json"]) == 2
        assert json.loads(capsys.readouterr().out)["error"]["code"] == "unknown_lesson"


def test_accept_without_runs_in_the_backlog_needs_the_project(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "backlog/P02").mkdir()
    (repo / "backlog/P02/index.md").write_text("---\nid: P02\ntitle: Other\n---\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "second project")
    store = LessonStore(repo / ".factory/trace.db")
    store.save_proposed(
        StoredLesson(
            "L12345678",
            "Keep the review prompt short.",
            "prompt",
            "reviewer",
            complaints=["gone#0"],
            runs=["run-x", "run-y"],
        )
    )
    store.close()

    assert main(["learn", "accept", "L12345678", "--repo", str(repo), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "project_required"

    data = _accept(capsys, repo, "L12345678", "--project", "P02")
    assert data["task"]["id"] == "P02-LEARN-T01"
    assert data["task"]["writes"] == [".factory/prompts/reviewer/"]
    node = load_backlog(repo).by_id["P02-LEARN-T01"]
    assert isinstance(node, Task)
    assert node.writes == [".factory/prompts/reviewer/"]
    assert "promptu role reviewer (`.factory/prompts/reviewer/`)" in node.body
    assert "- běh `run-x`" in node.body and "- běh `run-y`" in node.body


def test_target_writes_cover_the_rules_file_only() -> None:
    assert target_writes("CLAUDE.md") == ["CLAUDE.md"]
    assert target_writes("AGENTS.md", "ignored") == ["AGENTS.md"]
    assert target_writes("skill", "factory") == [
        ".claude/skills/factory/",
        ".agents/skills/factory/",
    ]
    assert target_writes("skill", "../etc") == [".claude/skills/", ".agents/skills/"]
    assert target_writes("prompt", "test-reviewer") == [".factory/prompts/test-reviewer/"]
    assert target_writes("prompt", "") == [".factory/prompts/"]
    assert target_writes("seed", "reviewer") == ["aifactory/src/aifactory/seed/agents/reviewer/"]
    assert target_writes("seed", "../x") == ["aifactory/src/aifactory/seed/agents/"]


@pytest.fixture
def two(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    monkeypatch.delenv(FACTORY_REPO_ENV, raising=False)
    return register_learn_repos(tmp_path, "factory", "beta")


def _keys(repo: Path, repo_id: str) -> list[str]:
    """The prefixed keys of the fixture's objections (run-a, run-b, run-b)."""
    return [f"{repo_id}:{o.key}" for o in collect(repo / ".factory/trace.db")]


def _save(repo: Path, lesson: StoredLesson) -> None:
    store = LessonStore(repo / ".factory/trace.db")
    try:
        store.save_proposed(lesson)
    finally:
        store.close()


def test_accept_a_lesson_with_objections_from_two_repos(
    two: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    factory, beta = two["factory"], two["beta"]
    own, other = _keys(factory, "factory"), _keys(beta, "beta")
    _save(
        factory,
        StoredLesson(
            "L00000001",
            "Test every new command.",
            "AGENTS.md",
            complaints=[own[1], other[0]],  # factory run-b (P01-S01-T02), beta run-a
            runs=["run-b", "run-a"],
            origin=["factory", "beta"],
        ),
    )

    data = _accept(capsys, factory, "L00000001")
    task = data["task"]
    assert task["id"] == "P01-LEARN-T01" and task["writes"] == ["AGENTS.md"]
    node = load_backlog(factory).by_id[task["id"]]
    assert isinstance(node, Task)
    assert node.writes == ["AGENTS.md"]
    # beta's run-a is of beta's P01-S01-T01, not of the factory backlog's task of that id
    assert node.related == []
    assert "Výtky z 2 běhů" in node.body
    assert (
        "- repo `factory`, běh `run-b`, task `P01-S01-T02` (review): tests: no test for 'factory x'"
    ) in node.body
    assert (
        "- repo `beta`, běh `run-a`, task `P01-S01-T01` (review): The new CLI command has no test."
    ) in node.body
    assert not list(beta.glob("backlog/P01/LEARN-*"))

    again = _accept(capsys, factory, "L00000001")
    assert again["existed"] is True and again["task"]["id"] == task["id"]
    learn_step = factory / "backlog/P01" / Path(node.path).parent.name
    assert len(list(learn_step.glob("P01-LEARN-T*.md"))) == 1


def test_accept_relates_only_tasks_of_the_target_repo(
    two: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    factory, beta = two["factory"], two["beta"]
    _save(
        factory,
        StoredLesson(
            "L00000002",
            "Mind the reviewer.",
            "AGENTS.md",
            complaints=[_keys(factory, "factory")[0], _keys(beta, "beta")[0]],
            runs=["run-a"],
        ),
    )
    data = _accept(capsys, factory, "L00000002")
    node = load_backlog(factory).by_id[data["task"]["id"]]
    assert isinstance(node, Task)
    assert node.related == ["P01-S01-T01"]


def test_tasks_of_another_repo_do_not_choose_the_project(
    two: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    factory, beta = two["factory"], two["beta"]
    (factory / "backlog/P02").mkdir()
    (factory / "backlog/P02/index.md").write_text("---\nid: P02\ntitle: Other\n---\n")
    git(factory, "add", ".")
    git(factory, "commit", "-qm", "second project")
    _save(
        factory,
        StoredLesson(
            "L00000003",
            "Keep the review short.",
            "AGENTS.md",
            complaints=_keys(beta, "beta"),  # beta's P01-S01-T01 and T02
            runs=["run-a", "run-b"],
        ),
    )

    assert main(["learn", "accept", "L00000003", "--repo", str(factory), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "project_required"

    data = _accept(capsys, factory, "L00000003", "--project", "P02")
    assert data["task"]["id"] == "P02-LEARN-T01"
    node = load_backlog(factory).by_id["P02-LEARN-T01"]
    assert isinstance(node, Task)
    assert node.related == []
    assert "- repo `beta`, běh `run-a`" in node.body


def test_accept_a_seed_lesson_writes_the_role_prompt_of_the_seed(
    two: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    factory, beta = two["factory"], two["beta"]
    _save(
        factory,
        StoredLesson(
            "L00000004",
            "The reviewer names the failing test.",
            "seed",
            "reviewer",
            complaints=[_keys(factory, "factory")[0], _keys(beta, "beta")[1]],
            runs=["run-a", "run-b"],
            origin=["factory", "beta"],
        ),
    )

    data = _accept(capsys, factory, "L00000004")
    writes = ["aifactory/src/aifactory/seed/agents/reviewer/"]
    assert data["task"]["writes"] == writes
    node = load_backlog(factory).by_id[data["task"]["id"]]
    assert isinstance(node, Task)
    assert node.writes == writes
    assert (
        "promptu role reviewer v semínku knihovny (`aifactory/src/aifactory/seed/agents/reviewer/`)"
    ) in node.body
    assert "`factory library seed`" in node.body
    assert "- repo `beta`, běh `run-b`" in node.body
    assert "- repo `factory`, běh `run-a`" in node.body
