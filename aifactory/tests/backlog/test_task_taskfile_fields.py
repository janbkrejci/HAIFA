"""Header field edits in `aifactory.backlog.taskfile` and `slugify`."""

from __future__ import annotations

import pytest
import yaml

from aifactory.backlog import parse_frontmatter, remove_field, set_field, slugify
from aifactory.backlog.taskfile import format_list, format_scalar, new_task_text

TEXT = (
    "---\n"
    "id: M01-S01-T02\n"
    "title: Loader\n"
    "status: todo\n"
    "depends_on:\n"
    "  - a\n"
    "  - b\n"
    "---\n"
    "\n"
    "## Zadání\n"
    "Tělo: beze změny.\n"
)


def _body(text: str) -> str:
    return text.split("---\n", 2)[2]


@pytest.mark.parametrize(
    ("value", "plain"),
    [
        ("Loader", True),
        ("Migrace hlavičky faktury", True),
        ("src/x/", True),
        ("true", False),
        ("123", False),
        ("null", False),
        ("a: b", False),
        ("x, y", False),
        ("- item", False),
        ("", False),
        (" pad", False),
        ('say "hi"', False),
    ],
)
def test_format_scalar(value: str, plain: bool) -> None:
    out = format_scalar(value)
    assert (out == value) is plain
    assert yaml.safe_load(f"k: {out}") == {"k": value}


def test_format_list() -> None:
    assert format_list([]) == "[]"
    out = format_list(["a", "b, c", "true"])
    assert yaml.safe_load(f"k: {out}") == {"k": ["a", "b, c", "true"]}


def test_set_field_replaces_line() -> None:
    out = set_field(TEXT, "title", "Nový: titulek")
    data, _ = parse_frontmatter(out)
    assert data["title"] == "Nový: titulek"
    assert out.replace('title: "Nový: titulek"', "title: Loader") == TEXT


def test_set_field_rewrites_block_list() -> None:
    out = set_field(TEXT, "depends_on", ["a", "c"])
    assert "depends_on: [a, c]\n---\n" in out
    assert "  - b" not in out
    assert _body(out) == _body(TEXT)


def test_set_field_inserts_in_field_order() -> None:
    out = set_field(TEXT, "workflow", "wf")
    lines = out.splitlines()
    assert lines.index("workflow: wf") == lines.index("status: todo") + 1
    out = set_field(out, "writes", [])
    assert out.splitlines()[out.splitlines().index("---", 1) - 1] == "writes: []"
    assert _body(out) == _body(TEXT)


def test_remove_field() -> None:
    out = remove_field(TEXT, "depends_on")
    assert "depends_on" not in out
    assert "  - a" not in out
    assert _body(out) == _body(TEXT)
    assert remove_field(TEXT, "writes") == TEXT


def test_new_task_text() -> None:
    text = new_task_text(
        {"id": "X-1", "title": "a: b", "status": "todo", "workflow": None, "depends_on": []},
        "Udělat věc.\n",
    )
    data, body = parse_frontmatter(text)
    assert data == {"id": "X-1", "title": "a: b", "status": "todo", "depends_on": []}
    assert "## Zadání\nUdělat věc.\n" in body
    assert "## Běhy" in body
    assert "## Zadání\n\n## Běhy" in new_task_text({"id": "X-1"}, "")


def test_slugify() -> None:
    assert slugify("Migrace hlavičky faktury") == "migrace-hlavicky-faktury"
    assert slugify("  ###  ") == ""
    assert slugify("") == ""
    long = slugify("a" * 39 + " bcd")
    assert len(long) <= 40
    assert not long.endswith("-")
