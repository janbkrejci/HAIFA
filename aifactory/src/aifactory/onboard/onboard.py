"""``factory onboard``: extract the repo's own configuration once (decision 8, AR31-AR33).

``plan_onboard`` reads base of the repo and plans:

- ``pre_library`` (``onboard.extract``): every agent and workflow of ``.factory/`` is
  decided; the repo part is ``.factory/manifest.yaml`` with the ``onboarding`` block, the
  workflows the backlog names and the repo lacks, and the runtime lines of ``.gitignore``.
  Existing files of ``.factory/`` stay byte for byte as they are.
- ``sssf`` (``onboard.sssf``, AR32): the roster ``adws/adw_sssf_config/sssf.config.yaml``,
  the prompts (merged with the stock sssf text), the pi extensions, the stock chains and
  ``quality.py`` are converted into a new ``.factory/`` (config, agents, prompts,
  extensions, workflows, manifest). ``adws/`` stays byte for byte; the plan only adds.
  Without a factory config the base comes from the detection (M8) when the configured one
  is not an sssf repo.
- the library part: new library items (one library commit, pushed without force).

The plan writes nothing to the repo (other than remote-tracking refs and ``FETCH_HEAD`` of
the remote check) and nothing to the library. The remote check is the only network step:
``git fetch <remote> <base>`` and ``git ls-remote --heads <remote>
factory-config/onboarding``.

Blockers (``data.blockers``, the commit refuses with the first, exit 2): ``already_onboarded``,
``not_installed``, ``config_not_committed``, ``sssf_roster_invalid``,
``source_not_committed``, ``library_missing``, ``library_dirty``, ``library_behind``,
``library_diverged``, ``onboarded_in_remote``, ``onboarding_pending``, ``remote_unchecked``,
``base_behind``, ``base_diverged``, ``not_on_base``, ``run_in_progress``, ``dirty_paths``,
``invalid_plan``.

``run_onboard`` with ``commit`` recomputes the plan (``plan_changed`` against ``--expect``),
writes and pushes the library first (a refusal stops before the repo is touched), then
commits the repo plan to base without a checkout, or to the branch
``factory-config/onboarding`` with a pull request.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from aifactory import __version__
from aifactory.config.manifest import (
    MANIFEST_FILE,
    Manifest,
    ManifestItems,
    Onboarding,
    dump_manifest,
)
from aifactory.config.settings import ProjectSettings
from aifactory.engine.role_registry import Issue
from aifactory.library.model import ItemType
from aifactory.library.store import LibraryStoreError
from aifactory.onboard.extract import Extraction, ReportRow, extract_pre_library
from aifactory.onboard.state import RepoState, repo_state
from aifactory.providers import git
from aifactory.providers.base import ProviderError, PullRequest
from aifactory.providers.publish import (
    DIRECT,
    PR,
    Blocker,
    PlannedFile,
    PublishPlan,
    plan_digest,
)

if TYPE_CHECKING:
    from aifactory.library.detect import Detected
    from aifactory.library.install import _Source
    from aifactory.library.store import LibraryPlan
    from aifactory.library.tree import TreeFile

ONBOARDING_BRANCH = "factory-config/onboarding"
OnboardTarget = Literal["direct", "pr"]
OnboardSource = Literal["pre_library", "sssf"]
_FACTORY = ".factory/"
_GITIGNORE = ".gitignore"


@dataclass
class OnboardPlan:
    root: Path
    repo: RepoState
    target: str
    publish: PublishPlan
    settings: ProjectSettings | None = None
    library: dict[str, Any] | None = None
    extraction: Extraction | None = None
    manifest: Manifest | None = None
    library_plan: LibraryPlan | None = None
    exclude: dict[str, Any] | None = None
    remote: dict[str, Any] | None = None
    issues: list[Issue] = dataclasses.field(default_factory=list)
    warnings: list[str] = dataclasses.field(default_factory=list)
    source: OnboardSource = "pre_library"

    @property
    def blockers(self) -> tuple[Blocker, ...]:
        return self.publish.blockers

    @property
    def digest(self) -> str:
        return self.publish.digest

    @property
    def report(self) -> list[ReportRow]:
        return self.extraction.report if self.extraction is not None else []

    def to_json(self) -> dict[str, Any]:
        return {
            "repo": str(self.root),
            "state": self.repo.state,
            "source": self.source,
            **self.publish.to_json(),
            "paths": [f.path for f in self.publish.files],
            "report": [r.to_json() for r in self.report],
            "items": (self.manifest.items.model_dump(mode="json") if self.manifest else None),
            "manifest": self.manifest.to_json() if self.manifest is not None else None,
            "library": self.library,
            "library_plan": (
                self.library_plan.to_json() if self.library_plan is not None else None
            ),
            "added_workflows": list(self.extraction.added_workflows) if self.extraction else [],
            "remote": self.remote,
            "exclude": self.exclude,
            "warnings": list(self.warnings),
            "validation": {"ok": not self.issues, "issues": [i.to_dict() for i in self.issues]},
            "message": report_text(self),
        }


@dataclass(frozen=True)
class OnboardResult:
    plan: OnboardPlan
    dry_run: bool
    committed: bool = False
    commit: str | None = None
    pushed: bool = False
    advanced: bool = False
    branch: str | None = None
    pr: PullRequest | None = None
    library_commit: str | None = None
    extra_warnings: tuple[str, ...] = ()

    @property
    def warnings(self) -> list[str]:
        return list(self.plan.warnings) + list(self.extra_warnings)

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
            "library_commit": self.library_commit,
        }


# ── the report ────────────────────────────────────────────────────────────────


def report_text(plan: OnboardPlan, library_commit: str | None = None) -> str:
    """The report of the plan as text: the commit message body and the PR description."""
    lines = ["Onboarding report:", ""]
    for r in plan.report:
        lines.append(f"- {r.code} {r.subject}: {r.message}")
        if r.detail:
            lines += [f"    {line}" for line in r.detail.splitlines()]
    if plan.library_plan is not None and plan.library_plan.files:
        lines += ["", "Library:", ""]
        lines += [
            f"- {i.action} {i.type}/{i.name} {i.version}"
            for i in plan.library_plan.items
            if i.action != "unchanged"
        ]
    lines += ["", "Files:", ""]
    lines += [f"- {f.action} {f.path}" for f in plan.publish.files]
    lines += ["", f"Plan digest: {plan.digest}"]
    if library_commit is not None:
        lines.append(f"Library commit: {library_commit}")
    return "\n".join(lines) + "\n"


# ── digest ────────────────────────────────────────────────────────────────────


def onboard_digest(repo: str, library: str) -> str:
    """The digest of an onboarding: the repo part and the library part together."""
    return hashlib.sha256(f"aifactory-onboard-v1\0{repo}\0{library}".encode()).hexdigest()


def _stable(manifest: Manifest) -> bytes:
    """The manifest without its time and library commit, for the digest."""
    onboarding = manifest.onboarding
    if onboarding is not None:
        onboarding = onboarding.model_copy(update={"at": "", "library_commit": ""})
    return dump_manifest(manifest.model_copy(update={"onboarding": onboarding})).encode("utf-8")


# ── blockers ──────────────────────────────────────────────────────────────────


def _state_blocker(rs: RepoState) -> Blocker | None:
    if rs.state == "onboarded":
        who = rs.onboarding or {}
        by = f" by {who['by']}" if who.get("by") else ""
        at = f" at {who['at']}" if who.get("at") else ""
        return Blocker(
            "already_onboarded",
            f"the repo is onboarded in {rs.base}{by}{at}; it is never extracted again, "
            "run factory adopt",
            fix="factory adopt",
        )
    if rs.state == "none":
        return Blocker(
            "not_installed",
            f"the repo has no factory configuration in {rs.base}; run factory init",
            fix="factory init",
        )
    if rs.state == "working_tree":
        return Blocker(
            "config_not_committed",
            f"the factory configuration is only in the working tree, not in {rs.base}; "
            "run factory config commit",
            fix="factory config commit",
        )
    return None


def _short_plan(
    root: Path, rs: RepoState, target: str, blocker: Blocker, **extra: Any
) -> OnboardPlan:
    base_sha = rs.commit or ""
    publish = PublishPlan(
        base=rs.base,
        base_sha=base_sha,
        target=target,
        files=(),
        blockers=(blocker,),
        digest=plan_digest(rs.base, base_sha, []),
    )
    return OnboardPlan(root=root, repo=rs, target=target, publish=publish, **extra)


def _source_changes(root: Path, base_files: Mapping[str, bytes], base_exe: set[str]) -> list[str]:
    from aifactory.library.config_edit import read_state
    from aifactory.onboard.sssf import _git_blob

    wt = read_state(root, "worktree")
    paths = {p for p in (*wt.files, *base_files) if p.startswith(_FACTORY)}
    changed = {
        p
        for p in paths
        if p not in wt.files or p not in base_files or ((p in wt.executable) != (p in base_exe))
    }
    candidates = {
        p: _git_blob(base_files[p]) for p in paths - changed if wt.files[p] != base_files[p]
    }
    changed.update(_filtered_changes(root, candidates))
    return sorted(changed)


def _filtered_changes(root: Path, expected: Mapping[str, str]) -> list[str]:
    """Compare regular files with blobs using Git's clean filters, without index writes."""
    from aifactory.config.source import git as config_git

    if not expected:
        return []
    paths = list(expected)
    hashes = config_git(root, "hash-object", "--", *paths).split()
    return [p for p, blob in zip(paths, hashes, strict=True) if blob != expected[p]]


def _library_blockers(source: _Source) -> list[Blocker]:
    from aifactory.library import store

    assert source.root is not None and source.head is not None
    root, head = source.root, source.head
    out: list[Blocker] = []
    dirty = store._dirty(root)
    if dirty:
        out.append(
            Blocker(
                "library_dirty",
                f"the library at {root} has uncommitted changes: {', '.join(dirty[:5])}",
                fix="commit or discard the changes in the library",
            )
        )
    branch = store.current_branch(root)
    tip = store.remote_tip(root, branch)
    if tip is not None and tip != head and not git.is_ancestor(root, tip, head):
        behind = git.count_commits(root, head, tip)
        ahead = git.count_commits(root, tip, head)
        err = (
            store.behind_error(branch, behind)
            if ahead == 0
            else store.diverged_error(branch, ahead, behind)
        )
        fix = "factory library pull" if ahead == 0 else None
        out.append(Blocker(err.code, err.message, fix=fix))
    return out


def _check_remote(
    root: Path, remote: str, base: str, base_sha: str, direct: bool
) -> tuple[list[Blocker], list[str], dict[str, Any]]:
    """The remote check: fetch base and list the onboarding branch (the only network step)."""
    from aifactory.providers.publish import compare_remote

    info: dict[str, Any] = {
        "name": remote,
        "url": None,
        "checked": False,
        "tip": None,
        "branch_exists": None,
    }
    blockers: list[Blocker] = []
    warnings: list[str] = []
    pending = Blocker(
        "onboarding_pending",
        f"the branch {ONBOARDING_BRANCH} exists; an onboarding is waiting for its PR: merge or "
        f"close it and delete the branch",
        fix=f"merge or close the PR of {ONBOARDING_BRANCH} and delete the branch",
    )
    local_branch = git.rev_parse(root, f"refs/heads/{ONBOARDING_BRANCH}") is not None
    if not git.has_remote(root, remote):
        warnings.append(
            f"no_remote: the repo has no remote {remote}; onboarding is a local commit only"
        )
        if local_branch:
            blockers.append(pending)
        return blockers, warnings, info
    url = git.remote_url(root, remote)
    info["url"] = git.redact_url(url) if url else None
    unchecked = "the remote {remote} cannot be read ({detail}); check the network and try again"
    try:
        git.fetch(root, remote, base)
    except ProviderError as exc:
        detail = exc.message
        blockers.append(Blocker("remote_unchecked", unchecked.format(remote=remote, detail=detail)))
        if local_branch:
            blockers.append(pending)
        return blockers, warnings, info
    tip = git.remote_tip(root, remote, base)
    info["tip"] = tip
    if tip is not None and git.blob_at(root, tip, MANIFEST_FILE) is not None:
        blockers.append(
            Blocker(
                "onboarded_in_remote",
                f"{remote}/{base} already has {MANIFEST_FILE}: the repo was onboarded elsewhere; "
                "run factory config pull, then factory adopt",
                fix="factory config pull, then factory adopt",
            )
        )
    exists = git.remote_branch_exists(root, remote, ONBOARDING_BRANCH)
    info["branch_exists"] = exists
    if exists is None:
        blockers.append(
            Blocker(
                "remote_unchecked",
                unchecked.format(remote=remote, detail=f"git ls-remote {ONBOARDING_BRANCH}"),
            )
        )
    elif exists or local_branch:
        blockers.append(pending)
    if exists is not None:
        info["checked"] = True
    if direct and not any(b.code == "onboarded_in_remote" for b in blockers):
        found, notes = compare_remote(root, remote, base, base_sha, tip)
        blockers += found
        warnings += [f"remote_note: {n}" for n in notes]
    return blockers, warnings, info


def _check_invariant(files: Sequence[PlannedFile]) -> None:
    """Onboarding only adds files under ``.factory/`` and appends lines to ``.gitignore``."""
    for f in files:
        if f.path == _GITIGNORE:
            old = f.old_content or b""
            if f.content is None or not f.content.startswith(old):
                raise RuntimeError(f"onboarding would rewrite {f.path}; it only appends lines")
            continue
        if not f.path.startswith(_FACTORY) or f.action != "create":
            raise RuntimeError(f"onboarding would {f.action} {f.path}; it only adds files")


# ── plan ──────────────────────────────────────────────────────────────────────


def _parse_keys(
    keep_local: Sequence[tuple[ItemType, str]], names: Sequence[tuple[ItemType, str, str]]
) -> tuple[set[tuple[ItemType, str]], dict[tuple[ItemType, str], str]]:
    renames: dict[tuple[ItemType, str], str] = {}
    for kind, slot, new in names:
        if (kind, slot) in renames and renames[(kind, slot)] != new:
            raise LibraryStoreError(
                "conflicting_options", f"--name {kind}/{slot} is given twice with other names"
            )
        renames[(kind, slot)] = new
    return set(keep_local), renames


def _detected_state(root: Path) -> tuple[RepoState, Detected | None]:
    """The repo state; for a repo without a factory config also the detected remote and
    base (M8), whose base is used when the configured one is not an sssf repo."""
    from aifactory.library.detect import detect

    rs = repo_state(root)
    if rs.state not in ("sssf", "none", "working_tree"):
        return rs, None
    if (root / ".factory" / "config.yaml").is_file():
        return rs, None
    detected = detect(root)
    if detected.base and detected.base != rs.base:
        alt = repo_state(root, detected.base)
        if alt.state == "sssf":
            rs = alt
    return rs, detected


def _library_missing(environ: Mapping[str, str] | None) -> Blocker:
    from aifactory.library.store import library_root

    lib = library_root(environ)
    return Blocker(
        "library_missing",
        f"no library at {lib}; create it with factory library init or clone the team's "
        "library with factory library clone URL",
        fix="factory library init (or factory library clone URL)",
    )


def _library_json(source: _Source) -> dict[str, Any]:
    assert source.library is not None
    return {
        "path": str(source.root),
        "head": source.head,
        "id": source.library.id,
        "name": source.library.name,
        "remote": source.library.remote,
    }


def plan_onboard(
    path: Path,
    *,
    pr: bool = False,
    keep_local: Sequence[tuple[ItemType, str]] = (),
    names: Sequence[tuple[ItemType, str, str]] = (),
    workflows: bool = False,
    environ: Mapping[str, str] | None = None,
) -> OnboardPlan:
    """The onboarding plan; see the module docstring. Writes nothing."""
    from aifactory.library.install import _repo_root

    root = _repo_root(path)
    rs, detected = _detected_state(root)
    target = PR if pr else DIRECT
    keep, renames = _parse_keys(keep_local, names)
    state_blocker = _state_blocker(rs)
    if state_blocker is not None or rs.commit is None:
        blocker = state_blocker or Blocker("not_installed", f"base {rs.base} does not exist")
        return _short_plan(root, rs, target, blocker)
    if rs.state == "sssf":
        from aifactory.library.detect import detect

        return _plan_sssf(
            root,
            rs,
            target,
            pr,
            keep,
            renames,
            workflows,
            detected if detected is not None else detect(root),
            environ,
        )
    if workflows:
        raise LibraryStoreError("conflicting_options", "--workflows is only for sssf repos")
    return _plan_pre_library(root, rs, target, pr, keep, renames, environ)


def _plan_pre_library(
    root: Path,
    rs: RepoState,
    target: str,
    pr: bool,
    keep: set[tuple[ItemType, str]],
    renames: dict[tuple[ItemType, str], str],
    environ: Mapping[str, str] | None,
) -> OnboardPlan:
    from aifactory.library.config_edit import read_state
    from aifactory.library.install import _Source

    state = read_state(root, "base")
    base, base_sha = state.base, state.base_sha
    settings = state.settings
    blockers: list[Blocker] = []

    changed = _source_changes(root, state.files, state.executable)
    if changed:
        blockers.append(
            Blocker(
                "source_not_committed",
                "the factory configuration has uncommitted changes: "
                + ", ".join(changed)
                + "; commit or discard the changes of .factory/ first",
                fix="commit or discard the changes of .factory/ first",
            )
        )

    source = _Source(environ)
    if source.root is None or source.head is None or source.library is None:
        return _short_plan(root, rs, target, _library_missing(environ), settings=settings)
    extraction = extract_pre_library(
        state,
        source,
        environ,
        keep_local=keep,
        names=renames,
        sssf_leftover=rs.sssf_leftover,
    )
    workflow_names = [*state.workflows(), *extraction.added_workflows]
    overlay = {f".factory/workflows/{n}.yaml": d for n, d in state.workflows().items()}
    return _finish(
        _Planned(
            root=root,
            rs=rs,
            target=target,
            pr=pr,
            base=base,
            base_sha=base_sha,
            settings=settings,
            source=source,
            extraction=extraction,
            onboarding_source="pre_library",
            workflows=workflow_names,
            overlay=overlay,
            roster=list(state.roster),
            blockers=blockers,
        ),
        environ,
    )


def _sssf_changes(root: Path, files: Mapping[str, TreeFile]) -> list[str]:
    """Paths the sssf conversion reads whose working tree differs from base, and untracked
    files next to them (no git status, no index refresh)."""
    import os

    out: set[str] = set()
    candidates: dict[str, str] = {}
    for path, f in files.items():
        disk = root / path
        if disk.is_symlink() or not disk.is_file():
            if f.mode != "120000" or not disk.is_symlink():
                out.add(path)
            continue
        if f.mode == "120000":
            out.add(path)
            continue
        exe = bool(disk.stat().st_mode & 0o100)
        if exe != (f.mode == "100755"):
            out.add(path)
        else:
            candidates[path] = f.blob
    out.update(_filtered_changes(root, candidates))
    for rel in ("adws/adw_sssf_config", "adws/adw_data/harness_engineering", "adws/adw_modules"):
        folder = root / rel
        if not folder.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if name.endswith(".pyc"):
                    continue
                path = Path(dirpath, name).relative_to(root).as_posix()
                if path not in files:
                    out.add(path)
    folder = root / "adws"
    if folder.is_dir():
        for disk in folder.glob("adw_*.py"):
            path = disk.relative_to(root).as_posix()
            if path not in files:
                out.add(path)
    return sorted(out)


def _plan_sssf(
    root: Path,
    rs: RepoState,
    target: str,
    pr: bool,
    keep: set[tuple[ItemType, str]],
    renames: dict[tuple[ItemType, str], str],
    workflows: bool,
    detected: Detected,
    environ: Mapping[str, str] | None,
) -> OnboardPlan:
    from aifactory.library.install import _Source
    from aifactory.onboard.sssf import extract_sssf

    assert rs.commit is not None
    base, base_sha = rs.base, rs.commit
    source = _Source(environ)
    if source.root is None or source.head is None or source.library is None:
        return _short_plan(root, rs, target, _library_missing(environ))
    try:
        conversion = extract_sssf(
            root,
            base,
            base_sha,
            source,
            environ,
            detected=detected,
            keep_local=keep,
            names=renames,
            workflows=workflows,
            rosters=rs.rosters,
        )
    except LibraryStoreError as exc:
        if exc.code != "sssf_roster_invalid":
            raise
        blocker = Blocker(
            "sssf_roster_invalid",
            exc.message,
            fix="fix adws/adw_sssf_config/sssf.config.yaml and commit it",
        )
        return _short_plan(root, rs, target, blocker)
    blockers: list[Blocker] = []
    changed = _sssf_changes(root, conversion.source_files)
    if changed:
        blockers.append(
            Blocker(
                "source_not_committed",
                "the sssf configuration has uncommitted changes: "
                + ", ".join(changed)
                + "; commit or discard the changes of adws/ first",
                fix="commit or discard the changes of adws/ first",
            )
        )
    return _finish(
        _Planned(
            root=root,
            rs=rs,
            target=target,
            pr=pr,
            base=base,
            base_sha=base_sha,
            settings=conversion.settings,
            source=source,
            extraction=conversion.extraction,
            onboarding_source="sssf",
            workflows=list(conversion.workflows),
            overlay={},
            roster=conversion.roster,
            blockers=blockers,
        ),
        environ,
    )


@dataclass
class _Planned:
    """What both extractors hand to the shared tail of the plan."""

    root: Path
    rs: RepoState
    target: str
    pr: bool
    base: str
    base_sha: str
    settings: ProjectSettings
    source: _Source
    extraction: Extraction
    onboarding_source: OnboardSource
    workflows: list[str]
    overlay: dict[str, bytes]
    roster: list[Any]
    blockers: list[Blocker]


def _finish(p: _Planned, environ: Mapping[str, str] | None) -> OnboardPlan:
    """Library, remote and M7 blockers, manifest, files, validation and digest."""
    from aifactory.library import install_commit
    from aifactory.library.config_edit import _missing_harnesses
    from aifactory.library.install import _git_out, _now

    root, base, base_sha, settings, source = p.root, p.base, p.base_sha, p.settings, p.source
    extraction = p.extraction
    assert source.head is not None and source.library is not None
    blockers = list(p.blockers)
    warnings: list[str] = []
    blockers += _library_blockers(source)
    library = _library_json(source)

    found, notes, remote = _check_remote(root, settings.remote, base, base_sha, not p.pr)
    blockers += found
    warnings += notes

    if not p.pr:
        from aifactory.providers.publish import direct_blockers

        store = install_commit._store(root)
        try:
            more, _ = direct_blockers(
                root,
                remote=settings.remote,
                base=base,
                base_sha=base_sha,
                store=store,
                check_remote=False,
            )
        finally:
            if store is not None:
                store.close()
        blockers += more

    warnings += extraction.warnings
    manifest = Manifest(
        written_by=__version__,
        library=source.library,
        onboarding=Onboarding(
            source=p.onboarding_source,
            source_commit=base_sha,
            at=_now(),
            by=_git_out(root, "config", "user.name"),
            factory=__version__,
            library_commit=source.head,
        ),
        items=ManifestItems(
            agents=dict(extraction.entries.get("agent", {})),
            workflows=dict(extraction.entries.get("workflow", {})),
            extensions=dict(extraction.entries.get("extension", {})),
        ),
    )
    contents: dict[str, bytes] = {
        **extraction.files,
        MANIFEST_FILE: dump_manifest(manifest).encode("utf-8"),
    }
    init_warnings: list[install_commit.InitWarning] = []
    exclude = install_commit._gitignore(root, base_sha, contents, init_warnings)
    warnings += [f"{w.code}: {w.message}" for w in init_warnings]
    from aifactory.providers.publish import plan_contents

    files = plan_contents(root, base_sha, contents)
    _check_invariant(files)

    dirty = install_commit._dirty(root, files)
    if dirty:
        blockers.append(
            Blocker(
                "dirty_paths",
                "planned paths exist in the working tree with other content: "
                + ", ".join(dirty)
                + "; move them away or commit them first",
            )
        )

    missing_harnesses = _missing_harnesses()
    issues = install_commit._validate(
        root, base, base_sha, {**p.overlay, **contents}, p.workflows, missing_harnesses
    )
    if issues:
        blockers.append(
            Blocker(
                "invalid_plan",
                f"the planned configuration has {len(issues)} problem(s); see the issues",
            )
        )
    warnings += _harness_warnings(p.roster, missing_harnesses)

    library_plan: LibraryPlan | None = None
    if extraction.library_items:
        from aifactory.library.store import import_items

        written = import_items(
            extraction.library_items,
            _library_source(root, base, base_sha),
            _library_subject(root, len(extraction.library_items)),
            dry_run=True,
            environ=environ,
        )
        library_plan = written.plan
        warnings += [w for w in written.warnings if "uncommitted changes" not in w]

    digest_files = [
        dataclasses.replace(f, content=_stable(manifest)) if f.path == MANIFEST_FILE else f
        for f in files
    ]
    if exclude is not None:
        content = "\n".join(exclude["lines"]).encode("utf-8")
        digest_files.append(
            PlannedFile(install_commit.EXCLUDE_PSEUDO_PATH, "create", None, None, "100644", content)
        )
    repo_part = plan_digest(base, base_sha, digest_files)
    library_part = (
        library_plan.digest if library_plan is not None else plan_digest("library", source.head, [])
    )
    publish = PublishPlan(
        base=base,
        base_sha=base_sha,
        target=p.target,
        files=tuple(files),
        blockers=tuple(blockers),
        digest=onboard_digest(repo_part, library_part),
    )
    return OnboardPlan(
        root=root,
        repo=p.rs,
        target=p.target,
        publish=publish,
        settings=settings,
        library=library,
        extraction=extraction,
        manifest=manifest,
        library_plan=library_plan,
        exclude=exclude,
        remote=remote,
        issues=issues,
        warnings=warnings,
        source=p.onboarding_source,
    )


def _harness_warnings(roster: Sequence[Mapping[str, Any]], missing: frozenset[str]) -> list[str]:
    from aifactory.harness.check import binary_name

    out: list[str] = []
    for entry in roster:
        name = entry.get("harness") or entry.get("coding_agent")
        if isinstance(name, str) and name in missing:
            out.append(
                f"harness_missing: agent {entry['name']} uses harness {name}, whose CLI "
                f"{binary_name(name)} is not on PATH"
            )
    return out


def _library_source(root: Path, base: str, base_sha: str) -> str:
    return f"onboard {root} {base}@{base_sha[:12]}"


def _library_subject(root: Path, count: int) -> str:
    return f"library: onboard {count} item(s) from {root.name}"


# ── commit ────────────────────────────────────────────────────────────────────


def _raise_blocker(plan: OnboardPlan) -> None:
    first = plan.blockers[0]
    issues = plan.issues if first.code == "invalid_plan" else []
    data = plan.to_json()
    if first.fix is not None:
        data["fix"] = first.fix
    raise LibraryStoreError(first.code, first.message, data=data, issues=issues)


def run_onboard(
    path: Path,
    *,
    commit: bool = False,
    pr: bool = False,
    expect: str | None = None,
    message: str | None = None,
    keep_local: Sequence[tuple[ItemType, str]] = (),
    names: Sequence[tuple[ItemType, str, str]] = (),
    workflows: bool = False,
    environ: Mapping[str, str] | None = None,
) -> OnboardResult:
    """The plan (without `commit`) or the onboarding: library first, then the repo."""
    plan = plan_onboard(
        path, pr=pr, keep_local=keep_local, names=names, workflows=workflows, environ=environ
    )
    if not commit:
        return OnboardResult(plan, True)
    if expect is not None and expect.strip() != plan.digest:
        raise LibraryStoreError(
            "plan_changed",
            "the plan changed since it was reviewed (--expect); run --dry-run again",
            data=plan.to_json(),
        )
    if plan.blockers:
        _raise_blocker(plan)
    assert plan.library is not None and plan.manifest is not None
    assert plan.extraction is not None and plan.settings is not None

    library_commit: str = plan.library["head"]
    if plan.library_plan is not None and plan.library_plan.files:
        from aifactory.library.store import import_items

        written = import_items(
            plan.extraction.library_items,
            _library_source(plan.root, plan.publish.base, plan.publish.base_sha),
            _library_subject(plan.root, len(plan.extraction.library_items)),
            environ=environ,
            expect_head=library_commit,
        )
        library_commit = written.commit or library_commit
    wrote_library = library_commit != plan.library["head"]

    onboarding = plan.manifest.onboarding
    assert onboarding is not None
    manifest = plan.manifest.model_copy(
        update={"onboarding": onboarding.model_copy(update={"library_commit": library_commit})}
    )
    content = dump_manifest(manifest).encode("utf-8")
    files = tuple(
        dataclasses.replace(f, content=content) if f.path == MANIFEST_FILE else f
        for f in plan.publish.files
    )
    publish_plan = dataclasses.replace(plan.publish, files=files)
    plan = dataclasses.replace(plan, manifest=manifest, publish=publish_plan)
    try:
        return _commit_repo(plan, pr, message, library_commit)
    except LibraryStoreError as exc:
        if not wrote_library:
            raise
        data = {**(exc.data or plan.to_json()), "library_commit": library_commit}
        data["fix"] = "factory onboard --dry-run"
        raise LibraryStoreError(
            exc.code,
            f"{exc.message}; the library already has the new versions "
            f"({library_commit[:12]}): run factory onboard again, it connects them",
            data=data,
            issues=exc.issues,
        ) from exc


def _commit_repo(
    plan: OnboardPlan, pr: bool, message: str | None, library_commit: str
) -> OnboardResult:
    from aifactory.library.install_commit import _store
    from aifactory.providers import get_provider, publish
    from aifactory.run import gitops

    assert plan.settings is not None and plan.library is not None
    root, settings = plan.root, plan.settings
    subject = (message or "").strip() or (
        f"factory: onboard {root.name} ({plan.source}) with the library {plan.library['name']}"
    )
    body = report_text(plan, library_commit)
    try:
        if pr:
            result = publish.publish_pr(
                root,
                provider=get_provider(settings, root),
                settings=settings,
                plan=plan.publish,
                message=f"{subject}\n\n{body}",
                body=body,
                prefix=ONBOARDING_BRANCH,
                branch=ONBOARDING_BRANCH,
            )
        else:
            store = _store(root)
            try:
                result = publish.publish_direct(
                    root,
                    settings=settings,
                    plan=plan.publish,
                    message=f"{subject}\n\n{body}",
                    store=store,
                    materialize=True,
                    command="onboard",
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
    return OnboardResult(
        plan,
        False,
        committed=True,
        commit=result.commit,
        pushed=result.pushed,
        advanced=result.advanced,
        branch=result.branch,
        pr=result.pr,
        library_commit=library_commit,
        extra_warnings=tuple(extra),
    )


__all__ = [
    "ONBOARDING_BRANCH",
    "OnboardPlan",
    "OnboardResult",
    "OnboardTarget",
    "onboard_digest",
    "plan_onboard",
    "report_text",
    "run_onboard",
]
