"""The guide must match the dashboard and the CLI it describes.

Bold text (``**…**``) in the guide names a dashboard label, so each one must occur in the
Vue sources; every ``factory …`` command and every ``--option`` must exist in the argparse
tree; and the guide stays short. Bold text that is not a UI label is listed in
``NOT_UI_LABELS`` with the reason.
"""

from __future__ import annotations

import argparse
import re
import shlex
from collections.abc import Iterable
from pathlib import Path

from aifactory import guide
from aifactory.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]
WEB_SRC = ROOT / "web" / "src"
MAX_WORDS = 4000

# Bold text in the guide that is not a dashboard label (terms, list lead-ins, headings of
# troubleshooting items, labels composed at runtime). Anything else must be in web/src.
NOT_UI_LABELS: dict[str, str] = {
    "Domovský adresář HAIFA": "term in the introduction",
    "Alespoň jeden harness": "installation prerequisite",
    "App Installer": "Windows component",
    "Bash, `curl` a `unzip`": "installation prerequisite",
    "CLI hostingu": "installation prerequisite",
    "Extrahovat vše": "Windows Explorer menu item",
    "Systém:": "list lead-in",
    "[uv](https://docs.astral.sh/uv/getting-started/installation/)": "installation prerequisite",
    "Chip aktualizací:": "list lead-in",
    "Chip knihovny:": "list lead-in",
    "Chip kontroly:": "list lead-in",
    "HAIFA:": "list lead-in naming the logo link",
    "Harnessy:": "list lead-in naming the limits bar",
    "Necommitnutý backlog": "UncommittedBanner composes it as `Necommitnutý ${title}`",
    "běhy čtou backlog z base": "emphasis",
    "Běhy čtou sdílenou konfiguraci z commitu v base.": "emphasis",
    "TODO": "name of the backlog step for reported work",
    "Nastavení agentů:": "list lead-in",
    "Nastavení repozitáře:": "list lead-in",
    "Běh selhal nebo se zasekl.": "troubleshooting item",
    "Harness chybí nebo není přihlášený.": "troubleshooting item",
    "Knihovna je pozadu nebo se rozešla s remote.": "troubleshooting item",
    "PR zůstal po schválení otevřený.": "troubleshooting item",
    "Task nejde spustit.": "troubleshooting item",
    "Změna `.factory/` nebo backlogu se v běhu neprojevila.": "troubleshooting item",
    "Kroky agentů": "workflow reference term",
    "Kódové kroky": "workflow reference term",
}

# Options in the guide that belong to other programs than `factory`.
NOT_CLI_OPTIONS: dict[str, str] = {
    "--purge": "uninstall.sh",
    "--keep-data": "uninstall.sh",
}

_FENCE = re.compile(r"^```.*?^```", re.M | re.S)
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE_SPAN = re.compile(r"`([^`\n]+)`")


def _guide_markdown() -> str:
    return "\n".join(c.markdown for c in guide.chapters())


def _web_sources() -> str:
    """The dashboard's own sources; tests and their fixtures do not count as UI."""
    files = sorted(
        p
        for p in WEB_SRC.rglob("*")
        if p.suffix in {".vue", ".ts"}
        and not p.name.endswith(".test.ts")
        and "test" not in p.relative_to(WEB_SRC).parts[:-1]
    )
    return "\n".join(p.read_text(encoding="utf-8") for p in files)


def bold_labels(markdown: str) -> set[str]:
    return set(_BOLD.findall(_FENCE.sub("", markdown)))


def missing_labels(markdown: str, sources: str, exceptions: Iterable[str] = ()) -> list[str]:
    """Bold texts of ``markdown`` that are neither in ``sources`` nor exceptions."""
    skip = set(exceptions)
    missing: list[str] = []
    for label in sorted(bold_labels(markdown) - skip):
        text = label.removesuffix(":").strip()
        if not re.search(rf"(?<!\w){re.escape(text)}(?!\w)", sources):
            missing.append(label)
    return missing


def factory_commands(markdown: str) -> list[str]:
    """``factory …`` commands in code spans and on lines of code blocks."""
    commands = [
        s for s in _CODE_SPAN.findall(_FENCE.sub("", markdown)) if s.split()[:1] == ["factory"]
    ]
    for block in _FENCE.findall(markdown):
        for line in block.splitlines():
            line = line.split(" #", 1)[0].strip().removeprefix("$ ")
            if line.split()[:1] == ["factory"]:
                commands.append(line)
    return commands


def standalone_options(markdown: str) -> list[str]:
    """Options quoted on their own, such as `--pr` or `--port N`."""
    spans = _CODE_SPAN.findall(_FENCE.sub("", markdown))
    return [s.split()[0] for s in spans if s.startswith("--")]


def _subcommands(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _all_options(parser: argparse.ArgumentParser) -> set[str]:
    found = set(parser._option_string_actions)
    for child in _subcommands(parser).values():
        found |= _all_options(child)
    return found


def command_problem(command: str, parser: argparse.ArgumentParser) -> str | None:
    """Why ``command`` does not exist in the argparse tree, or None."""
    current = parser
    path = ["factory"]
    descend = True
    for token in shlex.split(command)[1:]:
        if token.startswith("-"):
            option = token.split("=", 1)[0]
            if option not in current._option_string_actions:
                return f"{' '.join(path)} has no option {option}"
            continue
        children = _subcommands(current)
        if not descend or not children:
            continue
        if token.startswith("<"):
            descend = False  # a placeholder such as <příkaz>; only global options follow
            continue
        if token not in children:
            return f"{' '.join(path)} has no subcommand {token}"
        current = children[token]
        path.append(token)
    return None


def cli_problems(markdown: str, parser: argparse.ArgumentParser) -> list[str]:
    problems = [p for c in factory_commands(markdown) if (p := command_problem(c, parser))]
    known = _all_options(parser) | set(NOT_CLI_OPTIONS)
    problems += [f"unknown option {o}" for o in standalone_options(markdown) if o not in known]
    return problems


def test_bold_ui_labels_exist_in_the_dashboard() -> None:
    assert missing_labels(_guide_markdown(), _web_sources(), NOT_UI_LABELS) == []


def test_label_exceptions_are_still_used() -> None:
    assert set(NOT_UI_LABELS) - bold_labels(_guide_markdown()) == set()


def test_commands_and_options_exist_in_the_cli() -> None:
    markdown = _guide_markdown()
    assert len(factory_commands(markdown)) >= 20
    assert cli_problems(markdown, build_parser()) == []


def test_guide_stays_short() -> None:
    words = len(_guide_markdown().split())
    assert words <= MAX_WORDS, f"the guide has {words} words, the limit is {MAX_WORDS}"


def test_a_missing_label_is_reported() -> None:
    markdown = "Klikni na **Spustit**, pak na **Neexistující tlačítko** a **Stav:** zkontroluj."
    sources = "<button>Spustit</button> <span>Stav</span> <i>Neexistující tlačítkovník</i>"
    assert missing_labels(markdown, sources) == ["Neexistující tlačítko"]
    assert missing_labels(markdown, sources, ["Neexistující tlačítko"]) == []
    assert missing_labels("```\n**Uvnitř bloku**\n```\n", "") == []


def test_an_unknown_command_or_option_is_reported() -> None:
    parser = build_parser()
    markdown = (
        "Spusť `factory task run ID`, `factory <příkaz> --help`, `factory tasks list`, "
        "`factory task run ID --neexistuje` a přepínač `--nikde`.\n"
        "```bash\nfactory check --offline  # komentář --zadny\nfactory library vymysleny\n```\n"
    )
    assert cli_problems(markdown, parser) == [
        "factory has no subcommand tasks",
        "factory task run has no option --neexistuje",
        "factory library has no subcommand vymysleny",
        "unknown option --nikde",
    ]
