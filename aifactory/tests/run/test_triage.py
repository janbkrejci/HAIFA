"""Pure triage gates and real engine calls with an offline fake harness."""

from __future__ import annotations

import copy
import json
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from advice_fixture import make_repo
from aifactory.backlog import Backlog, Container, Task
from aifactory.config import ProjectSettings
from aifactory.engine import agents
from aifactory.engine.data_types import AgentResult
from aifactory.engine.tracer import Tracer
from aifactory.harness.check import HarnessStatus
from aifactory.run import triage
from aifactory.run.followups import Reported
from aifactory.run.task import prepare_cfg
from aifactory.run.triage import (
    BODY_LIMIT,
    Decision,
    TriageOutput,
    TriageUnavailable,
    _contained,
    _violations,
    ask_triager,
    context,
)


def report(**changes: Any) -> Reported:
    return replace(
        Reported("build", "builder", "Same title", "Reason", "Details", False), **changes
    )


@pytest.fixture
def backlog(tmp_path: Path) -> Backlog:
    parent = Container("P", "Project", "project", "backlog/P", defaults={"writes": ["src/app/"]})
    step = Container("S", "Step", "step", "backlog/P/S", parent=parent)
    parent.children.append(step)
    tasks = [
        Task(name, name, status, "task", f"backlog/P/S/{name}.md", step, body="Original work")
        for name, status in [("T1", "todo"), ("T2", "done"), ("T3", "cancelled")]
    ]
    tasks[0].depends_on = ["T2"]
    step.tasks = tasks
    return Backlog(
        tmp_path,
        ProjectSettings(),
        [parent],
        by_id={"P": parent, "S": step, **{t.id: t for t in tasks}},
    )


def choice(action: str = "covered", **changes: Any) -> dict[str, Any]:
    value: dict[str, Any] = {"follow_up_id": "f1", "action": action, "reason": "Related work."}
    if action != "new":
        value["task_id"] = "T1"
    if action == "extend":
        value.update(
            addition="Add cases in `src/app/test.py`.", addition_writes=["src/app/test.py"]
        )
    if action == "decide":
        value["proposal"] = "Replace the original approach; a person must settle the tradeoff."
    return {**value, **changes}


def output(*decisions: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"status": "success", "summary": "Triaged.", "decisions": list(decisions), **extra}


def errors(backlog: Backlog, *decisions: dict[str, Any], reports: Any = None) -> list[str]:
    return _violations(
        TriageOutput.model_validate(output(*decisions)), reports or [report()], backlog
    )


def test_context_is_pure_complete_and_only_todo(backlog: Backlog) -> None:
    step = backlog.containers[0].children[0]
    step.defaults["assignee"] = "human"
    step.tasks[0].body = "x" * (BODY_LIMIT + 20)
    step.tasks[0].depends_on = ["missing"]  # blocked todo is still a candidate
    reports = [report(writes=(), blocks_task=True, for_human=True), report()]
    before = copy.deepcopy(backlog)
    payload = context(reports, backlog)
    [task] = payload["backlog"]
    assert task == {
        "id": "T1",
        "title": "T1",
        "status": "todo",
        "path": "backlog/P/S/T1.md",
        "step": {"id": "S", "title": "Step"},
        "body": "x" * (BODY_LIMIT - 1) + "…",
        "body_truncated": True,
        "writes": ["src/app/"],
        "assignee": "human",
    }
    assert payload["follow_ups"] == [
        {
            "id": "f1",
            "title": "Same title",
            "reason": "Reason",
            "details": "Details",
            "blocks_task": True,
            "writes": [],
            "for_human": True,
        },
        {
            "id": "f2",
            "title": "Same title",
            "reason": "Reason",
            "details": "Details",
            "blocks_task": False,
            "writes": None,
            "for_human": False,
        },
    ]
    assert payload["output_schema"]["title"] == "TriageOutput"
    assert step.tasks[0].body == before.containers[0].children[0].tasks[0].body
    assert reports[0].writes == ()
    json.dumps(payload)


@pytest.mark.parametrize("action", ["covered", "extend", "decide", "new"])
def test_valid_decisions(backlog: Backlog, action: str) -> None:
    assert errors(backlog, choice(action)) == []


@pytest.mark.parametrize("target", ["unknown", "P", "S", "T2", "T3"])
def test_target_must_be_todo_task(backlog: Backlog, target: str) -> None:
    assert "known todo task" in " ".join(errors(backlog, choice(task_id=target)))


def test_inherited_human_and_human_report(backlog: Backlog) -> None:
    backlog.containers[0].defaults["assignee"] = "human"
    assert "human" in " ".join(errors(backlog, choice("extend")))
    assert errors(backlog, choice("covered")) == []
    assert errors(backlog, choice("decide")) == []
    del backlog.containers[0].defaults["assignee"]
    assert "human" in " ".join(errors(backlog, choice("extend"), reports=[report(for_human=True)]))


@pytest.mark.parametrize("decisions", [[], [choice(), choice()], [choice(follow_up_id="f2")]])
def test_identity_must_be_complete(backlog: Backlog, decisions: list[dict[str, Any]]) -> None:
    assert errors(backlog, *decisions)


@pytest.mark.parametrize(
    "changes",
    [
        {"reason": "   "},
        {"task_id": None},
        {"addition": "oops"},
        {"proposal": "oops"},
        {"addition_writes": []},
        {"unknown": 1},
        {"action": "new", "task_id": "T1"},
        {"action": "extend", "addition": " "},
        {"action": "decide", "proposal": " "},
    ],
)
def test_invalid_action_fields(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Decision.model_validate(choice(**changes))


@pytest.mark.parametrize(
    ("needed", "allowed", "ok"),
    [
        ("./src\\app/x.py", "src/app/", True),
        ("src/app/", "src/app/one.py", False),
        ("src/application/x.py", "src/app/", False),
        ("src/**", "src/*/one.py", False),
        ("src/app/*.py", "src/app/", True),
        ("src/*.py", "src/*.py", True),
        ("src/app/x.py", "src/**/*.py", True),
        ("src/app/", "src/**", False),
        ("../src/app/x.py", "**", False),
        ("src/../app/x.py", "**", False),
        ("/src/app/x.py", "**", False),
        ("C:\\src\\app", "**", False),
        ("src/app/x.py", "../src/", False),
        ("src/**", "**", True),
    ],
)
def test_conservative_containment(needed: str, allowed: str, ok: bool) -> None:
    assert _contained(needed, allowed) is ok


def test_extension_checks_report_and_declared_and_named_scope(backlog: Backlog) -> None:
    assert errors(backlog, choice("extend"), reports=[report(writes=("src/app/",))]) == []
    assert "other/" in " ".join(
        errors(backlog, choice("extend"), reports=[report(writes=("other/",))])
    )
    assert errors(backlog, choice("extend", addition_writes=["outside/file.py"]))
    assert errors(backlog, choice("extend", addition="Edit `outside/file.py`."))
    assert errors(backlog, choice("extend", addition="Edit src/app/other.py."))
    assert errors(backlog, choice("extend", addition_writes=[], addition="Read the task."))
    assert errors(
        backlog,
        choice("extend", addition_writes=[], addition="Read the task."),
        reports=[report(writes=("src/app/",))],
    )
    assert (
        errors(
            backlog,
            choice("extend", addition_writes=[], addition="Read the task."),
            reports=[report(writes=())],
        )
        == []
    )
    assert errors(
        backlog,
        choice("extend", addition_writes=[], addition="Edit `src/app/a.py`."),
        reports=[report(writes=())],
    )


@pytest.mark.parametrize("statuses", [[], ["done"], ["done", "cancelled"]])
def test_shortcuts_do_not_touch_configuration(
    tmp_path: Path, backlog: Backlog, monkeypatch: pytest.MonkeyPatch, statuses: list[str]
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Shortcut must not set up a run")

    monkeypatch.setattr(triage, "load_run_config", forbidden)
    monkeypatch.setattr(triage, "_isolated", forbidden)
    assert ask_triager(tmp_path / "absent", [], backlog) == []
    tasks = backlog.containers[0].children[0].tasks
    tasks[:] = [replace(tasks[0], id=f"T{n}", status=s) for n, s in enumerate(statuses)]
    found = ask_triager(tmp_path / "absent", [report(), report(for_human=True)], backlog)
    assert [(d.follow_up_id, d.action) for d in found] == [("f1", "new"), ("f2", "new")]
    assert not (tmp_path / "absent").exists()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "repo")


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[list[Any], list[Any]]]:
    seen: list[Any] = []
    answers: list[Any] = []
    monkeypatch.setattr(triage, "ensure_enabled", lambda name: None)
    monkeypatch.setattr(
        triage, "check_harness", lambda name: HarnessStatus(name, "fake", "fake", "1")
    )

    def run(request: Any, **kwargs: Any) -> AgentResult:
        seen.append(request)
        answer = answers[min(len(seen), len(answers)) - 1]
        if callable(answer):
            answer = answer(request)
        if isinstance(answer, Exception):
            raise answer
        return AgentResult(
            text=answer if isinstance(answer, str) else json.dumps(answer), returncode=0
        )

    monkeypatch.setattr(agents.INTERFACES["claude"], "run", run)
    tracers: list[Tracer] = []

    def tracer(*args: Any, **kwargs: Any) -> Tracer:
        instance = Tracer(*args, **kwargs)
        tracers.append(instance)
        return instance

    monkeypatch.setattr(triage, "Tracer", tracer)
    yield seen, answers
    for instance in tracers:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            instance.conn.execute("SELECT 1")


def test_engine_all_actions_order_and_isolation(
    repo: Path, backlog: Backlog, fake: tuple[list[Any], list[Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen, answers = fake
    answers.append(
        output(
            choice("new", follow_up_id="f4"),
            choice("extend", follow_up_id="f2"),
            choice("decide", follow_up_id="f3"),
            choice(),
        )
    )
    original = prepare_cfg
    resolved = []

    def permissive(*args: Any, **kwargs: Any) -> Any:
        cfg = original(*args, **kwargs)
        agent = agents.resolve(cfg, "triager")
        agent.writes = ["**"]
        resolved.append(agent)
        return cfg

    monkeypatch.setattr(triage, "prepare_cfg", permissive)
    decisions = ask_triager(repo, [report() for _ in range(4)], backlog)
    assert [d.action for d in decisions] == ["covered", "extend", "decide", "new"]
    assert [d.follow_up_id for d in decisions] == ["f1", "f2", "f3", "f4"]
    assert resolved[0].writes == []
    assert len(seen) == 1
    assert "Triager Agent" in seen[0].system_prompt
    assert Path(seen[0].cwd) != repo
    assert not Path(seen[0].cwd).exists()
    data, _ = json.JSONDecoder().raw_decode(seen[0].prompt[seen[0].prompt.index("{") :])
    assert len(data["follow_ups"]) == 4
    assert [t["id"] for t in data["backlog"]] == ["T1"]
    _finished(repo, "success")


def _finished(repo: Path, status: str) -> None:
    [db] = (repo / ".factory/data/triage").glob("*/trace.db")
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT status FROM sessions").fetchone() == (status,)


def test_gate_one_correction(
    repo: Path, backlog: Backlog, fake: tuple[list[Any], list[Any]]
) -> None:
    seen, answers = fake
    answers.extend([output(choice(task_id="unknown")), output(choice())])
    assert ask_triager(repo, [report()], backlog)[0].action == "covered"
    assert len(seen) == 2 and "unknown" in seen[1].prompt
    assert not Path(seen[0].cwd).exists()


@pytest.mark.parametrize(
    "bad",
    [
        output(choice(task_id="unknown")),
        output(),
        output(choice("extend", addition_writes=["bad/"])),
        output(choice(), choice()),
        output(choice(task_id="T2")),
    ],
)
def test_repeated_gate_failure_raises(
    repo: Path, backlog: Backlog, fake: tuple[list[Any], list[Any]], bad: dict[str, Any]
) -> None:
    seen, answers = fake
    answers.append(bad)
    with pytest.raises(TriageUnavailable, match="failed gates after 2 attempt") as exc:
        ask_triager(repo, [report()], backlog)
    assert exc.value.__cause__ is not None
    assert len(seen) == 2
    assert not Path(seen[0].cwd).exists()
    _finished(repo, "fail")


@pytest.mark.parametrize(
    "answer",
    ["not JSON", output(status="fail", summary="Cannot judge."), RuntimeError("Harness crashed")],
)
def test_output_and_invocation_failures(
    repo: Path, backlog: Backlog, fake: tuple[list[Any], list[Any]], answer: Any
) -> None:
    seen, answers = fake
    answers.append(answer)
    with pytest.raises(TriageUnavailable) as exc:
        ask_triager(repo, [report()], backlog)
    assert exc.value.__cause__ is not None
    assert not Path(seen[0].cwd).exists()
    _finished(repo, "fail")


@pytest.mark.parametrize("failure", ["missing", "disabled", "unavailable", "resolve", "validate"])
def test_unavailable_setup(
    repo: Path,
    backlog: Backlog,
    fake: tuple[list[Any], list[Any]],
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    seen, _ = fake
    if failure == "missing":
        original = prepare_cfg

        def missing(*args: Any, **kwargs: Any) -> Any:
            cfg = original(*args, **kwargs)
            cfg.agents = [a for a in cfg.agents if a.name != "triager"]
            return cfg

        monkeypatch.setattr(triage, "prepare_cfg", missing)
    elif failure == "disabled":

        def disabled(name: str) -> None:
            raise ValueError("Harness disabled")

        monkeypatch.setattr(triage, "ensure_enabled", disabled)
    elif failure == "unavailable":
        monkeypatch.setattr(
            triage, "check_harness", lambda n: HarnessStatus(n, "fake", error="Missing binary")
        )
    else:

        def invalid(*args: Any, **kwargs: Any) -> Any:
            raise SystemExit("Invalid roster")

        monkeypatch.setattr(agents, failure, invalid)
    with pytest.raises(TriageUnavailable):
        ask_triager(repo, [report()], backlog)
    assert seen == []


def test_read_only_guard_and_cleanup(
    repo: Path, backlog: Backlog, fake: tuple[list[Any], list[Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen, answers = fake
    original = (repo / "backlog/P01/S01/P01-S01-T01-first.md").read_bytes()
    tracers = []
    real_tracer = Tracer

    def tracer(*args: Any, **kwargs: Any) -> Any:
        instance = real_tracer(*args, **kwargs)
        tracers.append(instance)
        return instance

    monkeypatch.setattr(triage, "Tracer", tracer)

    def write(request: Any) -> dict[str, Any]:
        (Path(request.cwd) / "backlog/P01/S01/P01-S01-T01-first.md").write_text("Forbidden")
        (repo / "backlog/P01/S01/P01-S01-T01-first.md").write_text("Also forbidden")
        return output(choice())

    answers.append(write)
    with pytest.raises(TriageUnavailable, match="backlog"):
        ask_triager(repo, [report()], backlog)
    assert (repo / "backlog/P01/S01/P01-S01-T01-first.md").read_bytes() == original
    assert not Path(seen[0].cwd).exists()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        tracers[0].conn.execute("SELECT 1")
    _finished(repo, "fail")


@pytest.mark.parametrize("path", ["/src/app/x.py", "C:\\src\\app\\x.py", "src/../app/x.py"])
def test_addition_cannot_hide_unsafe_named_paths(backlog: Backlog, path: str) -> None:
    assert errors(backlog, choice("extend", addition=f"Edit {path}."))


def test_urls_are_not_addition_path_evidence(backlog: Backlog) -> None:
    assert (
        errors(
            backlog,
            choice(
                "extend", addition="Add cases in `src/app/test.py` for https://example.com/a/b."
            ),
        )
        == []
    )


def test_context_step_fallback_and_no_candidate_limit(backlog: Backlog) -> None:
    step = backlog.containers[0].children[0]
    step.level = "milestone"
    step.tasks = [replace(step.tasks[0], id=f"T{n}", body="Small") for n in range(450)]
    payload = context([report() for _ in range(450)], backlog)
    assert len(payload["follow_ups"]) == len(payload["backlog"]) == 450
    assert payload["backlog"][-1]["step"] == {"id": "S", "title": "Step"}
    assert payload["backlog"][-1]["body_truncated"] is False
