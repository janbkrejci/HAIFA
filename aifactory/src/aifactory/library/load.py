"""Read library items from the library layout or from a repo's ``.factory/`` copy.

Library layout (AR14)::

    agents/<name>/{agent.yaml,system.md,user.md}
    workflows/<name>.yaml
    skills/<name>/
    extensions/<name>/

Repo copy: purpose from ``.factory/agents.yaml``, prompts from
``.factory/prompts/<slot>/``, ``.factory/workflows/<name>.yaml``,
``.claude/skills/<name>/`` (copied to ``.agents/skills/<name>/``) and
``.factory/extensions/<name>/``.

Every ``check_*`` function collects all problems at once and never stops at the
first; ``load_*`` raises ``LibraryError`` with all of them.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from aifactory.backlog.frontmatter import FrontmatterError, parse_frontmatter
from aifactory.config.loader import (
    AGENTS_FILE,
    EXTENSIONS_DIR,
    PROMPTS_DIR,
    SKILLS_DIR,
    WORKFLOWS_DIR,
)
from aifactory.engine.role_registry import Issue, load_roles
from aifactory.library.model import (
    ITEM_TYPES,
    MAX_ITEM_BYTES,
    MAX_ITEM_FILES,
    AgentDefaults,
    Item,
    ItemFile,
    ItemType,
    LibraryError,
    check_name,
)
from aifactory.workflow.model import WorkflowError
from aifactory.workflow.parse import parse_workflow

AGENT_KEYS = frozenset({"purpose", "defaults"})
PROMPT_FILES = ("system.md", "user.md")
SKILL_FILE = "SKILL.md"

_LIBRARY_DIRS: dict[str, str] = {
    "agent": "agents",
    "workflow": "workflows",
    "skill": "skills",
    "extension": "extensions",
}
_REPO_DIRS: dict[str, str] = {
    "workflow": WORKFLOWS_DIR,
    "skill": SKILLS_DIR,
    "extension": EXTENSIONS_DIR,
}


def library_path(type: ItemType, name: str) -> str:
    """Where the item lives in the library, relative to the library root."""
    if type == "workflow":
        return f"{_LIBRARY_DIRS[type]}/{name}.yaml"
    return f"{_LIBRARY_DIRS[type]}/{name}"


def repo_path(type: ItemType, name: str) -> str:
    """Where the item lives in a repo, relative to the repo root."""
    if type == "agent":
        return f"{PROMPTS_DIR}/{name}"
    if type == "workflow":
        return f"{WORKFLOWS_DIR}/{name}.yaml"
    return f"{_REPO_DIRS[type]}/{name}"


# ── reading ───────────────────────────────────────────────────────────────────


def _read_file(base: Path, rel: str, issues: list[Issue], missing: str) -> ItemFile | None:
    """One regular file; ``ItemFile.path`` is its base name."""
    path = base / rel
    if path.is_symlink():
        issues.append(Issue("symlink", "symlinks are not allowed", rel))
        return None
    if not path.is_file():
        what = "missing" if not path.exists() else "not a regular file"
        issues.append(Issue(missing, what, rel))
        return None
    try:
        data = path.read_bytes()
        mode = path.lstat().st_mode
    except OSError as error:
        issues.append(Issue(missing, str(error), rel))
        return None
    return ItemFile(path=path.name, executable=bool(mode & stat.S_IXUSR), data=data)


def _check_dir(base: Path, rel: str, issues: list[Issue], missing: str) -> bool:
    path = base / rel
    if path.is_symlink():
        issues.append(Issue("symlink", "symlinks are not allowed", rel))
        return False
    if not path.is_dir():
        what = "missing" if not path.exists() else "not a directory"
        issues.append(Issue(missing, what, rel))
        return False
    return True


def _check_limits(count: int, size: int, rel: str, issues: list[Issue]) -> bool:
    ok = True
    if count > MAX_ITEM_FILES:
        issues.append(
            Issue("too_many_files", f"{count} files, at most {MAX_ITEM_FILES} allowed", rel)
        )
        ok = False
    if size > MAX_ITEM_BYTES:
        issues.append(Issue("too_large", f"{size} bytes, at most {MAX_ITEM_BYTES} allowed", rel))
        ok = False
    return ok


def _read_tree(base: Path, rel: str, issues: list[Issue]) -> tuple[ItemFile, ...] | None:
    """Every file under ``base/rel``; symlinks and special files are reported, never followed."""
    if not _check_dir(base, rel, issues, "missing_item"):
        return None
    root = base / rel
    found: list[tuple[str, Path, bool]] = []
    size = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        for dirname in sorted(dirnames):
            if (current / dirname).is_symlink():
                relpath = (current / dirname).relative_to(root).as_posix()
                issues.append(Issue("symlink", "symlinks are not allowed", f"{rel}/{relpath}"))
        dirnames[:] = sorted(d for d in dirnames if not (current / d).is_symlink())
        for filename in sorted(filenames):
            path = current / filename
            relpath = path.relative_to(root).as_posix()
            try:
                st = path.lstat()
            except OSError as error:
                issues.append(Issue("not_a_file", str(error), f"{rel}/{relpath}"))
                continue
            if stat.S_ISLNK(st.st_mode):
                issues.append(Issue("symlink", "symlinks are not allowed", f"{rel}/{relpath}"))
            elif not stat.S_ISREG(st.st_mode):
                issues.append(Issue("not_a_file", "not a regular file", f"{rel}/{relpath}"))
            else:
                found.append((relpath, path, bool(st.st_mode & stat.S_IXUSR)))
                size += st.st_size
    if not _check_limits(len(found), size, rel, issues):
        return None
    files = []
    for relpath, path, executable in found:
        try:
            files.append(ItemFile(path=relpath, executable=executable, data=path.read_bytes()))
        except OSError as error:
            issues.append(Issue("not_a_file", str(error), f"{rel}/{relpath}"))
    return tuple(sorted(files, key=lambda f: f.path.encode("utf-8")))


def _decode(data: bytes, rel: str, issues: list[Issue]) -> str | None:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        issues.append(Issue("not_utf8", str(error), rel))
        return None


def _yaml(text: str, rel: str, issues: list[Issue]) -> tuple[bool, Any]:
    try:
        return True, yaml.safe_load(text)
    except yaml.YAMLError as error:
        issues.append(Issue("invalid_yaml", str(error), rel))
        return False, None


def _agent_yaml(data: bytes, rel: str, issues: list[Issue]) -> tuple[str, AgentDefaults]:
    """Purpose and defaults from ``agent.yaml``; problems go to ``issues``."""
    defaults = AgentDefaults()
    text = _decode(data, rel, issues)
    if text is None:
        return "", defaults
    ok, raw = _yaml(text, rel, issues)
    if not ok:
        return "", defaults
    if not isinstance(raw, dict):
        issues.append(Issue("not_a_mapping", "agent.yaml must be a mapping", rel))
        return "", defaults
    for key in sorted(str(k) for k in raw if k not in AGENT_KEYS):
        issues.append(Issue("unknown_key", f"unknown key {key!r}", rel))
    purpose = raw.get("purpose")
    if not isinstance(purpose, str) or not purpose.strip():
        issues.append(Issue("missing_purpose", "purpose must be a non-empty string", rel))
        purpose = ""
    raw_defaults = raw.get("defaults")
    if raw_defaults is None:
        return purpose, defaults
    if not isinstance(raw_defaults, dict):
        issues.append(Issue("invalid_defaults", "defaults must be a mapping", rel))
        return purpose, defaults
    try:
        return purpose, AgentDefaults.model_validate(raw_defaults)
    except ValidationError as error:
        for problem in error.errors():
            loc = ".".join(str(part) for part in ("defaults", *problem["loc"]))
            issues.append(Issue("invalid_defaults", f"{loc}: {problem['msg']}", rel))
        return purpose, defaults


def _agent_item(
    name: str,
    purpose: str,
    prompts: list[ItemFile | None],
    rel: str,
    issues: list[Issue],
    defaults: AgentDefaults | None,
    meta: ItemFile | None = None,
) -> Item | None:
    system, user = prompts
    if system is None or user is None:
        return None
    files = (system, user)
    counted = [*files, *([meta] if meta is not None else [])]
    if not _check_limits(len(counted), sum(len(f.data) for f in counted), rel, issues):
        return None
    return Item(type="agent", name=name, files=files, purpose=purpose, defaults=defaults)


def _library_agent(root: Path, name: str, issues: list[Issue]) -> Item | None:
    rel = library_path("agent", name)
    if not _check_dir(root, rel, issues, "missing_item"):
        return None
    meta = _read_file(root, f"{rel}/agent.yaml", issues, "missing_file")
    prompts = [_read_file(root, f"{rel}/{f}", issues, "missing_file") for f in PROMPT_FILES]
    purpose, defaults = "", AgentDefaults()
    if meta is not None:
        purpose, defaults = _agent_yaml(meta.data, f"{rel}/agent.yaml", issues)
    return _agent_item(name, purpose, prompts, rel, issues, defaults, meta)


def _roster_purpose(repo: Path, name: str, issues: list[Issue]) -> str:
    path = repo / AGENTS_FILE
    if path.is_symlink():
        issues.append(Issue("symlink", "symlinks are not allowed", AGENTS_FILE))
        return ""
    try:
        data = path.read_bytes()
    except OSError:
        issues.append(Issue("unknown_agent", f"no {AGENTS_FILE} with agent {name!r}", AGENTS_FILE))
        return ""
    text = _decode(data, AGENTS_FILE, issues)
    if text is None:
        return ""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        issues.append(Issue("unknown_agent", f"invalid YAML: {error}", AGENTS_FILE))
        return ""
    agents = raw.get("agents") if isinstance(raw, dict) else None
    entry = (
        next(
            (a for a in agents or [] if isinstance(a, dict) and a.get("name") == name),
            None,
        )
        if isinstance(agents, list)
        else None
    )
    if entry is None:
        issues.append(Issue("unknown_agent", f"no agent {name!r} in the roster", AGENTS_FILE))
        return ""
    purpose = entry.get("purpose")
    if purpose is None:
        return ""
    if not isinstance(purpose, str):
        issues.append(
            Issue("invalid_purpose", f"agent {name!r}: purpose must be a string", AGENTS_FILE)
        )
        return ""
    return purpose


def _repo_agent(repo: Path, name: str, issues: list[Issue]) -> Item | None:
    rel = repo_path("agent", name)
    purpose = _roster_purpose(repo, name, issues)
    if (repo / rel).is_symlink():
        issues.append(Issue("symlink", "symlinks are not allowed", rel))
        return None
    prompts = [_read_file(repo, f"{rel}/{f}", issues, "missing_file") for f in PROMPT_FILES]
    return _agent_item(name, purpose, prompts, rel, issues, None)


def _single_file(
    base: Path, rel: str, type: ItemType, name: str, issues: list[Issue]
) -> Item | None:
    found = _read_file(base, rel, issues, "missing_item")
    if found is None or not _check_limits(1, len(found.data), rel, issues):
        return None
    return Item(type=type, name=name, files=(found,))


def _tree_item(base: Path, rel: str, type: ItemType, name: str, issues: list[Issue]) -> Item | None:
    files = _read_tree(base, rel, issues)
    if files is None:
        return None
    return Item(type=type, name=name, files=files)


def _check(base: Path, type: str, name: str, *, repo: bool) -> tuple[Item | None, list[Issue]]:
    issues: list[Issue] = []
    if type not in ITEM_TYPES:
        issues.append(Issue("invalid_type", f"unknown item type {type!r}", ""))
        return None, issues
    kind: ItemType = type
    if not check_name(name):
        issues.append(
            Issue("invalid_name", f"invalid name {name!r}: [a-z0-9][a-z0-9-]{{0,47}}", name)
        )
        return None, issues
    rel = repo_path(kind, name) if repo else library_path(kind, name)
    item: Item | None
    if kind == "agent":
        item = _repo_agent(base, name, issues) if repo else _library_agent(base, name, issues)
    elif kind == "workflow":
        item = _single_file(base, rel, kind, name, issues)
    else:
        item = _tree_item(base, rel, kind, name, issues)
    if item is not None:
        issues.extend(validate_item(item, rel))
    return item, issues


def check_library_item(root: Path, type: str, name: str) -> tuple[Item | None, list[Issue]]:
    """Read an item from the library at ``root``; return it with every problem found."""
    return _check(root, type, name, repo=False)


def check_repo_item(repo: Path, type: str, name: str) -> tuple[Item | None, list[Issue]]:
    """Read an item from the ``.factory/`` copy in ``repo``; return it with every problem."""
    return _check(repo, type, name, repo=True)


def load_library_item(root: Path, type: str, name: str) -> Item:
    """Read a valid item from the library; raise ``LibraryError`` with every problem."""
    item, issues = check_library_item(root, type, name)
    if issues or item is None:
        raise LibraryError(issues)
    return item


def load_repo_item(repo: Path, type: str, name: str) -> Item:
    """Read a valid item from a repo's ``.factory/``; raise ``LibraryError`` with every problem."""
    item, issues = check_repo_item(repo, type, name)
    if issues or item is None:
        raise LibraryError(issues)
    return item


# ── content rules ─────────────────────────────────────────────────────────────


def _validate_workflow(item: Item, rel: str) -> list[Issue]:
    issues: list[Issue] = []
    text = _decode(b"".join(f.data for f in item.files), rel, issues)
    if text is None:
        return issues
    ok, raw = _yaml(text, rel, issues)
    if not ok:
        return issues
    if not isinstance(raw, dict):
        issues.append(Issue("not_a_mapping", "a workflow must be a mapping", rel))
        return issues
    try:
        parse_workflow(raw, load_roles())
    except WorkflowError as error:
        issues.extend(Issue(i.code, i.message, f"{rel}:{i.path}") for i in error.issues)
    return issues


def _validate_skill(item: Item, rel: str) -> list[Issue]:
    issues: list[Issue] = []
    path = f"{rel}/{SKILL_FILE}"
    found = item.file(SKILL_FILE)
    if found is None:
        issues.append(Issue("missing_skill_md", f"a skill needs {SKILL_FILE}", path))
        return issues
    text = _decode(found.data, path, issues)
    if text is None:
        return issues
    try:
        header, _ = parse_frontmatter(text)
    except FrontmatterError as error:
        issues.append(Issue("invalid_front_matter", str(error), path))
        return issues
    if header.get("name") != item.name:
        issues.append(
            Issue(
                "name_mismatch",
                f"name {header.get('name')!r} must equal the folder name {item.name!r}",
                path,
            )
        )
    description = header.get("description")
    if not isinstance(description, str) or not description.strip():
        issues.append(Issue("missing_description", "description must be a non-empty string", path))
    return issues


def validate_item(item: Item, location: str | None = None) -> list[Issue]:
    """Content rules for a loaded item.

    ``location`` prefixes issue paths; by default the item's library layout path.
    """
    rel = location if location is not None else library_path(item.type, item.name)
    if item.type == "workflow":
        return _validate_workflow(item, rel)
    if item.type == "skill":
        return _validate_skill(item, rel)
    if item.type == "extension":
        entry = f"{item.name}.ts"
        if item.file(entry) is None:
            return [Issue("missing_entry", f"an extension needs {entry}", f"{rel}/{entry}")]
    return []
