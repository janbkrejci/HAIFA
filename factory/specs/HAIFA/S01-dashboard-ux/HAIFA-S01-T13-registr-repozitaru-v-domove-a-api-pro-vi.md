# Plan HAIFA-S01-T13: Registr repozitářů v domově a API pro více repozitářů (M3)

Design source: `docs/design/multi-repo-dashboard.md` (AR1, AR2, AR4, AR6, E1–E5, E9, E10, S2, S4, V2, V5).
D22: the dashboard port lives in the registry. `factory obs` and the frontend do not change
(M11 switches them). `create_app(repo)` stays and keeps serving one repo under `/api/`.

## 0. What exists today (read before coding)

- `aifactory/src/aifactory/home.py`: `haifa_home(environ)`, `logs_dir()` (mkdir + chmod 0700), `create_private`.
- `aifactory/src/aifactory/onboard/state.py`: `repo_state(root, base=None) -> RepoState`, with `.state`
  (`onboarded|pre_library|sssf|working_tree|none`), `.action`, `.onboarding`, `.to_json()`. It only
  runs `rev-parse`, `ls-tree` and `cat-file` through `aifactory.config.source.git` (`GIT_OPTIONAL_LOCKS=0`),
  and `worktree_base(root)` reads `config.yaml` from disk.
- `aifactory/src/aifactory/config/source.py`: `git(root, *args)` (raises `GitError`), `git_try(root, *args) -> str | None`.
- `aifactory/src/aifactory/config/settings.py`: `LocalSettings(port=4700, trace_db)`, `load_local(root)`,
  `LocalSettings.trace_db_path(root)`.
- `aifactory/src/aifactory/web/settings.py:269` `_write_atomic`: mkstemp in the same dir, write, `os.replace`.
- `aifactory/src/aifactory/library/store.py:107` `write_lock`: the flock pattern to copy.
- `aifactory/src/aifactory/web/app.py`: about 50 handlers read `request.app.state.repo` (and `live`, `launcher`,
  `limits`, `code`, `restart`). `create_app` builds `Mount("/api", routes=[...])` and sets `app.state.*`.
- `aifactory/src/aifactory/web/live.py`: `LiveHub(repo, interval)` with `subscribe`, `unsubscribe` and `aclose()`.
- `aifactory/src/aifactory/web/guard.py`: `WriteGuardMiddleware` (all `/api/` writes) and `StaleCodeMiddleware`.
  `StaleCodeMiddleware` exempts only `RESTART_PATH = "/api/restart"`.
- `aifactory/src/aifactory/skill/codes.py`: `_CODES`, with a "Dashboard" section. `tests/test_skill.py::test_error_codes_complete`
  scans calls of `ERROR_CLASSES` names for literal codes.
- Launcher (`web/launcher.py`) and `LimitsSource.get(repo)` already take the repo as an argument,
  so all repos can share them.

## 1. `config/settings.py` (small)

- Add `DEFAULT_PORT = 4700` and use it as the default of `LocalSettings.port`. Behaviour stays the same.
- Do not touch `LOCAL_KEYS` or the `port` key. `factory obs` still reads it (out of scope).

## 2. New module `aifactory/src/aifactory/web/registry.py` — the registry (AR1)

Module docstring: the file format, the locking and reload rules, the id rules, and that only the dashboard reads it.

Constants: `REGISTRY_FILE = "dashboard.yaml"`, `LOCK_FILE = "dashboard.lock"`, `REGISTRY_VERSION = 1`,
`ID_RE = re.compile(r"^[a-z0-9-]{1,32}$")`, `RESERVED_IDS = frozenset({"inspect"})`, `MAX_ID = 32`.

```python
class RepoError(Exception):           # also used by repos.py
    def __init__(self, code: str, message: str, *, data: dict[str, Any] | None = None) -> None: ...
    # .code .message .data

@dataclass(frozen=True)
class RepoEntry:  id: str; name: str; path: str; added_at: str      # to_json()

@dataclass(frozen=True)
class RegistryState: version: int; port: int; repos: tuple[RepoEntry, ...]
    def by_id(self, repo_id) -> RepoEntry | None
```

Functions and classes:

- `registry_path(home) -> Path`, `ensure_home(home) -> Path` (mkdir parents and `chmod 0o700` when created; copy `logs_dir`).
- `slugify(name) -> str`: lowercase; every run of characters outside `[a-z0-9]` becomes `-`; strip `-`;
  cut to 32 and strip `-` again; an empty result becomes `repo`.
- `unique_id(base, taken) -> str`: `taken` includes `RESERVED_IDS`. If `base` is free, return it.
  Otherwise try `-2`, `-3`, … with `base[: 32 - len(suffix)].rstrip("-") + suffix`.
- `parse_registry(text, label) -> tuple[RegistryState, dict]`: returns the validated state and the raw mapping.
  Raise `RepoError("registry_invalid", ...)` for invalid YAML, a non-mapping, `version` not an int,
  `port` not an int in 1..65535 (`bool` rejected), `repos` not a list, an entry that is not a mapping,
  an `id` that fails `ID_RE`, duplicate ids, a non-string or non-absolute `path`, or a missing `name`/`added_at`.
  Empty or missing file: `version 1`, `port DEFAULT_PORT`, `repos []`.
- `class Registry(home: Path)`:
  - `snapshot() -> tuple[RegistryState, list[str]]`: stat the file as `(st_mtime_ns, st_size, st_ino)`.
    On an unchanged stamp, return the cached state. Otherwise re-read and parse. A parse failure keeps the
    **last valid state** (empty default if none yet) and returns a warning
    `f"{path}: {problem}; the dashboard keeps the last valid registry"`. The warning repeats on every call while
    the file stays broken. A missing file gives the default state. Thread-safe with a `threading.Lock`
    (handlers run in a threadpool).
  - `@contextmanager _locked()`: `ensure_home`, `os.open(home/LOCK_FILE, O_RDWR|O_CREAT, 0o600)`,
    `fcntl.flock(fd, LOCK_EX)`, close in `finally`.
  - `_mutate(fn)`: under `_locked()`, read the raw file and parse it. A broken file raises
    `RepoError("registry_invalid")` and is **never overwritten**. Apply `fn(raw, state)` to the raw dict so
    unknown top-level and per-entry keys stay, set `version` if missing, write atomically
    (`tempfile.mkstemp(dir=home, prefix=".dashboard.yaml.", suffix=".tmp")`, `os.fchmod(fd, 0o600)`,
    `yaml.safe_dump(sort_keys=False, allow_unicode=True)`, `os.replace`, unlink the tmp file on failure),
    then refresh the cache from the written text.
  - `add(root: Path, *, now=None) -> tuple[RepoEntry, bool]`: `root` is already the vetted real repo root
    (see §3). Inside the lock, re-check duplicates with `same_repo` against every entry. A duplicate returns
    `(existing, False)` and writes nothing. Otherwise `id = unique_id(slugify(root.name), ids)`,
    `name = root.name`, `path = str(root)`, `added_at = datetime.now(UTC).isoformat(timespec="seconds")`,
    then append.
  - `remove(repo_id) -> RepoEntry | None`: drop the entry and keep everything else. An unknown id writes nothing.
  - `set_port(port: int) -> RegistryState`.
- `same_repo(a: Path, b: Path) -> bool`: `os.path.realpath` equal, or both exist and
  `(st_dev, st_ino)` are equal (macOS case-insensitive paths, symlinks).

Ids never change: `add` never renames, and nothing else edits ids.

## 3. New module `aifactory/src/aifactory/web/repos.py` — inspect, status, contexts

### 3a. Read-only git layout (put the helpers in `run/gitops.py`, as the task's "Where" names it)

Add to `run/gitops.py` a `read_git(path, *args) -> str | None` that runs git with
`env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}` (or reuse `aifactory.config.source.git_try`; either is fine,
as long as these are the only subcommands). Add a `RepoLayout` dataclass and
`repo_layout(path) -> RepoLayout | None`:

1. `git rev-parse --path-format=absolute --is-bare-repository --is-inside-git-dir --git-dir --git-common-dir`
   in `path` (this works in bare repos too). `None` means not git.
2. If not bare and not inside the git dir: `git rev-parse --show-toplevel`.

`RepoLayout(bare: bool, inside_git_dir: bool, git_dir: Path, common_dir: Path, toplevel: Path | None)`.
`linked = git_dir.resolve() != common_dir.resolve()`. For a linked worktree the main checkout is
`common_dir.parent` when `common_dir.name == ".git"`, else `None`.

**In an unregistered repo, only these git subcommands may run:** `rev-parse`, `cat-file`, `ls-tree`,
`for-each-ref`, `remote get-url`. No `status`, `diff`, `ls-files`, `config`, `init`, `symbolic-ref`.

### 3b. `vet_path(raw: object, registry_state) -> Vetted` (shared by inspect and add, S4)

Steps in order. Each failure is a `RepoError(code, message, data=...)`:

| step | code | HTTP |
|---|---|---|
| body `path` missing, not a str, or empty | `usage_error` (raise `backlog.UsageError` or return 400 directly) | 400 |
| `Path(raw).expanduser()` is not absolute | `usage_error` | 400 |
| does not exist | `path_not_found` | 404 |
| not a directory | `not_a_directory` | 422 |
| resolved path contains the parts `.factory`, `worktrees` in sequence | `run_worktree` | 422 |
| `repo_layout` is None, or `inside_git_dir` | `not_git` (message: HAIFA does not run `git init`) | 422 |
| `bare` | `bare_repo` | 422 |
| linked worktree | `linked_worktree`, `data={"main_checkout": str or None}` | 422 |
| `git rev-parse --verify --quiet HEAD^{commit}` fails at the toplevel | `no_commits` | 422 |
| trace DB equals that of another registered repo (not the same repo) | `trace_db_shared`, `data={"repo": other_id}` | 409 |

Also check the run worktree **after** taking the toplevel, in case a subfolder was given.

`root = layout.toplevel.resolve()`, and `subdir = path.relative_to(root)` when it differs (else `None`).

Trace DB: `trace_db_of(root)` is `load_local(root).trace_db_path(root)` (it reads `.factory/local.yaml`
from disk only). On `ConfigError`/`OSError`, use `(root / ".factory/trace.db").resolve()`. Two trace DBs
are "the same" when their realpaths are equal, or when both exist and `os.path.samefile` holds.
Skip registered entries whose folder is missing.

`registered` is the id of an entry where `same_repo(entry.path, root)`.

### 3c. `inspect_repo(raw_path, registry_state) -> dict` (E5, reads only)

Rejections in the table above return **ok** with `problem` filled. Only `usage_error` fails, so the
frontend can render the card. Data:

```
{ "path": <expanded input>, "root": str|None, "subdir": str|None,
  "registered": id|None, "addable": bool,
  "problem": {"code", "message", **data} | None,
  "branch": str|None,              # rev-parse --abbrev-ref HEAD (None on failure / "HEAD" -> detached: keep "HEAD")
  "remote": {"name": "origin", "url": str} | None,   # git remote get-url origin
  "trace_db": str|None,
  "factory": {state, action, sssf_leftover, alternate_rosters, rosters, base, commit,
              onboarding, library, manifest_error} | None }   # repo_state(root).to_json()
```

- `addable` is true when `problem is None` (a registered repo is addable too; adding is idempotent).
- `factory` is filled whenever a toplevel with a commit exists, even with a `trace_db_shared` problem.
- `onboarding` is the manifest's block only for `onboarded` (already so in `RepoState.to_json`).

### 3d. `repo_status(entry) -> dict` (E2 items)

`{**entry.to_json(), "status": ..., "factory": repo_state(root).to_json() | None}`:

- `missing`: `not Path(entry.path).is_dir()`.
- `not_git`: `repo_layout` is None or has no toplevel.
- `not_installed`: factory state `none` or `sssf`.
- `uncommitted`: state `working_tree`, or `settings.config_status(root)` data has `clean == False`
  (registered repo, so `git diff` with `GIT_OPTIONAL_LOCKS=0` is allowed).
- `ok`: otherwise.

Catch `ConfigError`/`GitError`/`OSError` per repo. On error, `factory = None` and the status
stays from the earlier checks (`not_git` if git is unreadable). One broken repo never fails the list.

### 3e. `RepoContext` and `RepoContexts`

```python
@dataclass
class RepoContext:  id: str | None; root: Path; live: LiveHub

class RepoContexts:
    def __init__(self, registry: Registry, live_interval: float) -> None
    async def resolve(self, repo_id: str) -> RepoContext   # raises RepoError unknown_repo / repo_missing
    async def drop(self, repo_id: str) -> None             # aclose the hub, forget the context
    async def aclose(self) -> None                         # all hubs (lifespan)
```

`resolve`:
1. `state, _ = registry.snapshot()` (cheap stat and read; plain call or `run_in_threadpool`).
2. Prune contexts whose id is gone or whose path changed, and `await ctx.live.aclose()` for each.
3. Unknown id raises `unknown_repo` (404). A folder that is not a dir raises `repo_missing` (404).
4. Create the context lazily: `LiveHub(Path(entry.path), interval=live_interval)`.

## 4. `web/app.py` — routing (AR2)

### 4a. Repo comes from the request

- Add `def _ctx(request) -> RepoContext: return request.scope[REPO_SCOPE_KEY]` and
  `def _repo(request) -> Path: return _ctx(request).root`, where `REPO_SCOPE_KEY = "haifa.repo"`.
- Replace **every** `request.app.state.repo` with `_repo(request)`, and `request.app.state.live` in `live()` with
  `_ctx(request).live`. Keep `launcher`, `limits`, `code` and `restart` on `app.state`; they are shared.
- `health` (single app) uses `_repo(request)`.

### 4b. `RepoScope` ASGI wrapper

```python
class RepoScope:
    """Put the RepoContext into scope before routing to the repo's API routes."""
    def __init__(self, app: ASGIApp, resolve: Callable[[Scope], Awaitable[RepoContext]]) -> None
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http": return await self.app(...)
        try: ctx = await self.resolve(scope)
        except RepoError as exc: return await JSONResponse(envelope_fail(exc.code, exc.message), status_code=_REPO_ERROR_STATUS[exc.code])(scope, receive, send)
        scope[REPO_SCOPE_KEY] = ctx
        await self.app(scope, receive, send)
```

- `def _repo_routes() -> list[BaseRoute]`: today's list **without** `/health`, moved out of `create_app`
  in the same order.
- Single repo: `create_app(...)` builds `ctx = RepoContext(None, repo.resolve(), LiveHub(...))` and
  `Mount("/api", app=RepoScope(Router(routes=[Route("/health", health), *_repo_routes()]), resolve=lambda s: _fixed(ctx)))`.
  Keep `app.state.repo` and `app.state.live` set (callers and tests read `app.state.launcher`). The lifespan closes `ctx.live`.
  Paths, envelopes and codes are unchanged. **The existing tests must pass without edits.**
- An inner `Router` with no matching route raises `HTTPException(404)` because `"app" in scope`, so
  `_http_error` still answers `not_found`. Verify this with an existing 404 test.

### 4c. `create_multi_app(...)` (new, exported from `web/__init__.py`)

```python
def create_multi_app(*, home: Path | None = None, port: int | None = None, static_dir=None,
                     live_interval=0.5, launcher=None, code_watch=None, restart=None,
                     limits_source=None) -> Starlette
```

- `home` defaults to `haifa_home()`. `port` is the port the server actually listens on (for `restart_required`).
- `app.state.registry = Registry(home)`, `app.state.repos = RepoContexts(registry, live_interval)`,
  `app.state.home`, `app.state.served_port`, plus shared `launcher`, `code`, `restart` and `limits` as in `create_app`.
- Routes under `Mount("/api", routes=[...])`, with globals **before** the repo mount:
  - `Route("/health", multi_health, GET)`: `{"app": "haifa-dashboard", "version": __version__, "home": str(home)}`.
  - `Route("/repos", repos_list, GET)`: `{"repos": [repo_status(e) ...], "home": str(home)}`, with registry warnings.
    Run in the threadpool.
  - `Route("/repos", repos_add, POST)`: body `{path}`. Vet, then `registry.add(root)`. Returns `{"repo": status_item, "created": bool}`:
    HTTP 201 when created, else 200. Writes nothing into the repo.
  - `Route("/repos/inspect", repos_inspect, POST)`: body `{path}`. Calls `inspect_repo` and writes nothing.
  - `Route("/repos/{repo_id}", repos_remove, DELETE)`: `registry.remove`, then `await app.state.repos.drop(id)`.
    Returns `{"removed": entry.to_json()}`, or 404 `unknown_repo`. Removes only the registry entry.
  - `Route("/dashboard/settings", dashboard_settings_get, GET)` and `POST`: data `{"port", "home", "registry": str(path),
    "restart_required": served_port is not None and port != served_port}`. POST `{port}` must be an int in 1..65535,
    else 422 `invalid_value` with `issues=[{"id": "port", "message": ...}]`. An unknown key in the body gives 400 `usage_error`.
  - `Mount("/repos/{repo_id}", app=RepoScope(Router(routes=_repo_routes()), resolve=lambda s: repos.resolve(s["path_params"]["repo_id"])))`.
    Starlette's Mount regex needs a trailing `/…`, so `POST /api/repos/inspect` and `DELETE /api/repos/x`
    never reach the mount. `inspect` is reserved, so no repo can shadow it.
- Static mount and middleware: same as `create_app`. Factor out `_build_app(routes, state_setup, lifespan_close)`
  or just duplicate the small middleware/exception block via a helper `_starlette(routes, lifespan)`.
- Lifespan: `await app.state.repos.aclose()`.
- `RepoError` handling in the global handlers: `_repo_error(exc)` maps through
  `_REPO_ERROR_STATUS = {"unknown_repo": 404, "repo_missing": 404, "path_not_found": 404, "not_a_directory": 422,
  "not_git": 422, "bare_repo": 422, "linked_worktree": 422, "run_worktree": 422, "no_commits": 422,
  "trace_db_shared": 409, "registry_invalid": 409, "invalid_value": 422}` and passes `data=exc.data` to `envelope_fail`.
- Body parsing: reuse `_json_body` (it raises `backlog.UsageError` and returns 400 `usage_error`).
- Update the module docstring with a "More repositories" paragraph listing the global endpoints and the mount.

### 4d. `web/guard.py`

`StaleCodeMiddleware` must also exempt `/api/repos/<id>/restart`: add
`is_restart_path(path)`, which matches `path == "/api/restart" or re.fullmatch(r"/api/repos/[^/]+/restart", path)`.
`WriteGuardMiddleware` already covers every new write (prefix `/api/`), including `DELETE`.

### 4e. `web/live.py`

No protocol change. Make sure `LiveHub.aclose()` is safe to call twice and on a hub that was never
subscribed (it already looks safe; add a test). Update the docstring: one hub per repo in the multi-repo app.

### 4f. `web/__init__.py`

Export `create_multi_app`, `Registry`, `RepoEntry` (and `RepoError` if handy).

## 5. `skill/codes.py`

Add to the "Dashboard" section (exit `"2"`, with a short meaning each): `unknown_repo`, `repo_missing`, `path_not_found`,
`not_a_directory`, `not_git`, `bare_repo`, `linked_worktree`, `run_worktree`, `no_commits`, `trace_db_shared`,
`registry_invalid`. (`invalid_value` and `usage_error` exist already; check `not_a_repository` is unrelated and stays.)
Add `"RepoError"` to `ERROR_CLASSES` in `tests/test_skill.py`, so the completeness scan covers the new raise sites.
Always pass the code as a **literal first argument** of `RepoError(...)`.
If a skill doc test lists codes, `test_skill_lists_error_codes` should pass automatically.

If `ISSUE_CODES` should list the E2 statuses, add `"dashboard_repo_status": ("ok", "uncommitted", "not_installed", "missing", "not_git")`
with a comment. This is optional; only add it if no test forbids extra keys.

## 6. Tests (`aifactory/tests/web/`, no model, no network)

New helper `tests/web/multi_repo.py`: `init_repo(path, commit=True)` with `git -c user.name=… -c user.email=… -c commit.gpgsign=false`
and `-b main`, `write(root, rel, text)`, `commit_all(root)`, and `multi_client(home, tmp_path, **kw) -> TestClient`
(`create_multi_app(home=home, static_dir=tmp_path/"nostatic")`, base_url `http://127.0.0.1:4700`).
Web tests cannot import `tests/onboard/onboard_repo.py` (another dir), so copy the few lines.
conftest already gives every test its own `HAIFA_HOME`; still pass `home=` explicitly.

`tests/web/test_web_registry.py` (unit tests of `registry.py`):
- the file is 0600, the home dir is 0700 (create it fresh under `tmp_path/"h"`), and the content has `version`, `port`, `repos[...]` with all four keys.
- **concurrent writes of two processes**: two `subprocess.Popen([sys.executable, "-c", SCRIPT], env={…, "HAIFA_HOME": home})`
  each add 10 distinct repo paths (plain dirs are fine for `Registry.add`, which does not vet). After both exit 0,
  all 20 entries are present with unique ids and the YAML parses.
- **duplicate through a symlink**: `add(real)`, then `add(symlink→real)` (and the `same_repo` inode path) returns `created False` and one entry.
- **id collision**: two repos `a/web` and `b/web` give `web` and `web-2`, and a third gives `web-3`. A folder named `inspect` gives `inspect-2`.
  A long or odd name (`"Můj Repo!!" * 5`) gives a `[a-z0-9-]{1,32}` slug. Ids do not change after removing `web` and adding another `web` (it gets a free id, while `web-2` keeps its id).
- **unknown keys kept**: write a file with `extra: {a: 1}` and an entry with `color: red`. After `add` and `set_port` both stay.
- **corrupt file**: snapshot a valid state, overwrite with `"repos: [\n"`. `snapshot()` returns the last valid state plus a warning.
  `add` raises `registry_invalid` and the file bytes are unchanged. A fresh `Registry` on a corrupt file gives the empty default plus a warning.
- **reload on change**: an external write (new size/mtime) is seen by the next `snapshot()`.

`tests/web/test_web_repos.py` (the API through `TestClient` on `create_multi_app`):
- `GET /api/health` returns `app == "haifa-dashboard"`, `version`, `home`.
- `GET /api/dashboard/settings` gives the default 4700 with `restart_required False` (with `port=4700` passed). `POST {port: 4801}` returns 200,
  `restart_required True`, and the file has `port: 4801`. `POST {port: 0}`, `{port: "x"}` and `{port: true}` give 422 `invalid_value`.
- **inspect** (each returns ok with the `problem.code` or the state, and the registry file stays untouched, i.e. absent):
  folder without git → `not_git`, and no `.git` was created. Subfolder → `root` is the toplevel, `subdir` set, `addable`.
  Linked worktree (`git worktree add`) → `linked_worktree` with `main_checkout`.
  Run worktree (`<repo>/.factory/worktrees/x` made with `git worktree add`) → `run_worktree`.
  Bare repo (`git init --bare`) → `bare_repo`. Repo without a commit → `no_commits`. Missing path → 404 `path_not_found`.
  A file → `not_a_directory`. A relative path → 400 `usage_error`. `~` is expanded (monkeypatch `HOME` and the env of `Path.expanduser`).
  Factory states: commit `adws/adw_sssf_config/sssf.config.yaml` → `factory.state == "sssf"`, `action == "onboard"`.
  Commit `.factory/config.yaml` (`base: main\n`) → `pre_library`.
  Commit config, agents and a manifest built like `tests/onboard/test_repo_state.py::_onboarded` (`dump_manifest(Manifest(...))`) → `onboarded`, `action == "adopt"`, `onboarding.by` present.
  **Shared trace DB**: register repo A, then repo B with `.factory/local.yaml` `trace_db: <A>/.factory/trace.db` → inspect `problem.code == "trace_db_shared"`, and POST add returns 409 `trace_db_shared`.
- **Inspect runs only allowed git commands**: monkeypatch `subprocess.run` (and `Popen` if used) in the modules involved with a spy that records
  the git subcommand (the first argv item after `git` that is not an option or `-c` pair) and calls through. Assert the set ⊆
  `{"rev-parse", "cat-file", "ls-tree", "for-each-ref", "remote"}`, and that `remote` is only followed by `get-url`.
- **add**: `POST /api/repos {path: subdir}` returns 201 `created True` and registers the root. Repeated → 200 `created False`, same id.
  Symlink path → same id. `git status --porcelain` and `.factory/` of the repo are unchanged (nothing written into the repo).
  Rejections give the codes above with no registry change.
- **list**: statuses `ok` (onboarded/pre_library committed, clean), `uncommitted` (`.factory/config.yaml` only in the working tree,
  or a committed config modified on disk), `not_installed` (plain repo, and the sssf repo), `missing` (registered then `rmtree`),
  `not_git` (registered then `.git` removed). `factory.state` is present for the git ones.
- **delete**: `DELETE /api/repos/{id}` returns `{removed}` and the repo dir is untouched. Again → 404 `unknown_repo`. After a delete, `GET /api/repos/{id}/backlog` → 404 `unknown_repo`.
- **unknown_repo / repo_missing** on `GET /api/repos/nope/runs` and on a registered repo whose folder was removed.
  An unknown sub-path of a known repo → 404 `not_found`. `/api/repos/{id}/health` → 404 `not_found`.
- **isolation of two repos**: use the backlog fixture style of `tests/web/backlog_fixture.py` / `trace_fixture.py`
  (read them; reuse their builders if they take a root path). Repo A has a task and a trace run, and repo B has different ones.
  `GET /api/repos/a/backlog` contains only A's task, `.../b/backlog` only B's. `GET .../runs` likewise.
  `POST /api/repos/a/settings {shared: {...}}` changes only A's `.factory/config.yaml`. A backlog write through `/api/repos/b/backlog/tasks` lands only in B.
  The launcher is a stub/thread double (see `tests/web/thread_launcher.py`) if a run is needed. Do not start real runs.
- **live isolation** (`@pytest.mark.xdist_group("live")`, uvicorn on a free port like `test_web_live.py::test_sse_stream_reports_file_change`):
  subscribe to `/api/repos/a/live`, wait for `hello`, append to a file under B's `backlog/` → no `files` event within ~1 s.
  Append under A's `backlog/` → a `files` event naming A's path. Then `DELETE /api/repos/a` → the stream ends (the hub is closed).
- **write guard (M1) on new endpoints**: for `POST /api/repos`, `POST /api/repos/inspect`, `DELETE /api/repos/{id}`,
  `POST /api/dashboard/settings` and `POST /api/repos/{id}/backlog/tasks`, test `Origin: http://evil.example` → 403 `cross_origin`,
  `Sec-Fetch-Site: cross-site` → 403, `Content-Type: text/plain` with a body → 415 `unsupported_media_type`, and the registry and repo are unchanged.
  Also: with a stale `CodeWatch` double, `POST /api/repos` → 409 `stale_code`, while `POST /api/repos/{id}/restart` is not blocked
  (inject `restart=lambda: None`).
- `create_app` back-compat: no edits to existing tests. Run the whole `tests/web/`.

Add `tests/web/test_web_live_multi.py`, or put the live test in `test_web_repos.py` with the xdist group. Do **not** add any new file to `SLOW_FILES` unless it is slow (>5 s).

## 7. Verify

```bash
just test            # whole suite (core changes: run all)
just typecheck
just lint            # ruff check + ruff format --check (run `cd aifactory && uv run ruff format .` first)
```

Also run `cd aifactory && uv run pytest tests/web tests/test_skill.py -n0 -q` while iterating.

## 8. Constraints and pitfalls

- Never write into a repo on inspect, add or remove. Never `git init`. No `git status` or `diff` in unregistered repos.
- Do not change `cli.py` `_obs`, the frontend (`aifactory/web/`) or `web/static/`.
- Do not edit `vendor/`, `prototype/`, `.factory/`, `docs/product-brief.md`.
- mypy is strict: annotate `RepoScope` with `starlette.types` (`ASGIApp`, `Scope`, `Receive`, `Send`).
  The `resolve` callable is `Callable[[Scope], Awaitable[RepoContext]]`.
- `fcntl` is POSIX only, as in `library/store.py`. That is fine.
- Keep handler logic thin. The core logic goes in `registry.py` and `repos.py`, so the unit tests do not need HTTP.
