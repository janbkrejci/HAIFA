"""Approve, return, resolve and clean task pull requests (steps 5 to 7 of "Běh úkolu").

* ``approve_task``: PR state -> one commit on the PR branch with ``status: done``
  and a ``## Běhy`` line -> push -> the CI checks of that head (``review.ci``; red
  checks get up to ``CI_FIX_ROUNDS`` ``ci-fix`` repair runs on the same branch, each
  followed by a new done commit, push and wait) -> supported host approval -> merge ->
  ``task_prs`` merged -> ``base`` caught up with the remote -> worktrees removed ->
  dependents restacked ->
  merged branch deleted locally and remotely when no open stack or checkout uses it.
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
  of runs a newer run of the same task has superseded; delete unused merged PR branches.
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from aifactory import failure as failures
from aifactory.backlog import Task, load_backlog, unmet
from aifactory.backlog.roots import owning_root
from aifactory.backlog.taskfile import mark_done, run_entry
from aifactory.config import ConfigError, RunConfig, load_run_config
from aifactory.config.settings import ProjectSettings
from aifactory.engine.data_types import ReviewOutput
from aifactory.providers import (
    CHECKS_FAILING,
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
from aifactory.review import ci
from aifactory.review.errors import ReviewError
from aifactory.review.prbody import branch_cost
from aifactory.review.publish import PublishResult, publish
from aifactory.run import gitops
from aifactory.run.errors import TaskRunError
from aifactory.run.resolve import CI_FIX_WORKFLOW, RESOLVE_REVIEWED_WORKFLOW, RESOLVE_WORKFLOW
from aifactory.run.scope import matches
from aifactory.run.stack import open_stack, stacked_on
from aifactory.run.store import (
    MERGED_BY_OPERATOR,
    RUNNING,
    STARTED_MANUAL,
    SUCCEEDED,
    TaskPrRow,
    TaskRunRow,
    TaskRunStore,
    _now,
    already_running,
)
from aifactory.run.task import TaskRunResult, run_task, session_dir_of
from aifactory.run.unchanged import finish_unchanged, unchanged
from aifactory.workflow import CodeRunner, WorkflowRun
from aifactory.workflow.journal import JOURNAL_FILE, read_journal

if TYPE_CHECKING:
    from aifactory.run.allow_writes import AllowWritesResult
    from aifactory.run.queue import ChainResult


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
    ci_fix_runs: list[str] = field(default_factory=list)  # ci-fix runs before the merge
    deleted_branches: list[str] = field(default_factory=list)
    allow_writes: dict[str, object] | None = None  # --allow-writes: the paths allowed first

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
            "ci_fix_runs": list(self.ci_fix_runs),
            "deleted_branches": list(self.deleted_branches),
            **({"allow_writes": self.allow_writes} if self.allow_writes is not None else {}),
        }


@dataclass
class CleanResult:
    removed: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    deleted_branches: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, object]:
        return {
            "ok": True,
            "removed": list(self.removed),
            "deleted_branches": list(self.deleted_branches),
            "warnings": list(self.warnings),
        }


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
        ctx.store.update_pr(
            row.branch,
            state=MERGED,
            merged_at=status.merged_at or _now(),
            merge_sha=status.merge_sha,
        )


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
    runs = ctx.store.runs_on_branch(branch)
    active = {Path(r.worktree).resolve() for r in runs if r.state == RUNNING}
    for r in runs:
        if Path(r.worktree).resolve() in active:
            continue
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
    gitops.git(main, *pgit.PARALLEL_CHECKOUT, "worktree", "add", "--quiet", str(temp), branch)
    return temp, temp


def _done_entry(ctx: _Ctx, row: TaskPrRow) -> str:
    """The ``## Běhy`` line for the PR `row`: workflow of its last successful run and the cost."""
    runs = ctx.store.runs_on_branch(row.branch)
    done = [r for r in runs if r.state == SUCCEEDED and r.workflow]
    # A resolve or ci-fix run only rebased or repaired the work; the line names the
    # workflow that did it.
    resolves = (RESOLVE_WORKFLOW, RESOLVE_REVIEWED_WORKFLOW, CI_FIX_WORKFLOW)
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
    code: CodeRunner | None = None,
    allow_writes: bool = False,
) -> ApproveResult:
    """Commit ``status: done`` to the task's PR branch, wait for its CI and merge the PR.

    ``merged_by`` is recorded in ``task_prs`` (``operator`` or ``auto-merge``). The
    checks of the pushed head decide (``review.ci``): none or green merge; red ones
    start up to ``ci.CI_FIX_ROUNDS`` ``ci-fix`` runs on the PR branch (``code`` runs
    their code steps), each followed by a new wait. Checks still red or running leave
    the PR open with the reason in ``task_prs.auto_merge_error`` and raise ``ReviewError``.
    A ``ci-fix`` run that needs paths outside the task's writes (``writes_needed``) stops
    with the code ``writes_needed`` and its paths. ``allow_writes`` (``factory task approve
    --allow-writes``) first adds those paths of the newest ``ci-fix`` run to the task's
    writes in base (``run.allow_writes``), so the new ``ci-fix`` runs may write them.
    """
    allowed = _allow_ci_fix_writes(repo, task_id) if allow_writes else None
    ctx = _context(repo, provider)
    row = ctx.store.latest_pr(task_id) if merged_by == MERGED_BY_OPERATOR else None
    try:
        if row is not None and row.state == OPEN:
            ctx.store.update_pr(row.branch, approved_at=_now(), auto_merge_error=None)
        try:
            if allowed is not None:
                _take_base_backlog(ctx, task_id)
            result = _approve_gated(repo, ctx, task_id, merged_by, code)
        except ProviderError as exc:
            raise ReviewError(exc.code, exc.message) from exc
        except RuntimeError as exc:
            raise ReviewError("worktree_failed", str(exc)) from exc
    except ReviewError as exc:
        if row is not None:
            saved = ctx.store.pr_for_branch(row.branch)
            if saved is not None and saved.state == OPEN:
                ctx.store.update_pr(
                    row.branch, approved_at=None, auto_merge_error=f"{exc.code}: {exc.message}"
                )
        raise
    finally:
        ctx.store.close()
    if allowed is not None:
        result.allow_writes = allowed.to_json()
        result.warnings += list(allowed.commit.warnings)
    # Local import: review.stack resolves and merges through this module.
    from aifactory.review.stack import restack_dependents

    result.warnings += restack_dependents(
        repo, ctx.store.db_path, result.pr.branch, provider=ctx.provider, code=code
    )
    # Restacking may recursively approve other PRs and writes through separate stores.
    ctx.store = TaskRunStore(ctx.store.db_path)
    try:
        _delete_merged_branch(ctx, result.pr, result.deleted_branches, result.warnings)
    finally:
        ctx.store.close()
    return result


def _allow_ci_fix_writes(repo: Path, task_id: str) -> AllowWritesResult:
    """``approve --allow-writes``: the paths of the newest ``ci-fix`` run into ``writes``."""
    from aifactory.run.allow_writes import allow_writes

    try:
        return allow_writes(repo, task_id, ci_fix=True)
    except TaskRunError as exc:
        raise ReviewError(exc.code, exc.message) from exc


def _take_base_backlog(ctx: _Ctx, task_id: str) -> None:
    """Merge base into the PR branch after ``--allow-writes`` changed the task in base.

    An earlier approve left its ``status: done`` commit on the branch; it and the new
    ``writes`` in base change the same front matter, so the PR would not merge. Backlog
    files take base's version (``_prepare_approve`` commits ``status: done`` again); a
    conflict in any other file aborts the merge (``conflict``).
    """
    row, _ = _checked_pr(ctx, task_id)
    settings = ctx.rc.config.settings
    base = f"refs/heads/{settings.base}"
    _free_branch(ctx, row)
    worktree, temp = _branch_worktree(ctx, row.branch, "allow-writes")
    try:
        if gitops.git(worktree, "merge-base", "HEAD", base) == gitops.git(
            worktree, "rev-parse", base
        ):
            return  # base is in the branch already
        try:
            gitops.git(worktree, "merge", "--no-ff", "--no-commit", base)
        except RuntimeError:
            pass
        conflicted = [
            p
            for p in gitops.git(worktree, "diff", "--name-only", "--diff-filter=U").splitlines()
            if p.strip()
        ]
        others = [
            p
            for p in conflicted
            if owning_root(p, settings) is None
            and not any(matches(p, root) for root in settings.backlog_patterns)
        ]
        if others:
            gitops.git(worktree, "merge", "--abort")
            raise ReviewError(
                "conflict",
                f"PR {row.url} does not merge into {row.base} ({', '.join(others)}); run "
                f"`factory task resolve {task_id}`, then approve again",
            )
        for path in conflicted:
            gitops.git(worktree, "checkout", "--theirs", "--", path)
            gitops.git(worktree, "add", "--", path)
        gitops.git(
            worktree,
            "commit",
            "-q",
            "--no-edit",
            "-m",
            f"{task_id}: merge {settings.base} (writes)",
        )
        ctx.provider.push(worktree, row.branch)
    finally:
        if temp is not None:
            _remove(ctx, temp, [], [])


def ci_fix_needs(run: TaskRunRow) -> str | None:
    """The reason of a ``ci-fix`` run that ended ``writes_needed``: its paths; else None."""
    if run.shown_failure_kind != failures.WRITES_NEEDED:
        return None
    detail = run.failure_detail_dict() or {}
    items = failures.needed_paths(detail.get("needs_writes") or [])
    if not items:
        items = failures.needed_paths([{"path": p} for p in detail.get("paths") or []])
    paths = "; ".join(f"{i['path']} ({i['reason']})" if i["reason"] else i["path"] for i in items)
    return (
        f"ci-fix run {run.run_id} needs paths outside the task's writes: {paths or '?'}; "
        f"allow them and approve again (factory task approve {run.task_id} --allow-writes)"
    )


def _approve_gated(
    repo: Path, ctx: _Ctx, task_id: str, merged_by: str, code: CodeRunner | None
) -> ApproveResult:
    """``_prepare_approve``, the CI gate with its repair runs, then ``_finish_approve``."""
    fixes: list[str] = []
    while True:
        prepared = _prepare_approve(ctx, task_id)
        row = prepared.row

        def stop(code_: str, reason: str, row: TaskPrRow = row) -> ReviewError:
            fields: dict[str, object] = {"auto_merge_error": f"{code_}: {reason}"}
            if merged_by == MERGED_BY_OPERATOR:
                fields["approved_at"] = None
            ctx.store.update_pr(row.branch, **fields)
            return ReviewError(code_, reason)

        try:
            checks = ci.head_checks(ctx.provider, row.request(), prepared.head)
        except ProviderError as exc:
            raise stop("checks_unavailable", f"{exc.code}: {exc.message}") from exc
        if checks.state != CHECKS_FAILING or len(fixes) >= ci.CI_FIX_ROUNDS:
            blocker = ci.checks_reason(checks, len(fixes))
            if blocker is not None:
                raise stop(*blocker)
            result = _finish_approve(ctx, prepared, merged_by)
            result.ci_fix_runs = fixes
            return result
        try:
            logs = ctx.provider.check_logs(row.request(), checks.failing)
        except ProviderError as exc:
            logs = {name: f"log unavailable: {exc.code}: {exc.message}" for name in checks.failing}
        if prepared.temp is not None:
            _remove(ctx, prepared.temp, [], [])
        _free_branch(ctx, row)
        try:
            fixed = ci.run_ci_fix(
                repo,
                task_id,
                row.branch,
                ci.ci_report(checks.failing, logs),
                ctx.provider,
                code,
            )
        except TaskRunError as exc:
            reason = f"ci-fix run did not start: {exc.code}: {exc.message}"
            raise stop("ci_fix_failed", reason) from exc
        fixes.append(fixed.run.run_id)
        needs = ci_fix_needs(fixed.run) if fixed.run.state != SUCCEEDED else None
        if needs is not None:
            raise stop("writes_needed", needs)
        if fixed.run.state != SUCCEEDED:
            detail = f": {fixed.run.error}" if fixed.run.error else ""
            raise stop(
                "ci_fix_failed",
                f"ci-fix run {fixed.run.run_id} ended {fixed.run.state}{detail} "
                f"(red checks: {', '.join(checks.failing) or '?'})",
            )


def _refuse_blocked(main: Path, settings: ProjectSettings, task_id: str) -> None:
    """``task_blocked`` when the task has unmet ``depends_on`` in the main checkout's backlog.

    A run whose agents reported a blocker links the task to it there
    (``run/followups.py``); a blocked task must not become done or be merged.
    """
    backlog = load_backlog(main, settings)
    node = backlog.by_id.get(task_id)
    if not isinstance(node, Task):
        return
    missing = unmet(backlog, node)
    if missing:
        ids = ", ".join(u.id for u in missing)
        raise ReviewError("task_blocked", f"task {task_id} is blocked by {ids}; finish them first")


@dataclass
class _Prepared:
    """The PR after the ``status: done`` commit was pushed: ``head`` is what gets merged."""

    row: TaskPrRow
    worktree: Path
    temp: Path | None
    head: str


def _prepare_approve(ctx: _Ctx, task_id: str) -> _Prepared:
    """Check the PR, commit ``status: done`` on its branch and push; safe to call again."""
    row, status = _checked_pr(ctx, task_id)
    if status.mergeability == CONFLICT:
        raise ReviewError(
            "conflict",
            f"PR {row.url} does not merge into {row.base}; run `factory task resolve {task_id}` "
            f"to rebase it onto {row.base}",
        )

    settings = ctx.rc.config.settings
    main, branch = ctx.main, row.branch
    _refuse_blocked(main, settings, task_id)
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
    return _Prepared(row, worktree, temp, head)


def _finish_approve(ctx: _Ctx, prepared: _Prepared, merged_by: str) -> ApproveResult:
    """Host approval, merge of ``prepared.head``, ``task_prs``, base caught up, cleanup."""
    row, head, temp = prepared.row, prepared.head, prepared.temp
    settings = ctx.rc.config.settings
    main, branch, task_id = ctx.main, row.branch, row.task_id
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


@dataclass
class TaskPublishResult(PublishResult):
    chain: ChainResult | None = None

    def to_json(self) -> dict[str, object]:
        data = super().to_json()
        data["auto_merge"] = None
        if self.chain is not None:
            first = self.chain.runs[0]
            data["auto_merge"] = first.auto_merge.to_json() if first.auto_merge else None
            data["chain"] = self.chain.to_json()
        return data


def publish_task(
    repo: Path,
    task_id: str,
    *,
    run_id: str | None = None,
    provider: GitProvider | None = None,
    code: CodeRunner | None = None,
) -> TaskPublishResult:
    """Push the branch of the task's last succeeded run and open its PR (``task publish``).

    For a run whose push or PR failed at the end of ``task run`` (``pr_failed``): the
    same push (transient failures retried) and PR as there, with the body kept from the
    run. A PR the hosting already has for the branch is adopted (recorded and its body
    updated). A run that left no commit on its branch marks the task done instead
    (``run/unchanged.py``). Without a succeeded run (``no_succeeded_run``), with a PR already known
    (``pr_exists``) or while a run of the task is in progress (``already_running``)
    nothing changes. `run_id` (the dashboard) must name that last succeeded run. A failed
    push or hosting call is ``result.pr_error`` and is kept on the run. After publication,
    effective ``auto_merge`` enables ``run_chain`` to finish auto-merge and auto-continue
    with the completed attempt as its first run; its review is recovered from the
    workflow journal. Otherwise the PR stays open for review without continuing the queue.
    """
    ctx = _context(repo, provider)
    operation_id = ctx.store.start_operation(task_id, "publish", os.getpid())
    try:
        published = _publish(ctx, task_id, run_id)
    except RuntimeError as exc:
        raise ReviewError("worktree_failed", str(exc)) from exc
    finally:
        ctx.store.finish_operation(operation_id)
        ctx.store.close()

    from aifactory.run.queue import _fresh_backlog, auto_merge_enabled, run_chain

    def first() -> TaskRunResult:
        # A retry's journal includes the replayed review of the finished attempt.
        journal = read_journal(session_dir_of(repo, published.run.run_id) / JOURNAL_FILE)
        wf = WorkflowRun(exit_code=0, accepted=True, adw_id=published.run.run_id)
        for entry in journal.entries:
            if entry.kept and entry.output == "ReviewOutput" and entry.envelope is not None:
                wf.history.append((entry.step, ReviewOutput.model_validate(entry.envelope)))
        return TaskRunResult(
            run=published.run,
            workflow_run=wf,
            warnings=tuple(published.warnings),
            trace_db=ctx.rc.local.trace_db_path(ctx.main),
            pr=published.pr,
            pr_error=published.pr_error,
            done_without_pr=published.done_without_pr,
        )

    chain = None
    if published.ok:
        with _fresh_backlog(repo) as backlog:
            task = backlog.by_id.get(task_id)
            resume_chain = isinstance(task, Task) and auto_merge_enabled(task)
        if resume_chain:
            chain = run_chain(repo, task_id, first_run=first, provider=provider, code=code)
    return TaskPublishResult(
        run=published.run,
        pr=published.pr,
        pr_error=published.pr_error,
        warnings=published.warnings,
        done_without_pr=published.done_without_pr,
        chain=chain,
    )


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
    if unchanged(row):
        failure, notes = finish_unchanged(ctx.main, ctx.store, row)
        ctx.store.set_pr_error(row.run_id, failure)
        return PublishResult(
            run=ctx.store.get(row.run_id) or row,
            pr=None,
            pr_error=failure,
            warnings=notes,
            done_without_pr=failure is None,
        )
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
        stack = open_stack(ctx.store, row.branch)
        if stack is not None:
            raise ReviewError(
                "stacked_on_open_pr",
                f"the PR of {task_id} builds on {stack.url} ({stack.task_id}), which is not "
                "merged yet; it is rebased onto base after that merge",
            )
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
    """Remove finished worktrees and unused local/remote branches of merged PRs."""
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
    active = {Path(r.worktree).resolve() for r in runs if r.state == RUNNING}
    for r in runs:
        path = Path(r.worktree)
        if path.resolve() in active or not path.exists():
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
    for pr in ctx.store.done_prs():
        if pr.state == MERGED:
            _delete_merged_branch(ctx, pr, result.deleted_branches, result.warnings)
    return result


def _delete_merged_branch(
    ctx: _Ctx, pr: TaskPrRow, deleted: list[str], warnings: list[str]
) -> None:
    """Best-effort cleanup after restack; keep branches still used by open PRs or runs."""
    branch = pr.branch
    try:
        if branch == ctx.rc.config.settings.base or branch == pr.base:
            return
        for child in ctx.store.open_prs():
            if stacked_on(ctx.store, child.branch) != branch:
                continue
            # stacked_on preserves the original fork even after a successful restack.
            # Only a completed resolve after that fork releases the dependency.
            for run in ctx.store.runs_on_branch(child.branch):
                if (
                    run.state == SUCCEEDED
                    and run.pr_error is None
                    and run.workflow in (RESOLVE_WORKFLOW, RESOLVE_REVIEWED_WORKFLOW)
                ):
                    break
                if run.stacked_on == branch:
                    return
        if any(r.state == RUNNING for r in ctx.store.runs_on_branch(branch)):
            return
        if pgit.checked_out_in(ctx.main, branch) is not None:
            return
    except (ProviderError, RuntimeError, OSError) as exc:
        warnings.append(f"branch {branch} not deleted: {exc}")
        return
    # Try each independently so a failed remote deletion remains retryable by task clean.
    try:
        if pgit.rev_parse(ctx.main, f"refs/heads/{branch}") is not None:
            pgit.git(ctx.main, "branch", "-D", "--", branch)
            deleted.append(branch)
    except (ProviderError, RuntimeError, OSError) as exc:
        warnings.append(f"branch {branch} not deleted: {exc}")
    remote = ctx.rc.config.settings.remote
    try:
        if pgit.has_remote(ctx.main, remote):
            exists = pgit.remote_branch_exists(ctx.main, remote, branch)
            if exists is None:
                raise RuntimeError(f"cannot query {remote}")
            if exists:
                pgit.git(ctx.main, "push", remote, "--delete", branch)
                deleted.append(f"{remote}/{branch}")
    except (ProviderError, RuntimeError, OSError) as exc:
        warnings.append(f"remote branch {remote}/{branch} not deleted: {exc}")
