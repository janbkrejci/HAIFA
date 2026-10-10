"""The checks a tester agent chose for a run; argv is always executed without a shell."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
Argv = Annotated[list[Text], Field(min_length=1)]
Coverage = Literal["full", "scoped", "none"]
MAX_CHECKS = 32


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Text
    argv: Argv
    timeout: Annotated[int, Field(gt=0)] | None = None


def plan_problems(coverage: str, checks: list[Check]) -> list[str]:
    """What makes a plan unusable; empty when it can run."""
    problems = []
    if bool(checks) != (coverage in ("full", "scoped")):
        problems.append("coverage `none` has no checks; `full` and `scoped` need at least one")
    if len(checks) > MAX_CHECKS:
        problems.append(f"at most {MAX_CHECKS} checks")
    names = [c.name for c in checks]
    if len(set(names)) != len(names):
        problems.append("check names must be unique")
    if any("/" in n or "\\" in n or n in (".", "..") for n in names):
        problems.append("check names must be safe file names (no slashes)")
    return problems


class Evidence(BaseModel):
    """What the `test` step ran, kept on its result for the reviewer and the PR body."""

    model_config = ConfigDict(extra="forbid")

    coverage: Coverage
    reason: Text
    executed: Annotated[int, Field(ge=0)]
    commands: list[str] = Field(default_factory=list)
