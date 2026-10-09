"""Workflow conditions: ``when``, ``until`` and ``accept``.

A condition reads fields of the typed envelopes earlier steps returned
(``test.passed``, ``review.approved``, ``revise.ran``), combined with ``and``,
``or``, ``not``, parentheses and comparisons against literals. It is parsed by a
small recursive-descent parser into a tree and evaluated by walking that tree;
nothing is ever evaluated as Python.
"""

from __future__ import annotations

import operator
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from aifactory.engine.role_registry import RAN_FIELD

__all__ = [
    "And",
    "Cmp",
    "Condition",
    "ConditionError",
    "Lit",
    "Node",
    "Not",
    "Or",
    "Ref",
    "evaluate",
    "parse_condition",
    "refs",
    "truthy",
]


class ConditionError(ValueError):
    """A condition does not parse."""

    def __init__(self, message: str, pos: int) -> None:
        self.pos = pos
        super().__init__(f"{message} (at column {pos + 1})")


@dataclass(frozen=True)
class Ref:
    step: str
    field: str


@dataclass(frozen=True)
class Lit:
    value: str | int | float | bool | None


@dataclass(frozen=True)
class Not:
    operand: Node


@dataclass(frozen=True)
class And:
    left: Node
    right: Node


@dataclass(frozen=True)
class Or:
    left: Node
    right: Node


@dataclass(frozen=True)
class Cmp:
    op: str
    left: Node
    right: Node


Node = Ref | Lit | Not | And | Or | Cmp

KEYWORDS = frozenset({"and", "or", "not", "true", "false", "null"})
_CMP_OPS: dict[str, Callable[[Any, Any], Any]] = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}
_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<op>==|!=|<=|>=|<|>)
  | (?P<lparen>\()
  | (?P<rparen>\))
  | (?P<number>\d+(?:\.\d+)?)
  | (?P<string>'[^']*'|"[^"]*")
  | (?P<name>[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*)
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class _Tok:
    kind: str
    text: str
    pos: int


def _tokenize(source: str) -> list[_Tok]:
    tokens: list[_Tok] = []
    pos = 0
    while pos < len(source):
        match = _TOKEN_RE.match(source, pos)
        if match is None:
            char = source[pos]
            if char in "'\"":
                raise ConditionError("unterminated string", pos)
            raise ConditionError(f"unexpected character {char!r}", pos)
        kind = match.lastgroup or ""
        if kind != "ws":
            tokens.append(_Tok(kind, match.group(), pos))
        pos = match.end()
    tokens.append(_Tok("end", "", len(source)))
    return tokens


class _CondParser:
    def __init__(self, source: str) -> None:
        self.tokens = _tokenize(source)
        self.i = 0

    @property
    def tok(self) -> _Tok:
        return self.tokens[self.i]

    def keyword(self, word: str) -> bool:
        if self.tok.kind == "name" and self.tok.text == word:
            self.i += 1
            return True
        return False

    def parse(self) -> Node:
        if self.tok.kind == "end":
            raise ConditionError("empty condition", 0)
        node = self.or_()
        if self.tok.kind != "end":
            raise ConditionError(f"unexpected {self.tok.text!r}", self.tok.pos)
        return node

    def or_(self) -> Node:
        node = self.and_()
        while self.keyword("or"):
            node = Or(node, self.and_())
        return node

    def and_(self) -> Node:
        node = self.not_()
        while self.keyword("and"):
            node = And(node, self.not_())
        return node

    def not_(self) -> Node:
        if self.keyword("not"):
            return Not(self.not_())
        return self.cmp()

    def cmp(self) -> Node:
        node = self.atom()
        if self.tok.kind == "op":
            op = self.tok.text
            self.i += 1
            node = Cmp(op, node, self.atom())
        return node

    def atom(self) -> Node:
        tok = self.tok
        if tok.kind == "end":
            raise ConditionError("expected a value, found the end of the condition", tok.pos)
        self.i += 1
        if tok.kind == "lparen":
            node = self.or_()
            if self.tok.kind != "rparen":
                raise ConditionError("expected ')'", self.tok.pos)
            self.i += 1
            return node
        if tok.kind == "number":
            return Lit(float(tok.text) if "." in tok.text else int(tok.text))
        if tok.kind == "string":
            return Lit(tok.text[1:-1])
        if tok.kind == "name":
            if tok.text in ("true", "false"):
                return Lit(tok.text == "true")
            if tok.text == "null":
                return Lit(None)
            parts = tok.text.split(".")
            if len(parts) != 2:
                raise ConditionError(
                    f"{tok.text!r} is not a reference — write <step>.<field>, e.g. test.passed",
                    tok.pos,
                )
            if parts[0] in KEYWORDS or parts[1] in KEYWORDS:
                raise ConditionError(f"{tok.text!r} uses a keyword as a name", tok.pos)
            return Ref(parts[0], parts[1])
        raise ConditionError(f"unexpected {tok.text!r}", tok.pos)


@dataclass(frozen=True)
class Condition:
    source: str
    node: Node


def parse_condition(source: object) -> Condition:
    """Parse ``source`` into a condition; raise ``ConditionError`` when it does not parse."""
    if isinstance(source, bool):
        return Condition("true" if source else "false", Lit(source))
    if not isinstance(source, str):
        raise ConditionError("a condition must be a string", 0)
    return Condition(source, _CondParser(source).parse())


def refs(node: Node) -> list[Ref]:
    """Every ``<step>.<field>`` reference in ``node``, in source order."""
    if isinstance(node, Ref):
        return [node]
    if isinstance(node, Lit):
        return []
    if isinstance(node, Not):
        return refs(node.operand)
    return [*refs(node.left), *refs(node.right)]


def evaluate(node: Node, ns: Mapping[str, Mapping[str, Any]]) -> Any:
    """Evaluate against step results. A step that never ran reads None (``ran``: False)."""
    if isinstance(node, Ref):
        result = ns.get(node.step)
        if result is None:
            return False if node.field == RAN_FIELD else None
        return result.get(node.field)
    if isinstance(node, Lit):
        return node.value
    if isinstance(node, Not):
        return not evaluate(node.operand, ns)
    if isinstance(node, And):
        return evaluate(node.left, ns) and evaluate(node.right, ns)
    if isinstance(node, Or):
        return evaluate(node.left, ns) or evaluate(node.right, ns)
    try:
        return bool(_CMP_OPS[node.op](evaluate(node.left, ns), evaluate(node.right, ns)))
    except TypeError:
        return False


def truthy(condition: Condition | None, ns: Mapping[str, Mapping[str, Any]]) -> bool:
    """A missing condition holds; otherwise Python truthiness of its value."""
    return True if condition is None else bool(evaluate(condition.node, ns))
