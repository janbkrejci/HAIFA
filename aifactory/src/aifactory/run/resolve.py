"""``factory task resolve``: the run that brings a conflicting PR up to date with base.

Step 6 of "Běh úkolu" in ``docs/product-brief.md`` (risk R2). The run uses the
workflow ``resolve`` on the PR's branch: the ``rebase`` code step
(``aifactory.workflow.rebase``) rebases onto the current ``base``; only when that
leaves conflicts does the ``resolve`` role run, and it may change nothing but
the conflicted files (``ConflictWriteGuard``). Then the suite runs, with up to
two repair rounds (``fix``) on the conflicted files when there was a conflict.

Generated outputs (``generated:`` in ``.factory/config.yaml``, e.g. the
frontend bundle) are not the agent's: a conflict inside one means both sides
changed its sources, and only a new build gives the right result. The guard
keeps such files out of the agents' scope; the code step ``rebuild``
(``aifactory.workflow.rebuild``) runs the output's build command after the
agent settled the other conflicts, and ``finish_resolve`` commits the whole
rebuilt output with the resolved files.

Code, not the workflow, finishes the run (``finish_resolve``): no conflict
marker may be left, the resolved files are staged and committed. When anything
fails, ``restore`` puts the branch back exactly where it was before the rebase.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aifactory.backlog import Task
from aifactory.backlog.derived import ancestors
from aifactory.run import gitops
from aifactory.run.guard import TaskWriteGuard
from aifactory.run.scope import TaskScope
from aifactory.workflow import (
    Generated,
    WorkflowRun,
    conflict_markers,
    covered,
    unmerged_files,
)
from aifactory.workflow.rebuild import to_rebuild

RESOLVE_WORKFLOW = "resolve"
RESOLVE_REVIEWED_WORKFLOW = "resolve-reviewed"
"""``resolve`` plus a review of a resolution the agent wrote; auto-merge resolves with it."""
# internal workflows: always packaged in a repo with a manifest (D32)
INTERNAL_WORKFLOWS = frozenset({RESOLVE_WORKFLOW, RESOLVE_REVIEWED_WORKFLOW})
TEST_TIER_ENV = "HAIFA_TEST_TIER"
"""Set to ``full`` while a resolve runs: the test command then runs the whole suite."""


@dataclass(frozen=True)
class ResolveSpec:
    """Where the resolve run rebases to (``onto``) and where the branch was (``before``)."""

    onto: str
    before: str
    base: str
    generated: tuple[Generated, ...] = ()


def resolve_prompt(
    task: Task, worktree: Path, base: str, onto: str, generated: tuple[str, ...] = ()
) -> str:
    """Task header, the resolve instructions, then the task text for context."""
    lines = [f"# Task {task.id}: {task.title}", "", f"- id: {task.id}", f"- title: {task.title}"]
    for container in reversed(ancestors(task)):
        label = " — ".join(x for x in (container.id, container.title) if x)
        if label:
            lines.append(f"- {container.level}: {label}")
    lines += [
        f"- working directory: {worktree} (all repository paths are relative to it)",
        "",
        "## Resolve",
        f"Branch was rebased onto `{base}` (`{onto[:7]}`). "
        "The previous step's report lists the files with conflicts.",
        "Resolve every conflict in exactly those files: keep what this task intended and "
        "what is now in base; remove all conflict markers.",
        "Change no other file. Do not run git add, commit, push, rebase, merge, reset, "
        "checkout, switch or branch; code stages, commits and pushes the result.",
    ]
    if generated:
        outputs = ", ".join(f"`{path}`" for path in generated)
        lines.append(
            f"Generated outputs ({outputs}) are not yours: leave their files as they are, "
            "even when conflicted, and do not build them; code rebuilds them after you."
        )
    text = "\n".join(lines) + "\n"
    body = task.body.strip()
    if body:
        text += f"\n## Task\n{body}\n"
    return text


class ConflictWriteGuard(TaskWriteGuard):
    """``TaskWriteGuard`` whose scope is exactly the files the rebase left conflicted.

    The scope is fixed at the first snapshot that sees unmerged files, so a
    retry after the agent staged a file does not narrow it. Without a conflict
    the scope stays empty and an agent may change nothing. Conflicted files
    inside a generated output (``generated``) are left out: only the code step
    ``rebuild`` writes them, and the guard does not watch code steps.
    """

    def __init__(
        self,
        main_root: Path,
        worktree: Path,
        task_id: str,
        main_ignored: tuple[str, ...] = (),
        generated: tuple[Generated, ...] = (),
    ) -> None:
        super().__init__(main_root, worktree, TaskScope(task_id, (), ()), main_ignored)
        self.generated = generated
        self.fixed = False

    def snapshot(self, run: Any) -> dict[str, Any]:
        if not self.fixed:
            files = unmerged_files(self.worktree)
            if files:
                mine = tuple(f for f in files if not covered(f, self.generated))
                self.scope = TaskScope(self.scope.task_id, mine, ())
                self.fixed = True
        return super().snapshot(run)


def finish_resolve(worktree: Path, wf: WorkflowRun, task_id: str, spec: ResolveSpec) -> str | None:
    """Check and commit the resolved files; return why the run fails, or None."""
    result = wf.results.get("rebase")
    if result is None:
        return "workflow resolve has no rebase step"
    if not result.get("conflict"):
        return None
    files = [str(f) for f in result.get("files") or []]
    targets = [g.path for g in to_rebuild(spec.generated, files)]
    rebuilt = wf.results.get("rebuild") or {}
    missing = [path for path in targets if path not in (rebuilt.get("built") or [])]
    if missing:
        return f"generated outputs in conflict were not rebuilt: {', '.join(missing)}"
    left = conflict_markers(worktree, files)
    if left:
        return f"conflict markers left in: {', '.join(left)}"
    gitops.git(worktree, "add", "-A", "--", *files, *targets)
    unresolved = sorted(
        {line.split("\t", 1)[-1] for line in gitops.git(worktree, "ls-files", "-u").splitlines()}
    )
    if unresolved:
        return f"unresolved paths: {', '.join(unresolved)}"
    message = (
        f"{task_id}: rebase onto {spec.base} {spec.onto[:7]}, "
        f"resolve conflicts in {', '.join(files)}"
    )
    if targets:
        message += f"; rebuild {', '.join(targets)}"
    gitops.git(worktree, "commit", "-q", "-m", message)
    return None


def restore(worktree: Path, before: str) -> None:
    """Put the worktree's branch back on `before` with a clean tree; raise if it is not."""
    for args in (("rebase", "--abort"), ("merge", "--abort")):
        subprocess.run(
            ["git", *args], cwd=worktree, capture_output=True, text=True, encoding="utf-8"
        )
    gitops.git(worktree, "reset", "--hard", "-q", before)
    gitops.git(worktree, "clean", "-fdq")
    now = gitops.head(worktree)
    if now != before:
        raise RuntimeError(f"branch not restored: HEAD is {now} instead of {before}")
