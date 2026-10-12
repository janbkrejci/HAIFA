"""Remove factory from a repo: delete ``.factory/`` and its ``.gitignore`` lines in one commit.

The dashboard's "remove repository": every committed file under ``.factory/`` is deleted
and the runtime lines factory added to ``.gitignore`` are taken out, in one commit on base
(pushed when there is a remote). Nothing else in the repo changes: the backlog, specs and
docs stay. An item worth keeping goes to the library first ("Move to library",
``factory config move``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aifactory.config import ProjectSettings
from aifactory.config.run import worktree_base
from aifactory.library.install import GITIGNORE_LINES, _repo_root
from aifactory.library.install_commit import FACTORY_DIR, _store, _tree_files
from aifactory.library.store import LibraryStoreError
from aifactory.providers import git
from aifactory.providers.base import ProviderError
from aifactory.providers.publish import (
    DIRECT,
    PR,
    Action,
    Blocker,
    PlannedFile,
    PublishPlan,
    direct_blockers,
    plan_digest,
    uses_pr,
)

UNINSTALL_BRANCH_PREFIX = "factory-uninstall/"


def _settings(root: Path) -> ProjectSettings:
    """The repository's settings; the defaults when its configuration is invalid."""
    from aifactory.config import load_run_config

    try:
        return load_run_config(root).config.settings
    except Exception:  # an invalid config still uninstalls, with the default remote
        return ProjectSettings()


@dataclass
class UninstallPlan:
    root: Path
    publish: PublishPlan

    def to_json(self) -> dict[str, Any]:
        return {
            "repo": str(self.root),
            **self.publish.to_json(),
            "blockers": [b.to_json() for b in self.publish.blockers],
        }


@dataclass
class UninstallResult:
    plan: UninstallPlan
    committed: bool
    commit: str | None = None
    pushed: bool = False
    warnings: list[str] = field(default_factory=list)
    pr: dict[str, str] | None = None
    merged: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            **self.plan.to_json(),
            "committed": self.committed,
            "commit": self.commit,
            "pushed": self.pushed,
            "pr": self.pr,
            "merged": self.merged,
        }


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
    settings = _settings(root)
    pr = uses_pr(settings)
    blockers: list[Blocker] = []
    if not pr:
        store = _store(root)
        try:
            blockers, _notes = direct_blockers(
                root,
                remote=settings.remote,
                base=base,
                base_sha=base_sha,
                store=store,
                check_remote=bool(files),
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
        target=PR if pr else DIRECT,
        files=tuple(files),
        blockers=tuple(blockers),
        digest=plan_digest(base, base_sha, files),
    )
    return UninstallPlan(root, publish)


def uninstall(path: Path, *, environ: Mapping[str, str] | None = None) -> UninstallResult:
    """Commit the removal of ``.factory/`` (or open its pull request)."""
    from aifactory.providers import get_provider, publish

    root = _repo_root(path)
    plan = plan_uninstall(root, environ)
    if plan.publish.blockers:
        b = plan.publish.blockers[0]
        raise LibraryStoreError(b.code, b.message, data=plan.to_json())
    if not plan.publish.files:
        return UninstallResult(plan, False)
    settings = _settings(root)
    message = "factory: remove factory from this repository"
    store = _store(root)
    try:
        if plan.publish.target == PR:
            provider = get_provider(settings, root)
            result = publish.publish_pr(
                root,
                provider=provider,
                settings=settings,
                plan=plan.publish,
                message=message,
                body="Remove factory: " + ", ".join(f.path for f in plan.publish.files) + "\n",
                prefix=UNINSTALL_BRANCH_PREFIX,
            )
            result = publish.finish_pr(
                root,
                provider=provider,
                settings=settings,
                plan=plan.publish,
                result=result,
                message=message,
                store=store,
                materialize=True,
                command="uninstall",
            )
        else:
            result = publish.publish_direct(
                root,
                settings=settings,
                plan=plan.publish,
                message=message,
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
    if result.advanced:  # an open pull request leaves factory in base and on disk
        warnings += _remove_folder(root)
    pr = result.pr
    return UninstallResult(
        plan,
        True,
        commit=result.commit,
        pushed=result.pushed,
        warnings=warnings,
        pr={"id": pr.id, "url": pr.url, "branch": pr.branch} if pr is not None else None,
        merged=result.merged,
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
