"""The command list of the skill, walked from the argparse definition of the CLI.

The walk is generic: a new subcommand appears in the skill without touching this file.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ArgSpec:
    """One argument of a leaf command."""

    names: tuple[str, ...]
    metavar: str | None
    help: str
    required: bool
    nargs: str | int | None
    choices: tuple[str, ...] | None
    default: Any
    positional: bool
    takes_value: bool
    group: str | None = None


@dataclass
class CommandSpec:
    """One leaf command, e.g. ``("task", "run")``."""

    path: tuple[str, ...]
    help: str
    description: str
    arguments: list[ArgSpec] = field(default_factory=list)
    has_json: bool = False
    has_repo: bool = False

    @property
    def name(self) -> str:
        return "factory " + " ".join(self.path)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["name"] = self.name
        data["path"] = list(self.path)
        for arg in data["arguments"]:
            arg["names"] = list(arg["names"])
            if arg["choices"] is not None:
                arg["choices"] = list(arg["choices"])
            if not isinstance(arg["default"], str | int | float | bool | list | type(None)):
                arg["default"] = str(arg["default"])
        return data


def _subparsers(parser: argparse.ArgumentParser) -> argparse._SubParsersAction[Any] | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def iter_commands(parser: argparse.ArgumentParser) -> list[CommandSpec]:
    """Every leaf command below ``parser``, in definition order."""
    specs: list[CommandSpec] = []
    _walk(parser, (), "", specs)
    return specs


def _walk(
    parser: argparse.ArgumentParser, path: tuple[str, ...], help_text: str, out: list[CommandSpec]
) -> None:
    sub = _subparsers(parser)
    if sub is None:
        if path:
            out.append(_spec(parser, path, help_text))
        return
    helps = {a.dest: a.help or "" for a in sub._choices_actions}
    for name, child in sub.choices.items():
        _walk(child, (*path, name), helps.get(name, ""), out)


def _group_labels(parser: argparse.ArgumentParser) -> dict[int, str]:
    labels: dict[int, str] = {}
    for group in parser._mutually_exclusive_groups:
        options = [a.option_strings[0] for a in group._group_actions if a.option_strings]
        label = "|".join(options) + (" (one required)" if group.required else "")
        for action in group._group_actions:
            labels[id(action)] = label
    return labels


def _spec(parser: argparse.ArgumentParser, path: tuple[str, ...], help_text: str) -> CommandSpec:
    groups = _group_labels(parser)
    args: list[ArgSpec] = []
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        positional = not action.option_strings
        metavar = action.metavar if isinstance(action.metavar, str) else None
        names = tuple(action.option_strings) if not positional else (metavar or action.dest,)
        choices = tuple(str(c) for c in action.choices) if action.choices else None
        takes_value = action.nargs != 0
        args.append(
            ArgSpec(
                names=names,
                metavar=metavar,
                help=action.help or "",
                required=bool(action.required),
                nargs=action.nargs,
                choices=choices,
                default=action.default if not positional else None,
                positional=positional,
                takes_value=takes_value,
                group=groups.get(id(action)),
            )
        )
    options = {n for a in args for n in a.names}
    return CommandSpec(
        path=path,
        help=help_text,
        description=parser.description or help_text,
        arguments=args,
        has_json="--json" in options,
        has_repo="--repo" in options,
    )


def _value(arg: ArgSpec) -> str:
    """The placeholder of an option's value: ``TEXT``, ``{a,b}``, ``PATH ...``."""
    if not arg.takes_value:
        return ""
    if arg.choices:
        word = "{" + ",".join(arg.choices) + "}"
    else:
        word = arg.metavar or arg.names[0].lstrip("-").upper()
    if arg.nargs == "*":
        return f" [{word} ...]"
    if arg.nargs == "+":
        return f" {word} [{word} ...]"
    return f" {word}"


def usage(spec: CommandSpec) -> str:
    """``factory task run ID [--note TEXT] [--force] ... [--json] [--repo PATH]``."""
    parts = [spec.name]
    seen_groups: set[str] = set()
    for arg in spec.arguments:
        if arg.positional:
            parts.append(f"[{arg.names[0]}]" if arg.nargs == "?" else arg.names[0])
            continue
        if arg.group is not None:
            if arg.group in seen_groups:
                continue
            seen_groups.add(arg.group)
            members = [a for a in spec.arguments if a.group == arg.group]
            inner = " | ".join(a.names[0] + _value(a) for a in members)
            parts.append(f"({inner})" if arg.required else f"[{inner}]")
            continue
        text = arg.names[0] + _value(arg)
        parts.append(text if arg.required else f"[{text}]")
    return " ".join(parts)


def _describe(arg: ArgSpec) -> str:
    names = ", ".join(f"`{n}`" for n in arg.names)
    value = _value(arg).strip()
    if value and not arg.positional:
        names += f" `{value}`"
    notes: list[str] = []
    if arg.required:
        notes.append("required")
    if arg.group is not None:
        notes.append(f"exclusive: {arg.group}")
    if arg.choices:
        notes.append("one of " + ", ".join(f"`{c}`" for c in arg.choices))
    default = arg.default
    if not arg.positional and default not in (None, False, [], "") and arg.takes_value:
        notes.append(f"default `{default}`")
    text = f"- {names}"
    if arg.help:
        text += f": {arg.help}"
    if notes:
        text += f" ({'; '.join(notes)})"
    return text


def format_commands(specs: list[CommandSpec]) -> str:
    """The markdown reference of every command."""
    blocks: list[str] = []
    for spec in specs:
        lines = [f"### {spec.name}", "", "```", usage(spec), "```", "", spec.description, ""]
        lines.extend(_describe(a) for a in spec.arguments)
        blocks.append("\n".join(lines).rstrip())
    return "\n\n".join(blocks)
