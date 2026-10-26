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
    link_task,
    load_backlog,
)
from aifactory.engine.data_types import FollowUp, PlanOutput
from aifactory.review import ReviewError, approve_task
from aifactory.run import TaskRunStore, run_task
from aifactory.run.errors import TaskRunError
from aifactory.run.followups import collect, follow_up_marker, record
from aifactory.workflow import StepRecord, WorkflowRun

TODO_STEP = "M01-TODO"


@pytest.fixture(autouse=True)
def offline_triage(monkeypatch: pytest.MonkeyPatch) -> None:
    from aifactory.run import triage

    def unavailable(*args: object) -> None:
        raise triage.TriageUnavailable("Offline legacy follow-up scenario")

    monkeypatch.setattr(triage, "ask_triager", unavailable)


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


def test_record_merges_phases_and_keeps_all_origins(repo: Path) -> None:
    item = follow_up().model_copy(update={"for_human": True})
    wf = workflow_run(follow_ups=[item])
    wf.history.append(("document", PlanOutput(status="success", follow_ups=[item])))
    wf.records.append(
        StepRecord(phase="document", step="document", kind="agent", owner="documenter")
    )

    outcome = record(repo, T01, "run-1", wf)

    assert len(outcome.created) == 1
    [filed] = backlog_of(repo).by_id[TODO_STEP].tasks
    assert is_human(filed)
    for origin in ("`plan`", "planner", "`document`", "documenter"):
        assert origin in filed.body.split("### Původ", 1)[1]


def test_record_keeps_different_assignees_separate(repo: Path) -> None:
    human = follow_up().model_copy(update={"for_human": True})
    outcome = record(repo, T01, "run-1", workflow_run(follow_ups=[follow_up(), human]))
    assert len(outcome.created) == 2
    assert [is_human(task_of(repo, c.id)) for c in outcome.created] == [False, True]
    assert [c.assignee for c in outcome.created] == ["agent", "human"]
    again = record(repo, T01, "run-2", workflow_run(follow_ups=[follow_up(), human]))
    assert [c.id for c in again.created] == [c.id for c in outcome.created]
    assert all(c.existed for c in again.created)
    assert [c.to_json()["assignee"] for c in again.created] == ["agent", "human"]


def test_record_merges_explicit_and_inferred_human_assignee(repo: Path) -> None:
    inferred = follow_up().model_copy(update={"writes": [".factory/config.yaml"]})
    explicit = follow_up().model_copy(update={"for_human": True})
    wf = workflow_run(follow_ups=[inferred])
    wf.history.append(("document", PlanOutput(status="success", follow_ups=[explicit])))

    outcome = record(repo, T01, "run-1", wf)

    assert len(outcome.created) == 1
    filed = task_of(repo, outcome.created[0].id)
    assert is_human(filed)
    assert "`plan`" in filed.body and "`document`" in filed.body


@pytest.mark.parametrize("related", [False, True])
def test_record_reuses_open_dependency(repo: Path, related: bool) -> None:
    # T02 already depends on T01. A run of T02 (or a related task) must reuse T01.
    task_id = T02
    if related:
        task_id = "M01-S01-T03"
        write(
            repo,
            f"backlog/M01-core/S01-model/{task_id}-more.md",
            f"---\nid: {task_id}\ntitle: More\nstatus: todo\nrelated: [{T02}]\n---\n",
        )
        git(repo, "add", "backlog")
        git(repo, "commit", "-q", "-m", "related task")
    item = follow_up(" schema ", blocks=True)
    outcome = record(repo, task_id, "run-1", workflow_run(follow_ups=[item]))

    assert len(outcome.created) == 1
    assert outcome.created[0].id == T01 and outcome.created[0].existed
    assert outcome.step_id is None
    assert TODO_STEP not in backlog_of(repo).by_id
    assert outcome.blocked_by == [T01] and outcome.warnings == []
    assert task_of(repo, task_id).depends_on == [T01]


@pytest.mark.parametrize("status", ["done", "cancelled"])
def test_record_does_not_reuse_closed_dependency(repo: Path, status: str) -> None:
    path = repo / task_of(repo).path
    path.write_text(
        path.read_text(encoding="utf-8").replace("status: todo", f"status: {status}"),
        encoding="utf-8",
    )
    git(repo, "commit", "-q", "-am", "Close dependency in target")
    outcome = record(repo, T02, "run-1", workflow_run(follow_ups=[follow_up("Schema")]))
    assert len(outcome.created) == 1 and not outcome.created[0].existed


@pytest.mark.parametrize(
    ("dependency_human", "follow_up_human"),
    [(True, True), (True, False), (False, True)],
)
def test_record_dependency_reuse_respects_assignee(
    repo: Path, dependency_human: bool, follow_up_human: bool
) -> None:
    # T02 depends on T01; the same title only covers work for the same assignee.
    edit_task(repo, T01, assignee="human" if dependency_human else "agent")
    if dependency_human:
        git(repo, "commit", "-q", "-am", "Assign dependency in target")
    item = follow_up("Schema").model_copy(update={"for_human": follow_up_human})

    outcome = record(repo, T02, "run-1", workflow_run(follow_ups=[item]))

    [created] = outcome.created
    reuse = dependency_human == follow_up_human
    assert created.id == (T01 if reuse else f"{TODO_STEP}-T01")
    assert created.existed is reuse
    assert is_human(task_of(repo, created.id)) is follow_up_human
    assert created.assignee == ("human" if follow_up_human else "agent")
    assert is_human(task_of(repo, T01)) is dependency_human
    if reuse:
        assert TODO_STEP not in backlog_of(repo).by_id
    else:
        assert [task.id for task in backlog_of(repo).by_id[TODO_STEP].tasks] == [created.id]
    assert outcome.warnings == []


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
    assert outcome.created[0].assignee == ("human" if human else "agent")


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


def test_cancelled_follow_up_does_not_block_again(repo: Path) -> None:
    # a retry replays the follow-ups of the first attempt: the cancelled one is waived
    wf = workflow_run(follow_ups=[follow_up(blocks=True)])
    first = record(repo, T01, "run-1", wf)
    new_id = first.created[0].id
    edit_task(repo, new_id, status="cancelled")
    link_task(repo, T01, depends_on=[new_id], remove=True)
    commit_backlog(repo, "waive")
    again = record(repo, T01, "run-1", wf)
    assert again.created[0].id == new_id and again.created[0].existed
    assert again.blocked_by == []
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


@pytest.mark.parametrize("mode", ["direct", "pr-manual", "pr-auto"])
def test_follow_up_run_leaves_checkout_clean_and_pullable(
    repo: Path, script: Script, tmp_path: Path, mode: str
) -> None:
    config = repo / ".factory/config.yaml"
    target, _, merge = mode.partition("-")
    write(
        repo,
        ".factory/config.yaml",
        config.read_text(encoding="utf-8")
        + f"base_changes: {target}\nbase_pr_merge: {merge or 'manual'}\n",
    )
    git(repo, "commit", "-q", "-am", "configure publishing")
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "-u", "origin", "main")
    planner_reports(script, follow_ups=[follow_up().model_dump()])

    result = run_task(repo, T01)

    assert result.ok, (result.run.error, result.pr_error)
    assert result.follow_ups is not None and result.follow_ups.committed
    assert git(repo, "status", "--porcelain") == ""
    if target == "pr":
        assert result.follow_ups.created[0].id not in backlog_of(repo).by_id
        # A reviewer merges a manual PR; auto may already have merged remotely
        # while the running task prevented the local base from advancing.
        git(repo, "push", "-q", "origin", "factory-backlog/1:main")
    git(repo, "pull", "--ff-only")
    assert git(repo, "status", "--porcelain") == ""
    assert result.follow_ups.created[0].id in backlog_of(repo).by_id


def test_follow_up_publish_failure_leaves_checkout_untouched(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.providers import publish
    from aifactory.providers.base import ProviderError

    def rejected(*args: Any, **kwargs: Any) -> Any:
        raise ProviderError("push_failed", "rejected")

    monkeypatch.setattr(publish, "publish_direct", rejected)
    before = git(repo, "rev-parse", "HEAD")
    outcome = record(repo, T01, "run-1", workflow_run(follow_ups=[follow_up(blocks=True)]))

    assert not outcome.committed and outcome.warnings
    assert git(repo, "rev-parse", "HEAD") == before
    assert git(repo, "status", "--porcelain") == ""
    assert task_of(repo).depends_on == []
    assert TODO_STEP not in backlog_of(repo).by_id


def test_follow_up_preserves_unrelated_worktree_and_index_changes(repo: Path) -> None:
    path = repo / task_of(repo, T02).path
    path.write_text(path.read_text(encoding="utf-8") + "\nLocal note.\n", encoding="utf-8")
    git(repo, "add", str(path))
    write(repo, "README.md", "local readme\n")
    staged = git(repo, "diff", "--cached")
    unstaged = git(repo, "diff")

    outcome = record(repo, T01, "run-1", workflow_run(follow_ups=[follow_up()]))

    assert outcome.committed and outcome.warnings == []
    assert git(repo, "diff", "--cached") == staged
    assert git(repo, "diff") == unstaged
    assert "Local note." not in git(repo, "show", f"HEAD:{task_of(repo, T02).path}")


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
