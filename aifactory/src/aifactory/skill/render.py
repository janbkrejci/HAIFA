"""Fill the packaged skill template (``skill.md``) from the current code."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from importlib import resources
from typing import Any

import yaml

from aifactory import __version__
from aifactory.skill.codes import ERROR_CODES, ISSUE_CODES
from aifactory.skill.commands import format_commands, iter_commands

TEMPLATE = "skill.md"


def _parser(parser: argparse.ArgumentParser | None) -> argparse.ArgumentParser:
    if parser is not None:
        return parser
    from aifactory.cli import build_parser  # lazy: the CLI imports this package

    return build_parser()


def _codes(values: Iterable[str]) -> str:
    return ", ".join(f"`{v}`" for v in values)


def _error_table() -> str:
    rows = sorted(ERROR_CODES.values(), key=lambda c: (c.exit, c.code))
    lines = ["| code | exit | meaning |", "| --- | --- | --- |"]
    lines += [f"| `{c.code}` | {c.exit} | {c.meaning} |" for c in rows]
    return "\n".join(lines)


def _issue_codes() -> str:
    return "\n".join(f"- {group}: {_codes(codes)}" for group, codes in ISSUE_CODES.items())


def _settings_keys() -> str:
    from aifactory.config.settings import AzureSettings, GeneratedOutput, ProjectSettings

    lines = ["| Key | Default | Meaning |", "| --- | --- | --- |"]
    for prefix, model in (
        ("", ProjectSettings),
        ("azure.", AzureSettings),
        ("generated[].", GeneratedOutput),
    ):
        for name, info in model.model_fields.items():
            if not info.description:
                raise RuntimeError(f"missing setting description: {prefix}{name}")
            default = (
                "required"
                if info.is_required()
                else json.dumps(info.get_default(call_default_factory=True))
            )
            lines.append(f"| `{prefix}{name}` | `{default}` | {info.description} |")
    return "\n".join(lines)


def _default_levels() -> str:
    from aifactory.config.settings import ProjectSettings

    levels = ProjectSettings.model_fields["levels"].get_default()
    return "[" + ", ".join(levels) + "]"


def _workflows() -> str:
    folder = resources.files("aifactory") / "defaults" / "workflows"
    items: list[str] = []
    entries = [e for e in folder.iterdir() if e.name.endswith(".yaml")]
    for entry in sorted(entries, key=lambda e: e.name.removesuffix(".yaml")):
        stem = entry.name.removesuffix(".yaml")
        try:
            data = yaml.safe_load(entry.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            data = None
        description = data.get("description") if isinstance(data, dict) else None
        items.append(f"`{stem}` ({description})" if description else f"`{stem}`")
    return "; ".join(items)


def _roles() -> str:
    from aifactory.engine.role_registry import load_roles

    registry = load_roles()
    by_role: dict[str, list[str]] = {}
    for name, role in registry.roles.items():
        by_role.setdefault(role.name, []).append(name)
    parts: list[str] = []
    for name, names in by_role.items():
        aliases = [n for n in names if n != name]
        parts.append(f"`{name}` (= {_codes(aliases)})" if aliases else f"`{name}`")
    return ", ".join(parts)


def _harnesses() -> str:
    from aifactory.harness import ALIASES, HARNESSES

    text = _codes(HARNESSES)
    if ALIASES:
        text += "; aliases " + ", ".join(f"`{a}` = `{c}`" for a, c in ALIASES.items())
    return text


def _test_command_rules() -> str:
    from aifactory.techstack import RULES

    return "\n".join(f"   - {files}: {command}" for files, command in RULES)


def placeholders(parser: argparse.ArgumentParser | None = None) -> dict[str, str]:
    """Every ``{{name}}`` of the template and its generated text."""
    from aifactory.backlog.model import INDEX_FILE, INHERITED_KEYS, LIST_FIELDS, VALID_STATUSES
    from aifactory.backlog.render import STATUS_FILTERS
    from aifactory.backlog.taskfile import FIELD_ORDER, RUNS_HEADING, RUNS_PLACEHOLDER
    from aifactory.engine.role_registry import CODE_ACTIONS
    from aifactory.harness.override import THINKING_LEVELS
    from aifactory.run.queue import SKIP_REASONS, STOP_REASONS

    return {
        "version": __version__,
        "commands": format_commands(iter_commands(_parser(parser))),
        "error_codes": _error_table(),
        "issue_codes": _issue_codes(),
        "statuses": ", ".join(VALID_STATUSES),
        "status_filters": ", ".join(STATUS_FILTERS),
        "inherited_keys": ", ".join(INHERITED_KEYS),
        "field_order": ", ".join(FIELD_ORDER),
        "list_fields": ", ".join(LIST_FIELDS),
        "runs_heading": RUNS_HEADING,
        "runs_placeholder": RUNS_PLACEHOLDER,
        "index_file": INDEX_FILE,
        "test_command_rules": _test_command_rules(),
        "default_levels": _default_levels(),
        "settings_keys": _settings_keys(),
        "code_actions": _codes(CODE_ACTIONS),
        "harnesses": _harnesses(),
        "thinking_levels": _codes(THINKING_LEVELS),
        "workflows": _workflows(),
        "roles": _roles(),
        "skip_reasons": _codes(SKIP_REASONS),
        "stop_reasons": _codes(STOP_REASONS),
    }


def render_skill(parser: argparse.ArgumentParser | None = None) -> str:
    """The skill as markdown, for this version of the code."""
    text = (resources.files("aifactory.skill") / TEMPLATE).read_text(encoding="utf-8")
    for name, value in placeholders(parser).items():
        text = text.replace("{{" + name + "}}", value)
    if "{{" in text:
        start = text.index("{{")
        raise RuntimeError(f"unfilled placeholder in the skill: {text[start : start + 40]!r}")
    return text


def skill_json(parser: argparse.ArgumentParser | None = None) -> dict[str, Any]:
    """The data of ``factory --skill --json``."""
    parser = _parser(parser)
    return {
        "version": __version__,
        "skill": render_skill(parser),
        "commands": [c.to_dict() for c in iter_commands(parser)],
        "error_codes": [c.to_dict() for c in ERROR_CODES.values()],
        "issue_codes": {group: list(codes) for group, codes in ISSUE_CODES.items()},
    }
