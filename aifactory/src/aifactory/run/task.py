"""``run_task``: start one backlog task in its own worktree and branch.

Check the task can start, create ``<worktrees_dir>/<run-id>`` on a new branch
``factory/<task-id>-<n>`` from ``base``, run the task's workflow there, record
the run in ``task_runs``. When ``accept`` is met the branch is pushed and its
pull request opened (or updated) through the configured ``GitProvider``
(``aifactory.review.publish``); the PR is a row in ``task_prs``. When that fails the
run stays succeeded with ``task_runs.pr_error`` (``factory task publish`` retries).

``factory task resolve`` (step 6) runs the workflow ``resolve`` on the branch
of a conflicting PR (``resolve.py``): rebase onto base, the agent settles the
conflicts, the suite runs, the branch is force-pushed with a lease. A failed
resolve run leaves the branch where it was before the rebase.

``factory task pause|resume`` (``pause.py``) hold a run between two phases: the
workflow calls the run's ``PauseGate`` before every phase.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import tempfile
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

from aifactory import database
from aifactory import failure as failures
from aifactory import harness as harness_mod
from aifactory.backlog import (
    Backlog,
    Task,
    effective_test_timeout,
    effective_workflow,
    has_workflow,
    is_human,
    load_backlog,
    unmet,
)
from aifactory.backlog.derived import ancestors, harness_values
from aifactory.config import (
    ConfigError,
    FactoryConfig,
    ProjectSettings,
    RunConfig,
    check_timeout,
    load_local,
    load_run_config,
)
from aifactory.config.loader import write_prompts
from aifactory.engine.quality import DEFAULT_TEST_TIMEOUT
from aifactory.engine.slots import TestSlots, default_slots_dir
from aifactory.engine.utils import new_id
from aifactory.harness.config import SSSFConfig
from aifactory.harness.override import THINKING_LEVELS
from aifactory.library.inherit import copy_library_items
from aifactory.providers import GitProvider, ProviderError, get_provider
from aifactory.providers import git as provider_git
from aifactory.run import basemoves, followups, gitops
from aifactory.run.accept import accept_failure
from aifactory.run.errors import TaskRunError
from aifactory.run.follows import FollowedTask, followed_section, followed_task
from aifactory.run.followups import FollowUpOutcome
from aifactory.run.guard import TaskWriteGuard
from aifactory.run.pause import PauseGate
from aifactory.run.resolve import (
    INTERNAL_WORKFLOWS,
    RESOLVE_WORKFLOW,
    ConflictWriteGuard,
    ResolveSpec,
    explain_allowed_repair_request,
    finish_resolve,
    resolve_prompt,
    restore,
)
from aifactory.run.scope import (
    OutputPaths,
    TaskScope,
    output_paths,
    task_scope,
)
from aifactory.run.stack import stack_point, stacked_on
from aifactory.run.store import (
    FAILED,
    RUNNING,
    STARTED_AUTO_CONTINUE,
    STARTED_MANUAL,
    SUCCEEDED,
    TaskPrRow,
    TaskRunRow,
    TaskRunStore,
    _now,
    already_running,
)
from aifactory.run.unchanged import finish_unchanged, only_spec_changes, unchanged
from aifactory.run.workdir import agent_workdir, project_workdir, validate_base_dirs
from aifactory.testing.profile import ProfileCache
from aifactory.workflow import (
    DEFAULT_WORKFLOWS_DIR,
    JOURNAL_FILE,
    CodeRunner,
    CodeStep,
    Generated,
    Journal,
    Workflow,
    WorkflowError,
    WorkflowRun,
    load_workflow,
    parse_workflow,
    preflight,
    run_workflow,
    walk,
)

if TYPE_CHECKING:  # review imports run; a runtime import would be a cycle
    from aifactory.review.automerge import AutoMergeResult

SSSF_DATA_DIR = "adws/adw_data"  # the engine's default; a task run uses FACTORY_DATA_DIR
FACTORY_DATA_DIR = ".factory/data"
_TRACE_DB_SUFFIXES = ("", "-wal", "-shm", "-journal")


@dataclass
class TaskRunResult:
    run: TaskRunRow
    workflow_run: WorkflowRun | None
    warnings: tuple[str, ...]
    trace_db: Path
    pr: TaskPrRow | None = None
    pr_error: str | None = None
    # set by run_chain when the task has `auto_merge: true` (review/automerge.py)
    auto_merge: AutoMergeResult | None = None
    # a chain member's auto-resolve run of its conflicting PR (cli `--member`)
    resolve_run: TaskRunResult | None = None
    # new work and blockers the run's agents reported, filed in the backlog (followups.py)
    follow_ups: FollowUpOutcome | None = None
    # the run changed nothing, so the task was marked done without a PR (run/unchanged.py)
    done_without_pr: bool = False
    # a chain closed its ``nothing_to_do`` failure: the task is done without changes (heal.py)
    closed_by_heal: bool = False

    @property
    def ok(self) -> bool:
        return self.run.state == SUCCEEDED and self.pr_error is None


# ── prompt, workflow, config ─────────────────────────────────────────────────


def task_prompt(
    task: Task,
    scope: TaskScope,
    outputs: OutputPaths,
    worktree: Path,
    note: str | None,
    follows: FollowedTask | None = None,
) -> str:
    """Task header, then the task text, then the original task, then the operator's note.

    The only absolute path is the worktree; every other path is relative to it.
    `follows` is the done task this one continues (``followed_task``); its section
    (``followed_section``) comes after the task text.
    """
    lines = [f"# Task {task.id}: {task.title}", "", f"- id: {task.id}", f"- title: {task.title}"]
    for container in reversed(ancestors(task)):
        label = " — ".join(x for x in (container.id, container.title) if x)
        if label:
            lines.append(f"- {container.level}: {label}")
    lines += [
        f"- working directory: {worktree} (all repository paths are relative to it)",
        f"- allowed paths: {', '.join(scope.paths)}",
        f"- spec file: {outputs.spec}",
        f"- documentation file: {outputs.doc}",
        "- The allowed paths are the task's, shared by all its agents. Change only the paths "
        "in the Write scope of your system prompt; anything else, including any file "
        "outside the working directory, is reverted and fails the phase.",
    ]
    if follows is not None:
        origin, origin_outputs = follows.task, follows.outputs
        lines.append(
            f"- follows: {origin.id} — {origin.title} (done; this task continues it, see "
            f"the section about {origin.id} below and read its files first: task file "
            f"{origin.path}, spec {origin_outputs.spec}, documentation {origin_outputs.doc})"
        )
    text = "\n".join(lines) + "\n"
    body = task.body.strip()
    if body:
        text += f"\n{body}\n"
    if follows is not None:
        text += "\n" + followed_section(follows)
    if note and note.strip():
        text += f"\n## Note\n{note.strip()}\n"
    return text


def no_workflow_error(task: Task) -> TaskRunError:
    return TaskRunError(
        "no_workflow", f"task {task.id} has no workflow, set `workflow:` on it or a container"
    )


def resolve_workflow(task: Task, config: FactoryConfig) -> Workflow:
    """The task's workflow, see ``named_workflow``."""
    name = effective_workflow(task)
    if name is None:
        raise no_workflow_error(task)
    if not isinstance(name, str) or not name.strip():
        raise TaskRunError("invalid_workflow", f"task {task.id}: workflow {name!r} is not a name")
    return named_workflow(name, config, task.id)


def resolve_test_timeout(task: Task, settings: ProjectSettings) -> int:
    """Time limit in seconds of every ``test`` step of the run.

    The task's ``test_timeout``, else the nearest ``index.md`` ``test_timeout`` above
    it, else ``test_timeout`` from ``.factory/config.yaml``, else 600.
    """
    value = effective_test_timeout(task)
    if value is not None:
        try:
            return check_timeout(value)
        except ValueError as exc:
            raise TaskRunError(
                "invalid_test_timeout", f"task {task.id}: test_timeout {value!r} {exc}"
            ) from exc
    if settings.test_timeout is not None:
        return settings.test_timeout
    return DEFAULT_TEST_TIMEOUT


def named_workflow(name: str, config: FactoryConfig, task_id: str) -> Workflow:
    """Workflow `name` of a run.

    ``.factory/workflows/`` in base first, then the library (the seed without one);
    ``config.workflows`` holds both. The internal resolve workflows also come from the
    package.
    """
    try:
        if name in config.workflows:
            return parse_workflow(config.workflows[name], config.roles)
        if name in INTERNAL_WORKFLOWS:
            return load_workflow(DEFAULT_WORKFLOWS_DIR / f"{name}.yaml", config.roles)
    except WorkflowError as exc:
        raise TaskRunError("invalid_workflow", f"workflow {name}: {exc}") from exc
    raise TaskRunError(
        "unknown_workflow",
        f"workflow {name!r} of task {task_id} is neither in .factory/workflows/ in base "
        "nor in the library",
    )


def _absolute(value: str, root: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (root / path).resolve()


def data_dir(main: Path, rc: RunConfig) -> Path:
    """The session runtime of task runs: agents.yaml ``data_dir``, else ``.factory/data``.

    Always in (or relative to) the main checkout, shared by all runs.
    """
    value = str(rc.config.agents.defaults.data_dir)
    if not value.strip() or value.rstrip("/") == SSSF_DATA_DIR:
        value = FACTORY_DATA_DIR
    return _absolute(value, main)


def prepare_cfg(main: Path, rc: RunConfig, prompts_dir: Path) -> SSSFConfig:
    """The roster of `rc` with prompts in `prompts_dir`, runtime and trace in the main checkout."""
    cfg = write_prompts(rc.config, prompts_dir).model_copy(deep=True)
    cfg.defaults.data_dir = str(data_dir(main, rc))
    cfg.observability.db = str(rc.local.trace_db_path(main))
    protected = [*cfg.defaults.protected_files, *rc.config.settings.protected_files]
    cfg.defaults.protected_files = list(dict.fromkeys(protected))
    return cfg


def _relative_to(path: Path, root: Path) -> str | None:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def _main_ignored(main: Path, worktrees_dir: str, cfg: SSSFConfig) -> tuple[str, ...]:
    """What the guard ignores in the main checkout: worktrees, session runtime, trace DB."""
    ignored = [worktrees_dir.strip("/").removeprefix("./") + "/"]
    data = _relative_to(Path(cfg.defaults.data_dir), main)
    if data:
        ignored.append(data.rstrip("/") + "/")
    db = _relative_to(Path(cfg.observability.db), main)
    if db:
        ignored += [db + suffix for suffix in _TRACE_DB_SUFFIXES]
    return tuple(ignored)


def _exclude_lines(ignored: tuple[str, ...]) -> list[str]:
    lines = []
    for entry in ignored:
        if entry.endswith("/"):
            lines.append("/" + entry)
        elif entry.endswith(_TRACE_DB_SUFFIXES[1:]):
            continue
        else:
            lines.append("/" + entry + "*")
    return lines


# ── backlog from base ────────────────────────────────────────────────────────


def _find_task(backlog: Backlog, task_id: str) -> Task | None:
    node = backlog.by_id.get(task_id)
    return node if isinstance(node, Task) else None


def _missing_task(main: Path, rc: RunConfig, base: Backlog, task_id: str) -> TaskRunError:
    node = base.by_id.get(task_id)
    if node is not None:
        return TaskRunError("unknown_task", f"{task_id} is a {node.level}, not a task")
    current = load_backlog(main, rc.config.settings).by_id.get(task_id)
    if isinstance(current, Task):
        return TaskRunError(
            "task_not_in_base",
            f"task {task_id} exists only in the working tree ({current.path}); "
            f"commit it to {rc.base} first",
        )
    if current is not None:
        return TaskRunError("unknown_task", f"{task_id} is a {current.level}, not a task")
    return TaskRunError("unknown_task", f"no task {task_id} in the backlog")


def _unmet_error(backlog: Backlog, task: Task, base: str) -> TaskRunError | None:
    missing = unmet(backlog, task)
    if not missing:
        return None
    detail = ", ".join(
        f"{u.id} ({u.reason}"
        + (f": {', '.join(u.missing)}" if u.missing and u.missing != [u.id] else "")
        + ")"
        for u in missing
    )
    return TaskRunError(
        "unmet_dependencies",
        f"task {task.id} depends on work not done in {base}: {detail} (use --force to run anyway)",
    )


# ── signals ──────────────────────────────────────────────────────────────────

_SIGNAL_LOCK = threading.Lock()


def _keep_signal(sig: int, handler: Any) -> Any:
    return signal.getsignal(sig)


@contextlib.contextmanager
def _signals_restored() -> Iterator[None]:
    """The engine installs SIGINT/SIGTERM handlers bound to one run; drop them afterwards.

    Off the main thread Python cannot install handlers at all, so there the
    engine's ``signal.signal`` call is turned into a no-op for the run.
    """
    if threading.current_thread() is not threading.main_thread():
        with _SIGNAL_LOCK, mock.patch.object(signal, "signal", _keep_signal):
            yield
        return
    sigs = (signal.SIGINT, signal.SIGTERM)
    saved = {s: signal.getsignal(s) for s in sigs}
    try:
        yield
    finally:
        for sig, handler in saved.items():
            with contextlib.suppress(ValueError, TypeError):
                signal.signal(sig, handler)


# ── the run ──────────────────────────────────────────────────────────────────


def _load(main: Path) -> RunConfig:
    try:
        return load_run_config(main)
    except ConfigError as exc:
        raise TaskRunError("invalid_config", str(exc)) from exc


OVERRIDE_KEYS = ("harness", "model", "thinking")
# The model a harness switch picks when no model is given (``config.roster.PRESETS``).
_HARNESS_MODELS = {"claude": "claude-opus-5-5", "codex": "gpt-6.1-sol"}


def apply_agents_override(rc: RunConfig, override: dict[str, str] | None) -> RunConfig:
    """`rc` with every agent of the roster on the given harness/model/thinking (in memory).

    The same as ``factory config roster set`` with defaults only: every role-level value
    is replaced. Nothing is written. A harness switch without a model takes that
    harness's preset model. Step overrides of the workflow (``harness/override.py``) still
    apply on top, so one workflow can still mix harnesses. Unknown harness, thinking or a
    model the harness rejects raise ``invalid_override``.
    """
    values = {k: v.strip() for k, v in (override or {}).items() if v and v.strip()}
    unknown = sorted(set(values) - set(OVERRIDE_KEYS))
    if unknown:
        raise TaskRunError("invalid_override", f"unknown override key(s): {', '.join(unknown)}")
    if not values:
        return rc
    harness = values.get("harness")
    if harness is not None:
        try:
            harness = harness_mod.canonical(harness)
        except ValueError as exc:
            raise TaskRunError("invalid_override", str(exc)) from exc
    thinking = values.get("thinking")
    if thinking is not None and thinking not in THINKING_LEVELS:
        raise TaskRunError(
            "invalid_override", f"thinking {thinking!r} is not one of {list(THINKING_LEVELS)}"
        )
    model = values.get("model")
    agents = []
    for agent in rc.config.agents.agents:
        update: dict[str, Any] = {}
        agent_harness = harness or agent.harness
        if harness is not None:
            update["coding_agent"] = harness
        if model is not None:
            update["model"] = model
        elif harness is not None and harness != agent.harness and harness in _HARNESS_MODELS:
            update["model"] = _HARNESS_MODELS[harness]
        if thinking is not None:
            update["thinking"] = thinking
        if agent_harness != "pi" and agent.harness_engineering:
            update["harness_engineering"] = []  # pi extensions belong to pi only
        try:
            harness_mod.load(agent_harness).resolve_model(update.get("model", agent.model))
        except (ValueError, ImportError) as exc:
            raise TaskRunError("invalid_override", f"agent {agent.name!r}: {exc}") from exc
        agents.append(agent.model_copy(update=update, deep=True))
    defaults = rc.config.agents.defaults.model_copy(
        update={
            k: v
            for k, v in (("coding_agent", harness), ("model", model), ("thinking", thinking))
            if v is not None
        },
        deep=True,
    )
    roster = rc.config.agents.model_copy(update={"agents": agents, "defaults": defaults})
    return replace(rc, config=replace(rc.config, agents=roster))


def override_note(note: str | None, override: dict[str, str] | None) -> str | None:
    """`note` with the per-run harness override appended, so the run shows it."""
    values = [f"{k}={v.strip()}" for k, v in (override or {}).items() if v and v.strip()]
    if not values:
        return note
    tag = f"[přepis rosteru: {', '.join(values)}]"
    return f"{note} {tag}" if note else tag


def task_harness_values(task: Task) -> dict[str, object]:
    """A harness switch at a nearer level inherits that harness's model, not its sibling's."""
    return harness_values(task)


def run_task(
    repo: Path,
    task_id: str,
    *,
    note: str | None = None,
    force: bool = False,
    code: CodeRunner | None = None,
    provider: GitProvider | None = None,
    branch: str | None = None,
    resolve_onto: str | None = None,
    resolve_with: str = RESOLVE_WORKFLOW,
    started_by: str = STARTED_MANUAL,
    agents_override: dict[str, str] | None = None,
    workflow_name: str | None = None,
) -> TaskRunResult:
    """Start `task_id` in a fresh worktree; raise `TaskRunError` if it cannot start.

    ``agents_override`` (``harness``, ``model``, ``thinking``) puts every agent of the
    roster on them for this run only (``apply_agents_override``); step overrides of the
    workflow still win.

    ``force`` skips only the check of ``depends_on``; it never overrides a
    running task, a task without ``writes`` or a task without a workflow
    (effective ``workflow`` unset or ``null``). ``provider`` defaults to the one
    ``git_provider`` names. ``branch`` is internal: ``review.return_task`` passes
    the branch of the returned PR, and the run continues on it instead of a new
    branch from ``base``. ``resolve_onto`` is internal too: ``review.resolve_task``
    passes the commit of ``base`` to rebase `branch` onto, and the run uses the
    workflow ``resolve`` (or ``resolve_with``) instead of the task's own. ``workflow_name``
    is internal as well: ``review.ci`` passes ``ci-fix`` with `branch`, and the run uses
    that workflow instead of the task's own, with the task's scope and prompt (the note
    holds the red checks). ``started_by`` records who started the run (``manual``; a chain
    ``auto-continue``, auto-merge ``auto-resolve``, a CI repair ``auto-ci-fix``).
    Auto-continue resumes the task's newest failed ordinary run through ``retry_run``
    instead of discarding its branch and completed phases.
    """
    main = gitops.main_root(repo)
    rc = _load(main)
    settings = rc.config.settings
    if started_by == STARTED_AUTO_CONTINUE and branch is None and workflow_name is None:
        previous = task_runs_for(main, task_id)
        if (
            previous
            and previous[0].state == FAILED
            and previous[0].workflow not in INTERNAL_WORKFLOWS
        ):
            from aifactory.run.retry import retry_run

            return retry_run(
                main,
                task_id,
                run_id=previous[0].run_id,
                note=note,
                code=code,
                provider=provider,
                agents_override=agents_override,
            )
    store = TaskRunStore(rc.local.trace_db_path(main))
    try:
        if provider is None:
            try:
                provider = get_provider(settings, main)
            except ProviderError as exc:
                raise TaskRunError(exc.code, exc.message) from exc
        fork_sha = rc.commit
        before: str | None = None
        if resolve_onto is not None and branch is None:
            raise TaskRunError("unknown_branch", "a resolve run needs the branch of the PR")
        if workflow_name is not None and branch is None:
            raise TaskRunError(
                "unknown_branch", f"a {workflow_name} run needs the branch of the PR"
            )
        if branch is not None:
            before = provider_git.rev_parse(main, f"refs/heads/{branch}")
            if before is None:
                raise TaskRunError("unknown_branch", f"branch {branch} does not exist")
            existing_pr = store.pr_for_branch(branch)
            if existing_pr is not None:
                fork_sha = existing_pr.base_sha
        fork_base = fork_sha
        if resolve_onto is not None:
            fork_sha = resolve_onto
        with tempfile.TemporaryDirectory(prefix="factory-base-") as tmp:
            base_copy = Path(tmp)
            try:
                gitops.extract_backlog(main, rc.commit, settings.backlog_patterns, base_copy)
            except (OSError, RuntimeError) as exc:
                raise TaskRunError("invalid_config", f"cannot read the backlog: {exc}") from exc
            backlog = load_backlog(base_copy, settings)
            task = _find_task(backlog, task_id)
            if task is None:
                raise _missing_task(main, rc, backlog, task_id)
            from aifactory.harness.settings import effective_override

            try:
                binding = effective_override(task_harness_values(task), agents_override)
                rc = apply_agents_override(rc, binding)
            except ValueError as exc:
                raise TaskRunError("invalid_override", str(exc)) from exc
            chain_start: _ChainStart | None = None
            if agents_override is None and resolve_onto is None and workflow_name is None:
                chain_start = _chain_start(store, rc, task, binding)
                if chain_start is not None and chain_start.rc is not None:
                    rc, binding = chain_start.rc, chain_start.binding
            note = override_note(note, binding)
            busy = store.running(task_id)
            if busy is not None:
                raise already_running(busy)
            if resolve_onto is None and is_human(task):
                raise TaskRunError(
                    "human_task", f"task {task.id} is for a person (assignee: human), not a run"
                )
            if resolve_onto is None and workflow_name is None and not has_workflow(task):
                raise no_workflow_error(task)
            stacked: str | None = None
            if not force:
                blocked = _unmet_error(backlog, task, rc.base)
                stack = (
                    stack_point(main, backlog, task, store)
                    if blocked is not None and settings.stacked_prs and branch is None
                    else None
                )
                if stack is not None:
                    # the dependencies wait in open PRs: fork from the newest of them
                    point, prs = stack
                    fork_sha, stacked = point.sha, point.branch
                    note = f"{note}\n\n{point.note(prs)}" if note else point.note(prs)
                elif blocked is not None:
                    raise blocked
            outputs = output_paths(task, settings)
            workdir = project_workdir(settings)
            validate_base_dirs(
                main,
                fork_sha,
                (workdir, str(Path(outputs.spec).parent), str(Path(outputs.doc).parent)),
                workdir,
            )
            scope = task_scope(task, outputs)
            if not scope.writes and resolve_onto is None:
                raise TaskRunError(
                    "no_writes",
                    f"task {task_id} has no writes, neither its own nor inherited from index.md",
                )
            test_timeout = resolve_test_timeout(task, settings)
            if resolve_onto is None and workflow_name is not None:
                workflow = named_workflow(workflow_name, rc.config, task_id)
            elif resolve_onto is None:
                workflow = resolve_workflow(task, rc.config)
            else:
                workflow = named_workflow(resolve_with, rc.config, task_id)
                if not any(
                    isinstance(s, CodeStep) and s.action == "rebase" for s in walk(workflow.steps)
                ):
                    raise TaskRunError(
                        "invalid_workflow", f"workflow {resolve_with} needs a rebase step"
                    )
            with tempfile.TemporaryDirectory(prefix="factory-prompts-") as prompts_tmp:
                probe = prepare_cfg(main, rc, Path(prompts_tmp))
                try:
                    preflight(workflow, probe)
                except WorkflowError as exc:
                    raise TaskRunError("invalid_workflow", str(exc)) from exc

        run_id = str(new_id(8))
        new_branch = branch is None
        if branch is None:
            branch = gitops.next_branch(main, task_id, store)
        worktree = (main / settings.worktrees_dir / run_id).resolve()
        resolve: ResolveSpec | None = None
        if resolve_onto is not None:
            assert before is not None
            generated = tuple(
                Generated(path=g.path, argv=g.command, timeout=g.timeout)
                for g in settings.generated
            )
            upstream = (
                fork_base
                if fork_base and not provider_git.is_ancestor(main, fork_base, resolve_onto)
                else None
            )
            resolve = ResolveSpec(
                onto=resolve_onto,
                before=before,
                base=rc.base,
                repair_scope=scope,
                generated=generated,
                upstream=upstream,
            )
            prompt = resolve_prompt(
                task,
                worktree,
                rc.base,
                resolve_onto,
                tuple(g.path for g in generated),
                repair_paths=scope.paths,
            )
        else:
            followed = followed_task(
                backlog, task, settings, main=main, commit=rc.commit, store=store
            )
            prompt = task_prompt(task, scope, outputs, worktree, note, followed)
            if workdir != ".":
                prompt += (
                    f"\nAgent working directory: {worktree / workdir}. "
                    f"Repository root: {worktree}. spec, docs, writes and artifact paths "
                    "are relative to the repository root, "
                    "including when running from this subdirectory.\n"
                )
        if any(isinstance(s, CodeStep) and s.action == "test" for s in walk(workflow.steps)):
            prompt += (
                "\n## Workflow verification\n"
                "This workflow has a separate test step. The builder implements and updates "
                "regression tests; the tester selects checks and the test runner executes them. "
                "The builder should run only a single targeted diagnostic test when needed "
                "to resolve an implementation question, then hand verification to the tester.\n"
            )
        prompt += followups.dependency_prompt(backlog, task)
        row = TaskRunRow(
            run_id=run_id,
            task_id=task_id,
            branch=branch,
            worktree=str(worktree),
            base=rc.base,
            base_sha=fork_sha,
            head_sha=None,
            state=RUNNING,
            started_at=_now(),
            pid=os.getpid(),
            workflow=workflow.name,
            note=note,
            started_by=started_by,
            library_commit=rc.config.library,
            stacked_on=stacked,
            harness_start=(
                json.dumps(chain_start.record, ensure_ascii=False)
                if chain_start is not None and chain_start.record is not None
                else None
            ),
        )
        store.claim(row)
        if chain_start is not None:
            chain_start.commit(store)
        result = _execute(
            main,
            rc,
            store,
            row,
            _Job(
                workflow,
                prompt,
                scope,
                outputs,
                task,
                new_branch,
                resolve,
                test_timeout,
                workdir,
                request_log=chain_start.request_log() if chain_start is not None else None,
            ),
            code,
            provider,
        )
        if chain_start is not None and chain_start.warnings:
            result.warnings = (*chain_start.warnings, *result.warnings)
        clear_quota_on_success(store, result, binding, rc)
    finally:
        store.close()
    if resolve_onto is not None or workflow_name is not None:
        return result  # a resolve or ci-fix run is not retried
    from aifactory.run.fallback import continue_on_fallback
    from aifactory.run.heal import auto_heal_enabled

    return continue_on_fallback(
        main, result, code=code, provider=provider, enabled=auto_heal_enabled(task), task=task
    )


@dataclass
class _ChainStart:
    """Where a new run starts in its project's quota chain (``quota_chain.py``)."""

    project_id: str
    position: str | None  # the project's place in the chain after the start
    changes: bool  # whether the place changes (written after the run is claimed)
    rc: RunConfig | None = None  # the configuration on the start harness; None: unchanged
    binding: dict[str, str] = field(default_factory=dict)
    record: dict[str, Any] | None = None  # ``harness_start``
    warnings: tuple[str, ...] = ()

    def commit(self, store: TaskRunStore) -> None:
        if self.changes:
            store.set_project_position(self.project_id, self.position)

    def request_log(self) -> dict[str, Any] | None:
        from aifactory.run.fallback import SWITCH_KEY, switch_text

        if self.record is None:
            return None
        return {SWITCH_KEY: switch_text(self.record)}


def _chain_start(
    store: TaskRunStore, rc: RunConfig, task: Task, binding: dict[str, str]
) -> _ChainStart | None:
    """The start of a new run on its project's quota chain; None without a chain."""
    from aifactory.harness.settings import effective_override
    from aifactory.run.fallback import _side
    from aifactory.run.quota_chain import QUOTA, project_chain, start_harness, start_record

    primary = binding.get("harness") or rc.config.agents.defaults.harness
    if not primary and rc.config.agents.agents:
        primary = rc.config.agents.agents[0].harness
    pc = project_chain(task, primary)
    if pc is None:
        return None
    stored = store.project_position(pc.project_id)
    start = start_harness(store, pc)
    changes = start.position != stored
    if start.reason is None:
        return _ChainStart(pc.project_id, None, changes)
    new_binding = binding
    new_rc: RunConfig | None = None
    if start.harness != pc.primary:
        try:
            new_binding = effective_override(task_harness_values(task), {"harness": start.harness})
            new_rc = apply_agents_override(rc, new_binding)
        except (ValueError, TaskRunError) as exc:
            message = exc.message if isinstance(exc, TaskRunError) else str(exc)
            return _ChainStart(
                pc.project_id,
                None,
                stored is not None,
                warnings=(
                    f"quota chain: cannot start on {start.harness}: {message}; "
                    f"the run starts on {pc.primary}",
                ),
            )

    def side(harness: str, values: dict[str, str]) -> dict[str, str]:
        return {"harness": harness, **{k: v for k, v in _side(values).items() if k != "harness"}}

    if start.reason == QUOTA:
        before = side(pc.primary, binding)
    else:
        before = {"harness": start.previous or pc.primary}
    after = side(start.harness, binding if start.harness == pc.primary else new_binding)
    record = start_record(before, after, start.reason, pc)
    return _ChainStart(pc.project_id, start.position, changes, new_rc, new_binding, record)


def clear_quota_on_success(
    store: TaskRunStore, result: TaskRunResult, binding: dict[str, str], rc: RunConfig
) -> None:
    """A succeeded run's harness has quota again (``harness_quota``, ``quota_chain.py``)."""
    if result.run.state != SUCCEEDED:
        return
    harness = binding.get("harness") or rc.config.agents.defaults.harness
    if harness:
        store.clear_quota(harness_mod.canonical(harness))


@dataclass
class RetrySpec:
    """What a retry (``retry.py``) adds to `_execute`: the replay and an optional rebase."""

    journal: Journal
    limit: int  # how many journal entries the workflow replays
    onto: str | None = None  # rebase the branch onto this base commit first
    baseline: str | None = None  # the first attempt's baseline (None: HEAD, or `onto`)
    lease: str | None = None  # a previously pushed tip whose history the rebase rewrites
    request_log: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _Job:
    """What `_execute` runs: the workflow, its prompt, the scope and the branch kind."""

    workflow: Workflow
    prompt: str
    scope: TaskScope
    outputs: OutputPaths
    task: Task
    new_branch: bool
    resolve: ResolveSpec | None = None
    test_timeout: int = DEFAULT_TEST_TIMEOUT
    workdir: str = "."
    retry: RetrySpec | None = None
    request_log: dict[str, Any] | None = None  # extra lines of a fresh run's request log


def _execute(
    main: Path,
    rc: RunConfig,
    store: TaskRunStore,
    row: TaskRunRow,
    job: _Job,
    code: CodeRunner | None,
    provider: GitProvider,
) -> TaskRunResult:
    # The row is already claimed/reclaimed. Protect its branch explicitly too:
    # return/resolve/retry can share a previous run's worktree.
    # A restack still needs its parent until approve finishes processing dependents.
    parent = row.stacked_on or stacked_on(store, row.branch)
    upstream = frozenset({parent}) if parent is not None else frozenset()
    warnings = _auto_clean(main, rc, store, provider, protected=upstream | {row.branch})
    result: TaskRunResult | None = None
    try:
        result = _execute_job(main, rc, store, row, job, code, provider)
        return result
    finally:
        warnings.extend(_auto_clean(main, rc, store, provider, protected=upstream))
        if result is not None:
            result.warnings += tuple(warnings)
        elif warnings:
            import logging

            logging.getLogger(__name__).warning("automatic cleanup: %s", "; ".join(warnings))


def _auto_clean(
    main: Path,
    rc: RunConfig,
    store: TaskRunStore,
    provider: GitProvider,
    *,
    protected: frozenset[str] = frozenset(),
) -> list[str]:
    try:
        from aifactory.review.flow import _clean, _Ctx

        return _clean(_Ctx(main, rc, store, provider), protected=protected).warnings
    except Exception as exc:
        return [f"automatic cleanup failed: {exc}"]


def _execute_job(
    main: Path,
    rc: RunConfig,
    store: TaskRunStore,
    row: TaskRunRow,
    job: _Job,
    code: CodeRunner | None,
    provider: GitProvider,
) -> TaskRunResult:
    workflow, prompt, scope, outputs = job.workflow, job.prompt, job.scope, job.outputs
    worktree = Path(row.worktree)
    settings = rc.config.settings
    session_dir = data_dir(main, rc) / "sessions" / row.run_id
    try:
        cfg = prepare_cfg(main, rc, session_dir / "prompt_templates")
        ignored = _main_ignored(main, settings.worktrees_dir, cfg)
        with store.serialized():
            gitops.ensure_excluded(main, _exclude_lines(ignored))
            worktree.parent.mkdir(parents=True, exist_ok=True)
            if job.retry is not None and worktree.is_dir():
                pass  # a retry continues in the run's own worktree
            elif job.new_branch:
                gitops.git(
                    main,
                    *provider_git.PARALLEL_CHECKOUT,
                    "worktree",
                    "add",
                    "-b",
                    row.branch,
                    str(worktree),
                    row.base_sha,
                )
            else:
                if job.retry is not None:
                    gitops.git(main, "worktree", "prune")
                gitops.git(
                    main,
                    *provider_git.PARALLEL_CHECKOUT,
                    "worktree",
                    "add",
                    str(worktree),
                    row.branch,
                )
        copy_library_items(worktree, rc.config.library)
    except (RuntimeError, OSError) as exc:
        store.finish(
            row.run_id, FAILED, None, str(exc)[:2000], failures.OTHER, {"cause": "worktree"}
        )
        raise TaskRunError("worktree_failed", str(exc)) from exc

    resolve = job.resolve
    guard: TaskWriteGuard
    if resolve is not None:
        guard = ConflictWriteGuard(
            main, worktree, row.task_id, ignored, resolve.generated, repair_scope=scope
        )
    else:
        guard = TaskWriteGuard(main, worktree, scope, ignored)
    variables = {
        "task_id": row.task_id,
        "spec_path": outputs.spec,
        "doc_path": outputs.doc,
        "workdir": str(worktree / job.workdir),
    }
    if resolve is not None:
        variables["rebase_onto"] = resolve.onto
        if resolve.upstream:
            variables["rebase_upstream"] = resolve.upstream
    retry = job.retry
    journal: Journal | None = None
    if retry is not None:
        journal = retry.journal
    elif resolve is None:
        journal = Journal(session_dir / JOURNAL_FILE)
    run_kwargs: dict[str, Any] = {
        "cfg": cfg,
        "code": code,
        "adw_id": row.run_id,
        "repo_root": worktree,
        "label": row.task_id,
        "test_timeout": job.test_timeout,
        "test_profile": ProfileCache(
            data_dir(main, rc) / "test_profiles",
            f"{main.resolve()}:{ancestors(job.task)[-1].path}",
        ),
        "test_slots": (
            TestSlots(default_slots_dir(), settings.test_slots) if settings.test_slots else None
        ),
        "phase_gate": PauseGate(store, row.run_id),
    }
    wf: WorkflowRun | None = None
    error: str | None = None
    failure_kind: str | None = None  # decided where the failure arose (aifactory.failure)
    failure_detail: dict[str, Any] = {}
    prev = Path.cwd()
    saved_run_env = os.environ.get(basemoves.RUN_ENV)

    try:
        try:
            os.chdir(worktree)
            os.environ[basemoves.RUN_ENV] = row.run_id
            with _signals_restored(), agent_workdir(job.workdir):
                baseline = retry.baseline if retry is not None else None
                if retry is not None and retry.onto is not None:
                    error = _retry_rebase(main, rc, row, job, retry.onto, ignored, run_kwargs)
                    if error is None:
                        store.set_base_sha(row.run_id, retry.onto)
                        baseline = retry.onto
                if retry is not None and error is None:
                    handoff = session_dir / "context_handoff"
                    handoff.mkdir(parents=True, exist_ok=True)
                    (handoff / f"retry_attempt_{row.attempt - 1}.json").write_text(
                        json.dumps(retry.journal.to_json(), indent=2),
                        encoding="utf-8",
                        newline="\n",
                    )
                    retry.journal.start_replay(retry.limit)
                if error is None:
                    wf = run_workflow(
                        workflow,
                        prompt,
                        write_guard=guard,
                        prompt_variables=variables,
                        generated=resolve.generated if resolve is not None else (),
                        journal=journal,
                        baseline=baseline,
                        request_log=retry.request_log if retry is not None else job.request_log,
                        **run_kwargs,
                    )
        finally:
            os.chdir(prev)
            if saved_run_env is None:
                os.environ.pop(basemoves.RUN_ENV, None)
            else:
                os.environ[basemoves.RUN_ENV] = saved_run_env
    except Exception as exc:
        if resolve is not None or retry is not None:
            command = f"factory task {'resolve' if resolve is not None else 'retry'} {row.task_id}"
            exc = explain_allowed_repair_request(exc, scope, command)
        error = str(exc)[:2000] or type(exc).__name__
        failure_kind, failure_detail = failures.classify(exc)
    except BaseException as exc:
        if resolve is not None:
            with contextlib.suppress(Exception):
                restore(worktree, resolve.before)
        kind, detail = _interrupt_failure(exc)
        store.finish(
            row.run_id,
            FAILED,
            gitops.head(worktree),
            f"interrupted: {exc!r}"[:2000],
            kind,
            detail,
        )
        raise
    if error is None and wf is not None and not (wf.accepted and wf.exit_code == 0):
        failure_kind = failures.ACCEPT_NOT_MET
        error, failure_detail = accept_failure(workflow, wf)
    if resolve is not None:
        before_resolve = error
        error = _finish_resolve(worktree, wf, row.task_id, resolve, error)
        if before_resolve is None and error is not None:
            failure_kind, failure_detail = failures.OTHER, {"cause": "resolve"}
    follow: FollowUpOutcome | None = None
    follow_warnings: list[str] = []
    if wf is not None and followups.reported_any(wf):
        # a resolve run files follow-ups too (e.g. a test its review found missing),
        # but never blocks: its task is built already
        follow, follow_warnings, blockers = _record_follow_ups(
            main, store, row, wf, blocking=resolve is None
        )
        if blockers:
            # a blocked task is neither published nor done: the run fails
            reason = blocked_reason(row.task_id, blockers)
            if error is None:
                failure_kind = failures.BLOCKED
                failure_detail = {"blockers": list(blockers)}
            error = reason if error is None else f"{reason}; {error}"[:2000]
    state = SUCCEEDED if error is None else FAILED
    store.finish(row.run_id, state, gitops.head(worktree), error, failure_kind, failure_detail)
    final = store.get(row.run_id)
    assert final is not None
    result = TaskRunResult(
        run=final,
        workflow_run=wf,
        warnings=tuple(rc.warnings) + tuple(follow_warnings),
        trace_db=store.db_path,
        follow_ups=follow,
    )
    if (
        state == SUCCEEDED
        and resolve is None
        and store.pr_for_branch(final.branch) is None
        and (
            unchanged(final)
            or (
                wf is not None
                and wf.already_done is not None
                and only_spec_changes(final, outputs.spec)
            )
        )
    ):
        evidence = wf.already_done.evidence if wf is not None and wf.already_done else ()
        reason = wf.already_done.reason if wf is not None and wf.already_done else ""
        failure, notes = finish_unchanged(main, store, final, evidence, reason)
        result.warnings += tuple(notes)
        if failure is not None:
            result.pr_error = failure
            store.set_pr_error(final.run_id, failure)
            result.run = store.get(final.run_id) or final
        else:
            result.done_without_pr = True
        return result
    if state == SUCCEEDED:
        # Local import: aifactory.review imports aifactory.run.
        from aifactory.review.publish import publish, run_pr_body

        body = run_pr_body(
            store, final, job.task, wf, follow_ups=follow.created if follow is not None else ()
        )
        try:
            result.pr = publish(
                main,
                rc.config.settings,
                store,
                final,
                job.task,
                wf,
                provider,
                lease=resolve.before if resolve is not None else retry.lease if retry else None,
                body=body,
            )
        except ProviderError as exc:
            result.pr_error = f"{exc.code}: {exc.message}"
            result.pr = store.pr_for_branch(final.branch)
            # kept for `factory task publish` and the dashboard
            store.set_pr_error(final.run_id, result.pr_error, body)
            kept = store.get(final.run_id)
            if kept is not None:
                result.run = kept
    return result


BLOCKED_PREFIX = failures.BLOCKED_PREFIX


def blocked_reason(task_id: str, blockers: list[str]) -> str:
    """The error of a run that ended blocked (``run_blockers`` reads it back)."""
    return failures.blocked_error(task_id, blockers)


def run_blockers(row: TaskRunRow) -> list[str] | None:
    """The blockers a failed run ended blocked on, from its error; None when not blocked.

    Read from the stored error, so it holds for a chain member's run (another process)
    too. The list may hold placeholders of blockers that were not filed.
    """
    if row.state != FAILED:
        return None
    return failures.error_blockers(row.error)


def _record_follow_ups(
    main: Path, store: TaskRunStore, row: TaskRunRow, wf: WorkflowRun, *, blocking: bool = True
) -> tuple[FollowUpOutcome | None, list[str], list[str]]:
    """File the run's follow-ups (``followups.record``): outcome, warnings, blockers.

    A failure to record never hides a blocker an agent reported (``blocking``).
    """
    try:
        from aifactory.backlog import load_for_edit
        from aifactory.run import triage
        from aifactory.run.retry import _note_override

        decisions = None
        triage_warnings: list[str] = []
        backlog = load_for_edit(main)
        reported, _ = followups.collect(wf, backlog.settings)
        if reported:
            try:
                choices = triage.ask_triager(
                    main, reported, backlog, task_id=row.task_id, binding=_note_override(row.note)
                )
                by_id = {choice.follow_up_id: choice for choice in choices}
                if len(choices) != len(reported) or set(by_id) != {
                    f"f{n}" for n in range(1, len(reported) + 1)
                }:
                    raise triage.TriageUnavailable("Incomplete follow-up decisions")
                decisions = {item: by_id[f"f{n}"] for n, item in enumerate(reported, 1)}
            except Exception as exc:
                triage_warnings.append(f"follow-up triage unavailable; using new: {exc}")
        with store.serialized():
            follow = followups.record(
                main,
                row.task_id,
                row.run_id,
                wf,
                blocking=blocking,
                decisions=decisions,
                running=store.running,
            )
            follow.warnings.extend(triage_warnings)
            if follow.committed:
                ids = [
                    c.id
                    for c in follow.created
                    if c.decision == "new" and not c.existed and c.assignee != "human"
                ]
                if ids:
                    try:
                        store.queue_front(ids)
                    except Exception as exc:
                        follow.warnings.append(f"follow-ups not queued: {exc}")
    except Exception as exc:
        has_blockers = blocking and followups.reported_blockers(wf)
        blockers = ["(neuložené hlášení agenta)"] if has_blockers else []
        return None, [f"follow-ups not recorded: {exc}"], blockers
    return follow, list(follow.warnings), list(follow.blocked_by)


def _retry_rebase(
    main: Path,
    rc: RunConfig,
    row: TaskRunRow,
    job: _Job,
    onto: str,
    ignored: tuple[str, ...],
    run_kwargs: dict[str, Any],
) -> str | None:
    """Rebase a retried run's branch onto `onto` (``retry.rebase_for_retry``)."""
    from aifactory.run.retry import rebase_for_retry

    settings = rc.config.settings
    generated = tuple(
        Generated(path=g.path, argv=g.command, timeout=g.timeout) for g in settings.generated
    )
    return rebase_for_retry(
        main,
        Path(row.worktree),
        job.task,
        onto,
        rc.base,
        generated=generated,
        ignored=ignored,
        workflow=named_workflow(RESOLVE_WORKFLOW, rc.config, row.task_id),
        run_kwargs=run_kwargs,
        variables={
            "task_id": row.task_id,
            "spec_path": job.outputs.spec,
            "doc_path": job.outputs.doc,
            "workdir": str(Path(row.worktree) / job.workdir),
        },
        prompt_suffix="\n## Continuation" + job.prompt.partition("\n## Continuation")[2],
    )


def _interrupt_failure(exc: BaseException) -> tuple[str, dict[str, Any]]:
    """The failure kind of a run whose process was interrupted: Ctrl+C or a signal stop it."""
    if isinstance(exc, KeyboardInterrupt):
        return failures.STOPPED, {"cause": "keyboard_interrupt"}
    if isinstance(exc, SystemExit) and isinstance(exc.code, int) and exc.code > 128:
        return failures.STOPPED, {"cause": "signal", "signal": exc.code - 128}
    return failures.OTHER, {"cause": "interrupted", "error_type": type(exc).__name__}


def _finish_resolve(
    worktree: Path, wf: WorkflowRun | None, task_id: str, spec: ResolveSpec, error: str | None
) -> str | None:
    """Commit a resolved run, or put a failed one back on the branch's old tip."""
    if error is None:
        if wf is None:
            error = "workflow resolve did not run"
        else:
            try:
                error = finish_resolve(worktree, wf, task_id, spec)
            except (RuntimeError, OSError) as exc:
                error = str(exc)[:2000] or type(exc).__name__
    if error is not None:
        try:
            restore(worktree, spec.before)
        except (RuntimeError, OSError) as exc:
            error = f"{error}; the branch was not restored: {exc}"[:2000]
    return error


def existing_store(repo: Path) -> TaskRunStore | None:
    """The store of the trace DB of `repo`, or None when there is no trace DB yet."""
    try:
        main = gitops.main_root(repo)
    except TaskRunError:
        main = repo.resolve()
    try:
        local = load_local(main)
    except ConfigError as exc:
        raise TaskRunError("invalid_config", str(exc)) from exc
    db = local.trace_db_path(main)
    if not database.available(db):
        return None
    return TaskRunStore(db)


def session_dir_of(repo: Path, run_id: str) -> Path:
    """The session directory of run `run_id`: ``<data_dir>/sessions/<run_id>``.

    Resolved from the run config of the main checkout (agents.yaml ``data_dir``, else
    ``.factory/data``), the same way `_execute` lays it out — never next to the trace DB.
    """
    try:
        main = gitops.main_root(repo)
    except TaskRunError:
        main = repo.resolve()
    return data_dir(main, _load(main)) / "sessions" / run_id


def task_runs_for(repo: Path, task_id: str) -> list[TaskRunRow]:
    """Every run of `task_id`, newest first. Creates nothing when there is no trace DB yet.

    Outside a git repository (a bare backlog directory) `repo` itself is the root.
    """
    store = existing_store(repo)
    if store is None:
        return []
    try:
        return store.for_task(task_id)
    finally:
        store.close()


def task_prs_for(repo: Path, task_id: str) -> list[TaskPrRow]:
    """Every pull request of `task_id`, newest first; `[]` when there is no trace DB yet."""
    store = existing_store(repo)
    if store is None:
        return []
    try:
        return store.prs_for_task(task_id)
    finally:
        store.close()
