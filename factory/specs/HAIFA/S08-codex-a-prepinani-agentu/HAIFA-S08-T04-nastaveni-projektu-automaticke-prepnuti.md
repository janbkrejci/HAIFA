# HAIFA-S08-T04: Project setting for an automatic harness switch on quota (chain and return)

## Goal

A project gets two new inherited keys in its `index.md`:

- `quota_switch: [codex, pi]`: an ordered chain of backup harnesses. Unset or `[]` means off.
- `quota_switch_back: true|false`: when a harness higher in the chain has its limit back,
  new runs go back up the chain one step at a time.

The full chain of a run is `[primary, *quota_switch]`. `primary` is the harness the run's
binding resolves to without the chain (`effective_override(task_harness_values(task), None)`).
On a `quota` failure the run continues on the next harness in the chain that has quota. When
that one runs out too, it moves on to the next. When the whole chain is used up, the run ends
`failed`/`quota` as it does today. With `quota_switch_back` on, a new run starts one step
higher once that harness has its limit back. Without it, new runs stay on the current harness.

## Design decisions (follow them exactly)

1. **Keys are project-only, like `harness`/`model`/`thinking`.** They go into
   `INHERITED_KEYS`, so a task inherits them from its project through `effective()`, and into
   `CONTAINER_KEYS`. They are rejected on a step with "harness settings are only allowed on a
   project", the same check as the harness keys. In the project's settings, "Zdědit" means
   unset: the effective value is the default (`quota_switch: []`, `quota_switch_back: false`,
   origin `{"source": "default"}`). Add `quota_switch_back` to `_FLAG_DEFAULTS` and
   `FLAG_KEYS`. Give `quota_switch` the default `[]` in `effective_sources`, either with a new
   `_LIST_DEFAULTS = ("quota_switch",)` that yields `{"value": [], "origin": {"source": "default"}}`
   or by extending the defaults logic the same way.
2. **Validation** (`backlog/edit.py::_check_container_value` and `backlog/loader.py`):
   `quota_switch` must be a list of strings. Each one goes through
   `aifactory.harness.canonical()` (an unknown name gives `invalid_value`). The canonical
   names are stored, and a duplicate gives `invalid_value` ("harness X is twice in
   quota_switch"). The loader reports a non-list or non-string value as `invalid_field`, the
   same way it handles `writes`. `quota_switch_back` is a flag (bool).
3. **Precedence over the existing `fallback`**, which is documented in code, the guide and the
   task doc: when the task's effective `quota_switch` is non-empty, the project chain applies
   and the `fallback` of `local.yaml` / `agents.yaml` is ignored for that run. Otherwise the
   existing single fallback works exactly as today: `local.yaml`, then the agent, then
   `defaults`, tried once. `auto_heal: false` disables both.
4. **Machine-local quota state** lives in the trace DB (`.factory/trace.db`, through
   `TaskRunStore`, whose schema setup already does `CREATE TABLE IF NOT EXISTS` and
   `_add_columns`):
   - Table `harness_quota(harness TEXT PRIMARY KEY, exhausted_at TEXT NOT NULL, retry_at TEXT NOT NULL, message TEXT)`.
     Every `quota` failure of a run upserts the harness from `failure_detail.harness`, for the
     legacy fallback path as well. `retry_at` is the parsed reset time when the message gives
     one, else `exhausted_at + 60 min` (`QUOTA_RECHECK = timedelta(hours=1)`). A harness "has
     quota" when it has no row or `retry_at <= now`. When a run ends `succeeded`, delete the
     row of the harness it ended on.
   - Table `project_harness(project_id TEXT PRIMARY KEY, harness TEXT NOT NULL, updated_at TEXT NOT NULL)`:
     the harness of the project's chain that the project is on now. No row means the primary.
   - Store methods: `mark_quota(harness, message, retry_at)`, `clear_quota(harness)`,
     `quota_available(harness, now) -> bool`, `project_position(project_id) -> str | None`,
     `set_project_position(project_id, harness | None)`, where `None` deletes the row.
5. **Reset time parsing** goes in a new `aifactory/harness/quota.py` as
   `retry_at(message: str, now: datetime) -> datetime`. It handles `try again in N
   minute(s)/hour(s)/day(s)` and Claude's `resets 3pm (Europe/Prague)` / `resets 3:30pm
   (Europe/Prague)`, which means the next occurrence of that time in that zone (`zoneinfo`; on
   an unknown zone use the local time). Anything else, or a parse error, gives `now +
   QUOTA_RECHECK`. Keep it small and fully unit-tested. It must never raise.
6. **The return happens per run, not per phase.** Switching harness in the middle of a run
   loses the agents' sessions, so it is unsafe. The return is applied only when a new run
   starts (`run_task` without an explicit `agents_override`, not a resolve or ci-fix run, i.e.
   `resolve_onto is None and workflow_name is None`). Manual `retry_run` keeps the run's
   harness as today. Write the reason in the module docstring and the guide.
7. **What happens at run start** (`run_task`, right after the binding is computed): the
   project id is the task's top ancestor (`ancestors(task)[-1].id`) and the chain is
   `[primary, *quota_switch]`, with entries equal to `primary` dropped from the tail.
   - No chain, or no stored position, or the position is not in the chain (the chain changed):
     clear the stale row and start on the primary.
   - The position is at index `i > 0`:
     - With `quota_switch_back` and `quota_available(chain[i-1])`, start on `chain[i-1]` and
       store it as the new position (when `i-1 == 0`, delete the row). Record a start switch with
       `reason: "quota_return"`.
     - Otherwise start on `chain[i]` and record a start switch with `reason: "quota"`.
   - Starting on another harness means
     `binding = effective_override(task_harness_values(task), {"harness": h})` followed by
     `apply_agents_override` and `override_note`. The model comes from the computer's choice
     for that harness, as in the existing fallback. If `effective_override` raises (for
     example the harness is disabled on this computer), stay on the primary, add a warning and
     clear the position.
   - The start switch is stored in a new `task_runs` column `harness_start TEXT` (JSON), added
     to `_RUN_ADDED_COLUMNS`, `_COLUMNS` and `TaskRunRow` (`harness_start: str | None = None`,
     with a `harness_start_dict()` helper like `failure_detail_dict()`). The record has the
     same shape as `harness_switch`:
     `{"from": {harness, model?, thinking?}, "to": {...}, "reason": "quota"|"quota_return", "auto": true, "source": "projekt <ID> (quota_switch)"}`.
     It is also logged in the run's `request` log as `harness_switch: switch_text(record)`;
     find where `_execute` writes `request_log`, and for a fresh run pass it through `_Job` /
     the request log the same way `RetrySpec.request_log` does.
8. **What happens on a quota failure** (`run/fallback.py::continue_on_fallback`):
   - On every `quota` failure, `mark_quota(detail.harness, detail.message, retry_at(...))`
     before any decision, also when nothing gets switched.
   - Load the task, from base the way `retry_run` does, or pass the task in from the callers.
     `run_task` and `retry_run` already hold `task` when they call `continue_on_fallback`, so
     add a keyword `task: Task | None = None` and pass it. Compute the chain
     (`project_chain(task)`, see below).
   - If the chain has a backup: `tried` is the set of harnesses this run has already used. That
     is the `to` harness of each `harness_switch` in `retries`, the `from` of the first switch
     (or the run's starting harness from `harness_start.to`, else `detail.harness`), and the
     harness that just ran out. The next harness is the first entry after the exhausted
     harness's index in the chain (from index 0 if the exhausted harness is not in the chain)
     that is not in `tried` and has `quota_available`. None left: add the warning
     `quota: chain of project <ID> exhausted` and return the failed result (`failure_kind`
     stays `quota`). Otherwise call `retry_run(..., agents_override={"harness": next}, switch={"auto": True, "source": "projekt <ID> (quota_switch)", "chain": True})`
     and call `set_project_position(project_id, next)` before the retry, because the position
     follows the exhaustion. A retry that cannot start keeps today's warning handling.
   - If there is no chain, keep today's code path unchanged (`configured_fallback`, once).
   - `retry_run`: today `if record is not None: return result  # a switch is never followed by another one`.
     Change it so that when `(switch or {}).get("chain")` is true, the retry goes through
     `continue_on_fallback` again, which walks the chain onward. Termination is guaranteed
     because `tried` only grows and the chain is finite. Operator switches and the legacy
     fallback stay "never followed by another switch".
   - `harness_switch()` / `switch_text()`: for `reason == "quota_return"` print
     `návrat (limit obnoven)` instead of the reason, and keep `kvóta` for `quota`.
9. **A helper module `aifactory/run/quota_chain.py`** keeps `fallback.py` and `task.py` small.
   - `ProjectChain(project_id: str, chain: tuple[str, ...], back: bool)`
   - `project_chain(task, primary: str) -> ProjectChain | None`: reads `effective(task)`
     (`quota_switch`, `quota_switch_back`), canonicalizes, drops duplicates and the primary,
     and returns None when it is empty.
   - `start_harness(store, pc, now) -> tuple[str, str | None]`: the harness and the reason
     (`None` / `"quota"` / `"quota_return"`); it updates the position (rule 7).
   - `next_harness(store, pc, exhausted, tried, now) -> str | None` (rule 8).
   - `SOURCE = "projekt {id} (quota_switch)"`.
   Unit-test it directly with a `TaskRunStore` on a tmp DB.
10. **Visibility.**
    - `fallback.harness_switches(runs)` also emits the run-start switch: the line
      `běh <id>, start: <switch_text>` comes before the retry lines of that run. The PR body
      section "### Přepnutí harnessu" then shows returns too.
    - `heal.switch_text` / `switch_event`: a chain switch is still a retry `harness_switch`,
      so nothing changes. For a `quota_return` record the heal text would be wrong, but
      returns never appear in retries, so leave heal alone.
    - Web: the run detail JSON (`web/runs.py`, next to `"retries": row.retry_list()`) adds
      `"harness_start": row.harness_start_dict()`. The frontend `lib/runs.ts` adds
      `harness_start?: HarnessSwitch | null` to the run detail type. `switchLabel` handles
      `reason === 'quota_return'` as `návrat (limit obnoven)`. `RunDetail.vue` shows a line
      `Start: {{ switchLabel(run.harness_start) }}` (`data-test="harness-start"`) next to the
      attempts list when it is set.

## Files to change

Backend (`aifactory/src/aifactory/`):

- `backlog/model.py`: add `"quota_switch"` and `"quota_switch_back"` to `INHERITED_KEYS`.
  Add `quota_switch_back` to `FLAG_KEYS`. Export `HARNESS_KEYS = ("harness", "model",
  "thinking", "quota_switch", "quota_switch_back")` for the project-only checks.
- `backlog/loader.py`: validate `quota_switch` (list of strings) in both the container and the
  task branches. Flags are already handled through `FLAG_KEYS`.
- `backlog/derived.py`: `_FLAG_DEFAULTS += ("quota_switch_back",)` and the `quota_switch`
  default `[]` (rule 1).
- `backlog/edit.py`: add both keys to `CONTAINER_KEYS`, validate them in
  `_check_container_value`, and use `HARNESS_KEYS` in the "only allowed on a project" check.
- `backlog/taskfile.py`: if `FIELD_ORDER` lists inherited keys for formatting, add the two
  keys after `auto_heal`. Check whether `_apply` needs it; if the order is only for tasks,
  leave it.
- `backlog/__init__.py`: re-export `HARNESS_KEYS` if added.
- `web/backlog.py`: `editable_keys` uses `HARNESS_KEYS` instead of the literal tuple.
  `edit_container` already passes any `CONTAINER_KEYS`, including a list value and `null` to clear.
- `cli.py` (`factory backlog edit`): add `--quota-switch HARNESS [HARNESS ...]` (`nargs="*"`,
  where an empty list sets `[]`) and `--quota-switch-back on|off`, wired in the
  `values` block next to `--auto-heal`. `--clear` gets the new keys automatically through
  `choices=CONTAINER_KEYS`.
- `harness/quota.py` (new): `QUOTA_RECHECK` and `retry_at()` (rule 5).
- `run/store.py`: the two tables, the column `harness_start`, the `TaskRunRow` field and
  helper, and the store methods (rule 4). Make sure `claim()` inserts `harness_start` (it goes
  into `_COLUMNS`).
- `run/quota_chain.py` (new): rule 9.
- `run/task.py`: the start-of-run logic (rule 7). Set `TaskRunRow.harness_start` before
  `store.claim(row)`. On a succeeded final result, call `clear_quota(<run's final harness>)`
  inside `continue_on_fallback` or right after `_execute`; the binding harness is known.
  Pass `task=task` to `continue_on_fallback`.
- `run/retry.py`: the chain continuation (rule 8) and passing `task=task`. Update the module
  docstring and the `retry_run` docstring.
- `run/fallback.py`: `mark_quota`, the chain branch, `harness_switches` with start lines,
  `switch_text` for `quota_return`, and a module docstring that states the precedence (rule 3).
- `web/runs.py`: `harness_start` in the run detail.
- `guide/05-behy-a-review.md`: one Czech paragraph on the project chain, the precedence over
  `fallback` and the per-run return.
- `skill/skill.md`: if it is generated from argparse and a test compares it (check
  `tests/skill/`), regenerate it with the project's recipe (look in `justfile` /
  `tests/skill` for how; for example a `--skill` render). Otherwise edit the CLI section by hand.

Frontend (`aifactory/web/src/`):

- `lib/backlog.ts`: add `'quota_switch'` and `'quota_switch_back'` to `CONTAINER_KEYS`.
  `SETTING_LABELS.quota_switch = 'Automaticky přepnout harness při vyčerpání limitu tokenů'`
  and `SETTING_LABELS.quota_switch_back = 'Vrátit zpět při obnovení limitu'`. Check that
  `settingText` renders a list as `a → b` for `quota_switch`, or special-case it there, and a
  bool as zapnuto/vypnuto.
- `components/backlog/ContainerSettings.vue`:
  - `keys`: treat the two new keys as project-only, like the harness keys, through a shared
    `HARNESS_KEYS` constant in `lib/backlog.ts`.
  - The `quota_switch` row ("Vlastní hodnota", when not inherited) is an editor with
    `data-test="edit-quota_switch"`. It has a checkbox `data-test="quota-switch-on"` (the
    toggle: off means own value `[]`) and, when on, an ordered list of chosen harnesses. Each
    list item has `data-test="quota-chain-item"`, buttons ↑ `data-test="chain-up"`,
    ↓ `data-test="chain-down"` and ✕ `data-test="chain-remove"`, plus a `SelectMenu`
    `data-test="chain-add"` to add one. The add options are `harnessOptions` without the empty
    "Zdědit" entry, minus the harnesses already in the chain, minus the project's own harness
    (`rows.harness.text` when not inherited, else `effective.harness?.value`). The row state
    holds the list as `rows.quota_switch.text` joined by `\n`, so `parse()` for `quota_switch`
    is `splitLines(text)` and `toText` keeps working through `Array.join('\n')`. That keeps
    `input`/`same()` unchanged. A toggle that is on with an empty list must not save `[]`
    silently as "on": show a hint `vyber aspoň jeden harness` and disable Uložit until the
    list is non-empty or the toggle is off.
  - The `quota_switch_back` row is a three-way `SelectMenu` (Zděděno / Zapnuto / Vypnuto),
    the same pattern as `auto_continue`: reuse `flagOptions`, made a function of the key,
    and the `setAutoContinue` logic generalized to `setFlag(key, value)`. `toText`/`parse`
    treat `quota_switch_back` like `auto_continue`. Show the row only when the effective or
    edited chain is non-empty; otherwise it is inert but still shown dimmed. Simplest: always
    show it.
- `lib/runs.ts`: `harness_start` on the run detail type, and `switchLabel` for `quota_return`.
- `components/runs/RunDetail.vue`: the start switch line.
- Fixtures: `test/backlogFixtures.ts`. Add the new keys to `effective` (with defaults) and to
  `editable_keys` so the existing tests still see a coherent detail.

Then run `just web-build` to regenerate and commit `aifactory/src/aifactory/web/static`.

## Tests

Python (`aifactory/tests/`):

- `tests/run/test_quota_chain.py` (new, using the fakes and the `run_repo` helpers from
  `test_quota_fallback.py`: `make_run_repo`, `fake_env`, `Script`, `write`, `commit_all`).
  The project's `index.md` in the run repo gets `quota_switch: [claude, pi]` (and
  `quota_switch_back` as needed). Find the project index path that `make_run_repo` creates
  and edit it with `write`, then `commit_all`. Roster harness `codex`.
  1. `test_chain_switches_in_order`: the planner raises `QuotaExhausted("codex")`, then
     `QuotaExhausted("claude")`, then succeeds on `pi`. Assert the planner calls' harnesses
     are `["codex", "claude", "pi"]`, the run is `SUCCEEDED`, `retries` has two
     `harness_switch` records codex→claude and claude→pi with `source` containing
     `quota_switch`, and the PR body lists both lines in that order.
  2. `test_whole_chain_exhausted_fails_quota`: all three raise quota. The run is `FAILED`
     with `failure_kind == quota`, the harnesses are `["codex", "claude", "pi"]`, and a warning
     contains `chain of project`.
  3. `test_return_when_limit_is_back`: set the position to `pi` and mark `claude` exhausted
     with `retry_at` in the past, through the store API on the repo's trace DB, with
     `quota_switch_back: true`. A new `run_task` runs on `claude`, `run.harness_start.reason
     == "quota_return"`, the position is now `claude`, and the PR body has the start line.
  4. `test_without_return_stays_on_current`: same state, `quota_switch_back: false`. The run
     goes on `pi`, the start reason is `quota`, and the position stays `pi`.
  5. `test_return_waits_while_quota_still_out`: return on, but `claude`'s `retry_at` is in the
     future, so the run stays on `pi`.
  6. `test_project_chain_wins_over_agents_fallback`: `agents.yaml` `defaults.fallback: pi`
     and project `quota_switch: [claude]`. A quota on codex goes to `claude`.
  7. `test_skips_harness_without_quota`: `claude` is marked exhausted (future `retry_at`), so
     a quota on codex goes straight to `pi`.
- `tests/harness/test_quota_reset.py` (new): `retry_at` for `try again in 3 days`,
  `in 45 minutes`, `resets 3pm (Europe/Prague)` (before and after 3pm local), an unknown
  zone, and garbage (`now + 1h`).
- `tests/run/test_quota_chain_unit.py`, or include it in the file above: `project_chain`,
  `start_harness` and `next_harness` with a tmp `TaskRunStore`.
- Backlog: extend the tests next to the existing `edit_container` and loader tests (find them
  with `grep -rln "edit_container\|auto_heal" tests/backlog`). Cover: set
  `quota_switch: [pi, claude]` on a project, get canonical names back, and `effective_sources`
  shows own; a duplicate gives `invalid_value`; an unknown harness gives `invalid_value`; on a
  step gives `invalid_value`; `quota_switch_back` must be a bool; `--clear quota_switch`
  returns to the default `[]` with origin `default`; a loader `invalid_field` for
  `quota_switch: codex` (not a list).
- CLI: `factory backlog edit P --quota-switch pi claude --quota-switch-back on --json` writes
  both keys. Put it in the existing backlog CLI test file.
- Web API: `POST /api/backlog/containers/{id}/edit` with `{"quota_switch": ["pi"], "quota_switch_back": true}`
  succeeds, and `editable_keys` of a project includes both keys while a step's does not. Use
  the existing web backlog test file.
- Run detail API: `harness_start` is present (null by default). Use the existing
  `tests/web` runs test.
- The existing `tests/run/test_quota_fallback.py` and `tests/harness/test_harness_quota.py`
  must pass unchanged.

Frontend (`web/src/components/backlog/ContainerSettings.test.ts`, `lib/runs` tests,
`RunDetail.test.ts`):

- The toggle on, add `pi` then `claude`, move `claude` up, enable the return, and Uložit
  emits `{quota_switch: ['claude', 'pi'], quota_switch_back: true}`.
- The add options exclude harnesses already in the chain and the project harness. Mock
  `useHarnessChoices` / `fetchHarnessSettings` the way other tests do (grep
  `machineHarnesses` in `web/src/**/*.test.ts`).
- An own value loaded from `container.own.quota_switch` shows the list in order. An inherited
  (default) value shows "zděděno · výchozí" and `[]`.
- The toggle off emits `quota_switch: []`. Inherit checked emits `clear: ['quota_switch']`.
- Uložit is disabled while the toggle is on with an empty list.
- A step (`parent !== null`) does not show the rows.
- `switchLabel` for `quota_return`, and `RunDetail` shows `[data-test="harness-start"]`.

## Verification

From the repository root:

- `just lint` and `just typecheck`
- `just pytest tests/run tests/harness tests/backlog tests/web tests/review tests/skill`
- `just web-test`
- `just web-build` (commit the regenerated `aifactory/src/aifactory/web/static`)

## Task documentation

Write `factory/docs/HAIFA/S08-codex-a-prepinani-agentu/HAIFA-S08-T04-nastaveni-projektu-automaticke-prepnuti.md`
in Czech. Cover the keys, the UI, the CLI (`factory backlog edit --quota-switch/--quota-switch-back`),
the API, the precedence (project chain > `local.yaml` > agent `fallback` > `defaults.fallback`;
the legacy fallback is used only without a project chain), the quota state (trace DB, reset
time parsing, the 60 min recheck), the per-run return and why it is not per phase, and where
switches show up.

`docs/decisions.md` (repo root) is outside this task's allowed paths. Updating its "Záložní
harness při vyčerpané kvótě" decision is a follow-up.
