"""Provider ``local``: a pull request is a branch, merging is a local merge into base.

With a remote configured the branch and base are pushed there; without one
nothing leaves the repository. Mergeability is computed locally, so an open PR
is never ``unknown``.
"""

from __future__ import annotations

from pathlib import Path

from aifactory.providers import git
from aifactory.providers.base import (
    CLOSED,
    CONFLICT,
    MERGEABLE,
    MERGED,
    OPEN,
    GitProvider,
    MergeFailed,
    ProviderError,
    PrStatus,
    PullRequest,
)


class LocalProvider(GitProvider):
    name = "local"

    def _has_remote(self) -> bool:
        return git.has_remote(self.root, self.settings.remote)

    def _url(self, branch: str) -> str:
        url = git.remote_url(self.root, self.settings.remote)
        return f"{url}#{branch}" if url else f"local:{branch}"

    def push(self, worktree: Path, branch: str, lease: str | None = None) -> None:
        if self._has_remote():
            git.push(worktree, self.settings.remote, branch, lease=lease)

    def create_pr(self, branch: str, title: str, body: str) -> PullRequest:
        return PullRequest(
            id=branch, url=self._url(branch), branch=branch, base=self.settings.base, title=title
        )

    def status(self, pr: PullRequest) -> PrStatus:
        tip = git.rev_parse(self.root, f"refs/heads/{pr.branch}")
        if tip is None:
            return PrStatus(CLOSED)
        base = git.rev_parse(self.root, f"refs/heads/{self.settings.base}")
        if base is None:
            raise ProviderError("unknown_base", f"base {self.settings.base!r} does not exist")
        if git.is_ancestor(self.root, tip, base):
            return PrStatus(MERGED, head_sha=tip)
        clean = git.trial_merge(self.root, base, tip)
        return PrStatus(OPEN, MERGEABLE if clean else CONFLICT, head_sha=tip)

    def merge(
        self, pr: PullRequest, head_sha: str, subject: str, strategy: str | None = None
    ) -> str | None:
        chosen = self._strategy(strategy)
        base = self.settings.base
        old = git.rev_parse(self.root, f"refs/heads/{base}")
        if old is None:
            raise MergeFailed("merge_failed", f"base {base!r} does not exist")
        tip = git.rev_parse(self.root, f"refs/heads/{pr.branch}")
        if tip != head_sha:
            raise MergeFailed("merge_failed", f"{pr.branch} moved: {tip} != {head_sha}")
        try:
            new = git.merge_commit(self.root, old, tip, chosen, subject)
        except ProviderError as exc:
            code = "conflict" if exc.code == "conflict" else "merge_failed"
            raise MergeFailed(code, exc.message) from exc
        git.advance_branch(self.root, base, new, old, command="task approve")
        if self._has_remote():
            git.push(self.root, self.settings.remote, base)
        return new

    def update_pr(self, pr: PullRequest, body: str) -> None:
        return None  # the description lives only in task_prs.body

    def comment(self, pr: PullRequest, body: str) -> None:
        return None  # nobody to send it to
