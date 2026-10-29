"""``factory task resolve``: the run that brings a conflicting PR up to date with base.

The run uses the workflow ``resolve`` on the PR's branch: the ``rebase`` code step
(``aifactory.workflow.rebase``) rebases onto the current ``base``; only when that
leaves conflicts does the ``resolve`` role run, and it may change nothing but
the conflicted files (``ConflictWriteGuard``). Then the suite runs, with up to
two repair rounds (``fix``) across the task writes, including files without conflicts.

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

from aifactory import failure
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
CI_FIX_WORKFLOW = "ci-fix"
"""Repairs a PR whose CI checks went red, on the PR's branch (``review.ci``)."""
# internal workflows: packaged, available also when neither the repo nor the library has them
INTERNAL_WORKFLOWS = frozenset({RESOLVE_WORKFLOW, RESOLVE_REVIEWED_WORKFLOW, CI_FIX_WORKFLOW})


@dataclass(frozen=True)
class ResolveSpec:
    """Where the resolve run rebases to (``onto``) and where the branch was (``before``)."""

    onto: str
    before: str
    base: str
    repair_scope: TaskScope
    generated: tuple[Generated, ...] = ()
    # the PR's fork point when base does not contain it (a stacked PR whose dependency
    # was squashed into base): only the commits after it are rebased
    upstream: str | None = None


def resolve_prompt(
    task: Task,
    worktree: Path,
    base: str,
    onto: str,
    generated: tuple[str, ...] = (),
    repair_paths: tuple[str, ...] = (),
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
        "In the resolve phase, resolve every conflict in exactly those files: "
        "keep what this task intended and "
        "what is now in base; remove all conflict markers.",
        "In the resolve phase, change no other file. "
        "In later repair phases (fix_N, test_fix_N), repair failing checks within the task "
        f"allowed paths: {list(repair_paths)}. Files without text conflicts are allowed there. "
        "For a path already covered by these paths, make the repair directly; "
        "do not request needs_writes. "
        "Do not run git add, commit, push, rebase, merge, reset, "
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


def explain_allowed_repair_request(exc: Exception, scope: TaskScope, command: str) -> Exception:
    """Give an actionable failure when an agent requests already granted paths."""
    kind, detail = failure.classify(exc)
    paths = detail.get("paths", [])
    if kind != failure.WRITES_NEEDED or not paths or not all(scope.permits(p) for p in paths):
        return exc
    return failure.InvalidOutput(
        f"Requested paths are already allowed by the task writes: {', '.join(paths)}. "
        "Do not extend writes or use --allow-writes. "
        "Keep the resolve phase limited to text conflicts; make these repairs in fix_N. "
        "If the builder has its own writes restriction in agents.yaml, adjust it to cover "
        f"these paths, then run `{command}`.",
        detail={"cause": "already_allowed_repair", "paths": paths},
    )


class ConflictWriteGuard(TaskWriteGuard):
    """Restrict resolution to conflicts, but allow repairs across the task scope.

    Conflict paths are captured before resolution removes the unmerged entries.
    Generated outputs remain code-owned in every agent phase.
    """

    def __init__(
        self,
        main_root: Path,
        worktree: Path,
        task_id: str,
        main_ignored: tuple[str, ...] = (),
        generated: tuple[Generated, ...] = (),
        *,
        repair_scope: TaskScope,
    ) -> None:
        super().__init__(main_root, worktree, TaskScope(task_id, (), ()), main_ignored)
        self.generated = generated
        self.repair_scope = repair_scope
        self.fixed = False

    def fix_scope(self) -> None:
        if not self.fixed:
            files = unmerged_files(self.worktree)
            if files:
                mine = tuple(f for f in files if not covered(f, self.generated))
                self.scope = TaskScope(self.scope.task_id, mine, ())
                self.fixed = True

    def allows_writes(self) -> bool:
        """Whether a repair can write a non-generated task path."""
        return any(not covered(p, self.generated) for p in self.repair_scope.paths)

    def _permitted(self, path: str, agent: Any, cfg: Any) -> bool:
        return not covered(path, self.generated) and super()._permitted(path, agent, cfg)

    def phase_scope(self, phase_name: str) -> TaskScope:
        self.fix_scope()
        if phase_name in ("fix", "test_fix") or phase_name.startswith(("fix_", "test_fix_")):
            return self.repair_scope
        return self.scope

    def agent_paths(self, agent: Any, phase_name: str) -> tuple[str, ...]:
        paths = super().agent_paths(agent, phase_name)
        return tuple(p for p in paths if not covered(p, self.generated))

    def enforce(self, run: Any, phase: Any, agent: Any, before: dict[str, Any]) -> list[str]:
        conflict_scope = self.scope
        name = phase.params.name
        if name in ("fix", "test_fix") or name.startswith(("fix_", "test_fix_")):
            self.scope = self.repair_scope
        try:
            return super().enforce(run, phase, agent, before)
        finally:
            self.scope = conflict_scope

    def snapshot(self, run: Any) -> dict[str, Any]:
        self.fix_scope()
        return super().snapshot(run)


def finish_resolve(worktree: Path, wf: WorkflowRun, task_id: str, spec: ResolveSpec) -> str | None:
    """Check and commit the resolved files; return why the run fails, or None."""
    result = wf.results.get("rebase")
    if result is None:
        return "workflow resolve has no rebase step"
    files = [str(f) for f in result.get("files") or []]
    targets = [g.path for g in to_rebuild(spec.generated, files)]
    rebuilt = wf.results.get("rebuild") or {}
    missing = [path for path in targets if path not in (rebuilt.get("built") or [])]
    if missing:
        return f"generated outputs in conflict were not rebuilt: {', '.join(missing)}"
    left = conflict_markers(worktree, files)
    if left:
        return f"conflict markers left in: {', '.join(left)}"
    # Code/test steps are not watched by the agent guard. Select concrete paths
    # rather than staging the whole tree (a check may have created a report).
    changed = set(gitops.git(worktree, "diff", "--no-renames", "--name-only", "-z").split("\0"))
    changed.update(
        gitops.git(worktree, "diff", "--cached", "--no-renames", "--name-only", "-z").split("\0")
    )
    changed.update(
        gitops.git(worktree, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    )
    # A squash rebase stages nonconflicting changes from the original branch too.
    # Preserve its generated paths without admitting arbitrary check outputs in
    # the same generated directory. Disable rename detection to retain deletions.
    branch_paths = gitops.git(
        worktree, "diff", "--no-renames", "--name-only", "-z", f"{spec.onto}...{spec.before}"
    ).split("\0")
    carried_generated = {path for path in branch_paths if covered(path, spec.generated)}
    rebuilt_outputs = tuple(g for g in spec.generated if g.path in targets)
    selected = sorted(
        set(files)
        | {
            path
            for path in changed
            if path
            and (
                path in carried_generated
                or covered(path, rebuilt_outputs)
                or (spec.repair_scope.permits(path) and not covered(path, spec.generated))
            )
        }
    )
    if not selected:
        return None
    # A deletion already staged by the squash has no index entry or worktree
    # file left; git add would reject its pathspec. It is still selected below.
    indexed = set(gitops.git(worktree, "ls-files", "-z").split("\0"))
    to_stage = [
        path
        for path in selected
        if path in indexed or (worktree / path).exists() or (worktree / path).is_symlink()
    ]
    if to_stage:
        gitops.git(worktree, "add", "-A", "--", *to_stage)
    unresolved = sorted(
        {line.split("\t", 1)[-1] for line in gitops.git(worktree, "ls-files", "-u").splitlines()}
    )
    if unresolved:
        return f"unresolved paths: {', '.join(unresolved)}"
    # Staging can cancel a rebase's index-only addition deleted by a rebuild.
    # Such a path is no longer known to git and cannot be passed to commit --only.
    commit_paths = sorted(
        set(
            gitops.git(worktree, "diff", "--cached", "--no-renames", "--name-only", "-z").split(
                "\0"
            )
        )
        & set(selected)
    )
    if not commit_paths:
        return None
    message = (
        f"{task_id}: rebase onto {spec.base} {spec.onto[:7]}, "
        f"resolve conflicts in {', '.join(files)}"
        if files
        else f"{task_id}: repair after rebase onto {spec.base} {spec.onto[:7]}"
    )
    if targets:
        message += f"; rebuild {', '.join(targets)}"
    # A check may also have staged unrelated files; commit only the selected paths.
    gitops.git(worktree, "commit", "--only", "-q", "-m", message, "--", *commit_paths)
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
