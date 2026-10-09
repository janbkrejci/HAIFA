"""Approve, return, resolve and clean task pull requests (steps 5 to 7 of "Běh úkolu").

* ``approve_task``: PR state -> one commit on the PR branch with ``status: done``
  and a ``## Běhy`` line -> push -> supported host approval -> merge ->
  ``task_prs`` merged -> ``base`` caught up with the remote -> worktrees removed.
  ``merged_by``
  (``operator``, or ``auto-merge`` from ``review/automerge.py``) goes to ``task_prs``.
* ``return_task``: a new run on the same branch with the note in the prompt;
  the PR body is updated when the run succeeds.
* ``resolve_task``: a PR that does not merge (``conflict``) gets a new run of
  the workflow ``resolve`` on its branch: rebase onto the current ``base``, the
  agent settles the conflicts in the conflicted files only, the suite runs, the
  branch is force-pushed with a lease and the PR updated. A failed run leaves
  the branch as it was before the rebase. Never started automatically.
* ``publish_task``: push the branch of the last succeeded run without a PR and open
  its PR (or adopt the open one the hosting has), as at the end of ``task run``.
* ``clean_worktrees``: remove worktrees of runs whose PR is merged or closed and
  of runs a newer run of the same task has superseded.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

from aifactory.backlog import Task, load_backlog
from aifactory.backlog.taskfile import mark_done, run_entry
from aifactory.config import ConfigError, RunConfig, load_run_config
from aifactory.providers import (
    CLOSED,
    CONFLICT,
    MERGED,
    OPEN,
    GitProvider,
    MergeFailed,
    ProviderError,
    PrStatus,
    get_provider,
)
from aifactory.providers import git as pgit
from aifactory.review.errors import ReviewError
from aifactory.review.prbody import branch_cost
from aifactory.review.publish import PublishResult, publish
from aifactory.run import gitops
from aifactory.run.errors import TaskRunError
from aifactory.run.resolve import RESOLVE_REVIEWED_WORKFLOW, RESOLVE_WORKFLOW
from aifactory.run.store import (
    MERGED_BY_OPERATOR,
    RUNNING,
    STARTED_MANUAL,
    SUCCEEDED,
    TaskPrRow,
    TaskRunStore,
    _now,
    already_running,
)
from aifactory.run.task import TaskRunResult, run_task
from aifactory.workflow import CodeRunner


@dataclass
class ApproveResult:
    task_id: str
    pr: TaskPrRow
    merge_sha: str | None
    strategy: str
    reviewed: bool  # True only for a successful host approval
    base_sha: str | None
    removed_worktrees: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    merged_by: str = MERGED_BY_OPERATOR

    def to_json(self) -> dict[str, object]:
        return {
            "ok": True,
            "task_id": self.task_id,
            "pr": self.pr.to_json(),
            "merge_sha": self.merge_sha,
            "merged_by": self.merged_by,
            "strategy": self.strategy,
            "reviewed": self.reviewed,
            "base_sha": self.base_sha,
            "removed_worktrees": list(self.removed_worktrees),
            "warnings": list(self.warnings),
        }


@dataclass
class CleanResult:
    removed: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, object]:
        return {"ok": True, "removed": list(self.removed), "warnings": list(self.warnings)}


@dataclass
class _Ctx:
    main: Path
    rc: RunConfig
    store: TaskRunStore
    provider: GitProvider


def _context(repo: Path, provider: GitProvider | None) -> _Ctx:
    try:
        main = gitops.main_root(repo)
    except TaskRunError as exc:
        raise ReviewError(exc.code, exc.message) from exc
    try:
        rc = load_run_config(main)
    except ConfigError as exc:
        raise ReviewError("invalid_config", str(exc)) from exc
    if provider is None:
        try:
            provider = get_provider(rc.config.settings, main)
        except ProviderError as exc:
            raise ReviewError(exc.code, exc.message) from exc
    try:
        store = TaskRunStore(rc.local.trace_db_path(main))
    except TaskRunError as exc:
        raise ReviewError(exc.code, exc.message) from exc
    return _Ctx(main, rc, store, provider)


def _record_state(ctx: _Ctx, row: TaskPrRow, status: PrStatus) -> None:
    """Write a closed or merged provider state into ``task_prs``."""
    if status.state == CLOSED:
        ctx.store.update_pr(row.branch, state=CLOSED)
    elif status.state == MERGED:
        ctx.store.update_pr(row.branch, state=MERGED, merged_at=_now(), merge_sha=status.merge_sha)


def _checked_pr(ctx: _Ctx, task_id: str) -> tuple[TaskPrRow, PrStatus]:
    """The task's newest PR if it is open at the provider; raise ``ReviewError`` otherwise."""
    row = ctx.store.latest_pr(task_id)
    if row is None:
        raise ReviewError("no_pr", f"task {task_id} has no pull request, run it first")
    if row.state != OPEN:
        raise ReviewError("pr_not_open", f"PR {row.url} is {row.state}")
    busy = ctx.store.running(task_id)
    if busy is not None:
        raise ReviewError(
            "already_running", f"task {task_id} is running: run {busy.run_id} on {busy.branch}"
        )
    status = ctx.provider.status(row.request())
    _record_state(ctx, row, status)
    if status.state == CLOSED:
        raise ReviewError("pr_not_open", f"PR {row.url} is closed")
    if status.state == MERGED:
        raise ReviewError(
            "pr_not_open",
            f"PR {row.url} was merged outside factory; `factory backlog sync` marks it done",
        )
    return row, status


def _catch_up_base(ctx: _Ctx) -> list[str]:
    """Fast-forward local ``base`` to the remote one; return warnings, never raise."""
    settings = ctx.rc.config.settings
    base, remote, main = settings.base, settings.remote, ctx.main
    try:
        if not pgit.has_remote(main, remote):
            return []
        pgit.fetch(main, remote, base)
        theirs = pgit.rev_parse(main, f"refs/remotes/{remote}/{base}") or pgit.rev_parse(
            main, "FETCH_HEAD"
        )
        ours = pgit.rev_parse(main, f"refs/heads/{base}")
        if theirs is None or ours is None or theirs == ours:
            return []
        if pgit.is_ancestor(main, ours, theirs):
            pgit.advance_branch(main, base, theirs, ours, command="task approve")
            return []
        if pgit.is_ancestor(main, theirs, ours):
            return []
        return [f"base {base} and {remote}/{base} have diverged; base not updated"]
    except ProviderError as exc:
        return [f"base not updated: {exc.code}: {exc.message}"]
    except (RuntimeError, OSError) as exc:
        return [f"base not updated: {exc}"]


def _remove(ctx: _Ctx, path: Path, removed: list[str], warnings: list[str]) -> None:
    try:
        if pgit.remove_worktree(ctx.main, path):
            removed.append(str(path))
    except (ProviderError, RuntimeError, OSError) as exc:
        warnings.append(f"worktree {path} not removed: {exc}")


def _remove_run_worktrees(ctx: _Ctx, branch: str) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    warnings: list[str] = []
    for r in ctx.store.runs_on_branch(branch):
        _remove(ctx, Path(r.worktree), removed, warnings)
    return removed, warnings


def _main_checkout_error(ctx: _Ctx, branch: str) -> ReviewError:
    return ReviewError(
        "branch_checked_out",
        f"{branch} is checked out in the main checkout {ctx.main}, switch away first",
    )


def _worktrees_dir(ctx: _Ctx) -> str:
    return ctx.rc.config.settings.worktrees_dir.strip("/").removeprefix("./")


def _branch_worktree(ctx: _Ctx, branch: str, prefix: str) -> tuple[Path, Path | None]:
    """``(worktree, temp)``: where `branch` is checked out, or a temporary worktree on it."""
    main = ctx.main
    worktree = pgit.checked_out_in(main, branch)
    if worktree is not None and worktree.resolve() == main.resolve():
        raise _main_checkout_error(ctx, branch)
    if worktree is not None and worktree.is_dir():
        return worktree, None
    worktrees_dir = _worktrees_dir(ctx)
    temp = main / worktrees_dir / f"{prefix}-{branch.replace('/', '-')}"
    pgit.remove_worktree(main, temp)
    gitops.ensure_excluded(main, ["/" + worktrees_dir + "/"])
    temp.parent.mkdir(parents=True, exist_ok=True)
    gitops.git(main, "worktree", "add", "--quiet", str(temp), branch)
    return temp, temp


def _done_entry(ctx: _Ctx, row: TaskPrRow) -> str:
    """The ``## Běhy`` line for the PR `row`: workflow of its last successful run and the cost."""
    runs = ctx.store.runs_on_branch(row.branch)
    done = [r for r in runs if r.state == SUCCEEDED and r.workflow]
    # A resolve run only rebased the work; the line names the workflow that did it.
    resolves = (RESOLVE_WORKFLOW, RESOLVE_REVIEWED_WORKFLOW)
    workflow = next((r.workflow for r in done if r.workflow not in resolves), None)
    if workflow is None:
        workflow = next((r.workflow for r in done), None)
    cost, _ = branch_cost(ctx.store.db_path, [r.run_id for r in runs])
    return run_entry(datetime.date.today().isoformat(), workflow or "?", row.url, cost)


# ── approve ──────────────────────────────────────────────────────────────────


def approve_task(
    repo: Path,
    task_id: str,
    *,
    provider: GitProvider | None = None,
    merged_by: str = MERGED_BY_OPERATOR,
) -> ApproveResult:
    """Commit ``status: done`` to the task's PR branch and merge the PR.

    ``merged_by`` is recorded in ``task_prs`` (``operator`` or ``auto-merge``).
    """
    ctx = _context(repo, provider)
    try:
        return _approve(ctx, task_id, merged_by)
    except ProviderError as exc:
        raise ReviewError(exc.code, exc.message) from exc
    except RuntimeError as exc:
        raise ReviewError("worktree_failed", str(exc)) from exc
    finally:
        ctx.store.close()


def _approve(ctx: _Ctx, task_id: str, merged_by: str = MERGED_BY_OPERATOR) -> ApproveResult:
    row, status = _checked_pr(ctx, task_id)
    if status.mergeability == CONFLICT:
        raise ReviewError(
            "conflict",
            f"PR {row.url} does not merge into {row.base}; run `factory task resolve {task_id}` "
            f"to rebase it onto {row.base}",
        )

    settings = ctx.rc.config.settings
    main, branch = ctx.main, row.branch
    worktree, temp = _branch_worktree(ctx, branch, "approve")

    backlog = load_backlog(worktree, settings)
    node = backlog.by_id.get(task_id)
    if not isinstance(node, Task):
        raise ReviewError("unknown_task", f"no task {task_id} on {branch}")
    entry = _done_entry(ctx, row)
    task_file = worktree / node.path
    text = task_file.read_text(encoding="utf-8")
    new = mark_done(text, entry, pr_url=row.url)
    if new != text:
        task_file.write_text(new, encoding="utf-8", newline="\n")
        gitops.git(worktree, "add", "--", node.path)
        gitops.git(worktree, "commit", "-q", "-m", f"{task_id}: status done")
    ctx.provider.push(worktree, branch)
    head = gitops.git(worktree, "rev-parse", "HEAD")

    try:
        reviewed = ctx.provider.approve(row.request(), head)
    except ProviderError as exc:
        raise ReviewError(
            exc.code,
            f"{exc.message} (merge stopped; the done commit stays on {branch}; retry approve)",
        ) from exc

    try:
        merge_sha = ctx.provider.merge(row.request(), head, row.title)
    except MergeFailed as exc:
        # The done commit stays on the branch; mark_done is idempotent, so approve can be rerun.
        raise ReviewError(exc.code, f"{exc.message} (the done commit stays on {branch})") from exc
    ctx.store.update_pr(
        branch,
        state=MERGED,
        merged_at=_now(),
        merge_sha=merge_sha,
        merged_by=merged_by,
        auto_merge_error=None,
    )

    warnings = _catch_up_base(ctx)
    removed, remove_warnings = _remove_run_worktrees(ctx, branch)
    warnings += remove_warnings
    if temp is not None:
        _remove(ctx, temp, removed, warnings)
    saved = ctx.store.pr_for_branch(branch)
    assert saved is not None
    return ApproveResult(
        task_id=task_id,
        pr=saved,
        merge_sha=merge_sha,
        strategy=settings.merge_strategy,
        reviewed=reviewed,
        base_sha=pgit.rev_parse(main, f"refs/heads/{settings.base}"),
        removed_worktrees=removed,
        warnings=warnings,
        merged_by=merged_by,
    )


# ── return ───────────────────────────────────────────────────────────────────


def _dirty(path: Path) -> bool:
    return bool(gitops.git(path, "status", "--porcelain"))


def _free_branch(ctx: _Ctx, row: TaskPrRow) -> None:
    """Remove every worktree of the PR's branch so a new run can check it out.

    Refuses when the branch is checked out in the main checkout or a worktree
    of it has uncommitted changes.
    """
    worktrees = [Path(r.worktree) for r in ctx.store.runs_on_branch(row.branch)]
    other = pgit.checked_out_in(ctx.main, row.branch)
    if other is not None and other.resolve() == ctx.main.resolve():
        raise _main_checkout_error(ctx, row.branch)
    if other is not None and other not in worktrees:
        worktrees.append(other)
    for path in worktrees:
        if path.is_dir() and _dirty(path):
            raise ReviewError(
                "dirty_worktree", f"{path} has uncommitted changes, commit or drop them"
            )
    for path in worktrees:
        pgit.remove_worktree(ctx.main, path)


def return_task(
    repo: Path,
    task_id: str,
    note: str,
    *,
    provider: GitProvider | None = None,
    code: CodeRunner | None = None,
) -> TaskRunResult:
    """Start a new run of `task_id` on its PR branch with `note` in the prompt."""
    if not note or not note.strip():
        raise ReviewError("missing_note", "task return needs --note with what to change")
    ctx = _context(repo, provider)
    try:
        row, _ = _checked_pr(ctx, task_id)
        _free_branch(ctx, row)
        ctx.provider.comment(row.request(), f"Vráceno k přepracování:\n\n{note.strip()}")
    except ProviderError as exc:
        raise ReviewError(exc.code, exc.message) from exc
    except RuntimeError as exc:
        raise ReviewError("worktree_failed", str(exc)) from exc
    finally:
        ctx.store.close()
    return run_task(
        repo,
        task_id,
        note=note.strip(),
        force=True,
        code=code,
        provider=ctx.provider,
        branch=row.branch,
    )


# ── publish ──────────────────────────────────────────────────────────────────


def publish_task(
    repo: Path,
    task_id: str,
    *,
    run_id: str | None = None,
    provider: GitProvider | None = None,
) -> PublishResult:
    """Push the branch of the task's last succeeded run and open its PR (``task publish``).

    For a run whose push or PR failed at the end of ``task run`` (``pr_failed``): the
    same push (transient failures retried) and PR as there, with the body kept from the
    run. A PR the hosting already has for the branch is adopted (recorded and its body
    updated). Without a succeeded run (``no_succeeded_run``), with a PR already known
    (``pr_exists``) or while a run of the task is in progress (``already_running``)
    nothing changes. `run_id` (the dashboard) must name that last succeeded run. A failed
    push or hosting call is ``result.pr_error`` and is kept on the run.
    """
    ctx = _context(repo, provider)
    try:
        return _publish(ctx, task_id, run_id)
    except RuntimeError as exc:
        raise ReviewError("worktree_failed", str(exc)) from exc
    finally:
        ctx.store.close()


def _publish(ctx: _Ctx, task_id: str, run_id: str | None) -> PublishResult:
    busy = ctx.store.running(task_id)
    if busy is not None:
        err = already_running(busy)
        raise ReviewError(err.code, err.message)
    succeeded = [r for r in ctx.store.for_task(task_id) if r.state == SUCCEEDED]
    if not succeeded:
        raise ReviewError("no_succeeded_run", f"task {task_id} has no succeeded run to publish")
    row = succeeded[0]
    if run_id is not None and run_id != row.run_id:
        raise ReviewError(
            "invalid_value",
            f"run {run_id} is not the last succeeded run of task {task_id} ({row.run_id})",
        )
    known = ctx.store.open_pr(task_id) or ctx.store.pr_for_branch(row.branch)
    if known is not None:
        raise ReviewError(
            "pr_exists", f"task {task_id} already has pull request {known.url} ({known.state})"
        )
    if pgit.rev_parse(ctx.main, f"refs/heads/{row.branch}") is None:
        raise ReviewError("unknown_branch", f"branch {row.branch} of run {row.run_id} is gone")
    settings = ctx.rc.config.settings
    worktree = Path(row.worktree)
    source = worktree if worktree.is_dir() else ctx.main
    task = load_backlog(source, settings).by_id.get(task_id)
    if not isinstance(task, Task):
        raise ReviewError("unknown_task", f"no task {task_id} in {source}")
    body = ctx.store.pr_body_of(row.run_id)
    try:
        pr = publish(
            ctx.main,
            settings,
            ctx.store,
            row,
            task,
            None,
            ctx.provider,
            body=body,
            adopt_first=True,
        )
    except ProviderError as exc:
        error = f"{exc.code}: {exc.message}"
        ctx.store.set_pr_error(row.run_id, error)
        return PublishResult(
            run=ctx.store.get(row.run_id) or row,
            pr=ctx.store.pr_for_branch(row.branch),
            pr_error=error,
        )
    ctx.store.set_pr_error(row.run_id, None)
    return PublishResult(run=ctx.store.get(row.run_id) or row, pr=pr)


# ── resolve ──────────────────────────────────────────────────────────────────


def resolve_task(
    repo: Path,
    task_id: str,
    *,
    provider: GitProvider | None = None,
    code: CodeRunner | None = None,
    workflow: str = RESOLVE_WORKFLOW,
    started_by: str = STARTED_MANUAL,
) -> TaskRunResult:
    """Rebase the branch of `task_id`'s open PR onto the current base in a new run.

    Works for a PR in ``conflict`` and for a ``mergeable`` one (then it only
    brings the branch up to date). Base is caught up with the remote first.
    ``workflow`` is ``resolve`` or ``resolve-reviewed`` (auto-merge, a review of the resolution).
    """
    ctx = _context(repo, provider)
    try:
        row, _ = _checked_pr(ctx, task_id)
        _free_branch(ctx, row)
        warnings = _catch_up_base(ctx)
        base = ctx.rc.config.settings.base
        onto = pgit.rev_parse(ctx.main, f"refs/heads/{base}")
        if onto is None:
            raise ReviewError("unknown_base", f"base {base!r} does not exist")
    except ProviderError as exc:
        raise ReviewError(exc.code, exc.message) from exc
    except RuntimeError as exc:
        raise ReviewError("worktree_failed", str(exc)) from exc
    finally:
        ctx.store.close()
    result = run_task(
        repo,
        task_id,
        force=True,
        code=code,
        provider=ctx.provider,
        branch=row.branch,
        resolve_onto=onto,
        resolve_with=workflow,
        started_by=started_by,
    )
    result.warnings = (*result.warnings, *warnings)
    return result


# ── clean ────────────────────────────────────────────────────────────────────


def clean_worktrees(repo: Path, *, provider: GitProvider | None = None) -> CleanResult:
    """Remove worktrees of runs whose PR is merged or closed, and of abandoned runs."""
    ctx = _context(repo, provider)
    try:
        return _clean(ctx)
    finally:
        ctx.store.close()


def _clean(ctx: _Ctx) -> CleanResult:
    result = CleanResult()
    for open_pr in ctx.store.open_prs():
        try:
            _record_state(ctx, open_pr, ctx.provider.status(open_pr.request()))
        except ProviderError as exc:
            result.warnings.append(f"PR {open_pr.url}: {exc.code}: {exc.message}")
    runs = ctx.store.all_runs()  # newest first
    newest: dict[str, str] = {}
    for r in runs:
        newest.setdefault(r.task_id, r.run_id)
    for r in runs:
        path = Path(r.worktree)
        if r.state == RUNNING or not path.exists():
            continue
        pr = ctx.store.pr_for_branch(r.branch)
        if pr is not None and pr.state in (MERGED, CLOSED):
            reason = pr.state
        elif pr is None and newest.get(r.task_id) != r.run_id:
            reason = "abandoned"
        else:
            continue  # the open PR's worktree, or the task's last run without a PR
        try:
            pgit.remove_worktree(ctx.main, path)
        except (ProviderError, RuntimeError, OSError) as exc:
            result.warnings.append(f"worktree {path} not removed: {exc}")
            continue
        result.removed.append(
            {
                "run_id": r.run_id,
                "task_id": r.task_id,
                "branch": r.branch,
                "worktree": str(path),
                "reason": reason,
            }
        )
    return result
