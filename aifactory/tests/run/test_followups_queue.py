"""Follow-ups enter the manual queue through real runs, retries and resolves."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from run_repo import T01, Script, commit_all, fake_env, make_run_repo, write
from test_followups import follow_up, planner_reports, workflow_run
from test_task_resolve import MODEL, ResolveCode, resolver, run_both, settle
from test_task_resolve import tester as plan_resolve_tests

from aifactory.backlog import commit_backlog, edit_task, link_task, load_backlog
from aifactory.review import resolve_task
from aifactory.run import TaskRunStore, run_task
from aifactory.run.followups import record
from aifactory.run.queue import select_ready
from aifactory.run.retry import retry_run
from aifactory.run.task import _record_follow_ups


@pytest.fixture(autouse=True)
def offline_triage(monkeypatch: pytest.MonkeyPatch) -> None:
    from aifactory.run import triage

    def unavailable(*args: object, **kwargs: object) -> None:
        raise triage.TriageUnavailable("Offline legacy follow-up scenario")

    monkeypatch.setattr(triage, "ask_triager", unavailable)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


@pytest.fixture(name="script")
def script_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


def queue_store(repo: Path) -> TaskRunStore:
    return TaskRunStore(repo / ".factory/trace.db")


@pytest.mark.parametrize("publish_pr", [False, True])
def test_run_queues_only_new_agents_in_creation_order(
    repo: Path, script: Script, publish_pr: bool
) -> None:
    existing = follow_up("Already filed")
    previous = record(repo, T01, "previous", workflow_run(follow_ups=[existing]))
    old_id = previous.created[0].id
    if publish_pr:
        config = repo / ".factory/config.yaml"
        config.write_text(config.read_text() + "base_changes: pr\nbase_pr_merge: manual\n")
        commit_all(repo, "Publish backlog through PRs")
    human = follow_up("Shared title").model_copy(update={"for_human": True})
    inferred = follow_up("Protected work").model_copy(update={"writes": [".factory/config.yaml"]})
    planner_reports(
        script,
        follow_ups=[
            existing.model_dump(),
            follow_up("Shared title").model_dump(),
            human.model_dump(),
            follow_up("Second agent").model_dump(),
            inferred.model_dump(),
        ],
    )
    store = queue_store(repo)
    try:
        store.set_queue_order([T01, old_id])
        result = run_task(repo, T01)
        assert result.ok, (result.run.error, result.pr_error)
        assert result.follow_ups is not None and result.follow_ups.committed
        reused, first, person, second, protected = result.follow_ups.created
        assert reused.existed and reused.id == old_id
        assert person.assignee == protected.assignee == "human"
        assert store.queue_prefs().order == (first.id, second.id, T01, old_id)
        backlog = load_backlog(repo)
        if publish_pr:
            assert first.id not in backlog.by_id
        else:
            selection = select_ready(
                backlog, open_pr=lambda _: None, running=lambda _: None, prefs=store.queue_prefs()
            )
            assert selection.next is not None and selection.next.id == first.id
    finally:
        store.close()


def test_queue_failure_warns_without_failing_run(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    def rejected(self: TaskRunStore, task_ids: list[str]) -> None:
        raise sqlite3.OperationalError("queue unavailable")

    monkeypatch.setattr(TaskRunStore, "queue_front", rejected)
    planner_reports(script, follow_ups=[follow_up().model_dump()])
    result = run_task(repo, T01)
    assert result.ok, result.run.error
    assert result.follow_ups is not None and result.follow_ups.committed
    warning = "follow-ups not queued: queue unavailable"
    assert warning in result.follow_ups.warnings and warning in result.warnings


def test_retry_queues_new_followups_without_moving_existing(repo: Path, script: Script) -> None:
    original = follow_up("Original")
    planner_reports(
        script, follow_ups=[original.model_copy(update={"blocks_task": True}).model_dump()]
    )
    first = run_task(repo, T01)
    assert not first.ok and first.follow_ups is not None
    old_id = first.follow_ups.created[0].id
    edit_task(repo, old_id, status="cancelled")
    link_task(repo, T01, depends_on=[old_id], remove=True)
    commit_backlog(repo, "Waive original blocker")
    store = queue_store(repo)
    try:
        store.set_queue_order([T01, old_id])
        planner_reports(script, follow_ups=[original.model_dump(), follow_up("New").model_dump()])
        retried = retry_run(repo, T01, from_phase="plan")
        assert retried.ok, (retried.run.error, retried.pr_error)
        assert retried.follow_ups is not None
        reused, new = retried.follow_ups.created
        assert reused.existed and reused.id == old_id
        assert not new.existed
        assert store.queue_prefs().order == (new.id, T01, old_id)
    finally:
        store.close()


def test_blocker_priority_stays_ahead_of_manual_followups(repo: Path, script: Script) -> None:
    planner_reports(
        script,
        follow_ups=[
            follow_up("Ordinary").model_dump(),
            follow_up("Blocker", blocks=True).model_dump(),
        ],
    )
    result = run_task(repo, T01)
    assert not result.ok and result.follow_ups is not None
    ordinary, blocker = result.follow_ups.created
    store = queue_store(repo)
    try:
        prefs = store.queue_prefs()
        assert prefs.order == (ordinary.id, blocker.id)
        assert prefs.priority[0].task_id == T01
        assert prefs.priority[0].blockers == (blocker.id,)
        selection = select_ready(
            load_backlog(repo), open_pr=lambda _: None, running=lambda _: None, prefs=prefs
        )
        assert selection.next is not None and selection.next.id == blocker.id
    finally:
        store.close()


def test_resolve_queues_followups_without_blocking(repo: Path, script: Script) -> None:
    from run_repo import T02

    write(repo, MODEL, "VALUE = 0\n")
    commit_all(repo, "Model for resolve")
    run_both(repo, script)
    resolver(
        script,
        settle,
        changed_files=[MODEL],
        commit_message="Resolve model conflict",
        follow_ups=[
            follow_up("After resolve", blocks=True).model_dump(),
            follow_up("Human").model_copy(update={"for_human": True}).model_dump(),
        ],
    )
    plan_resolve_tests(script)
    result = resolve_task(repo, T02, code=ResolveCode([True]))
    assert result.ok, (result.run.error, result.pr_error)
    assert result.follow_ups is not None and result.follow_ups.blocked_by == []
    agent, human = result.follow_ups.created
    assert not agent.blocks and human.assignee == "human"
    store = queue_store(repo)
    try:
        assert store.queue_prefs().order == (agent.id,)
    finally:
        store.close()


def test_unpublished_followups_are_not_queued(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aifactory.providers import ProviderError, publish

    planner_reports(script)
    result = run_task(repo, T01)
    assert result.ok

    def rejected(*args: object, **kwargs: object) -> None:
        raise ProviderError("push_failed", "rejected")

    monkeypatch.setattr(publish, "publish_direct", rejected)
    store = queue_store(repo)
    try:
        store.set_queue_order([T01])
        follow, warnings, blockers = _record_follow_ups(
            repo, store, result.run, workflow_run(follow_ups=[follow_up()])
        )
        assert follow is not None and not follow.committed
        assert warnings and blockers == []
        assert store.queue_prefs().order == (T01,)
    finally:
        store.close()


def test_mixed_triage_only_queues_new_agent_tasks(
    repo: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    from run_repo import T02

    from aifactory.run import triage
    from aifactory.run.triage import Decision

    planner_reports(script)
    result = run_task(repo, T01)
    assert result.ok
    items = [
        follow_up("New agent"),
        follow_up("Already covered"),
        follow_up("Addition"),
        follow_up("Change assignment"),
        follow_up("Human work").model_copy(update={"for_human": True}),
    ]
    choices = [
        Decision(follow_up_id="f1", action="new", reason="Separate work"),
        Decision(follow_up_id="f2", action="covered", reason="Covered", task_id=T02),
        Decision(
            follow_up_id="f3",
            action="extend",
            reason="Additive",
            task_id=T02,
            addition="Also document `src/app/model.py`.",
            addition_writes=["src/app/model.py"],
        ),
        Decision(
            follow_up_id="f4",
            action="decide",
            reason="Needs a person",
            task_id=T02,
            proposal="Reduce the original assignment",
        ),
        Decision(follow_up_id="f5", action="new", reason="Human work"),
    ]
    # Recommendations are keyed by fN, independently of their return order.
    monkeypatch.setattr(triage, "ask_triager", lambda *args, **kwargs: list(reversed(choices)))
    store = queue_store(repo)
    try:
        store.set_queue_order([T01, T02])
        outcome, warnings, blockers = _record_follow_ups(
            repo, store, result.run, workflow_run(follow_ups=items)
        )
        assert outcome is not None and outcome.committed, warnings
        assert not warnings and not blockers
        assert sorted(c.decision for c in outcome.created) == [
            "covered",
            "decide",
            "extend",
            "new",
            "new",
        ]
        [new_agent] = [c for c in outcome.created if c.decision == "new" and c.assignee == "agent"]
        assert store.queue_prefs().order == (new_agent.id, T01, T02)
    finally:
        store.close()
