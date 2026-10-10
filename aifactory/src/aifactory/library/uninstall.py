"""Remove factory from a repo: delete ``.factory/`` and its ``.gitignore`` lines in one commit.

The dashboard's "remove repository": the repo's own items (agents, workflows, skills,
extensions that are not the library's) can go to the library first (``config export``),
then every committed file under ``.factory/`` is deleted and the runtime lines factory
added to ``.gitignore`` are taken out, in one commit on base (pushed when there is a
remote). Nothing else in the repo changes: the backlog, specs and docs stay.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aifactory.config.run import worktree_base
from aifactory.library.install import GITIGNORE_LINES, _repo_root
from aifactory.library.install_commit import FACTORY_DIR, _store, _tree_files
from aifactory.library.store import LibraryStoreError
from aifactory.providers import git
from aifactory.providers.base import ProviderError
from aifactory.providers.publish import (
    DIRECT,
    Action,
    Blocker,
    PlannedFile,
    PublishPlan,
    direct_blockers,
    plan_digest,
)

OWN_STATES = frozenset({"local", "modified", "diverged", "unknown"})
"""Item states whose repo copy is not (or no longer) what the library holds."""


@dataclass
class UninstallPlan:
    root: Path
    publish: PublishPlan
    own_items: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "repo": str(self.root),
            **self.publish.to_json(),
            "blockers": [b.to_json() for b in self.publish.blockers],
            "own_items": self.own_items,
        }


@dataclass
class UninstallResult:
    plan: UninstallPlan
    committed: bool
    commit: str | None = None
    pushed: bool = False
    exported: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            **self.plan.to_json(),
            "committed": self.committed,
            "commit": self.commit,
            "pushed": self.pushed,
            "exported": self.exported,
        }


def own_items(root: Path, environ: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """The repo's own items in base: those the library does not hold as they are."""
    from aifactory.library.state import repo_items

    try:
        items = repo_items(root, "", environ, save_cache=False)["items"]
    except (LibraryStoreError, ProviderError, OSError, ValueError):
        return []
    return [
        {"type": i["type"], "name": i["name"], "state": i["state"]}
        for i in items
        if i.get("state") in OWN_STATES
    ]


def _without_lines(text: str) -> str:
    drop = set(GITIGNORE_LINES)
    lines = [line for line in text.splitlines() if line.strip() not in drop]
    return "\n".join(lines) + "\n" if lines else ""


def plan_uninstall(path: Path, environ: Mapping[str, str] | None = None) -> UninstallPlan:
    """What removing factory commits; writes nothing."""
    root = _repo_root(path)
    base = worktree_base(root)
    base_sha = git.rev_parse(root, f"refs/heads/{base}")
    if base_sha is None:
        raise LibraryStoreError("unknown_base", f"base {base!r} does not exist in {root}")
    files: list[PlannedFile] = []
    for rel in _tree_files(root, base_sha, FACTORY_DIR):
        old = git.blob_at(root, base_sha, rel)
        if old is not None:
            files.append(
                PlannedFile(rel, "delete", old[0], old[1], None, None, git.read_blob(root, old[1]))
            )
    ignore = git.blob_at(root, base_sha, ".gitignore")
    if ignore is not None:
        before = git.read_blob(root, ignore[1])
        after = _without_lines(before.decode("utf-8", "replace")).encode("utf-8")
        if after != before:
            action: Action = "delete" if not after else "modify"
            files.append(
                PlannedFile(
                    ".gitignore",
                    action,
                    ignore[0],
                    ignore[1],
                    None if not after else "100644",
                    None if not after else after,
                    before,
                )
            )
    dirty = [
        line[3:]
        for line in git.git(
            root, "status", "--porcelain", "--untracked-files=no", "--", FACTORY_DIR, ".gitignore"
        ).splitlines()
        if line.strip()
    ]
    from aifactory.config import load_run_config

    try:
        remote = load_run_config(root).config.settings.remote
    except Exception:  # an invalid config still uninstalls; the default remote then
        remote = "origin"
    store = _store(root)
    try:
        blockers, _notes = direct_blockers(
            root, remote=remote, base=base, base_sha=base_sha, store=store, check_remote=bool(files)
        )
    except ProviderError as exc:
        raise LibraryStoreError(exc.code, exc.message) from exc
    finally:
        if store is not None:
            store.close()
    if dirty:
        blockers.insert(
            0,
            Blocker(
                "dirty_paths",
                "uncommitted changes would be lost: "
                + ", ".join(dirty)
                + "; commit or discard them first",
            ),
        )
    publish = PublishPlan(
        base=base,
        base_sha=base_sha,
        target=DIRECT,
        files=tuple(files),
        blockers=tuple(blockers),
        digest=plan_digest(base, base_sha, files),
    )
    return UninstallPlan(root, publish, own_items(root, environ))


def uninstall(
    path: Path,
    *,
    export: Sequence[tuple[str, str]] = (),
    environ: Mapping[str, str] | None = None,
) -> UninstallResult:
    """Export `export` (type, name) to the library, then commit the removal of ``.factory/``."""
    from aifactory.library.config_edit import execute_plan, plan_config
    from aifactory.providers import publish

    root = _repo_root(path)
    first = plan_uninstall(root, environ)
    if first.publish.blockers:
        b = first.publish.blockers[0]
        raise LibraryStoreError(b.code, b.message, data=first.to_json())
    exported: list[dict[str, str]] = []
    for kind, name in export:
        change = plan_config("export", root, type=kind, name=name, commit=True, environ=environ)
        execute_plan(change, environ=environ)
        exported.append({"type": kind, "name": name})
    plan = plan_uninstall(root, environ) if exported else first
    if not plan.publish.files:
        return UninstallResult(plan, False, exported=exported)
    from aifactory.config import ProjectSettings, load_run_config

    try:
        settings = load_run_config(root).config.settings
    except Exception:  # an invalid config still uninstalls, with the default remote
        settings = ProjectSettings()
    store = _store(root)
    try:
        result = publish.publish_direct(
            root,
            settings=settings,
            plan=plan.publish,
            message="factory: remove factory from this repository",
            store=store,
            materialize=True,
            command="uninstall",
        )
    except ProviderError as exc:
        raise LibraryStoreError(exc.code, exc.message, data=plan.to_json()) from exc
    except RuntimeError as exc:
        raise LibraryStoreError("commit_failed", str(exc), data=plan.to_json()) from exc
    finally:
        if store is not None:
            store.close()
    warnings = list(result.warnings)
    warnings += _remove_folder(root)
    return UninstallResult(
        plan,
        True,
        commit=result.commit,
        pushed=result.pushed,
        exported=exported,
        warnings=warnings,
    )


def _remove_folder(root: Path) -> list[str]:
    """Delete what is left of ``.factory/`` on disk: run worktrees, trace DB, local files."""
    import shutil

    folder = root / FACTORY_DIR
    for line in git.git(root, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            tree = Path(line.removeprefix("worktree "))
            if folder.resolve() in tree.resolve().parents:
                git.git_ok(root, "worktree", "remove", "--force", str(tree))
    try:
        shutil.rmtree(folder)
    except FileNotFoundError:
        pass
    except OSError as exc:
        return [f"{FACTORY_DIR}/ not fully removed: {exc}"]
    git.git_ok(root, "worktree", "prune")
    return []
