"""The library seed shipped in the package (AR16).

Agents live in ``aifactory/seed/agents/<name>/``; the seed workflows are the
package defaults in ``aifactory/defaults/workflows/`` and are not copied.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from aifactory.library.load import load_library_item
from aifactory.library.model import ITEM_TYPES, Item
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
)


def seed_agent_names() -> list[str]:
    """Names of the seed agents, sorted."""
    return sorted(p.name for p in (SEED_DIR / "agents").iterdir() if p.is_dir())


def seed_workflow_names() -> list[str]:
    """Names of the seed workflows, sorted."""
    return sorted(p.stem for p in DEFAULT_WORKFLOWS_DIR.glob("*.yaml"))


def seed_items() -> list[Item]:
    """Every seed item, loaded and validated, sorted by type and name."""
    items = [load_library_item(SEED_DIR, "agent", name) for name in seed_agent_names()]
    items += [
        load_library_item(SEED_WORKFLOWS_ROOT, "workflow", name) for name in seed_workflow_names()
    ]
    return sorted(items, key=lambda i: (ITEM_TYPES.index(i.type), i.name))
