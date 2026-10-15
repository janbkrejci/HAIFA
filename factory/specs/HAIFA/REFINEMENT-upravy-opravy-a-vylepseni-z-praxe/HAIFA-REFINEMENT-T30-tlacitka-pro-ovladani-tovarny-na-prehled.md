# HAIFA-REFINEMENT-T30: Factory controls and task status summary on the Overview

## Goal

Every repository on the Overview (`#/overview`, `GET /api/overview`) gets:

1. **Spustit továrnu** (green, Play icon). It is shown only when the repo has at least one ready task and at least one free parallel slot. A click starts `min(free slots, startable ready tasks)` runs. It uses the existing auto-continue selection (`run/queue.py`), so the kanban's manual queue order, excluded tasks, dependencies and write-path collisions are respected.
2. A **task status summary**: how many tasks are in each kanban board state (`todo`, `ready`, `blocked`, `running`, `in review`, `done`, `cancelled`), the same states `web/backlog.py::board_state` uses.
3. **Pauza** and **Stop** (player icons). They act on every running run of the repo through the existing `pause_run` / `stop_run`. The UI then shows progress ("Pozastavuje se – dobíhají 2 běhy" → "Pozastaveno", "Zastavuje se – dobíhají 2 běhy" → "Zastaveno") until every affected run has finished. **Pokračovat** (resume all paused runs) is added because without it a paused factory could only be resumed run by run. The buttons are shown only when there is something to act on.

All allowed paths: `aifactory/src/aifactory/web/`, `aifactory/src/aifactory/run/`, `aifactory/web/src/`, `aifactory/tests/`, this spec and the doc file. No CLI change: `cli.py` and `docs/decisions.md` are outside the allowed paths, and the feature does not need them.

## Design

### Why the start goes through separate `factory task run ID` processes

The dashboard already starts every run as a separate process (`RunLauncher.start`). "Spustit továrnu" picks tasks with the auto-continue selection, then starts each one with `launcher.start(repo, task_id, note=None, force=False)`, which is the same as clicking Spustit on that task. It does **not** pass `auto=True`: each started run becomes an ordinary `run_chain`, and that chain continues only according to the inherited `auto_continue` (the existing semantics). No new parallel mechanism is added.

There is one gap in the existing mechanism that this feature would expose. A parallel chain's `fill()` in `_run_parallel` counts only its **own** active runs (`len(runner.active()) < max_parallel`). Several chains started side by side could therefore exceed `max_parallel_runs` in total. Fix it as part of this task (step 1b), so that the limit holds for the whole repo.

### Selection for the whole repo (no "after" task)

`select_next(backlog, after, ...)` takes its candidates from `candidates(after, order)`, which covers the project of `after`. For the factory start, split out the checking loop so the same rules apply to a repo-wide candidate list.

### Pause/stop progress

- **Pause**: `pause_run` only records `pausing`. The run becomes `paused` at the next phase boundary, which can take minutes. Progress comes from the DB: the overview exposes `pause` (`null | "pausing" | "paused"`) for every running run. "Dobíhá" means affected runs still `running` with `pause != "paused"`.
- **Stop**: `stop_run` marks the row `stopped` immediately, then signals the process and waits up to 10 s (SIGKILL after that). The DB therefore cannot tell that a process is still dying. Stops run in background threads held by an in-memory `FactoryControl` object (per server, keyed by repo root). Each stop is "dobíhá" until its `stop_run` call returns. The overview item carries the control state.

---

## Implementation steps

### 1. `aifactory/src/aifactory/run/queue.py`

**1a. Repo-wide selection.**

- Extract the body of `select_next` after candidate generation into a private `_select(pool: Sequence[Task], backlog, *, open_pr, running, exclude, conflict, require_auto_continue, prefs) -> Selection`. `select_next` becomes `return _select(candidates(after, prefs.order), backlog, ...)`, and its behaviour must stay byte-for-byte the same (existing tests in `tests/run/test_chain_parts.py`, `test_parallel_chain.py` and `test_queue_prefs.py` must stay green).
- Add `repo_candidates(backlog: Backlog, order: Sequence[str] = ()) -> list[Task]`: every `status == "todo"` task of the backlog in backlog order (iterate like `candidates` does, with `descendant_tasks` over every project of `backlog.projects`, or `iter_tasks(backlog)` from `aifactory.backlog`; check which gives backlog order). The ones in `order` come first, by rank. Same docstring style as `candidates`.
- Add `select_ready(backlog, *, open_pr, running, exclude=frozenset(), conflict=None, prefs=None) -> Selection` = `_select(repo_candidates(backlog, prefs.order), ..., require_auto_continue=False)`. A start by hand does not need `auto_continue` (same as the Spustit button). Excluded tasks are skipped as `excluded`, tasks without a workflow as `no_workflow`, unmet dependencies as `blocked` / `waits_on_pr`, running ones as `running`, and ones with an open PR as `in_review`.

**1b. A parallel chain respects the repo-wide limit.** In `_run_parallel.fill()`, replace the loop condition `len(runner.active()) < max_parallel` with a check that also counts live runs in the trace DB. Inside the loop, after opening `store = TaskRunStore(db)`, compute `busy = max(len(runner.active()), len(store.live_runs()))`. If `busy >= max_parallel`, close the store, `save()` and return. Keep `halt is None` in the loop condition. (`live_runs` includes the chain's own claimed runs, and `max` keeps fake runners in tests working when they write no rows.) Update the module docstring paragraph on parallel runs: "keeps up to that many runs going at once **in the repository** (runs of other chains count)". Add a test in `tests/run/test_parallel_chain.py`. Use the existing fake runner of that file, put one extra `running` row with a live pid (e.g. `os.getpid()` of a sleeping child, as the existing tests do for live rows) into the store, set `max_parallel=2`, and assert the chain fills only one slot.

**1c. `start_factory`.** Add it to `queue.py` and export it from `run/__init__.py` (`__all__`):

```python
@dataclass
class FactoryStart:
    max_parallel: int
    running: int            # live runs before the start
    free_slots: int         # max(0, max_parallel - running)
    started: list[TaskRunRow | str]   # claimed rows; a task id when the claim timed out
    skipped: list[Skip]     # candidates not started (reasons as in SKIP_REASONS)

    def to_json(self) -> dict[str, object]: ...
        # {"max_parallel_runs", "running", "free_slots",
        #  "started": [{"task_id", "run_id" | None}], "skipped": [s.to_json()]}

def start_factory(
    repo: Path,
    start: Callable[[str], TaskRunRow | None],
    *,
    max_parallel: int | None = None,
    pr_files: Callable[[TaskPrRow], list[str] | None] | None = None,
) -> FactoryStart:
```

Behaviour:
- `main = gitops.main_root(repo)`, `limit = max_parallel if not None else _max_parallel(repo)`, `db = task_mod._load(main).local.trace_db_path(main)` (as `_run_parallel` does). `files_of` is the same default as in `_run_parallel` (extract a small helper `_pr_files_default(main)` and use it in both).
- If `db` does not exist: running = 0, no open PRs, no queue prefs. Do not create the DB just to read it; use `TaskRunStore(db)` only when `db.is_file()`, otherwise pass `open_pr=lambda _: None`, `running=lambda _: None`, `QueuePrefs()` and an empty `Occupancy([], [], main)`.
- `running = len(store.live_runs())`, `free = max(0, limit - running)`. If `free == 0`, return with nothing started (`skipped` empty).
- Loop while `len(started) < free`: inside `with _fresh_backlog(repo) as backlog` (base backlog, as the chains use), open the store and build `Occupancy.build(backlog, store, main, files_of)` again every iteration, so a run claimed in the previous iteration counts. Then call `select_ready(backlog, open_pr=store.open_pr, running=store.running, exclude=exclude, conflict=conflict, prefs=store.queue_prefs())`. Here `conflict` is the occupancy plus the **pending** tasks (started but not yet claimed, `start` returned None). For each pending task, use its `effective_task_writes` and treat it like a running run: same overlap and wide (`is_wide`) rules, Skip reason `writes_overlap` / `exclusive`. Implement this as a small wrapper function, or by appending synthetic entries. If you append, give `Occupancy.runs` entries a row: simplest is a separate `pending: list[tuple[str, tuple[str, ...]]]` checked after `occupancy(task)`.
- Keep the skips of the **last** selection as `skipped` (like `last_skips` in `_run_parallel`), plus `cannot_start` skips collected across iterations (`start_skips`).
- `nxt = selection.next`. If it is None, break. Otherwise `exclude.add(nxt.id)`, then `try: row = start(nxt.id)`. On `except TaskRunError as exc`, append `Skip(nxt.id, "cannot_start", f"{exc.code}: {exc.message}")` and continue. Append `row` or `nxt.id` (pending) to `started`.
- `start` is called with the store closed (the launched process needs the DB).

Tests go in a new file `tests/run/test_factory_start.py`. Use the backlog and trace helpers of the existing `test_parallel_chain.py` / `test_chain_parts.py` (reuse their fixtures; do not duplicate them; import from a shared helper if one exists). Cover:
- With 3 ready tasks, limit 2 and nothing running, 2 start in queue order, and the manual `task_queue` order wins over backlog order.
- An excluded task, a task without a workflow and a blocked task are not started and come back in `skipped` with the right reasons.
- One live run plus limit 2 gives exactly 1 start.
- Overlapping `writes` between two ready tasks: only the first starts, and the second is `writes_overlap`, including when the first was only pending (`start` returned None).
- `start` raising `TaskRunError` gives `cannot_start`, and the next candidate starts.
- Limit 1 with one live run starts nothing.
- No trace DB: it is not created by `start_factory` itself (the fake `start` creates nothing).

The fake `start` records task ids and returns a `TaskRunRow` it inserted into the store with a live pid (so `live_runs` sees it), or None.

### 2. `aifactory/src/aifactory/web/control.py` (new module): `FactoryControl`

Module docstring: the Overview's factory controls (`POST /api/repos/{id}/control/start|pause|resume|stop`) and the in-memory progress of a repo-wide stop.

```python
class FactoryControl:
    """Repo-wide start, pause, resume and stop; the progress of a stop per repository root."""
    def __init__(self, stop: Callable[[Path, str], object] = run_stop.stop_run) -> None
    def start(self, repo: Path, launcher: Launcher) -> JsonDict
    def pause(self, repo: Path) -> JsonDict
    def resume(self, repo: Path) -> JsonDict
    def stop(self, repo: Path) -> JsonDict
    def snapshot(self, repo: Path) -> JsonDict | None   # for the overview
```

- Key the state by `str(gitops.main_root(repo))` (fall back to `str(repo)` on `TaskRunError`). The overview uses the same key function: expose `control_key(root: Path) -> str`.
- `start`: `start_factory(repo, lambda task_id: launcher.start(repo, task_id, note=None, force=False))`, then return `result.to_json()`. A `TaskRunError` of `start_factory` itself (e.g. `invalid_config`) propagates.
- `running_runs(repo) -> list[TaskRunRow]`: `existing_store(repo)` (None gives `[]`), then `store.live_runs()` (reaps dead ones).
- `pause`: for every running run with `pause is None`, call `run_pause.pause_run(repo, run_id)`. Collect `TaskRunError` per run into `errors: [{run_id, task_id, code, message}]` and do not abort. Return `{"action": "pause", "run_ids": [...requested...], "errors": [...]}`. Record `{"action": "pause", "run_ids": affected, "started_at": iso}` in the state, so the UI knows which runs to watch. Affected = requested plus runs already `pausing`/`paused`.
- `resume`: the same for runs with `pause in ("pausing", "paused")`, using `run_pause.resume_run`. It clears the recorded pause action.
- `stop`: collect the running run ids. For each id, start a daemon thread that calls `self._stop(repo, run_id)` and catches `TaskRunError`/`ConfigError`/`OSError`, storing `{code, message}`. Return at once with `{"action": "stop", "run_ids": [...], "pending": [...]}` (HTTP 202). State: `{"action": "stop", "run_ids", "pending": set, "errors": [...], "started_at", "finished_at"}`. A thread removes its id from `pending` under a lock when done. When the last one finishes, run **one sweep**: if `live_runs()` now shows runs started after `started_at` (a chain refilled a slot just before its member was stopped), stop those too, at most 3 sweep rounds. This covers "ať se nové běhy z řetězu už nespouští". A stopped member makes its chain halt (`STOP_FAILED`, the result is not ok), so normally nothing new starts. A second `stop` while one is pending adds the new ids to the same state.
- `snapshot(repo)`: `{"action", "run_ids", "pending": sorted list, "errors", "started_at", "finished_at"}`, or None. Keep a finished stop for 60 s after `finished_at` (injectable clock), so the UI can show "Zastaveno". After that, return None and drop it. A pause record is returned as long as any of its runs is still running (the overview decides the label from the run rows). Drop it when none of its runs runs.
- Thread safety: one `threading.Lock` for the dict. `wait(timeout)` waits for the stop threads (tests).

Register it in `_shared_state` in `app.py`: `app.state.control = FactoryControl()`. In `create_multi_app`, pass it to the overview: `Overview(registry, control=app.state.control)`. Note that `_shared_state` runs after `app.state.overview = Overview(registry)`: either create the control before the overview, or set `overview.control` afterwards. Choose one and keep `create_app` (single repo) working too.

### 3. Routes in `aifactory/src/aifactory/web/app.py`

Add to `_repo_routes()`:

```
Route("/control/start", control_start, methods=["POST"]),
Route("/control/pause", control_pause, methods=["POST"]),
Route("/control/resume", control_resume, methods=["POST"]),
Route("/control/stop", control_stop, methods=["POST"]),
```

(`/factory/...` is already the Factory tab, so the prefix is `control`.) Each handler runs the control method in `run_in_threadpool`. It maps `TaskRunError`/`ConfigError` with the existing `_run_error` helper (same status mapping as the per-run endpoints) and returns `envelope_ok(data)`. `start` returns 200 even when nothing started; `data.started` says so. `stop` returns 202. A request body is not needed; an empty body or `{}` is accepted. If the body has unknown keys, return `_usage_error` like other endpoints do (`_json_body` + key check, see `backlog.RUN_KEYS` usage), or simply ignore the body. Pick the simpler path that matches neighbouring handlers. Mention the new endpoints in the `app.py` module docstring next to `GET /api/overview`.

### 4. `aifactory/src/aifactory/web/overview.py`

- `_read_trace`: also select `pause` from `task_runs` **if the column exists** (`PRAGMA table_info(task_runs)`; older DBs may lack it, in which case use NULL). Add `"pause": row["pause"]` to every item of `running`.
- Read the kanban queue prefs read-only: if the `task_queue` table exists, `SELECT task_id, excluded FROM task_queue WHERE excluded = 1` into `_Trace.excluded: frozenset[str]`.
- Task cache: `_task_index` currently caches `{id: (title, status)}`. Cache the loaded `Backlog` alongside it (e.g. return a small dataclass `_Tasks(index, backlog)` or a tuple). Keep `TASKS_TTL` and the warnings.
- New `_task_summary(backlog, trace) -> JsonDict`. Build a `web.backlog._Runtime` from the trace rows: `running` = task ids of rows in state `running` whose process is not `ended`; `in_review` = task ids of open PRs. For every task of the backlog, take `web.backlog.board_state(backlog, task, rt)` and count by state. Always return every key of `BOARD_STATES` (zeros included): `{"todo": n, "ready": n, "blocked": n, "running": n, "in review": n, "done": n, "cancelled": n}`. Import `BOARD_STATES`, `board_state`, `_Runtime` from `aifactory.web.backlog` (make `_Runtime` public as `Runtime` with an alias if mypy/ruff complain about private import; otherwise keep the name). It must not open `TaskRunStore`: `test_overview_never_uses_task_run_store` must stay green. Without a trace DB, use an empty runtime.
- New `factory` block per item:
  ```
  "factory": {
    "max_parallel_runs": int | None,   # chains._max_parallel_runs(root); None when invalid
    "running": int,                     # running rows whose process is not "ended"
    "free_slots": int,                  # max(0, max_parallel_runs - running); 0 when None
    "ready": int,                       # board state "ready" and not excluded in task_queue
    "can_start": bool,                  # ready > 0 and free_slots > 0 and state == "ok"
    "paused": int, "pausing": int,      # running rows by pause
    "control": FactoryControl.snapshot(root) | None
  }
  ```
  When `config` is missing or invalid (`state != "ok"` and not `"uncommitted"`), `can_start` is false. Decide: also allow `uncommitted` (runs read base, so uncommitted config does not stop a run). Allow `ok` and `uncommitted`, and document it in the docstring.
- `_stub` gets `"tasks": None` and `"factory": None`, so missing/timeout/error repos have them as null.
- `Overview.__init__(..., control: FactoryControl | None = None)` stores it. `repo()` fills `item["tasks"]` and `item["factory"]` (control snapshot keyed by `control_key(root)`).
- `collect().totals`: unchanged keys (do not break the frontend). Optionally add `"ready"` (the sum of `factory.ready`), but do not add a new filter button for it.
- Update the module docstring (new keys `tasks`, `factory`).
- Import cycle check: `overview` → `web.backlog` → `web.launcher` / `web.settings`. Make sure that does not import `overview`. `web.chains` is fine. `control.py` imports `run.queue`, `run.pause`, `run.stop`, `run.task` and `web.launcher` (for the `Launcher` type only, under `TYPE_CHECKING` if needed).

### 5. Backend tests

- `tests/web/test_web_overview.py` (extend; use `overview_fixture.make_overview_repo`):
  - `tasks` counts match the fixture. `T_RUN` is `running` (live pid). `T_REV` is `in review`. `T_DEAD` (dead pid) is not running; its board state comes from the backlog (`ready`, since the M01 project has `workflow: plan-commit`). `T_DONE` is `done`, `T_CANC` is `cancelled`. Check every key of `BOARD_STATES` is present.
  - The `factory` block: `max_parallel_runs` from `.factory/config.yaml` (write `max_parallel_runs: 2` in a test repo, and the default when absent; check what `parse_project_settings` returns), `running`, `free_slots`, `ready`, `can_start`. Add a case where an excluded task (insert a `task_queue` row with `excluded = 1` through `TaskRunStore.set_excluded` or the existing setter in the fixture; the fixture may use the store) is not counted in `ready`. Add a case where full slots give `can_start == false`.
  - A `running` item has `pause` (null; and `"pausing"` after `store.request_pause`).
  - A trace DB whose `task_runs` lacks the `pause` column still works.
  - Stubs (missing folder) have `tasks: None` and `factory: None`.
  - The existing tests stay green unchanged, except for added assertions.
- `tests/web/test_web_control.py` (new):
  - `POST /api/repos/{id}/control/start` uses a fake launcher (follow the pattern of `test_web_task_run.py` / `thread_launcher.py`, or a minimal double implementing `Launcher.start` that inserts a claimed running row with a live pid). With limit 2 and 3 ready tasks, two `start` calls happen in queue order, and the response has `started` of length 2 and the skips. Repeat with nothing free: `started == []`.
  - `control/pause` on two running runs: both have `pause == "pausing"` in the DB. The response `run_ids` lists both. A run that is already paused is not re-requested and gives no error.
  - `control/resume` drops the pause of both.
  - `control/stop`: inject a fake stop (`FactoryControl(stop=fake)`) that blocks on an `Event`. Right after the POST (202), `GET /api/overview` shows `factory.control.pending` with both ids. After the event is set and `control.wait()`, `pending == []` and `finished_at` is set. With a fake clock beyond 60 s, `control` is None. Errors of a fake stop that raises `TaskRunError("remote_run", ...)` appear in `errors`.
  - Errors: an invalid config gives the same status as `/backlog/tasks/{id}/run`.
  - Single-repo `create_app` also serves `/api/control/...` (one smoke test).

### 6. Frontend: types and API (`aifactory/web/src/lib/`)

- `api.ts`: extend `OverviewRunning` with `pause: 'pausing' | 'paused' | null`. Extend `OverviewRepo` with `tasks: Record<BoardState, number> | null` (reuse the board-state type if `lib/backlog.ts` exports one; otherwise define `OverviewTaskCounts` with the seven keys) and `factory: OverviewFactory | null`:
  ```ts
  export interface OverviewControl { action: 'stop' | 'pause'; run_ids: string[]; pending: string[]; errors: { run_id: string; task_id?: string; code: string; message: string }[]; started_at: string; finished_at: string | null }
  export interface OverviewFactory { max_parallel_runs: number | null; running: number; free_slots: number; ready: number; can_start: boolean; paused: number; pausing: number; control: OverviewControl | null }
  export interface FactoryStartResult { max_parallel_runs: number; running: number; free_slots: number; started: { task_id: string; run_id: string | null }[]; skipped: { task_id: string; reason: string; detail: string; waits_on: string[] }[] }
  ```
  Add functions `controlStart(repoId)`, `controlPause(repoId)`, `controlResume(repoId)`, `controlStop(repoId)` using `postGlobal(`/repos/${encodeURIComponent(id)}/control/start`)` etc. Check `postGlobal` builds `/api` + path. Update fixtures/mocks in existing tests that construct `OverviewRepo` objects (`OverviewView.test.ts`, `lib/overview` tests, the switcher) to include `tasks`/`factory` (null is allowed), so vue-tsc passes.
- `lib/overview.ts`: pure helpers (unit-tested in the overview lib test file, `lib/overview.test.ts` if present, otherwise create it):
  - `taskSummary(repo): { state: string; label: string; count: number }[]`: the board states in `BOARD_STATES` order with Czech labels (reuse the kanban column labels if a constant exists in `lib/backlog.ts` / the board component; otherwise `todo: 'K zadání'`, `ready: 'Připraveno'`, `blocked: 'Blokováno'`, `running: 'Běží'`, `in review: 'Review'`, `done: 'Hotovo'`, `cancelled: 'Zrušeno'`). States with a zero count are omitted. An empty array when `tasks` is null.
  - `canStart(repo)`: `repo.factory?.can_start === true`.
  - `canPause(repo)`: some `activeRuns(repo)` run has `pause == null`.
  - `canResume(repo)`: some run is `pausing` or `paused`.
  - `canStop(repo)`: `activeRuns(repo).length > 0`.
  - `controlStatus(repo): { kind: 'stopping' | 'stopped' | 'pausing' | 'paused'; text: string } | null`:
    - stop with `pending.length > 0`: `Zastavuje se – dobíhá(jí) N běh(y/ů)` (Czech plural: 1 běh "dobíhá 1 běh", 2–4 "dobíhají N běhy", 5+ "dobíhá N běhů"; a helper `plural(n, one, few, many)` may already exist in `lib/format.ts`; reuse it).
    - stop finished: `Zastaveno`.
    - pause: count the affected runs (`control.run_ids` ∩ running) whose `pause !== 'paused'`. More than 0 gives `Pozastavuje se – dobíhá N běh…`. 0 with at least one paused affected run gives `Pozastaveno`.
    - Otherwise null. Errors are shown separately as a line (`Nepodařilo se: TASK – message`).

### 7. Frontend: `RepoControls.vue` (new, `aifactory/web/src/components/overview/`)

A component used both in `RepoCard.vue` (under the header) and in the calm-repo row of `OverviewView.vue`. Calm repos have no card but can have ready tasks, so the start button must be reachable there too.

- Props: `repo: OverviewRepo`. Emits `changed` (the parent calls `refresh()` of `useOverview`).
- Buttons (lucide icons `Play`, `Pause`, `Square`, plus `Play` for resume, labelled `Pokračovat`):
  - `Spustit továrnu`, class `start` (green, like other primary/green action buttons; reuse an existing CSS class/variable such as `var(--green)`), `data-test="factory-start"`, `v-if="canStart(repo)"`. While the request runs it is disabled and shows `<Spinner />` (`@/components/ui/Spinner.vue`), the same pattern as `RunDetail.vue` (`stopping`/`pauseBusy`). After the response: if `started.length === 0`, show a short message `Nic se nespustilo: ` + the first skip reasons (`data-test="factory-start-message"`). Otherwise show `Spuštěno N běh(ů)`. Then emit `changed`.
  - `Pauza` `data-test="factory-pause"`, `v-if="canPause(repo)"`. `Pokračovat` `data-test="factory-resume"`, `v-if="canResume(repo)"`. `Stop` `data-test="factory-stop"`, `v-if="canStop(repo)"`. Each has its own busy flag and spinner. Stop asks for confirmation through the existing `lib/confirm.ts` helper, as the per-run Stop does (check `RunDetail.vue`). Request errors go to an error line (`errorText` from `lib/format`).
  - Status line `data-test="factory-control-status"` with `controlStatus(repo)`; it updates on every overview reload (the view polls every 2 s).
  - Task summary `data-test="task-summary"`: one chip per non-zero state, `data-state` = the state, e.g. `Připraveno 3 · Běží 1 · Hotovo 12`. Also show the slot info when `factory` is known: `Sloty: running/max` (`data-test="factory-slots"`).
- Clicks must not navigate. The card rows are links, but the controls are outside them; use `type="button"`.

`RepoCard.vue`: render `<RepoControls :repo="repo" @changed="emit('changed')" />` after the header. Add `changed` to its emits. `OverviewView.vue`: pass `@changed="refresh"` to `RepoCard`, and render `RepoControls` in each calm `<li>` (compact). In `lib/overview.ts::urgency`, a repo with `factory.control?.pending.length` stays at least `running`, so it does not fold into the calm list while a stop is in progress.

### 8. Frontend tests (vitest)

- `components/overview/RepoControls.test.ts` (new):
  - Start is visible only when `can_start` is true. A click calls `controlStart` (mock `@/lib/api`), the spinner shows while the promise is pending, and `changed` is emitted after.
  - The message is shown when nothing started.
  - Pause, Resume and Stop are visible according to the run pause states, and hidden when nothing runs.
  - Stop asks for confirmation and calls `controlStop`.
  - Status texts: stop pending with 2 runs gives "Zastavuje se – dobíhají 2 běhy". Stop finished gives "Zastaveno". Pause with one run still `pausing` gives "Pozastavuje se – dobíhá 1 běh". All paused gives "Pozastaveno".
  - The task summary shows non-zero states with counts.
- `lib/overview` helper tests for `taskSummary`, `canStart/canPause/canResume/canStop` and `controlStatus` (plural forms).
- `views/OverviewView.test.ts`: the existing tests stay green. Add one test where a calm repo with `factory.can_start` renders `factory-start` in the calm list, and one where the card renders `task-summary`.

### 9. Build and docs

- `just web-build` to regenerate `aifactory/src/aifactory/web/static` (committed, inside the allowed path `aifactory/src/aifactory/web/`).
- Write `factory/docs/HAIFA/REFINEMENT-upravy-opravy-a-vylepseni-z-praxe/HAIFA-REFINEMENT-T30-tlacitka-pro-ovladani-tovarny-na-prehled.md` in Czech. Cover what the buttons do, when they are shown, how many runs the start launches and the selection rules, that each started run continues by its `auto_continue`, that a parallel chain now respects the repo-wide limit, the stop/pause progress texts, and the new endpoints `POST /api/repos/{id}/control/start|pause|resume|stop` plus the new overview keys `tasks` and `factory`.

## Verification

From the worktree root:

- `just lint`, `just typecheck`
- `just pytest tests/run/test_factory_start.py tests/run/test_parallel_chain.py tests/run/test_chain_parts.py tests/run/test_queue_prefs.py tests/run/test_task_pause.py tests/run/test_task_stop.py`
- `just pytest tests/web/test_web_overview.py tests/web/test_web_control.py tests/web/test_web_chains.py tests/web/test_web_app.py tests/web/test_web_task_run.py`
- `just web-test` (vue-tsc and vitest)
- `just web-build` (static committed)
- Optional, if time allows: `just pytest tests/e2e/test_multi_repo_browser.py -n0`, since the Overview screen changed.

## Acceptance mapping

- Start is visible iff `factory.can_start` (ready and not excluded > 0, free slot > 0). The click starts `min(free, startable ready)` runs through `start_factory` → `launcher.start`. Collisions and dependencies may lower the number, and the reasons are returned and shown.
- The summary is `tasks` from `board_state` over the repo backlog plus trace runs/PRs, the same states as the kanban.
- Pause/Stop act on every live run of the repo. The UI shows "dobíhá N" → "Pozastaveno"/"Zastaveno" from the run `pause` states and the control's `pending`.
- pytest covers `start_factory`, the chain limit fix, the overview keys and the control endpoints. Vitest covers `RepoControls`, the helpers and `OverviewView`.
