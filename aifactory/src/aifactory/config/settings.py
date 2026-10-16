"""``.factory/config.yaml`` (shared, committed) and ``.factory/local.yaml`` (machine-local)."""

from __future__ import annotations

import shlex
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from aifactory import yamlload
from aifactory.config.errors import ConfigError, ConfigIssue
from aifactory.config.source import LOCAL_FILE

CONFIG_FILE = ".factory/config.yaml"
# keys that belong to local.yaml; named explicitly when they show up in config.yaml
LOCAL_KEYS = ("trace_db", "database_url")
# warning code: an old local.yaml still sets the dashboard port (D22)
LOCAL_PORT_IGNORED = "local_port_ignored"


def _relative(value: str, *, allow_dot: bool = True) -> str:
    text = value.strip()
    if not text:
        raise ValueError("must not be empty")
    if PurePosixPath(text).is_absolute() or PureWindowsPath(text).drive or "\\" in text:
        raise ValueError(f"must be a path relative to the repository, got {value!r}")
    if ".." in PurePosixPath(text).parts:
        raise ValueError(f"must stay inside the repository, got {value!r}")
    if not allow_dot and PurePosixPath(text) == PurePosixPath("."):
        raise ValueError("must name a directory inside the repository")
    return text


OBSOLETE_KEYS = frozenset({"test_command", "backlog_dir", "backlog_dirs", "specs_dir", "docs_dir"})
"""``test_command``: a tester agent chooses the checks of every run (3.0).
``backlog_dir``, ``backlog_dirs``, ``specs_dir``, ``docs_dir``: replaced by ``docs_root``."""

DEFAULT_DOCS_ROOT = "factory"
"""The root of the factory documents when ``docs_root`` is not set."""


def normalize_dir(text: str) -> str:
    """A relative directory without ``./`` prefixes and trailing slashes; ``.`` stays."""
    value = text.strip()
    while value.startswith("./"):
        value = value[2:]
    value = value.rstrip("/")
    return value or "."


def split_command(value: object) -> tuple[str, ...]:
    """A command as argv: a string is split like a shell, a list must hold strings.

    Raises ``ValueError`` when the value has another type, cannot be split, is
    empty, or has an empty part.
    """
    if isinstance(value, str):
        try:
            parts = tuple(shlex.split(value))
        except ValueError as exc:
            raise ValueError(f"cannot split {value!r}: {exc}") from exc
    elif isinstance(value, (list, tuple)) and all(isinstance(part, str) for part in value):
        parts = tuple(value)
    else:
        raise ValueError("must be a string or a list of strings")
    if not parts or any(not part.strip() for part in parts):
        raise ValueError("must be a non-empty list of non-empty strings")
    return parts


def check_relative_dir(value: object) -> str:
    """A directory inside the repository: a non-empty relative path without ``..``.

    Returns the stripped path; raises ``ValueError`` otherwise (also for a non-string).
    """
    if not isinstance(value, str):
        raise ValueError(f"must be a path relative to the repository, got {value!r}")
    return _relative(value)


def check_repo_dir(root: Path, value: object) -> str:
    """Validate a repository-relative directory, including existing symlink ancestors."""
    text = check_relative_dir(value)
    path = (root / text).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("directory must stay inside the repository")
    if path.exists() and not path.is_dir():
        raise ValueError("path must be a directory")
    return text


def check_timeout(value: object) -> int:
    """A time limit in whole seconds: an int greater than 0 (not a bool).

    Raises ``ValueError`` otherwise.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("must be a whole number of seconds greater than 0")
    return value


class AzureSettings(BaseModel):
    """``azure:`` section of ``.factory/config.yaml`` (used with ``git_provider: azure``).

    ``organization`` is a name (``contoso``) or a full URL
    (``https://dev.azure.com/contoso``).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    organization: str = Field(description="Azure DevOps organization name or full URL.")
    project: str = Field(description="Azure DevOps project name.")
    repository: str = Field(description="Azure DevOps repository name.")

    @field_validator("organization", "project", "repository")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must not be empty")
        return text

    @property
    def organization_url(self) -> str:
        if "://" in self.organization:
            return self.organization.rstrip("/")
        return f"https://dev.azure.com/{self.organization}"


class GeneratedOutput(BaseModel):
    """One entry of ``generated:``: a build output kept in git and the command that builds it.

    ``path`` is a file or directory relative to the repository (a directory
    covers its whole subtree); ``command`` runs from the repository root. A
    ``factory task resolve`` whose rebase leaves a conflict inside ``path``
    does not give that file to the agent: code rebuilds the output with
    ``command`` (step ``rebuild``) and commits the result.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(description="Generated file or directory relative to the repository.")
    command: tuple[str, ...] = Field(
        description=(
            "Command run from the repository root to rebuild this output after a resolve conflict."
        )
    )
    timeout: int = Field(
        default=600, gt=0, strict=True, description="Rebuild time limit in positive whole seconds."
    )

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        text = _relative(value, allow_dot=False)
        while text.startswith("./"):
            text = text[2:]
        return text

    @field_validator("command", mode="before")
    @classmethod
    def _command(cls, value: Any) -> Any:
        return split_command(value)


class ProjectSettings(BaseModel):
    """Shared project settings from ``.factory/config.yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _obsolete(cls, value: Any) -> Any:
        """Keys older configs carry and nothing reads any more; dropped, not refused."""
        if isinstance(value, dict) and OBSOLETE_KEYS & value.keys():
            value = {k: v for k, v in value.items() if k not in OBSOLETE_KEYS}
        return value

    workdir: str = Field(default=".", description="Working directory relative to the repository.")
    docs_root: str = Field(
        default=DEFAULT_DOCS_ROOT,
        description=(
            "Root of the factory documents: backlog/, specs/ and docs/ under it, each "
            "structured project/step/task."
        ),
    )
    levels: tuple[str, ...] = Field(
        default=("project", "step", "task"),
        description="Ordered backlog hierarchy; the last level contains tasks.",
    )
    worktrees_dir: str = Field(
        default=".factory/worktrees",
        description="Directory for isolated task worktrees, relative to the repository.",
    )
    base: str = Field(
        default="main",
        description="Base branch whose committed configuration and backlog runs read.",
    )
    remote: str = Field(
        default="origin", description="Git remote used for publishing and synchronizing base."
    )
    git_provider: Literal["local", "github", "azure"] = Field(
        default="local",
        description="Hosting provider: local (no PR hosting), github (gh), or azure (az).",
    )
    merge_strategy: Literal["squash", "merge"] = Field(
        default="squash", description="Strategy for merging approved task pull requests."
    )
    base_changes: Literal["direct", "pr"] = Field(
        default="direct",
        description=(
            "How factory changes base (install, configuration, library items, backlog, "
            "uninstall): direct commits pushed to base, or pr, one pull request per change "
            "for a base that takes changes only through pull requests."
        ),
    )
    base_pr_merge: Literal["manual", "auto"] = Field(
        default="manual",
        description=(
            "Pull requests of factory's own base changes: manual leaves them to a reviewer; "
            "auto approves them where the hosting lets the author (Azure DevOps), merges "
            "them at once (GitHub with --admin when the branch protection requires it) and "
            "fast-forwards the local base."
        ),
    )
    github_approver: str | None = Field(
        default=None,
        description=(
            "GitHub login that sends the approve review when a task PR is approved "
            "(git_provider github). It must be another account than the PR author, "
            "logged in to gh on the machine (gh auth login). Unset: no review is sent."
        ),
    )
    test_timeout: int | None = Field(
        default=None,
        gt=0,
        strict=True,
        description=(
            "Shared time limit in positive whole seconds of the checks a test step runs; "
            "null means 600. Inherited backlog test_timeout overrides it."
        ),
    )
    test_slots: int = Field(
        default=1,
        ge=1,
        strict=True,
        description=(
            "Maximum simultaneous test steps on this machine; others queue without consuming "
            "their timeout."
        ),
    )
    stacked_prs: bool = Field(
        default=False,
        strict=True,
        description=(
            "A task whose dependencies wait only in open pull requests starts from the "
            "dependency's PR branch; its PR is rebased onto base and merged after theirs."
        ),
    )
    max_parallel_runs: int = Field(
        default=1,
        ge=1,
        strict=True,
        description="Maximum concurrent task runs within one auto-continue chain.",
    )
    protected_files: tuple[str, ...] = Field(
        default=(".factory/",),
        description=(
            "Paths protected from agents unless explicitly allowed by their writes; task "
            "scope still applies."
        ),
    )
    generated: tuple[GeneratedOutput, ...] = Field(
        default=(),
        description="Tracked build outputs and rebuild commands used when resolving conflicts.",
    )
    azure: AzureSettings | None = Field(
        default=None,
        description="Azure DevOps connection details; required when git_provider is azure.",
    )

    @model_validator(mode="after")
    def _provider_section(self) -> ProjectSettings:
        if self.git_provider == "azure" and self.azure is None:
            raise ValueError(
                "git_provider 'azure' needs an 'azure' section with organization, "
                "project and repository"
            )
        return self

    def _under_root(self, name: str) -> str:
        root = self.docs_root
        return name if root == "." else f"{root}/{name}"

    @property
    def backlog_dir(self) -> str:
        """The backlog: ``<docs_root>/backlog``."""
        return self._under_root("backlog")

    @property
    def specs_dir(self) -> str:
        """Task specs: ``<docs_root>/specs/<project>/<step>/<task-id>-<slug>.md``."""
        return self._under_root("specs")

    @property
    def docs_dir(self) -> str:
        """Task documentation: ``<docs_root>/docs/<project>/<step>/<task-id>-<slug>.md``."""
        return self._under_root("docs")

    @property
    def backlog_patterns(self) -> tuple[str, ...]:
        """The backlog root as a one-item tuple (the shape the backlog readers take)."""
        return (self.backlog_dir,)

    @property
    def backlog_label(self) -> str:
        """The backlog root for messages."""
        return self.backlog_dir

    @field_validator("workdir", "worktrees_dir")
    @classmethod
    def _relative_path(cls, value: str) -> str:
        return _relative(value)

    @field_validator("docs_root")
    @classmethod
    def _docs_root(cls, value: str) -> str:
        return normalize_dir(_relative(value))

    @field_validator("levels")
    @classmethod
    def _levels(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        items = tuple(item.strip() for item in value)
        if len(items) < 2:
            raise ValueError("needs at least 2 levels")
        if any(not item for item in items):
            raise ValueError("levels must not be empty")
        if len(set(items)) != len(items):
            raise ValueError("levels must be unique")
        return items

    @field_validator("base", "remote")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must not be empty")
        return text

    @field_validator("github_approver")
    @classmethod
    def _approver(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text or any(ch.isspace() for ch in text):
            raise ValueError("must be a GitHub login")
        return text


DEFAULT_PORT = 4700
"""The dashboard port when the registry sets none."""


class LocalSettings(BaseModel):
    """Machine-local settings from ``.factory/local.yaml`` (never committed)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    trace_db: str = ".factory/trace.db"
    database_url: str | None = None

    @field_validator("trace_db")
    @classmethod
    def _trace_db(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    def trace_db_path(self, root: Path) -> Path:
        """The trace DB as an absolute path (relative paths are from the repo root)."""
        path = Path(self.trace_db).expanduser()
        from aifactory.database import database_path

        local = path if path.is_absolute() else (root / path).resolve()
        return database_path(root, local, self.database_url)


def parse_mapping(text: str | None, label: str, issues: list[ConfigIssue]) -> dict[str, Any] | None:
    """YAML text as a mapping: ``{}`` for missing/empty, None (and an issue) when invalid."""
    if text is None:
        return {}
    try:
        data = yamlload.safe_load(text)
    except yaml.YAMLError as exc:
        issues.append(ConfigIssue(label, f"invalid YAML: {exc}"))
        return None
    if data is None:
        return {}
    if not isinstance(data, dict):
        issues.append(ConfigIssue(label, f"must be a mapping, got {type(data).__name__}"))
        return None
    return data


def validation_issues(exc: ValidationError, label: str) -> list[ConfigIssue]:
    issues = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "<root>"
        issues.append(ConfigIssue(label, f"{loc}: {err['msg']}"))
    return issues


def parse_project_settings(
    text: str | None, label: str, issues: list[ConfigIssue]
) -> ProjectSettings | None:
    """Parse ``config.yaml`` text; problems go to ``issues`` and return None."""
    data = parse_mapping(text, label, issues)
    if data is None:
        return None
    if "port" in data:
        issues.append(
            ConfigIssue(
                label,
                "'port' is the dashboard's; set it in the registry "
                "(factory obs --port, dashboard.yaml)",
            )
        )
    misplaced = [key for key in LOCAL_KEYS if key in data]
    for key in misplaced:
        issues.append(ConfigIssue(label, f"'{key}' is machine-local; put it in {LOCAL_FILE}"))
    if misplaced or "port" in data:
        return None
    try:
        return ProjectSettings.model_validate(data)
    except ValidationError as exc:
        issues.extend(validation_issues(exc, label))
        return None


def local_port_warning() -> str:
    """The warning for an old ``local.yaml`` that still sets ``port``."""
    return (
        f"{LOCAL_PORT_IGNORED}: {LOCAL_FILE}: port is ignored, the dashboard port is in "
        "the registry; delete the port line"
    )


def load_local_checked(root: Path) -> tuple[LocalSettings, list[str]]:
    """Read ``.factory/local.yaml`` from disk, with warnings.

    An old ``port`` key is dropped before validation (the dashboard port lives in
    the registry, D22) and reported as a ``local_port_ignored`` warning.
    """
    path = root / LOCAL_FILE
    label = str(path)
    issues: list[ConfigIssue] = []
    warnings: list[str] = []
    text = path.read_text(encoding="utf-8") if path.is_file() else None
    data = parse_mapping(text, label, issues)
    if data is not None:
        if "port" in data:
            data = {key: value for key, value in data.items() if key != "port"}
            warnings.append(local_port_warning())
        try:
            return LocalSettings.model_validate(data), warnings
        except ValidationError as exc:
            issues.extend(validation_issues(exc, label))
    raise ConfigError(issues)


def load_local(root: Path) -> LocalSettings:
    """Read ``.factory/local.yaml`` from the working tree at ``root`` (only from disk)."""
    return load_local_checked(root)[0]
