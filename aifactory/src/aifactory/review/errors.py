"""The one error approve, return and clean raise."""

from __future__ import annotations


class ReviewError(Exception):
    """A task PR cannot be approved, returned or cleaned; ``code`` says why."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
