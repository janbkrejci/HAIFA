# Runs and review

A run executes a workflow in a worktree and branch `factory/<task-id>-<n>`.

## Starting and monitoring <!-- section:spusteni-a-sledovani -->

**Run** (`factory task run ID`) shows the workflow, allowed writes, uncommitted-change warnings, **Harness for this run** and a note. Repository settings on [Overview](#/overview) control auto continue. Running tasks and tasks with an open PR cannot start again. Unsatisfied dependencies cannot be bypassed; with `stacked_prs`, a stacked start is allowed when all dependencies are awaiting merge in open PRs.

The **Runs** tab has **Active** and **Archived** runs, **Costs** and **Chain** panels. Select a phase in details to open prompts, output and live events. **Pause** finishes the phase and waits, **Resume** starts the next phase, **Stop** ends the run (the worktree remains).

## Resuming <!-- section:navazani -->

The failure card shows the type, reason and details. **Continue** (**Retry** in details, `factory task retry ID`) resumes the same branch: completed phases are not repeated; base is updated and the branch rebased first. **Run** starts over; **Cancel task** cancels the task.

**Allow these paths and continue** (`factory task retry ID --allow-writes`) expands writes in base. It cannot allow `protected_files`, the backlog or the main checkout. **Done** for `nothing_to_do` records the reason and done status without a PR; the same applies to evidenced `already_done`. **Continue with another harness** (`factory task retry ID --harness NAME`) resumes with an allowed harness. Automatic switching prefers the project's `quota_switch`, then `fallback` from `.factory/local.yaml` or `.factory/agents.yaml`; `quota_switch_back` returns new runs higher in the chain. Details and the PR show switches.

Cleanup runs automatically; trigger it manually with `factory task clean --json`. It removes unnecessary worktrees and branches, including remote branches; it preserves active runs, open PRs, branches in use, the last failed/stopped todo run and uncommitted worktrees. Errors are reported as warnings.

## Follow-ups <!-- section:follow-upy -->

Agents report work outside scope as tasks in **TODO**, with writes and a workflow; human work as **For a person**. A prerequisite adds `depends_on` and ends the run as `blocked`.

## Local automations <!-- section:mistni-automatizace -->

Auto continue and auto merge are off by default. Enable them on Overview or with `factory config local set --auto-continue on --repo PATH` or `--auto-merge on`. Changes apply immediately in the local HAIFA_HOME without a commit. Enabling does not start work. Disabling continue lets accepted runs finish and prevents further starts and retries; `--auto` cannot override it. See the updates chapter for importing legacy choices.

## Approval and CI <!-- section:schvaleni-a-ci -->

A successful run opens a PR; the task is **Awaiting review**. PR details on the **Review** tab show the description, tests, reviewer verdict and diff.

**Approve** (`factory task approve ID`) commits `status: done`, waits for CI and merges the PR. Up to two `ci-fix` runs repair failing CI; after failure or 30 minutes, the PR stays open. **Approved, awaiting CI** means waiting, **Awaiting review** means failure, **Done** means merged. Approval can be repeated. Azure receives an approval vote; GitHub receives a review only with `github_approver`.

**Return with a note** (`factory task return ID --note "…"`) starts a new run on the same branch. **Resolve conflict with base** or **Rebase onto base** (`factory task resolve ID`) rebases the PR with the `resolve` workflow.

## Auto-merge <!-- section:auto-merge -->

Local auto merge approves and merges PRs after approved review and passing CI. It tries `resolve-reviewed` once for a conflict; otherwise it shows **Awaiting review**.

A chain stopped at `not_merged` resumes once after a manual merge through **Approve** or the hosting service (after refreshing the dashboard). A merged task does not run again; reconcile todo status with `factory backlog sync` and merge the sync PR.

## Concurrency and stacked PRs <!-- section:soubeh-a-stacked-pr -->

`max_parallel_runs` sets repository slots; both runs and open PRs occupy slots. Only tasks with non-overlapping writes run concurrently. With `stacked_prs: true`, a task awaiting a dependency's PR starts from its branch and merges after it.
