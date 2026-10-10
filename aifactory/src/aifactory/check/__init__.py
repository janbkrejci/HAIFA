"""``factory check``: will factory run in this repository and on this machine?

The check only reads: nothing is written to the repository, the trace DB, the library
or the home directory, and nothing is fetched (ahead/behind come from local
remote-tracking refs). Findings are split by ``scope``: ``repo`` (fix and commit to
base), ``machine`` (fix locally) and ``library`` (fix in the library in ``$HAIFA_HOME``).

Outside a git repository (no ``--repo`` given) only the rules with ``needs_repo=False``
run: the machine and the library. ``--offline`` skips every call to the hosting and to
the harness logins (``gh auth status``, ``az account show``, ``claude auth status``,
``codex login status``, ``pi auth check``, ``pi --list-models``).

Rules are registered in ``RULE_GROUPS``, a list of ``RuleGroup``; another group (for
example onboarding or harness logins) is added with ``RULE_GROUPS.append(...)``,
without touching the CLI. A rule that raises an expected error (git, configuration,
I/O) becomes a ``check_failed`` finding instead of stopping the check.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

from aifactory.check.context import CheckContext, NotARepositoryError, main_checkout
from aifactory.check.library_rules import LIBRARY_GROUP
from aifactory.check.machine import Machine, Probe, SystemMachine
from aifactory.check.machine_rules import MACHINE_GROUP
from aifactory.check.model import (
    Action,
    CheckReport,
    Finding,
    Rule,
    RuleGroup,
    Scope,
    Severity,
    State,
)
from aifactory.check.repo_rules import REPO_GROUP
from aifactory.config.errors import ConfigError
from aifactory.library.store import LibraryStoreError
from aifactory.providers.base import ProviderError

RULE_GROUPS: list[RuleGroup] = [REPO_GROUP, MACHINE_GROUP, LIBRARY_GROUP]

_EXPECTED = (
    ConfigError,
    LibraryStoreError,
    ProviderError,
    OSError,
    RuntimeError,
    ValueError,
    subprocess.SubprocessError,
)


def default_machine() -> Machine:
    return SystemMachine()


def _run_rule(ctx: CheckContext, group: RuleGroup, rule: Rule) -> list[Finding]:
    try:
        return list(rule.run(ctx))
    except _EXPECTED as exc:
        return [
            Finding(
                "check_failed",
                group.scope,
                "warning",
                f"{rule.name}: {exc}",
                "the rule could not finish; run the check again or look at the message",
            )
        ]


def run_check(
    repo: Path,
    *,
    offline: bool = False,
    machine: Machine | None = None,
    groups: Sequence[RuleGroup] | None = None,
    require_repo: bool = True,
) -> CheckReport:
    """Run every rule of ``groups`` (default: ``RULE_GROUPS`` at call time) on ``repo``.

    Raises ``NotARepositoryError`` when ``repo`` is not inside a git repository and
    ``require_repo`` is true; otherwise only the machine and library rules run there.
    """
    ctx = CheckContext(
        repo, offline=offline, machine=machine or default_machine(), require_repo=require_repo
    )
    selected = list(RULE_GROUPS if groups is None else groups)
    if not ctx.in_repo:
        return _outside_report(ctx, selected)
    installed = ctx.installed
    findings: list[Finding] = []
    for group in selected:
        for rule in group.rules:
            if rule.needs_install and not installed:
                continue
            findings.extend(_run_rule(ctx, group, rule))
    counts = ctx.ahead_behind if installed else None
    try:
        backlog = ctx.backlog_summary if installed else {}
    except _EXPECTED:
        backlog = {}
    remote = ctx.settings.remote if ctx.settings.remote in ctx.remotes else None
    return CheckReport(
        repo=str(ctx.main),
        state=ctx.state.state,
        action=ctx.state.action,
        base=ctx.base,
        commit=ctx.commit,
        remote=remote,
        ahead=counts[0] if counts else None,
        behind=counts[1] if counts else None,
        offline=offline,
        groups=tuple(group.name for group in selected),
        findings=tuple(findings),
        backlog=backlog,
        onboarding=ctx.state.onboarding,
    )


def _outside_report(ctx: CheckContext, selected: list[RuleGroup]) -> CheckReport:
    """Outside a git repository: only the rules that need no repo."""
    findings: list[Finding] = []
    for group in selected:
        for rule in group.rules:
            if not rule.needs_repo:
                findings.extend(_run_rule(ctx, group, rule))
    return CheckReport(
        repo=None,
        state=None,
        action=None,
        base=None,
        commit=None,
        remote=None,
        ahead=None,
        behind=None,
        offline=ctx.offline,
        groups=tuple(group.name for group in selected),
        findings=tuple(findings),
        in_repo=False,
    )


__all__ = [
    "LIBRARY_GROUP",
    "RULE_GROUPS",
    "Action",
    "CheckContext",
    "CheckReport",
    "Finding",
    "Machine",
    "NotARepositoryError",
    "Probe",
    "Rule",
    "RuleGroup",
    "Scope",
    "Severity",
    "State",
    "SystemMachine",
    "default_machine",
    "main_checkout",
    "run_check",
]
