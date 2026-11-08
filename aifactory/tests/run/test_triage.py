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


@pytest.mark.parametrize("source", ["T1", None])
def test_large_context_budget(backlog: Backlog, source: str | None) -> None:
    local_step = backlog.containers[0].children[0]
    local_step.tasks[0].body = "č" * BODY_LIMIT
    other = Container("OTHER", "Other project", "project", "backlog/OTHER")
    step = Container("OS", "Other step", "step", "backlog/OTHER/OS", parent=other)
    other.children.append(step)
    # Put unrelated tasks first to ensure traversal order does not determine priority.
    backlog.containers.insert(0, other)
    for n in range(599):
        task = Task(
            f"O{n}",
            f"Other {n}",
            "todo",
            "task",
            f"backlog/OTHER/OS/O{n}.md",
            step,
            body=('"\\\nč' * BODY_LIMIT)[:BODY_LIMIT],
        )
        step.tasks.append(task)
        backlog.by_id[task.id] = task
    local_step.tasks[0].depends_on = ["O598"]
    step.tasks[-1].depends_on = ["O597"]
    step.tasks[-2].depends_on = ["O598"]  # a dependency cycle must terminate
    before = copy.deepcopy(backlog)
    payload = context([report()], backlog, task_id=source)
    assert len(json.dumps(payload, ensure_ascii=False, indent=2)) <= triage.CONTEXT_LIMIT
    assert payload["backlog_truncated"] is True
    if source:
        assert [t["id"] for t in payload["backlog"][:3]] == ["T1", "O597", "O598"]
        assert payload["backlog"][0]["body"] == "č" * BODY_LIMIT
        assert payload["backlog"][0]["body_truncated"] is False
        assert all(len(t["body"]) == BODY_LIMIT for t in payload["backlog"][1:3])
    assert any(set(t) == {"id", "title"} for t in payload["backlog"])
    assert len(step.tasks[0].body) == len(before.containers[0].children[0].tasks[0].body)


def test_context_omits_candidates_when_titles_exceed_budget(
    backlog: Backlog, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = context([report()], backlog)
    monkeypatch.setattr(triage, "CONTEXT_LIMIT", len(triage._context_json(baseline)))
    backlog.containers[0].children[0].tasks[0].title = "Huge title" * BODY_LIMIT
    payload = context([report()], backlog, task_id="T1")
    assert payload["backlog"] == []
    assert payload["backlog_truncated"] is True
    assert len(triage._context_json(payload)) <= triage.CONTEXT_LIMIT


def test_context_rejects_oversized_followups(backlog: Backlog) -> None:
    with pytest.raises(TriageUnavailable, match="exceeds budget"):
        context([report(details="x" * triage.CONTEXT_LIMIT)], backlog)


def test_complete_context_is_not_marked_truncated(backlog: Backlog) -> None:
    assert context([report()], backlog)["backlog_truncated"] is False


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
    found = ask_triager(tmp_path / "absent", [report()], backlog)
    assert [(d.follow_up_id, d.action) for d in found] == [("f1", "new")]
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


def test_model_error_is_in_phase_error_and_trace(
    repo: Path, backlog: Backlog, fake: tuple[list[Any], list[Any]]
) -> None:
    _, answers = fake
    answers.append("Prompt is too long")
    with pytest.raises(TriageUnavailable, match="Prompt is too long"):
        ask_triager(repo, [report()], backlog)
    [db] = (repo / ".factory/data/triage").glob("*/trace.db")
    with sqlite3.connect(db) as conn:
        status, error = conn.execute("SELECT status, error FROM phases").fetchone()
        assert status == "fail"
        assert "Prompt is too long" in error
        logs = conn.execute("SELECT payload_json FROM events WHERE type='log'").fetchall()
        assert any(json.loads(row[0]).get("model_response") == "Prompt is too long" for row in logs)
    [events] = (repo / ".factory/data/triage").glob("*/events.jsonl")
    assert "Prompt is too long" in events.read_text(encoding="utf-8")
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


def test_context_step_fallback(backlog: Backlog) -> None:
    step = backlog.containers[0].children[0]
    step.level = "milestone"
    payload = context([report()], backlog)
    assert payload["backlog"][0]["step"] == {"id": "S", "title": "Step"}
    assert payload["backlog"][0]["body_truncated"] is False
    assert payload["backlog_truncated"] is False


def test_context_preserves_followups_and_bounds_candidates(backlog: Backlog) -> None:
    step = backlog.containers[0].children[0]
    step.tasks = [replace(step.tasks[0], id=f"T{n}", body="Small") for n in range(450)]
    payload = context([report() for _ in range(450)], backlog)
    assert len(payload["follow_ups"]) == len(payload["backlog"]) == 450
    assert payload["backlog_truncated"] is True
    assert len(json.dumps(payload, ensure_ascii=False, indent=2)) <= triage.CONTEXT_LIMIT
    assert payload["backlog"][-1] == {"id": "T449", "title": "T1"}


@pytest.mark.parametrize("source", ["binding", "task", "computer"])
def test_triager_context_binding(
    repo: Path,
    backlog: Backlog,
    fake: tuple[list[Any], list[Any]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    source: str,
) -> None:
    from aifactory.harness import settings, thinking

    monkeypatch.setenv("HAIFA_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(thinking, "codex_models", lambda: [])
    settings.write(
        {
            "default_harness": "claude",
            "harnesses": {
                "pi": {"enabled": False},
                "claude": {"enabled": True, "model": "sonnet", "thinking": "high"},
                "codex": {"enabled": True, "model": "gpt-5.5", "thinking": "medium"},
            },
        },
        tmp_path / "home",
    )
    parent = backlog.containers[0]
    step = parent.children[0]
    task = step.tasks[1]  # The source may already be done.
    parent.defaults["harness"] = "codex" if source == "task" else "claude"
    step.defaults["model"] = "gpt-5.5" if source == "task" else "sonnet"
    task.own["thinking"] = "high"
    if source == "computer":
        parent.defaults.pop("harness")
        step.defaults.pop("model")
        settings.write(
            {
                "default_harness": "codex",
                "harnesses": {
                    "claude": {"enabled": True, "model": "sonnet"},
                    "pi": {"enabled": False},
                    "codex": {"enabled": True, "model": "gpt-5.5", "thinking": "medium"},
                },
            },
            tmp_path / "home",
        )
    seen, _ = fake
    codex_seen: list[Any] = []

    def codex(request: Any, **kwargs: Any) -> AgentResult:
        codex_seen.append(request)
        return AgentResult(text=json.dumps(output(choice())), returncode=0)

    monkeypatch.setattr(agents.INTERFACES["codex"], "run", codex)
    binding = {"harness": "codex", "model": "gpt-5.5", "thinking": "high"}
    assert (
        ask_triager(
            repo,
            [report()],
            backlog,
            task_id=task.id,
            binding=binding if source == "binding" else None,
        )[0].action
        == "covered"
    )
    assert not seen
    [request] = codex_seen
    assert request.model == "gpt-5.5" and request.thinking == "high"
    assert Path(request.cwd) != repo and not Path(request.cwd).exists()


@pytest.mark.parametrize("binding", [None, {}])
def test_triager_roster_without_context_or_with_empty_binding(
    repo: Path, backlog: Backlog, fake: tuple[list[Any], list[Any]], binding: Any
) -> None:
    seen, answers = fake
    answers.append(output(choice()))
    backlog.containers[0].defaults["harness"] = "codex"
    ask_triager(repo, [report()], backlog, task_id="T1" if binding == {} else None, binding=binding)
    assert len(seen) == 1 and seen[0].model == "sonnet"


def test_triager_unknown_source_task(repo: Path, backlog: Backlog) -> None:
    with pytest.raises(TriageUnavailable, match="Unknown source task"):
        ask_triager(repo, [report()], backlog, task_id="missing")


def peer_choice(source: str, target: str) -> dict[str, Any]:
    return choice(task_id=None, follow_up_id=source, target_follow_up_id=target)


@pytest.mark.parametrize(
    ("decisions", "message"),
    [
        ([peer_choice("f1", "missing"), choice("new", follow_up_id="f2")], "unknown"),
        ([peer_choice("f1", "f1"), choice("new", follow_up_id="f2")], "cycle"),
        ([peer_choice("f1", "f2"), peer_choice("f2", "f1")], "cycle"),
    ],
)
def test_invalid_follow_up_graph_is_rejected(
    backlog: Backlog, decisions: list[dict[str, Any]], message: str
) -> None:
    assert message in " ".join(errors(backlog, *decisions, reports=[report(), report()]))


@pytest.mark.parametrize("human", [False, True])
def test_follow_up_chain_is_valid(backlog: Backlog, human: bool) -> None:
    assert (
        errors(
            backlog,
            peer_choice("f3", "f2"),
            choice("new"),
            peer_choice("f2", "f1"),
            reports=[report(for_human=human) for _ in range(3)],
        )
        == []
    )


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("implicit_human", [False, True])
def test_follow_up_coverage_preserves_assignment(
    backlog: Backlog, reverse: bool, implicit_human: bool
) -> None:
    human = report(writes=(".factory/config.yaml",)) if implicit_human else report(for_human=True)
    reports = [human, report()]
    if reverse:
        reports.reverse()
    assert "human assignment" in " ".join(
        errors(backlog, peer_choice("f1", "f2"), choice("new", follow_up_id="f2"), reports=reports)
    )


@pytest.mark.parametrize("action", ["new", "extend", "decide", "covered"])
def test_follow_up_target_fields_are_exclusive(action: str) -> None:
    # covered also rejects supplying both kinds of target.
    with pytest.raises(ValidationError):
        Decision.model_validate(choice(action, target_follow_up_id="f2"))


@pytest.mark.parametrize("cycle", [False, True])
def test_peer_graph_gets_one_engine_correction(
    repo: Path, backlog: Backlog, fake: tuple[list[Any], list[Any]], cycle: bool
) -> None:
    seen, answers = fake
    answers.extend(
        [
            output(
                peer_choice("f1", "f2"),
                peer_choice("f2", "f1" if cycle else "missing"),
            ),
            output(choice("new"), peer_choice("f2", "f1")),
        ]
    )
    assert ask_triager(repo, [report(), report()], backlog)[1].target_follow_up_id == "f1"
    assert len(seen) == 2
    assert ("cycle" if cycle else "unknown") in seen[1].prompt


def test_peer_triage_without_todo_backlog(
    repo: Path, backlog: Backlog, fake: tuple[list[Any], list[Any]]
) -> None:
    seen, answers = fake
    backlog.containers[0].children[0].tasks.clear()
    answers.append(output(choice("new"), peer_choice("f2", "f1")))
    assert ask_triager(repo, [report(), report()], backlog)[1].target_follow_up_id == "f1"
    assert len(seen) == 1
