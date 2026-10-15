# HAIFA-REFINEMENT-T33: The Overview shows PRs merged outside factory as waiting for review

## Problem

When a task PR is merged outside factory (`gh pr merge`, the GitHub web UI, Azure), its row in
`task_prs` in the trace DB stays `open`. Today only `factory backlog sync` refreshes it.
Three readers see that stale `open` row:

- the Overview: `web/overview.py::_lists` (`review`) and `_task_summary` (`in review` count);
- the kanban: `web/backlog.py::_runtime` (`rt.in_review = {pr.task_id for pr in store.open_prs()}`);
- the queue: `run/queue.py` (`open_pr` → skip `in_review`, `Occupancy` from `store.open_prs()`).

The fix is to refresh the `task_prs` state in the background, so all three readers get correct data
without any change to them. The Overview also gets a state filter and a "merged outside factory"
action.

Allowed paths: `aifactory/src/aifactory/web/` (including `web/static`, rebuilt by
`just web-build`), `aifactory/src/aifactory/review/`, `aifactory/src/aifactory/run/`,
`aifactory/web/src/`, `aifactory/tests/`, this spec and the task doc. **`providers/`, `cli.py` and
`docs/decisions.md` are not allowed.**

## Scope note: point 4 (`merged_at` from the provider) is a follow-up

`PrStatus` (`providers/base.py`) has no merge time. The GitHub status query (`_STATUS_FIELDS =
"state,mergeable,headRefOid,mergeCommit"` in `providers/github.py`) and Azure `_parse`
(`providers/azure.py`) do not read one. Supporting a provider-supplied time needs a change in
`providers/`, which this run may not touch. It is filed as a follow-up. This task leaves
`_record_state` and `_refresh_sync_prs` writing `merged_at=_now()` as they do today. Do not add
`getattr(status, "merged_at", ...)` hacks.

## Design

### 1. Background refresh (review side): `review/sync.py`

Add a public function next to `sync_backlog` that reuses the existing helpers. Do not copy their
bodies:

```python
def refresh_prs(repo: Path, *, provider: GitProvider | None = None) -> SyncResult:
    """Refresh the provider state of open task PRs and open sync PRs; nothing else.

    No git fetch, no worktree, no commit, no PR is created. A provider error of one PR
    is a warning in the result. Used by the dashboard's background refresh.
    """
    ctx = _context(repo, provider)
    try:
        result = SyncResult(pr=None, created=False, updated=False)
        _refresh_task_prs(ctx, result)
        _refresh_sync_prs(ctx, result)
        return result
    except ProviderError as exc:
        raise ReviewError(exc.code, exc.message) from exc
    finally:
        ctx.store.close()
```

- Both `_refresh_*` helpers already catch a `ProviderError` per PR and add it to warnings. Keep
  the outer `except` anyway, for `_context`-free provider failures.
- `_sync` keeps calling the two helpers itself, unchanged.
- Export `refresh_prs` from `aifactory.review` (`review/__init__.py`), next to `sync_backlog`,
  if `sync_backlog` is exported there. Follow the existing `__all__` pattern.
- Update the module docstring with one sentence about `refresh_prs`.
- `TaskRunStore.open_prs`, `open_sync_prs`, `update_pr` and `update_sync_pr` do not reap runs, so
  the refresh does not change the Overview's "proces skončil" rows.

### 2. Dashboard refresher: new `web/pr_refresh.py`

```python
PR_REFRESH_INTERVAL = 120.0  # s, background refresh of open task PRs from the provider

def refresh_registered(
    registry: Registry,
    *,
    refresh: Callable[[Path], object] | None = None,
) -> list[str]:
    """Refresh open task PRs of every registered repository that has a trace DB; warnings."""
```

- Iterate `registry.snapshot()` (it returns `(state, warnings)`; see `Overview.collect`) and
  handle `state.repos` one repository at a time, sequentially.
- Skip a repository unless all of these hold: `Path(entry.path).is_dir()`, `repo_layout(path)`
  has a `toplevel`, and `database.available(trace_db_of(root))`. Never create a trace DB.
- Call `refresh(root)`. The default is `aifactory.review.sync.refresh_prs`, looked up at call time
  so tests can monkeypatch it. Pass `refresh=` in tests to inject a fake provider, for example
  `lambda root: refresh_prs(root, provider=FakeProvider(...))`.
- Catch `ReviewError`, `TaskRunError`, `ConfigError` and `OSError`/`sqlite3.Error` per repository.
  A repository that is not installed raises `invalid_config` from `_context`. Each caught error
  becomes the warning `f"{entry.id}: {exc}"`. Also turn the `SyncResult.warnings` into warnings
  with the repo id prefix. Log the warnings with `logging.getLogger(__name__).warning` and return
  them. One broken repository never stops the others.
- Module docstring: why the refresh exists (merges outside factory), that `GET /api/overview`
  stays read-only, and the interval.

Wire it in `web/app.py::create_multi_app` → `lifespan`, inside `if background_checks:`, next to
the other `periodic(...)` tasks:

```python
asyncio.create_task(
    periodic(lambda: refresh_registered(app.state.registry), PR_REFRESH_INTERVAL)
),
```

`periodic` (`web/monitoring.py`) runs right away at startup, then every interval, in the
threadpool. It never overlaps itself and logs exceptions. `cli.py` already passes
`background_checks=True`. Tests keep the default `False`.

### 3. Overview filter and the "merged outside" action: `web/overview.py`

**Trace read (`_read_trace`):**
- Add `merged_at` to the `task_prs` SELECT. Use `"merged_at" if "merged_at" in
  _columns(conn, "task_prs") else "NULL AS merged_at"`, the same pattern as `pause`.
- Add `sync_prs: list[sqlite3.Row]` to `_Trace` (default empty). If `_has_table(conn,
  "sync_prs")`, fill it with `SELECT branch, url, state, tasks, created_at FROM sync_prs WHERE
  state = 'open' ORDER BY created_at DESC`. The empty `_Trace(...)` constructions in `_trace_view`
  must still work, so give the new field a default.

**`_lists(trace, tasks, now, root)`:** pass `root` (the repository toplevel) in from
`Overview.repo`.
- **review filter (point 2):** skip a PR whose task is closed in the index, the same check
  `failed` uses: `hit = tasks.get(pr["task_id"]); if hit is not None and hit[1] in
  CLOSED_STATUSES: continue`. Do this in the loop that builds `open_prs`.
- **merged_outside (point 3):** for each task, take its newest PR across all states, by
  `created_at` and then rowid order. Add the rowid to the SELECT, or compare `created_at` the way
  the existing loop does. List the task when all of these hold:
  - that newest PR has `state == "merged"`;
  - the task is in the index and its status is not in `CLOSED_STATUSES`. A task missing from the
    index is skipped, the same as `_candidates`' `not_in_base`;
  - the task has no active run (`active` set);
  - the task file does not already contain the PR URL in `## Běhy`. This is the `reopened` case
    of `_candidates`: `has_entry(text, url)` from `aifactory.backlog.taskfile`. To read the file
    the overview needs the task path. Extend `TaskIndex` values from `(title, status)` to
    `(title, status, path)`. Check every `tasks.get(...)`/`hit[0]`/`hit[1]` use. Read
    `(root / path).read_text(encoding="utf-8")` and skip the task on `OSError`.

  Item shape: `{"task_id", "task_title", "pr_id", "url", "branch", "merged_at"}`, newest
  `merged_at` first.
- **sync_pr:** the newest open sync PR (`{"url", "branch", "tasks": [...]}` with `tasks` parsed
  from the JSON column, `[]` on bad JSON), or `None`.
- Return both in `lists` as `"merged_outside"` and `"sync_pr"`.

**`_stub`:** add `"merged_outside": []` and `"sync_pr": None`.

**`collect` totals:** add `"merged_outside": sum(len(r["merged_outside"]) for r in repos)`.

**`_task_summary`:** `board_state` already returns `done`/`cancelled` before `in review`, so it
needs no change. Do not add a filter there.

**Docstring:** update the module docstring. Cover the review filter (done/cancelled excluded), the
`merged_outside` and `sync_pr` fields, and that the PR state is kept fresh by `web/pr_refresh.py`
while the overview itself still makes no provider call.

### 4. Sync action endpoint: `web/app.py`

Add `Route("/backlog/sync", backlog_sync, methods=["POST"])` to `_repo_routes()`, near
`/backlog/commit`:

```python
async def backlog_sync(request: Request) -> JSONResponse:
    """``factory backlog sync``: open (or extend) the sync PR for tasks merged outside factory."""
    repo: Path = _repo(request)
    try:
        result = await run_in_threadpool(review_core.sync_backlog, repo)
    except (ReviewError, TaskRunError, ConfigError) as exc:
        return _review_error(exc)
    data = result.to_json()
    data.pop("ok", None)
    return JSONResponse(envelope_ok(data, list(result.warnings)))
```

Use whatever name `app.py` already imports for the review core module. Look up `sync_backlog` on
the module at call time so tests can monkeypatch it. Map any new `ReviewError` codes in
`_REVIEW_ERROR_STATUS` only if needed: `sync_on_base`, `unknown_base` and `worktree_failed` → 409
or 500, following the existing style. The write guard (`web/guard.py`) applies to every POST
automatically. A sync PR is never created automatically, only by this request.

### 5. Frontend (`aifactory/web/src/`)

- `lib/api.ts`:
  - `OverviewMergedOutside { task_id; task_title: string|null; pr_id: string|null; url:
    string|null; branch: string|null; merged_at: string|null }`.
  - On `OverviewRepo`: `merged_outside?: OverviewMergedOutside[]` and `sync_pr?: { url: string;
    branch: string; tasks: string[] } | null`. Make them optional so old fixtures still type-check,
    and default them in `fetchOverview` normalisation if repos are normalised there.
  - `backlogSync(repoId)` → `postGlobal<BacklogSyncResult>(`/repos/${encodeURIComponent(repoId)}/backlog/sync`, {})`
    with `BacklogSyncResult { url: string|null; created: boolean; updated: boolean; tasks: {task_id: string}[]; warnings: string[] }`.
- `components/overview/RepoCard.vue`: a new section after "Čeká na review", shown when
  `repo.merged_outside?.length`:
  - Heading `Sloučeno mimo factory`. Each row has the task id and title, and a link to the PR
    `url` (`target="_blank" rel="noopener"`). Use `data-test="row-merged-outside"`.
  - When `repo.sync_pr` is set: the link `Sync PR čeká na merge` to `sync_pr.url`
    (`data-test="sync-pr-link"`).
  - Otherwise: the button `Otevřít sync PR` (`data-test="sync-open"`). It calls `backlogSync`,
    shows the existing `Spinner` while busy, and on success shows the returned PR link and emits
    the card's refresh event. Use the mechanism `RepoControls.vue` uses after start/stop. Errors
    go through `errorText`. Follow `RepoControls.vue` for the busy/error pattern and whether a
    confirm dialog is used. A confirm is optional and not required.
- `lib/overview.ts`: no urgency change is required. If counts are shown per repo, leave them as
  they are.
- Tests: extend `RepoCard`/`OverviewView` tests (`OverviewView.test.ts`,
  `test/overviewFixtures.ts`). Cover that the section renders, that the button posts to
  `/repos/<id>/backlog/sync`, and that the link replaces the button when `sync_pr` is set.
- Run `just web-build` and commit the regenerated `aifactory/src/aifactory/web/static`.

## Tests (no network; the provider is `local` or a fake)

1. `aifactory/tests/run/test_backlog_sync.py` (reuses its fixtures `repo`, `script`,
   `run_and_merge_outside`, `stored_pr`):
   - `test_refresh_prs_records_outside_merge`: run and merge outside, then call
     `refresh_prs(repo)`. Check that `stored_pr(repo).state == "merged"`, that `result.states` has
     the task, and that there is no sync branch (`branch_exists(repo, SYNC)` is False), no new
     commit on base and no `sync-check` worktree left.
   - `test_refresh_prs_provider_error_is_warning`: use a `LocalProvider` subclass whose `status`
     raises `ProviderError("gh_failed", "x")`, passed as `provider=`. The row stays `open` and the
     result has one warning. Import `LocalProvider` from wherever `providers/local.py` defines it.
2. `aifactory/tests/web/test_web_pr_refresh.py` (new; use `overview_fixture.register`,
   `make_installed_repo` or the `run_repo` helpers):
   - `refresh_registered` with an injected `refresh` that records the roots. It is called for a
     repo with a trace DB and skipped for a repo without one, which also checks that no trace DB
     is created, and for a missing folder.
   - An injected `refresh` that raises `ReviewError("invalid_config", ...)` for one repo still
     lets the other repo refresh, and the warning carries the repo id.
   - End-to-end with a `local` provider: a task PR merged outside factory. After
     `refresh_registered`, `Overview(registry).repo(entry)["review"]` is empty and
     `web.backlog._runtime(root)[0].in_review` does not contain the task. This covers the first
     acceptance criterion. If the existing `run_repo` fixtures do not register cleanly, building
     trace rows directly with `TaskRunStore.save_pr` plus a fake provider is acceptable.
3. `aifactory/tests/web/test_web_overview.py`:
   - A task with `status: done` in the backlog and an `open` PR row is not in `review` (second
     acceptance criterion). The same holds for `cancelled`.
   - A task that is not done, whose newest PR is `merged`, is in `merged_outside` and
     `sync_pr is None`. With an open `sync_prs` row (`TaskRunStore.save_sync_pr`), `sync_pr` is
     set.
   - A done task with a merged PR is not in `merged_outside`. A task with a newer `open` PR after
     the merged one is not in it either.
   - A task whose file already has the PR URL in `## Běhy` (reopened) is not in it.
   - `_stub` items and `totals` contain the new keys.
4. `aifactory/tests/web/test_web_app.py` (or the review web tests): `POST
   /api/repos/<id>/backlog/sync` with `sync_backlog` monkeypatched to return a `SyncResult`
   gives 200 and the envelope data has `url`. A raised `ReviewError` gives the mapped error
   status.

## Verification

- `just lint`, `just typecheck`
- `just pytest tests/run/test_backlog_sync.py tests/web/test_web_overview.py tests/web/test_web_pr_refresh.py tests/web/test_web_app.py tests/web/test_web_backlog.py tests/web/test_web_monitoring.py`
- `just pytest tests/review tests/run/test_queue*.py` if anything under `review/` or `run/`
  beyond `sync.py` changed
- `just web-test`, then `just web-build`

## Out of scope

- The provider merge time (`merged_at`, point 4) is a follow-up: it needs `providers/`.
- Kanban and queue code need no change; they read `task_prs`, which the refresh now keeps
  current.
- The local `base` is not fast-forwarded by the refresher. No `git fetch` runs in the background.
