"""``factory backlog sync``: mark done the tasks whose PR was merged outside factory.

The states of open task PRs (and of open sync PRs) are refreshed from the
provider first; a closed task PR is only recorded, the task is left alone.
Tasks whose newest PR is merged but which are not ``done`` in ``base`` get
``status: done`` and a line in ``## Běhy`` in ONE commit on a branch
``factory-sync/<n>`` that exists neither locally nor on the remote (an already
open sync PR is reused), and one PR is opened.

The commit is made only in a temporary worktree on the sync branch, never on
``base``; the sync PR is never merged by factory. With nothing to mark done no
branch, commit or PR is created.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from aifactory.backlog import Task, load_backlog
from aifactory.backlog.taskfile import has_entry, mark_done
from aifactory.config import ConfigError
from aifactory.providers import CLOSED, MERGED, OPEN, GitProvider, ProviderError
from aifactory.providers import git as pgit
from aifactory.review.errors import ReviewError
from aifactory.review.flow import (
    _branch_worktree,
    _catch_up_base,
    _context,
    _Ctx,
    _done_entry,
    _record_state,
    _remove,
    _worktrees_dir,
)
from aifactory.run import gitops
from aifactory.run.store import SyncPrRow, TaskPrRow, _now

# NOT "factory/": task_id_from_branch must not read a sync branch as a task branch.
SYNC_PREFIX = "factory-sync/"


@dataclass
class SyncTask:
    task_id: str
    path: str
    pr_url: str
    pr_branch: str
    merge_sha: str | None

    def to_json(self) -> dict[str, object]:
        return dict(asdict(self))


@dataclass
class SyncSkip:
    task_id: str
    reason: str
    pr_url: str | None

    def to_json(self) -> dict[str, object]:
        return dict(asdict(self))


@dataclass
class SyncResult:
    pr: SyncPrRow | None
    created: bool  # a new sync PR was opened now
    updated: bool  # a commit was added to an already open sync PR
    tasks: list[SyncTask] = field(default_factory=list)  # tasks marked done in the sync PR
    skipped: list[SyncSkip] = field(default_factory=list)
    states: list[dict[str, str]] = field(default_factory=list)  # task PRs whose state changed
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, object]:
        return {
            "ok": True,
            "pr": self.pr.to_json() if self.pr is not None else None,
            "url": self.pr.url if self.pr is not None else None,
            "created": self.created,
            "updated": self.updated,
            "tasks": [t.to_json() for t in self.tasks],
            "skipped": [s.to_json() for s in self.skipped],
            "states": list(self.states),
            "warnings": list(self.warnings),
        }


def sync_backlog(repo: Path, *, provider: GitProvider | None = None) -> SyncResult:
    """Open one PR that marks done the tasks whose PR was merged outside factory."""
    ctx = _context(repo, provider)
    try:
        return _sync(ctx)
    except ProviderError as exc:
        raise ReviewError(exc.code, exc.message) from exc
    except ConfigError as exc:
        raise ReviewError("invalid_config", str(exc)) from exc
    except RuntimeError as exc:
        raise ReviewError("worktree_failed", str(exc)) from exc
    finally:
        ctx.store.close()


def _refresh_task_prs(ctx: _Ctx, result: SyncResult) -> None:
    for row in ctx.store.open_prs():
        try:
            status = ctx.provider.status(row.request())
        except ProviderError as exc:
            result.warnings.append(f"PR {row.url}: {exc.code}: {exc.message}")
            continue
        _record_state(ctx, row, status)
        if status.state in (CLOSED, MERGED):
            result.states.append(
                {
                    "task_id": row.task_id,
                    "branch": row.branch,
                    "url": row.url,
                    "state": status.state,
                }
            )


def _refresh_sync_prs(ctx: _Ctx, result: SyncResult) -> None:
    for row in ctx.store.open_sync_prs():
        try:
            status = ctx.provider.status(row.request())
        except ProviderError as exc:
            result.warnings.append(f"sync PR {row.url}: {exc.code}: {exc.message}")
            continue
        if status.state == CLOSED:
            ctx.store.update_sync_pr(row.branch, state=CLOSED)
        elif status.state == MERGED:
            ctx.store.update_sync_pr(
                row.branch, state=MERGED, merged_at=_now(), merge_sha=status.merge_sha
            )


def _start_ref(ctx: _Ctx) -> str:
    settings = ctx.rc.config.settings
    base, remote = settings.base, settings.remote
    if pgit.has_remote(ctx.main, remote):
        remote_ref = f"refs/remotes/{remote}/{base}"
        if pgit.rev_parse(ctx.main, remote_ref) is not None:
            return remote_ref
    local_ref = f"refs/heads/{base}"
    if pgit.rev_parse(ctx.main, local_ref) is None:
        raise ReviewError("unknown_base", f"base {base!r} does not exist")
    return local_ref


def _candidates(ctx: _Ctx, checkout: Path, result: SyncResult) -> list[tuple[Task, TaskPrRow]]:
    backlog = load_backlog(checkout, ctx.rc.config.settings)
    found: list[tuple[Task, TaskPrRow]] = []
    for task_id in ctx.store.merged_task_ids():
        latest = ctx.store.latest_pr(task_id)
        if latest is None:
            continue
        if latest.state != MERGED:
            result.skipped.append(SyncSkip(task_id, "newer_pr", latest.url))
            continue
        node = backlog.by_id.get(task_id)
        if not isinstance(node, Task):
            result.skipped.append(SyncSkip(task_id, "not_in_base", latest.url))
            continue
        if node.status == "done":
            continue
        if node.status == "cancelled":
            result.skipped.append(SyncSkip(task_id, "cancelled", latest.url))
            continue
        text = (checkout / node.path).read_text(encoding="utf-8")
        if has_entry(text, latest.url):
            result.skipped.append(SyncSkip(task_id, "reopened", latest.url))
            continue
        found.append((node, latest))
    return found


def _next_sync_branch(ctx: _Ctx, warnings: list[str]) -> str:
    """The first free ``factory-sync/<n>``: unknown locally, to the DB and on the remote."""
    remote = ctx.rc.config.settings.remote
    local = gitops.git(
        ctx.main, "for-each-ref", "--format=%(refname:short)", f"refs/heads/{SYNC_PREFIX}*"
    ).splitlines()
    tracking = gitops.git(
        ctx.main,
        "for-each-ref",
        "--format=%(refname:short)",
        f"refs/remotes/{remote}/{SYNC_PREFIX}*",
    ).splitlines()
    names = [*local, *(n.strip().removeprefix(f"{remote}/") for n in tracking)]
    names += ctx.store.sync_branches()
    if pgit.has_remote(ctx.main, remote):
        listed = pgit.remote_branches(ctx.main, remote, SYNC_PREFIX)
        if listed is None:
            warnings.append(f"cannot list {remote} branches; sync branch chosen from local refs")
        else:
            names += listed
    highest = 0
    for name in names:
        name = name.strip()
        suffix = name.removeprefix(SYNC_PREFIX)
        if name.startswith(SYNC_PREFIX) and suffix.isdigit():
            highest = max(highest, int(suffix))
    number = highest + 1
    while pgit.rev_parse(ctx.main, f"refs/heads/{SYNC_PREFIX}{number}") is not None:
        number += 1
    return f"{SYNC_PREFIX}{number}"


def _task_line(task: SyncTask) -> str:
    return f"- {task.task_id} ({task.path}): PR {task.pr_url}"


def _task_lines(body: str) -> list[str]:
    return [line for line in body.splitlines() if line.startswith("- ")]


def _sync_body(branch: str, task_lines: list[str]) -> str:
    lines = [
        f"<!-- factory: sync branch={branch} -->",
        "",
        "Doplňuje `status: done` a záznam v `## Běhy` pro tasky, "
        "jejichž PR byl mergnut mimo HAIFA.",
        "",
    ]
    lines += task_lines
    return "\n".join(lines) + "\n"


def _guard_branch(ctx: _Ctx, worktree: Path) -> str:
    """The branch checked out in `worktree`; refuse anything but a sync branch."""
    head = pgit.git(worktree, "symbolic-ref", "--quiet", "--short", "HEAD")
    if not head.startswith(SYNC_PREFIX) or head == ctx.rc.config.settings.base:
        raise ReviewError("sync_on_base", f"refusing to commit backlog sync on {head!r}")
    return head


def _sync(ctx: _Ctx) -> SyncResult:
    result = SyncResult(pr=None, created=False, updated=False)
    _refresh_task_prs(ctx, result)
    _refresh_sync_prs(ctx, result)
    result.warnings += _catch_up_base(ctx)
    start_sha = pgit.rev_parse(ctx.main, _start_ref(ctx))
    assert start_sha is not None

    worktrees_dir = _worktrees_dir(ctx)
    check = ctx.main / worktrees_dir / "sync-check"
    temp: Path | None = None
    removed: list[str] = []
    try:
        pgit.remove_worktree(ctx.main, check)
        gitops.ensure_excluded(ctx.main, ["/" + worktrees_dir + "/"])
        check.parent.mkdir(parents=True, exist_ok=True)
        gitops.git(ctx.main, "worktree", "add", "--quiet", "--detach", str(check), start_sha)

        candidates = _candidates(ctx, check, result)
        if not candidates:
            return result

        open_syncs = ctx.store.open_sync_prs()
        existing = open_syncs[0] if open_syncs else None
        if existing is not None:
            worktree, temp = _branch_worktree(ctx, existing.branch, "sync")
            branch = existing.branch
        else:
            worktree, branch = check, _next_sync_branch(ctx, result.warnings)

        marked: list[SyncTask] = []
        for task, latest in candidates:
            item = SyncTask(task.id, task.path, latest.url, latest.branch, latest.merge_sha)
            task_file = worktree / task.path
            if not task_file.is_file():
                result.skipped.append(SyncSkip(task.id, "missing_on_sync_branch", latest.url))
                continue
            text = task_file.read_text(encoding="utf-8")
            new = mark_done(text, _done_entry(ctx, latest), pr_url=latest.url)
            if new != text:
                task_file.write_text(new, encoding="utf-8", newline="\n")
                gitops.git(worktree, "add", "--", task.path)
                marked.append(item)
            else:
                result.tasks.append(item)  # already on the open sync branch

        if not marked:
            result.pr = existing
            return result

        if existing is None:
            gitops.git(worktree, "switch", "-q", "-c", branch)
        head = _guard_branch(ctx, worktree)
        assert head == branch
        ids = ", ".join(t.task_id for t in marked)
        gitops.git(worktree, "commit", "-q", "-m", f"backlog sync: status done for {ids}")
        ctx.provider.push(worktree, branch)

        result.tasks += marked
        previous = existing.task_ids() if existing is not None else []
        added = [t for t in marked if t.task_id not in previous]
        all_ids = previous + [t.task_id for t in added]
        kept = _task_lines(existing.body) if existing is not None else []
        title = f"backlog sync: done for {len(all_ids)} task(s)"
        body = _sync_body(branch, kept + [_task_line(t) for t in added])
        if existing is None:
            pr = ctx.provider.create_pr(branch, title, body)
            now = _now()
            ctx.store.save_sync_pr(
                SyncPrRow(
                    branch=branch,
                    provider=ctx.provider.name,
                    pr_id=pr.id,
                    url=pr.url,
                    base=ctx.rc.config.settings.base,
                    base_sha=start_sha,
                    title=title,
                    body=body,
                    state=OPEN,
                    tasks=json.dumps(all_ids),
                    created_at=now,
                    updated_at=now,
                )
            )
            result.created = True
        else:
            ctx.provider.update_pr(existing.request(), body)
            ctx.store.update_sync_pr(branch, body=body, title=title, tasks=json.dumps(all_ids))
            result.updated = True
        result.pr = ctx.store.sync_pr_for_branch(branch)
        return result
    finally:
        if temp is not None:
            _remove(ctx, temp, removed, result.warnings)
        _remove(ctx, check, removed, result.warnings)
