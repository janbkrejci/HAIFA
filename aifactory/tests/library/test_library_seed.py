"""The library seed: HAIFA's agents plus scout, and the package workflows."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aifactory.config.loader import load_config, write_prompts
from aifactory.config.settings import ProjectSettings
from aifactory.config.source import WorktreeSource
from aifactory.library import (
    SEED_AGENTS,
    SEED_DIR,
    load_library_item,
    load_repo_item,
    roster_entry,
    seed_agent_names,
    seed_items,
    seed_workflow_names,
)
from aifactory.workflow import DEFAULT_WORKFLOWS_DIR, load_workflow, preflight

HAIFA_ROOT = Path(__file__).resolve().parents[3]
HAIFA_AGENTS = ("planner", "builder", "tester", "reviewer", "documenter")
VENDOR_SCOUT = HAIFA_ROOT / "vendor/sssf/templates/prompt_engineering/scout"
HANDOFF = (
    "`<context_handoff_dir>` is an absolute path outside the repo. Write handoff files at "
    "exactly that path; never create a directory of the same name inside the repo or the "
    "worktree."
)
GIT_LINE = (
    "- Git is the workflow's job, not yours. Run no git command that changes anything: "
    "never `git commit`, `git add`, `git stash`, `git reset`, `git rebase`, `git merge` or "
    "`git push`, and never create, switch or delete branches (`git switch`, `git checkout`, "
    "`git branch`). Leave the working tree exactly as you found it."
)
EXPECTED_WRITES = {
    "planner": ["specs/"],
    "builder": None,
    "tester": [],
    "reviewer": [],
    "documenter": ["app_docs/"],
}


def test_seed_names() -> None:
    assert seed_agent_names() == sorted(SEED_AGENTS)
    assert seed_workflow_names() == sorted(p.stem for p in DEFAULT_WORKFLOWS_DIR.glob("*.yaml"))
    assert "scout" in seed_workflow_names()
    assert "resolve" in seed_workflow_names()


def test_seed_items_load() -> None:
    items = seed_items()
    assert [(i.type, i.name) for i in items] == [
        *(("agent", n) for n in sorted(SEED_AGENTS)),
        *(("workflow", n) for n in seed_workflow_names()),
    ]
    assert all(i.version.startswith("sha256:") for i in items)


def test_seed_workflows_are_not_copied() -> None:
    assert not (SEED_DIR / "workflows").exists()


# Seed additions HAIFA's own `.factory/prompts` (protected, edited by the operator)
# may not have picked up yet. With or without them the prompts must be equal.
PENDING_SEED_BLOCKS: dict[tuple[str, str], bytes] = {
    ("tester", "system"): (
        b"- The test step runs every check, also after one fails, and hands the builder "
        b"the output of every failed check. Order the checks from the shortest expected "
        b"run to the longest: lint and type check first, then the targeted tests, then "
        b"wider suites.\n- Set `stop_on_fail: true` only on a check without which the "
        b"others make no sense (a build, a dependency install, test collection). Its "
        b"failure stops the remaining checks, which the result lists in "
        b"`test_plan.not_run`. Leave it out everywhere else.\n- In a triage, "
        b"`failed_test.failed_checks` lists every failed check with its log.\n"
    ),
    ("tester", "user"): (
        b"Order the checks from the fastest to the slowest. `stop_on_fail` (optional, "
        b"default `false`) is only for a prerequisite such as a build or an install "
        b'whose failure makes the remaining checks pointless: `{ "name": "build", '
        b'"argv": ["npm", "run", "build"], "stop_on_fail": true }`.\n\n'
    ),
}


def _haifa_prompt(name: str, kind: str) -> bytes:
    return (HAIFA_ROOT / ".factory/prompts" / name / f"{kind}.md").read_bytes()


def _pending(name: str) -> bool:
    """Whether HAIFA's copy of agent ``name`` still lacks a seed addition."""
    return any(
        block not in _haifa_prompt(agent, kind)
        for (agent, kind), block in PENDING_SEED_BLOCKS.items()
        if agent == name
    )


@pytest.mark.parametrize("name", HAIFA_AGENTS)
@pytest.mark.parametrize("kind", ["system", "user"])
def test_seed_prompts_equal_haifa(name: str, kind: str) -> None:
    seed = (SEED_DIR / "agents" / name / f"{kind}.md").read_bytes()
    haifa = _haifa_prompt(name, kind)
    block = PENDING_SEED_BLOCKS.get((name, kind))
    if block is not None:
        assert block in seed
        seed, haifa = seed.replace(block, b""), haifa.replace(block, b"")
    assert seed == haifa


def test_seed_bindings_preserve_haifa_roles() -> None:
    config = load_config(WorktreeSource(HAIFA_ROOT))
    roster = {agent.name: agent for agent in config.agents.agents}
    for name in HAIFA_AGENTS:
        entry = roster_entry(load_library_item(SEED_DIR, "agent", name), config.settings)
        agent = roster[name]
        assert entry["purpose"] == agent.purpose
        # Seed defaults are stable; the operator may switch HAIFA's local roster
        # to Codex or mix providers without changing the library's role templates.
        assert entry["harness"] == "claude"
        assert entry["model"] == "claude-opus-5-5"
        assert entry["thinking"] == "medium"
        assert entry.get("writes") == agent.writes == EXPECTED_WRITES[name]


@pytest.mark.parametrize("name", HAIFA_AGENTS)
def test_seed_version_equals_haifa_repo_copy(name: str) -> None:
    if _pending(name):
        pytest.skip(f"{name}: .factory/prompts lacks a seed addition (PENDING_SEED_BLOCKS)")
    seed = load_library_item(SEED_DIR, "agent", name)
    assert seed.version == load_repo_item(HAIFA_ROOT, "agent", name).version


def test_scout_defaults() -> None:
    scout = load_library_item(SEED_DIR, "agent", "scout")
    assert scout.purpose == "Find and report where things live; change nothing."
    assert scout.defaults is not None
    assert scout.defaults.writes == ()
    assert scout.defaults.harness == "claude"
    assert scout.defaults.model == "claude-opus-5-5"
    assert scout.defaults.thinking == "medium"


@pytest.mark.parametrize(
    ("kind", "inserted"),
    [("system", ["- " + HANDOFF, GIT_LINE]), ("user", [HANDOFF, ""])],
)
def test_scout_prompts_adapted_from_vendor(kind: str, inserted: list[str]) -> None:
    seed = (SEED_DIR / "agents/scout" / f"{kind}.md").read_text(encoding="utf-8")
    vendor = (VENDOR_SCOUT / f"{kind}.md").read_text(encoding="utf-8")
    assert "adw_id" not in seed
    for line in inserted:
        assert line in seed.splitlines()
    lines = seed.splitlines(keepends=True)
    added = [i for i, line in enumerate(lines) if line.rstrip("\n") in inserted[:1] + [GIT_LINE]]
    if kind == "user":
        # the handoff paragraph is followed by one blank line
        added += [added[0] + 1]
    remaining = "".join(line for i, line in enumerate(lines) if i not in added)
    assert remaining == vendor


def test_seed_roster_passes_config_and_preflight(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".factory").mkdir(parents=True)
    (repo / ".factory/config.yaml").write_text("base: main\n", encoding="utf-8", newline="\n")
    seeds = {name: load_library_item(SEED_DIR, "agent", name) for name in SEED_AGENTS}
    entries = [roster_entry(item, ProjectSettings()) for item in seeds.values()]
    roster = yaml.safe_dump({"agents": entries}, sort_keys=False)
    (repo / ".factory/agents.yaml").write_text(roster, encoding="utf-8", newline="\n")
    for name, item in seeds.items():
        for item_file in item.files:
            path = repo / ".factory/prompts" / name / item_file.path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(item_file.data)

    config = load_config(WorktreeSource(repo))
    assert sorted(a.name for a in config.agents.agents) == sorted(SEED_AGENTS)
    for name, item in seeds.items():
        assert load_repo_item(repo, "agent", name).version == item.version

    cfg = write_prompts(config, tmp_path / "prompts")
    workflows = sorted(DEFAULT_WORKFLOWS_DIR.glob("*.yaml"))
    assert {p.stem for p in workflows} >= {"scout", "resolve"}
    for path in workflows:
        preflight(load_workflow(path, config.roles), cfg)
