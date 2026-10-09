"""Conditions parse into a tree and read only step results; no Python is evaluated."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

import aifactory.workflow
from aifactory.workflow.conditions import (
    And,
    Cmp,
    ConditionError,
    Lit,
    Not,
    Or,
    Ref,
    evaluate,
    parse_condition,
    refs,
    truthy,
)

NS: dict[str, dict[str, Any]] = {
    "a": {"x": False, "n": 3, "s": "ok", "ran": True},
    "b": {"y": True, "ran": True},
    "c": {"z": True, "ran": True},
}


def ev(source: str, ns: dict[str, dict[str, Any]] = NS) -> Any:
    return evaluate(parse_condition(source).node, ns)


def test_precedence_not_and_or() -> None:
    node = parse_condition("not a.x or b.y and c.z").node
    assert node == Or(Not(Ref("a", "x")), And(Ref("b", "y"), Ref("c", "z")))
    assert ev("not a.x or b.y and c.z") is True
    assert ev("a.x or b.y and not c.z") is False


def test_parentheses_change_grouping() -> None:
    assert ev("not (a.x or b.y)") is False
    assert ev("(a.x or b.y) and c.z") is True


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a.n == 3", True),
        ("a.n != 3", False),
        ("a.n < 4", True),
        ("a.n <= 3", True),
        ("a.n > 3", False),
        ("a.n >= 2.5", True),
        ("a.s == 'ok'", True),
        ('a.s != "ok"', False),
        ("a.x == false", True),
        ("b.y == true", True),
        ("a.missing == null", True),
    ],
)
def test_comparisons_and_literals(source: str, expected: bool) -> None:
    assert ev(source) is expected


def test_comparison_node() -> None:
    assert parse_condition("a.n >= 2").node == Cmp(">=", Ref("a", "n"), Lit(2))


def test_step_that_never_ran() -> None:
    assert ev("ghost.passed") is None
    assert ev("ghost.ran") is False
    assert ev("ghost.passed < 1") is False
    assert ev("not ghost.ran") is True


def test_truthy_defaults_to_true() -> None:
    assert truthy(None, {}) is True
    assert truthy(parse_condition("a.x"), NS) is False


def test_refs_lists_every_reference() -> None:
    node = parse_condition("test.passed and (review.approved or not revise.ran)").node
    assert refs(node) == [Ref("test", "passed"), Ref("review", "approved"), Ref("revise", "ran")]


@pytest.mark.parametrize(
    "source",
    [
        "__import__('os').system('x')",
        "a",
        "a.b.c",
        "a.b ==",
        '"unterminated',
        "a.b and",
        "",
        "a.b c.d",
        "(a.b",
        "a.and",
        "a.b; x",
    ],
)
def test_bad_conditions(source: str) -> None:
    with pytest.raises(ConditionError):
        parse_condition(source)


def test_no_python_evaluation_in_source() -> None:
    package = Path(aifactory.workflow.__file__).parent
    for source in sorted(package.glob("*.py")):
        text = source.read_text(encoding="utf-8")
        # builtins only: `re.compile(` is a method and fine
        found = re.findall(r"(?<![\w.])(?:eval|exec|compile|__import__)\(", text)
        assert found == [], source.name


def test_bool_literal_condition() -> None:
    assert parse_condition(True).source == "true"
    with pytest.raises(ConditionError):
        parse_condition(3)
