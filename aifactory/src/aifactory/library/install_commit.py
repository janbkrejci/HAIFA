"""``factory init --dry-run`` and ``factory init --commit``: install factory by one commit.

``plan_init`` renders the same files as the working-tree ``init`` (``config.yaml``; the
backlog ``.gitkeep`` only when the backlog directory does not exist; the ``.gitignore``
lines) and turns them into a ``PublishPlan`` against base. Nothing is written anywhere:
not to the repo, not to the library, not to ``$HAIFA_HOME``. The plan carries what was
detected (remote, base, provider, harness CLIs; ``library.detect``), blockers, warnings
and a ``digest``. Agents and workflows come from the library at run time
(``aifactory.library.inherit``).

The digest is ``publish.plan_digest`` over the planned files plus, when the runtime lines
go to ``info/exclude``, a pseudo file ``:info/exclude`` with those lines.

``commit_init`` makes the plan one commit on base through ``providers.publish``: pushed
before the local base moves, and the files reach the checkout of base only after that
(``materialize``); ``info/exclude`` is written after a successful publish. With ``pr`` the
commit goes to ``factory-init/<n>`` with a pull request; base and the checkout stay.

Blockers (``data.blockers``; the commit refuses with the first, exit 2):
``already_installed`` (``config.yaml`` in base), ``existing_config`` (an sssf installation;
HAIFA does not take it over), ``config_not_committed`` (``config.yaml`` only in the working
tree; ``factory config commit``), ``dirty_paths`` (a planned path on disk with other
content), ``invalid_plan`` (the planned configuration does not load) and, for the direct
target, ``not_on_base``, ``run_in_progress``, ``base_behind``, ``base_diverged``.

Raised: ``invalid_value``, ``unknown_base``, ``plan_changed``, ``fetch_failed``,
``commit_failed``, ``base_moved``, ``push_failed`` and the provider's codes for ``pr``.
Warnings (``data.warnings[].code``): ``harness_missing``, ``gitignore_dirty``,
``foreign_content``, ``remote_note``.
"""

from __future__ import annotations

import dataclasses
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from aifactory import yamlload
from aifactory.config.errors import ConfigError
from aifactory.config.settings import CONFIG_FILE, ProjectSettings, load_local
from aifactory.engine.role_registry import Issue
from aifactory.library.detect import Detected, detect
from aifactory.library.install import (
    GITIGNORE_LINES,
    SSSF_CONFIG_DIR,
    _committed,
    _git_out,
    _repo_root,
    project_settings,
    render_config,
)
from aifactory.library.store import LibraryStoreError
from aifactory.providers import git
from aifactory.providers.base import ProviderError, PullRequest
from aifactory.providers.publish import (
    DIRECT,
    PR,
    Blocker,
    PlannedFile,
    PublishPlan,
    direct_blockers,
    holds,
    plan_contents,
    plan_digest,
    uses_pr,
)

if TYPE_CHECKING:
    from aifactory.config.source import ConfigSource
    from aifactory.library.inherit import LibrarySnapshot
    from aifactory.run.store import TaskRunStore

INIT_BRANCH_PREFIX = "factory-init/"
EXCLUDE_PSEUDO_PATH = ":info/exclude"


@dataclass(frozen=True)
class InitWarning:
    code: str
    message: str

    def to_json(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass
class InitPlan:
    root: Path
    publish: PublishPlan
    settings: ProjectSettings
    detected: Detected
    exclude: dict[str, Any] | None
    warnings: list[InitWarning]
    issues: list[Issue]

    @property
    def blockers(self) -> tuple[Blocker, ...]:
        return self.publish.blockers

    def to_json(self) -> dict[str, Any]:
        settings = self.settings
        return {
            "repo": str(self.root),
            **self.publish.to_json(),
            "paths": [f.path for f in self.publish.files],
            "provider": settings.git_provider,
            "remote": settings.remote,
            "azure": settings.azure.model_dump(mode="json") if settings.azure else None,
            "docs_root": settings.docs_root,
            "exclude": self.exclude,
            "warnings": [w.to_json() for w in self.warnings],
            "validation": {
                "ok": not self.issues,
                "issues": [i.to_dict() for i in self.issues],
            },
            "detected": self.detected.to_json(),
        }


@dataclass(frozen=True)
class InitCommitResult:
    plan: InitPlan
    dry_run: bool
    committed: bool = False
    commit: str | None = None
    pushed: bool = False
    advanced: bool = False
    branch: str | None = None
    pr: PullRequest | None = None
    extra_warnings: tuple[str, ...] = ()
    merged: bool = False

    @property
    def warnings(self) -> list[str]:
        return [w.message for w in self.plan.warnings] + list(self.extra_warnings)

    def to_json(self) -> dict[str, Any]:
        pr = None
        if self.pr is not None:
            pr = {"id": self.pr.id, "url": self.pr.url, "branch": self.pr.branch}
        return {
            **self.plan.to_json(),
            "dry_run": self.dry_run,
            "committed": self.committed,
            "commit": self.commit,
            "pushed": self.pushed,
            "advanced": self.advanced,
            "branch": self.branch,
            "pr": pr,
            "merged": self.merged,
        }


# ── repository reads ──────────────────────────────────────────────────────────


def _in_tree(root: Path, sha: str, rel: str) -> bool:
    return _committed(root, sha, rel.rstrip("/"))


def _tree_files(root: Path, sha: str, rel_dir: str) -> list[str]:
    out = _git_out(root, "ls-tree", "-r", "--name-only", "-z", sha, "--", rel_dir.rstrip("/") + "/")
    return [p for p in (out or "").split("\0") if p]


def _disk_files(root: Path, rel_dir: str) -> list[str]:
    base = root / rel_dir
    if not base.is_dir():
        return []
    return [
        p.relative_to(root).as_posix()
        for p in base.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(root).parts
    ]


def _store(root: Path) -> TaskRunStore | None:
    """The trace DB when it exists; opening it otherwise would create it in the repo."""
    try:
        path = load_local(root).trace_db_path(root)
    except ConfigError:
        return None
    if not path.exists():
        return None
    from aifactory.run.errors import TaskRunError
    from aifactory.run.store import TaskRunStore

    try:
        return TaskRunStore(path)
    except TaskRunError as exc:
        raise LibraryStoreError(exc.code, exc.message) from exc


def _exclude_file(root: Path) -> Path | None:
    from aifactory.run import gitops

    common = gitops.common_dir(root)
    return None if common is None else common / "info" / "exclude"


# ── planned contents ──────────────────────────────────────────────────────────


def _append_lines(text: str, lines: Sequence[str]) -> str:
    if text and not text.endswith("\n"):
        text += "\n"
    return text + "".join(f"{line}\n" for line in lines)


def _gitignore(
    root: Path, base_sha: str, contents: dict[str, bytes], warnings: list[InitWarning]
) -> dict[str, Any] | None:
    """Add the runtime lines to ``.gitignore`` in the plan, or to ``info/exclude``.

    Returns the ``exclude`` part of the plan (None when nothing goes there).
    """
    old = git.blob_at(root, base_sha, ".gitignore")
    base_bytes = git.read_blob(root, old[1]) if old else None
    disk = root / ".gitignore"
    disk_bytes = disk.read_bytes() if disk.is_file() else None
    base_text = (base_bytes or b"").decode("utf-8", "replace")
    present = {line.strip() for line in base_text.splitlines()}
    missing = [line for line in GITIGNORE_LINES if line not in present]
    if not missing:
        return None
    if disk_bytes == base_bytes and not (disk.exists() and not disk.is_file()):
        contents[".gitignore"] = _append_lines(base_text, missing).encode("utf-8")
        return None
    local = {line.strip() for line in (disk_bytes or b"").decode("utf-8", "replace").splitlines()}
    path = _exclude_file(root)
    if path is not None and path.is_file():
        local |= {line.strip() for line in path.read_text(encoding="utf-8").splitlines()}
    lines = [line for line in missing if line not in local]
    warnings.append(
        InitWarning(
            "gitignore_dirty",
            ".gitignore has uncommitted changes; it stays as it is and the runtime lines "
            "of factory go to info/exclude of this clone",
        )
    )
    if not lines or path is None:
        return None
    return {"path": str(path), "lines": lines}


def _foreign(root: Path, base_sha: str, settings: ProjectSettings) -> list[InitWarning]:
    out: list[InitWarning] = []
    seen: set[str] = set()
    for what, rel in (
        ("backlog", settings.backlog_dir),
        ("specs", settings.specs_dir),
        ("docs", settings.docs_dir),
    ):
        rel = rel.strip("/")
        if rel in ("", ".") or rel in seen:
            continue
        seen.add(rel)
        files = {*_tree_files(root, base_sha, rel), *_disk_files(root, rel)}
        files = {f for f in files if Path(f).name != ".gitkeep"}
        if files:
            out.append(
                InitWarning(
                    "foreign_content",
                    f"{rel}/ ({what}) already has {len(files)} file(s); "
                    "factory will use them as they are",
                )
            )
    return out


def _harness_warnings(harnesses: Mapping[str, str], detected: Detected) -> list[InitWarning]:
    """``harness_missing`` for every agent whose harness CLI is not on PATH."""
    from aifactory.harness.check import binary_name

    out: list[InitWarning] = []
    for agent, name in harnesses.items():
        if detected.harnesses.get(name, "") is None:
            out.append(
                InitWarning(
                    "harness_missing",
                    f"agent {agent} uses harness {name}, whose CLI "
                    f"{binary_name(name)} is not on PATH",
                )
            )
    return out


# ── blockers and validation ───────────────────────────────────────────────────


FACTORY_DIR = ".factory"


def _committed_base_changes(
    root: Path, base_sha: str, settings: ProjectSettings
) -> ProjectSettings:
    """`settings` with ``base_changes`` and ``base_pr_merge`` of the ``config.yaml`` in base.

    The dashboard's "add" of an installed repository keeps that file, so its choice of how
    factory changes base applies.
    """
    from aifactory.config.settings import parse_project_settings

    blob = git.blob_at(root, base_sha, CONFIG_FILE)
    if blob is None:
        return settings
    text = git.read_blob(root, blob[1]).decode("utf-8", "replace")
    committed = parse_project_settings(text, CONFIG_FILE, [])
    if committed is None:
        return settings
    return settings.model_copy(
        update={
            "base_changes": committed.base_changes,
            "base_pr_merge": committed.base_pr_merge,
        }
    )


def _state_blocker(root: Path, base_sha: str) -> Blocker | None:
    if _committed(root, base_sha, CONFIG_FILE) or _committed(root, "HEAD", CONFIG_FILE):
        return Blocker("already_installed", f"{CONFIG_FILE} is committed; factory is installed")
    if _committed(root, base_sha, SSSF_CONFIG_DIR) or (root / SSSF_CONFIG_DIR).is_dir():
        return Blocker(
            "existing_config",
            f"the repo has an sssf installation ({SSSF_CONFIG_DIR}/); "
            "HAIFA does not take over sssf",
        )
    if (root / CONFIG_FILE).exists():
        return Blocker(
            "config_not_committed",
            f"{CONFIG_FILE} is in the working tree but not in base; run factory config commit",
            fix="factory config commit",
        )
    return None


def _dirty(root: Path, files: Sequence[PlannedFile]) -> list[str]:
    out: list[str] = []
    for f in files:
        disk = root / f.path
        if not disk.exists() and not disk.is_symlink():
            continue
        if holds(root, f.path, f.content) or holds(root, f.path, f.old_content):
            continue
        out.append(f.path)
    return out


def _load(root: Path, base: str, base_sha: str, contents: Mapping[str, bytes]) -> Any:
    """The configuration of base with the plan on top, or the issues why it does not load."""
    from aifactory.config.loader import load_config
    from aifactory.config.source import CommitSource, OverlaySource

    overlay = {p: c for p, c in contents.items() if p.startswith(".factory/")}
    try:
        return load_config(OverlaySource(CommitSource(root, base, base_sha), overlay))
    except ConfigError as exc:
        return [Issue("invalid_config", i.message, i.path) for i in exc.issues]


def validate_source(
    source: ConfigSource,
    workflows: Mapping[str, bytes],
    missing: frozenset[str] = frozenset(),
    library: LibrarySnapshot | None = None,
) -> list[Issue]:
    """The configuration in `source` loads and every workflow of `workflows` preflights.

    A step whose harness CLI is in `missing` cannot have its model checked on this machine
    (pi lists its models only through its CLI); the ``harness_missing`` warning covers it,
    so its ``invalid_agent`` issues are left out.
    """
    from aifactory.config.loader import load_config, write_prompts
    from aifactory.harness import canonical
    from aifactory.workflow.interpreter import preflight
    from aifactory.workflow.model import RoleStep, WorkflowError, walk
    from aifactory.workflow.parse import parse_workflow

    try:
        cfg = load_config(source, library)
    except ConfigError as exc:
        return [Issue("invalid_config", i.message, i.path) for i in exc.issues]
    harness_of = {a.name: str(a.coding_agent) for a in cfg.agents.agents}
    issues: list[Issue] = []
    with tempfile.TemporaryDirectory(prefix="factory-plan-") as tmp:
        roster = write_prompts(cfg, Path(tmp))
        for name, data in workflows.items():
            try:
                workflow = parse_workflow(yamlload.safe_load(data.decode("utf-8")), cfg.roles)
            except WorkflowError as exc:
                issues += [dataclasses.replace(i, path=f"{name}: {i.path}") for i in exc.issues]
                continue
            except (UnicodeDecodeError, yaml.YAMLError) as exc:
                issues.append(Issue("invalid_yaml", str(exc), name))
                continue
            unchecked: set[str] = set()
            for step in walk(workflow.steps):
                if not isinstance(step, RoleStep):
                    continue
                used = step.harness or harness_of.get(step.role.agent)
                try:
                    if used is not None and canonical(used) in missing:
                        unchecked.add(step.path)
                except ValueError:
                    continue
            try:
                preflight(workflow, roster)
            except WorkflowError as exc:
                issues += [
                    dataclasses.replace(i, path=f"{name}: {i.path}")
                    for i in exc.issues
                    if not (i.code == "invalid_agent" and i.path in unchecked)
                ]
    return issues


# ── plan ──────────────────────────────────────────────────────────────────────


def _azure(
    provider: str, given: Mapping[str, str | None] | None, detected: Detected
) -> dict[str, str] | None:
    if provider != "azure":
        return None
    found = detected.info.azure or {}
    keys = ("organization", "project", "repository")
    merged = {k: (given or {}).get(k) or found.get(k) for k in keys}
    if not all(merged.values()):
        raise LibraryStoreError(
            "invalid_value",
            "--provider azure needs --azure-org, --azure-project and --azure-repo "
            "(or an Azure DevOps remote URL)",
        )
    return {k: str(v) for k, v in merged.items()}


def plan_init(
    path: Path,
    *,
    base: str | None = None,
    provider: str | None = None,
    azure: Mapping[str, str | None] | None = None,
    docs_root: str | None = None,
    pr: bool = False,
    environ: Mapping[str, str] | None = None,
    replace: bool = False,
    base_changes: str | None = None,
    base_pr_merge: str | None = None,
) -> InitPlan:
    """The install plan; see the module docstring. Writes nothing.

    ``replace`` (the dashboard's "add") keeps a committed ``config.yaml`` as it is and plans
    only what is missing (the ``.gitignore`` lines) instead of refusing it.
    """
    root = _repo_root(path)
    detected = detect(root)
    if base is not None and not base.strip():
        raise LibraryStoreError("invalid_value", "--base must not be empty")
    base = base.strip() if base is not None else detected.base
    if base is None:
        raise LibraryStoreError(
            "invalid_value", "HEAD is detached and the remote has no HEAD; pass --base"
        )
    base_sha = git.rev_parse(root, f"refs/heads/{base}")
    if base_sha is None:
        raise LibraryStoreError("unknown_base", f"base {base!r} does not exist in {root}")
    chosen = provider or detected.provider
    settings = project_settings(
        base=base,
        provider=chosen,
        azure=_azure(chosen, azure, detected),
        remote=detected.remote,
        docs_root=docs_root,
        base_changes=base_changes,
        base_pr_merge=base_pr_merge,
    )
    warnings: list[InitWarning] = []
    contents: dict[str, bytes] = {}
    keep = replace and _committed(root, base_sha, CONFIG_FILE)
    if keep:
        settings = _committed_base_changes(root, base_sha, settings)
    pr = uses_pr(settings, pr)
    if not keep:
        write_remote = detected.remote not in (None, "origin")
        contents[CONFIG_FILE] = render_config(settings, write_remote=write_remote)
        backlog = settings.backlog_dir.strip("/")
        if not _in_tree(root, base_sha, backlog) and not (root / backlog).exists():
            contents[f"{backlog}/.gitkeep"] = b""
    exclude = _gitignore(root, base_sha, contents, warnings)
    files = plan_contents(root, base_sha, contents)

    blockers: list[Blocker] = []
    issues: list[Issue] = []
    state = None if replace else _state_blocker(root, base_sha)
    if state is not None:
        blockers.append(state)
    else:
        dirty = _dirty(root, files)
        if dirty:
            blockers.append(
                Blocker(
                    "dirty_paths",
                    "planned paths exist in the working tree with other content: "
                    + ", ".join(dirty)
                    + "; move them away or commit them first",
                )
            )
        loaded = _load(root, base, base_sha, contents)
        if isinstance(loaded, list):
            issues = loaded
            blockers.append(
                Blocker(
                    "invalid_plan",
                    f"the planned configuration has {len(issues)} problem(s); see the issues",
                )
            )
        else:
            from aifactory.harness import canonical

            harnesses = {a.name: canonical(str(a.coding_agent)) for a in loaded.agents.agents}
            warnings += _harness_warnings(harnesses, detected)
    if not pr:
        store = _store(root)
        try:
            found, notes = direct_blockers(
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
        blockers += found
        warnings += [InitWarning("remote_note", note) for note in notes]
    if not keep:
        warnings += _foreign(root, base_sha, settings)

    digest_files = list(files)
    if exclude is not None:
        content = "\n".join(exclude["lines"]).encode("utf-8")
        digest_files.append(
            PlannedFile(EXCLUDE_PSEUDO_PATH, "create", None, None, "100644", content)
        )
    publish = PublishPlan(
        base=base,
        base_sha=base_sha,
        target=PR if pr else DIRECT,
        files=tuple(files),
        blockers=tuple(blockers),
        digest=plan_digest(base, base_sha, digest_files),
    )
    return InitPlan(
        root=root,
        publish=publish,
        settings=settings,
        detected=detected,
        exclude=exclude,
        warnings=warnings,
        issues=issues,
    )


# ── commit ────────────────────────────────────────────────────────────────────


def _body(plan: InitPlan) -> str:
    lines = [f"- {f.action} `{f.path}`" for f in plan.publish.files]
    return "Install factory:\n\n" + "\n".join(lines) + f"\n\nPlan digest: `{plan.publish.digest}`\n"


def commit_init(
    path: Path,
    *,
    expect: str | None = None,
    message: str | None = None,
    pr: bool = False,
    dry_run: bool = False,
    **options: Any,
) -> InitCommitResult:
    """Preview (`dry_run`) or commit the install plan to base in one commit (or a PR)."""
    from aifactory.providers import get_provider, publish
    from aifactory.run import gitops

    plan = plan_init(path, pr=pr, **options)
    if dry_run:
        return InitCommitResult(plan, True)
    if expect is not None and expect.strip() != plan.publish.digest:
        raise LibraryStoreError(
            "plan_changed",
            "the plan changed since it was reviewed (--expect); run --dry-run again",
            data=plan.to_json(),
        )
    if plan.blockers:
        first = plan.blockers[0]
        issues = plan.issues if first.code == "invalid_plan" else []
        raise LibraryStoreError(first.code, first.message, data=plan.to_json(), issues=issues)
    if not plan.publish.files:  # already installed: nothing to commit
        return InitCommitResult(plan, False)
    subject = (message or "").strip() or "factory: install"
    root, settings = plan.root, plan.settings
    try:
        if plan.publish.target == PR:
            provider = get_provider(settings, root)
            result = publish.publish_pr(
                root,
                provider=provider,
                settings=settings,
                plan=plan.publish,
                message=subject,
                body=_body(plan),
                prefix=INIT_BRANCH_PREFIX,
            )
            store = _store(root)
            try:
                result = publish.finish_pr(
                    root,
                    provider=provider,
                    settings=settings,
                    plan=plan.publish,
                    result=result,
                    message=subject,
                    store=store,
                    materialize=True,
                    command="init",
                )
            finally:
                if store is not None:
                    store.close()
        else:
            store = _store(root)
            try:
                result = publish.publish_direct(
                    root,
                    settings=settings,
                    plan=plan.publish,
                    message=subject,
                    store=store,
                    materialize=True,
                    command="init",
                )
            finally:
                if store is not None:
                    store.close()
    except ProviderError as exc:
        raise LibraryStoreError(exc.code, exc.message, data=plan.to_json()) from exc
    except RuntimeError as exc:
        raise LibraryStoreError("commit_failed", str(exc), data=plan.to_json()) from exc
    extra = list(result.warnings)
    if plan.exclude is not None:
        try:
            gitops.ensure_excluded(root, plan.exclude["lines"])
        except (RuntimeError, OSError) as exc:
            extra.append(f"info/exclude not updated: {exc}")
    return InitCommitResult(
        plan,
        False,
        committed=True,
        commit=result.commit,
        pushed=result.pushed,
        advanced=result.advanced,
        branch=result.branch,
        pr=result.pr,
        extra_warnings=tuple(extra),
        merged=result.merged,
    )
