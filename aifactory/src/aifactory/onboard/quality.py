"""sssf ``adws/adw_modules/quality.py`` read with ``ast``; nothing runs (AR32, O3).

Every ``QualityCheckSpec(name=..., argv=..., timeout_seconds=...)`` call is a block. A
literal ``argv`` (list or tuple of strings) and a literal ``timeout_seconds`` (int) are
taken; ``argv=_placeholder(...)`` is a placeholder; anything else is not literal.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from aifactory.config.settings import check_timeout, split_command

_SPEC = "QualityCheckSpec"
_LITERAL_KEYS = ("argv", "timeout_seconds")


@dataclass(frozen=True)
class QualityBlock:
    name: str
    argv: tuple[str, ...] | None
    placeholder: bool
    timeout: int | None
    literal: bool


def _is_spec(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id == _SPEC
    return isinstance(func, ast.Attribute) and func.attr == _SPEC


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _argv(node: ast.expr | None) -> tuple[tuple[str, ...] | None, bool, bool]:
    """(argv, placeholder, literal)."""
    if node is None:
        return None, False, False
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "_placeholder":
            return None, True, True
    if isinstance(node, (ast.List, ast.Tuple)) and all(
        isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts
    ):
        values = [e.value for e in node.elts if isinstance(e, ast.Constant)]
        try:
            return split_command([str(v) for v in values]), False, True
        except ValueError:
            return None, False, False
    return None, False, False


def _timeout(node: ast.expr | None) -> tuple[int | None, bool]:
    """(timeout, literal)."""
    if node is None:
        return None, True
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        try:
            return check_timeout(node.value), True
        except ValueError:
            return None, False
    return None, False


def parse_quality(source: str) -> tuple[dict[str, QualityBlock], str | None]:
    """The blocks by name, and the error text when the source does not parse."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {}, f"not valid Python: {exc.msg} (line {exc.lineno})"
    blocks: dict[str, QualityBlock] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_spec(node):
            continue
        name = _keyword(node, "name")
        if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
            continue
        argv, placeholder, argv_literal = _argv(_keyword(node, "argv"))
        timeout, timeout_literal = _timeout(_keyword(node, "timeout_seconds"))
        blocks[name.value] = QualityBlock(
            name=name.value,
            argv=argv,
            placeholder=placeholder,
            timeout=timeout,
            literal=argv_literal and timeout_literal,
        )
    return blocks, None


def _normalized(source: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_spec(node):
            for keyword in node.keywords:
                if keyword.arg in _LITERAL_KEYS:
                    keyword.value = ast.Constant(None)
    return ast.dump(tree)


def same_as_stock(source: str, stock_source: str) -> bool:
    """True when ``source`` differs from the stock only in the ``argv``/``timeout_seconds``
    values of ``QualityCheckSpec`` calls (comments and formatting do not count)."""
    try:
        return _normalized(source) == _normalized(stock_source)
    except SyntaxError:
        return False


__all__ = ["QualityBlock", "parse_quality", "same_as_stock"]
