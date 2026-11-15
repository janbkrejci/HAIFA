"""`giro --skill`: every command, every error code and the formats are in the skill."""

from __future__ import annotations

import argparse
import ast
import json
import re
import tomllib
from pathlib import Path

import pytest
import yaml

from aifactory import guide
from aifactory.cli import build_parser, main
from aifactory.skill import (
    ERROR_CODES,
    ISSUE_CODES,
    envelope_problems,
    iter_commands,
    render_skill,
)

Capsys = pytest.CaptureFixture[str]
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "aifactory"


def _leaves(
    parser: argparse.ArgumentParser, path: tuple[str, ...] = ()
) -> list[tuple[tuple[str, ...], argparse.ArgumentParser]]:
    """Every leaf parser, walked independently of ``iter_commands``."""
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subs:
        return [(path, parser)] if path else []
    found: list[tuple[tuple[str, ...], argparse.ArgumentParser]] = []
    for name, child in subs[0].choices.items():
        found += _leaves(child, (*path, name))
    return found


def _section(skill: str, name: str) -> str:
    start = skill.index(f"### {name}\n")
    end = skill.find("\n### ", start + 1)
    end_h2 = skill.find("\n## ", start + 1)
    ends = [e for e in (end, end_h2) if e != -1]
    return skill[start : min(ends)] if ends else skill[start:]


def test_every_command_is_in_skill() -> None:
    parser = build_parser()
    skill = render_skill(parser)
    leaves = _leaves(parser)
    assert len(leaves) == len(iter_commands(parser))
    for path, leaf in leaves:
        name = "giro " + " ".join(path)
        assert name in skill
        section = _section(skill, name)
        for action in leaf._actions:
            if isinstance(action, argparse._HelpAction):
                continue
            words = action.option_strings or [str(action.metavar or action.dest)]
            for word in words:
                assert word in section, (name, word)


def test_every_command_has_json() -> None:
    for path, leaf in _leaves(build_parser()):
        options = {o for a in leaf._actions for o in a.option_strings}
        assert "--json" in options, path


def test_skill_lists_error_codes() -> None:
    skill = render_skill()
    assert "{{" not in skill
    for code in ERROR_CODES:
        assert f"`{code}`" in skill, code
    for codes in ISSUE_CODES.values():
        for code in codes:
            assert f"`{code}`" in skill, code


def test_skill_sections() -> None:
    skill = render_skill()
    for text in (
        "## Prerequisites",
        "### Add GIRO to an existing repo",
        "### Agents and prompts",
        "### Items of the repo: config set / remove / move",
        "## Calling convention",
        "## Commands",
        "## Error codes",
        "## Backlog format",
        "index.md",
        "depends_on",
        "writes",
        "## Zadání",
        "## Běhy",
        "## Workflow format",
        "repeat",
        "accept",
        "## Procedures",
        "### Plan -> backlog",
        "### Run",
        "### Review",
        "### Approve",
        "### Return",
        "### Resolve",
        "giro task resolve",
    ):
        assert text in skill, text


def test_skill_front_matter_and_version() -> None:
    from aifactory import __version__

    skill = render_skill()
    assert skill.startswith("---\n")
    metadata = yaml.safe_load(skill.split("---\n", 2)[1])
    assert metadata["name"] == "factory"
    assert "# GIRO skill" in skill
    assert "Goal in. Release out." in skill
    assert "Use when" in metadata["description"]
    assert "Do not use" in metadata["description"]
    assert __version__ in skill
    assert "giro --version" in skill
    assert "regenerate this skill" in skill
    assert "never copy it into a repository" not in skill


def test_skill_settings_reference_is_generated() -> None:
    from aifactory.config.settings import AzureSettings, GeneratedOutput, ProjectSettings

    section = _section(render_skill(), "`.factory/config.yaml`")
    for prefix, model in (
        ("", ProjectSettings),
        ("azure.", AzureSettings),
        ("generated[].", GeneratedOutput),
    ):
        for name, info in model.model_fields.items():
            assert info.description, (prefix, name)
            default = (
                "required"
                if info.is_required()
                else json.dumps(info.get_default(call_default_factory=True))
            )
            assert f"| `{prefix}{name}` | `{default}` | {info.description} |" in section


def test_skill_settings_reference_tracks_model_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    from aifactory.config.settings import ProjectSettings

    info = ProjectSettings.model_fields["base"]
    monkeypatch.setattr(info, "default", "trunk")
    monkeypatch.setattr(info, "description", "Changed base description.")
    assert '| `base` | `"trunk"` | Changed base description. |' in render_skill()


def test_skill_installation_procedure() -> None:
    skill = render_skill()
    prerequisites = skill.split("## Prerequisites\n", 1)[1].split("\n## ", 1)[0]
    for text in (
        "giro check --json",
        "data.action",
        "`installed`",
        "`unsupported`",
        "`uncommitted`",
        "`none`",
        "does not take over",
    ):
        assert text in prerequisites, text
    assert "repo_unsupported" in skill
    for text in (
        "giro onboard",
        "giro adopt",
        "pre_library_config",
        "sssf_leftover",
        "giro update",
        "config export",
        "config add",
        "manifest.yaml",
    ):
        assert text not in skill, text
    install = _section(skill, "Add GIRO to an existing repo")
    for text in (
        "giro check --json",
        "giro init --dry-run --json",
        "Show the user the files",
        "digest",
        "giro init --commit --expect <digest>",
        "push_failed",
        "only with their consent",
        "--pr",
        "giro backlog check --json",
        "Repeat all options",
    ):
        assert text in install, text


def test_skill_agents_prompts_and_library() -> None:
    skill = render_skill()
    agents = _section(skill, "Agents and prompts")
    for text in (
        "agents.yaml",
        "defaults",
        "name",
        "harness",
        "model",
        "thinking",
        "tools",
        "writes",
        "disallowed_commands",
        "harness_engineering",
        "prompt_engineering",
        ".factory/prompts/<name>/system.md",
        ".factory/prompts/<name>/user.md",
        "prompt",
        "previous_envelope",
        "context_handoff_dir",
        "task_id",
        "spec_path",
        "doc_path",
        "workdir",
        "test_result",
        "rebase_onto",
        "library",
        "the seed",
        "library_commit",
        "giro config move agent",
    ):
        assert text in agents, text
    items = _section(skill, "Items of the repo: config set / remove / move")
    for text in ("giro config move", "library_missing", "in_use", "--expect <digest>"):
        assert text in items, text


def test_skill_backlog_creation_procedure() -> None:
    from aifactory.library.seed import seed_workflow_names

    skill = render_skill()
    section = _section(skill, "Plan -> backlog")
    for text in (
        'giro backlog add --id M01 --title "Core"',
        'giro backlog add M01 --id S01 --title "API"',
        "giro backlog edit M01 --workflow simple-sdlc",
        "giro task add M01-S01",
        "project → step → task",
        "nearest value wins",
        "giro backlog commit --json",
    ):
        assert text in section, text
    assigned = re.findall(r"giro backlog edit M01 --workflow ([\w-]+)", section)
    assert assigned
    assert set(assigned) <= set(seed_workflow_names())


def test_skill_uses_project_level() -> None:
    skill = render_skill()
    for text in (
        "<docs_root>/backlog/<project>/<step>/<task>.md",
        "default `[project, step, task]`",
        "--project",
        "unknown_project",
        "Map every module of the plan to a project",
    ):
        assert text in skill, text
    for text in ("<module>", "unknown_module", "--module"):
        assert text not in skill, text


def test_skill_cli(capsys: Capsys) -> None:
    assert main(["--skill"]) == 0
    assert capsys.readouterr().out.startswith("---\nname: factory\n")
    assert main(["--skill", "--json"]) == 0
    obj = json.loads(capsys.readouterr().out)
    assert envelope_problems(obj) == []
    data = obj["data"]
    assert data["skill"].startswith("---\nname: factory\n")
    assert {c["name"] for c in data["commands"]} >= {"giro task run", "giro task resolve"}
    assert {c["code"] for c in data["error_codes"]} == set(ERROR_CODES)


def test_root_json_without_skill(capsys: Capsys) -> None:
    assert main(["--json", "task", "list"]) == 2
    obj = json.loads(capsys.readouterr().out)
    assert envelope_problems(obj) == [] and obj["error"]["code"] == "usage_error"


# ── the code registry is complete ─────────────────────────────────────────────

ERROR_CLASSES = {
    "TaskEditError",
    "TaskRunError",
    "ReviewError",
    "ProviderError",
    "MergeFailed",
    "ConfigCommitError",
    "LibraryStoreError",
    "RepoError",
    "UpgradeError",
}
EMITTERS = {"_emit_fail", "envelope_fail"}
ISSUE_BUILDERS = {"Issue", "add", "issue"}  # Issue(...) and the loaders' add/issue helpers


def _excluded() -> set[Path]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return {ROOT / p for p in data["tool"]["ruff"]["extend-exclude"]}


def _calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)]


def _name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _literal_code(call: ast.Call) -> str | None:
    for kw in call.keywords:
        if kw.arg == "code" and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


def test_error_codes_complete() -> None:
    excluded = _excluded()
    found: dict[str, str] = {}
    for path in sorted(SRC.rglob("*.py")):
        if path in excluded:
            continue
        for call in _calls(path):
            name = _name(call)
            if name in ERROR_CLASSES or (name in EMITTERS and path.name == "cli.py"):
                code = _literal_code(call)
                if code is not None:
                    found[code] = str(path.relative_to(ROOT))
    assert len(found) > 30  # the scan sees the raise sites
    missing = {c: where for c, where in found.items() if c not in ERROR_CODES}
    assert missing == {}


def test_issue_codes_complete() -> None:
    known = {c for codes in ISSUE_CODES.values() for c in codes}
    sources = [
        *sorted((SRC / "backlog").rglob("*.py")),
        *sorted((SRC / "workflow").rglob("*.py")),
        SRC / "engine" / "role_registry.py",
    ]
    found: dict[str, str] = {}
    for path in sources:
        for call in _calls(path):
            if _name(call) in ISSUE_BUILDERS and len(call.args) >= 3:
                code = _literal_code(call)
                if code is not None:
                    found[code] = str(path.relative_to(ROOT))
    assert len(found) > 30
    assert {c: w for c, w in found.items() if c not in known} == {}


def test_check_codes_complete() -> None:
    """Every ``Finding("<code>", ...)`` of ``giro check`` is in ISSUE_CODES["check"]."""
    found: set[str] = set()
    for path in sorted((SRC / "check").rglob("*.py")):
        for call in _calls(path):
            if _name(call) == "Finding":
                assert call.args and isinstance(call.args[0], ast.Constant), (path, call.lineno)
                found.add(str(call.args[0].value))
    assert found == set(ISSUE_CODES["check"])


def test_skill_describes_check() -> None:
    skill = render_skill()
    section = _section(skill, "Check")
    for text in ("giro check", "--offline", "scope: repo", "scope: machine", "action"):
        assert text in section, text
    assert "only by reading" in _section(skill, "giro check")


def test_skill_describes_repo_instructions_and_skills() -> None:
    text = render_skill()
    for needle in (
        "### Repo instructions and skills",
        "giro skills sync",
        ".agents/skills",
        "--setting-sources project,local",
        "CLAUDE_SAFE_MODE",
        "CODEX_SAFE_MODE",
        "PI_SAFE_MODE",
        "skill_mirror_missing",
        "codex_not_isolated",
        "pi_not_isolated",
    ):
        assert needle in text, needle


README = ROOT / "README.md"


def _code_spans(text: str) -> list[str]:
    """Fenced code lines and inline code spans of markdown, whitespace collapsed."""
    spans: list[str] = []
    fences = re.compile(r"^[ \t]*```[^\n]*\n(.*?)^[ \t]*```", re.M | re.S)
    for block in fences.findall(text):
        spans += [line.strip() for line in block.splitlines()]
    spans += [" ".join(s.split()) for s in re.findall(r"`([^`]+)`", fences.sub("", text))]
    return spans


def _factory_commands(text: str) -> set[tuple[str, ...]]:
    """Every ``giro <word> ...`` in code: the leading lowercase words after ``giro``."""
    found: set[tuple[str, ...]] = set()
    for span in _code_spans(text):
        for match in re.finditer(r"(?:^|[\s(])giro((?:\s+[a-z][a-z-]*)*)", span):
            found.add(tuple(match.group(1).split()))
    return found


def _unknown_commands(text: str) -> list[str]:
    """Commands of ``text`` the CLI parser does not have."""
    unknown: list[str] = []
    for words in sorted(_factory_commands(text)):
        parser = build_parser()
        for word in words:
            subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
            if not subs:
                break  # a leaf: the rest are arguments
            if word not in subs[0].choices:
                unknown.append("giro " + " ".join(words))
                break
            parser = subs[0].choices[word]
    return unknown


def _guide() -> str:
    return "\n".join(chapter.markdown for chapter in guide.chapters())


def test_guide_leaves_check_fixes_to_factory_check() -> None:
    """The guide does not repeat the ``fix`` of every ``giro check`` code in tables."""
    text = _guide()
    assert "| Kód |" not in text
    assert "`fix`" in text


def test_guide_covers_setup_library_repos_and_upgrades() -> None:
    text = _guide()
    for needle in (
        "./install.sh",
        "giro check",
        "giro library clone",
        "giro library init",
        "giro init",
        "giro obs",
        "giro upgrade",
        "giro library seed",
        "min_factory_version",
        "just bundle",
    ):
        assert needle in text, needle
    for removed in ("giro adopt", "giro update", "config export", "library where"):
        assert removed not in text, removed


def test_readme_points_to_the_guide() -> None:
    readme = README.read_text(encoding="utf-8")
    assert "giro obs" in readme
    assert "src/aifactory/guide" in readme


def test_pyproject_readme() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["readme"] == "README.md"


def test_factory_commands_exist_in_parser() -> None:
    readme = README.read_text(encoding="utf-8")
    text = _guide()
    skill = render_skill()
    assert len(_factory_commands(text)) > 30
    assert len(_factory_commands(skill)) > 50
    assert _unknown_commands(readme) == []
    assert _unknown_commands(text) == []
    assert _unknown_commands(skill) == []
    assert _unknown_commands("`giro library where`, `giro adopt`") == [
        "giro adopt",
        "giro library where",
    ]


def test_skill_setup_and_item_procedures() -> None:
    skill = render_skill()
    setup = _section(skill, "Set up a machine")
    for text in ("giro check --json", "giro library clone", "giro library init"):
        assert text in setup, text
    takeover = _section(skill, "Take over a repo with committed `.factory/`")
    for text in ("giro check --json", "`installed`", "Never run", "giro obs"):
        assert text in takeover, text
    items = _section(skill, "Manage items")
    for text in (
        "giro library import",
        "giro config set",
        "giro config remove",
        "giro config move",
        "giro config commit",
        "inherit",
    ):
        assert text in items, text
    upgrade = _section(skill, "Upgrade")
    for text in ("giro upgrade", "giro library seed", "next run"):
        assert text in upgrade, text


def test_allow_writes_explains_uncommitted_base() -> None:
    section = _section(render_skill(), "Retry")
    assert "writes_not_committed" in section
    assert "giro backlog commit --json" in section
    assert "giro task retry ID --json" in section
    assert ERROR_CODES["writes_not_committed"]


def test_skill_explains_explicit_local_transition() -> None:
    skill = render_skill()
    for text in (
        "giro config local legacy",
        "giro config local import",
        "--overwrite",
        "deprecated_option",
        "Both automations default to off",
        "Restart an already running dashboard",
        "an upgraded computer uses local choices",
    ):
        assert text in skill
    assert "auto_continue: false" not in skill
    assert "auto_merge: false" not in skill
    assert "auto_continue: true" not in skill


def test_documented_docs_root_defaults_match_settings() -> None:
    from aifactory.config.settings import ProjectSettings

    skill = render_skill()
    patterns = (
        r"`docs_root` in `\.factory/config\.yaml`\s*\(default `([^`]+)`\)",
        r"`--docs-root DIR` \(default `([^`]+)`\)",
    )
    for pattern in patterns:
        documented = re.search(pattern, skill)
        assert documented is not None, pattern
        assert documented.group(1) == ProjectSettings().docs_root
