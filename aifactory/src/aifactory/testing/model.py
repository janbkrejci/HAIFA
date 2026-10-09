"""Versioned selector protocol; argv is always executed without a shell."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
Argv = Annotated[list[Text], Field(min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    @field_validator("version", mode="before", check_fields=False)
    @classmethod
    def strict_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("version must be an integer")
        return value


class Check(StrictModel):
    name: Text
    argv: Argv
    timeout: Annotated[int, Field(gt=0)] | None = None


class Plan(StrictModel):
    version: Literal[1] = 1
    coverage: Literal["full", "scoped", "none", "deferred"]
    reason: Text
    checks: Annotated[list[Check], Field(max_length=32)]

    @model_validator(mode="after")
    def coherent(self) -> "Plan":
        if bool(self.checks) != (self.coverage in ("full", "scoped")):
            raise ValueError("coverage and checks disagree")
        if len({c.name for c in self.checks}) != len(self.checks):
            raise ValueError("duplicate check names")
        if any("/" in c.name or "\\" in c.name or c.name in (".", "..") for c in self.checks):
            raise ValueError("check names must be safe artifact names")
        return self


class Context(StrictModel):
    version: Literal[1] = 1
    repo_root: Text
    baseline: Text
    head: Text
    changed_paths: list[str]
    force_full: bool
    fallback_argv: Argv
    test_timeout: Annotated[int, Field(gt=0)]
    defer_to: Text | None = None


class Evidence(StrictModel):
    coverage: Literal["full", "scoped", "none", "deferred", "legacy"]
    reason: Text
    executed: Annotated[int, Field(ge=0)]
    defer_to: Text | None = None
    fallback_reason: str | None = None
