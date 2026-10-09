"""Check both checkouts after every agent call of a task run; undo what was not allowed.

The engine calls ``snapshot(run)`` before an agent phase and ``enforce(run,
phase, agent, before)`` after it, also when the phase fails (harness error,
invalid JSON, a gate that stays red). ``TaskWriteGuard`` looks at two trees:

* **the worktree of the run.** A changed path must be allowed by the agent's
  own `writes` and protected files *and* by the task scope (``scope.py``). A
  commit the agent made itself is undone with ``git reset --soft`` to the
  commit before the phase, so the committed files are checked like any other
  change; the move is reported as ``HEAD``. The two outputs of the task (spec
  and documentation) are writable for an agent whose own `writes` is a
  non-empty list even when its `writes` do not cover them (``docs/decisions.md``,
  "Výstupy po projektech"); an agent with ``writes: []`` may not write them.
  Files already uncommitted before the phase (earlier phases' work) are saved
  too; an agent that may not touch one and reverts or edits it gets it restored.
* **the main checkout.** An agent of a task run has no business there at all.
  Before every call the guard saves the uncommitted state of the main checkout
  (``backup.py``: tracked changes, staged or not, the index and untracked files
  that are not gitignored) under ``<session>/guard_backup/NNN/``. After the call
  any difference is restored exactly, whether the agent changed a clean path or
  reverted, edited or deleted the operator's own uncommitted work; whatever the
  restore overwrites is kept under ``replaced/`` of that backup. Only the
  worktrees directory, the session runtime and the trace DB (``main_ignored``)
  are skipped. A moved ``HEAD`` or switched branch is reported but not undone;
  then only the previously uncommitted files are put back.

  Another factory command may fast-forward the base checked out there during
  the phase (``task approve`` of a concurrent run, ``backlog commit``,
  ``config commit``, ``config pull``). Such commands write the base-move
  journal (``basemoves.py``) with the ``HAIFA_RUN_ID`` of their process. When
  the branch is the same and the journal chains the ``HEAD`` before the phase to
  the ``HEAD`` now through moves of other processes only, the move is not a
  breach: the backup is switched to the new ``HEAD`` (and the index recorded
  with the move) and files are checked and restored against it. A commit,
  reset, checkout or branch switch of the agent, or a factory command the agent
  started itself (it carries the run's own id), stays a breach.

  The operator may also change the backlog through the factory during the phase
  (``task add``, ``task edit``, ``task link``, ``backlog auto-continue``,
  ``backlog auto-merge``; CLI or
  dashboard). Those commands write the journal of factory writes
  (``mainwrites.py``) with the content they wrote. A write of another process is
  neither undone nor reported: the backup takes its content as the expected
  state of the path. A write that carries the run's own id is the agent's and
  stays a breach. When both the factory and the agent write the same file, the
  factory's content stays and the agent's write is undone and reported, no
  matter which came first.

Uncommitted work present before the phase is never discarded: if it cannot be
saved, the agent is not started. Any breach raises
``permissions.PermissionBreach`` naming every path, where it was and what
happened to it, and the backup of that phase is kept; without a breach it is
removed.

Known limit: files ignored by ``.gitignore`` are invisible to git, so a write to
such a path in either checkout is neither detected nor undone.
"""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from aifactory.engine import permissions
from aifactory.run import backup, basemoves, gitops, mainwrites
from aifactory.run.scope import TaskScope

WORKTREE = "worktree"
MAIN = "main checkout"

_ignored = backup.ignored


def roll_back(root: Path, path: str, after: dict[str, str]) -> str:
    """Undo one change the agent introduced on a path that was clean before the phase.

    Like ``permissions._roll_back``, but a staged file (``git add``, or a commit
    undone with ``reset --soft``) is restored from ``HEAD`` in index and tree.
    """
    target = root / path
    if after.get(path) == "untracked":
        try:
            target.unlink()
            return "deleted"
        except OSError as error:
            return f"could not delete ({error})"
    if gitops.git_ok(root, "cat-file", "-e", f"HEAD:{path}"):
        ok = gitops.git_ok(root, "checkout", "HEAD", "--", path)
        return "rolled back" if ok else "could not roll back"
    subprocess.run(
        ["git", "rm", "--cached", "-q", "--", path],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    try:
        target.unlink(missing_ok=True)
    except OSError as error:
        return f"could not delete ({error})"
    return "deleted"


class TaskWriteGuard:
    """The engine's write guard for one task run (see the module docstring)."""

    def __init__(
        self,
        main_root: Path,
        worktree: Path,
        scope: TaskScope,
        main_ignored: tuple[str, ...] = (),
    ) -> None:
        self.main_root = main_root
        self.worktree = worktree
        self.scope = scope
        self.main_ignored = main_ignored
        self._seq = 0

    def _permitted(self, path: str, agent: Any, cfg: Any) -> bool:
        if any(permissions._matches(path, p) for p in permissions.always_writable(cfg)):
            return True
        if not self.scope.permits(path):
            return False
        if permissions.permitted(path, agent, cfg):
            return True
        # docs/decisions.md, "Výstupy po projektech": the two outputs of the task are
        # writable for an agent that may write at all, even outside its own `writes`.
        return (
            self.scope.is_output(path)
            and bool(getattr(agent, "writes", None))
            and not any(permissions._matches(path, p) for p in cfg.defaults.protected_files)
        )

    def _backup_dir(self, run: Any) -> Path:
        self._seq += 1
        session = getattr(run, "session_dir", None)
        if session:
            base = Path(session) / "guard_backup"
            path = base / f"{self._seq:03d}"
            while path.exists():
                self._seq += 1
                path = base / f"{self._seq:03d}"
            path.mkdir(parents=True)
            return path
        return Path(tempfile.mkdtemp(prefix="haifa-guard-"))

    def snapshot(self, run: Any) -> dict[str, Any]:
        name = getattr(getattr(run, "current_agent", None), "name", None) or "the agent"
        base_moves = basemoves.offset(self.main_root)
        main_writes = mainwrites.offset(self.main_root)
        try:
            where = self._backup_dir(run)
            main_backup = backup.capture(self.main_root, where / "main", self.main_ignored)
            worktree_backup = backup.capture(self.worktree, where / "worktree")
        except OSError as error:
            raise permissions.PermissionBreach(
                f"cannot back up the main checkout before {name}: {error}"
            ) from error
        return {
            "backup_dir": where,
            "worktree": permissions.snapshot(run),
            "worktree_backup": worktree_backup,
            "worktree_head": gitops.head(self.worktree),
            "worktree_ref": gitops.symbolic_head(self.worktree),
            "main_backup": main_backup,
            "base_moves": base_moves,
            "main_writes": main_writes,
            "main_head": main_backup.head,
            "main_ref": main_backup.ref,
        }

    def enforce(self, run: Any, phase: Any, agent: Any, before: dict[str, Any]) -> list[str]:
        """Undo and raise ``PermissionBreach`` on any breach; else the worktree paths changed."""
        problems: list[str] = []

        head_before = before["worktree_head"]
        head_now = gitops.head(self.worktree)
        ref_now = gitops.symbolic_head(self.worktree)
        if head_now != head_before:
            if ref_now == before["worktree_ref"] and head_before:
                reset = gitops.git_ok(self.worktree, "reset", "--soft", "-q", head_before)
                outcome = (
                    f"agent committed, reset to {head_before[:7]}"
                    if reset
                    else f"could not roll back: HEAD moved to {(head_now or '?')[:7]}"
                )
            else:
                where = ref_now or (head_now or "?")[:7]
                outcome = f"could not roll back: HEAD moved to {where}"
            problems.append(f"{WORKTREE}: HEAD — {outcome}")

        permissions.require_enforceable(run.repo_root)
        after = permissions.snapshot(run)
        wt_backup: backup.CheckoutBackup = before["worktree_backup"]
        pre_dirty_off = [p for p in backup.verify(wt_backup, index=False) if p in wt_backup.files]
        changed = set(permissions.changed_paths(before["worktree"], after))
        touched = sorted(changed | set(pre_dirty_off))
        for path in touched:
            if self._permitted(path, agent, run.cfg):
                continue
            if path in wt_backup.files:
                outcome = backup.restore(wt_backup, (), [path], index=False)[path]
            else:
                outcome = roll_back(self.worktree, path, after)
            problems.append(f"{WORKTREE}: {path} — {outcome}")

        main_backup: backup.CheckoutBackup = before["main_backup"]
        # The state before the phase; supersede changes the backup's dicts in place.
        original = dataclasses.replace(
            main_backup, files=dict(main_backup.files), links=dict(main_backup.links)
        )
        main_head = gitops.head(self.main_root)
        main_ref = gitops.symbolic_head(self.main_root)
        factory_move = False
        if (
            main_ref
            and main_ref == before["main_ref"]
            and main_head
            and before["main_head"]
            and main_head != before["main_head"]
        ):
            move = basemoves.wait_for_chain(
                self.main_root,
                before.get("base_moves", 0),
                main_ref,
                before["main_head"],
                main_head,
                getattr(run, "adw_id", None),
            )
            if move is not None:
                main_backup = dataclasses.replace(
                    main_backup, head=main_head, index_tree=move.index_tree
                )
                factory_move = True
        own_run = getattr(run, "adw_id", None)
        writes_start = before.get("main_writes", 0)

        def accept(writes: list[mainwrites.MainWrite]) -> mainwrites.Accepted:
            found = mainwrites.accept(
                self.main_root, writes, lambda p: backup.expected(original, p), own_run
            )
            for path, (data, mode) in found.states.items():
                if not _ignored(path, self.main_ignored):
                    backup.supersede(main_backup, path, data, mode)
            return found

        accepted = accept(mainwrites.writes_since(self.main_root, writes_start))
        off = backup.verify(main_backup, self.main_ignored)
        # A factory command journals its write right after it; wait briefly for it.
        unexplained = [p for p in off if p.endswith(".md") and p not in accepted.states]
        if unexplained:
            accepted = accept(mainwrites.wait_for_writes(self.main_root, writes_start, unexplained))
            off = backup.verify(main_backup, self.main_ignored)
        if off:
            outcomes = backup.restore(main_backup, self.main_ignored, off)
            for path in off:
                outcome = outcomes.get(path, "unchanged")
                if path in accepted.states and outcome.startswith("restored"):
                    outcome = "restored to the factory write"
                problems.append(f"{MAIN}: {path} — {outcome}")
        for path in accepted.agent_first:
            if path not in off:
                problems.append(
                    f"{MAIN}: {path} — changed by the agent before a factory write; "
                    "factory content kept"
                )
        if not factory_move and (
            main_head != before["main_head"] or main_ref != before["main_ref"]
        ):
            where = main_ref or (main_head or "?")[:7]
            problems.append(f"{MAIN}: HEAD — moved to {where}, not rolled back")
        if off:
            saved = main_backup.dir.parent
            problems.append(f"{MAIN}: backup of the state before the phase at {saved}")

        if not problems:
            shutil.rmtree(before["backup_dir"], ignore_errors=True)
            return touched
        detail = "\n".join(f"  - {p}" for p in problems)
        raise permissions.PermissionBreach(
            f"{agent.name} changed paths outside its task run:\n{detail}\n"
            f"task {self.scope.task_id} may only change {list(self.scope.paths)} "
            "inside its worktree"
        )
