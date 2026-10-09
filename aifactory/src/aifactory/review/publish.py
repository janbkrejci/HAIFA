"""Push a successful run's branch and open (or update) its pull request.

``publish`` runs at the end of ``factory task run``. When it fails (``pr_error``), the
run stays succeeded, the error and the PR body it meant to send are kept on the run
(``task_runs.pr_error``, ``pr_body``) and ``publish_task`` (``factory task publish``)
tries again later: push, then open the PR, or adopt the open PR the hosting already has
for the branch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from aifactory.backlog import Task
from aifactory.config.settings import ProjectSettings
from aifactory.providers.base import OPEN, GitProvider, ProviderError, PullRequest
from aifactory.review.prbody import pr_body, pr_title
from aifactory.run.store import SUCCEEDED, TaskPrRow, TaskRunRow, TaskRunStore, _now
from aifactory.workflow import WorkflowRun


def run_pr_body(store: TaskRunStore, row: TaskRunRow, task: Task, wf: WorkflowRun | None) -> str:
    """The PR body for `row`: every successful run on its branch (a returned task adds runs)."""
    runs = [r for r in store.runs_on_branch(row.branch) if r.state == SUCCEEDED]
    return pr_body(task, runs, wf, store.db_path, row.branch)


def _save_new(
    store: TaskRunStore, row: TaskRunRow, provider: GitProvider, pr: PullRequest, body: str
) -> TaskPrRow:
    now = _now()
    saved = TaskPrRow(
        branch=row.branch,
        task_id=row.task_id,
        provider=provider.name,
        pr_id=pr.id,
        url=pr.url,
        base=pr.base or row.base,
        base_sha=row.base_sha,
        title=pr.title,
        body=body,
        state=OPEN,
        created_at=now,
        updated_at=now,
    )
    store.save_pr(saved)
    return saved


def _adopt(
    store: TaskRunStore, row: TaskRunRow, provider: GitProvider, pr: PullRequest, body: str
) -> TaskPrRow:
    """Record a PR the hosting has but ``task_prs`` does not, with the run's body."""
    provider.update_pr(pr, body)
    return _save_new(store, row, provider, pr, body)


def publish(
    main: Path,
    settings: ProjectSettings,
    store: TaskRunStore,
    row: TaskRunRow,
    task: Task,
    wf: WorkflowRun | None,
    provider: GitProvider,
    lease: str | None = None,
    *,
    body: str | None = None,
    adopt_first: bool = False,
) -> TaskPrRow:
    """Push the run's branch and open its PR, or update the PR the branch already has.

    The body covers every successful run on the branch (a returned task adds runs);
    `body` overrides it (``publish_task`` sends the body kept from the run).
    ``lease`` (the branch's tip before a resolve run rebased it) makes the push a
    force-with-lease push. An existing PR takes the run's ``base_sha``. A PR the
    hosting already has for the branch but ``task_prs`` does not is adopted: with
    `adopt_first` it is looked up before opening one, otherwise when opening fails.
    Raises ``ProviderError`` when the push or the hosting fails.
    """
    if body is None:
        body = run_pr_body(store, row, task, wf)
    worktree = Path(row.worktree)
    provider.push(worktree if worktree.is_dir() else main, row.branch, lease=lease)
    existing = store.pr_for_branch(row.branch)
    if existing is not None:
        provider.update_pr(existing.request(), body)
        store.update_pr(row.branch, body=body, state=OPEN, base_sha=row.base_sha)
        updated = store.pr_for_branch(row.branch)
        assert updated is not None
        return updated
    if adopt_first:
        found = provider.find_open_pr(row.branch)
        if found is not None:
            return _adopt(store, row, provider, found, body)
    title = pr_title(task)
    try:
        created = provider.create_pr(row.branch, title, body)
    except ProviderError:
        try:
            found = provider.find_open_pr(row.branch)
        except ProviderError:
            found = None
        if found is None:
            raise
        return _adopt(store, row, provider, found, body)
    return _save_new(store, row, provider, created, body)


@dataclass
class PublishResult:
    """``factory task publish``: the run that was published and its PR (or the error)."""

    run: TaskRunRow
    pr: TaskPrRow | None
    pr_error: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.pr is not None and self.pr_error is None

    def to_json(self) -> dict[str, object]:
        return {
            "run": self.run.to_json(),
            "pr": self.pr.to_json() if self.pr is not None else None,
            "pr_error": self.pr_error,
        }
