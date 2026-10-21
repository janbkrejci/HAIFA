"""The library seed shipped in the package (AR16).

Agents live in ``aifactory/seed/agents/<name>/`` and pi extensions in
``aifactory/seed/extensions/<name>/`` (``subagents`` from sssf); the seed workflows are the
package defaults in ``aifactory/defaults/workflows/`` and are not copied. The skill
``factory`` is generated: its ``SKILL.md`` is ``factory --skill`` of this version
(``skill_seed_item``). It is part of the library seed (``store.packaged_seed``) but not of
``seed_items``, the no-library fallback for inheritance.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from aifactory.library.load import load_library_item, validate_item
from aifactory.library.model import ITEM_TYPES, Item, ItemFile, LibraryError
from aifactory.workflow.parse import DEFAULT_WORKFLOWS_DIR

SEED_DIR = Path(str(resources.files("aifactory") / "seed"))
SEED_WORKFLOWS_ROOT = DEFAULT_WORKFLOWS_DIR.parent
SEED_AGENTS: tuple[str, ...] = (
    "planner",
    "builder",
    "tester",
    "test-reviewer",
    "reviewer",
    "documenter",
    "scout",
    "guide",
    "proposer",
    "learner",
    "triager",
)
SKILL_NAME = "factory"
SKILL_FILE = "SKILL.md"


def seed_agent_names() -> list[str]:
    """Names of the seed agents, sorted."""
    return sorted(p.name for p in (SEED_DIR / "agents").iterdir() if p.is_dir())


def seed_extension_names() -> list[str]:
    """Names of the seed pi extensions, sorted."""
    folder = SEED_DIR / "extensions"
    return sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []


def seed_workflow_names() -> list[str]:
    """Names of the seed workflows, sorted."""
    return sorted(p.stem for p in DEFAULT_WORKFLOWS_DIR.glob("*.yaml"))


def seed_items() -> list[Item]:
    """Every seed item, loaded and validated, sorted by type and name."""
    items = [load_library_item(SEED_DIR, "agent", name) for name in seed_agent_names()]
    items += [load_library_item(SEED_DIR, "extension", name) for name in seed_extension_names()]
    items += [
        load_library_item(SEED_WORKFLOWS_ROOT, "workflow", name) for name in seed_workflow_names()
    ]
    return sorted(items, key=lambda i: (ITEM_TYPES.index(i.type), i.name))


def skill_seed_item() -> Item:
    """The generated seed skill ``factory`` (``factory --skill``), validated like any skill."""
    from aifactory.skill.render import render_skill  # the CLI parser imports the library

    data = render_skill().encode("utf-8")
    item = Item("skill", SKILL_NAME, (ItemFile(SKILL_FILE, False, data),))
    issues = validate_item(item)
    if issues:
        raise LibraryError(issues)
    return item
