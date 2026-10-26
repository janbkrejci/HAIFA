"""Follow-up ID allocation and merge repair against a fresh target (offline Git)."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier

import pytest
from run_repo import SPEC, T01, T02, Script, commit_all, fake_env, git, make_run_repo, ok, write
from test_followups import follow_up, workflow_run

from aifactory.backlog import Task, check_backlog, link_task, load_backlog
from aifactory.config import ProjectSettings, load_run_config
from aifactory.providers import CHECKS_NONE, ChecksStatus, ProviderError, PullRequest, publish
from aifactory.providers import git as pgit
from aifactory.providers.local import LocalProvider
from aifactory.review import ReviewError, approve_task
from aifactory.review.automerge import _hosting_and_merge
from aifactory.run import TaskRunStore, run_task
from aifactory.run.followups import (
    _contents,
    _record,
    _snapshot,
    advance_pr,
    follow_up_marker,
    publication_lock,
    reconcile_ids,
    record,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_run_repo(tmp_path / "repo")


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> Iterator[Script]:
    yield from fake_env(monkeypatch)


def candidate(
    repo: Path, source: str, title: str, *, linked: bool = False, blocking: bool = True
) -> tuple[publish.PublishPlan, str]:
    rc = load_run_config(repo)
    with _snapshot(repo, rc.commit, rc.config.settings) as stage:
        config = stage / ".factory/config.yaml"
        config.parent.mkdir()
        config.write_bytes((repo / ".factory/config.yaml").read_bytes())
        outcome = _record(
            stage,
            source,
            title,
            workflow_run(follow_ups=[follow_up(title, blocks=blocking)]),
        )
        new_id = outcome.created[0].id
        if linked:
            second = _record(stage, new_id, "child", workflow_run(follow_ups=[follow_up("Child")]))
            link_task(stage, second.created[0].id, depends_on=[new_id])
        files = publish.plan_contents(repo, rc.commit, _contents(stage))
    return publish.PublishPlan("main", rc.commit, "pr", tuple(files), (), "test"), new_id


def open_pr(
    repo: Path,
    provider: LocalProvider,
    settings: ProjectSettings,
    plan: publish.PublishPlan,
) -> publish.PublishResult:
    return publish.publish_pr(
        repo,
        provider=provider,
        settings=settings,
        plan=plan,
        message="Follow-ups",
        body="Follow-ups",
        prefix="factory-backlog/",
    )


def finish(
    repo: Path,
    provider: LocalProvider,
    settings: ProjectSettings,
    plan: publish.PublishPlan,
    result: publish.PublishResult,
) -> publish.PublishResult:
    return publish.finish_pr(
        repo,
        provider=provider,
        settings=settings,
        plan=plan,
        result=result,
        message="Follow-ups",
        store=None,
        materialize=True,
        command="follow-ups",
    )


def test_concurrent_records_allocate_distinct_ids(repo: Path) -> None:
    barrier = Barrier(2)

    def create(source: str) -> str:
        barrier.wait(timeout=10)
        outcome = record(repo, source, source, workflow_run(follow_ups=[follow_up(source)]))
        assert outcome.committed and not outcome.warnings
        return outcome.created[0].id

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = list(executor.map(create, [T01, T02]))
    assert set(ids) == {"M01-TODO-T01", "M01-TODO-T02"}
    assert check_backlog(load_backlog(repo)) == []
    assert git(repo, "status", "--porcelain") == ""


def test_stale_run_uses_fetched_target_without_moving_its_worktree(
    repo: Path, tmp_path: Path
) -> None:
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", "-q", str(origin))
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "origin", "main")
    old = git(repo, "rev-parse", "HEAD")
    stale = tmp_path / "stale"
    git(repo, "worktree", "add", "--detach", str(stale), old)
    plan, _ = candidate(repo, T01, "Other run")
    remote_head = pgit.commit_tree_with(repo, old, publish._changes(repo, plan.files), "Other run")
    pgit.push_ref(repo, "origin", remote_head, "main")
    assert git(repo, "rev-parse", "main") == old

    outcome = record(stale, T02, "stale", workflow_run(follow_ups=[follow_up("Stale run")]))

    assert outcome.committed and not outcome.warnings
    assert outcome.created[0].id == "M01-TODO-T02"
    assert git(stale, "rev-parse", "HEAD") == old
    assert git(stale, "status", "--porcelain") == ""
    assert git(origin, "rev-parse", "main") == git(repo, "rev-parse", "main")
    backlog = load_backlog(repo)
    assert check_backlog(backlog) == []
    assert backlog.by_id["M01-TODO-T01"].title == "Other run"


def test_concurrent_prs_renumber_and_rewrite_only_branch_references(repo: Path) -> None:
    settings = load_run_config(repo).config.settings.model_copy(update={"base_pr_merge": "auto"})
    provider = LocalProvider(repo, settings)
    first_plan, old_id = candidate(repo, T01, "First")
    second_plan, _ = candidate(repo, T02, "Second", linked=True)
    first = open_pr(repo, provider, settings, first_plan)
    second = open_pr(repo, provider, settings, second_plan)

    assert finish(repo, provider, settings, first_plan, first).merged
    repaired = finish(repo, provider, settings, second_plan, second)

    assert repaired.merged and repaired.advanced and not repaired.warnings
    assert repaired.renamed_ids == {old_id: "M01-TODO-T03"}
    backlog = load_backlog(repo)
    assert check_backlog(backlog) == []
    original = backlog.by_id[old_id]
    renamed = backlog.by_id["M01-TODO-T03"]
    child = backlog.by_id["M01-TODO-T02"]
    assert isinstance(original, Task) and isinstance(renamed, Task) and isinstance(child, Task)
    assert original.title == "First" and original.related == [T01]
    assert follow_up_marker(T01) in original.body
    assert renamed.title == "Second" and renamed.related == [T02]
    assert child.related == child.depends_on == [renamed.id]
    assert follow_up_marker(renamed.id) in child.body
    source = backlog.by_id[T02]
    assert isinstance(source, Task) and source.depends_on == [T01, renamed.id]
    assert git(repo, "status", "--porcelain") == ""


def test_unrepairable_merge_stays_open_with_reason(repo: Path) -> None:
    settings = load_run_config(repo).config.settings.model_copy(update={"base_pr_merge": "auto"})
    provider = LocalProvider(repo, settings)
    first_plan, _ = candidate(repo, T01, "First")
    second_plan, _ = candidate(repo, T01, "Second")
    first = open_pr(repo, provider, settings, first_plan)
    second = open_pr(repo, provider, settings, second_plan)
    assert finish(repo, provider, settings, first_plan, first).merged
    before = git(repo, "rev-parse", "main")

    refused = finish(repo, provider, settings, second_plan, second)

    assert not refused.merged
    assert "follow_up_collision" in " ".join(refused.warnings)
    assert git(repo, "rev-parse", "main") == before
    assert git(repo, "rev-parse", str(second.branch)) == second.commit


def test_fetch_failure_does_not_use_stale_ids(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan, _ = candidate(repo, T01, "New")
    head = pgit.commit_tree_with(repo, plan.base_sha, publish._changes(repo, plan.files), "New")
    monkeypatch.setattr(pgit, "has_remote", lambda *args: True)

    def fail(*args: object) -> None:
        raise ProviderError("fetch_failed", "offline")

    monkeypatch.setattr(pgit, "fetch", fail)
    with publication_lock(repo), pytest.raises(ProviderError, match="offline"):
        reconcile_ids(repo, head, "main", load_run_config(repo).config.settings)
    assert git(repo, "rev-parse", "main") == plan.base_sha


def test_task_approval_rechecks_ci_after_target_adds_colliding_id(
    repo: Path, script: Script
) -> None:
    settings = load_run_config(repo).config.settings
    checked: list[str] = []

    class RacingProvider(LocalProvider):
        def checks(self, pr: PullRequest) -> ChecksStatus:
            checked.append(git(repo, "rev-parse", pr.branch))
            if len(checked) == 1:
                other = record(
                    repo, T02, "other", workflow_run(follow_ups=[follow_up("Other run")])
                )
                assert other.committed
            return ChecksStatus(CHECKS_NONE)

    provider = RacingProvider(repo, settings)
    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add spec"))
    run = run_task(repo, T01, provider=provider)
    assert run.ok and run.pr is not None
    branch = run.pr.branch
    head = git(repo, "rev-parse", branch)
    plan, _ = candidate(repo, T01, "This run", blocking=False)
    candidate_head = pgit.commit_tree_with(
        repo, head, publish._changes(repo, plan.files), "Follow-up"
    )
    advance_pr(repo, branch, head, candidate_head)

    approved = approve_task(repo, T01, provider=provider)

    assert approved.merge_sha
    assert len(checked) == 2 and checked[0] != checked[1]
    backlog = load_backlog(repo)
    assert check_backlog(backlog) == []
    assert backlog.by_id["M01-TODO-T01"].title == "Other run"
    assert backlog.by_id["M01-TODO-T02"].title == "This run"


@pytest.mark.parametrize("auto", [False, True])
def test_same_path_follow_up_collision_is_repaired_before_mergeability_rejection(
    repo: Path, script: Script, auto: bool
) -> None:
    settings = load_run_config(repo).config.settings
    provider = LocalProvider(repo, settings)
    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add spec"))
    run = run_task(repo, T01, provider=provider)
    assert run.ok and run.pr is not None
    branch = run.pr.branch
    head = git(repo, "rev-parse", branch)
    plan, _ = candidate(repo, T01, "Shared title", blocking=False)
    candidate_head = pgit.commit_tree_with(
        repo, head, publish._changes(repo, plan.files), "Follow-up"
    )
    advance_pr(repo, branch, head, candidate_head)
    other = record(repo, T02, "other", workflow_run(follow_ups=[follow_up("Shared title")]))
    assert other.committed

    if auto:
        rc = load_run_config(repo)
        task = load_backlog(repo).by_id[T01]
        assert isinstance(task, Task)
        outcome = _hosting_and_merge(repo, run.pr, task, provider, rc, repo)
        assert outcome.merged, (outcome.code, outcome.reason)
    else:
        assert approve_task(repo, T01, provider=provider).merge_sha

    backlog = load_backlog(repo)
    assert check_backlog(backlog) == []
    original = backlog.by_id["M01-TODO-T01"]
    repaired = backlog.by_id["M01-TODO-T02"]
    assert isinstance(original, Task) and isinstance(repaired, Task)
    assert original.related == [T02] and repaired.related == [T01]


def test_unrepairable_task_pr_records_dashboard_reason(repo: Path, script: Script) -> None:
    provider = LocalProvider(repo, load_run_config(repo).config.settings)
    script.on("planner", lambda wt: write(wt, SPEC, "# spec\n"))
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add spec"))
    run = run_task(repo, T01, provider=provider)
    assert run.ok and run.pr is not None
    branch = run.pr.branch
    head = git(repo, "rev-parse", branch)
    plan, _ = candidate(repo, T01, "This run", blocking=False)
    changes = publish._changes(repo, plan.files)
    changes.append(("README.md", "100644", pgit.hash_blob(repo, b"PR change\n")))
    candidate_head = pgit.commit_tree_with(repo, head, changes, "Follow-up and README")
    advance_pr(repo, branch, head, candidate_head)
    other = record(repo, T02, "other", workflow_run(follow_ups=[follow_up("Other run")]))
    assert other.committed
    write(repo, "README.md", "Target change\n")
    before = commit_all(repo, "Concurrent target edit")

    with pytest.raises(ReviewError) as info:
        approve_task(repo, T01, provider=provider)

    assert info.value.code == "follow_up_collision"
    assert git(repo, "rev-parse", "main") == before
    assert git(repo, "rev-parse", branch) == candidate_head
    with closing(TaskRunStore(repo / ".factory/trace.db")) as store:
        saved = store.pr_for_branch(branch)
        assert saved is not None and saved.state == "open"
        assert saved.auto_merge_error and "follow_up_collision" in saved.auto_merge_error


def test_automerge_keeps_unrelated_conflict_open(repo: Path, script: Script) -> None:
    provider = LocalProvider(repo, load_run_config(repo).config.settings)
    script.on("planner", lambda wt: write(wt, SPEC, "# PR spec\n"))
    script.add("planner", ok(artifacts=[SPEC], commit_message="Add spec"))
    run = run_task(repo, T01, provider=provider)
    assert run.ok and run.pr is not None
    head = git(repo, "rev-parse", run.pr.branch)
    write(repo, SPEC, "# Conflicting target spec\n")
    before = commit_all(repo, "Concurrent target spec")
    rc = load_run_config(repo)
    task = load_backlog(repo).by_id[T01]
    assert isinstance(task, Task)

    outcome = _hosting_and_merge(repo, run.pr, task, provider, rc, repo)

    assert not outcome.merged and outcome.code == "conflict"
    assert git(repo, "rev-parse", "main") == before
    assert git(repo, "rev-parse", run.pr.branch) == head
    remaining = load_backlog(repo).by_id[T01]
    assert isinstance(remaining, Task) and remaining.status == "todo"


def test_unchanged_backlog_does_not_need_snapshots(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rc = load_run_config(repo)
    head = pgit.commit_tree_with(
        repo,
        rc.commit,
        [("README.md", "100644", pgit.hash_blob(repo, b"Documentation change\n"))],
        "Update documentation",
    )

    def unexpected(*args: object) -> None:
        raise AssertionError("unchanged backlog must not be extracted")

    monkeypatch.setattr("aifactory.run.followups._snapshot", unexpected)
    with publication_lock(repo):
        assert reconcile_ids(repo, head, "main", rc.config.settings) == (head, {})


def test_modified_task_id_still_checks_for_duplicates(repo: Path) -> None:
    rc = load_run_config(repo)
    task = load_backlog(repo).by_id[T02]
    assert isinstance(task, Task)
    content = (repo / task.path).read_bytes().replace(T02.encode(), T01.encode(), 1)
    head = pgit.commit_tree_with(
        repo, rc.commit, [(task.path, "100644", pgit.hash_blob(repo, content))], "Duplicate ID"
    )

    with publication_lock(repo), pytest.raises(ProviderError, match="duplicate"):
        reconcile_ids(repo, head, "main", rc.config.settings)
