"""`factory --skill`: every command, every error code and the formats are in the skill."""

from __future__ import annotations

import argparse
import ast
import json
import re
import tomllib
from pathlib import Path

import pytest
import yaml

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
        name = "factory " + " ".join(path)
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
        "### Add factory to an existing repo",
        "### Agents and prompts",
        "### Manifest and item states",
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
        "factory task resolve",
    ):
        assert text in skill, text


def test_skill_front_matter_and_version() -> None:
    from aifactory import __version__

    skill = render_skill()
    assert skill.startswith("---\n")
    metadata = yaml.safe_load(skill.split("---\n", 2)[1])
    assert metadata["name"] == "factory"
    assert "Use when" in metadata["description"]
    assert "Do not use" in metadata["description"]
    assert __version__ in skill
    assert "factory --version" in skill
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
        "factory check --json",
        "data.action",
        "`installed`",
        "`unsupported`",
        "`uncommitted`",
        "`none`",
        "does not take over",
    ):
        assert text in prerequisites, text
    assert "repo_unsupported" in skill
    for text in ("factory onboard", "factory adopt", "pre_library_config", "sssf_leftover"):
        assert text not in skill, text
    install = _section(skill, "Add factory to an existing repo")
    for text in (
        "factory check --json",
        "factory init --dry-run --json",
        "--agents",
        "--bind",
        "Show the user the files",
        "digest",
        "factory init --commit --expect <digest>",
        "push_failed",
        "only with their consent",
        "--pr",
        "factory backlog check --json",
        "Repeat all selection options",
    ):
        assert text in install, text


def test_skill_agents_prompts_and_manifest() -> None:
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
        ".factory/prompts/<slot>/system.md",
        ".factory/prompts/<slot>/user.md",
        "prompt",
        "previous_envelope",
        "context_handoff_dir",
        "task_id",
        "spec_path",
        "doc_path",
        "workdir",
        "test_result",
        "rebase_onto",
        "modified",
        "slot",
        "factory config export agent",
    ):
        assert text in agents, text
    manifest = _section(skill, "Manifest and item states")
    for text in ("onboarding", "source_commit", "items", "version", "reads only `format`"):
        assert text in manifest, text


def test_skill_backlog_creation_procedure() -> None:
    from aifactory.library.seed import seed_workflow_names

    skill = render_skill()
    section = _section(skill, "Plan -> backlog")
    for text in (
        'factory backlog add --id M01 --title "Core"',
        'factory backlog add M01 --id S01 --title "API"',
        "factory backlog edit M01 --workflow simple-sdlc",
        "factory task add M01-S01",
        "project → step → task",
        "nearest value wins",
        "factory backlog commit --json",
    ):
        assert text in section, text
    install = _section(skill, "Add factory to an existing repo")
    installed = re.findall(
        r"factory init --dry-run --json --agents [\w,-]+ --workflows ([\w-]+)", install
    )
    assigned = re.findall(r"factory backlog edit M01 --workflow ([\w-]+)", section)
    assert installed and assigned
    assert set(installed) <= set(seed_workflow_names())
    assert set(assigned) <= set(installed)


def test_skill_uses_project_level() -> None:
    skill = render_skill()
    for text in (
        "<backlog_dir>/<project>/<step>/<task>.md",
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
    assert {c["name"] for c in data["commands"]} >= {"factory task run", "factory task resolve"}
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
    """Every ``Finding("<code>", ...)`` of ``factory check`` is in ISSUE_CODES["check"]."""
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
    for text in ("factory check", "--offline", "scope: repo", "scope: machine", "action"):
        assert text in section, text
    assert "only by reading" in _section(skill, "factory check")


def test_skill_describes_repo_instructions_and_skills() -> None:
    text = render_skill()
    for needle in (
        "### Repo instructions and skills",
        "factory skills sync",
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
