"""Commit the shared ``.factory/`` configuration to base (``factory config commit``, D4).

The paths come from ``config_changes`` (``config.yaml``, ``agents.yaml``, ``roles.yaml``,
``manifest.yaml``, ``prompts/``, ``workflows/``, ``extensions/`` and the repo skills in
``.claude/skills/`` and ``.agents/skills/``; never ``local.yaml``). The plan lists every file (path,
action, diff against base, content), the blockers and a ``digest``; ``--expect DIGEST``
refuses a plan that changed since it was reviewed (``plan_changed``). Committing goes
through ``providers.publish``: a commit on base without a checkout, pushed before the
local base moves (direct target) or opened as a PR from ``factory-config/<n>``.
``factory config pull`` fast-forwards the local base to the remote one.

Error codes (``ConfigCommitError.code``, exit 2): ``invalid_config``, ``unknown_base``,
``not_on_base``, ``run_in_progress``, ``base_behind``, ``base_diverged``,
``plan_changed``, ``fetch_failed``, ``commit_failed``, ``base_moved``, ``push_failed``,
``no_remote``, ``dirty_base`` and the provider's codes for ``--pr``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aifactory.config.errors import ConfigError, ConfigIssue
from aifactory.config.loader import load_config
from aifactory.config.run import worktree_base
from aifactory.config.settings import CONFIG_FILE, ProjectSettings, load_local
from aifactory.config.settings import parse_project_settings as _parse_settings
from aifactory.config.source import CommitSource, WorktreeSource
from aifactory.config.status import config_changes

if TYPE_CHECKING:
    from aifactory.providers.base import PullRequest
    from aifactory.providers.publish import PublishPlan, PullResult
    from aifactory.run.store import TaskRunStore

CONFIG_BRANCH_PREFIX = "factory-config/"


class ConfigCommitError(Exception):
    """``factory config commit``/``pull`` refused or failed; ``code`` says why."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        data: dict[str, Any] | None = None,
        issues: list[dict[str, Any]] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.data = data
        self.issues = list(issues or [])
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class ConfigCommitResult:
    plan: PublishPlan
    dry_run: bool
    committed: bool
    commit: str | None = None
    pushed: bool = False
    advanced: bool = False
    branch: str | None = None
    pr: PullRequest | None = None
    warnings: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        pr = None
        if self.pr is not None:
            pr = {"id": self.pr.id, "url": self.pr.url, "branch": self.pr.branch}
        return {
            **self.plan.to_json(),
            "paths": [f.path for f in self.plan.files],
            "dry_run": self.dry_run,
            "committed": self.committed,
            "commit": self.commit,
            "pushed": self.pushed,
            "advanced": self.advanced,
            "branch": self.branch,
            "pr": pr,
        }


@dataclass
class _Context:
    main: Path
    settings: ProjectSettings
    issues: list[dict[str, Any]]


def _issue_dicts(issues: list[ConfigIssue]) -> list[dict[str, Any]]:
    return [
        {"code": "invalid_config", "message": i.message, "path": i.path, "id": None} for i in issues
    ]


def _main(repo: Path) -> Path:
    from aifactory.run import gitops
    from aifactory.run.errors import TaskRunError

    try:
        return gitops.main_root(repo)
    except TaskRunError as exc:
        raise ConfigCommitError("invalid_config", exc.message) from exc


def _context(repo: Path) -> _Context:
    """The main checkout and its settings, from the working tree's configuration.

    Base may hold a broken configuration that the working tree fixes, so the working
    tree is what counts; when it does not load, the settings fall back to its
    config.yaml alone, then to base, then to the defaults.
    """
    main = _main(repo)
    try:
        return _Context(main, load_config(WorktreeSource(main)).settings, [])
    except ConfigError as exc:
        issues = _issue_dicts(exc.issues)
    try:
        text = WorktreeSource(main).read_text(CONFIG_FILE)
    except OSError:
        text = None
    settings = _parse_settings(text, CONFIG_FILE, [])
    if settings is None:
        from aifactory.providers import git as pgit

        base = worktree_base(main)
        sha = pgit.rev_parse(main, f"refs/heads/{base}")
        try:
            settings = load_config(CommitSource(main, base, sha)).settings if sha else None
        except ConfigError:
            settings = None
    return _Context(main, settings or ProjectSettings(base=worktree_base(main)), issues)


def _store(main: Path) -> TaskRunStore:
    from aifactory.run.errors import TaskRunError
    from aifactory.run.store import TaskRunStore

    try:
        return TaskRunStore(load_local(main).trace_db_path(main))
    except ConfigError as exc:
        raise ConfigCommitError(
            "invalid_config", str(exc), issues=_issue_dicts(exc.issues)
        ) from exc
    except TaskRunError as exc:
        raise ConfigCommitError(exc.code, exc.message) from exc


def plan_config_commit(repo: Path, *, pr: bool = False) -> tuple[PublishPlan, _Context, list[str]]:
    """The plan of ``factory config commit``: files, blockers and digest (nothing written)."""
    from aifactory.providers import ProviderError, publish
    from aifactory.providers import git as pgit

    ctx = _context(repo)
    main, settings = ctx.main, ctx.settings
    base = settings.base
    base_sha = pgit.rev_parse(main, f"refs/heads/{base}")
    if base_sha is None:
        raise ConfigCommitError("unknown_base", f"base {base!r} does not exist in {main}")
    try:
        changes = config_changes(main, base_sha)
    except ConfigError as exc:
        raise ConfigCommitError("invalid_config", str(exc)) from exc
    files = publish.plan_files(main, base_sha, [c.path for c in changes])

    blockers: list[publish.Blocker] = []
    warnings: list[str] = []
    if ctx.issues:
        blockers.append(
            publish.Blocker(
                "invalid_config",
                f"the working-tree configuration has {len(ctx.issues)} problem(s)",
            )
        )
    if not pr:
        store = _store(main)
        try:
            found, notes = publish.direct_blockers(
                main,
                remote=settings.remote,
                base=base,
                base_sha=base_sha,
                store=store,
                check_remote=bool(files),
            )
        except ProviderError as exc:
            raise ConfigCommitError(exc.code, exc.message) from exc
        finally:
            store.close()
        blockers += found
        warnings += notes
    plan = publish.PublishPlan(
        base=base,
        base_sha=base_sha,
        target=publish.PR if pr else publish.DIRECT,
        files=tuple(files),
        blockers=tuple(blockers),
        digest=publish.plan_digest(base, base_sha, files),
    )
    return plan, ctx, warnings


def _body(plan: PublishPlan) -> str:
    lines = [f"- {f.action} `{f.path}`" for f in plan.files]
    return (
        "Shared factory configuration from the main checkout:\n\n"
        + "\n".join(lines)
        + f"\n\nPlan digest: `{plan.digest}`\n"
    )


def commit_config(
    repo: Path,
    *,
    pr: bool = False,
    dry_run: bool = False,
    expect: str | None = None,
    message: str | None = None,
) -> ConfigCommitResult:
    """Commit the uncommitted shared configuration to base in one commit (or a PR)."""
    from aifactory.providers import ProviderError, get_provider, publish

    plan, ctx, warnings = plan_config_commit(repo, pr=pr)
    if dry_run:
        return ConfigCommitResult(plan, True, False, warnings=tuple(warnings))
    if expect is not None and expect.strip() != plan.digest:
        raise ConfigCommitError(
            "plan_changed",
            "the plan changed since it was reviewed (--expect); run --dry-run again",
            data=plan.to_json(),
        )
    if not plan.files:
        return ConfigCommitResult(plan, False, False, warnings=tuple(warnings))
    if plan.blockers:
        first = plan.blockers[0]
        issues = ctx.issues if first.code == "invalid_config" else []
        raise ConfigCommitError(first.code, first.message, data=plan.to_json(), issues=issues)
    subject = (message or "").strip() or f"config: {len(plan.files)} file(s) from factory"
    try:
        if pr:
            result = publish.publish_pr(
                ctx.main,
                provider=get_provider(ctx.settings, ctx.main),
                settings=ctx.settings,
                plan=plan,
                message=subject,
                body=_body(plan),
                prefix=CONFIG_BRANCH_PREFIX,
            )
        else:
            store = _store(ctx.main)
            try:
                result = publish.publish_direct(
                    ctx.main, settings=ctx.settings, plan=plan, message=subject, store=store
                )
            finally:
                store.close()
    except ProviderError as exc:
        raise ConfigCommitError(exc.code, exc.message, data=plan.to_json()) from exc
    except RuntimeError as exc:
        raise ConfigCommitError("commit_failed", str(exc), data=plan.to_json()) from exc
    return ConfigCommitResult(
        plan,
        False,
        True,
        commit=result.commit,
        pushed=result.pushed,
        advanced=result.advanced,
        branch=result.branch,
        pr=result.pr,
        warnings=(*warnings, *result.warnings),
    )


def pull_config(repo: Path, *, expect: str | None = None) -> PullResult:
    """Fast-forward the local base to the remote base (``factory config pull``)."""
    from aifactory.providers import ProviderError, publish

    ctx = _context(repo)
    store = _store(ctx.main)
    try:
        return publish.pull_base(ctx.main, settings=ctx.settings, store=store, expect=expect)
    except ProviderError as exc:
        raise ConfigCommitError(exc.code, exc.message) from exc
    except RuntimeError as exc:
        raise ConfigCommitError("pull_failed", str(exc)) from exc
    finally:
        store.close()


def plan_pull_config(repo: Path) -> dict[str, Any]:
    """Preview the remote base without advancing the local ref."""
    from aifactory.providers import publish

    ctx = _context(repo)
    store = _store(ctx.main)
    try:
        return publish.plan_pull_base(ctx.main, settings=ctx.settings, store=store)
    finally:
        store.close()
