"""``factory task retry``: continue a failed or stopped run where it ended.

The retry is another attempt of the same run: the same ``run_id``, worktree and branch,
the same trace session (phases, tokens and costs add up) and the same session directory,
so every agent rejoins its coding-agent session (``agent_map.json``: ``claude --resume``,
``codex exec resume``, pi's ``--session-id``) when its model is unchanged. The prompt gets
a ``## Continuation`` section with the phases already done, their summaries and the
``context_handoff/`` directory, for an agent whose session is gone, and the operator's
note.

What the retry does, in order; any refusal before the claim changes nothing:

1. Refuses a run that is not ``failed``, ``stopped`` or ``aborted``
   (``run_not_retryable``), a task whose PR was merged or whose status in base is
   ``done`` (``task_done``) and a task with a running run (``already_running``).
2. Pulls base from the remote like ``factory config pull`` (``pull_base``); when base
   cannot move (``base_diverged``, ``dirty_base``, ``run_in_progress``, ...) it stops
   with that error.
3. Reads the configuration, the backlog and the task's workflow from the current base.
4. Picks the phase to continue from (``plan_retry``): the phase that failed or was
   stopped (the journal's ``current``); after an ``accept_not_met`` failure the top-level
   step whose result failed ``accept`` (a review loop gets a new round); with ``--from``
   the named phase. A phase whose step the current workflow lacks starts the workflow from its
   first phase, with a warning.
5. Claims the run again (``TaskRunStore.reclaim``).
6. When base moved past the branch, rebases the branch onto it (uncommitted work is
   committed first as work in progress); a conflict goes through the workflow
   ``resolve`` like ``factory task resolve`` (``rebase_for_retry``). When that fails the
   branch is put back as it was and the workflow does not run. After a rebase the
   replay ends at the last ``test`` before the first review, so the tests run again on
   the rebased code before anything is reviewed.
7. Runs the workflow replaying the journal (``aifactory.workflow.journal``) and publishes
   the PR like ``task run``. ``queue.retry_chain`` (``factory task retry`` and the
   dashboard) then auto-merges and auto-continues like ``task run``.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aifactory import failure as failures
from aifactory.backlog import Task, load_backlog
from aifactory.backlog.derived import is_done
from aifactory.config import ProjectSettings
from aifactory.providers import GitProvider, ProviderError, get_provider
from aifactory.providers import git as provider_git
from aifactory.run import gitops
from aifactory.run.errors import TaskRunError
from aifactory.run.resolve import (
    CI_FIX_WORKFLOW,
    INTERNAL_WORKFLOWS,
    ConflictWriteGuard,
    ResolveSpec,
    resolve_prompt,
    restore,
)
from aifactory.run.scope import output_paths, task_scope
from aifactory.run.stack import open_stack
from aifactory.run.store import MERGED_BY_AUTO, RUNNING, TaskRunRow, TaskRunStore, _now
from aifactory.run.workdir import project_workdir
from aifactory.workflow import (
    JOURNAL_FILE,
    CodeRunner,
    Generated,
    Journal,
    Workflow,
    WorkflowError,
    evaluate,
    preflight,
    read_journal,
    refs,
    run_workflow,
    walk,
)
from aifactory.workflow.interpreter import PLAN_REVIEW_PHASE
from aifactory.workflow.rebase import rebase_onto

if TYPE_CHECKING:  # task.py imports this module at run time
    from aifactory.run.task import TaskRunResult

ACCEPT_NOT_MET = "accept not met"  # the error of a resolve whose accept failed
_REVIEW_OUTPUT = "ReviewOutput"
_OVERRIDE_TAG = re.compile(r"\[přepis rosteru: ([^\]]*)\]")

__all__ = ["ACCEPT_NOT_MET", "RetryPlan", "plan_retry", "rebase_for_retry", "retry_run"]


@dataclass
class RetryPlan:
    """How many journal entries the retry replays and the phase it continues from."""

    limit: int
    resume: str | None  # phase name; None: the workflow's first phase or what follows
    warnings: list[str] = field(default_factory=list)


def _results(journal: Journal) -> dict[str, dict[str, Any]]:
    """The step results the journal's entries leave, as the interpreter keeps them."""
    results: dict[str, dict[str, Any]] = {}
    for entry in journal.entries:
        if not entry.kept:
            continue
        value = entry.result if entry.action == "commit" else entry.envelope
        results[entry.step] = {**(value or {}), "ran": True}
    return results


def _accept_target(journal: Journal, workflow: Workflow) -> int:
    """Where to continue after ``accept not met``: the top-level step that failed accept.

    The earliest top-level step whose latest result makes a reference of ``accept``
    false; without one, the last top-level step that ran. Its first entry is the limit,
    so a loop (a review with revisions, tests with repairs) gets a whole new round.
    """
    entries = journal.entries
    if not entries:
        return 0
    tops: list[str] = []
    if workflow.accept is not None:
        results = _results(journal)
        for ref in refs(workflow.accept.node):
            if ref.step not in results or evaluate(ref, results):
                continue
            last = next(e for e in reversed(entries) if e.kept and e.step == ref.step)
            tops.append(last.top)
    if not tops:
        tops = [entries[-1].top]
    return min(next(i for i, e in enumerate(entries) if e.top == top) for top in tops)


def _from_phase(journal: Journal, name: str, run_id: str) -> int:
    entries = journal.entries
    for i, entry in enumerate(entries):
        if entry.phase == name:
            return i
    for i, entry in enumerate(entries):
        if entry.step == name:
            return i
    current = journal.current or {}
    if name in (current.get("phase"), current.get("step")):
        return len(entries)
    known = [e.phase for e in entries] + ([current["phase"]] if current.get("phase") else [])
    raise TaskRunError(
        "unknown_phase",
        f"run {run_id} has no phase {name!r}; its phases: {', '.join(known) or '(none)'}",
    )


def plan_retry(
    journal: Journal,
    workflow: Workflow,
    *,
    run_id: str,
    error: str | None,
    from_phase: str | None = None,
    rebased: bool = False,
    failure_kind: str | None = None,
) -> RetryPlan:
    """The replay limit and resume phase of a retry (see the module docstring, step 4)."""
    entries = journal.entries
    warnings: list[str] = []
    if from_phase:
        limit = _from_phase(journal, from_phase.strip(), run_id)
    elif (
        failure_kind == failures.ACCEPT_NOT_MET
        or error == ACCEPT_NOT_MET
        or (
            journal.current is None
            and workflow.accept is not None
            and not evaluate(workflow.accept.node, _results(journal))
        )
    ):
        limit = _accept_target(journal, workflow)
    else:
        limit = len(entries)
    current = journal.current or {}
    resume: str | None
    step: str | None
    if limit < len(entries):
        resume, step = entries[limit].phase, entries[limit].step
    else:
        resume, step = current.get("phase"), current.get("step")
    keys = {leaf.key for leaf in walk(workflow.steps)} | {PLAN_REVIEW_PHASE}
    if step is not None and step not in keys:
        warnings.append(
            f"phase {resume} (step {step}) is not in workflow {workflow.name} any more; "
            "the run continues from the workflow's first phase"
        )
        return RetryPlan(0, None, warnings)
    if rebased:
        # the review of the code, not the review of a test plan
        reviews = [
            i
            for i, e in enumerate(entries[:limit])
            if e.output == _REVIEW_OUTPUT and e.step != PLAN_REVIEW_PHASE
        ]
        end = reviews[0] if reviews else limit
        tests = [i for i, e in enumerate(entries[:end]) if e.action == "test"]
        if tests and tests[-1] < limit:
            limit = tests[-1]
            resume = entries[limit].phase
    return RetryPlan(limit, resume, warnings)


def continuation(
    row: TaskRunRow,
    journal: Journal,
    plan: RetryPlan,
    note: str | None,
    handoff: Path,
    rebased_onto: str | None,
) -> str:
    """The ``## Continuation`` section of a retry's prompt."""
    lines = [
        "",
        "## Continuation",
        f"This is attempt {row.attempt + 1} of run {row.run_id}: it continues the earlier "
        "attempt in the same working directory and branch. Phases already done are not "
        "repeated; their results stand.",
        f"Continuing from phase: {plan.resume or '(the first phase)'}.",
    ]
    if row.error:
        lines.append(f"The earlier attempt ended: {row.error.strip()[:500]}")
    if rebased_onto:
        lines.append(
            f"The branch was rebased onto `{row.base}` (`{rebased_onto[:7]}`) before this "
            "attempt: the code around your change may have moved, check it again."
        )
    done = journal.entries[: plan.limit]
    if done:
        lines.append("Phases done:")
        lines += [f"- {e.phase}: {e.summary.strip()[:300] or '(no summary)'}" for e in done]
    lines.append(
        f"If you do not remember the earlier work, read the files in {handoff} and the "
        "outputs above before you go on. The previous attempt's full phase outputs are "
        f"in {handoff / f'retry_attempt_{row.attempt}.json'}."
    )
    text = "\n".join(lines) + "\n"
    if note and note.strip():
        text += f"\n## Retry note\n{note.strip()}\n"
    return text


def _note_override(note: str | None) -> dict[str, str] | None:
    """The roster override ``override_note`` recorded in the run's note, or None."""
    match = _OVERRIDE_TAG.search(note or "")
    if match is None:
        return None
    values = dict(part.strip().split("=", 1) for part in match.group(1).split(",") if "=" in part)
    return {k.strip(): v.strip() for k, v in values.items() if v.strip()} or None


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


def _refuse_done(store: TaskRunStore, task: Task | None, task_id: str) -> None:
    merged = [p for p in store.prs_for_task(task_id) if p.state == "merged"]
    if merged:
        how = "auto-merged" if merged[0].merged_by == MERGED_BY_AUTO else "merged"
        raise TaskRunError(
            "task_done", f"task {task_id} is already {how} ({merged[0].url}); nothing to retry"
        )
    if task is not None and is_done(task):
        raise TaskRunError(
            "task_done", f"task {task_id} is done (approved) in base; nothing to retry"
        )


def _pull_base(main: Path, settings: ProjectSettings, store: TaskRunStore) -> list[str]:
    """Fast-forward local base to the remote like ``factory config pull``."""
    from aifactory.providers import publish

    if not provider_git.has_remote(main, settings.remote):
        return []
    try:
        result = publish.pull_base(main, settings=settings, store=store)
    except ProviderError as exc:
        raise TaskRunError(
            exc.code, f"base cannot be brought up to date: {exc.message}; nothing changed"
        ) from exc
    except RuntimeError as exc:
        raise TaskRunError("pull_failed", f"{exc}; nothing changed") from exc
    return list(result.warnings)


def retry_run(
    repo: Path,
    task_id: str,
    *,
    run_id: str | None = None,
    note: str | None = None,
    from_phase: str | None = None,
    code: CodeRunner | None = None,
    provider: GitProvider | None = None,
) -> TaskRunResult:
    """Continue the task's newest (or `run_id`) failed or stopped run; a ``TaskRunResult``."""
    from aifactory.harness.settings import effective_override
    from aifactory.run import task as run_mod

    main = gitops.main_root(repo)
    rc = run_mod._load(main)
    store = TaskRunStore(rc.local.trace_db_path(main))
    try:
        row = _pick_run(store, task_id, run_id)
        busy = store.running(task_id)
        if busy is not None:
            from aifactory.run.store import already_running

            raise already_running(busy)
        if row.state == RUNNING or row.state not in ("failed", "stopped", "aborted"):
            raise TaskRunError(
                "run_not_retryable",
                f"run {row.run_id} of task {task_id} is {row.state}; only a failed, stopped "
                "or aborted run can be retried",
            )
        if row.workflow in INTERNAL_WORKFLOWS:
            again = (
                f"approve the PR again (factory task approve {task_id})"
                if row.workflow == CI_FIX_WORKFLOW
                else "run factory task resolve again"
            )
            raise TaskRunError(
                "run_not_retryable", f"run {row.run_id} is a {row.workflow} run; {again}"
            )
        _refuse_done(store, None, task_id)
        warnings = _pull_base(main, rc.config.settings, store)
        rc = run_mod._load(main)
        settings = rc.config.settings
        if provider is None:
            try:
                provider = get_provider(settings, main)
            except ProviderError as exc:
                raise TaskRunError(exc.code, exc.message) from exc
        with tempfile.TemporaryDirectory(prefix="factory-base-") as tmp:
            base_copy = Path(tmp)
            try:
                gitops.extract_backlog(main, rc.commit, settings.backlog_patterns, base_copy)
            except (OSError, RuntimeError) as exc:
                raise TaskRunError("invalid_config", f"cannot read the backlog: {exc}") from exc
            backlog = load_backlog(base_copy, settings)
        task = run_mod._find_task(backlog, task_id)
        if task is None:
            raise run_mod._missing_task(main, rc, backlog, task_id)
        _refuse_done(store, task, task_id)
        try:
            binding = effective_override(
                run_mod.task_harness_values(task), _note_override(row.note)
            )
            rc = run_mod.apply_agents_override(rc, binding)
        except ValueError as exc:
            raise TaskRunError("invalid_override", str(exc)) from exc
        outputs = output_paths(task, settings)
        workdir = project_workdir(settings)
        scope = task_scope(task, outputs)
        test_timeout = run_mod.resolve_test_timeout(task, settings)
        workflow = run_mod.resolve_workflow(task, rc.config)
        with tempfile.TemporaryDirectory(prefix="factory-prompts-") as prompts_tmp:
            probe = run_mod.prepare_cfg(main, rc, Path(prompts_tmp))
            try:
                preflight(workflow, probe)
            except WorkflowError as exc:
                raise TaskRunError("invalid_workflow", str(exc)) from exc

        tip = provider_git.rev_parse(main, f"refs/heads/{row.branch}")
        if tip is None:
            raise TaskRunError("unknown_branch", f"branch {row.branch} of run {row.run_id} is gone")
        worktree = Path(row.worktree)
        if not worktree.is_dir():
            other = provider_git.checked_out_in(main, row.branch)
            if other is not None:
                raise TaskRunError(
                    "branch_checked_out",
                    f"branch {row.branch} is checked out in {other}; free it first",
                )
        onto = rc.commit
        # a run stacked on a still open PR keeps its fork: base lacks the work it builds on
        rebase = not provider_git.is_ancestor(main, onto, tip) and (
            open_stack(store, row.branch) is None
        )
        lease = None
        if rebase:
            published_tip = provider_git.rev_parse(
                main, f"refs/remotes/{settings.remote}/{row.branch}"
            )
            if published_tip and provider_git.is_ancestor(main, published_tip, tip):
                lease = published_tip

        session_dir = run_mod.data_dir(main, rc) / "sessions" / row.run_id
        journal = read_journal(session_dir / JOURNAL_FILE)
        if not journal.entries and journal.current is None:
            warnings.append(
                f"run {row.run_id} has no phase journal (an older run); the workflow starts "
                "from its first phase, the agents rejoin their sessions"
            )
        plan = plan_retry(
            journal,
            workflow,
            run_id=row.run_id,
            error=row.error,
            from_phase=from_phase,
            rebased=rebase,
            failure_kind=row.failure_kind,
        )
        warnings += plan.warnings
        prompt = run_mod.task_prompt(task, scope, outputs, worktree, row.note)
        if workdir != ".":
            prompt += (
                f"\nAgent working directory: {worktree / workdir}. "
                f"Repository root: {worktree}. spec, docs, writes and artifact paths "
                "are relative to the repository root, "
                "including when running from this subdirectory.\n"
            )
        prompt += continuation(
            row, journal, plan, note, session_dir / "context_handoff", onto if rebase else None
        )
        retry = {
            "started_at": _now(),
            "from_phase": plan.resume,
            "replayed": plan.limit,
            "note": note.strip() if note and note.strip() else None,
            "rebased_onto": onto if rebase else None,
            "previous_state": row.state,
            "previous_error": row.error,
        }
        claimed = store.reclaim(row.run_id, os.getpid(), retry)
        result = run_mod._execute(
            main,
            rc,
            store,
            claimed,
            run_mod._Job(
                workflow,
                prompt,
                scope,
                outputs,
                task,
                False,
                None,
                test_timeout,
                workdir,
                retry=run_mod.RetrySpec(
                    journal=journal,
                    limit=plan.limit,
                    onto=onto if rebase else None,
                    baseline=None if rebase else (journal.baseline or None),
                    lease=lease,
                    request_log={
                        "retry": f"attempt {claimed.attempt}",
                        "resume_from": plan.resume or "(first phase)",
                        "replayed_phases": plan.limit,
                        **({"rebased_onto": onto[:7]} if rebase else {}),
                        **({"retry_note": retry["note"]} if retry["note"] else {}),
                    },
                ),
            ),
            code,
            provider,
        )
        result.warnings = (*result.warnings, *warnings)
        return result
    finally:
        store.close()


def rebase_for_retry(
    main: Path,
    worktree: Path,
    task: Task,
    onto: str,
    base: str,
    *,
    generated: tuple[Generated, ...],
    ignored: tuple[str, ...],
    workflow: Workflow,
    run_kwargs: dict[str, Any],
    variables: dict[str, str],
    prompt_suffix: str = "",
) -> str | None:
    """Rebase the run's branch onto `onto`; None when done, else why (branch put back).

    Uncommitted work is committed first as work in progress, so the rebase carries it.
    A conflict runs `workflow` (``resolve``) in the worktree, as ``factory task resolve``
    does: the agent may change only the conflicted files, the suite runs, code commits
    the resolution (``finish_resolve``). On any failure the branch and the worktree are
    put back exactly as they were, uncommitted work included.
    """
    from aifactory.run.task import _finish_resolve

    before = gitops.head(worktree)
    if before is None:
        return "the run's worktree has no HEAD"
    index_path = Path(gitops.git(worktree, "rev-parse", "--git-path", "index"))
    if not index_path.is_absolute():
        index_path = worktree / index_path
    index_before = index_path.read_bytes() if index_path.exists() else None
    if gitops.git(worktree, "status", "--porcelain"):
        gitops.git(worktree, "add", "-A")
        gitops.git(
            worktree,
            "commit",
            "-q",
            "-m",
            f"{task.id}: work in progress before the rebase onto {base} {onto[:7]}",
        )
    tip = gitops.head(worktree) or before

    def put_back(error: str) -> str:
        try:
            restore(worktree, tip)
            if tip != before:
                gitops.git(worktree, "reset", "-q", "--soft", before)
                gitops.git(worktree, "reset", "-q")
                if index_before is not None:
                    index_path.write_bytes(index_before)
        except (RuntimeError, OSError) as exc:
            return f"{error}; the branch was not restored: {exc}"[:2000]
        return error[:2000]

    try:
        rebased = rebase_onto(worktree, onto)
    except RuntimeError as exc:
        return put_back(f"rebase onto {base} {onto[:7]} failed: {exc}")
    except BaseException:
        put_back("rebase interrupted")
        raise
    if not rebased.conflict:
        return None
    try:
        restore(worktree, tip)
    except (RuntimeError, OSError) as exc:
        return put_back(f"rebase onto {base} {onto[:7]} failed: {exc}")
    spec = ResolveSpec(onto=onto, before=tip, base=base, generated=generated)
    guard = ConflictWriteGuard(main, worktree, task.id, ignored, generated)
    prompt = resolve_prompt(task, worktree, base, onto, tuple(g.path for g in generated))
    prompt += prompt_suffix
    wf = None
    error: str | None = None
    try:
        wf = run_workflow(
            workflow,
            prompt,
            write_guard=guard,
            prompt_variables={**variables, "rebase_onto": onto},
            generated=generated,
            **run_kwargs,
        )
    except Exception as exc:
        error = str(exc)[:2000] or type(exc).__name__
    except BaseException:
        put_back("resolve interrupted")
        raise
    if error is None and wf is not None and not (wf.accepted and wf.exit_code == 0):
        error = ACCEPT_NOT_MET
    error = _finish_resolve(worktree, wf, task.id, spec, error)
    if error is not None:
        return put_back(f"resolve after the rebase onto {base} {onto[:7]} failed: {error}")
    return None
