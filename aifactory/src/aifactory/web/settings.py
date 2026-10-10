"""The dashboard's Settings screen and the uncommitted-config warning (D4).

``settings_view`` reads ``.factory/config.yaml`` (shared, committed) and
``.factory/local.yaml`` (machine-local, never committed) from the main checkout on disk.
``save_settings`` merges the sent keys into the existing YAML mapping (other keys such as
``levels``, ``remote`` or ``azure`` stay), validates the result with ``ProjectSettings`` and
``LocalSettings`` and writes it atomically. ``local`` has only ``trace_db``: the dashboard
port is in the registry (D22), ``local.port`` is ``invalid_value`` and an old ``port``
line in ``local.yaml`` is kept as it is and reported as ``local_port_ignored``. When any
value of any section is invalid, nothing is written (``SettingsError`` with one issue per
field). Nothing is ever staged or committed; ``local.yaml`` is added to ``info/exclude``
unless git already ignores it.

Known limitation: the files are rewritten with PyYAML, so comments in them are lost.

``config_status`` is ``factory config status`` (``config_changes``): shared config in the
working tree that differs from the ``base`` commit.
"""

from __future__ import annotations

import os
import tempfile
import typing
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from aifactory.backlog import container_detail_json, load_backlog
from aifactory.config import (
    ConfigError,
    ConfigIssue,
    LocalSettings,
    ProjectSettings,
    change_warnings,
    config_changes,
    resolve_commit,
    worktree_base,
)
from aifactory.config.settings import (
    CONFIG_FILE,
    LOCAL_KEYS,
    _relative,
    check_repo_dir,
    local_port_warning,
    parse_mapping,
    parse_project_settings,
    validation_issues,
)
from aifactory.config.source import LOCAL_FILE, git
from aifactory.run import gitops

JsonDict = dict[str, Any]

SHARED_FIELDS = (
    "workdir",
    "backlog_dir",
    "specs_dir",
    "docs_dir",
    "worktrees_dir",
    "base",
    "git_provider",
    "merge_strategy",
    "protected_files",
    "max_parallel_runs",
)
LOCAL_FIELDS = ("trace_db",)
_SECTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "shared": (CONFIG_FILE, SHARED_FIELDS),
    "local": (LOCAL_FILE, LOCAL_FIELDS),
}


class UsageError(Exception):
    """A request body the settings API does not understand (``usage_error``)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class SettingsError(Exception):
    """Settings that fail validation; nothing was written."""

    def __init__(self, code: str, message: str, issues: list[JsonDict]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.issues = issues


def config_status(root: Path) -> tuple[JsonDict | None, list[str]]:
    """``factory config status`` (D4): shared config not committed to base."""
    try:
        base = worktree_base(root)
        sha = resolve_commit(root, base)
        changes = config_changes(root, sha)
    except ConfigError as exc:
        return None, [f"config status: {exc}"]
    data: JsonDict = {
        "base": base,
        "commit": sha,
        "clean": not changes,
        "changes": [c.to_dict() for c in changes],
    }
    return data, change_warnings(changes, base, sha)


def _options(name: str) -> list[str]:
    return list(typing.get_args(ProjectSettings.model_fields[name].annotation))


def _read(root: Path, rel: str) -> str | None:
    path = root / rel
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _issue_dicts(issues: list[ConfigIssue]) -> list[JsonDict]:
    return [{"path": i.path, "message": i.message} for i in issues]


def _shared_form(settings: ProjectSettings) -> JsonDict:
    data = {name: getattr(settings, name) for name in SHARED_FIELDS}
    data["protected_files"] = list(settings.protected_files)
    return data


def _raw_shared(raw: JsonDict | None) -> JsonDict:
    """Form values of an invalid ``config.yaml``: defaults overlaid with the raw keys."""
    data = _shared_form(ProjectSettings())
    for name in SHARED_FIELDS:
        if raw is None or name not in raw:
            continue
        value = raw[name]
        if name == "protected_files" and isinstance(value, list):
            value = [str(item) for item in value]
        elif value is not None and not isinstance(value, str | int | float | bool):
            value = str(value)
        data[name] = value
    return data


def _without_port(data: JsonDict) -> JsonDict:
    """``local.yaml`` without the old ``port`` key (the dashboard port is in the registry)."""
    return {key: value for key, value in data.items() if key != "port"}


def _local_form(root: Path) -> tuple[JsonDict, list[JsonDict], list[str]]:
    issues: list[ConfigIssue] = []
    warnings: list[str] = []
    raw = parse_mapping(_read(root, LOCAL_FILE), LOCAL_FILE, issues)
    if raw is not None and "port" in raw:
        raw = _without_port(raw)
        warnings.append(local_port_warning())
    if raw is not None:
        try:
            settings = LocalSettings.model_validate(raw)
            return {"trace_db": settings.trace_db}, [], warnings
        except ValidationError as exc:
            issues.extend(validation_issues(exc, LOCAL_FILE))
    default = LocalSettings()
    data: JsonDict = {"trace_db": default.trace_db}
    for name in LOCAL_FIELDS:
        if raw is not None and name in raw:
            value = raw[name]
            data[name] = value if isinstance(value, str | int) else str(value)
    return data, _issue_dicts(issues), warnings


def _view(root: Path) -> tuple[JsonDict, list[str]]:
    issues: list[ConfigIssue] = []
    text = _read(root, CONFIG_FILE)
    settings = parse_project_settings(text, CONFIG_FILE, issues)
    if settings is not None:
        shared = _shared_form(settings)
    else:
        shared = _raw_shared(parse_mapping(text, CONFIG_FILE, []))
    local, local_issues, local_warnings = _local_form(root)
    status, warnings = config_status(root)
    warnings = [*local_warnings, *warnings]
    projects: list[JsonDict] = []
    if settings is not None:
        backlog = load_backlog(root, settings)
        projects = [
            container_detail_json(backlog, project)
            for project in backlog.containers
            if project.id is not None
        ]
    data: JsonDict = {
        "projects": projects,
        "repository": str(root),
        "shared": shared,
        "local": local,
        "files": {"shared": CONFIG_FILE, "local": LOCAL_FILE},
        "options": {
            "git_provider": _options("git_provider"),
            "merge_strategy": _options("merge_strategy"),
        },
        "shared_issues": _issue_dicts(issues),
        "local_issues": local_issues,
        "status": status,
    }
    return data, warnings


def settings_view(repo: Path) -> tuple[JsonDict, list[str]]:
    """Shared and local settings of the main checkout for the form, plus config status."""
    return _view(gitops.main_root(repo))


def _parse_body(body: JsonDict) -> dict[str, JsonDict]:
    unknown = [key for key in body if key not in _SECTIONS]
    if unknown:
        raise UsageError(
            f"unknown key(s) {', '.join(sorted(unknown))}; allowed: {', '.join(_SECTIONS)}"
        )
    sections: dict[str, JsonDict] = {}
    for name, (_, allowed) in _SECTIONS.items():
        if name not in body:
            continue
        section = body[name]
        if not isinstance(section, dict):
            raise UsageError(f"'{name}' must be an object")
        if name == "local" and "port" in section:
            raise SettingsError(
                "invalid_value",
                "invalid settings: port",
                [
                    _issue(
                        LOCAL_FILE,
                        "port",
                        f"the dashboard port is in the registry, not in {LOCAL_FILE}",
                    )
                ],
            )
        extra = [key for key in section if key not in allowed]
        if extra:
            raise UsageError(
                f"unknown {name} setting(s) {', '.join(sorted(extra))}; "
                f"allowed: {', '.join(allowed)}"
            )
        if section:
            sections[name] = section
    return sections


def _issue(rel: str, field: str | None, message: str) -> JsonDict:
    return {"code": "invalid_value", "message": message, "path": rel, "id": field}


def _merge(root: Path, rel: str, changes: JsonDict, issues: list[JsonDict]) -> JsonDict | None:
    """The file's mapping with ``changes`` applied (``None`` removes a key)."""
    found: list[ConfigIssue] = []
    current = parse_mapping(_read(root, rel), rel, found)
    if current is None:
        issues.extend(_issue(rel, None, f"{i.message}; fix the file by hand") for i in found)
        return None
    merged = dict(current)
    for key, value in changes.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def _model_issues(
    model: type[BaseModel], data: JsonDict, rel: str, default_field: str
) -> list[JsonDict]:
    try:
        model.model_validate(data)
    except ValidationError as exc:
        out = []
        for err in exc.errors():
            loc = err["loc"]
            field = str(loc[0]) if loc else default_field
            message = str(err["msg"]).removeprefix("Value error, ")
            out.append(_issue(rel, field, message))
        return out
    return []


def _protected_files(value: Any, rel: str, issues: list[JsonDict]) -> Any:
    """Strip and check ``protected_files`` entries (the model does not check them)."""
    if not isinstance(value, list):
        return value  # the model reports the wrong type
    cleaned: list[Any] = []
    for item in value:
        if not isinstance(item, str):
            cleaned.append(item)
            continue
        try:
            cleaned.append(_relative(item))
        except ValueError as exc:
            issues.append(_issue(rel, "protected_files", str(exc)))
    return cleaned


def _write_atomic(path: Path, data: JsonDict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _git_ok(root: Path, *args: str) -> bool:
    try:
        git(root, *args)
    except ConfigError:
        return False
    return True


def _keep_local_out_of_git(root: Path) -> list[str]:
    """Make sure ``local.yaml`` is ignored; warn when it is tracked. Never stages anything."""
    if not _git_ok(root, "check-ignore", "-q", LOCAL_FILE):
        gitops.ensure_excluded(root, [LOCAL_FILE])
    if _git_ok(root, "ls-files", "--error-unmatch", LOCAL_FILE):
        return [f"{LOCAL_FILE} is tracked by git; remove it with git rm --cached"]
    return []


def save_settings(repo: Path, body: JsonDict) -> tuple[JsonDict, list[str]]:
    """Validate and write the sent settings; all or nothing across both files."""
    sections = _parse_body(body)
    root = gitops.main_root(repo)
    issues: list[JsonDict] = []
    merged: dict[str, JsonDict] = {}

    shared = sections.get("shared")
    if shared is not None:
        data = _merge(root, CONFIG_FILE, shared, issues)
        if data is not None:
            if "protected_files" in data:
                data["protected_files"] = _protected_files(
                    data["protected_files"], CONFIG_FILE, issues
                )
            for key in LOCAL_KEYS:
                if key in data:
                    issues.append(
                        _issue(
                            CONFIG_FILE, key, f"'{key}' is machine-local; put it in {LOCAL_FILE}"
                        )
                    )
            issues.extend(_model_issues(ProjectSettings, data, CONFIG_FILE, "git_provider"))
            for key in ("workdir", "specs_dir", "docs_dir"):
                if key in data:
                    try:
                        check_repo_dir(root, data[key])
                    except ValueError as exc:
                        issues.append(_issue(CONFIG_FILE, key, str(exc)))
            merged["shared"] = data

    local = sections.get("local")
    if local is not None:
        data = _merge(root, LOCAL_FILE, local, issues)
        if data is not None:
            # an old port line stays in the file untouched; it is not validated
            issues.extend(_model_issues(LocalSettings, _without_port(data), LOCAL_FILE, "trace_db"))
            merged["local"] = data

    if issues:
        fields = sorted({str(i["id"]) for i in issues if i["id"]})
        detail = f": {', '.join(fields)}" if fields else ""
        raise SettingsError("invalid_value", f"invalid settings{detail}", issues)

    saved: list[str] = []
    extra: list[str] = []
    if "shared" in merged:
        _write_atomic(root / CONFIG_FILE, merged["shared"])
        saved.append("shared")
    if "local" in merged:
        _write_atomic(root / LOCAL_FILE, merged["local"])
        saved.append("local")
        extra = _keep_local_out_of_git(root)
    data, warnings = _view(root)
    data["saved"] = saved
    return data, extra + warnings
