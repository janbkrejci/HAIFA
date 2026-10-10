# Plán 1.5: `haifa-proto task run` — běh tasku ve worktree, omezení zápisů na task, `task_runs`

## Zadání (shrnutí)

`haifa-proto task run <task-id> [--note TEXT] [--force]` spustí task z backlogu ve vlastním git worktree a větvi (kroky 1–3 sekce „Běh úkolu“ v `docs/product-brief.md`). Plus `haifa-proto task show <task-id> [--json]`.

Mimo rozsah: push/PR (1.6), auto-continue (1.7), web. **Nikdy** nezapisovat `status: done` do souboru tasku. **Neupravovat `vendor/`.** Testy nevolají model.

## Co už existuje (nezkoumej znovu)

- `prototype/src/haifa_proto/config.py` — `FactoryConfig(levels, backlog_dir)`, `load_config(repo_root)` z `.factory/config.yaml`.
- `prototype/src/haifa_proto/backlog.py` — `load_backlog(root, config)`, `Task` (`id,title,status,path,parent,own,depends_on,related,writes,body`), `Container` (`id,title,level,defaults,extra,parent`), `ancestors()`, `effective(task)` (dědí `owner, source, target, test, workflow, auto_continue`; **`writes` se nedědí** — u kontejneru skončí v `container.extra["writes"]`), `unmet(backlog, task)`, `derived_state`.
- `prototype/src/haifa_proto/workflow.py` — `load_workflow(path, roles)`, `preflight(workflow, cfg)`, `run_workflow(workflow, prompt, cfg, *, code=None, adw_id=None) -> WorkflowRun(exit_code, accepted, adw_id, ...)`, `EngineCodeRunner`, `DEFAULT_WORKFLOWS_DIR`. Chyby fází se propagují jako výjimky.
- `prototype/src/haifa_proto/roles.py` — `load_roles(path=None)` (výchozí `defaults/roles.yaml`).
- `prototype/src/haifa_proto/engine.py` — `load_engine_module("permissions" | "agents" | "utils" | ...)`.
- Engine (jen ke čtení, `vendor/sssf/templates/adws/adw_modules/`):
  - `Run.repo_root = git_helper.repo_root()` = `git rev-parse --show-toplevel` **z cwd procesu**. `git_helper.commit_all`, gates (`Path(f).exists()`) a harness (`cwd=run.repo_root`) — vše závisí na cwd. ⇒ stačí `os.chdir(worktree)` po dobu běhu.
  - `session.ensure(cfg, adw_id)`: tracer na `cfg.observability.db` a `cfg.defaults.data_dir/sessions/<adw_id>/…` — relativní cesty se berou vůči cwd. ⇒ před chdir je převést na **absolutní cesty do hlavního checkoutu**.
  - `agents.execute` volá `permissions.snapshot(run)` a `permissions.enforce(run, phase, agent, before)` přes atribut modulu; `enforce` volá `permitted(path, agent, cfg)` přes globální jméno modulu. ⇒ task scope jde doplnit dočasnou náhradou `permissions.permitted` (a obalením `permissions.enforce` kvůli zprávě) v kontextovém manažeru, bez úpravy vendoru. `enforce` sám vrací porušení (`_roll_back`: untracked smaže, tracked `git checkout --`) a vyhodí `PermissionBreach` → fáze selže.
  - `permissions._matches(path, pattern)`: `dir/` = prefix, `*` nepřekročí `/`, `**` ano, jinak přesná shoda.
- Testy: `tests/workflow_fakes.py` (`make_engine_env`, `FakeHarness`, `Script`, `FakeCodeRunner`, `ok()`), fixture `engine_env` v `tests/conftest.py`. Agenti ve fake configu mají `writes` neuvedené (= neomezeno), `data_dir` a `db` jsou mimo repo v `tmp_path/data`.
- `tests/test_cli.py::test_subcommands_are_noops` volá `main(["task"])` a čeká `0` → `task` bez podpříkazu musí vytisknout help a vrátit 0.

## Návrhová rozhodnutí

1. **run-id = adw_id** (`utils.new_id(8)` z enginu). Session v trace i worktree mají stejné id: `.factory/worktrees/<run-id>`.
2. **Větev** `factory/<task-id>-<n>`: `n` = 1 + max ze stávajících `n` přes `git for-each-ref --format=%(refname:short) refs/heads/factory/<task-id>-*` i přes `branch` v `task_runs` pro task (bere se víc). Neparsovatelné sufixy ignorovat.
3. **„Hotové v base“** se kontroluje na obsahu commitu `base`, ne na pracovním stromu: `git archive --format=tar <base_sha> -- <backlog_dir> [.factory/workflows] [.factory/roles.yaml]` (každou cestu přidej jen když `git cat-file -e <base_sha>:<cesta>` uspěje) → rozbalit (`tarfile`, `filter="data"` pokud je k dispozici) do `tempfile.TemporaryDirectory()` → `load_backlog(tmp, config)`. Z téhle kopie se bere i task (hlavička, text, writes, workflow), workflow YAML a roles. Task, který v base není (jen v pracovním stromu), je chyba `task_not_in_base` („commitni ho do base“). Neexistující vůbec → `unknown_task`.
4. **Konfigurace** (`.factory/config.yaml`, hlavní checkout) — nové klíče ve `FactoryConfig`:
   - `base: str = "main"` (neprázdný řetězec),
   - `worktrees_dir: str = ".factory/worktrees"` (relativní cesta),
   - `agents_config: str = "adws/adw_sssf_config/sssf.config.yaml"` (relativní; sssf config s agenty, `data_dir`, `observability.db`),
   - `specs_dir: str = "specs"`, `docs_dir: str = "app_docs"` (relativní; viz bod 6).
   Validace relativních cest: zobecni `_parse_backlog_dir` na `_parse_rel_path(key, value, where)`; chybové hlášky zmiňují jméno klíče.
5. **sssf cfg**: `run_task` přijme volitelné `cfg` (testy). Jinak `agents.load_config(str(main_root / config.agents_config))` (po `ensure_harnesses()` z `workflow.py`, aby se rozšířil `coding_agent`). Vždy `cfg = cfg.model_copy(deep=True)` a pak `cfg.defaults.data_dir` a `cfg.observability.db` převést na absolutní vůči `main_root`, pokud jsou relativní. Relativní cesty promptů (`prompt_engineering`) se pak čtou vůči cwd = worktree, tedy z verze v `base` (v souladu s briefem „běh vychází z commitu v base“). Definice agentů se čtou z hlavního checkoutu — odchylku zapiš do docstringu `run.py` (podklad pro zprávu 1.10).
6. **Task scope** (`scope.py`): povolené cesty = efektivní `writes` tasku ∪ `{specs_dir}/` ∪ `{docs_dir}/`. Důvod pro specs/docs: planner a documenter ze `simple-sdlc`/`plan-build` zapisují plán a dokumentaci do repa, jinak by každý reálný běh selhal v první fázi. Chráněné soubory a `writes` agenta dál platí (scope je průnik, ne sjednocení s omezením agenta). Session runtime (`permissions.always_writable(cfg)`) zůstává vždy povolený. Odchylku od „jen writes tasku“ uveď v docstringu `scope.py`.
   - **Efektivní `writes`**: vlastní `task.writes`, pokud je neprázdný; jinak nejbližší předek (step, pak modul…), který má v `container.extra["writes"]` (nebo `defaults`, kdyby tam byl) seznam řetězců; jinak `[]`. Hodnota předka, která není seznam řetězců → `ScopeError`.
   - Prázdné efektivní `writes` (bez extra adresářů) → start odmítnut chybou `no_writes` („task nemá writes, ani zděděné z index.md“). `--force` to nepřebije.
   - **Shoda cest** `scope.matches(path, pattern)`: vzor s `*`/`?` nebo končící `/` → `permissions._matches`; vzor bez zástupných znaků a bez `/` na konci → přesná shoda **nebo** prefix `pattern + "/"` (aby `src/api` fungovalo jako adresář). Vzory normalizuj: odstranit úvodní `./`.
7. **Běžící task**: řádek v `task_runs` se `state='running'`. Řádek má i `pid`. Když proces s tím pid neběží (`os.kill(pid, 0)` → `ProcessLookupError`), řádek se při kontrole přepíše na `aborted` s `ended_at` a nebrání startu. Kontrola + vložení nového řádku probíhá v jedné transakci `BEGIN IMMEDIATE` (dva současné starty se nepředběhnou). `--force` běžící task **nikdy** nepřebije.
8. **Hlavní checkout beze změny**: worktree leží uvnitř hlavního checkoutu, takže `git status` by ukázal `.factory/worktrees/` jako untracked. Před `git worktree add` zapiš (idempotentně) řádek `/<worktrees_dir>/` do `<git-common-dir>/info/exclude` (`git rev-parse --git-common-dir` v main_root; relativní výsledek vztáhni k main_root). Nesahá to na sledované soubory.
9. **Výsledek běhu**: `run_task` při chybě kontroly vyhodí `TaskRunError(code, message)` a nic nevytvoří. Po založení řádku se každá výjimka z workflow (včetně `PermissionBreach`, `GateFailure`, `WorkflowError` z preflightu) zachytí (`except Exception`), řádek dostane `state='failed'`, `error=str(exc)[:2000]`, `head_sha`, `ended_at` a `run_task` vrátí `TaskRunResult(state="failed", error=...)`. `BaseException` (KeyboardInterrupt, SystemExit ze signálu) → řádek `failed` a znovu vyhodit. Úspěch = `result.accepted and result.exit_code == 0` → `succeeded`, jinak `failed` s `error="accept not met"`. Worktree se při selhání **nemaže** (brief: „Selhal, worktree zůstává“).
10. **cwd**: `prev = Path.cwd()`; `os.chdir(worktree)` jen kolem `run_workflow`; v `finally` `os.chdir(prev)`.

## Soubory

### 1. `prototype/src/haifa_proto/config.py` (upravit)

- Rozšířit `FactoryConfig` o `base`, `worktrees_dir`, `agents_config`, `specs_dir`, `docs_dir` s výchozími hodnotami výše.
- `load_config` je načte a validuje (`base`: neprázdný str; ostatní: `_parse_rel_path`). Neznámé klíče se dál ignorují.

### 2. `prototype/src/haifa_proto/scope.py` (nový)

```python
class ScopeError(Exception): ...

@dataclass(frozen=True)
class TaskScope:
    task_id: str
    writes: tuple[str, ...]        # efektivní writes tasku (vlastní nebo zděděné)
    extra: tuple[str, ...]         # specs_dir/, docs_dir/
    @property
    def paths(self) -> tuple[str, ...]: ...   # writes + extra, bez duplicit, v pořadí
    def permits(self, path: str) -> bool: ...

def effective_writes(task: Task) -> list[str]
def matches(path: str, pattern: str) -> bool
def task_scope(task: Task, config: FactoryConfig) -> TaskScope

@contextmanager
def enforce_task_scope(scope: TaskScope) -> Iterator[None]:
    """Dočasně nahradí permissions.permitted a obalí permissions.enforce."""
```

`enforce_task_scope`:
- `permissions = engine.load_engine_module("permissions")`; ulož `orig_permitted`, `orig_enforce`.
- `def permitted(path, agent, cfg)`: `if any(permissions._matches(path, p) for p in permissions.always_writable(cfg)): return True`; `return orig_permitted(path, agent, cfg) and scope.permits(path)`.
- `def enforce(run, phase, agent, before)`: `try: return orig_enforce(...)` / `except permissions.PermissionBreach as e: raise permissions.PermissionBreach(f"{e}\ntask {scope.task_id} may only change {list(scope.paths)}") from e`.
- Nastav `permissions.permitted = permitted`, `permissions.enforce = enforce`; v `finally` vrať originály. (`agents.py` volá `permissions.enforce` přes atribut modulu a `enforce` volá `permitted` přes globál modulu, takže obojí zabere.)
- Hlavičku promptu dej také sem nebo do `run.py` (viz níže) — doporučeno `run.py`.

### 3. `prototype/src/haifa_proto/run.py` (nový)

Obsah:

```python
RUNNING, SUCCEEDED, FAILED, ABORTED = "running", "succeeded", "failed", "aborted"

class TaskRunError(Exception):
    def __init__(self, code: str, message: str) -> None  # code: unknown_task, task_not_in_base,
        # unmet_dependencies, already_running, no_writes, unknown_base, no_workflow,
        # unknown_workflow, invalid_workflow, invalid_config, worktree_failed

@dataclass
class TaskRunRow:  # jeden řádek task_runs
    run_id, task_id, branch, worktree, base, base_sha, head_sha: str | None, state,
    started_at, ended_at: str | None, pid: int | None, workflow: str | None,
    note: str | None, error: str | None
    def to_json(self) -> dict[str, object]

@dataclass
class TaskRunResult:
    run: TaskRunRow
    workflow_run: WorkflowRun | None
    @property
    def ok(self) -> bool  # run.state == SUCCEEDED

class TaskRunStore:
    """Tabulka task_runs v trace DB (cfg.observability.db). Vlastní sqlite spojení."""
    def __init__(self, db_path: Path) -> None   # mkdir parent, connect(isolation_level=None), CREATE TABLE/INDEX
    def claim(self, row: TaskRunRow) -> None    # BEGIN IMMEDIATE; označ mrtvé running jako aborted; když zbyl running pro task → ROLLBACK a TaskRunError("already_running", "... run <id> (pid N) since ..."); jinak INSERT; COMMIT
    def running(self, task_id: str) -> TaskRunRow | None  # po vyčištění mrtvých
    def finish(self, run_id: str, state: str, head_sha: str | None, error: str | None) -> None
    def for_task(self, task_id: str) -> list[TaskRunRow]  # nejnovější první (started_at DESC, rowid DESC)
    def branches(self, task_id: str) -> list[str]
    def close(self) -> None
```

Schéma:

```sql
CREATE TABLE IF NOT EXISTS task_runs (
  run_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  branch TEXT NOT NULL,
  worktree TEXT NOT NULL,
  base TEXT NOT NULL,
  base_sha TEXT NOT NULL,
  head_sha TEXT,
  state TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  pid INTEGER,
  workflow TEXT,
  note TEXT,
  error TEXT
);
CREATE INDEX IF NOT EXISTS task_runs_task ON task_runs(task_id);
```

Časy přes `engine.load_engine_module("utils").now_iso()`. `worktree` ukládej jako absolutní cestu.

Pomocné funkce:

- `_git(cwd: Path, *args) -> str` (subprocess, `check` → při chybě `RuntimeError` se stderr); `_git_ok(cwd, *args) -> bool`.
- `main_root(repo: Path) -> Path` = `git rev-parse --show-toplevel` v `repo`; když `repo` není git repo → `TaskRunError("invalid_config", ...)`. Pokud `repo` je sám worktree (má `.git` soubor), stačí toplevel — neřešit.
- `trace_db_path(repo: Path, config: FactoryConfig, cfg: Any | None = None) -> Path`: z `cfg.observability.db` (když `cfg` není, načti sssf config z `repo/config.agents_config`, pokud existuje, jinak default `adws/adw_data/sssf.db`), relativní vůči `repo`. Používá i `task show`.
- `load_base_backlog(root, config, base_sha, dest) -> Backlog` (git archive viz rozhodnutí 3).
- `resolve_workflow(name, base_copy: Path, roles) -> tuple[Workflow, Path]`: `name` z `effective_workflow(task)`; `None` → `no_workflow`; hledej `base_copy/.factory/workflows/<name>.yaml`, pak `DEFAULT_WORKFLOWS_DIR/<name>.yaml`; nic → `unknown_workflow`; `WorkflowError` → `invalid_workflow` se zprávou. Roles: `base_copy/.factory/roles.yaml` pokud existuje, jinak `load_roles()`.
- `next_branch(root, task_id, store) -> str`.
- `ensure_excluded(root, worktrees_dir)`.
- `task_prompt(task, scope, note) -> str` — hlavička + text + poznámka:

```
# Task <id>: <title>

- id: <id>
- title: <title>
- <level>: <id> — <title>          # jeden řádek za každého předka, od nejvyššího (module, step)
- source: <source | (not set)>
- target: <target | (not set)>
- allowed paths: <p1>, <p2>, ...   # scope.paths
- You may change only the allowed paths; any other change is reverted and fails the phase.

<task.body.strip()>

## Note
<note>                              # jen když note je neprázdný
```

  `source`/`target` z `effective(task)`. Předek bez id/title → vypiš jen, co je.

- Hlavní funkce:

```python
def run_task(repo: Path, task_id: str, *, note: str | None = None, force: bool = False,
             cfg: Any | None = None, code: CodeRunner | None = None) -> TaskRunResult
```

Pořadí kroků (nic nevytvářet, dokud neprojdou kontroly 1–8):

1. `root = main_root(repo)`; `config = load_config(root)` (`ConfigError` → `TaskRunError("invalid_config")`).
2. `base_sha = rev-parse --verify <config.base>^{commit}`; selhání → `unknown_base`.
3. `cfg` připravit (rozhodnutí 5); `store = TaskRunStore(trace_db_path(root, config, cfg))`.
4. V `TemporaryDirectory`: `backlog = load_base_backlog(...)`. Task: `backlog.by_id.get(task_id)` musí být `Task`; pokud ne, zkontroluj pracovní strom (`load_backlog(root, config)`) → `task_not_in_base`, jinak `unknown_task`. (Id kontejneru → `unknown_task` se zprávou „is a <level>, not a task“.)
5. `store.running(task_id)` → `already_running` (dřív než závislosti, a i s `--force`).
6. `if not force and (u := unmet(backlog, task))` → `unmet_dependencies` se seznamem `id (reason: missing…)`.
7. `scope = task_scope(task, config)`; `if not scope.writes` → `no_writes`.
8. `workflow = resolve_workflow(...)`; `preflight(workflow, cfg)` (`WorkflowError` → `invalid_workflow`). Prompt `task_prompt(...)` sestav teď (tempdir pak zmizí).
9. `run_id = utils.new_id(8)`; `branch = next_branch(...)`; `worktree = (root / config.worktrees_dir / run_id).resolve()`.
10. `store.claim(TaskRunRow(..., state=RUNNING, pid=os.getpid(), started_at=now, workflow=workflow.name, note=note))` (tady může ještě padnout `already_running` z race).
11. `ensure_excluded(...)`; `git worktree add -b <branch> <worktree> <base_sha>` v `root`; chyba → `store.finish(run_id, FAILED, None, err)` a `TaskRunError("worktree_failed")`.
12. `prev = Path.cwd()`; `try: os.chdir(worktree); with enforce_task_scope(scope): wf = run_workflow(workflow, prompt, cfg, code=code, adw_id=run_id)` — výjimky podle rozhodnutí 9; `finally: os.chdir(prev)`.
13. `head_sha = git -C worktree rev-parse HEAD`; `store.finish(...)`; `store.close()`; vrátit `TaskRunResult`.

- `task_runs_for(repo, task_id) -> list[TaskRunRow]` pro `task show` (otevře store, vyčistí mrtvé running, vrátí řádky).

Soubor tasku se nikdy nezapisuje. Žádný push.

### 4. `prototype/src/haifa_proto/cli.py` (upravit)

- Nahradit stub `task` subparserem se `set_defaults(task_parser=task)` a podpříkazy:
  - `run <task_id> [--note TEXT] [--force] [--repo PATH] [--json]`
  - `show <task_id> [--repo PATH] [--json]`
- `main`: `task` bez podpříkazu → help, `0` (zachovat `test_subcommands_are_noops`).
- `_task_run(repo, task_id, note, force, as_json)`: import `run` líně (jako harness/workflow). `TaskRunError` → JSON `{"ok": false, "error": {"code", "message"}}` nebo `error: <code>: <message>` na stderr, exit 1. Úspěch/neúspěch běhu → JSON `{"ok": result.ok, "run": row.to_json()}`; text: `run <run_id> <state>: branch <branch>, worktree <path>` (+ `error: …` při selhání). Exit `0` jen při `succeeded`, jinak `1`.
- `_task_show(repo, task_id, as_json)`: task z pracovního stromu (`load_backlog`) + běhy z `task_runs_for`. Když task v backlogu není a nemá ani běhy → `unknown_task`, exit 1. JSON: `{"ok": true, "task": {"id","title","path","status","state": derived_state, "writes": effective_writes, "workflow"} | null, "runs": [row.to_json(), ...]}`. Text: hlavička tasku a pod ní řádek na běh `<started_at>  <run_id>  <state>  <branch>  <head_sha[:7]>`, nebo `no runs`. `ConfigError` → `_config_error`.

### 5. Testy (`prototype/tests/`)

**`workflow_fakes.py` (upravit, zpětně kompatibilně)**:
- `Call` dostane pole `cwd: str = ""` (plní se z `request.cwd`).
- `Script` dostane `effects: dict[str, list[Callable[[Path], None]]]` a metodu `on(agent, *effects)`. `FakeHarness.run` před vrácením envelope vyjme další effect agenta (když existuje) a zavolá ho s `Path(request.cwd)`.

**Nový helper `tests/task_repo.py`** (nebo fixture v `conftest.py`): `make_task_repo(env: EngineEnv) -> Path` nad `env.repo` (už má commit a chdir):
- `git branch -M main`;
- `.factory/config.yaml`: `levels: [module, step, task]`, `backlog_dir: backlog` (výchozí base/worktrees);
- `.factory/workflows/build-commit.yaml`: `name: build-commit`, popis, `steps: [build, commit]`, `accept: commit.committed` (commit krok potřebuje `description` podle validace — zkontroluj `load_workflow` a dopiš popisy, které nepřepakovávají jméno fáze);
- `backlog/M01-core/index.md` (`id: M01`, `title: Core`, `workflow: build-commit`, `source: src/`, `target: src/`);
- `backlog/M01-core/S01-app/index.md` (`id: M01-S01`, `title: App`, `writes: [src/app/]`);
- `M01-S01-T01-health.md` (`status: todo`, bez `writes` → dědí `src/app/`, tělo `## Zadání\nAdd a health check.`);
- `M01-S01-T02-metrics.md` (`status: todo`, `depends_on: [M01-S01-T01]`, `writes: [src/metrics/]`);
- `M01-S01-T03-readonly.md` pod stepem bez writes? → dej ho do dalšího stepu `S02-empty/index.md` bez `writes` (`id: M01-S02`), task `M01-S02-T01` bez writes → pro test `no_writes`;
- `src/app/__init__.py` prázdný; commit „fixture backlog“.
- vrací cestu k repu. `cfg` z `env.cfg` se předává do `run_task(..., cfg=env.cfg)`; `code=None` → skutečný `EngineCodeRunner` (commit v worktree přes git).

**`tests/test_task_run.py`** (nový):
1. `test_run_creates_branch_and_worktree` — builder effect zapíše `src/app/health.py`, envelope `ok(summary="built", changed_files=["src/app/health.py"], commit_message="Add health check")`. Ověř: `result.ok`; `result.run.branch == "factory/M01-S01-T01-1"`; worktree `repo/.factory/worktrees/<run_id>` existuje a v něm `health.py`; `git -C wt log -1 --format=%s` == `Add health check`; `git rev-parse main` == původní sha (== `row.base_sha`); `git branch --contains <head_sha>` obsahuje jen větev factory; hlavní checkout: `git status --porcelain` prázdný a `src/app/health.py` neexistuje; soubor tasku má stále `status: todo`; všechny `script.calls[*].cwd` == worktree; prompt každého volání začíná `# Task M01-S01-T01: …` a obsahuje `- allowed paths: src/app/, specs/, app_docs/`, `step: M01-S01`, `source: src/`, text tasku; `Path.cwd()` po běhu == repo; `task_runs` (přes `TaskRunStore(...).for_task`) má jeden řádek `succeeded` s `head_sha`, `base_sha`, `worktree`, `branch`, `started_at`, `ended_at`; trace DB (`sessions`) má session s `adw_id == run_id`, soubor DB leží mimo worktree.
2. `test_note_is_appended_to_prompt` — `note="use port 8081"` → prompt obsahuje `## Note\nuse port 8081` za textem tasku.
3. `test_write_outside_scope_is_reverted_and_fails` — builder effect zapíše `src/app/ok.py`, upraví `README.md` a vytvoří `other/new.py`. Ověř: `not result.ok`, řádek `failed`, `error` zmiňuje `README.md`, `other/new.py` a `may only change`; ve worktree `other/new.py` neexistuje a `git -C wt diff --quiet -- README.md` uspěje; hlavní checkout čistý; žádný nový commit na větvi (`head_sha == base_sha`).
4. `test_second_run_of_running_task_fails` — vlož `TaskRunStore.claim(...)` s `state=running`, `pid=os.getpid()`; `run_task(..., force=True)` → `TaskRunError` s `code == "already_running"`; nevznikla žádná větev `factory/*` ani adresář `.factory/worktrees`; `main(["task","run","M01-S01-T01","--repo",str(repo),"--json"])` vrátí 1 a JSON s `error.code == "already_running"` (pozn.: CLI si cfg načte z `agents_config` — v testu CLI proto buď nastav `agents_config` v `.factory/config.yaml` na absolutní? **Ne** — relativní cesta je povinná; místo toho zapiš do repa `.factory/…` a zkopíruj/nasměruj: nejjednodušší je v testu monkeypatchnout `haifa_proto.run.run_task` tak, aby doplnil `cfg=env.cfg` (`functools.partial`). Kontrola běžícího tasku musí proběhnout dřív než cokoli, co potřebuje agenty.)
5. `test_stale_running_row_does_not_block` — řádek `running` s pid ukončeného procesu (`p = subprocess.Popen(["true"]); p.wait(); pid = p.pid`) → běh proběhne, starý řádek je `aborted`.
6. `test_unmet_dependency_blocks_and_force_overrides` — T02 (závisí na T01 `todo`) → `unmet_dependencies`; pak změň T01 na `status: done` jen v pracovním stromu (necommitnuté) → stále `unmet_dependencies` (kontrola je na base); `force=True` → běh proběhne (builder effect zapíše `src/metrics/m.py`).
7. `test_branch_number_increments` — dva po sobě jdoucí úspěšné běhy T01 → větve `-1` a `-2`, dva řádky, `for_task` vrací nejnovější první.
8. `test_task_without_writes_is_refused` — `M01-S02-T01` → `no_writes`, nic nevzniklo.
9. `test_unknown_task_and_task_not_in_base` — neexistující id → `unknown_task`; task vytvořený jen v pracovním stromu → `task_not_in_base`.

**`tests/test_scope.py`** (nový, čisté unit testy nad `sample_repo` a ručně sestavenými `Task`/`Container`):
- `effective_writes`: vlastní vyhrává; dědí ze stepu; dědí z modulu, když step nemá; nic → `[]`; neplatná hodnota předka → `ScopeError`.
- `matches`: `src/api/` prefix; `src/api` jako adresář i soubor; `src/*.py` nepřekročí `/`; `src/**` ano; `./src/` normalizace.
- `task_scope(...).paths` obsahuje writes + `specs/` + `app_docs/` (a respektuje vlastní `specs_dir`/`docs_dir`).
- `enforce_task_scope`: uvnitř kontextu `permissions.permitted` odmítne cestu mimo scope i pro agenta s `writes=None`, povolí cestu ve scope, povolí session runtime (`data_dir/…`), odmítne chráněný soubor i ve scope (průnik); po výstupu (i po výjimce) jsou `permissions.permitted`/`enforce` zase originály.
- `task_prompt`: pořadí hlavička → text → poznámka; `(not set)` pro chybějící `source`.

**`tests/test_config.py`** (doplnit): výchozí `base == "main"`, `worktrees_dir == ".factory/worktrees"`, `agents_config`, `specs_dir`, `docs_dir`; vlastní hodnoty; neplatné: `base: ''`, `worktrees_dir: /abs`, `specs_dir: ''`.

**`tests/test_cli_task.py`** (nový): `task --help` ukazuje `run` a `show`; `task show <id> --json` po jednom běhu (přes `run_task` s `cfg=env.cfg`) vypíše `task` a `runs` s jedním řádkem a `state`; `task show` pro neznámé id → exit 1; `task show` pro task bez běhů → `runs: []`, exit 0. `task show` čte DB přes `trace_db_path`: v testu buď zapiš do repa `adws/adw_sssf_config/sssf.config.yaml` s absolutním `observability.db` (sssf config sám absolutní cesty dovoluje — omezení na relativní platí jen pro `agents_config` v `.factory/config.yaml`), nebo monkeypatchni `trace_db_path`. Preferuj první variantu (zkopíruj `tmp_path/sssf.config.yaml` z `make_engine_env` do repa a commitni ho), ať se testuje skutečná cesta; pak ho lze použít i v bodě 4 místo monkeypatche `run_task` — ale pozor, `agents.load_config` z CLI pak musí najít fake harnessy už nainstalované v `agents.INTERFACES` (jsou, fixture je dosadí přes monkeypatch).

Všechny testy běží s fixture `engine_env` (fake harnessy, žádný model, obnova signal handlerů). Každý test, který spustí `run_task`, musí na konci mít cwd zpět v repu.

## Ověření

Z kořene repa:

```bash
just test        # celé pytest, včetně nových testů
just typecheck   # mypy --strict nad src i tests
just lint        # ruff
```

Ruční kontrola (volitelná, bez modelu nelze spustit celý běh): `uv run --project prototype haifa-proto task --help`, `... task show M01-S02-T01 --repo prototype/tests/fixtures/backlog --json` (task bez běhů → `runs: []`).

Posuď podle exit kódu, ne podle textu výstupu.

## Kontrolní seznam pro buildera

- [ ] `vendor/` beze změny (`git status vendor/` prázdný).
- [ ] Žádný zápis do souborů tasků; žádné `status: done`.
- [ ] `permissions.permitted`/`enforce` se po běhu vždy vrátí na originál (i při výjimce).
- [ ] cwd se po běhu vždy vrátí.
- [ ] `data_dir` a `db` absolutní do hlavního checkoutu; nic z runtime nevzniká ve worktree.
- [ ] Worktree se při selhání nemaže.
- [ ] `task` bez podpříkazu vrací 0.
- [ ] mypy strict: typy u všech nových funkcí, `Any` pro objekty z enginu.
