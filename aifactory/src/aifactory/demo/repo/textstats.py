"""Simple statistics of a text: words and lines."""

from __future__ import annotations

import re

__all__ = ["line_count", "word_count", "words"]

_WORD = re.compile(r"[^\W_]+(?:['-][^\W_]+)*")


def words(text: str) -> list[str]:
    """The words of `text` in order, lower-cased; punctuation is not part of a word."""
    return [match.group(0).lower() for match in _WORD.finditer(text)]


def word_count(text: str) -> int:
    """How many words `text` has."""
    return len(words(text))


def line_count(text: str) -> int:
    """How many lines `text` has; a trailing newline does not start a new line."""
    return len(text.splitlines())
