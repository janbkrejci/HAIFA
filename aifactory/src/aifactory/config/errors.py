"""Configuration problems, collected across every file before raising."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigIssue:
    """One problem: where (a source label, see ``ConfigSource.label``) and what."""

    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message}


class ConfigError(Exception):
    """The configuration is invalid or unreadable. ``issues`` lists every problem.

    ``code`` is the ``error.code``: ``invalid_config``, or ``format_unsupported`` for a
    manifest format this HAIFA does not know.
    """

    def __init__(self, issues: list[ConfigIssue], code: str = "invalid_config") -> None:
        self.issues = list(issues)
        self.code = code
        super().__init__("\n".join(f"{i.path}: {i.message}" for i in self.issues))
