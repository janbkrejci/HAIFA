"""Allow the paths of a ``writes_violation`` or ``writes_needed`` and continue the run
(``task retry --allow-writes``).

A run that failed because an agent wrote outside the task's ``writes`` records the
rolled-back worktree paths in ``failure_detail.paths`` (``guard.py``; older runs only
in ``problems``). A run whose agent reported the paths it needs (``fail_kind:
needs_writes``, the run's kind ``writes_needed``) records them in ``failure_detail.paths``
too. ``plan_allow_writes`` sorts them the same way for both kinds:

- ``allow``: paths the task's ``writes`` do not cover. Adding them lets the agent
  write them on the retry.
- ``refused``: paths no change of ``writes`` makes writable, each with its reason:
  ``protected`` (``protected_files`` of ``config.yaml`` or ``agents.yaml``), ``backlog``
  (under a backlog root: only the factory writes the backlog), ``main_checkout`` (a
  write outside the run's worktree), ``already_allowed`` (the task's ``writes`` or
  outputs cover it already, so the agent's own ``writes`` in ``agents.yaml`` forbade it).

``allow_writes`` first fetches and fast-forwards base using the same safety checks as
retry, then replans against the updated backlog. Paths brought by the remote need
no edit or commit. A failed edit or commit restores the task file and index; an
already committed change stays committed.

``allow_writes`` adds the ``allow`` paths to the task's own ``writes`` (the effective
value plus the new paths, through ``backlog.edit``) and commits the backlog to ``base``
(``commit_backlog``, by ``base_changes``). The caller then retries the run
(``factory task retry --allow-writes``, ``POST /api/runs/{id}/allow-writes``) with
``retry_note`` in the prompt, so the agent knows which paths it may write now. A
``ci-fix`` run is not retried: ``factory task approve --allow-writes`` approves the PR
again and its new ``ci-fix`` runs read the extended writes from base. With
``base_changes: pr`` and a PR that is not merged at once, base lacks the new writes:
``writes_in_pr`` is raised and the run is not retried. Every other commit result
(including a no-op or a merged PR) is checked against the backlog in the base
commit. If any allowed path is missing from the effective writes there,
``writes_not_committed`` is raised before the caller can retry.

Error codes (``TaskRunError.code``): ``unknown_run``, ``invalid_value`` (a run of another
task), ``already_running``, ``run_not_retryable``, ``not_writes_violation``,
``nothing_to_allow``, ``writes_in_pr``, ``writes_not_committed``. Errors of the edit
and the commit are ``TaskEditError`` (``backlog_invalid``, ``not_on_base``, ``commit_failed``, ...).
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aifactory import failure
from aifactory.backlog import (
    Task,
    commit_backlog,
    edit_task,
    find_task,
    load_backlog,
    load_for_edit,
)
from aifactory.backlog.commit import BacklogCommit
from aifactory.backlog.roots import owning_root
from aifactory.config import ConfigError, ProjectSettings, load_run_config
from aifactory.engine import permissions
from aifactory.run import gitops
from aifactory.run.errors import TaskRunError
from aifactory.run.resolve import CI_FIX_WORKFLOW, INTERNAL_WORKFLOWS
from aifactory.run.retry import _pull_base
from aifactory.run.scope import effective_task_writes, matches, normalize, output_paths
from aifactory.run.store import RETRYABLE, TaskRunRow, TaskRunStore, already_running

ALLOWABLE_KINDS = (failure.WRITES_VIOLATION, failure.WRITES_NEEDED)
"""The failure kinds whose paths ``allow_writes`` adds to the task's writes."""

PROTECTED = "protected"
BACKLOG = "backlog"
MAIN_CHECKOUT = "main_checkout"
ALREADY_ALLOWED = "already_allowed"
REASONS = {
    PROTECTED: "a protected path (protected_files); writes cannot allow it",
    BACKLOG: "a backlog path; only the factory writes the backlog",
    MAIN_CHECKOUT: "written in the main checkout, outside the run's worktree",
    ALREADY_ALLOWED: "the task's writes allow it already; the agent's own writes "
    "(agents.yaml) forbid it",
}
_WORKTREE_PREFIX = "worktree: "


@dataclass(frozen=True)
class Refused:
    path: str
    reason: str

    def to_json(self) -> dict[str, str]:
        return {"path": self.path, "reason": self.reason, "message": REASONS[self.reason]}


@dataclass
class AllowWritesPlan:
    run_id: str
    task_id: str
    writes: list[str]  # the task's effective writes now
    allow: list[str] = field(default_factory=list)
    refused: list[Refused] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "writes": list(self.writes),
            "allow": list(self.allow),
            "refused": [r.to_json() for r in self.refused],
        }


@dataclass
class AllowWritesResult:
    plan: AllowWritesPlan
    writes: list[str]  # the task's writes after the change
    commit: BacklogCommit

    def to_json(self) -> dict[str, Any]:
        return {**self.plan.to_json(), "new_writes": self.writes, "commit": self.commit.to_json()}


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [normalize(v) for v in value if isinstance(v, str) and v.strip()]


def violation_paths(
    detail: dict[str, Any], kind: str = failure.WRITES_VIOLATION
) -> tuple[list[str], list[str]]:
    """The worktree paths and the main checkout paths of a ``writes_violation`` (or the
    paths a ``writes_needed`` agent reported, never in the main checkout)."""
    worktree = _strings(detail.get("paths"))
    if kind == failure.WRITES_NEEDED:
        return list(dict.fromkeys(worktree)), []
    if not worktree:  # a run recorded before ``paths``: read them from the problems
        for problem in _strings(detail.get("problems")):
            if problem.startswith(_WORKTREE_PREFIX) and " — " in problem:
                path = problem[len(_WORKTREE_PREFIX) :].split(" — ", 1)[0].strip()
                if path and path != "HEAD":
                    worktree.append(path)
    main = _strings(detail.get("main_paths"))
    return list(dict.fromkeys(worktree)), list(dict.fromkeys(main))


def classify(
    paths: list[str],
    main_paths: list[str],
    *,
    writes: list[str],
    outputs: tuple[str, ...],
    protected: list[str],
    settings: ProjectSettings,
) -> tuple[list[str], list[Refused]]:
    """Split the paths into those to add to ``writes`` and those refused, with a reason."""
    allow: list[str] = []
    refused: list[Refused] = []
    for path in paths:
        if any(permissions._matches(path, p) for p in protected):
            refused.append(Refused(path, PROTECTED))
        elif owning_root(path, settings) is not None or any(
            matches(path, root) for root in settings.backlog_patterns
        ):
            refused.append(Refused(path, BACKLOG))
        elif path in outputs or any(matches(path, w) for w in writes):
            refused.append(Refused(path, ALREADY_ALLOWED))
        elif path not in allow:
            allow.append(path)
    refused.extend(Refused(p, MAIN_CHECKOUT) for p in main_paths)
    return allow, refused


def _pick_run(store: TaskRunStore, task_id: str, run_id: str | None) -> TaskRunRow:
    runs = store.for_task(task_id)
    if run_id is not None:
        row = next((r for r in runs if r.run_id == run_id), None)
        if row is None:
            raise TaskRunError("invalid_value", f"run {run_id} is not a run of task {task_id}")
        return row
    if not runs:
        raise TaskRunError("unknown_run", f"task {task_id} has no run to retry")
    return runs[0]


def plan_allow_writes(
    repo: Path, task_id: str, run_id: str | None = None, *, ci_fix: bool = False
) -> AllowWritesPlan:
    """What ``allow_writes`` would add to the task's writes and what it refuses.

    A run of an internal workflow (``resolve``, ``ci-fix``) is not retried, so it is
    refused (``run_not_retryable``) unless `ci_fix` asks for the newest ``ci-fix`` run,
    as ``factory task approve --allow-writes`` does.
    """
    main = gitops.main_root(repo)
    try:
        rc = load_run_config(main)
    except ConfigError as exc:
        raise TaskRunError("invalid_config", str(exc)) from exc
    store = TaskRunStore(rc.local.trace_db_path(main))
    try:
        row = _pick_run(store, task_id, run_id)
        busy = store.running(task_id)
    finally:
        store.close()
    if busy is not None:
        raise already_running(busy)
    if ci_fix and row.workflow != CI_FIX_WORKFLOW:
        raise TaskRunError(
            "not_writes_violation",
            f"run {row.run_id} of task {task_id} is a {row.workflow} run, not a "
            f"{CI_FIX_WORKFLOW} run; retry it (factory task retry {task_id} --allow-writes)",
        )
    if row.state not in RETRYABLE:
        raise TaskRunError(
            "run_not_retryable",
            f"run {row.run_id} of task {task_id} is {row.state}; only a failed, stopped "
            "or aborted run can be retried",
        )
    if not ci_fix and row.workflow in INTERNAL_WORKFLOWS:
        again = (
            f"approve the PR again (factory task approve {task_id} --allow-writes)"
            if row.workflow == CI_FIX_WORKFLOW
            else "run factory task resolve again"
        )
        raise TaskRunError(
            "run_not_retryable", f"run {row.run_id} is a {row.workflow} run; {again}"
        )
    kind = row.shown_failure_kind
    if kind not in ALLOWABLE_KINDS:
        raise TaskRunError(
            "not_writes_violation",
            f"run {row.run_id} of task {task_id} failed with {kind}, not "
            f"{' or '.join(ALLOWABLE_KINDS)}; there are no paths to allow",
        )
    settings = rc.config.settings
    task = find_task(load_for_edit(main), task_id)
    writes = list(effective_task_writes(task))
    outputs = output_paths(task, settings)
    protected = [*rc.config.agents.defaults.protected_files, *settings.protected_files]
    paths, main_paths = violation_paths(row.failure_detail_dict() or {}, kind or "")
    allow, refused = classify(
        paths,
        main_paths,
        writes=writes,
        outputs=(outputs.spec, outputs.doc),
        protected=list(dict.fromkeys(protected)),
        settings=settings,
    )
    return AllowWritesPlan(row.run_id, task_id, writes, allow, refused)


@contextmanager
def _restore_failed_edit(main: Path, path: str) -> Iterator[None]:
    """Undo our uncommitted edit, preserving the operator's file and index bytes.

    If a commit already advanced HEAD, keep its version rather than introducing
    a reverse edit of a committed (possibly pushed) change.
    """
    from aifactory.providers import git as provider_git

    target = main / path
    before = target.read_bytes()
    head = gitops.head(main)
    index = Path(gitops.git(main, "rev-parse", "--git-path", "index"))
    if not index.is_absolute():
        index = main / index
    index_before = index.read_bytes() if index.exists() else None
    try:
        yield
    except BaseException:
        if gitops.head(main) == head:
            target.write_bytes(before)
            if index_before is not None:
                index.write_bytes(index_before)
            else:
                index.unlink(missing_ok=True)
        else:
            committed = provider_git.run_bytes(main, ["show", f"HEAD:{path}"])
            if committed.returncode == 0:
                target.write_bytes(committed.stdout)
        raise


def allow_writes(
    repo: Path, task_id: str, run_id: str | None = None, *, ci_fix: bool = False
) -> AllowWritesResult:
    """Add the allowed paths of the run's ``writes_violation`` or ``writes_needed`` to the
    task's writes in base (`ci_fix`: of the task's newest ``ci-fix`` run)."""
    plan = plan_allow_writes(repo, task_id, run_id, ci_fix=ci_fix)
    if not plan.allow:
        why = "; ".join(f"{r.path}: {REASONS[r.reason]}" for r in plan.refused)
        raise TaskRunError(
            "nothing_to_allow",
            f"run {plan.run_id} of task {task_id} has no path writes can allow"
            + (f" ({why})" if why else ""),
        )
    main = gitops.main_root(repo)
    rc = load_run_config(main)
    store = TaskRunStore(rc.local.trace_db_path(main))
    try:
        _pull_base(main, rc.config.settings, store)
    finally:
        store.close()
    rc = load_run_config(main)
    refreshed = plan_allow_writes(main, task_id, plan.run_id, ci_fix=ci_fix)
    new_writes = [*refreshed.writes, *refreshed.allow]
    task = find_task(load_for_edit(main), task_id)
    with _restore_failed_edit(main, task.path):
        again = f"factory task approve {task_id}" if ci_fix else f"factory task retry {task_id}"
        if refreshed.allow:
            edit_task(main, task_id, writes=new_writes)
            commit = commit_backlog(
                main, f"backlog: {task_id} writes += {', '.join(refreshed.allow)}"
            )
        else:
            commit = BacklogCommit(False, None, rc.base, [], False)
        if commit.pr is not None and not commit.merged:
            raise TaskRunError(
                "writes_in_pr",
                f"the writes of {task_id} are extended in "
                f"{commit.pr.get('url') or 'a pull request'}; "
                f"run {again} after it is merged",
            )
        rc = load_run_config(main)
        settings = rc.config.settings
        with tempfile.TemporaryDirectory(prefix="factory-base-") as tmp:
            base_copy = Path(tmp)
            try:
                sha = gitops.git(main, "rev-parse", f"refs/heads/{rc.base}")
                gitops.extract_backlog(main, sha, settings.backlog_patterns, base_copy)
            except (OSError, RuntimeError) as exc:
                raise TaskRunError("invalid_config", f"cannot read the backlog: {exc}") from exc
            committed_task = load_backlog(base_copy, settings).by_id.get(task_id)
            committed_writes = (
                effective_task_writes(committed_task) if isinstance(committed_task, Task) else ()
            )
        missing = [p for p in plan.allow if not any(matches(p, w) for w in committed_writes)]
        if missing:
            raise TaskRunError(
                "writes_not_committed",
                f"the backlog in base {rc.base} does not allow these paths for {task_id}: "
                f"{', '.join(missing)}; commit the backlog to base "
                f"(factory backlog commit), then run {again}",
            )
        return AllowWritesResult(plan, new_writes, commit)


def retry_note(result: AllowWritesResult, note: str | None = None) -> str:
    """The ``## Retry note`` of the retry after `result`: the allowed paths, the refused
    ones, then the operator's `note`."""
    lines = [
        "The task's writes now allow these paths, write them where the task needs it: "
        + ", ".join(result.plan.allow)
        + "."
    ]
    if result.plan.refused:
        lines.append(
            "Still not allowed: "
            + "; ".join(f"{r.path} ({REASONS[r.reason]})" for r in result.plan.refused)
            + "."
        )
    if note and note.strip():
        lines += ["", note.strip()]
    return "\n".join(lines)
