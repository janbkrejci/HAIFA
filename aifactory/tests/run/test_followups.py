"""Follow-ups and blockers the agents report: TODO step and tasks, depends_on, blocked runs."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from run_repo import SPEC, T01, T02, Script, fake_env, git, make_run_repo, ok, write

from aifactory.backlog import (
    Task,
    check_backlog,
    commit_backlog,
    derived_state,
    edit_task,
    is_human,
    load_backlog,
)
from aifactory.engine.data_types import FollowUp, PlanOutput
from aifactory.review import ReviewError, approve_task
from aifactory.run import TaskRunStore, run_task
from aifactory.run.errors import TaskRunError
from aifactory.run.followups import collect, follow_up_marker, record
from aifactory.workflow import StepRecord, WorkflowRun

TODO_STEP = "M01-TODO"


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


def workflow_run(**fields: Any) -> WorkflowRun:
    envelope = PlanOutput(status="success", summary="planned", **fields)
    return WorkflowRun(
        exit_code=0,
        accepted=True,
        adw_id="run-1",
        records=[StepRecord(phase="plan", step="plan", kind="agent", owner="planner")],
        envelopes={"plan": envelope},
        history=[("plan", envelope)],
    )


def follow_up(title: str = "Migrace indexů", blocks: bool = False) -> FollowUp:
    return FollowUp(
        title=title,
        reason="schéma potřebuje indexy, které nejsou v rozsahu",
        details="Doplnit indexy do schématu.",
        blocks_task=blocks,
    )


def backlog_of(repo: Path) -> Any:
    return load_backlog(repo)


def task_of(repo: Path, task_id: str = T01) -> Task:
    node = load_backlog(repo).by_id[task_id]
    assert isinstance(node, Task)
    return node


def test_collect_dedupes_titles_and_ors_blocking() -> None:
    first = PlanOutput(status="success", follow_ups=[follow_up()], blocked_by=["X", "X"])
    second = PlanOutput(status="success", follow_ups=[follow_up(" migrace  INDEXŮ ", True)])
    wf = WorkflowRun(0, True, "r", history=[("plan", first), ("build", second)])
    reported, blocked = collect(wf)
    assert len(reported) == 1 and reported[0].blocks_task and reported[0].step == "plan"
    assert blocked == ["X"]


def test_record_creates_todo_step_and_task(repo: Path) -> None:
    outcome = record(repo, T01, "run-1", workflow_run(follow_ups=[follow_up()]))

    assert outcome.step_id == TODO_STEP
    assert outcome.blocked_by == [] and outcome.warnings == []
    assert outcome.committed
    backlog = backlog_of(repo)
    assert check_backlog(backlog) == []
    step = backlog.by_id[TODO_STEP]
    assert step.title == "TODO" and step.parent.id == "M01"
    [task] = step.tasks
    assert task.id == outcome.created[0].id == f"{TODO_STEP}-T01"
    assert task.related == [T01]
    assert "Doplnit indexy do schématu." in task.body
    assert "### Původ" in task.body
    for part in ("run-1", T01, "`plan`", "planner", "schéma potřebuje indexy"):
        assert part in task.body
    assert follow_up_marker(T01) in task.body
    assert backlog.by_id[T01].depends_on == []
    assert git(repo, "log", "-1", "--format=%s") == f"{T01}: TODO tasky z běhu run-1"
    assert git(repo, "status", "--porcelain") == ""


def test_record_gives_follow_up_its_writes(repo: Path) -> None:
    item = follow_up().model_copy(update={"writes": [" docs/decisions.md ", "docs/decisions.md"]})
    outcome = record(repo, T01, "run-1", workflow_run(follow_ups=[item, follow_up("Jiný")]))

    with_writes, inherited = (task_of(repo, c.id) for c in outcome.created)
    assert with_writes.writes == ["docs/decisions.md"]
    assert inherited.writes == []
    assert check_backlog(backlog_of(repo)) == []


@pytest.mark.parametrize(
    ("update", "human"),
    [
        ({"for_human": True}, True),
        ({"writes": ["backlog/M01-core/S01-model/"]}, True),
        ({"writes": [".factory/config.yaml"]}, True),
        ({"writes": ["docs/decisions.md"]}, False),
        ({"writes": ["**"]}, False),
    ],
)
def test_record_files_a_persons_follow_up(repo: Path, update: dict[str, Any], human: bool) -> None:
    item = follow_up().model_copy(update=update)
    outcome = record(repo, T01, "run-1", workflow_run(follow_ups=[item]))

    filed = task_of(repo, outcome.created[0].id)
    assert is_human(filed) is human


def test_record_gives_follow_up_its_workflow(repo: Path) -> None:
    item = follow_up().model_copy(update={"workflow": "build-review"})
    outcome = record(repo, T01, "run-1", workflow_run(follow_ups=[item]))

    assert task_of(repo, outcome.created[0].id).own["workflow"] == "build-review"


def test_run_refuses_a_persons_task(repo: Path, script: Script) -> None:
    outcome = record(repo, T01, "run-1", workflow_run(follow_ups=[follow_up(blocks=True)]))
    new_id = outcome.created[0].id
    edit_task(repo, new_id, assignee="human")
    commit_backlog(repo, "human")

    with pytest.raises(TaskRunError) as caught:
        run_task(repo, new_id)
    assert caught.value.code == "human_task"


def test_record_is_idempotent(repo: Path) -> None:
    wf = workflow_run(follow_ups=[follow_up(blocks=True)])
    first = record(repo, T01, "run-1", wf)
    head = git(repo, "rev-parse", "HEAD")
    again = record(repo, T01, "run-2", wf)
    assert [c.id for c in again.created] == [c.id for c in first.created]
    assert again.created[0].existed and again.blocked_by == first.blocked_by
    assert git(repo, "rev-parse", "HEAD") == head
    assert len(backlog_of(repo).by_id[TODO_STEP].tasks) == 1


@pytest.mark.parametrize(
    ("directory", "step_id", "title"),
    [("TODO-todo", TODO_STEP, "TODO"), ("S09-later", "M01-S09", "todo")],
)
def test_record_reuses_existing_todo_step(
    repo: Path, directory: str, step_id: str, title: str
) -> None:
    write(
        repo,
        f"backlog/M01-core/{directory}/index.md",
        f"---\nid: {step_id}\ntitle: {title}\n---\n\nOdložené.\n",
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "todo step")
    outcome = record(repo, T01, "run-1", workflow_run(follow_ups=[follow_up()]))
    assert outcome.step_id == step_id
    backlog = backlog_of(repo)
    assert [t.id for t in backlog.by_id[step_id].tasks] == [f"{step_id}-T01"]
    assert TODO_STEP not in backlog.by_id or step_id == TODO_STEP


def test_blocking_follow_up_links_and_blocks(repo: Path) -> None:
    outcome = record(repo, T01, "run-1", workflow_run(follow_ups=[follow_up(blocks=True)]))
    new_id = outcome.created[0].id
    assert outcome.blocked_by == [new_id]
    backlog = backlog_of(repo)
    task = backlog.by_id[T01]
    assert task.depends_on == [new_id]
    assert derived_state(backlog, task) == "blocked"
    assert "zůstává blokovaný" in backlog.by_id[new_id].body


def test_blocked_by_existing_ids(repo: Path) -> None:
    # T03 is not done: it blocks; an unknown id is a warning
    t03 = "M01-S01-T03"
    write(
        repo,
        f"backlog/M01-core/S01-model/{t03}-index.md",
        f"---\nid: {t03}\ntitle: Index\nstatus: todo\n---\n\n## Zadání\nIndex.\n",
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "T03")
    outcome = record(repo, T01, "run-1", workflow_run(blocked_by=[t03, "M01-S01-T99"]))
    assert outcome.blocked_by == [t03]
    assert any("M01-S01-T99" in w for w in outcome.warnings)
    assert outcome.step_id is None  # no follow-up, no TODO step
    assert backlog_of(repo).by_id[T01].depends_on == [t03]


def test_blocker_that_cannot_be_linked_still_blocks(repo: Path) -> None:
    # T02 depends on T01: the link would be a cycle, the blocker still counts
    outcome = record(repo, T01, "run-1", workflow_run(blocked_by=[T02]))
    assert outcome.blocked_by == [T02]
    assert any("not written" in w for w in outcome.warnings)
    assert backlog_of(repo).by_id[T01].depends_on == []


def test_blocked_by_done_task_does_not_block(repo: Path) -> None:
    path = repo / "backlog/M01-core/S01-model/M01-S01-T02-loader.md"
    text = path.read_text(encoding="utf-8").replace("status: todo", "status: done")
    text = text.replace(f"depends_on: [{T01}]\n", "")
    path.write_text(text, encoding="utf-8", newline="\n")
    git(repo, "commit", "-q", "-am", "T02 done")
    outcome = record(repo, T01, "run-1", workflow_run(blocked_by=[T02]))
    assert outcome.blocked_by == []
    assert backlog_of(repo).by_id[T01].depends_on == []


# ── task run ─────────────────────────────────────────────────────────────────


def planner_reports(script: Script, **fields: Any) -> None:
    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add schema spec", **fields))


def stored_pr_count(repo: Path) -> int:
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        return len(store.prs_for_task(T01))
    finally:
        store.close()


def test_blocked_run_fails_without_pr(repo: Path, script: Script) -> None:
    item = follow_up(blocks=True).model_dump()
    planner_reports(script, follow_ups=[item])
    result = run_task(repo, T01)

    assert result.run.state == "failed"
    assert result.run.error is not None and result.run.error.startswith("blocked:")
    assert result.pr is None and stored_pr_count(repo) == 0
    assert result.follow_ups is not None
    new_id = result.follow_ups.created[0].id
    assert new_id in result.run.error
    backlog = load_backlog(repo)
    task = task_of(repo)
    assert task.depends_on == [new_id] and task.status == "todo"
    assert derived_state(backlog, task) == "blocked"


def test_follow_up_is_listed_in_pr_body(repo: Path, script: Script) -> None:
    summary = {"goal": "Schéma pro data.", "done": ["Navržené schéma."], "not_done": []}
    planner_reports(script, follow_ups=[follow_up().model_dump()], pr_summary=summary)
    result = run_task(repo, T01)

    assert result.ok, (result.run.error, result.pr_error)
    assert result.pr is not None and result.follow_ups is not None
    new_id = result.follow_ups.created[0].id
    body = result.pr.body
    not_done = body.split("## Co uděláno nebylo", 1)[1].split("## Technické podrobnosti")[0]
    assert f"`{new_id}`" in not_done and "Migrace indexů" in not_done
    assert "Schéma pro data." in body.split("## Co bylo uděláno")[0]
    assert task_of(repo).depends_on == []


def test_approve_refuses_a_blocked_task(repo: Path, script: Script) -> None:
    planner_reports(script)
    result = run_task(repo, T01)
    assert result.ok, (result.run.error, result.pr_error)
    # a later run (or the operator) linked T01 to a blocker that is not done
    record(repo, T01, "run-2", workflow_run(follow_ups=[follow_up(blocks=True)]))

    with pytest.raises(ReviewError) as caught:
        approve_task(repo, T01)
    assert caught.value.code == "task_blocked"
    store = TaskRunStore(repo / ".factory" / "trace.db")
    try:
        pr = store.pr_for_branch(result.run.branch)
    finally:
        store.close()
    assert pr is not None and pr.state == "open"
    assert git(repo, "log", "-1", "--format=%s", result.run.branch) != f"{T01}: status done"
