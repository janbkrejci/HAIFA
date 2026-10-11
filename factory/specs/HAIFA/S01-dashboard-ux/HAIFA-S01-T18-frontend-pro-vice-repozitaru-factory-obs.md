# Plan HAIFA-S01-T18: Frontend pro více repozitářů, `factory obs` bez repa a port jen v registru

Design source: `docs/design/multi-repo-dashboard.md` (W5, W8, AR4, AR12, D22). Read-only for you.

## Where things are today

- **Backend for many repos already exists (M3).** `aifactory/src/aifactory/web/app.py` has `create_multi_app(home=, port=, …)`. It serves `GET /api/health` (`app: haifa-dashboard`, `version`, `home`), `GET/POST /api/repos`, `POST /api/repos/inspect`, `DELETE /api/repos/{id}`, `/api/dashboard/settings`, `/api/fs/*`, `/api/overview` and every repo route under `/api/repos/{id}/…`, including `/live`, `/code`, `/restart` and `/limits`. The registry is `web/registry.py` (`Registry`, `dashboard.yaml` in `haifa_home()`, `port`, default `DEFAULT_PORT` 4700). Validation for adding a repo is `web/repos.py` `vet_path` + `check_trace_db` + `Registry.add` (see `repos_add` in app.py).
- **`factory obs` still serves one repo.** `cli.py` `_obs` (around line 2462) calls `repo_root(cwd or --repo)`, takes the port from `load_local(root).port` and uses `create_app(root)`. `web/server.py` `serve(app, port, open_browser=, host=)` opens `dashboard_url`.
- **The port is still in `.factory/local.yaml`.** `config/settings.py` has `LocalSettings.port` (`extra="forbid"`) and `LOCAL_KEYS = ("port", "trace_db")`. `config/run.py` `RunConfig.to_json` emits `local.port`. `cli.py` `_config_show` prints `port`. `web/settings.py` has `LOCAL_FIELDS = ("port","trace_db")`, `_local_form` and `save_settings` with default field `"port"`. `check/machine_rules.py` `local()` emits `local_config_invalid` with the fix "(port, trace_db)".
- **The frontend is single-repo.** `lib/router.ts` uses `#/backlog|runs|review|settings[/params]`. `lib/api.ts` `getApi`/`postApi` call `/api<path>`. `lib/live.ts` opens one shared `EventSource('/api/live')`. `lib/configStatus.ts` is one global ref. `App.vue` shows a repo chip from `/api/health.repo`. `lib/code.ts` uses `/code` and `/restart`, and `lib/limits.ts` uses `/limits`, both through `getApi`.
- **Frontend tests** mock `fetch` with exact URLs like `'/api/backlog'`: 143 occurrences in 18 test files, and 32 tests set `window.location.hash`.

## Decisions (follow them; they fill gaps in the task)

1. **The repo is only in the URL.** `currentRepoId()` parses `window.location.hash` *at call time*, not from a cached ref, so lib functions such as `fetchBacklog()` keep their signatures and call sites.
2. **Global endpoints `/api/code` and `/api/restart` are added to `create_multi_app`.** They need no repo, and the stale-code banner must work on the overview and with no repos. `guard.is_restart_path` already accepts `/api/restart`. `lib/code.ts` uses new global helpers. **Limits stay per repo** (`/api/repos/<id>/limits`, which depends on the repo's harnesses). The LimitsBar shows only on repo screens, and `useLimits` refetches when the repo id changes and returns `[]` without one.
3. **JSON `url` of `factory obs` stays the dashboard root** (today's value, e.g. `http://127.0.0.1:4700/`). The browser opens `url + "#/r/<id>/backlog"` with `--repo`, otherwise `url` (the overview). The text output prints the URL that was opened.
4. **The running-dashboard probe only runs when `check_port` fails**, and never when restarted (`HAIFA_OBS_RESTART`).
5. **Old `local.yaml` with `port`:** `load_local` drops the key before validation, so it never fails. The warning goes to callers that can show it (see B2). Saving local settings from the dashboard keeps the file's existing `port` line untouched (only the sent keys change, as the module doc promises). `factory check` tells the user to delete it.
6. **`#/repos` and `#/repos/add`** are in scope only as routes. Adding and removing repos in the UI is out of scope:
   - `#/repos` ("Spravovat…") shows the same repo list as the overview, titled "Repozitáře".
   - `#/repos/add` ("Přidat repozitář…") shows `EmptyScreen` with the hint `factory obs --repo <cesta>`.

## Backend changes

### B1 `config/settings.py`
- Remove `port` from `LocalSettings`. Keep `DEFAULT_PORT = 4700`, which the registry uses, and update its docstring to "dashboard port when the registry sets none".
- `LOCAL_KEYS = ("trace_db",)`. Keep a separate check in `parse_project_settings`: `port` in `config.yaml` gives the issue `'port' is the dashboard's; set it in the registry (factory obs --port, dashboard.yaml)`. Keep the misplaced-key loop for `trace_db`.
- Add `LOCAL_PORT_IGNORED = "local_port_ignored"` and a function returning settings plus warnings:
  ```python
  def load_local_checked(root: Path) -> tuple[LocalSettings, list[str]]:
      # parse; if data has "port": pop it and add the warning
      # f"local_port_ignored: {LOCAL_FILE}: port is ignored, the dashboard port is in the registry; delete the port line"
  def load_local(root: Path) -> LocalSettings:
      return load_local_checked(root)[0]
  ```
  Export it from `config/__init__.py`. All other `load_local` callers (`run/task.py`, `config/commit.py`, `web/repos.py`, `web/live.py`, `library/install_commit.py`, `check/repo_rules.py`) keep working because `port` is dropped silently.

### B2 `config/run.py`
- `load_run_config` uses `load_local_checked` and appends its warnings to `warnings`.
- `to_json()["local"]` becomes `{"trace_db": …}`, with no port.

### B3 `cli.py`
- `_config_show`: drop the `port` line. The warnings already print to stderr, and the JSON already carries them through `strip_payload`/`warnings`.
- **`_add_obs_command`**: `--repo` help becomes "register this repository and open it (any folder inside it)". `--port` help becomes "port (default: port in the registry dashboard.yaml, else 4700)".
- **`_obs` rewrite** (keep the port range check and the `--host`, restart and Ctrl+C message behaviour):
  1. `home = haifa_home()` and `registry = Registry(home)`. `state, warnings = registry.snapshot()`. Port is `args.port`, else `state.port` (4700 when the file is missing; with a broken file the snapshot gives EMPTY plus a warning, which stays a warning).
  2. With `--repo`, use the same steps as `repos_add`:
     ```python
     examined = vet_path(args.repo, state)
     root = examined.root
     entry, created = registry.add(root, check=lambda cur: check_trace_db(root, cur))
     ```
     A `RepoError` becomes `_emit_fail(exc.code, exc.message, exit_code=2, data=exc.data or None)` in JSON, or `factory obs: <code>: <message>` on stderr with exit 2. After registering, call `load_local_checked(root)` and add any warning to `warnings`; it means the dashboard does not use that port. Fold that into one shared helper, e.g. `web/repos.py: register_repo(registry, raw) -> tuple[RepoEntry, bool]`, and use it from both `repos_add` and the CLI so the validation is literally the same. `fragment = f"#/r/{entry.id}/backlog"`. Without `--repo`, `fragment = ""` and there is no git call at all.
  3. `host = resolve_host(args.host)`, `url = dashboard_url(port, host)` and `restarted = …`.
  4. `check_port(...)`. On `PortInUseError`, when not restarted, call `web_server.probe_dashboard(port, host)` (new). If it returns True, the dashboard is ours and we reuse it:
     - open `url + fragment` with `webbrowser.open` unless `--no-open`;
     - print the envelope (`--json`) or `HAIFA dashboard už běží: <url+fragment>`;
     - return 0 with `reused: True`.
     Otherwise it is `port_in_use` as today.
  5. `app = web_app.create_multi_app(home=home, port=port, allowed_hosts=allowed_hosts(host))`.
  6. JSON data: `{"url", "host", "port", "repo": str(root) or None, "version", "repo_id": entry.id or None, "home": str(home), "reused": False}`, emitted with `warnings`. In text mode print `HAIFA dashboard: <url+fragment>  (Ctrl+C ukončí…)` and each warning to stderr as `warning: …`.
  7. `web_server.serve(app, port, open_browser=…, host=host, open_path=fragment)`.
- Update the module docstring line about `obs` if it mentions the repo.

### B4 `web/server.py`
- `serve(..., open_path: str = "")` opens `dashboard_url(port, host) + open_path`.
- New `probe_dashboard(port, host, timeout=1.0) -> bool`: `urllib.request.urlopen(f"{dashboard_url(port, host)}api/health")`, parse JSON, return True iff `ok` is true and `data.app == "haifa-dashboard"`. Any exception returns False. Import `APP_NAME` lazily or duplicate the constant, so there is no import cycle (app.py imports server).
- Update the docstrings that say "the repository".

### B5 `web/app.py`
- In `create_multi_app`, add `Route("/code", code_state, methods=["GET"])` and `Route("/restart", restart_dashboard, methods=["POST"])` to the top-level `/api` routes. They don't use `_repo`. Keep them in `_repo_routes` too.
- Update the module docstring: the global code/restart, and that settings carry no `port`.
- Leave `create_app` in place; tests use it.

### B6 `web/settings.py`
- `LOCAL_FIELDS = ("trace_db",)`.
- `_local_form` returns only `{"trace_db": …}`. Validate `raw` with `port` popped, so an old file does not show an issue in the form. The `local_port_ignored` warning is added to the GET/POST warnings through `_view`: put it in `warnings` when the file has `port`.
- `_parse_body`: when `local` contains `port`, raise `SettingsError("invalid_value", "invalid settings: port", [_issue(LOCAL_FILE, "port", "the dashboard port is in the registry, not in .factory/local.yaml")])`. That gives HTTP 422 `invalid_value`; check that the app's `_settings_error` maps `invalid_value` to 422. Run this check before the generic unknown-key check.
- `save_settings` local: validate `merged` with `port` removed (`{k: v for k, v in data.items() if k != "port"}`) and write `merged` as is, keeping the old port line. The `_model_issues` default field becomes `"trace_db"`.

### B7 `check/machine_rules.py` (M6)
- In `local(ctx)`, use `load_local_checked`. If the file has `port`, yield:
  ```python
  Finding("local_port_ignored", "machine", "warning",
          f"{LOCAL_FILE}: port is ignored; the dashboard port is in the registry (dashboard.yaml)",
          "smaž řádek port z .factory/local.yaml")
  ```
  Keep `local_config_invalid` and change its fix text to "fix .factory/local.yaml (trace_db)".
- Add `"local_port_ignored"` to `ISSUE_CODES["check"]` in `skill/codes.py` (`test_check_codes_complete` requires it).

### B8 Python tests (update and add)
- `tests/config/test_config_settings.py`, `test_config_commit.py`, `test_config_cli.py`, `tests/web/test_web_settings.py`, `tests/check/test_factory_check.py` and every other `.port`/`port:` use of `LocalSettings`: run `grep -rn "port" aifactory/tests | grep -v "import\|report\|support"` and fix them. Expected results:
  - `run.local.port` is gone;
  - `config show --json` has `local == {"trace_db": …}`;
  - an old `local.yaml` with `port: 2222` loads, and the run config warnings contain `local_port_ignored`;
  - settings GET has no `local.port`, and settings POST `{"local": {"port": 4800}}` returns 422 `invalid_value` with issue id `port`;
  - `factory check` on a repo with `port` in `local.yaml` reports `local_port_ignored` with that fix and stays ok when there is no error;
  - `port` in `config.yaml` is still an issue.
- **`tests/web/test_obs_cli.py`** (rewrite; `HAIFA_HOME=tmp_path/"home"` through monkeypatch in a fixture; `fake_serve(app, port, *, open_browser, host, open_path="")`; patch `webbrowser.open` and `web_server.probe_dashboard`):
  - no `--repo`, cwd = tmp dir outside git (`monkeypatch.chdir`): rc 0, `repo`/`repo_id` None, `home` == HAIFA_HOME, `reused` False, port 4700, the app is a multi app (`app.state.registry`), and nothing is written to the registry;
  - `--repo` on a git repo (`web_repo.git_repo`): `dashboard.yaml` contains the entry, `repo_id` is set, and `open_path == "#/r/<id>/backlog"`. A second call is idempotent (same id);
  - `--repo` on a non-git dir gives `not_git` exit 2, and a missing path gives `path_not_found`;
  - port order: `--port` > registry `port: 4811` (write `dashboard.yaml`) > 4700;
  - running dashboard: `check_port` raises and `probe_dashboard` returns True, so rc 0, `reused` True, serve not called, the registry written and `webbrowser.open` called with the fragment URL (not with `--no-open`);
  - foreign service: `probe_dashboard` returns False, so `port_in_use`;
  - old `local.yaml` with `port: 4811` and `--repo`: rc 0, port 4700 (not 4811), warnings contain `local_port_ignored`. Also run `config show --json`, `check --json` and `obs --json` on that repo: each returns ok/0 and contains the warning or finding;
  - keep the existing tests (host, bad port, runs-that-go-on message), adapted.
- Add a server test for `probe_dashboard` with a tiny stdlib `http.server` on a free port, or monkeypatch `urlopen`: True for `app: haifa-dashboard`, False for other JSON or non-JSON. Add an app test that the multi app answers `GET /api/code` and `POST /api/restart` (restart stubbed).
- No network or model access. Loopback in tests is fine.

## Frontend changes (`aifactory/web/src/`)

No new dependencies. Icons come from `lucide-vue-next` (already a dependency) and UI from `components/ui/` (`SelectMenu`, `Tooltip`, `Spinner`, `BackLink`); reuse the dropdown pattern there.

### F1 `lib/router.ts`
```ts
export type Screen = 'backlog' | 'runs' | 'review' | 'settings'
export type Page = 'overview' | 'repos' | 'repos-add' | 'repo'
export interface Route { page: Page; repo: string | null; screen: Screen; params: string[] }
```
- `parseRoute(hash)`:
  - `''`, `#/` and `#/overview` give overview;
  - `#/repos` gives repos, and `#/repos/add` gives repos-add;
  - `#/r/<id>` gives repo/backlog (redirect), `#/r/<id>/<screen>/…` gives repo, and an unknown screen gives backlog;
  - anything else, including the legacy `#/backlog…`, `#/runs…` and so on, gives overview.
  The id is decoded. Return `redirect: string | null` when the canonical hash differs (legacy, empty, `#/r/<id>`, unknown). The hashchange handler and init apply it with `history.replaceState(null, '', canonical)`, so legacy URLs end on `#/overview`.
- `currentRepoId(): string | null` reads `parseRoute(window.location.hash).repo`.
- Refs: `useRoute(): Ref<Screen>` stays (screen of the repo page, `backlog` otherwise), `useRouteParams()` stays, and new `usePage(): Ref<Page>` and `useRepoId(): Ref<string | null>`.
- Hrefs: `repoHref(id, screen = 'backlog', ...params)`, `OVERVIEW_HREF = '#/overview'`, `REPOS_HREF = '#/repos'` and `REPOS_ADD_HREF = '#/repos/add'`. `hrefFor`, `taskHref`, `runHref`, `reviewHref`, `graphHref` and `newContainerHref` build `#/r/<currentRepoId()>/…` (with `encodeURIComponent`) and fall back to `OVERVIEW_HREF` without a repo. Their signatures don't change.
- `SCREEN_LABELS` (from `SCREENS`) for the title.

### F2 `lib/api.ts`
- `apiBase(): string` returns `/api/repos/${encodeURIComponent(id)}`. Without a repo, `getApi`/`postApi` throw `new ApiError('no_repo', 'Není vybrané žádné repo')` and do not call fetch.
- `getApi`/`postApi` use `apiBase() + path`.
- New `getGlobal<T>(path)` and `postGlobal<T>(path, body?)` fetch `/api${path}`, with the same envelope handling, refactored onto a shared internal `request(url, init)`.
- `Health` becomes `{ app: string; version: string; home: string }` and `fetchHealth` uses `getGlobal`. Add:
  ```ts
  export type RepoStatus = 'ok' | 'uncommitted' | 'not_installed' | 'missing' | 'not_git'
  export interface RepoItem { id: string; name: string; path: string; added_at: string; status: RepoStatus; factory: Record<string, unknown> | null }
  export function fetchRepos(): Promise<{ repos: RepoItem[]; home: string }>  // getGlobal('/repos')
  ```
- `lib/code.ts`: `fetchCode` and `restartDashboard` use `getGlobal`/`postGlobal`.

### F3 `lib/live.ts`
- Keep one `EventSource` per tab. `open()` uses ``new EventSource(`${apiBase()}/live`)`` and does nothing when there is no repo; remember `openRepo`.
- `export function reopenLive(): void` closes and opens again if there are subscribers, then calls `resyncAll()` so screens reload.
- Visibility: install a `document.visibilitychange` listener once at module load or on the first subscribe. When the tab is `hidden`, `close()`. When it becomes `visible` with subscribers, `open()` and `resyncAll()`.
- The source does not survive a repo switch by itself, because the repo component remounts and the subscribers unsubscribe, so the count reaches 0 and the source closes. Also handle it defensively: in `open()`, if `openRepo !== currentRepoId()`, close first.
- `resetLiveForTests` also resets `openRepo`.

### F4 `lib/configStatus.ts` (D4 per repo)
- `const statuses = reactive(new Map<string, {status, error}>())`, or `ref<Record<string, …>>`.
- `useConfigStatus(repoId?: string)` returns `{ status, error, refresh }` as computeds for `repoId ?? currentRepoId()`. `refresh` records the result under the repo it was started for, so a late answer for another repo cannot leak into the current one.
- `SettingsView` keeps calling `useConfigStatus()`.

### F5 `lib/settings.ts`, `components/settings/SettingsForm.vue` and `test/settingsFixtures.ts`
- `LocalSettings = { trace_db: string }`. Remove `port` from `SettingsFormValues`, `formValues`, `settingsDiff` (no `local.port`) and the form field (`data-test="port"`, `error-port`). Keep the `trace_db` field. Remove `portValue` if it is only used for port; it is also used for `max_parallel_runs`, so rename it to something like `intValue` instead.
- Fixtures: `local: { trace_db: '.factory/trace.db' }`.

### F6 New `components/RepoScreen.vue` (rendered by App with `:key="repoId"`)
- It contains what used to be per repo in App.vue:
  - `ConfigStatusBanner` and `BacklogStatusBanner`, each with the status for this repo;
  - `useLive` handlers (config, backlog, names);
  - `refreshNames` on mount;
  - the focus listener;
  - the screen component `VIEWS[screen]`.
  Because it is keyed by id, switching repos unmounts everything, which resets view data, the run cursors in RunsView, subscriptions and banners.
- `lib/backlogStatus.ts` and `lib/names.ts` are shared singletons. Call `reset` on mount, or key them by repo the same way as configStatus. At minimum, clear their state on RepoScreen mount (add `resetBacklogStatus()` and `resetNames()`) so the previous repo's data never shows.
- The `backlog-dirty` padding class moves with it: emit an event or keep the computed in App reading the shared backlogStatus.

### F7 New `components/RepoSwitcher.vue` (replaces `.repo-chip` in the topbar; root class `repo-switcher`, `data-test="repo-switcher"`)
- The button shows the current repo name, or "Přehled" or "Repozitáře" off a repo page, plus `v<version>` from health. If health fails, show "API nedostupné" (class `api-down`), as today.
- Menu items, as links (`<a href>`):
  - "Přehled" goes to `#/overview` (`data-test="switch-overview"`);
  - one item per repo (`data-test="switch-repo-<id>"`): the name, the parent folder (`path` without its last segment, dim), and a label `nenainstalováno` for `not_installed` or `chybí` for `missing` (`data-test="repo-label"`). The href is `repoHref(id, currentScreen)` with no params, so `#/r/haifa/review/T1` becomes `#/r/sandbox/review`;
  - "Přidat repozitář…" goes to `#/repos/add`, and "Spravovat…" goes to `#/repos`.
- Close on outside click and Escape. Reuse the existing ui patterns; `noNativeUi.test.ts` forbids native tooltips/selects, so check what it forbids. Refresh the repo list when the menu opens.

### F8 New views
- `views/OverviewView.vue` with `fetchRepos()`:
  - no repos: `EmptyScreen` titled "Žádné repozitáře" with a hint containing `factory obs --repo <cesta>`;
  - otherwise a list (`data-test="overview-repo"`) with the name, path, status text (ok / neuložená konfigurace / nenainstalováno / chybí / není git) and a link "Backlog" to `repoHref(id,'backlog')`;
  - title "Přehled". There is no activity section (out of scope).
- `views/ReposView.vue` ("Repozitáře") is the same list, and can share a `components/RepoList.vue`.
- `EmptyScreen.vue` gets an optional `code?: string` prop rendered in `<code>` and an optional default slot for a link.
- Unknown repo id: `EmptyScreen` titled ``Repo ${id} v dashboardu není`` with a `BackLink`/`<a href="#/overview">` to the overview (`data-test="unknown-repo"`).

### F9 `App.vue`
- On mount, load `fetchHealth()` (global) and `fetchRepos()`. Reload the repos when `usePage`/`useRepoId` changes and on window focus.
- The nav (`SCREENS` tabs) shows only on the repo page. Its hrefs come from `hrefFor`, which is now repo-aware.
- The LimitsBar renders only on the repo page, and `useLimits` is keyed on the repo id (decision 2). The CodeStaleBanner stays global.
- Main:
  - `page === 'overview'`: `repos.length === 0` gives EmptyScreen, otherwise OverviewView;
  - `repos`: ReposView;
  - `repos-add`: EmptyScreen with the hint;
  - `repo`: wait until the repos have loaded (spinner), then the unknown-repo screen when the id is absent, else `<RepoScreen :key="repoId" />`.
- Title: `watchEffect` sets `document.title`:
  - repo page: `${repoName} · ${screenLabel} · HAIFA`;
  - overview: `Přehled · HAIFA`;
  - repos: `Repozitáře · HAIFA`;
  - repos-add: `Přidat repozitář · HAIFA`.

### F10 Frontend tests (vitest)
- Global test setup: add `src/test/setup.ts`, registered as `test.setupFiles` in `aifactory/web/vite.config.ts`. It sets `window.location.hash = '#/r/haifa/backlog'` before each test, unless a test sets its own hash. Then mechanically rewrite the repo-scoped URLs in existing tests, `'/api/<x>'` to `'/api/repos/haifa/<x>'`. That excludes `/api/health`, `/api/repos`, `/api/code` and `/api/restart`, which become global. Rewrite the hashes `#/runs/…` to `#/r/haifa/runs/…` and so on. In App.test the health mock becomes `{app:'haifa-dashboard', version, home}`, and a `/api/repos` mock returns `[{id:'haifa', name:'HAIFA', path:'/work/HAIFA', status:'ok', …}]`.
- New and updated tests:
  - `lib/router.test.ts`: parse of every route; legacy `#/backlog/T1` gives overview with a redirect; `#/r/x` redirects to `#/r/x/backlog`; `hrefFor`, `taskHref`, `runHref`, `reviewHref`, `graphHref` and `newContainerHref` carry the current repo; ids are encoded.
  - `lib/api.test.ts`: `getApi('/backlog')` fetches `/api/repos/haifa/backlog`; `postApi` likewise; no repo throws `no_repo` without fetch; `getGlobal('/health')` fetches `/api/health`.
  - `lib/live.test.ts`: the URL is `/api/repos/haifa/live`; after changing the hash and remounting (or `reopenLive()`) a new source for the new repo opens and the old one is closed; `visibilitychange` to hidden closes it, back to visible opens a new one and calls the `resync` handler. Use `FakeEventSource` and stub `document.visibilityState` with `Object.defineProperty`.
  - `App.test.ts`:
    - switching `#/r/haifa/runs` to `#/r/other/runs` remounts the screen (the RunsView fetch for `other` happens and old data disappears) and the config banner shows other's status, not haifa's;
    - the switcher lists Přehled, the repos with `nenainstalováno`/`chybí` labels and the parent folder, Přidat repozitář… and Spravovat…, and keeps the screen without params;
    - the title is `HAIFA · Běhy · HAIFA`;
    - no repos on `#/overview` shows the EmptyScreen with `factory obs --repo`;
    - an unknown id shows "Repo nope v dashboardu není" with an `#/overview` link;
    - the overview lists repos with a Backlog link;
    - the legacy hash redirects.
  - `SettingsView.test.ts` / `SettingsForm`: no `[data-test="port"]`, and `settingsDiff` never produces `local.port`.
  - Update `components/ConfigStatusBanner.test.ts` if its props change, and `lib/settings.test.ts`.

### F11 Build
`just web-build` writes into `aifactory/src/aifactory/web/static/`. Commit the result as part of the change; the workflow commits it. Old hashed assets are removed by `emptyOutDir`.

## E2E (`aifactory/tests/e2e/`)
- `f3_repo.py`:
  - `obs_server` already passes `HAIFA_HOME=home`, a tmp dir. Keep `--repo repo`, so the server registers it. Read the repo id from the registry (`yaml.safe_load(home/"dashboard.yaml")`, the id of the entry whose path equals the repo) or derive it from the folder name slug. Yield `url` and expose `repo_id`, e.g. return a small dataclass or yield `(url, repo_id)`.
  - `api_get` callers (`task_runs`, `run_state`, `runs_report`) use `/api/repos/<id>/runs…`. `_healthy` keeps `/api/health`.
- `test_f3_browser.py`:
  - `page.goto(f"/#/r/{repo_id}/backlog")`;
  - `_nav` and the URL regexes become `#/r/<id>/<screen>` (e.g. `rf"#/r/{id}/runs/{run_id}$"`, `#/r/{id}/backlog/M01-S01-T\d+$`);
  - every `href.endswith("#/runs/…")` becomes the `#/r/<id>/runs/…` form;
  - grep the file for `#/`.
- `test_limits_layout.py`:
  - mock `/api/health` as `{app, version, home}`, `/api/repos` as one repo `haifa`, and `/api/repos/haifa/limits` (and other `/api/repos/haifa/*` with `{}`, as now);
  - goto `http://haifa.test/#/r/haifa/backlog`;
  - replace `.repo-chip` with `.repo-switcher` in the waits, the control boxes and the visibility asserts. Keep the switcher compact enough that the layout assertions still pass at 1280–1600 px.

## Out of scope (do not build)
Overview activity, add/remove repo UI (inspect, fs picker), the Factory tab, port in the UI, the `just dash` recipe (leave `justfile` unchanged unless a recipe breaks), and `vendor/`/`prototype/`.

## Verification
Run each of these from the worktree root; each must exit 0:
1. `just web-build` (vue-tsc + vite), followed by `git status aifactory/src/aifactory/web/static` showing the new build.
2. `just test` (web-test: vitest + typecheck, then the pytest suite).
3. `just typecheck`.
4. `just lint` (ruff check + format; run `cd aifactory && uv run ruff format .` first if needed).
5. `just e2e` (Playwright, system Chrome; `just e2e-install` if no Chrome).
6. Manual smoke (optional):
   - `HAIFA_HOME=$(mktemp -d) uv run --project aifactory factory obs --no-open --json --port 4799` from `/tmp` shows ok with `repo_id: null`;
   - a second terminal running `… factory obs --repo . --port 4799 --json` shows `reused: true` and exit 0.

## Pitfalls
- `test_skill.py::test_check_codes_complete` needs `local_port_ignored` in `ISSUE_CODES["check"]`. `test_error_codes_complete` scans literal codes in `_emit_fail` calls in cli.py, so pass `exc.code` (dynamic) for RepoErrors and do not invent new literal error codes. `no_repo` is frontend only.
- The `.claude/` skill mirror is protected. Do not edit it. If a test compares this repo's own mirror with `render_skill()`, report that instead of editing `.claude/`.
- `web/registry.py` imports `DEFAULT_PORT` from `config.settings`, so keep the constant.
- `create_app` (single repo) stays for existing tests; its `/api/settings` loses port too.
- Keep the Windows paths (`oscompat`) as they are; the CLI uses `Path`, and the switcher's parent folder split handles `\` and `/`.
