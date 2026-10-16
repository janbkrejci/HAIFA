"""The ``fallback`` key: the harness a run continues on when its harness runs out of quota.

Written as ``fallback: {harness, model?, thinking?}`` in three places; the first one set
wins (``run/fallback.py``):

1. ``.factory/local.yaml`` ``fallback``: this computer, for every agent of every run.
2. ``.factory/agents.yaml`` on the agent whose harness reported the exhausted quota.
3. ``.factory/agents.yaml`` ``defaults.fallback``: every agent of the roster.

Without ``model`` the fallback takes the model this computer chose for that harness
(``harnesses.json``), else the harness's preset model; without ``thinking`` the
computer's level for it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from aifactory.harness import canonical


class Fallback(BaseModel):
    """``fallback`` of an agent, of the roster's defaults or of ``local.yaml``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    harness: str
    model: str | None = None
    thinking: str | None = None

    @field_validator("harness")
    @classmethod
    def _harness(cls, value: str) -> str:
        return canonical(value.strip())

    @field_validator("model", "thinking")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    def override(self) -> dict[str, str]:
        """The run override (``harness``, ``model``, ``thinking``) this fallback asks for."""
        values = {"harness": self.harness, "model": self.model, "thinking": self.thinking}
        return {key: value for key, value in values.items() if value}
