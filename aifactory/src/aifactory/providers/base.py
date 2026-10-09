"""The ``GitProvider`` interface: pull requests on some git hosting.

A provider opens, inspects, merges and comments pull requests. Pushing a branch
is plain git (``providers.git.push``). The state of a PR (``open``, ``merged``,
``closed``) is separate from its mergeability (``mergeable``, ``conflict``,
``unknown``), which only means something for an open PR. ``checks`` reports the
CI checks of a PR on the hosting (``none`` when the provider has none).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from pathlib import Path

from aifactory.config.settings import ProjectSettings

OPEN, MERGED, CLOSED = "open", "merged", "closed"
PR_STATES: tuple[str, ...] = (OPEN, MERGED, CLOSED)
MERGEABLE, CONFLICT, UNKNOWN = "mergeable", "conflict", "unknown"
MERGEABILITY: tuple[str, ...] = (MERGEABLE, CONFLICT, UNKNOWN)
STRATEGIES: tuple[str, ...] = ("squash", "merge")
BRANCH_PREFIX = "factory/"
CHECKS_PASSING, CHECKS_PENDING = "passing", "pending"
CHECKS_FAILING, CHECKS_NONE = "failing", "none"


class ProviderError(Exception):
    """A git or hosting operation failed; ``code`` says which kind."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class MergeFailed(ProviderError):
    """The merge did not happen; ``code`` is ``merge_failed`` or ``conflict``."""


@dataclass(frozen=True)
class PullRequest:
    id: str  # github: the PR number; local: the branch name
    url: str
    branch: str
    base: str
    title: str


@dataclass(frozen=True)
class PrStatus:
    state: str  # OPEN | MERGED | CLOSED
    mergeability: str = UNKNOWN  # MERGEABLE | CONFLICT | UNKNOWN; UNKNOWN unless OPEN
    head_sha: str | None = None
    merge_sha: str | None = None


@dataclass(frozen=True)
class ChecksStatus:
    state: str  # CHECKS_PASSING | CHECKS_PENDING | CHECKS_FAILING | CHECKS_NONE
    failing: tuple[str, ...] = ()  # names of the red checks


def task_id_from_branch(branch: str) -> str | None:
    """``factory/<task-id>-<n>`` -> ``<task-id>``; anything else -> None."""
    if not branch.startswith(BRANCH_PREFIX):
        return None
    stem, sep, suffix = branch.removeprefix(BRANCH_PREFIX).rpartition("-")
    if not sep or not stem or not suffix.isdigit():
        return None
    return stem


class GitProvider(abc.ABC):
    name: str = ""

    def __init__(self, root: Path, settings: ProjectSettings) -> None:
        self.root = root
        self.settings = settings

    def push(self, worktree: Path, branch: str, lease: str | None = None) -> None:
        """Push `branch`; with `lease` (the old tip) as a force-with-lease push."""
        from aifactory.providers import git

        git.push(worktree, self.settings.remote, branch, lease=lease)

    def _strategy(self, strategy: str | None) -> str:
        """`strategy` or the configured one (default squash, D9); reject unknown ones."""
        chosen = strategy if strategy is not None else self.settings.merge_strategy
        if chosen not in STRATEGIES:
            raise ProviderError(
                "invalid_strategy", f"unknown merge strategy {chosen!r} (use squash or merge)"
            )
        return chosen

    @abc.abstractmethod
    def create_pr(self, branch: str, title: str, body: str) -> PullRequest: ...

    def find_open_pr(self, branch: str) -> PullRequest | None:
        """The open PR the hosting already has for `branch`, or None.

        ``publish`` adopts it instead of opening a second one (an earlier publish that
        opened the PR but did not record it). Providers that cannot tell return None.
        """
        return None

    @abc.abstractmethod
    def status(self, pr: PullRequest) -> PrStatus: ...

    def checks(self, pr: PullRequest) -> ChecksStatus:
        """CI checks of `pr` on the hosting; providers without checks report ``none``."""
        return ChecksStatus(CHECKS_NONE)

    def approve(self, pr: PullRequest, head_sha: str) -> bool:
        """Submit a host approval for the expected head; True only when actually sent.

        Local has no reviews; GitHub disallows an author's own APPROVE review.
        Providers without supported self-approval retain their existing merge behavior.
        """
        return False

    @abc.abstractmethod
    def merge(
        self, pr: PullRequest, head_sha: str, subject: str, strategy: str | None = None
    ) -> str | None:
        """Merge `pr` if its head is still `head_sha`; return the merge commit when known.

        Raises ``MergeFailed`` with ``code == "conflict"`` on a conflict and
        ``code == "merge_failed"`` on any other failure.
        """

    @abc.abstractmethod
    def update_pr(self, pr: PullRequest, body: str) -> None:
        """Replace the description of `pr` with `body`."""

    @abc.abstractmethod
    def comment(self, pr: PullRequest, body: str) -> None: ...
