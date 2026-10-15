# HAIFA-REFINEMENT-T28: Auto-merge and approve wait for green CI and repair red CI in the same PR

## Goal

Both the operator approve (`factory task approve` and the dashboard) and auto-merge merge a PR only after its CI checks pass. The checks that count are those of the head that will be merged, which is the head after the `status: done` commit is pushed. Red checks start a bounded number of repair runs on the PR's own branch. The PR is merged once the checks are green. If they stay red, or never finish, the PR stays open and the reason goes into `task_prs.auto_merge_error`.

## Design overview

New module `aifactory/src/aifactory/review/ci.py`. It is the single "CI gate" that `approve_task` uses, so auto-merge gets the gate through `approve_task` too.

```
approve_task(repo, task_id, *, provider=None, merged_by=OPERATOR, code=None)
  loop:
    prepare   = done commit + push              (flow._prepare_approve, split out of _approve)
    checks    = ci.head_checks(provider, row, head)   # waits for checks of exactly `head`
    none/passing        -> flow._finish_approve (approve, merge, store, catch up, cleanup)
    pending (timeout)   -> record + raise ReviewError("checks_pending")
    failing, rounds left-> logs = provider.check_logs(...); ci-fix run on the branch; loop
    failing, no rounds  -> record + raise ReviewError("checks_failing", "... after N repair run(s)")
    ci-fix run failed   -> record + raise ReviewError("ci_fix_failed", ...)
```

"Record" means `store.update_pr(branch, auto_merge_error="<code>: <reason>")`. This applies to operator approve as well, so the dashboard and CLI show the reason the same way they show auto-merge errors today. A successful merge clears the error, as `_approve` already does.

## Changes

### 1. `providers/base.py` and `providers/github.py`

- Add `GitProvider.check_logs(self, pr: PullRequest, failing: tuple[str, ...]) -> dict[str, str]`. The default returns `{}`. Docstring: the output or log of each red check, so a repair run can read it; providers without logs return nothing.
- In `GitHubProvider.check_logs`, call `gh pr checks <id> --json name,bucket,link`. For every failing name, parse the job id from `link` (`.../actions/runs/<run>/job/<job>`), then call `gh run view --job <job> --log-failed`.
  - Keep only the last `CHECK_LOG_LINES = 150` lines per check.
  - If a check has no job link, or `gh` fails, use the `link` text (or "log unavailable: <stderr first line>"). It must never raise for a single check. Only a failure of the first `gh pr checks` call may raise `ProviderError`, and `ci.py` catches that.
- `AzureProvider` stays without checks. It inherits the defaults, so `checks` reports `none` and `check_logs` returns `{}`.

### 2. `review/ci.py` (new)

- Move these from `automerge.py` into `ci.py`, with the same names and values: `AUTO_MERGE_CHECKS_DELAY`, `AUTO_MERGE_CHECKS_TIMEOUT`, `AUTO_MERGE_CHECKS_APPEAR`, `_clock`, the `sleep` import and `settled_checks`. `automerge.py` re-exports `settled_checks` in `__all__` for API compatibility, but the module attributes that tests patch now live in `ci`.
- Add `CI_FIX_ROUNDS = 2`: the maximum number of repair runs per approve or auto-merge.
- Add `head_checks(provider, request, head) -> ChecksStatus`.
  - First wait until `provider.status(request).head_sha == head`, polling with `AUTO_MERGE_CHECKS_DELAY` and bounded by `AUTO_MERGE_CHECKS_APPEAR`. This step only applies when `reports_checks` is true and `head_sha` is not None. A hosting with no head info, or without checks, skips it.
  - Then call `settled_checks`. This stops checks of the previous head from counting.
  - If the head never shows up in time, return `ChecksStatus(CHECKS_PENDING)`.
- Add `ci_report(failing, logs) -> str`: the note text for the repair run, in English. It contains:
  - a heading `CI checks failed on this PR`;
  - one bullet per check name;
  - a section per check with its log in a fenced block;
  - the instruction: "Fix the cause in the code this task owns so these checks pass; do not disable or skip checks; do not edit CI configuration unless the failure is in it and it is in your allowed paths."

  Cap the total at `CI_REPORT_LIMIT = 16_000` characters by trimming the logs from their start.
- Add `run_ci_fix(repo, task_id, row, report, provider, code) -> TaskRunResult`. It calls `run_task(repo, task_id, note=report, force=True, code=code, provider=provider, branch=row.branch, workflow_name=CI_FIX_WORKFLOW, started_by=STARTED_AUTO_CI_FIX)`. The caller frees the branch first.
- Add `provider_reports_checks(repo) -> bool`, for the web layer. It loads the run config from the main root and returns `get_provider(...).reports_checks`.

### 3. `review/flow.py`

- Split `_approve` into:
  - `_prepare_approve(ctx, task_id) -> _Prepared(row, worktree, temp, head)`: today's code up to and including the push and `rev-parse HEAD`. It keeps the conflict, blocked and unknown-task checks. Calling it again after a repair run is safe: `mark_done` is idempotent and the push is a no-op.
  - `_finish_approve(ctx, prepared, merged_by) -> ApproveResult`: `provider.approve`, `merge`, `update_pr`, `_catch_up_base`, worktree removal and the result. This is today's tail, unchanged.
- In `approve_task(repo, task_id, *, provider=None, merged_by=MERGED_BY_OPERATOR, code=None)`, implement the loop from the overview with `ci.head_checks`.
  - Before a repair run, remove the temp approve worktree (`_remove`) and call `_free_branch(ctx, row)`.
  - After the run (`SUCCEEDED` required), start the next round with a fresh `_prepare_approve`. That call re-reads the row and status, so a repair that caused a conflict raises `conflict` as it does today.
  - Collect the repair runs in a new field on `ApproveResult`: `ci_fix_runs: list[str]` (run ids). Add it to `to_json` as `"ci_fix_runs"`.
  - Wrap `ProviderError` from checks as `ReviewError("checks_unavailable", ...)`, and record it.
  - Use a local import of `aifactory.review.ci` inside `approve_task` only if a cycle appears. `ci.py` must import only `providers`, `run` and `config`, never `flow` or `automerge`.
- In `_done_entry`, add `CI_FIX_WORKFLOW` to the excluded workflows (`resolves`).
- Update the module docstring for approve: it waits for the CI and makes repair runs.

### 4. `review/automerge.py`

- In `_hosting_and_merge`, keep the `status` and mergeability polling and the `pr_not_open`, `conflict` and `mergeability_unknown` blockers. Remove the pre-merge `settled_checks` call: checks are now evaluated inside `approve_task` on the merge head. Pass `code` through to `approve_task(..., merged_by=AUTO_MERGE, code=code)`. `ReviewError` maps to `blocked(exc.code, exc.message)` as today, so `checks_failing`, `checks_pending` and `ci_fix_failed` reach `auto_merge_error`.
- `hosting_blocker` keeps its signature. Callers pass `ChecksStatus(CHECKS_NONE)`, or the checks branch is moved to a `checks_blocker(checks, rounds)` helper in `ci.py`. Choose one, and keep `test_auto_merge_rules.py` passing (adjust its imports or calls only if needed).
- `try_auto_merge` and `_check_and_merge` get an optional `code: CodeRunner | None = None`, threaded through to `approve_task`. In `run/queue.py`, pass `code=code` where `try_auto_merge` is called (lines ~618 and ~720).
- Rewrite the module docstring condition 5: the checks of the merge head (after the `status: done` push) are waited for; red checks trigger up to `CI_FIX_ROUNDS` `ci-fix` runs on the PR branch; then `checks_failing`.
- The merge lock: a member's auto-merge (`member_auto_merge`) holds the merge lock across the CI wait and any repair run. Say this in the docstring. Today it already holds the lock across the 30-minute check wait.

### 5. `run/` changes

- `run/resolve.py`: add `CI_FIX_WORKFLOW = "ci-fix"` and add it to `INTERNAL_WORKFLOWS`. Rename the docstring comment to "internal workflows".
- `run/store.py`: add `STARTED_AUTO_CI_FIX = "auto-ci-fix"` next to the other `STARTED_*` constants and update the comments (lines ~9 and ~295).
- `run/task.py`, in `run_task`, add the internal parameter `workflow_name: str | None = None`. It requires `branch` (otherwise `TaskRunError("unknown_branch", ...)`). When set, use `named_workflow(workflow_name, rc.config, task_id)` instead of `resolve_workflow(task, ...)` and skip the `has_workflow(task)` check. It keeps the normal task scope and guard (`TaskWriteGuard`), the normal prompt (`task_prompt` with `note`), and publishing to the existing PR. Document it in the docstring next to `resolve_onto`.
- `run/retry.py:322`: the refusal message for internal workflows names the right action: for `ci-fix`, "approve the PR again"; for resolve, keep the current text.
- `cli.py:1876`: add `"auto-ci-fix"` to the `started_by` choices. Update the `factory task approve` help and description: it waits for the PR's CI checks, and red checks start up to 2 `ci-fix` repair runs on the PR branch. The text output of approve lists the repair run ids when there were any.

### 6. `defaults/workflows/ci-fix.yaml` (new)

```yaml
# Repair a PR whose CI checks went red, on the PR's own branch.
# The prompt's Note holds the names and logs of the red checks.
name: ci-fix
description: Repair what the PR's red CI checks reported, test, review, commit to the same PR
steps:
  - fix:
      description: Repair what the red CI checks in the Note reported, from their verbatim log
  - test_plan:
      description: Plan the checks that reproduce the CI failures and cover the repair
  - repeat: {max: 3, until: test.passed}
    steps:
      - test
      - fix:
          description: Repair what the checks reported, from their verbatim output
      - test_plan:
          description: Plan the checks again — the fix changed code, keep every earlier check
  - review:
      input: [fix]
      description: Confirm the repair fixes the CI failures and keeps what the task asked
  - commit:
      when: test.passed and review.approved
      description: Land the repair on the PR branch
accept: test.passed and review.approved
```

If `preflight` rejects `fix` as the first step (it has no previous envelope), use `build` with the same description as the first step instead. Verify this with a `named_workflow("ci-fix", ...)` and `preflight` unit test.

### 7. Web

`approve` in `web/review.py` and `review_approve` in `web/app.py`:

- When `ci.provider_reports_checks(repo)` is False (`local`, `azure`), keep today's synchronous call and response.
- When it is True (GitHub), the wait can take up to 30 min plus repair runs, so do not block the HTTP request. Add `Launcher.start_approve(repo, task_id) -> None` (protocol plus `RunLauncher`) that spawns `factory task approve <id> --repo <repo> --json` like `_launch`. It does not wait for a run row: approve claims none. Return HTTP 202 with `{"task_id", "action": "approve", "started": true, "approve_review_sent": false, "approve_note": APPROVE_NOTE}`. Update the test launcher double in `tests/web` with `start_approve`.
- Frontend `web/src/lib/review.ts`: `approvePr` returns either the merge result or `{started: true}`. In `ReviewView.vue`, when `started` is true, show the info text "Schvalování běží na pozadí: čeká na CI, při červené CI proběhne oprava do téhož PR. Výsledek uvidíš v detailu PR a v Bězích." and reload the detail. Do not show the "merged" box. Add a vitest case. Run `just web-build` so `src/aifactory/web/static` is updated.
- `web/src/lib/runs.ts`: add the label `'auto-ci-fix': 'auto-ci-fix'` to the started-by map and switch (~lines 475–490).

### 8. Documentation

- `aifactory/src/aifactory/guide/07-review.md` (Czech):
  - Rewrite condition 4 of the auto-merge section and the approve section. Both approve and auto-merge wait for the checks of the head after the `status: done` commit. Red checks start up to 2 `ci-fix` runs on the PR branch (`started_by` `auto-ci-fix`, visible in Běhy). After that, or after 30 minutes of running checks, the PR stays open with `checks_failing`, `checks_pending` or `ci_fix_failed`.
  - A PR without checks merges immediately.
  - On GitHub, the dashboard approves in the background.
- `aifactory/src/aifactory/guide/06-behy.md:21`: mention `auto-ci-fix` among who started the run.
- Task doc `factory/docs/HAIFA/REFINEMENT-upravy-opravy-a-vylepseni-z-praxe/HAIFA-REFINEMENT-T28-automerge-se-musi-postarat-i-o-zelenou-c.md` (Czech): a short description of the behavior.

## Tests

### Global

Add an autouse fixture in `aifactory/tests/conftest.py` that sets `ci.AUTO_MERGE_CHECKS_TIMEOUT = 0.0` and `ci.AUTO_MERGE_CHECKS_APPEAR = 0.0`. Otherwise every GitHub approve test would wait 90 s for checks to appear. In `tests/run/test_auto_merge.py`, move the `_no_checks_wait` and `clock` fixtures to patch `aifactory.review.ci` (`_clock`, `sleep` and the constants) instead of `automerge`. Their assertions stay the same.

### Existing tests that change meaning

- `test_github_red_checks_block` now gets repair runs first. Monkeypatch `ci.CI_FIX_ROUNDS = 0` there so that it still asserts `checks_failing` with no merge. The new tests cover the repair path.
- `test_github_checks_running_past_the_limit_keep_the_pr_open` and `test_github_waits_for_checks_to_finish`: the wait now happens after the done push. Update the expected sleep counts if the head-match step adds polls. With the fake `gh`, `headRefOid` must match the pushed head, or the test makes `status` return `head_sha=None`.

### New tests

Put them in `tests/review/test_ci_gate.py`. Use a fake `GitProvider` subclass, or the `local` provider subclassed with scripted `checks`, `check_logs` and `reports_checks`, together with the `run_repo` fixtures and `fake_env` script used by `test_auto_merge.py`. Cover both `approve_task` (operator) and `try_auto_merge`:

1. No checks (`none`) → merged. For auto-merge, `merged_by == auto-merge`.
2. `passing` → merged.
3. `failing` once, then `passing`: one `ci-fix` run.
   - It runs on the same branch: `run.branch == pr.branch`, `workflow == "ci-fix"`, `started_by == "auto-ci-fix"`.
   - Its note contains the failing check name and the log text from `check_logs`.
   - No new PR row; the PR is then merged and `ApproveResult.ci_fix_runs` has the run id.
4. Always `failing`: exactly `CI_FIX_ROUNDS` repair runs, no merge, PR open.
   - Operator approve raises `ReviewError("checks_failing")`; auto-merge returns `code == "checks_failing"`.
   - `task_prs.auto_merge_error` starts with `checks_failing:` in both cases.
5. `pending` past the limit (use the clock fixture) → `checks_pending`, no repair run, error recorded.
6. The repair run fails (scripted agent output that fails accept) → `ci_fix_failed`, no merge, error recorded.
7. `head_checks` ignores the checks of an old head: `status.head_sha` differs at first, then matches.

Further unit tests:

- `GitHubProvider.check_logs` with the fake `gh`: link parsing, truncation to `CHECK_LOG_LINES`, and a failing `gh run view` giving the "log unavailable" text.
- In `tests/providers/`, `ci_report` truncation.
- `run_task(workflow_name=...)` without `branch` → `unknown_branch`.
- In `tests/web/`, approve with a provider that reports checks returns 202 and calls `launcher.start_approve`, while `local` stays synchronous.

## Verification

From the repo root:

- `just lint`, `just typecheck`
- `just pytest tests/review tests/run/test_auto_merge.py tests/providers tests/web/test_web_review.py`
- `just pytest tests/run` (the `run_task` and retry changes; `run/queue.py`)
- `just web-test`, then `just web-build`, and commit the updated `src/aifactory/web/static`.
