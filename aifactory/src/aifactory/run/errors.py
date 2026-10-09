"""The one error a task run raises before anything was created."""

from __future__ import annotations


class TaskRunError(Exception):
    """The task cannot be started (or its runs cannot be read). Nothing was created."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
