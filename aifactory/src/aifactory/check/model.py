"""What ``factory check`` reports: findings, rules, rule groups and the report."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from aifactory.onboard.state import RepoAction, RepoStateName

if TYPE_CHECKING:
    from aifactory.check.context import CheckContext

Scope = Literal["repo", "machine", "library"]
Severity = Literal["error", "warning", "info"]
Action = Literal["init", "update", "export", "config_commit", "config_pull", "onboard", "adopt"]
# the onboarding state of the repo (AR30), see ``aifactory.onboard.state``
State = RepoStateName

SEVERITIES: tuple[Severity, ...] = ("error", "warning", "info")


@dataclass(frozen=True)
class Finding:
    """One problem: ``repo`` findings are fixed and committed, ``machine`` ones locally,
    ``library`` ones in the library in ``$HAIFA_HOME``.

    ``fix`` says in words what to do; ``action`` names the fix command (dashboard/CLI)
    or is None when the fix is manual.
    """

    code: str
    scope: Scope
    severity: Severity
    message: str
    fix: str | None = None
    action: Action | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "scope": self.scope,
            "severity": self.severity,
            "message": self.message,
            "fix": self.fix,
            "action": self.action,
        }


@dataclass(frozen=True)
class Rule:
    """One check. ``needs_install=False`` runs it even when the repo has no factory.

    ``needs_repo=False`` (machine and library rules) runs it outside a git repository
    too; outside a repository only such rules run.
    """

    name: str
    run: Callable[[CheckContext], Iterable[Finding]]
    needs_install: bool = True
    needs_repo: bool = True


@dataclass(frozen=True)
class RuleGroup:
    """A named list of rules; findings of a failing rule get the group's scope."""

    name: str
    rules: tuple[Rule, ...]
    scope: Scope = "repo"


@dataclass(frozen=True)
class CheckReport:
    """The result; outside a git repository (``in_repo`` false) the repo fields are None."""

    repo: str | None
    state: State | None
    action: RepoAction | None
    base: str | None
    commit: str | None
    remote: str | None
    ahead: int | None
    behind: int | None
    offline: bool
    groups: tuple[str, ...]
    findings: tuple[Finding, ...]
    backlog: dict[str, int] = field(default_factory=dict)
    sssf_leftover: bool = False
    alternate_rosters: bool = False
    onboarding: dict[str, Any] | None = None
    in_repo: bool = True

    @property
    def ok(self) -> bool:
        """No finding with severity ``error``."""
        return not any(f.severity == "error" for f in self.findings)

    def counts(self) -> dict[str, int]:
        result: dict[str, int] = dict.fromkeys(SEVERITIES, 0)
        for finding in self.findings:
            result[finding.severity] += 1
        return result

    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    def to_json(self) -> dict[str, Any]:
        return {
            "in_repo": self.in_repo,
            "repo": self.repo,
            "state": self.state,
            "action": self.action,
            "sssf_leftover": self.sssf_leftover,
            "alternate_rosters": self.alternate_rosters,
            "onboarding": self.onboarding,
            "base": self.base,
            "commit": self.commit,
            "remote": self.remote,
            "ahead": self.ahead,
            "behind": self.behind,
            "offline": self.offline,
            "ok": self.ok,
            "counts": self.counts(),
            "groups": list(self.groups),
            "backlog": dict(self.backlog),
            "findings": [f.to_dict() for f in self.findings],
        }
