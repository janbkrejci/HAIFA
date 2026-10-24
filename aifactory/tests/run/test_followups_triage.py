"""Apply offline triage recommendations against the fresh backlog under the run lock."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from run_repo import T01, T02, commit_all, make_run_repo
from test_followups import TODO_STEP, follow_up, task_of, workflow_run

from aifactory.backlog import Backlog, check_backlog, edit_task, link_task, load_backlog
from aifactory.run import TaskRunStore, triage
from aifactory.run.followups import FollowUpOutcome, Reported
from aifactory.run.store import TaskRunRow
from aifactory.run.task import _record_follow_ups
from aifactory.run.triage import Decision

TARGET = "M01-S01-T03"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = make_run_repo(tmp_path / "repo")
    target = root / f"backlog/M01-core/S01-model/{TARGET}-target.md"
    target.write_text(
        f"---\nid: {TARGET}\ntitle: Existing work\nstatus: todo\n"
        "writes: [src/app/]\nworkflow: plan-commit\nrelated: []\n---\n\n"
        "## Zadání\nKeep the entire assignment.\n\n## Běhy\nOld history.\n\n"
        "## Extra\nKeep this too.\n",
        encoding="utf-8",
    )
    commit_all(root, "Independent target")
    return root


def choice(action: str, target: str = TARGET, fid: str = "f1") -> Decision:
    fields: dict[str, Any] = dict(follow_up_id=fid, action=action, reason="Triage reason")
    if action != "new":
        fields["task_id"] = target
    if action == "extend":
        fields.update(
            addition="Also verify `src/app/index.py`.", addition_writes=["src/app/index.py"]
        )
    if action == "decide":
        fields["proposal"] = "Drop the original acceptance criterion."
    return Decision.model_validate(fields)


def apply(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    choices: list[Decision] | Exception,
    *,
    items: list[Any] | None = None,
    blocking: bool = True,
    run_id: str = "run-1",
) -> FollowUpOutcome:
    def ask(*args: object, **kwargs: object) -> list[Decision]:
        if isinstance(choices, Exception):
            raise choices
        return choices

    monkeypatch.setattr(triage, "ask_triager", ask)
    with closing(TaskRunStore(repo / ".factory/trace.db")) as store:
        row = cast(TaskRunRow, SimpleNamespace(task_id=T01, note=None, run_id=run_id))
        result, warnings, blockers = _record_follow_ups(
            repo,
            store,
            row,
            workflow_run(follow_ups=items or [follow_up(blocks=True)]),
            blocking=blocking,
        )
        assert result is not None, warnings
        assert warnings == result.warnings and blockers == result.blocked_by
        return result


@pytest.mark.parametrize("action", ["covered", "extend", "decide", "new"])
@pytest.mark.parametrize("blocking", [False, True])
def test_actions_and_blockers(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    blocking: bool,
) -> None:
    path = repo / task_of(repo, TARGET).path
    before = path.read_bytes()
    outcome = apply(repo, monkeypatch, [choice(action)], blocking=blocking)
    [created] = outcome.created
    assert created.decision == created.to_json()["decision"] == action
    assert outcome.to_json()["created"] == [created.to_json()]
    assert created.existed == (action in ("covered", "extend"))
    assert outcome.blocked_by == ([created.id] if blocking else [])
    assert task_of(repo).depends_on == ([created.id] if blocking else [])
    backlog = load_backlog(repo)
    assert check_backlog(backlog) == []
    if action in ("covered", "extend"):
        assert created.id == TARGET and TODO_STEP not in backlog.by_id
    else:
        assert created.id.startswith(TODO_STEP)
        filed = task_of(repo, created.id)
        assert filed.related == ([T01, TARGET] if action == "decide" else [T01])
        assert created.assignee == ("human" if action == "decide" else "agent")
        if action == "decide":
            assert "Drop the original" in filed.body and "Triage reason" in filed.body
    if action == "extend":
        assert path.read_bytes().startswith(before)
        assert "### Doplnění z běhu run-1 tasku" in path.read_text()
    else:
        assert path.read_bytes() == before
    with closing(TaskRunStore(repo / ".factory/trace.db")) as store:
        assert store.queue_prefs().order == ((created.id,) if action == "new" else ())


def test_two_extensions_survive_retry_and_reordered_replay(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [follow_up("First"), follow_up("Second")]
    path = repo / task_of(repo, TARGET).path
    before = path.read_bytes()
    first = apply(repo, monkeypatch, [choice("extend", fid=f"f{i}") for i in (1, 2)], items=items)
    after = path.read_bytes()
    assert after.startswith(before) and after.count(b"<!-- factory: extended-by=") == 2
    assert len(first.created) == 2
    again = apply(
        repo,
        monkeypatch,
        [
            choice("extend", fid=f"f{i}").model_copy(update={"addition": "Different wording"})
            for i in (1, 2)
        ],
        items=list(reversed(items)),
        run_id="retry-2",
    )
    assert all(c.existed for c in again.created)
    assert not again.committed and path.read_bytes() == after
    assert TODO_STEP not in load_backlog(repo).by_id


def test_decide_retry_is_idempotent(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = apply(repo, monkeypatch, [choice("decide")])
    again = apply(repo, monkeypatch, [choice("decide")], run_id="retry")
    assert first.created[0].id == again.created[0].id and again.created[0].existed
    assert not again.committed


@pytest.mark.parametrize("change", ["cancelled", "deleted", "human", "scope", "running"])
def test_rechecks_fresh_target_under_lock(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    depth = 0
    serialized = TaskRunStore.serialized

    @contextmanager
    def locked(self: TaskRunStore) -> Iterator[None]:
        nonlocal depth
        with serialized(self):
            depth += 1
            try:
                yield
            finally:
                depth -= 1

    def running(self: TaskRunStore, task_id: str) -> object:
        assert depth > 0
        return object() if change == "running" and task_id == TARGET else None

    def ask(
        root: Path, reported: Sequence[Reported], backlog: Backlog, **kwargs: object
    ) -> list[Decision]:
        assert depth == 0
        if change == "cancelled":
            edit_task(root, TARGET, status="cancelled")
        elif change == "deleted":
            (root / task_of(root, TARGET).path).unlink()
        elif change == "human":
            edit_task(root, TARGET, assignee="human")
        elif change == "scope":
            edit_task(root, TARGET, writes=["elsewhere/"])
        if change != "running":
            commit_all(root, "Concurrent backlog change")
        return [choice("extend")]

    monkeypatch.setattr(TaskRunStore, "serialized", locked)
    monkeypatch.setattr(TaskRunStore, "running", running)
    monkeypatch.setattr(triage, "ask_triager", ask)
    with closing(TaskRunStore(repo / ".factory/trace.db")) as store:
        row = cast(TaskRunRow, SimpleNamespace(task_id=T01, note=None, run_id="r"))
        result, warnings, _ = _record_follow_ups(
            repo,
            store,
            row,
            workflow_run(follow_ups=[follow_up(blocks=True)]),
        )
    assert result is not None and result.created[0].decision == "new", warnings
    assert any("no longer applies" in w for w in warnings)
    if change != "deleted":
        assert "extended-by" not in (repo / task_of(repo, TARGET).path).read_text()


@pytest.mark.parametrize("target", [T01, T02])
def test_covered_cannot_self_depend_or_create_cycle(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    result = apply(repo, monkeypatch, [choice("covered", target)])
    assert result.created[0].decision == "new"
    assert result.blocked_by == [result.created[0].id]
    assert check_backlog(load_backlog(repo)) == []


@pytest.mark.parametrize(
    "error", [triage.TriageUnavailable("missing triager"), RuntimeError("failed")]
)
def test_unavailable_triage_preserves_legacy_fallback(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    link_task(repo, T01, depends_on=[TARGET])
    commit_all(repo, "Existing blocker")

    def ask(*args: object, **kwargs: object) -> list[Decision]:
        raise error

    monkeypatch.setattr(triage, "ask_triager", ask)
    with closing(TaskRunStore(repo / ".factory/trace.db")) as store:
        row = cast(TaskRunRow, SimpleNamespace(task_id=T01, note=None, run_id="r"))
        result, warnings, blockers = _record_follow_ups(
            repo,
            store,
            row,
            workflow_run(
                follow_ups=[
                    follow_up("Existing work", blocks=True),
                    follow_up("New work", blocks=True),
                ]
            ),
        )
    assert result is not None
    assert result.created[0].id == TARGET and result.created[0].existed
    assert result.created[1].decision == "new" and not result.created[1].existed
    assert blockers == [c.id for c in result.created]
    assert any(str(error) in w for w in warnings)


def test_no_followups_never_calls_agent(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected(*args: object) -> list[Decision]:
        pytest.fail("No follow-ups to triage")

    monkeypatch.setattr(triage, "ask_triager", unexpected)
    with closing(TaskRunStore(repo / ".factory/trace.db")) as store:
        row = cast(TaskRunRow, SimpleNamespace(task_id=T01, note=None, run_id="r"))
        result, warnings, blockers = _record_follow_ups(repo, store, row, workflow_run())
    assert result is not None and not result.created and not warnings and not blockers


@pytest.mark.parametrize(
    "update",
    [
        {"for_human": True},
        {"writes": [".factory/config.yaml"]},
        {"writes": ["outside/file.py"]},
    ],
)
def test_extend_rejects_human_or_out_of_scope_work(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    update: dict[str, Any],
) -> None:
    path = repo / task_of(repo, TARGET).path
    before = path.read_bytes()
    result = apply(
        repo, monkeypatch, [choice("extend")], items=[follow_up().model_copy(update=update)]
    )
    assert result.created[0].decision == "new" and result.warnings
    assert path.read_bytes() == before


def test_explicit_new_is_not_overridden_by_matching_dependency_title(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    link_task(repo, T01, depends_on=[TARGET])
    commit_all(repo, "Existing dependency")
    result = apply(repo, monkeypatch, [choice("new")], items=[follow_up("Existing work")])
    assert result.created[0].id != TARGET and not result.created[0].existed
    assert result.created[0].decision == "new"


def test_extend_preserves_original_crlf(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = repo / task_of(repo, TARGET).path
    original = path.read_bytes().replace(b"\n", b"\r\n")
    path.write_bytes(original)
    commit_all(repo, "CRLF task")
    result = apply(repo, monkeypatch, [choice("extend")], blocking=False)
    assert result.created[0].decision == "extend"
    assert path.read_bytes().startswith(original)


@pytest.mark.parametrize("blocking", [False, True])
@pytest.mark.parametrize("recommendation", ["new", "unavailable", "covered", "extend", "decide"])
def test_persisted_extension_precedes_changed_recommendation(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    recommendation: str,
    blocking: bool,
) -> None:
    first = apply(repo, monkeypatch, [choice("extend")], blocking=blocking)
    path = repo / task_of(repo, TARGET).path
    after = path.read_bytes()
    other_path = repo / task_of(repo, T02).path
    other_before = other_path.read_bytes()
    choices: list[Decision] | Exception = (
        triage.TriageUnavailable("triager missing on retry")
        if recommendation == "unavailable"
        else [choice(recommendation, target=T02)]
    )
    if recommendation == "extend":
        assert isinstance(choices, list)
        choices = [
            choices[0].model_copy(
                update={
                    "addition": "Different suggestion in `outside/scope.py`.",
                    "addition_writes": ["outside/scope.py"],
                }
            )
        ]
    again = apply(repo, monkeypatch, choices, blocking=blocking, run_id="run-2")
    [created] = again.created
    assert created.id == first.created[0].id == TARGET
    assert created.decision == "extend" and created.existed
    assert again.blocked_by == ([TARGET] if blocking else [])
    assert not again.committed and path.read_bytes() == after
    assert other_path.read_bytes() == other_before
    assert TODO_STEP not in load_backlog(repo).by_id
    assert bool(again.warnings) == (recommendation == "unavailable")
    with closing(TaskRunStore(repo / ".factory/trace.db")) as store:
        assert store.queue_prefs().order == ()


@pytest.mark.parametrize("recommendation", ["new", "unavailable", "retarget"])
def test_two_persisted_extensions_survive_changed_reordered_replay(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    recommendation: str,
) -> None:
    items = [follow_up("First"), follow_up("Second")]
    apply(repo, monkeypatch, [choice("extend", fid=f"f{i}") for i in (1, 2)], items=items)
    path = repo / task_of(repo, TARGET).path
    after = path.read_bytes()
    choices: list[Decision] | Exception = (
        triage.TriageUnavailable("retry unavailable")
        if recommendation == "unavailable"
        else [
            choice("extend" if recommendation == "retarget" else "new", target=T02, fid=f"f{i}")
            for i in (1, 2)
        ]
    )
    again = apply(repo, monkeypatch, choices, items=list(reversed(items)), run_id="replay")
    assert len(again.created) == 2
    assert all(c.id == TARGET and c.existed and c.decision == "extend" for c in again.created)
    assert not again.committed and path.read_bytes() == after
    assert after.count(b"<!-- factory: extended-by=") == 2
    assert TODO_STEP not in load_backlog(repo).by_id


@pytest.mark.parametrize("change", ["cancelled", "done", "human", "scope", "running"])
def test_acknowledging_extension_does_not_reapply_to_changed_task(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    apply(repo, monkeypatch, [choice("extend")], blocking=False)
    if change == "done":
        path = repo / task_of(repo, TARGET).path
        path.write_bytes(path.read_bytes().replace(b"status: todo", b"status: done", 1))
    elif change == "cancelled":
        edit_task(repo, TARGET, status="cancelled")
    elif change == "human":
        edit_task(repo, TARGET, assignee="human")
    elif change == "scope":
        edit_task(repo, TARGET, writes=["elsewhere/"])
    if change != "running":
        commit_all(repo, "Changed applied task")
    else:
        monkeypatch.setattr(TaskRunStore, "running", lambda self, task_id: object())
    path = repo / task_of(repo, TARGET).path
    before = path.read_bytes()
    again = apply(repo, monkeypatch, [choice("extend")], blocking=False, run_id="retry")
    assert again.created[0].id == TARGET and again.created[0].decision == "extend"
    assert again.created[0].existed and not again.committed
    assert again.created[0].assignee == ("human" if change == "human" else "agent")
    assert not again.warnings and path.read_bytes() == before
    assert TODO_STEP not in load_backlog(repo).by_id


def test_acknowledged_extension_cannot_create_new_dependency_cycle(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply(repo, monkeypatch, [choice("extend")], blocking=False)
    link_task(repo, TARGET, depends_on=[T01])
    commit_all(repo, "Applied target now depends on source")
    before = (repo / task_of(repo, TARGET).path).read_bytes()
    again = apply(repo, monkeypatch, [choice("new")], run_id="blocking-retry")
    assert again.created[0].id == TARGET and again.created[0].decision == "extend"
    assert again.created[0].existed and not again.committed
    assert again.warnings and again.blocked_by
    assert task_of(repo).depends_on == []
    assert TODO_STEP not in load_backlog(repo).by_id
    assert check_backlog(load_backlog(repo)) == []
    assert (repo / task_of(repo, TARGET).path).read_bytes() == before


def test_acknowledged_extension_can_add_safe_blocker_without_reapplying(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply(repo, monkeypatch, [choice("extend")], blocking=False)
    path = repo / task_of(repo, TARGET).path
    before = path.read_bytes()
    again = apply(repo, monkeypatch, [choice("new")], run_id="blocking-retry")
    assert again.created[0].id == TARGET and again.created[0].decision == "extend"
    assert again.created[0].existed and again.committed
    assert again.blocked_by == [TARGET] and task_of(repo).depends_on == [TARGET]
    assert path.read_bytes() == before and not again.warnings
    assert TODO_STEP not in load_backlog(repo).by_id
    with closing(TaskRunStore(repo / ".factory/trace.db")) as store:
        assert store.queue_prefs().order == ()


@pytest.mark.parametrize("explicit_empty", [True, False], ids=["empty-writes", "omitted-writes"])
def test_explicit_empty_writes_survive_collection_and_allow_no_file_extension(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    explicit_empty: bool,
) -> None:
    item = follow_up().model_copy(update={"writes": []}) if explicit_empty else follow_up()
    expected_writes: tuple[str, ...] | None = () if explicit_empty else None
    seen: list[tuple[str, ...] | None] = []
    addition = "Also explain the acceptance criteria without changing files."

    def ask(
        root: Path, reported: Sequence[Reported], backlog: Backlog, **kwargs: object
    ) -> list[Decision]:
        [report] = reported
        seen.append(report.writes)
        assert report.writes == expected_writes
        return [
            Decision(
                follow_up_id="f1",
                action="extend",
                reason="Clarify the existing assignment",
                task_id=TARGET,
                addition=addition,
                addition_writes=[],
            )
        ]

    monkeypatch.setattr(triage, "ask_triager", ask)
    path = repo / task_of(repo, TARGET).path
    before = path.read_bytes()
    with closing(TaskRunStore(repo / ".factory/trace.db")) as store:
        row = cast(
            TaskRunRow, SimpleNamespace(task_id=T01, note=None, run_id="read-only-follow-up")
        )
        result, warnings, blockers = _record_follow_ups(
            repo, store, row, workflow_run(follow_ups=[item])
        )
    assert seen == [expected_writes]
    assert result is not None and result.committed, warnings
    assert blockers == []
    [created] = result.created
    if explicit_empty:
        assert created.id == TARGET and created.decision == "extend" and created.existed
        assert path.read_bytes().startswith(before)
        assert addition in task_of(repo, TARGET).body
        assert TODO_STEP not in load_backlog(repo).by_id
        assert warnings == []
    else:
        assert created.id.startswith(TODO_STEP) and created.decision == "new"
        assert not created.existed and path.read_bytes() == before
        assert any("explicitly read-only reported writes=[]" in warning for warning in warnings)
    assert check_backlog(load_backlog(repo)) == []


@pytest.mark.parametrize("saved", [False, True])
def test_record_passes_run_binding(
    repo: Path, monkeypatch: pytest.MonkeyPatch, saved: bool
) -> None:
    from aifactory.run.task import override_note

    binding = {"harness": "codex", "model": "gpt-5.5", "thinking": "high"}
    seen: list[dict[str, Any]] = []

    def ask(*args: object, **kwargs: Any) -> list[Decision]:
        seen.append(kwargs)
        return [choice("covered")]

    monkeypatch.setattr(triage, "ask_triager", ask)
    with closing(TaskRunStore(repo / ".factory/trace.db")) as store:
        row = cast(
            TaskRunRow,
            SimpleNamespace(
                task_id=T01, run_id="r", note=override_note("retry", binding) if saved else "retry"
            ),
        )
        result, warnings, _ = _record_follow_ups(
            repo, store, row, workflow_run(follow_ups=[follow_up()])
        )
    assert result is not None and not warnings
    assert seen == [{"task_id": T01, "binding": binding if saved else None}]


def test_triager_uses_binding_after_quota_switch(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from aifactory.engine import agents
    from aifactory.engine.data_types import AgentResult
    from aifactory.harness import thinking
    from aifactory.harness.check import HarnessStatus
    from aifactory.run.task import override_note

    path = repo / task_of(repo, T01).path
    path.write_text(
        path.read_text().replace(
            "status: todo", "status: todo\nharness: claude\nmodel: sonnet\nthinking: medium", 1
        )
    )
    commit_all(repo, "Original task harness")
    monkeypatch.setattr(thinking, "codex_models", lambda: [])
    monkeypatch.setattr(
        triage, "check_harness", lambda name: HarnessStatus(name, "fake", "fake", "1")
    )
    seen: list[Any] = []

    def codex(request: Any, **kwargs: Any) -> AgentResult:
        seen.append(request)
        return AgentResult(
            text=json.dumps(
                {
                    "status": "success",
                    "summary": "Covered",
                    "decisions": [choice("covered").model_dump()],
                }
            ),
            returncode=0,
        )

    monkeypatch.setattr(agents.INTERFACES["codex"], "run", codex)
    binding = {"harness": "codex", "model": "gpt-5.5", "thinking": "high"}
    with closing(TaskRunStore(repo / ".factory/trace.db")) as store:
        row = cast(
            TaskRunRow,
            SimpleNamespace(task_id=T01, run_id="switched", note=override_note(None, binding)),
        )
        result, warnings, _ = _record_follow_ups(
            repo, store, row, workflow_run(follow_ups=[follow_up()])
        )
    assert result is not None and not warnings
    assert result.created[0].decision == "covered"
    [request] = seen
    assert request.model == "gpt-5.5" and request.thinking == "high"
