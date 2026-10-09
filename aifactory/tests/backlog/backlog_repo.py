"""Copies of the sample backlog repository (helpers, not fixtures)."""

from __future__ import annotations

import shutil
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "sample"
M01_S01 = "backlog/M01-core/S01-model"
M01_S02 = "backlog/M01-core/S02-api"
M02_S01 = "backlog/M02-ui/S01-list"
T01 = f"{M01_S01}/M01-S01-T01-schema.md"
T02 = f"{M01_S01}/M01-S01-T02-loader.md"
ENDPOINT = f"{M01_S02}/M01-S02-T01-endpoint.md"
DOCS = f"{M01_S02}/M01-S02-T02-docs.md"
VIEW = f"{M02_S01}/M02-S01-T01-view.md"
FILTER = f"{M02_S01}/M02-S01-T02-filter.md"


def sample_repo(tmp_path: Path) -> Path:
    """A fresh copy of the sample repository (not a git repository)."""
    root = tmp_path / "repo"
    shutil.copytree(FIXTURE, root)
    return root


def rewrite(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in {path}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def task_md(task_id: str, status: str = "todo", extra: str = "") -> str:
    return f"---\nid: {task_id}\ntitle: {task_id}\nstatus: {status}\n{extra}---\n\nbody\n"


def index_md(node_id: str, extra: str = "") -> str:
    return f"---\nid: {node_id}\ntitle: {node_id}\n{extra}---\n"
