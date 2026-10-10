# HAIFA-S01-T17: API for the Factory tab: check, plan, apply and base pull

## Goal

Expose `factory check`, `factory init --dry-run|--commit`, `factory update --commit`,
`factory config commit` and `factory config pull` through the per-repository dashboard
API. The endpoints call the **same core functions** as the CLI and answer with the same
envelopes. No new core logic, no frontend.

New routes (relative to the repo prefix: `/api/repos/{id}/` in `create_multi_app`,
`/api/` in `create_app(repo)`; both come from `_repo_routes()`, so adding them there
serves both):

| Method | Path | Core function |
|---|---|---|
| GET  | `/factory/check?offline=&fresh=` | `aifactory.check.run_check` (+ registry finding `trace_db_shared`) |
| POST | `/factory/plan` `{action, options, target?}` | `commit_init(dry_run=True)` / `run_update(dry_run=True, commit=True)` / `commit_config(dry_run=True)` |
| POST | `/factory/apply` `{action, digest, options, target, message}` | same functions with `expect=digest`, `message=` |
| POST | `/config/pull` | `aifactory.config.commit.pull_config` |

## Files to touch

1. **New** `aifactory/src/aifactory/web/factory.py` – the sync logic (body validation,
   option mapping, core calls, check cache, error→HTTP mapping data). Keeps `app.py` thin,
   like `web/settings.py` / `web/backlog.py`.
2. `aifactory/src/aifactory/web/repos.py` – add per-repo factory state to `RepoContext`.
3. `aifactory/src/aifactory/web/app.py` – four async handlers, routes in `_repo_routes()`,
   `app.state.check_machine` in `_shared_state`, module docstring section.
4. `aifactory/src/aifactory/skill/codes.py` – add the new error code `busy`
   (`RepoError` is in `ERROR_CLASSES` of `tests/test_skill.py`, so every literal code raised
   with it must be registered). Do **not** add `trace_db_shared` to `ISSUE_CODES["check"]`
   (`test_check_codes_complete` compares it with `Finding(...)` calls under `check/` only;
   the finding is built in `web/`). `trace_db_shared` is already an error code.
5. **New** `aifactory/tests/web/test_web_factory.py` (+ optionally a small fixture module
   `aifactory/tests/web/factory_fixture.py`).
6. `app_docs/HAIFA-S01-T17-…md` is the documenter's job (not the builder's).

Do not touch `vendor/`, `prototype/`, `.factory/`, core modules (`library/`, `config/`,
`check/`, `providers/`) – their behaviour is reused as is.

## 1. `web/repos.py`: per-repo state

```python
@dataclass
class FactoryState:
    """Per-repository state of the Factory tab: one apply/pull at a time, the check cache."""
    lock: threading.Lock = field(default_factory=threading.Lock)
    checks: dict[bool, tuple[float, CheckReport, str]] = field(default_factory=dict)
    # key: offline flag -> (monotonic time, report, checked_at ISO UTC)
```

Add to `RepoContext`: `factory: FactoryState = field(default_factory=FactoryState, repr=False)`
(keep it last, after `live`). `RepoContexts` already keeps one context per registered id
(and recreates it when the path changes), and `create_app` builds one fixed context, so the
lock and cache are per repository automatically → isolation between repos. Import
`CheckReport` only under `TYPE_CHECKING` (or type the tuple as `Any`) to keep the import
graph light. If `FactoryState` fits better in `web/factory.py`, define it there and import
it in `repos.py` – but avoid a cycle (`factory.py` must then not import `repos.py`).

## 2. `web/factory.py`

```python
CHECK_TTL = 60.0
ACTIONS = ("init", "update", "config_commit")
TARGETS = ("base", "pr")          # base = direct commit to base; pr = pull request
_clock = time.monotonic            # module attribute so tests can monkeypatch it

class UsageError(Exception): message   # -> HTTP 400 usage_error (or reuse backlog.UsageError)

@dataclass
class Failure(Exception):          # normalised core error
    code: str; message: str; status: int
    data: Mapping | None = None; issues: list[dict] = []
```

### 2.1 Check

```python
def check_view(root, state: FactoryState, *, offline: bool, fresh: bool,
               machine: Machine | None, registry_state: RegistryState | None,
               repo_id: str | None) -> tuple[dict, bool]:   # (data, ok)
```

- Cache: `entry = state.checks.get(offline)`; reuse when `not fresh` and
  `_clock() - entry.time < CHECK_TTL`; else
  `report = check.run_check(root, offline=offline, machine=machine, require_repo=True)`
  (call through the module, `from aifactory import check` then `check.run_check`, so a test
  can monkeypatch it) and store it with the time and `datetime.now(UTC)` ISO string.
  `NotARepositoryError` → `Failure("not_a_repository", …, 422)`.
- Registry finding (computed on **every** request, not cached; only when
  `registry_state` is not None, i.e. the multi app): call
  `repos.check_trace_db(root, registry_state)`; on `RepoError` with code `trace_db_shared`
  add `Finding("trace_db_shared", "machine", "error", exc.message, fix="set trace_db in
  .factory/local.yaml to a file no other registered repository uses", action=None)`.
  Use `dataclasses.replace(report, findings=(*report.findings, finding))` so `ok` and
  `counts()` are recomputed by `to_json()`. Note `check_trace_db` skips the entry that is
  the repo itself (`same_repo`), so it only fires for another registered repo.
- `data = {**report.to_json(), "checked_at": iso, "cached": bool}`.
- Same envelope as `factory check --json`: `report.ok` → `envelope_ok(data)`; else
  `envelope_fail("checks_failed", f"{n} error(s): {codes}", data=data)` (same message
  format as `cli._check`). HTTP **200** in both cases – the check itself succeeded; the
  envelope's `ok` tells the result. Document this.
- The check is read-only and does **not** take `state.lock`.

### 2.2 Body validation (pure, before any core call)

`parse_plan_body(body)` / `parse_apply_body(body)`:

- Allowed top-level keys – plan: `action`, `options`, `target`; apply: `action`, `digest`,
  `options`, `target`, `message`. **Any other key → 400 `usage_error`** (this enforces the
  hard rule that apply takes no paths/file contents: there is no `files`, `path`, `repo`,
  `content` …; the repo always comes from the request scope).
- `action` required, one of `ACTIONS`, else `usage_error`.
- `target` optional, default `"base"`, one of `TARGETS`. On plan it only selects which
  blockers are reported (`not_on_base` etc. exist only for the direct target); the digest
  does not depend on the target (`publish.plan_digest`), so a plan made for `base` can be
  applied as `pr` with the same digest.
- `digest` (apply) required non-empty string, else `usage_error`.
- `message` optional string or null.
- `options` optional object (default `{}`); keys allowed per action, unknown key →
  `usage_error`:
  - `init`: `agents` (list[str]), `bind` (object `{agent: {harness, model?, thinking?}}`),
    `workflows` (list[str]), `base` (str), `provider` (`local|github|azure`), `azure`
    (object with optional `organization`, `project`, `repository` strings),
    `backlog_dir`, `specs_dir`, `docs_dir` (str). `null` for any key = not given.
  - `update`: `take`, `merge`, `migrate` (list[str] each).
  - `config_commit`: no options (empty object or missing).
  Type errors → `usage_error` naming the key.

`init` option mapping (mirror `cli._init` / `_init_plan`):

```python
bindings = [parse_binding(_bind_text(agent, spec)) for agent, spec in bind.items()]
# _bind_text: f"{agent}={harness}:{model or ''}:{thinking or ''}" (strip trailing ':');
# reject harness/model/thinking values containing ':' '=' or ',' and a missing/empty
# harness with LibraryStoreError("invalid_value", ...) BEFORE building the text.
provider = options.provider; if provider is None and any(azure values): provider = "azure"
if azure given and provider not in (None, "azure"): conflicting_options (like _init_conflict)
kwargs = dict(base=..., provider=provider, azure=azure_dict_or_None, bindings=bindings,
              agents=..., workflows=..., backlog_dir=..., specs_dir=..., docs_dir=...)
```

`parse_binding` validates harness name and thinking level (`invalid_value`).

### 2.3 Plan and apply

```python
def plan(root, req) -> tuple[dict, list[str]]
def apply(root, req) -> tuple[dict, list[str]]
```

Core calls (`pr = req.target == "pr"`):

| action | plan | apply |
|---|---|---|
| init | `commit_init(root, dry_run=True, pr=pr, **kw)` | `commit_init(root, expect=digest, message=msg, pr=pr, **kw)` |
| update | `run_update(root, take, merge, migrate, dry_run=True, commit=True, pr=pr)` | `run_update(root, take, merge, migrate, commit=True, pr=pr, expect=digest, message=msg)` |
| config_commit | `commit_config(root, dry_run=True, pr=pr)` | `commit_config(root, pr=pr, expect=digest, message=msg)` |

(`from aifactory.library.install_commit import commit_init`,
`from aifactory.library.update import run_update`,
`from aifactory.config.commit import commit_config, pull_config`,
`from aifactory.library.install import parse_binding` – import lazily inside the functions
like the CLI does, to keep dashboard start-up fast.)

- Plan data = `{"action": action, **result.to_json()}`; warnings = `list(result.warnings)`.
  This already contains `digest`, `files`, `blockers`, `target`; for `init` also
  `detected` and `available` (`InitPlan.to_json`). Plan never writes and does not take the
  lock.
- Apply success data = `{"action", "commit", "pushed", "pr", "warnings", "committed",
  "advanced", "branch"}` taken from `result.to_json()` (`pr` is `{id, url, branch}` or
  null); envelope warnings = same list. `config_commit` without changes returns
  `committed: false, commit: null` (core behaviour) – keep it.
- Update always uses `commit=True` (direct or PR); the working-tree mode of `factory update`
  is not offered (the tab publishes commits).

### 2.4 Error → HTTP mapping

Catch `LibraryStoreError`, `ConfigCommitError`, `ProviderError`, `ConfigError` and turn
them into `Failure(code, message, status, data, issues)`.
`issues`: `LibraryStoreError.issues` are `Issue` objects → `[i.to_dict() for i in …]`;
`ConfigCommitError.issues` are dicts already. `data` = `exc.data` (the core puts the new
plan JSON there for `plan_changed` and for blockers – keep it unchanged, so 409
`plan_changed` carries the new plan with its new `digest`). For `init`, add `"action"` to a
dict copy of `data` when present (optional, nice for the UI).

Status:

```python
_STATUS = {
  # 409: state conflicts / blockers
  "plan_changed": 409, "busy": 409, "run_in_progress": 409, "not_on_base": 409,
  "base_behind": 409, "base_diverged": 409, "base_moved": 409, "dirty_paths": 409,
  "dirty_base": 409, "already_installed": 409, "existing_config": 409,
  "config_not_committed": 409, "not_onboarded": 409, "merge_conflict": 409,
  "no_remote": 409, "library_dirty": 409, "library_behind": 409, "library_diverged": 409,
  # 422: invalid input / plan
  "invalid_plan": 422, "invalid_value": 422, "conflicting_options": 422,
  "unknown_base": 422, "unknown_item": 422, "invalid_item": 422, "invalid_config": 422,
  "format_unsupported": 422, "not_a_repository": 422,
  # 502: remote / hosting
  "push_failed": 502, "fetch_failed": 502, "pull_failed": 502,
  "gh_failed": 502, "gh_missing": 502, "az_failed": 502, "az_missing": 502,
  "az_not_logged_in": 502, "az_timeout": 502, "az_devops_missing": 502,
  "commit_failed": 500,
}
```

Plus a rule: any code that equals a blocker code in `data["blockers"]` → 409 (covers
future blockers). Default 500. `usage_error` → 400.

### 2.5 Pull

`pull(root) -> tuple[dict, list[str]]`: `result = pull_config(root)`; data =
`result.to_json()` (`{base, remote, before, after, updated}`), warnings =
`list(result.warnings)`. Errors through the same mapping (`ConfigCommitError` codes
`no_remote`, `base_diverged`, `dirty_base`, `run_in_progress`, `fetch_failed`,
`pull_failed`, `unknown_base`, `invalid_config`).

### 2.6 The `busy` guard

```python
@contextmanager
def exclusive(state: FactoryState) -> Iterator[None]:
    if not state.lock.acquire(blocking=False):
        raise RepoError("busy", "another apply or base pull is running in this repository; try again")
    try: yield
    finally: state.lock.release()
```

Used by apply and config/pull only (not by check/plan). Acquire in the handler, around
the `run_in_threadpool` call (acquire and release happen on the event-loop thread; the
non-blocking acquire never blocks the loop). Map `RepoError("busy")` → 409 envelope
`busy` (add `"busy": 409` to `_REPO_ERROR_STATUS` in `app.py`, or handle it in the
factory error path – one place only). After a successful apply or pull, drop the check
cache of the repo (`state.checks.clear()`), since the state changed.

## 3. `web/app.py`

Handlers (async, like `settings_save`):

```python
async def factory_check(request):
    ctx = _ctx(request)
    offline = _flag(request, "offline"); fresh = _flag(request, "fresh")
    registry = getattr(request.app.state, "registry", None)
    reg_state = registry.snapshot()[0] if registry is not None else None   # multi app only
    data, ok, msg = await run_in_threadpool(factory.check_view, ctx.root, ctx.factory, ...,
                                             machine=request.app.state.check_machine, ...)
    -> JSONResponse(envelope_ok(data) | envelope_fail("checks_failed", msg, data=data), 200)

async def factory_plan(request): body=_json_body; req=parse; run_in_threadpool(factory.plan, root, req)
async def factory_apply(request): body/parse first (400 before locking), then
    with factory.exclusive(ctx.factory): await run_in_threadpool(factory.apply, root, req)
async def config_pull(request): with factory.exclusive(...): run_in_threadpool(factory.pull, root)
```

- `_flag(request, name)`: `"1"`, `"true"`, `"yes"` (case-insensitive) → True; missing,
  `""`, `"0"`, `"false"`, `"no"` → False; anything else → `HTTPException(400, …)`.
- Failures: `JSONResponse(envelope_fail(f.code, f.message, data=f.data, issues=f.issues),
  status_code=f.status)`; usage errors via existing `_usage_error`; `RepoError` via
  `_repo_error`. Use `backlog.UsageError` from `_json_body` for a bad body.
- Root: `_repo(request)` (`ctx.root`, the main checkout). For the multi app this is the
  registered path; never from the body.
- Routes in `_repo_routes()`:
  ```python
  Route("/factory/check", factory_check, methods=["GET"]),
  Route("/factory/plan", factory_plan, methods=["POST"]),
  Route("/factory/apply", factory_apply, methods=["POST"]),
  Route("/config/pull", config_pull, methods=["POST"]),
  ```
- `_shared_state`: `app.state.check_machine = None` (the real `SystemMachine` via
  `run_check`'s default). Tests set `client.app.state.check_machine = FakeMachine(...)` so
  no CLI login probe or network call runs. (Optionally add a `check_machine` keyword to
  `create_app`/`create_multi_app`; not required.)
- Module docstring: add a "Factory tab" paragraph describing the four endpoints, the 60 s
  cache (`fresh=1`), the 200 + `checks_failed` envelope, the options per action, the
  `target` values, the 409 `plan_changed` (new plan in `data`), 409 blockers with their
  code, 502 `push_failed`, success `{commit, pushed, pr, warnings}`, 409 `busy`, and that
  apply takes no paths or file contents.

## 4. `skill/codes.py`

Next to the other dashboard API codes:

```python
("busy", "2", "dashboard API: another apply or base pull runs in this repository (HTTP 409)"),
```

Check `tests/test_skill.py` still passes (codes registry complete; any skill-render test
that lists codes).

## 5. Tests: `aifactory/tests/web/test_web_factory.py`

No model, no network: bare remotes are local directories, the provider is `local`
(the PR is created by `LocalProvider.create_pr`, no `gh`), the check uses `FakeMachine`
with `offline=1`.

Fixtures (copy the patterns of `tests/library/test_library_install_commit.py` and
`tests/library/test_library_update.py`):

- autouse `home` fixture: `HAIFA_HOME=tmp/haifa-home`, `HAIFA_LIBRARY` unset, git identity
  env (`GIT_AUTHOR_*`, `GIT_COMMITTER_*`, `GIT_CONFIG_*` gpgsign false), stub `claude`
  via `CLAUDE_CODE_PATH`, `CODEX_PATH`/`PI_PATH` pointing to nothing.
- `make_repo(tmp_path, name)`: repo on `main` with `README.md` + `justfile`, a bare
  `"{name}-origin.git"`, push, `remote set-head origin main`. Put the trace DB outside the
  repo where a run is claimed (`.factory/local.yaml` `trace_db: tmp/<name>-trace.db`)
  only in tests that need it (local.yaml is not committed).
- Two repos `a`, `b`; multi client: `multi_client(tmp_path / "dash-home", tmp_path)` from
  `multi_repo.py`; register both with `POST /api/repos {path}` (201); ids from the response
  (`data.repo.id` or whatever `repos_add` returns – read `test_web_repos.py`).
  Set `client.app.state.check_machine = FakeMachine()` (import from
  `tests/check/factory_check_repo.py` via `sys.path.insert` like the install test does).
- Helpers `_get/_post` that assert `envelope_problems(body) == []` and the status.
- `pre_receive_reject_main(bare)`: hook script
  `#!/bin/sh\nwhile read old new ref; do [ "$ref" = refs/heads/main ] && exit 1; done\nexit 0\n`,
  `chmod 0o755`.

Tests (one function each, names indicative):

1. `test_install_builder_on_other_harness` – `plan {action: init, options: {bind:
   {builder: {harness: codex, model: gpt-5.5}}}}` on repo a → 200, `digest`, `detected`,
   `available`, `bindings.builder.harness == "codex"`, blockers `[]`, warning
   `harness_missing`. `apply` with that digest → 200, `commit`, `pushed: true`, `pr: null`;
   bare `main` == commit; `agents.yaml` in the commit has builder on codex, the others on
   claude. Repo b unchanged (its `main` sha and working tree same as before) → isolation.
2. `test_rejected_push_then_pr_with_same_digest` – hook rejects `main`; plan init → digest;
   apply target `base` → 502 `push_failed`, `data.files` present, local `main` and bare
   `main` unchanged, no `.factory/` in the checkout; apply target `pr` with the **same**
   digest → 200, `pr.branch == "factory-init/1"`, `pushed: true`, bare has
   `factory-init/1` == `commit`, local `main` unchanged.
3. `test_plan_changed` – plan init → digest; commit+push an unrelated change to `main`;
   apply with the old digest → 409 `plan_changed`, `data.digest` is new and != old, nothing
   committed; apply with the new digest → 200.
4. `test_busy` – monkeypatch `aifactory.web.factory`'s core call (e.g. patch
   `aifactory.config.commit.commit_config` or a module-level hook in `factory.py`) to wait
   on a `threading.Event` after setting a "started" event; send apply for repo a in a
   `threading.Thread`; wait for "started"; then `POST apply` and `POST config/pull` on repo
   a → 409 `busy`; `POST config/pull` on repo b → not `busy` (200 or its own code) →
   isolation; release the event, join, first request 200. Alternative if threads with
   `TestClient` are awkward: acquire `ctx.factory.lock` of repo a directly (single-repo
   `create_app` exposes its context; for the multi app reach it via
   `client.app.state.repos`) and assert both endpoints answer 409 `busy` while b does not.
   Prefer the thread variant; it exercises the real path.
5. `test_run_in_progress` – install repo a (apply init), add a config change in
   `.factory/` (e.g. edit `config.yaml`), set `local.yaml` trace_db outside the repo,
   claim a running run with the current pid (`TaskRunStore.claim(TaskRunRow(... state=
   RUNNING, pid=os.getpid()))` as `_claim` in `tests/config/test_config_publish.py`).
   Plan `config_commit` shows blocker `run_in_progress`; apply → 409 `run_in_progress`;
   `config/pull` → 409 `run_in_progress` when the remote is ahead (or skip that half).
6. `test_update_with_take_and_migrate` – library with a bare remote
   (`store.init_library("team", remote=...)` before installing), install repo a through the
   API (plan+apply init). (a) take: change `.factory/prompts/builder/system.md` in the repo,
   commit+push; advance the library (`agents/builder/system.md`, commit, push in
   `store.library_root()`); plan `update` → conflict for `agent/builder:system.md`; plan
   with `options.take: ["agent/builder:system.md"]` → status `taken`; apply with that
   digest → 200, committed and pushed, file == library text. (b) migrate: append
   `levels: [module, step, task]` to `.factory/config.yaml`, commit+push; plan update →
   `update.migrations[0].id == "m001"`, not applied; plan with `migrate: ["m001"]` →
   applied; apply → config.yaml has `levels: [project, step, task]` in base.
   `options.migrate: ["m999"]` → 422 `invalid_value`.
7. `test_config_commit` – after install, edit `.factory/config.yaml` in the working tree;
   plan `config_commit` → `files` lists it, `digest`; apply with `message: "tune config"`
   → 200, bare `main` subject `tune config`, `git status --porcelain` clean.
8. `test_config_pull` – push a commit to repo a's bare from a second clone; `POST
   /config/pull` → 200, `updated: true`, local `main` == remote; again → `updated: false`.
   No remote → 409 `no_remote` (use repo without remote or skip).
9. `test_check_cache_and_trace_db_shared` – `GET factory/check?offline=1` → 200, envelope
   with `data.state`, `data.findings`, `cached: false`; again → `cached: true`, same
   `checked_at`; `fresh=1` → `cached: false`; monkeypatch `aifactory.web.factory._clock`
   to +61 s → `cached: false`. Then write repo b's `.factory/local.yaml` with `trace_db`
   pointing at repo a's trace DB path (`repos.trace_db_of(a)`) → check of b contains a
   finding `{code: trace_db_shared, severity: error, scope: machine}` and the envelope is
   `ok: false`, `error.code == "checks_failed"` (status 200); repo a's cached check still
   answers from cache unless `fresh=1` (then it also has the finding) – assert at least b.
10. `test_validation` – unknown top-level key (`files`, `path`) on apply → 400
    `usage_error`; unknown action → 400; missing digest → 400; unknown option key for
    `update` → 400; bad `bind` harness → 422 `invalid_value`; `azure` with
    `provider: github` → 422 `conflicting_options`.
11. `test_single_repo_app` – `create_app(repo)` + `TestClient(app, base_url=BASE)`: `GET
    /api/factory/check?offline=1` (set `app.state.check_machine`), `POST
    /api/factory/plan {action: init}` → 200 with digest, `POST /api/config/pull` on a
    repo without remote → 409 `no_remote`; no `trace_db_shared` finding (no registry).

Keep the whole file fast: one install per test at most; reuse helpers; no `sleep` beyond
thread joins with a timeout. Mark nothing `slow` unless the file takes > a few seconds
(check `tests/tiers.py` conventions; web tests belong to the fast layer).

## Verification

```bash
cd aifactory && uv run pytest tests/web/test_web_factory.py -q
cd aifactory && uv run pytest tests/test_skill.py tests/web -q
just typecheck
just lint
just test          # full suite incl. frontend checks
```

All must exit 0. Also confirm `git diff --stat` touches only `aifactory/…` (and the spec /
app_docs files).

## Notes and pitfalls

- `commit_init` takes `path`; pass `ctx.root`. `commit_config`/`pull_config` take the repo
  and resolve the main checkout themselves.
- The digest is target-independent (`plan_digest` docstring), which is what makes "push
  rejected → PR with the same digest" work.
- `update` plans for `commit=True` read the **tree of base**, not the working tree; tests
  must commit+push repo changes before planning.
- `init` with no library uses the seed; with a library in `$HAIFA_HOME` it uses the
  library (test 6 needs the library to exist **before** the install).
- `factory init` derives `provider` from the remote URL; a local bare path gives `local`,
  so PRs go through `LocalProvider` (no `gh`).
- Keep `FactoryState` lock non-blocking; never hold it across an `await` other than the
  threadpool call of the same request.
- Don't change `RepoContext` positional order (`RepoContext(None, root, LiveHub(...))` is
  used in `create_app` and possibly tests); add the new field with a default at the end.
