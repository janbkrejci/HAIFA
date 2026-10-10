"""Read the backlog tree from disk. Nothing here writes a file."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from aifactory.backlog.frontmatter import FrontmatterError, parse_frontmatter
from aifactory.backlog.model import (
    FLAG_KEYS,
    INDEX_FILE,
    INHERITED_KEYS,
    LIST_FIELDS,
    VALID_STATUSES,
    Backlog,
    Container,
    Issue,
    Node,
    Task,
)
from aifactory.backlog.roots import backlog_roots
from aifactory.config import ConfigError, ConfigIssue, ProjectSettings, WorktreeSource
from aifactory.config.settings import (
    CONFIG_FILE,
    check_relative_dir,
    check_timeout,
    parse_project_settings,
)


def load_settings(root: Path) -> ProjectSettings:
    """``.factory/config.yaml`` from the working tree; defaults when the file is missing."""
    source = WorktreeSource(root)
    issues: list[ConfigIssue] = []
    settings = parse_project_settings(
        source.read_text(CONFIG_FILE), source.label(CONFIG_FILE), issues
    )
    if settings is None:
        raise ConfigError(issues)
    return settings


def _string_list(value: object) -> list[str] | None:
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    return None


class _Loader:
    def __init__(self, root: Path, settings: ProjectSettings) -> None:
        self.root = root
        self.settings = settings
        self.levels = settings.levels
        self.issues: list[Issue] = []

    def rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def issue(self, code: str, message: str, path: Path, node_id: str | None = None) -> None:
        self.issues.append(Issue(code, message, self.rel(path), node_id))

    def read_header(self, path: Path) -> tuple[dict[str, object], str] | None:
        try:
            return parse_frontmatter(path.read_text(encoding="utf-8"))
        except FrontmatterError as exc:
            self.issue("invalid_frontmatter", f"{self.rel(path)}: {exc}", path)
        except (OSError, UnicodeDecodeError) as exc:
            self.issue("invalid_frontmatter", f"{self.rel(path)}: cannot read file: {exc}", path)
        return None

    def required_str(
        self, data: dict[str, object], key: str, path: Path, node_id: str | None
    ) -> str | None:
        if key not in data or data[key] is None:
            self.issue("missing_field", f"missing required field '{key}'", path, node_id)
            return None
        value = data[key]
        if not isinstance(value, str) or not value.strip():
            self.issue(
                "invalid_field",
                f"field '{key}' must be a non-empty string, got {value!r}",
                path,
                node_id,
            )
            return None
        return value

    def load_root(self) -> list[Container]:
        roots = backlog_roots(self.root, self.settings)
        if not roots:
            label = self.settings.backlog_label
            self.issue(
                "missing_backlog_dir",
                f"no backlog directory matches '{label}'",
                self.root / self.settings.backlog_patterns[0],
            )
            return []
        result: list[Container] = []
        for backlog_dir in roots:
            result.extend(self.load_backlog_dir(backlog_dir))
        return result

    def load_backlog_dir(self, backlog_dir: str) -> list[Container]:
        backlog_root = self.root / backlog_dir
        if not backlog_root.is_dir():
            self.issue(
                "missing_backlog_dir",
                f"backlog directory '{backlog_dir}' does not exist",
                backlog_root,
            )
            return []
        result: list[Container] = []
        for entry in sorted(backlog_root.iterdir(), key=lambda p: p.name):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                result.append(self.load_container(entry, 0, None))
            elif entry.suffix == ".md" and entry.name != INDEX_FILE:
                self.issue(
                    "misplaced_file",
                    f"markdown file directly in backlog root, expected a "
                    f"'{self.levels[0]}' directory",
                    entry,
                )
        return result

    def load_container(self, directory: Path, depth: int, parent: Container | None) -> Container:
        level = self.levels[depth]
        container = Container(
            id=None, title=None, level=level, path=self.rel(directory), parent=parent
        )
        index = directory / INDEX_FILE
        if not index.is_file():
            self.issue(
                "missing_index",
                f"{level} directory '{self.rel(directory)}' has no {INDEX_FILE}",
                directory,
            )
        else:
            container.index_path = self.rel(index)
            parsed = self.read_header(index)
            if parsed is not None:
                data, body = parsed
                container.body = body
                container.id = self.required_str(data, "id", index, None)
                container.title = self.required_str(data, "title", index, container.id)
                for key, value in data.items():
                    if key in ("id", "title"):
                        continue
                    if key == "writes" and value is not None and _string_list(value) is None:
                        self.issue(
                            "invalid_field",
                            f"field 'writes' must be a list of strings, got {value!r}",
                            index,
                            container.id,
                        )
                        continue
                    if key in FLAG_KEYS and not _flag(value):
                        self.issue("invalid_field", _flag_message(key), index, container.id)
                        continue
                    if key == "test_timeout" and (problem := _timeout_issue(value)) is not None:
                        # Kept: a task inheriting it must fail, not fall back to 600 s.
                        self.issue("invalid_field", problem, index, container.id)
                    if key == "workdir" and parent is not None:
                        self.issue(
                            "invalid_field",
                            "workdir is only allowed on a project",
                            index,
                            container.id,
                        )
                    if (
                        key in (*OUTPUT_DIR_KEYS, "workdir")
                        and (problem := _dir_issue(key, value)) is not None
                    ):
                        # Kept: a task inheriting it must fail, not fall back to the config.
                        self.issue("invalid_field", problem, index, container.id)
                    if key in INHERITED_KEYS:
                        container.defaults[key] = value
                    else:
                        container.extra[key] = value

        task_depth = len(self.levels) - 2
        for entry in sorted(directory.iterdir(), key=lambda p: p.name):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                if depth < task_depth:
                    container.children.append(self.load_container(entry, depth + 1, container))
                else:
                    self.issue(
                        "misplaced_dir",
                        f"directory is deeper than configured levels {list(self.levels)}",
                        entry,
                    )
            elif entry.is_file() and entry.suffix == ".md" and entry.name != INDEX_FILE:
                if depth == task_depth:
                    task = self.load_task(entry, container)
                    if task is not None:
                        container.tasks.append(task)
                else:
                    self.issue(
                        "misplaced_file",
                        f"task file in a '{level}' directory, tasks belong in "
                        f"'{self.levels[task_depth]}' directories",
                        entry,
                    )
        return container

    def load_task(self, path: Path, parent: Container) -> Task | None:
        parsed = self.read_header(path)
        if parsed is None:
            return None
        data, body = parsed
        task_id = self.required_str(data, "id", path, None)
        title = self.required_str(data, "title", path, task_id)
        status: str = ""
        if "status" not in data or data["status"] is None:
            self.issue("missing_field", "missing required field 'status'", path, task_id)
        else:
            raw = data["status"]
            status = raw if isinstance(raw, str) else str(raw)
            if status not in VALID_STATUSES:
                self.issue(
                    "invalid_status",
                    f"invalid status {status!r}, allowed: {', '.join(VALID_STATUSES)}",
                    path,
                    task_id,
                )
        lists: dict[str, list[str]] = {}
        if "workdir" in data:
            self.issue("invalid_field", "workdir is only allowed on a project", path, task_id)
        own = {k: v for k, v in data.items() if k in INHERITED_KEYS}
        for key in FLAG_KEYS:
            if not _flag(own.get(key)):
                self.issue("invalid_field", _flag_message(key), path, task_id)
                own.pop(key)
        if (problem := _timeout_issue(own.get("test_timeout"))) is not None:
            # Kept: running the task must fail, not fall back to an inherited limit.
            self.issue("invalid_field", problem, path, task_id)
        for key in OUTPUT_DIR_KEYS:
            if (problem := _dir_issue(key, own.get(key))) is not None:
                # Kept: running the task must fail, not fall back to another directory.
                self.issue("invalid_field", problem, path, task_id)
        for key in LIST_FIELDS:
            value = data.get(key)
            if value is None:
                lists[key] = []
                continue
            items = _string_list(value)
            if items is None:
                self.issue(
                    "invalid_field",
                    f"field '{key}' must be a list of strings, got {value!r}",
                    path,
                    task_id,
                )
                own.pop(key, None)
                items = []
            lists[key] = items
        if task_id is None:
            return None
        return Task(
            id=task_id,
            title=title or "",
            status=status,
            level=self.levels[-1],
            path=self.rel(path),
            parent=parent,
            own=own,
            depends_on=lists["depends_on"],
            related=lists["related"],
            writes=lists["writes"],
            body=body,
        )


def _flag_message(key: str) -> str:
    return f"field '{key}' must be true or false"


def _timeout_issue(value: object) -> str | None:
    """Why a ``test_timeout`` value is invalid; ``None`` when it is missing or valid."""
    if value is None:
        return None
    try:
        check_timeout(value)
    except ValueError:
        return (
            f"field 'test_timeout' must be a whole number of seconds greater than 0, got {value!r}"
        )
    return None


OUTPUT_DIR_KEYS = ("specs_dir", "docs_dir")


def _dir_issue(key: str, value: object) -> str | None:
    """Why a ``specs_dir``/``docs_dir`` value is invalid; ``None`` when missing or valid."""
    if value is None:
        return None
    try:
        check_relative_dir(value)
    except ValueError as exc:
        return f"field '{key}' must be a directory relative to the repository: {exc}"
    return None


def _flag(value: object) -> bool:
    """A valid flag value (``auto_continue``, ``auto_merge``): missing (``None``) or a bool."""
    return value is None or isinstance(value, bool)


def iter_containers(containers: list[Container]) -> Iterator[Container]:
    for container in containers:
        yield container
        yield from iter_containers(container.children)


def iter_nodes(backlog: Backlog) -> Iterator[Node]:
    """All containers with an id and all tasks, depth first in path order."""

    def walk(container: Container) -> Iterator[Node]:
        if container.id is not None:
            yield container
        for child in container.children:
            yield from walk(child)
        yield from container.tasks

    for container in backlog.containers:
        yield from walk(container)


def iter_tasks(backlog: Backlog) -> Iterator[Task]:
    for node in iter_nodes(backlog):
        if isinstance(node, Task):
            yield node


def load_backlog(root: Path, settings: ProjectSettings | None = None) -> Backlog:
    """Read the backlog tree; in remote mode synchronize its local Markdown mirror.

    Raises ``ConfigError`` when ``settings`` is not given and ``.factory/config.yaml``
    is invalid.
    """
    if settings is None:
        settings = load_settings(root)
    from aifactory.database.backlog import synchronize

    synchronize(root, settings)
    loader = _Loader(root, settings)
    containers = loader.load_root()
    backlog = Backlog(root=root, settings=settings, containers=containers, issues=loader.issues)
    backlog.roots = [r for r in backlog_roots(root, settings) if (root / r).is_dir()]
    for node in iter_nodes(backlog):
        assert node.id is not None
        backlog.by_id.setdefault(node.id, node)
    return backlog
