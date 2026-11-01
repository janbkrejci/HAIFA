"""``factory learn scan`` and ``reject`` over a fixture trace DB, with a fake harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aifactory.cli import main
from aifactory.learn.collect import collect
from aifactory.learn.sources import FACTORY_REPO_ENV
from aifactory.learn.store import ACCEPTED, REJECTED, LessonStore, StoredLesson
from learn_fixture import fake_learner, make_learn_repo, register_learn_repos

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
    # without --all: the repo the scan runs in (not registered here), no origin repos
    assert (lesson["repo"], lesson["origin"], lesson["origin_repos"]) == ("", [], 1)
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
    assert "repos" not in context and "repo_rule" not in context
    assert "seed" not in context["targets"]
    assert all("repo" not in o for o in context["objections"])
    assert all("repo" not in c for c in lesson["complaints"])
    store = LessonStore(repo / ".factory/trace.db")
    try:
        assert [s.origin for s in store.all()] == [[]]
    finally:
        store.close()
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


@pytest.mark.parametrize("configured", [False, True])
def test_learner_computer_binding(
    repo: Path,
    fake: tuple[list[Any], list[dict[str, Any]]],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    configured: bool,
) -> None:
    from aifactory.engine import agents
    from aifactory.engine.data_types import AgentResult
    from aifactory.harness import settings, thinking

    monkeypatch.setenv("HAIFA_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(thinking, "codex_models", lambda: [])
    if configured:
        settings.write(
            {
                "default_harness": "codex",
                "harnesses": {
                    "claude": {"enabled": True, "model": "sonnet"},
                    "pi": {"enabled": False},
                    "codex": {"enabled": True, "model": "gpt-5.5", "thinking": "high"},
                },
            },
            tmp_path / "home",
        )
    seen, answers = fake
    answers.append(_lessons(TESTS_LESSON))
    codex_seen: list[Any] = []

    def codex(request: Any, **kwargs: Any) -> AgentResult:
        codex_seen.append(request)
        return AgentResult(text=json.dumps(_lessons(TESTS_LESSON)), returncode=0)

    monkeypatch.setattr(agents.INTERFACES["codex"], "run", codex)
    [lesson] = _scan(capsys, repo)["lessons"]
    assert lesson["rule"] == TESTS_RULE and lesson["occurrences"] == 2
    if configured:
        assert not seen
        [request] = codex_seen
        assert request.model == "gpt-5.5" and request.thinking == "high"
    else:
        assert not codex_seen
        [request] = seen
        assert request.model == "sonnet"
    assert Path(request.cwd) != repo and not Path(request.cwd).exists()


def test_seed_target_without_all_outside_factory_is_corrected(
    repo: Path, fake: tuple[list[Any], list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    seen, answers = fake
    answers += [
        _lessons({**TESTS_LESSON, "target": "seed", "target_detail": "builder"}),
        _lessons(TESTS_LESSON),
    ]
    [lesson] = _scan(capsys, repo)["lessons"]
    assert lesson["target"] == "AGENTS.md"
    assert len(seen) == 2
    assert "target 'seed' is only for there is no factory repo" in seen[1].prompt


SEED_LESSON = {
    "rule": "Builder: run ruff before reporting.",
    "target": "seed",
    "target_detail": "builder",
    "repo": "haifa",
    "complaints": ["c3", "c6"],
}


@pytest.fixture
def two_repos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """``haifa`` (the factory repo) and ``app``: objections c1-c3 and c4-c6 with --all."""
    monkeypatch.setenv(FACTORY_REPO_ENV, "haifa")
    repos = register_learn_repos(tmp_path, "haifa", "app")
    assert list(repos) == ["haifa", "app"]
    return repos


def _stored(root: Path) -> list[StoredLesson]:
    store = LessonStore(root / ".factory/trace.db")
    try:
        return store.all()
    finally:
        store.close()


def test_scan_all_saves_each_lesson_in_its_target_repo(
    two_repos: dict[str, Path],
    fake: tuple[list[Any], list[dict[str, Any]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen, answers = fake
    app_lesson = {**TESTS_LESSON, "repo": "app", "complaints": ["c4", "c5"]}
    answers.append(_lessons(SEED_LESSON, app_lesson))
    data = _scan(capsys, two_repos["haifa"], "--all")
    assert data["all"] is True
    # run-a and run-b of both repos are four distinct runs
    assert (data["objections"], data["runs"], data["repos"]) == (6, 4, 2)
    by_repo = {lesson["repo"]: lesson for lesson in data["lessons"]}
    assert set(by_repo) == {"haifa", "app"}
    seed = by_repo["haifa"]
    assert (seed["target"], seed["target_detail"]) == ("seed", "builder")
    assert (seed["origin"], seed["origin_repos"], seed["occurrences"]) == (["app", "haifa"], 2, 2)
    assert seed["runs"] == [
        {"run_id": "run-b", "task_id": "P01-S01-T02", "repo": "haifa"},
        {"run_id": "run-b", "task_id": "P01-S01-T02", "repo": "app"},
    ]
    assert [c["repo"] for c in seed["complaints"]] == ["haifa", "app"]
    app = by_repo["app"]
    assert (app["origin"], app["origin_repos"], app["occurrences"]) == (["app"], 1, 2)

    [in_haifa] = _stored(two_repos["haifa"])
    assert (in_haifa.lesson_id, in_haifa.target) == (seed["id"], "seed")
    assert in_haifa.origin == ["app", "haifa"]
    assert [k.split(":")[0] for k in in_haifa.complaints] == ["haifa", "app"]
    [in_app] = _stored(two_repos["app"])
    assert (in_app.lesson_id, in_app.rule, in_app.origin) == (app["id"], TESTS_RULE, ["app"])
    assert all(k.startswith("app:") for k in in_app.complaints)

    context = _context(seen[0])
    assert context["repos"] == [
        {"id": "haifa", "name": "haifa", "is_factory": True},
        {"id": "app", "name": "app", "is_factory": False},
    ]
    assert [o["repo"] for o in context["objections"]] == ["haifa"] * 3 + ["app"] * 3
    assert "seed" in context["targets"] and "is_factory" in context["repo_rule"]

    assert main(["learn", "scan", "--repo", str(two_repos["haifa"]), "--all"]) == 0
    out = capsys.readouterr().out
    assert "6 objection(s) in 4 run(s) of 2 repo(s)" in out
    assert f"{seed['id']}  2 run(s)  -> seed (builder)  in haifa (objections from 2 repo(s))" in out
    assert "[test_triage app:run-b]" in out


def test_scan_all_unknown_repo_and_seed_outside_factory_are_corrected(
    two_repos: dict[str, Path],
    fake: tuple[list[Any], list[dict[str, Any]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen, answers = fake
    app_lesson = {**TESTS_LESSON, "repo": "app", "complaints": ["c4", "c5"]}
    answers += [
        _lessons({**app_lesson, "repo": "nope"}, {**SEED_LESSON, "repo": "app"}),
        _lessons(app_lesson, SEED_LESSON),
    ]
    data = _scan(capsys, two_repos["haifa"], "--all")
    assert len(seen) == 2
    assert "unknown repo id 'nope'" in seen[1].prompt
    assert "target 'seed' is only for the factory repo 'haifa'" in seen[1].prompt
    assert sorted(lesson["repo"] for lesson in data["lessons"]) == ["app", "haifa"]
    assert [s.target for s in _stored(two_repos["haifa"])] == ["seed"]
    assert [s.rule for s in _stored(two_repos["app"])] == [TESTS_RULE]


def test_scan_all_skips_settled_lessons_of_any_repo(
    two_repos: dict[str, Path],
    fake: tuple[list[Any], list[dict[str, Any]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen, answers = fake
    app_db = two_repos["app"] / ".factory/trace.db"
    app_keys = [o.key for o in collect(app_db)]  # stored by a one-repo scan: no prefix
    store = LessonStore(app_db)
    try:
        store.save_proposed(StoredLesson("L00000001", TESTS_RULE, "AGENTS.md", "", app_keys[:2]))
        store.reject("L00000001", "known")
        store.save_proposed(
            StoredLesson("L00000002", "Run ruff first.", "AGENTS.md", "", [app_keys[2]])
        )
        store.accept("L00000002", "T")
    finally:
        store.close()

    answers.append(
        _lessons(
            # the rejected rule, now for the factory repo
            {**TESTS_LESSON, "repo": "haifa", "complaints": ["c1", "c2"]},
            # other words over the rejected lesson's objections (unprefixed in the store)
            {**TESTS_LESSON, "rule": "Test new commands.", "repo": "app", "complaints": ["c4"]},
            # the factory repo repeats the lesson accepted in app
            {**LINT_LESSON, "repo": "haifa", "accepted": "L00000002"},
        )
    )
    data = _scan(capsys, two_repos["haifa"], "--all")
    assert data["lessons"] == []
    assert data["repeats"] == [{"id": "L00000002", "added": 1, "repo": "app"}]
    context = _context(seen[0])
    assert context["rejected_lessons"] == [{"id": "L00000001", "rule": TESTS_RULE}]
    assert context["accepted_lessons"] == [{"id": "L00000002", "rule": "Run ruff first."}]
    assert _stored(two_repos["haifa"]) == []
    accepted = next(s for s in _stored(two_repos["app"]) if s.state == ACCEPTED)
    assert accepted.complaints[0] == app_keys[2]
    assert accepted.complaints[1].startswith("haifa:")
