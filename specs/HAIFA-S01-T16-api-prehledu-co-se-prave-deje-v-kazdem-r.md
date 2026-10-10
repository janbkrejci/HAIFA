# HAIFA-S01-T16: Overview API (what is happening in each repo right now)

## Goal

Add `GET /api/overview` to the multi-repo dashboard (`create_multi_app`). For every repo in
the registry it reports what is running, what waits for review, what failed and what state
the configuration is in. It **only reads**: nothing is written to a repo, a trace DB or the
registry, no provider call, no `git fetch`, a missing trace DB is not created.

Out of scope: frontend, SSE for the overview, PR state in the hosting.

## Files

| File | Change |
|---|---|
| `aifactory/src/aifactory/web/overview.py` | **new**: the whole overview logic |
| `aifactory/src/aifactory/web/app.py` | route `GET /api/overview` in `create_multi_app`, `app.state.overview`, docstring line |
| `aifactory/tests/web/overview_fixture.py` | **new**: repos + trace DBs for the tests (modelled on `trace_fixture.py`) |
| `aifactory/tests/web/test_web_overview.py` | **new**: tests |

Nothing else changes. Do **not** modify `run/store.py`, `runs.py`, `review.py` (reuse only).

## Existing code to reuse (read-only usage)

- `aifactory.web.registry.Registry.snapshot()` → `(RegistryState, warnings)`; entries `RepoEntry(id, name, path, added_at)`. Pure read (stat + read file).
- `aifactory.run.gitops.repo_layout(path)` → `RepoLayout | None` (`toplevel`); uses `read_git` with `GIT_OPTIONAL_LOCKS=0`. **Do not** use `gitops.main_root` / `gitops.git` (no `READ_ENV`).
- `aifactory.onboard.state.repo_state(root)` → `RepoState(state, base, commit, …)`; reads via `config.source.git` (has `GIT_OPTIONAL_LOCKS=0`).
- `aifactory.config.loader.load_config(CommitSource(root, base, sha))` raises `ConfigError` (with `.issues: list[ConfigIssue(path, message)]`) when the configuration in base is invalid. `CommitSource` reads only via `ls-tree`/`cat-file` with `READ_ENV`.
- `aifactory.config.status.config_changes(root, sha)` → `list[ConfigChange]` (D4 uncommitted shared config); uses `diff-index`/`hash-object`/`ls-files` with `READ_ENV`, never refreshes the index. `GitError` is a `ConfigError`.
- `aifactory.web.repos.trace_db_of(root)` → trace DB path from `local.yaml` (falls back to `.factory/trace.db`). Does not create anything.
- `aifactory.backlog.load_for_edit(root)` + `iter_tasks(backlog)` → `Task(id, title, status, …)`; never writes (see `runs._task_titles` for the exception set: `ConfigError, TaskEditError, OSError, ValueError`).
- `aifactory.skill.envelope_ok(data, warnings)` as every other handler.

**Never** use `TaskRunStore`, `existing_store`, `runs.list_runs`, `review.review_list` etc.: they
open the DB read-write, run `CREATE TABLE IF NOT EXISTS`/`ALTER TABLE`, and reap dead
running rows (`_reap` writes `aborted`). `review.py` also calls the provider.

## Module `web/overview.py`

Module docstring (English, like the other modules) describing the contract below, incl. the
read-only guarantees, caches and the per-repo time limit.

### Constants

```python
CONFIG_TTL = 15.0      # s, config state per repo
TASKS_TTL = 60.0       # s, task titles + statuses per repo
REPO_TIMEOUT = 2.0     # s, per repo
DB_TIMEOUT = 0.5       # s, sqlite busy wait of the read-only connection
CLOSED_STATUSES = frozenset({"done", "cancelled"})
FAILED_STATES = frozenset({"failed", "aborted"})
PROCESS_ENDED = "proces skončil"
```

Repo `state` values (first match wins):
`missing` (folder gone) → `not_git` (`repo_layout` None / no toplevel) → `timeout` (over the
limit) → `error` (unexpected exception while computing) → `not_installed` (repo_state in
`{"none", "sssf"}`) → `invalid_config` (load_config in base failed) → `uncommitted`
(`working_tree` state or D4 changes non-empty) → `ok`.

### Trace reading (`_open_ro(db) -> sqlite3.Connection | None`)

- Return `None` if `not db.is_file()` (never create it).
- `sqlite3.connect(f"file:{quote(str(db))}?mode=ro", uri=True, timeout=DB_TIMEOUT, isolation_level=None, check_same_thread=False)`; then `PRAGMA query_only = ON`. Use `urllib.parse.quote` for the path (spaces etc.; keep `/`).
- Always close in `finally`.
- `_has_table` check before each query (as `runs._has_table`); missing table = empty.
- Select only columns that exist since the first release (old DBs lack `archived`, `started_by`):
  - `task_runs`: `rowid, run_id, task_id, state, started_at, ended_at, pid, workflow, error`
  - `task_prs`: `branch, task_id, pr_id, url, state, created_at, updated_at`
  - `phases` (optional): `adw_id, name, attempt, status, started_at, seq, rowid`
  - `sessions` (optional): `adw_id, total_cost, total_tokens`
- `sqlite3.Error` → repo warning `"trace DB {db} is not readable: {exc}"`, lists empty, the
  repo is otherwise returned normally.

Liveness: own helper `_process(pid) -> "alive" | "ended" | "unknown"` mirroring
`run.store._alive` (`os.kill(pid, 0)`: `ProcessLookupError` → ended, `PermissionError` →
alive, `pid is None` → unknown). Do not import the private `_alive`.

### Lists

`running[]` — every `task_runs` row with `state = 'running'`, newest `started_at` first:

```json
{"run_id", "task_id", "task_title", "workflow", "started_at",
 "phase": {"name", "attempt", "started_at"} | null,
 "cost": float, "tokens": int,
 "process": "alive" | "ended" | "unknown",
 "status_label": null | "proces skončil"}
```

- `phase`: the run's phase with `status = 'running'`, highest `seq`, then `rowid`; null if none.
- `cost`/`tokens`: `sessions.total_cost`/`total_tokens` of the run (0 when missing). Round cost to 6 places.
- Dead process (`ended`): row stays in `running[]`, `status_label = PROCESS_ENDED`, and the DB is **not** touched.

`review[]` — open PRs from `task_prs` (`state = 'open'`), one per task (newest `created_at`),
for tasks **without an active running run** (a `running` row whose process is not `ended`).
Newest first:

```json
{"task_id", "task_title", "pr_id", "url", "branch", "opened_at", "age_s": float,
 "source": "trace"}
```

`age_s` = now − `created_at` (seconds, ≥ 0, rounded to 1 decimal; null if unparsable).
`source: "trace"` marks that it comes from the trace, not the hosting.

`failed[]` — per task, the newest run (`ORDER BY started_at DESC, rowid DESC`, first per
`task_id`, all runs incl. archived) whose `state` is `failed` or `aborted`, and the task's
backlog status is not in `CLOSED_STATUSES` (status unknown → included). Newest first:

```json
{"run_id", "task_id", "task_title", "state", "workflow", "ended_at", "error"}
```

`last_activity` — the latest timestamp among `task_runs.started_at`, `task_runs.ended_at` and
`task_prs.updated_at` (compare parsed datetimes, return the original ISO string); null if none.
Reuse the parse idea of `runs._time` (write a local `_time`, do not import private helpers).

### Config (`config` object, cached `CONFIG_TTL` per repo)

```json
{"factory_state": "onboarded|pre_library|sssf|working_tree|none",
 "installed": bool,                      # factory_state not in {"none", "sssf"}
 "base": str, "commit": str | null,
 "invalid": bool, "issues": [str],      # load_config in base failed; "path: message", at most 20
 "uncommitted": [{"path", "status"}],   # D4: config_changes(root, commit)
 "clean": bool}
```

Steps for the toplevel `root`:
1. `st = repo_state(root)`.
2. If `st.commit` and `st.state in {"onboarded", "pre_library"}`: `load_config(CommitSource(root, st.base, st.commit))`; `ConfigError` → `invalid=True`, `issues`.
3. If `st.commit`: `config_changes(root, st.commit)`; a `ConfigError` here → repo warning, `uncommitted = []`.
4. `ConfigError` from step 1 → warning + `config = None` (state `error`).

All git calls must go through `config.source.git`/`read_git` (`GIT_OPTIONAL_LOCKS=0`); add no
other subprocess calls.

### Task index (cached `TASKS_TTL` per repo)

`{task_id: (title, status)}` from `load_for_edit(root)` + `iter_tasks`; failure → `{}` and a
repo warning `"task titles are not available: …"` (the warning is cached with it).

### Caching

`class _TtlCache` (thread-safe: `threading.Lock`) with `get(key, ttl, compute)`; key =
`(entry.id, entry.path)`; time from an injectable `clock: Callable[[], float] = time.monotonic`.
Only successful/complete results are cached (a timed-out compute stores nothing). A repo
removed from the registry may stay in the cache (bounded by registry size; optionally prune keys
not in the current snapshot on each collect).

### Orchestration

```python
class Overview:
    def __init__(self, registry: Registry, *, timeout: float = REPO_TIMEOUT,
                 clock: Callable[[], float] = time.monotonic) -> None: ...

    def repo(self, entry: RepoEntry) -> JsonDict:          # sync, runs in a thread
    async def collect(self) -> tuple[JsonDict, list[str]]:
```

- `collect`: `state, warnings = await asyncio.to_thread(self.registry.snapshot)`; then
  `asyncio.gather(*(self._bounded(e) for e in state.repos))`, keeping registry order.
- `_bounded(entry)`: `await asyncio.wait_for(asyncio.to_thread(self.repo, entry), self.timeout)`;
  `TimeoutError` → stub repo with `state="timeout"`, empty lists, `config=None`,
  `last_activity=None`, `warnings=[f"repository {entry.id} did not answer within {timeout:g} s"]`;
  any other `Exception` → stub with `state="error"` and warning `f"{type(exc).__name__}: {exc}"`.
  One bad repo never fails the response.
- Repo item:

```json
{"id", "name", "path", "state", "has_trace": bool,
 "running": [], "review": [], "failed": [],
 "config": {...} | null, "last_activity": str | null, "warnings": [str]}
```

- Missing folder (`not Path(entry.path).is_dir()`): `state="missing"`, warning `f"the folder {path} is missing"`, nothing else computed.
- `totals`: `{"repos": n, "running": Σ, "review": Σ, "failed": Σ, "process_ended": Σ running with process "ended", "with_warnings": count of repos with warnings}`.
- Result: `({"repos": [...], "totals": {...}}, registry_warnings)`.

## `app.py`

- In `create_multi_app`: `app.state.overview = Overview(registry)`; add
  `Route("/overview", overview_get, methods=["GET"])` in the `/api` mount (before the
  `/repos/{repo_id}` mount).
- Handler:

```python
async def overview_get(request: Request) -> JSONResponse:
    """What runs, waits for review and failed in every registered repository (reads only)."""
    ov: Overview = request.app.state.overview
    data, warnings = await ov.collect()
    return JSONResponse(envelope_ok(data, warnings))
```
- Add one sentence about `GET /api/overview` to the "More repositories" paragraph of the module docstring.
- `create_app` (single repo) does not get the route.

## Tests

### `tests/web/overview_fixture.py`

Helpers (reuse `web_repo.git_repo` / `multi_repo.init_repo, write, commit_all` and
`TaskRunStore` + `aifactory.engine.tracer.SCHEMA` **only in the fixture** to build DBs, then close
everything):

- `make_overview_repo(path, *, live_pid, dead_pid) -> Path`: git repo on `main` with committed
  `.factory/config.yaml` (`base: main\n`) and `.factory/agents.yaml` (`multi_repo.AGENTS`), a
  backlog with tasks (statuses in front matter): `T-RUN` todo, `T-REV` todo, `T-FAIL` todo,
  `T-DONE` **done**, `T-CANC` **cancelled**, `T-DEAD` todo. Commit everything. Use the backlog
  layout of `trace_fixture._FILES` (project/step `index.md` + task files). Check the IDs fit the
  backlog id format of that fixture (e.g. `M01-S01-T01`…`T06`), name constants accordingly.
- Trace DB `.factory/trace.db` (keep it out of the commit or commit before creating it; the
  repo must not show D4 changes unless a test wants it — trace.db is not shared config anyway):
  - `T-RUN`: running run `r-run`, `pid=live_pid` (os.getpid()), session cost 0.42, phases
    `plan` success seq 1 and `build` running seq 2 attempt 2.
  - `T-REV`: succeeded run + open PR in `task_prs` (`url`, `created_at` fixed in the past).
  - `T-FAIL`: older succeeded run, newest run `failed` with `error="accept not met"`.
  - `T-DONE`: newest run `failed`, backlog status `done` → not in failed[].
  - `T-CANC`: newest run `aborted`, backlog status `cancelled` → not in failed[].
  - `T-DEAD`: running run with `pid=dead_pid`.
  Create runs with `store.claim(...)` + `store.finish(...)` as `trace_fixture` does; insert
  `sessions`/`phases` with `SCHEMA` via a plain connection; close all connections.
- `dead_pid()`: `p = subprocess.Popen([sys.executable, "-c", "pass"]); p.wait(); return p.pid`.
- `register(home, *roots)`: `Registry(home).add(root)` for each; for the missing-folder case add a
  repo and then `shutil.rmtree` it.

### `tests/web/test_web_overview.py`

Client: `TestClient(create_multi_app(home=tmp_home, static_dir=tmp_path / "nostatic"), base_url=BASE)`;
assert `envelope_problems(body) == []` like `test_web_db_busy._get`.

1. **two repos with trace** (repo A full set, repo B a second running + failed task) plus
   **repo without trace DB** (installed config, no `trace.db`) and **missing folder**:
   - A: `running` has `T-RUN` (task title, workflow, `phase == {"name": "build", "attempt": 2, ...}`, `started_at`, `cost == 0.42`, `process == "alive"`) and `T-DEAD`; `review` has exactly `T-REV` with `url`, `age_s > 0`, `source == "trace"`; `failed` has exactly `T-FAIL` with `error == "accept not met"`; `T-DONE`/`T-CANC` absent; `config.installed`, `not config.invalid`, `config.clean`; `last_activity` set; `state == "ok"`.
   - B: its own lists, independent of A.
   - no-trace repo: `has_trace is False`, empty lists, `config` present, and **no `trace.db` created** afterwards.
   - missing folder: `state == "missing"`, a warning, the response is still 200.
   - `totals` match the sums.
2. **dead process, no writes**: before the call record sha256 + `st_mtime_ns` of `trace.db`,
   bytes of `trace.db-wal` if it exists, the set of `trace.db*` files in `.factory/`, the
   `task_runs` row of `r-dead` (via a fresh `mode=ro` connection) and the bytes of
   `dashboard.yaml`. After the GET: `T-DEAD` is in `running` with `process == "ended"` and
   `status_label == "proces skončil"`; everything recorded is identical (row still `running`,
   `ended_at` still null). Builder: verify empirically that a `mode=ro` connection to the
   closed WAL DB creates no `-wal`/`-shm` (SQLite ≥ 3.22 opens read-only WAL DBs without them);
   if the platform SQLite does create a `-shm`, compare the main file, the row and `-wal`
   content and document why `-shm` is excluded.
3. **never TaskRunStore**: monkeypatch `aifactory.run.store.TaskRunStore.__init__` to raise;
   the overview still answers 200 with full data.
4. **git reads only, with GIT_OPTIONAL_LOCKS=0, no fetch**: wrap `subprocess.run` (monkeypatch
   `subprocess.run` globally with a recorder that delegates); after a GET assert every recorded
   `git` call has `env["GIT_OPTIONAL_LOCKS"] == "0"` and none has `fetch` in its args.
5. **busy DB, answer under 1 s**: warm-up GET (fills caches), then
   `hold_write_lock(db, 3.0)` (import as `test_web_db_busy` does via `sys.path` to
   `tests/run`); time the GET: `< 1.0 s`, status 200, `T-RUN` present; `holder.wait()` in `finally`.
6. **slow / broken repo**: construct `Overview(registry, timeout=0.3)` and set it as
   `app.state.overview` (or monkeypatch), monkeypatch an internal per-repo step (e.g.
   `overview._trace_view`) to `time.sleep(1.5)` for repo A only → A has `state == "timeout"`
   and a warning, B normal, whole response under ~1 s. Second case: the step raises
   `RuntimeError` for A → `state == "error"` with warning, B normal.
7. **caches** (unit test on `Overview.repo` with a fake clock): count calls to the config
   computation and the task index loader (monkeypatch `overview.repo_state` /
   `overview.load_for_edit` with counting wrappers); within 15 s config is computed once,
   after `clock += 16` again; task index once within 60 s, again after `+61`.
8. **invalid config in base / uncommitted (D4)**: repo whose committed
   `.factory/config.yaml` is invalid (e.g. `base: [1]` or an unknown `merge_strategy`) →
   `config.invalid` and `state == "invalid_config"`; repo with an uncommitted edit of
   `.factory/config.yaml` → `uncommitted` non-empty, `state == "uncommitted"`. Make sure the
   chosen invalid value actually makes `load_config` raise (try it).

Tests call no model and no network (the local provider is never touched; no `git fetch`).

## Verification

```bash
just test tests/web/test_web_overview.py
just test
just typecheck
just lint
```

All must exit 0. Run `uv run ruff format` on new files before `just lint`.

## Constraints

- The overview writes nothing (repo, trace DB, registry, index).
- `vendor/`, `prototype/` unchanged. Change only `aifactory/`, `justfile` (no justfile change is needed).
