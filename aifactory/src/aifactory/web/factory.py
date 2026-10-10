"""The Factory tab of one repository: check, plan, apply and the base pull.

``check_view`` is ``factory check`` (``run_check``) plus the registry finding
``trace_db_shared`` and a 60 s cache per ``offline`` flag (``fresh`` renews it).
``plan`` and ``apply`` call the CLI core for init, update, config commit,
item add/set/remove/export/revert. ``items`` returns CLI item states
without writing the cache. ``pull`` is ``factory config pull`` (``pull_config``).

The body of plan and apply carries only the action, its options, the target (``base`` or
``pr``), the commit message and the digest; any other key is a ``usage_error``, so no path
or file content comes from the request. ``exclusive`` lets one apply or pull run at a time
per repository (``busy``).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from aifactory.web.backlog import UsageError
from aifactory.web.registry import RepoError

if TYPE_CHECKING:
    from aifactory.check.machine import Machine
    from aifactory.check.model import CheckReport
    from aifactory.web.registry import RegistryState

JsonDict = dict[str, Any]

CHECK_TTL = 60.0
"""Seconds a check result is reused (``fresh=1`` renews it)."""
ITEM_ACTIONS = ("add", "set", "remove", "export", "revert")
ACTIONS = ("init", "update", "config_commit", *ITEM_ACTIONS)
TARGETS = ("base", "pr")
PROVIDERS = ("local", "github", "azure")
AZURE_KEYS = ("organization", "project", "repository")
INIT_OPTIONS = (
    "agents",
    "bind",
    "workflows",
    "base",
    "provider",
    "azure",
    "backlog_dir",
    "specs_dir",
    "docs_dir",
)
UPDATE_OPTIONS = ("item", "take", "merge", "migrate")
OPTIONS: dict[str, tuple[str, ...]] = {
    "init": INIT_OPTIONS,
    "update": UPDATE_OPTIONS,
    "config_commit": (),
    "add": ("type", "name", "slot", "harness", "model", "thinking", "agent"),
    "set": ("type", "name", "harness", "model", "thinking", "tools", "writes", "color"),
    "remove": ("type", "name", "prune"),
    "export": ("type", "name", "slot"),
    "revert": ("type", "name", "to"),
}
PLAN_KEYS = ("action", "options", "target")
APPLY_KEYS = ("action", "digest", "options", "target", "message")
TRACE_DB_FIX = "set trace_db in .factory/local.yaml to a file no other registered repository uses"

_clock = time.monotonic
"""The clock of the check cache (a module attribute, so tests can move it)."""

STATUS: dict[str, int] = {
    # state conflicts and blockers
    "invalid_library": 422,
    "slot_taken": 409,
    "in_use": 409,
    "item_exists": 409,
    "library_changed_since": 409,
    "library_missing": 409,
    "registry_missing": 409,
    "registry_invalid": 422,
    "unknown_repo": 404,
    "unknown_version": 422,
    "git_identity_missing": 409,
    "plan_changed": 409,
    "busy": 409,
    "run_in_progress": 409,
    "not_on_base": 409,
    "base_behind": 409,
    "base_diverged": 409,
    "base_moved": 409,
    "dirty_paths": 409,
    "dirty_base": 409,
    "already_installed": 409,
    "existing_config": 409,
    "config_not_committed": 409,
    "not_onboarded": 409,
    "merge_conflict": 409,
    "no_remote": 409,
    "library_dirty": 409,
    "library_behind": 409,
    "library_diverged": 409,
    # invalid input or plan
    "invalid_plan": 422,
    "invalid_value": 422,
    "conflicting_options": 422,
    "unknown_base": 422,
    "unknown_item": 422,
    "invalid_item": 422,
    "invalid_config": 422,
    "format_unsupported": 422,
    "not_a_repository": 422,
    # remote and hosting
    "push_failed": 502,
    "fetch_failed": 502,
    "pull_failed": 502,
    "gh_failed": 502,
    "gh_missing": 502,
    "az_failed": 502,
    "az_missing": 502,
    "az_not_logged_in": 502,
    "az_timeout": 502,
    "az_devops_missing": 502,
    "commit_failed": 500,
}


@dataclass
class FactoryState:
    """Per-repository state of the Factory tab: one apply or pull at a time, the check cache."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    checks: dict[bool, tuple[float, CheckReport, str]] = field(default_factory=dict)


class Failure(Exception):
    """A core error turned into an envelope: ``code``, HTTP ``status``, ``data``, ``issues``."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int,
        *,
        data: Mapping[str, Any] | None = None,
        issues: list[JsonDict] | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status = status
        self.data = data
        self.issues = list(issues or [])


@dataclass(frozen=True)
class Request:
    """A validated plan or apply body."""

    action: str
    options: JsonDict
    target: str = "base"
    digest: str | None = None
    message: str | None = None

    @property
    def pr(self) -> bool:
        return self.target == "pr"


# ── the busy guard ────────────────────────────────────────────────────────────


@contextmanager
def exclusive(state: FactoryState) -> Iterator[None]:
    """Hold the repository's lock; ``busy`` when another apply or pull holds it."""
    if not state.lock.acquire(blocking=False):
        raise RepoError(
            "busy", "another apply or base pull is running in this repository; try again"
        )
    try:
        yield
    finally:
        state.lock.release()


# ── check ─────────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _trace_db_finding(root: Path, registry_state: RegistryState) -> Any:
    from aifactory.check.model import Finding
    from aifactory.web.repos import check_trace_db

    try:
        check_trace_db(root, registry_state)
    except RepoError as exc:
        if exc.code == "trace_db_shared":
            return Finding(
                "trace_db_shared", "machine", "error", exc.message, fix=TRACE_DB_FIX, action=None
            )
        raise
    return None


def check_view(
    root: Path,
    state: FactoryState,
    *,
    offline: bool,
    fresh: bool,
    machine: Machine | None = None,
    registry_state: RegistryState | None = None,
) -> tuple[JsonDict, bool, str]:
    """``factory check`` of ``root``: ``(data, ok, message)``; the message when not ok."""
    from aifactory import check

    entry = state.checks.get(offline)
    cached = entry is not None and not fresh and _clock() - entry[0] < CHECK_TTL
    if cached:
        assert entry is not None
        _at, report, checked_at = entry
    else:
        try:
            report = check.run_check(root, offline=offline, machine=machine, require_repo=True)
        except check.NotARepositoryError as exc:
            raise Failure("not_a_repository", str(exc), 422) from exc
        checked_at = _now()
        state.checks[offline] = (_clock(), report, checked_at)
    if registry_state is not None:
        finding = _trace_db_finding(root, registry_state)
        if finding is not None:
            report = replace(report, findings=(*report.findings, finding))
    data = {
        **report.to_json(),
        "checked_at": checked_at,
        "cached": cached,
        **_manifest_view(root),
    }
    errors = report.errors()
    codes = ", ".join(dict.fromkeys(f.code for f in errors))
    return data, report.ok, f"{len(errors)} error(s): {codes}"


def _manifest_view(root: Path) -> JsonDict:
    """The manifest in base (``format``, ``written_by``) and the package version; never cached."""
    import aifactory
    from aifactory.config import ConfigError
    from aifactory.config.repo_state import repo_state

    manifest: JsonDict | None = None
    manifest_error: str | None = None
    try:
        repo = repo_state(root)
    except (ConfigError, OSError):
        repo = None
    if repo is not None:
        if repo.manifest is not None:
            manifest = {"format": repo.manifest.format, "written_by": repo.manifest.written_by}
        manifest_error = repo.manifest_error
    return {
        "manifest": manifest,
        "manifest_error": manifest_error,
        "library": repo.library if repo is not None else None,
        "version": aifactory.__version__,
    }


# ── body validation ───────────────────────────────────────────────────────────


def _keys(body: Mapping[str, Any], allowed: tuple[str, ...], what: str) -> None:
    unknown = sorted(set(body) - set(allowed))
    if unknown:
        raise UsageError(f"unknown {what}: {', '.join(unknown)}; allowed: {', '.join(allowed)}")


def _str_list(value: object, key: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise UsageError(f"options.{key} must be a list of strings")
    return list(value)


def _opt_str(value: object, key: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise UsageError(f"{key} must be a string")


def _options(action: str, raw: object) -> JsonDict:
    from aifactory.library.model import ITEM_TYPES

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise UsageError("options must be a JSON object")
    _keys(raw, OPTIONS[action], f"options for {action}")
    out: JsonDict = {}
    for key, value in raw.items():
        if key == "prune":
            if not isinstance(value, bool):
                raise UsageError(f"options.{key} must be a boolean")
            out[key] = value
        elif key in ("agents", "workflows", "item", "take", "merge", "migrate"):
            if value is None and action == "init":
                continue
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise UsageError(f"options.{key} must be a list of strings")
            out[key] = list(value)
        elif key == "bind":
            out[key] = _bind(value)
        elif key == "azure":
            out[key] = _azure(value)
        else:
            if value is None and action == "init":
                continue
            if not isinstance(value, str):
                raise UsageError(f"options.{key} must be a string")
            out[key] = value
    if action in ITEM_ACTIONS:
        if any(not isinstance(out.get(k), str) or not out[k].strip() for k in ("type", "name")):
            raise UsageError("options.type and options.name are required non-empty strings")
        if out["type"] not in ITEM_TYPES:
            raise UsageError("unknown item type")
    return out


def _bind(value: object) -> dict[str, JsonDict]:
    if not isinstance(value, dict):
        raise UsageError("options.bind must be an object {agent: {harness, model?, thinking?}}")
    out: dict[str, JsonDict] = {}
    for agent, spec in value.items():
        if not isinstance(spec, dict):
            raise UsageError(
                f"options.bind.{agent} must be an object {{harness, model?, thinking?}}"
            )
        _keys(spec, ("harness", "model", "thinking"), f"keys in options.bind.{agent}")
        out[agent] = {k: _opt_str(spec.get(k), f"options.bind.{agent}.{k}") for k in spec}
    return out


def _azure(value: object) -> JsonDict:
    if not isinstance(value, dict):
        raise UsageError("options.azure must be an object {organization, project, repository}")
    _keys(value, AZURE_KEYS, "keys in options.azure")
    return {k: _opt_str(value.get(k), f"options.azure.{k}") for k in AZURE_KEYS}


def _common(body: Mapping[str, Any]) -> tuple[str, JsonDict, str]:
    action = body.get("action")
    if action not in ACTIONS:
        raise UsageError(f"action must be one of {', '.join(ACTIONS)}, got {action!r}")
    target = body.get("target")
    if target is None:
        target = "base"
    if target not in TARGETS:
        raise UsageError(f"target must be one of {', '.join(TARGETS)}, got {target!r}")
    if "options" in body and not isinstance(body["options"], dict):
        raise UsageError("options must be a JSON object")
    return action, _options(action, body.get("options")), target


def parse_plan_body(body: Mapping[str, Any]) -> Request:
    """The body of ``POST factory/plan``; ``UsageError`` for a bad one."""
    _keys(body, PLAN_KEYS, "keys")
    action, options, target = _common(body)
    return Request(action, options, target)


def parse_apply_body(body: Mapping[str, Any]) -> Request:
    """The body of ``POST factory/apply``; ``UsageError`` for a bad one."""
    _keys(body, APPLY_KEYS, "keys")
    action, options, target = _common(body)
    digest = body.get("digest")
    if not isinstance(digest, str) or not digest.strip():
        raise UsageError("digest must be the non-empty digest of the reviewed plan")
    message = _opt_str(body.get("message"), "message")
    return Request(action, options, target, digest.strip(), message)


# ── core calls ────────────────────────────────────────────────────────────────


def _bind_text(agent: str, spec: Mapping[str, str | None]) -> str:
    from aifactory.library.store import LibraryStoreError

    harness = (spec.get("harness") or "").strip()
    if not harness:
        raise LibraryStoreError("invalid_value", f"bind {agent}: harness is required")
    parts = [harness, spec.get("model") or "", spec.get("thinking") or ""]
    for part in (agent, *parts):
        if any(ch in part for ch in ":=,"):
            raise LibraryStoreError(
                "invalid_value", f"bind {agent}: {part!r} must not contain ':', '=' or ','"
            )
    return f"{agent}={':'.join(parts).rstrip(':')}"


def _init_kwargs(options: Mapping[str, Any]) -> JsonDict:
    from aifactory.library.install import parse_binding
    from aifactory.library.store import LibraryStoreError

    provider = options.get("provider")
    if provider is not None and provider not in PROVIDERS:
        raise LibraryStoreError(
            "invalid_value", f"provider must be one of {', '.join(PROVIDERS)}, got {provider!r}"
        )
    azure: JsonDict | None = options.get("azure")
    azure_given = azure is not None and any(azure.values())
    if azure_given and provider not in (None, "azure"):
        raise LibraryStoreError(
            "conflicting_options", f"azure needs provider azure, not {provider}"
        )
    if provider is None and azure_given:
        provider = "azure"
    bind: Mapping[str, Mapping[str, str | None]] = options.get("bind") or {}
    return {
        "base": options.get("base"),
        "provider": provider,
        "azure": azure if azure_given else None,
        "bindings": [parse_binding(_bind_text(agent, spec)) for agent, spec in bind.items()],
        "agents": options.get("agents"),
        "workflows": options.get("workflows"),
        "backlog_dir": options.get("backlog_dir"),
        "specs_dir": options.get("specs_dir"),
        "docs_dir": options.get("docs_dir"),
    }


def _issues(exc: Exception) -> list[JsonDict]:
    from aifactory.library.store import LibraryStoreError

    raw = getattr(exc, "issues", [])
    if isinstance(exc, LibraryStoreError):
        return [i.to_dict() for i in raw]
    return [dict(i) for i in raw]


def _status(code: str, data: Mapping[str, Any] | None) -> int:
    if code in STATUS:
        return STATUS[code]
    blockers = (data or {}).get("blockers") or []
    if any(isinstance(b, Mapping) and b.get("code") == code for b in blockers):
        return 409
    return 500


@contextmanager
def _core_errors(action: str | None = None) -> Iterator[None]:
    from aifactory.config import ConfigError
    from aifactory.config.commit import ConfigCommitError
    from aifactory.library.store import LibraryStoreError
    from aifactory.providers.base import ProviderError

    try:
        yield
    except (LibraryStoreError, ConfigCommitError) as exc:
        data = dict(exc.data) if exc.data is not None else None
        if data is not None and action is not None:
            data.setdefault("action", action)
        raise Failure(
            exc.code, exc.message, _status(exc.code, data), data=data, issues=_issues(exc)
        ) from exc
    except ProviderError as exc:
        raise Failure(exc.code, exc.message, _status(exc.code, None)) from exc
    except ConfigError as exc:
        code = getattr(exc, "code", None) or "invalid_config"
        raise Failure(code, str(exc), _status(code, None)) from exc


def _call(
    root: Path, req: Request, *, dry_run: bool, environ: Mapping[str, str] | None = None
) -> Any:
    expect = None if dry_run else req.digest
    message = None if dry_run else req.message
    if req.action == "init":
        from aifactory.library.install_commit import commit_init

        return commit_init(
            root,
            dry_run=dry_run,
            pr=req.pr,
            expect=expect,
            message=message,
            environ=environ,
            **_init_kwargs(req.options),
        )
    if req.action == "update":
        from aifactory.library.update import run_update

        return run_update(
            root,
            item=req.options.get("item") or (),
            environ=environ,
            take=req.options.get("take") or (),
            merge=req.options.get("merge") or (),
            migrate=req.options.get("migrate") or (),
            dry_run=dry_run,
            commit=True,
            pr=req.pr,
            expect=expect,
            message=message,
        )
    if req.action in ITEM_ACTIONS:
        from aifactory.library.config_edit import Command, run_config

        return run_config(
            cast(Command, req.action),
            root,
            dry_run=dry_run,
            commit=True,
            pr=req.pr,
            expect=expect,
            message=message,
            environ=environ,
            **req.options,
        )
    from aifactory.config.commit import commit_config

    return commit_config(root, pr=req.pr, dry_run=dry_run, expect=expect, message=message)


def plan(
    root: Path, req: Request, *, environ: Mapping[str, str] | None = None
) -> tuple[JsonDict, list[str]]:
    """The plan of ``req`` with its ``digest``; reads only."""
    with _core_errors(req.action):
        result = _call(root, req, dry_run=True, environ=environ)
    data = {"action": req.action, **result.to_json()}
    if req.action not in ("init", "update", "config_commit"):
        return data, list(result.warnings)
    if "remote" not in data:
        if req.action == "update":
            data["remote"] = result.plan.state.settings.remote
        else:
            from aifactory.config.commit import _context

            data["remote"] = _context(root).settings.remote
    from aifactory.providers import git

    if data.get("remote") and not git.has_remote(root, data["remote"]):
        data["remote"] = None
    return data, list(result.warnings)


APPLY_FIELDS = ("commit", "pushed", "pr", "committed", "advanced", "branch")


def apply(
    root: Path,
    req: Request,
    state: FactoryState | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> tuple[JsonDict, list[str]]:
    """Recompute the plan, check the digest and blockers, then commit (direct or PR)."""
    try:
        with _core_errors(req.action):
            result = _call(root, req, dry_run=False, environ=environ)
    finally:
        if state is not None:
            state.checks.clear()
    full = result.to_json()
    if req.action not in ("init", "update", "config_commit"):
        return {"action": req.action, **full, "warnings": list(result.warnings)}, list(
            result.warnings
        )
    warnings = list(result.warnings)
    data = {"action": req.action, **{k: full.get(k) for k in APPLY_FIELDS}, "warnings": warnings}
    return data, warnings


def pull(
    root: Path, state: FactoryState | None = None, *, digest: str
) -> tuple[JsonDict, list[str]]:
    """``factory config pull``: fast-forward the local base to the remote one."""
    from aifactory.config.commit import pull_config

    with _core_errors():
        result = pull_config(root, expect=digest)
    if state is not None:
        state.checks.clear()
    return result.to_json(), list(result.warnings)


def pull_plan(root: Path) -> tuple[JsonDict, list[str]]:
    from aifactory.config.commit import plan_pull_config

    with _core_errors():
        return plan_pull_config(root), []


def items(
    root: Path, *, base: str | None = None, environ: Mapping[str, str] | None = None
) -> JsonDict:
    """The CLI item states, without writing its optional cache."""
    from aifactory.library.state import repo_items

    with _core_errors():
        return repo_items(root, base=base, environ=environ, save_cache=False)


def workflow_overrides(root: Path) -> list[JsonDict]:
    """Steps of the working tree's workflows that override harness, model or thinking.

    Read-only, for the roster editor. A configuration or workflow that does not load gives
    no rows (``factory check`` reports it).
    """
    import yaml

    from aifactory.config import ConfigError
    from aifactory.config.loader import load_worktree_config
    from aifactory.workflow.model import RoleStep, WorkflowError, walk
    from aifactory.workflow.parse import parse_workflow

    try:
        cfg = load_worktree_config(root)
    except (ConfigError, OSError, yaml.YAMLError):
        return []
    rows: list[JsonDict] = []
    for name in sorted(cfg.workflows):
        try:
            workflow = parse_workflow(cfg.workflows[name], cfg.roles)
        except WorkflowError:
            continue
        for step in walk(workflow.steps):
            if not isinstance(step, RoleStep):
                continue
            if step.harness is None and step.model is None and step.thinking is None:
                continue
            rows.append(
                {
                    "workflow": name,
                    "step": step.name,
                    "agent": step.role.agent,
                    "harness": step.harness,
                    "model": step.model,
                    "thinking": step.thinking,
                }
            )
    return rows


def roster(root: Path) -> JsonDict:
    """Read bindings and backlog usage without sending editable file contents.

    Also the presets and thinking levels the editor offers and the step overrides of the
    workflows (``workflow_overrides``).
    """
    from aifactory.config.roster import PRESETS
    from aifactory.harness.override import THINKING_LEVELS
    from aifactory.library.config_edit import _base_tasks, read_state

    with _core_errors():
        state = read_state(root, "worktree")
        counts: dict[str, int] = {}
        for _, workflow in _base_tasks(state):
            if isinstance(workflow, str):
                counts[workflow] = counts.get(workflow, 0) + 1
        return {
            "agents": state.roster,
            "workflow_tasks": counts,
            "presets": {name: dict(values) for name, values in PRESETS.items()},
            "thinking_levels": list(THINKING_LEVELS),
            "workflow_overrides": workflow_overrides(root),
        }


ROSTER_KEYS = ("preset", "agent", "harness", "model", "thinking", "dry_run")


@dataclass(frozen=True)
class RosterChange:
    """A validated body of ``POST factory/roster``."""

    preset: str | None = None
    agent: str | None = None
    harness: str | None = None
    model: str | None = None
    thinking: str | None = None
    dry_run: bool = False


def parse_roster_body(body: Mapping[str, Any]) -> RosterChange:
    """The body of ``POST factory/roster``; ``UsageError`` for a bad one."""
    _keys(body, ROSTER_KEYS, "keys")
    dry_run = body.get("dry_run", False)
    if not isinstance(dry_run, bool):
        raise UsageError("dry_run must be a boolean")
    values = {k: _opt_str(body.get(k), k) for k in ROSTER_KEYS if k != "dry_run"}
    return RosterChange(dry_run=dry_run, **values)


def roster_change(root: Path, change: RosterChange, state: FactoryState | None = None) -> JsonDict:
    """``factory config roster set``: preview (``dry_run``) or write ``.factory/agents.yaml``.

    Writes only the working tree; runs use the change once the configuration is committed.
    An invalid change is ``invalid_config`` (HTTP 422).
    """
    from aifactory.config.roster import roster as edit_roster

    try:
        with _core_errors():
            result = edit_roster(
                root,
                change=True,
                preset=change.preset,
                agent=change.agent,
                harness=change.harness,
                model=change.model,
                thinking=change.thinking,
                dry_run=change.dry_run,
            )
    finally:
        if state is not None and not change.dry_run:
            state.checks.clear()
    return {k: v for k, v in result.items() if k != "path"}


def item_diff(root: Path, kind: str, name: str, environ: Mapping[str, str]) -> JsonDict:
    from aifactory.library.config_transfer import diff_item

    with _core_errors():
        return diff_item(root, kind, name, environ)
