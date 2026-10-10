"""Every prompt that uses ``context_handoff_dir`` says it is an absolute path outside the repo.

A model that reads the name as a repo-relative directory writes ``context_handoff/``
into the worktree, which the write guard rejects. No model is called; only files are read.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from validation.sandbox import AIFACTORY_DIR

PROMPTS = AIFACTORY_DIR / "validation/template/.factory/prompts"
RULE = (
    "`<context_handoff_dir>` is an absolute path outside the repo. Write handoff files at "
    "exactly that path; never create a directory of the same name inside the repo"
)


def prompt_files() -> list[Path]:
    roots = [PROMPTS, AIFACTORY_DIR / "src"]
    return sorted(
        p
        for root in roots
        for p in root.rglob("*.md")
        if "context_handoff_dir" in p.read_text("utf-8")
    )


def test_some_prompts_use_it() -> None:
    assert len(prompt_files()) >= 6


@pytest.mark.parametrize("path", prompt_files(), ids=lambda p: str(p.relative_to(AIFACTORY_DIR)))
def test_prompt_says_handoff_dir_is_absolute(path: Path) -> None:
    assert RULE in path.read_text("utf-8")


@pytest.mark.parametrize("path", prompt_files(), ids=lambda p: str(p.relative_to(AIFACTORY_DIR)))
def test_rule_stays_out_of_the_task_section(path: Path) -> None:
    text = path.read_text("utf-8")
    if "## Task" in text:
        assert RULE not in text.rsplit("## Task", 1)[1].split("\n## ", 1)[0]
