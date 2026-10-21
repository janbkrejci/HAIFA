"""Read-only dashboard inventory. Never consulted by runtime item resolution."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, cast

from aifactory.library.load import check_repo_item, repo_path
from aifactory.library.model import ITEM_TYPES, MAX_ITEM_BYTES, MAX_ITEM_FILES, ItemType
from aifactory.web import factory
from aifactory.web.backlog import UsageError
from aifactory.web.factory import Failure
from aifactory.web.registry import Registry


def rules_body(body: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    if set(body) != {"repo", "rules"} or not isinstance(body["repo"], str):
        raise UsageError("expected repo and rules")
    rules = body["rules"]
    if not isinstance(rules, list) or len(rules) > 1000:
        raise UsageError("rules must be a list of at most 1000 rules")
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {"type", "mode", "value"}:
            raise UsageError("rule requires type, mode and value")
        if rule["type"] not in (*ITEM_TYPES, "*") or rule["mode"] not in (
            "item",
            "prefix",
            "directory",
        ):
            raise UsageError("invalid rule type or mode")
        value = rule["value"]
        if not isinstance(value, str) or not value or "\\" in value:
            raise UsageError("rule value must be a non-empty POSIX path or name prefix")
        if rule["mode"] != "prefix" and (
            PurePosixPath(value).is_absolute()
            or ".." in value.split("/")
            or str(PurePosixPath(value)) != value
        ):
            raise UsageError("rule path must be normalized and repository-relative")
    return body["repo"], rules


def matches(row: dict[str, Any], rule: dict[str, Any]) -> bool:
    if rule["type"] not in ("*", row["type"]):
        return False
    value = rule["value"]
    if rule["mode"] == "prefix":
        return bool(row["name"].startswith(value))
    if rule["mode"] == "item":
        return bool(row["path"] == value)
    return bool(row["path"] == value or row["path"].startswith(value + "/"))


def scan(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir():
        raise OSError(f"Repository is unavailable: {root}")
    found: dict[tuple[str, str], dict[str, Any]] = {}

    def add(kind: str, name: str, path: Path) -> None:
        if not path.resolve().is_relative_to(root.resolve()):
            return
        rel = path.relative_to(root).as_posix()
        found[(kind, rel)] = {
            "type": kind,
            "name": name,
            "path": rel,
            "movable": rel == repo_path(cast(ItemType, kind), name),
        }

    for kind, folder in (
        ("workflow", ".factory/workflows"),
        ("agent", ".factory/prompts"),
        ("extension", ".factory/extensions"),
    ):
        base = root / folder
        if base.is_dir():
            for path in sorted(base.iterdir()):
                if kind == "workflow" and path.is_file() and path.suffix in (".yaml", ".yml"):
                    add(kind, path.stem, path)
                elif kind != "workflow" and path.is_dir():
                    add(kind, path.name, path)
    canonical = root / ".claude/skills"
    for folder in (".claude/skills", ".agents/skills", ".codex/skills", ".pi/skills"):
        base = root / folder
        if base.is_dir():
            for skill in sorted(base.rglob("SKILL.md")):
                relative = skill.parent.relative_to(base)
                if folder == ".agents/skills" and (canonical / relative / "SKILL.md").is_file():
                    continue
                add("skill", relative.as_posix(), skill.parent)
    for folder in (".claude/agents", ".codex/agents", ".pi/agents", ".agents/agents"):
        base = root / folder
        if base.is_dir():
            for path in sorted(base.rglob("*")):
                if path.is_file() and path.suffix in (".md", ".toml", ".yaml", ".yml"):
                    add("agent", path.relative_to(base).with_suffix("").as_posix(), path)
    return list(found.values())


def inventory(registry: Registry) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    repos: list[dict[str, Any]] = []
    for entry in registry.snapshot()[0].repos:
        rules = registry.library_rules(entry.id)
        repos.append({"id": entry.id, "name": entry.name, "rules": rules})
        try:
            if (Path(entry.path) / ".factory/config.yaml").is_file():
                try:
                    factory.items(Path(entry.path))
                except Failure as exc:
                    errors.append(
                        {"repo": entry.id, "repo_name": entry.name, "message": exc.message}
                    )
            for row in scan(Path(entry.path)):
                rows.append(
                    {
                        **row,
                        "repo": entry.id,
                        "repo_name": entry.name,
                        "ignored": any(matches(row, r) for r in rules),
                    }
                )
        except OSError as exc:
            errors.append({"repo": entry.id, "repo_name": entry.name, "message": str(exc)})
    return {"items": rows, "repos": repos, "errors": errors}


def detail(registry: Registry, body: dict[str, Any]) -> dict[str, Any]:
    if set(body) != {"repo", "type", "path"} or not all(isinstance(v, str) for v in body.values()):
        raise UsageError("expected repo, type and path")
    entry = registry.snapshot()[0].by_id(body["repo"])
    if entry is None:
        raise Failure("unknown_repo", "repository is not registered", 404)
    root = Path(entry.path)
    row = next(
        (r for r in scan(root) if r["type"] == body["type"] and r["path"] == body["path"]), None
    )
    if row is None:
        raise Failure("unknown_item", "item is no longer available", 404)
    path = root / row["path"]
    paths = sorted(path.rglob("*")) if path.is_dir() else [path]
    files: list[dict[str, Any]] = []
    size = 0
    for file in paths:
        if not file.is_file() or not file.resolve().is_relative_to(root.resolve()):
            continue
        size += file.stat().st_size
        if len(files) >= MAX_ITEM_FILES or size > MAX_ITEM_BYTES:
            raise Failure("invalid_item", "item exceeds preview limits", 409)
        data = file.read_bytes()
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            content = None
        files.append(
            {
                "path": file.relative_to(root).as_posix(),
                "content": content,
                "binary": content is None,
            }
        )
    movable = False
    if row["movable"]:
        own, issues = check_repo_item(root, row["type"], row["name"])
        movable = own is not None and not issues
    return {**row, "movable": movable, "files": files, "absolute_path": str(path)}
