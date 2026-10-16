"""Stacked pull requests (``stacked_prs: true`` in ``.factory/config.yaml``).

A task whose unmet dependencies all wait in open pull requests does not wait for their
merge: its run forks from the tip of the dependency's PR branch (``stack_point``) and
``task_runs.stacked_on`` names that branch. Its PR targets base like any other, so it
holds the dependency's commits until they are merged.

The stacked PR is merged only after its dependencies (approve refuses a task whose
``depends_on`` are not done). Once a dependency's PR is merged, ``review/stack.py``
rebases the stacked PR onto base without the dependency's commits
(``git rebase --onto <base> <fork point>``, the resolve workflow on a conflict) and
auto-merges it when the task has ``auto_merge``. A stacked PR whose dependency is still
open is never rebased onto base: that would drop the work it builds on.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aifactory.backlog import Backlog, Task, unmet
from aifactory.providers import OPEN
from aifactory.providers import git as provider_git
from aifactory.run.store import TaskPrRow, TaskRunStore

# a dependency in one of these states cannot be stacked on
_STACKABLE_REASONS = ("not_done", "incomplete")


@dataclass(frozen=True)
class StackPoint:
    """Where a stacked run forks: the dependency PR's branch and its tip."""

    branch: str
    sha: str
    dependencies: tuple[str, ...]

    def note(self, prs: dict[str, TaskPrRow]) -> str:
        urls = ", ".join(f"{dep} ({prs[dep].url})" for dep in self.dependencies if dep in prs)
        return (
            f"Větev navazuje na neschválené pull requesty závislostí: {urls}. "
            "Jejich změny už v ní jsou, neměň je; měň jen to, co patří tomuto tasku."
        )


def unmet_ids(backlog: Backlog, task: Task) -> list[str] | None:
    """The tasks `task` waits for, or None when one cannot be stacked on (unknown, ...)."""
    ids: list[str] = []
    for item in unmet(backlog, task):
        if item.reason not in _STACKABLE_REASONS:
            return None
        for dep in item.missing or [item.id]:
            if dep not in ids:
                ids.append(dep)
    return ids


def stack_tip(main: Path, prs: dict[str, TaskPrRow]) -> tuple[str, str] | None:
    """The PR branch (and tip) that contains every other one of `prs`; None when none does."""
    tips: list[tuple[str, str]] = []
    for pr in prs.values():
        sha = provider_git.rev_parse(main, f"refs/heads/{pr.branch}")
        if sha is None:
            return None
        tips.append((pr.branch, sha))
    for branch, sha in tips:
        if all(provider_git.is_ancestor(main, other, sha) for _, other in tips):
            return branch, sha
    return None


def stack_point(
    main: Path, backlog: Backlog, task: Task, store: TaskRunStore
) -> tuple[StackPoint, dict[str, TaskPrRow]] | None:
    """Where a run of `task` forks when every unmet dependency waits in an open PR."""
    ids = unmet_ids(backlog, task)
    if not ids:
        return None
    prs: dict[str, TaskPrRow] = {}
    for dep in ids:
        pr = store.open_pr(dep)
        if pr is None:
            return None
        prs[dep] = pr
    tip = stack_tip(main, prs)
    if tip is None:
        return None
    return StackPoint(tip[0], tip[1], tuple(ids)), prs


def open_stack(store: TaskRunStore, branch: str) -> TaskPrRow | None:
    """The still open PR the runs on `branch` are stacked on; None when not stacked."""
    for row in store.runs_on_branch(branch):
        if row.stacked_on:
            pr = store.pr_for_branch(row.stacked_on)
            if pr is not None and pr.state == OPEN:
                return pr
    return None


def stacked_on(store: TaskRunStore, branch: str) -> str | None:
    """The dependency branch the first run on `branch` forked from; None: base."""
    rows = store.runs_on_branch(branch)
    return rows[-1].stacked_on if rows else None
