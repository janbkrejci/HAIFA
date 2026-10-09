"""Run one backlog task in its own git worktree and branch (``factory task run``).

What is read from where:

* everything under ``.factory/`` (agents, prompts, roles, workflows,
  ``config.yaml``) and the backlog come from the commit ``base`` points to, not
  from the working tree: a run starts from what is committed;
* ``.factory/local.yaml`` and the trace DB are read from the disk of the main
  checkout;
* the session runtime (``.factory/data`` unless agents.yaml sets ``data_dir``)
  stays in the main checkout, shared by all runs; the agents work only in the
  run's worktree ``<worktrees_dir>/<run-id>``.

Every run is a row in ``task_runs`` in the trace DB (``store.py``). A run that
meets ``accept`` is pushed and gets a pull request, a row in ``task_prs``
(``aifactory.review``: publish, approve, return, resolve, clean). A resolve
run (``resolve.py``) rebases a conflicting PR branch onto base. After every
agent call ``TaskWriteGuard`` (``guard.py``) checks both the worktree and the
main checkout and rolls back what the task scope (``scope.py``) does not allow.

Auto-continue (``queue.py``, ``factory task run --auto`` or ``auto_continue``
in ``index.md``): after a run opens its PR, ``run_chain`` starts the next
ready task of the step, then of the project; a task waiting on an unmerged PR
is skipped. With ``auto_merge`` the finished task's PR is merged first
(``review.automerge``) and the chain continues only after that merge. Runs of
different tasks may go in parallel: ``claim`` refuses a second run of the same
task, ``serialized`` holds a lock file (not the DB write lock) around
``git worktree add``, and the store switches the trace DB to WAL before the
engine's Tracer opens it. With ``max_parallel_runs`` above 1 the chain keeps that
many runs going at once as separate processes (``members.ProcessRunner``), and
starts a task only when its ``writes`` overlap no running run's ``writes`` and no
open PR's files (``writes_overlap``); a task with wide ``writes`` runs alone
(``exclusive``). The chain's state is a row of ``task_chains``.

Stop (``stop.py``, ``factory task stop`` and the dashboard): ``stop_run`` marks
a running run ``stopped``, sends SIGTERM to its coding agents, then to the run's
process, and SIGKILL to what outlives the timeout.

Pause (``pause.py``, ``factory task pause|resume`` and the dashboard): ``pause_run``
asks a running run to wait before its next phase (``pausing``, then ``paused``);
``resume_run`` lets it go on. A paused run stays ``running`` in ``task_runs``.
"""

from aifactory.run.errors import TaskRunError
from aifactory.run.guard import TaskWriteGuard
from aifactory.run.members import ChainRunner, ProcessRunner
from aifactory.run.pause import PauseGate, pause_run, resume_run
from aifactory.run.queue import (
    SKIP_REASONS,
    STOP_DISABLED,
    STOP_EXHAUSTED,
    STOP_FAILED,
    STOP_NOT_MERGED,
    ChainResult,
    Occupancy,
    Skip,
    auto_continue_enabled,
    auto_merge_enabled,
    run_chain,
    select_next,
)
from aifactory.run.scope import OutputPaths, TaskScope, output_paths, task_scope
from aifactory.run.stop import StopResult, running_run, stop_run
from aifactory.run.store import (
    STOPPED,
    SyncPrRow,
    TaskChainRow,
    TaskPrRow,
    TaskRunRow,
    TaskRunStore,
)
from aifactory.run.task import (
    TaskRunResult,
    run_task,
    task_prompt,
    task_prs_for,
    task_runs_for,
)

__all__ = [
    "SKIP_REASONS",
    "STOP_DISABLED",
    "STOP_EXHAUSTED",
    "STOPPED",
    "STOP_FAILED",
    "STOP_NOT_MERGED",
    "ChainResult",
    "ChainRunner",
    "Occupancy",
    "PauseGate",
    "OutputPaths",
    "ProcessRunner",
    "Skip",
    "StopResult",
    "SyncPrRow",
    "TaskChainRow",
    "TaskPrRow",
    "TaskRunError",
    "TaskRunResult",
    "TaskRunRow",
    "TaskRunStore",
    "TaskScope",
    "TaskWriteGuard",
    "auto_continue_enabled",
    "auto_merge_enabled",
    "output_paths",
    "pause_run",
    "resume_run",
    "run_chain",
    "run_task",
    "running_run",
    "select_next",
    "stop_run",
    "task_prompt",
    "task_prs_for",
    "task_runs_for",
    "task_scope",
]
