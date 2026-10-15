"""Pull requests of task runs: publish, approve, return, resolve, clean.

* ``publish``: after a run meets ``accept`` its branch is pushed and the PR is
  opened (or its body updated) with the task, agent summaries, gate and test
  results, the reviewer's verdict and the costs (``prbody``); the PR is a row in
  ``task_prs``.
* ``approve_task`` (``factory task approve``): one commit on the PR branch with
  ``status: done`` and a line in ``## Běhy``, then the merge; ``base`` is caught
  up with the remote and the branch's worktrees are removed. Before the merge the
  provider sends a host approval where it can: an Azure vote, or a GitHub APPROVE
  review as ``github_approver`` when that is set.
* ``try_auto_merge`` (``automerge``): with ``auto_merge: true`` the PR of a
  succeeded run is approved and merged like ``task approve`` (``merged_by``
  ``auto-merge``) when the workflow has a review phase, the last review approved
  with no blocking or unmet item, the PR merges cleanly and no check is red;
  otherwise the PR stays open and ``task_prs.auto_merge_error`` says why.
* ``publish_task`` (``factory task publish``): for the last succeeded run whose push
  or PR failed, push and open the PR again (or adopt the one the hosting has).
* ``return_task`` (``factory task return``): a new run on the same branch with
  the note in the prompt; the PR body is updated.
* ``resolve_task`` (``factory task resolve``): a new run of the workflow
  ``resolve`` on the PR branch: rebase onto the current base, the agent settles
  conflicts in the conflicted files only, the suite runs, force-with-lease push
  and the PR is updated. A failed run leaves the branch as it was.
* ``clean_worktrees`` (``factory task clean``): worktrees of runs whose PR is
  merged or closed, and of abandoned runs, are removed.
* ``sync_backlog`` (``factory backlog sync``): tasks whose PR was merged outside
  factory get ``status: done`` in one PR from a ``factory-sync/<n>`` branch
  (never a commit on ``base``); the sync PR is a row in ``sync_prs``.
* ``refresh_prs``: only the provider states of open task and sync PRs are
  refreshed; the dashboard runs it in the background.

A PR the provider reports as closed or merged is recorded so in ``task_prs``;
approving or returning it fails with ``pr_not_open``.
"""

from aifactory.review.automerge import (
    AutoMergeResult,
    auto_merge_enabled,
    hosting_blocker,
    last_review,
    review_blocker,
    try_auto_merge,
    workflow_has_review,
)
from aifactory.review.errors import ReviewError
from aifactory.review.flow import (
    ApproveResult,
    CleanResult,
    approve_task,
    clean_worktrees,
    publish_task,
    resolve_task,
    return_task,
)
from aifactory.review.prbody import pr_body, pr_title
from aifactory.review.publish import PublishResult, publish
from aifactory.review.sync import SyncResult, refresh_prs, sync_backlog

__all__ = [
    "ApproveResult",
    "AutoMergeResult",
    "CleanResult",
    "PublishResult",
    "ReviewError",
    "SyncResult",
    "approve_task",
    "auto_merge_enabled",
    "clean_worktrees",
    "hosting_blocker",
    "last_review",
    "pr_body",
    "pr_title",
    "publish",
    "publish_task",
    "refresh_prs",
    "resolve_task",
    "return_task",
    "review_blocker",
    "sync_backlog",
    "try_auto_merge",
    "workflow_has_review",
]
