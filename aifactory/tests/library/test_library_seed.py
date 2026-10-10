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

_BUILDER_OLD_TESTS = (
    b"- Run only the tests that cover the code you changed (by explicit test file or "
    b"project), plus the repo's type check and lint for the changed files. Never run "
    b"the whole suite: the test step after you runs the checks a tester chose and "
    b"returns every failure to you. A check you could not finish is not a reason to "
    b"report `fail`.\n"
)
_BUILDER_NEW_TESTS = (
    b"- Only verify your own change, quickly. Run only explicit test files that you "
    b"changed or that directly cover a module you changed, or single tests in them "
    b"(`pytest tests/x/test_y.py`, `pytest tests/x/test_y.py::test_name`, "
    b"`bun run test src/y.test.ts`). Never pass a directory, never start a test runner "
    b"without a file path, and never run whole-suite commands such as `just check`, "
    b"`just check-scoped`, `just test`, `just e2e`, `just web-test`, or `pytest` or "
    b"`bun run test` without a file.\n"
    b"- Run the type check and lint only on the files you changed.\n"
    b"- The checks that count are the tester's: the test step after you runs every "
    b"check the tester chose, also after one fails, and returns every failed check to "
    b"you. A check you could not finish is not a reason to report `fail`.\n"
)

# Seed rewrites HAIFA's own `.factory/prompts` may not have picked up yet:
# (agent, kind) -> (HAIFA's old text, the seed's new text).
PENDING_SEED_REPLACEMENTS: dict[tuple[str, str], tuple[bytes, bytes]] = {
    ("builder", "system"): (_BUILDER_OLD_TESTS, _BUILDER_NEW_TESTS),
}


def _haifa_prompt(name: str, kind: str) -> bytes:
    return (HAIFA_ROOT / ".factory/prompts" / name / f"{kind}.md").read_bytes()


def _pending(name: str) -> bool:
    """Whether HAIFA's copy of agent ``name`` still lacks a seed addition."""
    return any(
        block not in _haifa_prompt(agent, kind)
        for (agent, kind), block in PENDING_SEED_BLOCKS.items()
        if agent == name
    ) or any(
        new not in _haifa_prompt(agent, kind)
        for (agent, kind), (_old, new) in PENDING_SEED_REPLACEMENTS.items()
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
    replacement = PENDING_SEED_REPLACEMENTS.get((name, kind))
    if replacement is not None:
        old, new = replacement
        assert new in seed
        seed = seed.replace(new, old)
        haifa = haifa.replace(new, old)
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
def test_scout_prompts_have_handoff_and_git_lines(kind: str, inserted: list[str]) -> None:
    seed = (SEED_DIR / "agents/scout" / f"{kind}.md").read_text(encoding="utf-8")
    assert "adw_id" not in seed
    for line in inserted:
        assert line in seed.splitlines()


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
