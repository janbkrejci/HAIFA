# Plán 2.9: `factory task run` ve worktree, hlídání zápisů mimo worktree, výstupy podle tasku

## Zadání (shrnutí)

`factory task run <task-id> [--note TEXT] [--force] [--json] [--repo PATH]` spustí task z backlogu ve vlastním git worktree a větvi (kroky 1 až 3 sekce „Běh úkolu“ v `docs/product-brief.md`). `factory task show` navíc ukáže běhy tasku. Kód hlídá, aby agent nezměnil nic mimo worktree svého běhu a mimo povolené cesty. Opravuje zjištění Z1 z `docs/prototype-report.md`: agent zapisoval do hlavního checkoutu, gate `artifacts_exist` to přijala a kontrola `writes` to neviděla.

Mimo rozsah: push a PR (2.12, žádná tabulka `task_prs`, žádný `GitProvider`), auto-continue (2.15), dashboard.

Pevná omezení: `vendor/` a `prototype/` se nemění. Testy nevolají model. Nikdy se nezapisuje `status: done` do souboru tasku.

## Co už existuje (nezkoumej znovu)

- **Prototyp jako zdroj:** `prototype/src/haifa_proto/run.py` (`TaskRunStore`, `_ensure_wal`, `claim`, `serialized`, `_reap`, `ensure_excluded`, `next_branch`, `load_base_backlog`, `task_prompt`, `_missing_task`, `_signals_restored`, `_run`) a `scope.py` (`matches`, `TaskScope`). Přenášej logiku, ne monkeypatching: engine je teď náš (`aifactory/src/aifactory/engine/`), takže háky se přidají přímo do něj. Části pro PR (`task_prs`, `publish`, `run_on_branch`, provider) nepřenášej.
- **Konfigurace z base (2.4):** `aifactory.config.load_run_config(root) -> RunConfig(base, commit, config: FactoryConfig, local: LocalSettings, changes, warnings)`. `FactoryConfig.settings: ProjectSettings` má `backlog_dir`, `levels`, `specs_dir` (výchozí `specs`), `docs_dir` (`app_docs`), `worktrees_dir` (`.factory/worktrees`), `base`, `protected_files` (`(".factory/",)`). `FactoryConfig.agents: SSSFConfig`, `.roles: RoleRegistry`, `.workflows: dict[name, raw dict]` z `.factory/workflows/*.yaml` v base, `.prompts`. `write_prompts(config, dest) -> SSSFConfig` zapíše prompty agentů pod `dest/<agent>/{system,user}.md` (absolutní cesty) a vrátí roster, který na ně ukazuje. `LocalSettings.trace_db_path(root)` = trace DB (výchozí `.factory/trace.db`). `load_run_config` vyhazuje `ConfigError` (i pro neexistující base).
- **Backlog (2.5):** `aifactory.backlog.load_backlog(root, settings)`, `Task` (`id, title, status, path, depends_on, writes, body, ...`), `effective_writes(task)` (dědí z `index.md`), `effective_workflow(task)`, `effective(task)`, `unmet(backlog, task) -> list[Unmet(id, reason, missing)]`, `slugify(text)` v `aifactory.backlog.edit`. `ancestors` je v `aifactory.backlog.derived`.
- **Workflow (2.7/2.8):** `aifactory.workflow.parse_workflow(data, roles, source=None)`, `load_workflow(path, roles)`, `DEFAULT_WORKFLOWS_DIR`, `preflight(workflow, cfg)`, `run_workflow(workflow, prompt, cfg, *, code=None, adw_id=None) -> WorkflowRun(exit_code, accepted, adw_id, results, ...)`, `EngineCodeRunner` (commit = `git_helper.commit_all`, které už při čistém stromu vrací `""` místo chyby).
- **Engine:** `session.ensure(cfg, adw_id)` → `Run` (`repo_root = git_helper.repo_root()` z cwd procesu, `session_dir = data_dir/sessions/<adw_id>`, `context_handoff_dir`). `agents.execute` renderuje prompty s proměnnými `prompt`, `previous_envelope`, `context_handoff_dir`, volá harness s `cwd=run.repo_root`, pak `permissions.snapshot(run)` před a `permissions.enforce(run, phase, agent, before)` po. **Díra:** když selže parse nebo gate (`GateFailure`) nebo harness, `enforce` se vůbec nezavolá a neoprávněné zápisy zůstanou. `gates.artifacts_exist` bere `Path(a).exists()` bez ohledu na to, kde cesta leží. Gates se v `RoleRegistry` resolvují na objekty funkcí při načtení, monkeypatch modulu by nepomohl.
- **Engine není lintovaný ani typovaný** (`pyproject.toml`: ruff `extend-exclude`, mypy override). Tak to nech. Uprav jen komentář nad `extend-exclude`: engine už není „byte-identical“, logické změny oproti sssf jsou označené komentářem `# aifactory 2.9:` v kódu.
- **Testy:** `tests/workflow/workflow_fakes.py` (`FakeHarness`, `Script` s `add`/`on` efekty, které dostanou `Path(request.cwd)`, `Call`, `ok()`, `make_engine_env`), `tests/config/config_repo.py` (`git`, `write`, `commit_all`, `make_repo`). Sdílený `conftest.py` není; fixture se importují z modulu fakes.
- **CLI:** `aifactory/src/aifactory/cli.py`: `_add_task_commands`, `_task` (dispatch), `_task_show`, `TASK_EPILOG`, `_print_json`, `_backlog_root(repo)`. Chybové JSON má tvar `{"ok": false, "errors": [{"code", "message", ...}]}`.

## Návrhová rozhodnutí

1. **run-id = adw_id** (`aifactory.engine.utils.new_id(8)`). Worktree `<main>/<worktrees_dir>/<run-id>`, větev `factory/<task-id>-<n>`, `n` = 1 + max přes `git for-each-ref refs/heads/factory/<task-id>-*` a přes `branch` v `task_runs` (jako prototyp).
2. **Vše z base:** `load_run_config(main_root)` dá base, sha a celou `.factory/` z commitu. Backlog z base: `git archive <sha> -- <backlog_dir>` do `tempfile.TemporaryDirectory()`, rozbalit `tarfile` s `filter="data"`, `load_backlog(tmp, settings)`. Task, který je jen v pracovním stromu → `task_not_in_base`. Neexistující → `unknown_task`. Workflow: `config.workflows[name]` → `parse_workflow(data, config.roles)`, jinak `DEFAULT_WORKFLOWS_DIR/<name>.yaml` → `load_workflow(path, config.roles)`, jinak `unknown_workflow`. Varování z `RunConfig.warnings` jdou do výsledku a v CLI na stderr.
3. **cfg běhu** (`prepare_cfg(main_root, run_config, prompts_dir) -> SSSFConfig`): `write_prompts(config, prompts_dir)`, pak `model_copy(deep=True)` a:
   - `defaults.data_dir`: když agents.yaml `data_dir` nenastavil nebo je rovný výchozímu sssf `adws/adw_data`, použij `.factory/data`. Vždy převést na absolutní cestu vůči hlavnímu checkoutu (session runtime zůstává v hlavním checkoutu, jak říká brief).
   - `observability.db = str(local.trace_db_path(main_root))`.
   - `defaults.protected_files` = sjednocení stávajících a `settings.protected_files`.
   Pro kontrolu před startem zapiš prompty do `TemporaryDirectory` (nic se nevytvoří). Pro běh je zapiš po `claim` do `<session_dir>/prompt_templates` (`session_dir = data_dir/sessions/<run-id>`).
4. **Povolené cesty (task scope)** = `effective_writes(task)` ∪ `{spec_path, doc_path}`. Přesně dva soubory, ne celé adresáře, takže kód vynutí i pojmenování výstupů. Scope je průnik s omezením agenta: cesta projde, když ji dovolí agent (`permissions.permitted`, včetně protected files) **a** zároveň task scope. Session runtime (`always_writable`) je povolený vždy. Prázdné `effective_writes` → `no_writes` a start se odmítne; `--force` to nepřebije. Shoda cest je `scope.matches` z prototypu: vzor s `*`/`?` nebo s `/` na konci jde přes `permissions._matches`, holá cesta platí jako přesná shoda nebo adresářový prefix. Úvodní `./` se odstraní.
5. **Výstupy podle tasku:** `slug` = jméno souboru tasku bez `.md` a bez prefixu `<task-id>-`. Když zbude prázdný řetězec, `slugify(task.title)`, a když ani to nic nedá, `task`. `spec_path = <specs_dir>/<task-id>-<slug>.md`, `doc_path = <docs_dir>/<task-id>-<slug>.md` (posix, relativní k worktree; když je adresář `.`, jen jméno souboru). Agent je dostane v task promptu a jako proměnné šablony `{{task_id}}`, `{{spec_path}}`, `{{doc_path}}`, `{{workdir}}`. Záložní zpráva commitu (když žádný envelope nemá `commit_message`) je `<task-id>: <summary>` místo `sssf(<adw_id>): …`. `run-id` zůstává jen v trace, v session adresáři, v názvu worktree a v id sessionů agentů.
6. **Hlídání zápisů (write guard):** nový hák v enginu. `Run.write_guard` je objekt s `snapshot(run)` a `enforce(run, phase, agent, before) -> list[str]`. Výchozí `None` znamená modul `permissions` (má přesně tyto funkce), takže mimo task run se chování nemění. Pro task run se použije `TaskWriteGuard` (`aifactory/run/guard.py`), který po **každém** volání agenta zkontroluje obojí:
   - **worktree:** změny proti snapshotu. Cesta mimo „agent ∧ task scope ∧ ne session runtime“ se vrátí přes `permissions._roll_back` (untracked smazat, tracked `git checkout --`). Když se ve worktree posunul `HEAD` (agent commitnul) na stejné větvi, `git reset --soft <head_před>` a porušení se pojmenuje jako `HEAD`. Commitnuté soubory se tím vrátí do diffu, takže se na ně použije stejná kontrola. Když agent přepnul větev, zapiš porušení „could not roll back: HEAD moved to …“.
   - **hlavní checkout:** stejný otisk (`git diff HEAD --numstat` + `git ls-files --others --exclude-standard`) s `cwd=main_root`. Ignorují se jen prefixy `<worktrees_dir>/`, session runtime (`data_dir` relativně k main, když leží uvnitř) a trace DB (`<db>`, `<db>-wal`, `<db>-shm`, `<db>-journal`). **Každá** jiná nově vzniklá změna je porušení a vrátí se (rollback jako výše, s `repo_root=main_root`). Posun `HEAD` nebo změna větve v hlavním checkoutu je porušení bez rollbacku.
   - Když je nějaké porušení, vyhoď `permissions.PermissionBreach` se zprávou, která jmenuje **každý** soubor s místem a výsledkem, např.:
     ```
     planner changed paths outside its task run:
       - main checkout: README.md — rolled back
       - worktree: src/other.py — deleted
     task M01-S01-T01 may only change ['src/app/', 'specs/M01-S01-T01-schema.md', 'app_docs/M01-S01-T01-schema.md'] inside its worktree
     ```
   Změny, které byly v hlavním checkoutu už před voláním agenta (rozdělaná práce operátora), se nevracejí. `_roll_back` je nechá být, stejně jako dnes.
   Známé omezení: soubory ignorované přes `.gitignore` git nevidí. Zapiš to do docstringu `guard.py`.
7. **Enforce i při selhání fáze:** v `agents.execute` obal část „send → parse → gates“ tak, aby se při jakékoli výjimce (`GateFailure`, chyba parse, výjimka harnessu) před jejím propagováním zavolal `guard.enforce(...)`. Když enforce vyhodí `PermissionBreach`, zapiš trace event `permission_breach` a vyhoď breach (`raise breach from error`). Jinak propaguj původní výjimku. Bez toho by zápis do hlavního checkoutu, na kterém pak selže gate, zůstal.
8. **`artifacts_exist`:** artefakt se vyhodnotí jako `p = Path(a)`; relativní cesta se vztáhne k `run.repo_root`, pak `p.resolve()`. Projde jen tehdy, když leží uvnitř `Path(run.repo_root).resolve()` nebo `Path(run.session_dir).resolve()` a existuje. Jinak check selže se zprávou `declared artifact is outside the run's worktree and session directory` (`declared artifact does not exist` zůstává). Použij `Path.is_relative_to`. V běžném (ne-task) běhu leží session dir obvykle v repu, takže se chování mění jen pro cesty mimo repo a mimo session.
9. **cwd:** `os.chdir(worktree)` jen kolem `run_workflow`, v `finally` vrátit. Navíc `run_workflow` nastaví `run.repo_root = worktree` explicitně, nespoléhá jen na cwd.
10. **Běžící task:** tabulka `task_runs` v trace DB, `claim` v `BEGIN IMMEDIATE`, mrtvé `pid` → `aborted` (jako prototyp). `--force` běžící task nikdy nepřebije. `TaskRunStore.__init__` přepne DB do WAL s retry (`_ensure_wal`), aby Tracer nespadl na zámku.
11. **Hlavní checkout zůstane čistý:** před `git worktree add` (uvnitř `store.serialized()`) idempotentně doplň do `<git-common-dir>/info/exclude` řádky `/<worktrees_dir>/`, `/<data_dir_rel>/` (když leží uvnitř main) a `/<trace_db_rel>*` (když leží uvnitř main). Sledované soubory se nemění.
12. **Výsledek:** chyba kontroly → `TaskRunError(code, message)` a nic se nevytvoří. Po `claim` se každá `Exception` z běhu zachytí a řádek dostane `failed` s `error=str(exc)[:2000]` a `head_sha`. `BaseException` → `failed` s `interrupted: …` a znovu vyhodit. Úspěch = `wf.accepted and wf.exit_code == 0`, jinak `failed` s `accept not met`. Worktree se nemaže. Handlery SIGINT/SIGTERM, které nainstaluje `session.ensure`, se po běhu vrátí (`_signals_restored` z prototypu).

## Soubory

### Engine (`aifactory/src/aifactory/engine/`), malé a označené změny `# aifactory 2.9:`

1. **`runner.py`:** `Run.__init__` přidá `self.write_guard = None` a `self.prompt_variables: dict = {}`.
2. **`agents.py` → `execute`:**
   - `guard = run.write_guard or permissions`. `tree_before = guard.snapshot(run)`. `touched = guard.enforce(run, phase, agent, tree_before)` místo přímého `permissions.*`. Stávající zpracování `except permissions.PermissionBreach` a trace eventu zůstane.
   - `variables = {**run.prompt_variables, "prompt": …, "previous_envelope": …, "context_handoff_dir": …}` (engine má přednost).
   - Bod 7: blok od `result = send(user_text)` po konec smyčky gates obal `try/except Exception as error:` a v handleru `guard.enforce` → při `PermissionBreach` event + `raise breach from error`, jinak `raise`. Vyčleň na to pomocnou funkci `_enforce_after_failure(run, phase, agent, guard, before, error)`, ať se trace event nepíše dvakrát.
3. **`gates.py` → `artifacts_exist`:** podle bodu 8. Pomocná `_inside(path, roots) -> bool`. Když `run` nemá `repo_root` nebo `session_dir` (`getattr(..., None)`), kontrolu umístění přeskoč. Staré volání s falešným `run` tak nespadne.

### Workflow

4. **`aifactory/src/aifactory/workflow/interpreter.py` → `run_workflow`:** nové keyword parametry `repo_root: Path | None = None`, `write_guard: Any = None`, `prompt_variables: Mapping[str, str] | None = None`, `label: str | None = None`. Po `session.ensure` je nastav na `run` (`repo_root` jen když není `None`). `_Interpreter` dostane `label`. `commit_message()` použije při fallbacku `f"{label}: {summary}"`, když je `label` zadaný, jinak dnešní `sssf(<adw_id>): …`.

### Nový balíček `aifactory/src/aifactory/run/`

5. **`__init__.py`:** docstring (co se čte odkud: vše ze `.factory/` a backlog z commitu v base, local.yaml a trace z disku hlavního checkoutu, session runtime v hlavním checkoutu) a exporty `run_task`, `task_runs_for`, `TaskRunError`, `TaskRunResult`, `TaskRunRow`, `TaskRunStore`, `TaskScope`, `TaskWriteGuard`, `OutputPaths`, `output_paths`, `task_prompt`.
6. **`errors.py`:** `TaskRunError(code, message)`, převzaté z prototypu.
7. **`store.py`:** `RUNNING/SUCCEEDED/FAILED/ABORTED`, `_SCHEMA` jen s `task_runs` (sloupce jako v prototypu), `TaskRunRow` (`to_json`), `_alive`, `_ensure_wal`, `TaskRunStore` (`claim`, `serialized`, `running`, `finish`, `get`, `for_task`, `branches`, `close`), `already_running(row) -> TaskRunError`. `_now()` z `aifactory.engine.utils.now_iso`.
8. **`gitops.py`:** `git(root, *args) -> str` (RuntimeError s stderr), `git_ok`, `main_root(repo)` (chyba → `TaskRunError("invalid_config")`), `ensure_excluded(root, lines)`, `next_branch(root, task_id, store)`, `extract_backlog(root, sha, backlog_dir, dest)` (archive + tar), `head(path) -> str | None`, `symbolic_head(path) -> str | None`, `fingerprint(root) -> dict[str, str]` (stejný formát jako `permissions.snapshot`, ale pro libovolný kořen).
9. **`scope.py`:** `normalize`, `matches`, `TaskScope(task_id, writes, outputs)` s `paths` a `permits(path)`, `OutputPaths(spec, doc)`, `task_slug(task)`, `output_paths(task, settings)`, `task_scope(task, outputs)`. Docstring vysvětlí průnik s agentem a proč jsou spec/doc povolené (přesné soubory).
10. **`guard.py`:** `TaskWriteGuard(main_root, worktree, scope, main_ignored: tuple[str, ...])` s metodami `snapshot(run) -> dict[str, Any]` (`{"worktree": permissions.snapshot(run), "worktree_head", "worktree_ref", "main": fingerprint(main) po filtru, "main_head", "main_ref"}`) a `enforce(run, phase, agent, before) -> list[str]` podle bodu 6. `_permitted(path, agent, cfg)`: `always_writable` → True, jinak `permissions.permitted(path, agent, cfg) and scope.permits(path)`. Rollback v hlavním checkoutu: `permissions._roll_back(SimpleNamespace(repo_root=main_root), path, before, after)`. Vrací cesty změněné ve worktree, které jsou povolené (pro trace `paths_touched`).
11. **`task.py`:**
    - `TaskRunResult(run: TaskRunRow, workflow_run: WorkflowRun | None, warnings: tuple[str, ...], trace_db: Path)` s `ok`.
    - `task_prompt(task, scope, outputs, worktree, note)`: hlavička jako v prototypu (`# Task <id>: <title>`, id, title, kontejnery z `ancestors`, source/target) plus řádky `- working directory: <worktree>` (all repo paths are relative to it), `- allowed paths: …`, `- spec file: <spec_path>`, `- documentation file: <doc_path>` a pravidlo „change only the allowed paths inside the working directory; anything else, including any file outside the working directory, is reverted and fails the phase“. Pak tělo tasku, pak `## Note`. Žádná jiná absolutní cesta, zvlášť ne `task.path` (míří do dočasné kopie base).
    - `resolve_workflow(task, config) -> Workflow`, `prepare_cfg(...)`, `_missing_task(...)`, `_signals_restored()`.
    - `run_task(repo, task_id, *, note=None, force=False, code=None) -> TaskRunResult`, pořadí:
      1. `root = main_root(repo)`, `rc = load_run_config(root)` (`ConfigError` → `invalid_config`), `store = TaskRunStore(rc.local.trace_db_path(root))`.
      2. Backlog z base → task (`unknown_task` / `task_not_in_base`) → `store.running` (`already_running`) → `unmet`, když není `--force` (`unmet_dependencies`, text jako v prototypu) → `effective_writes` (`no_writes`) → `output_paths` → `task_scope` → `resolve_workflow` (`no_workflow`/`invalid_workflow`/`unknown_workflow`) → `preflight` s prompty v dočasném adresáři (`WorkflowError` → `invalid_workflow`).
      3. `run_id`, `branch = next_branch`, `worktree = (root / worktrees_dir / run_id).resolve()`, `claim(row)`.
      4. V `store.serialized()`: `ensure_excluded`, `git worktree add -b <branch> <worktree> <base_sha>` (chyba → `finish(failed)` + `TaskRunError("worktree_failed")`).
      5. `cfg = prepare_cfg(..., session_dir / "prompt_templates")`. Guard: `main_ignored` = worktrees_dir, data_dir_rel, trace db rel + přípony. `prompt_variables = {"task_id", "spec_path", "doc_path", "workdir": str(worktree)}`.
      6. `chdir(worktree)`, `_signals_restored()`, `run_workflow(workflow, prompt, cfg, code=code, adw_id=run_id, repo_root=worktree, write_guard=guard, prompt_variables=vars, label=task_id)`, finally `chdir(prev)`. Stavy a chyby podle bodu 12. `finish(...)` a vrácení výsledku.
    - `task_runs_for(repo, task_id) -> list[TaskRunRow]`: trace DB z `load_local`. Když soubor neexistuje, `[]` (nic nevytvářet).

### CLI (`aifactory/src/aifactory/cli.py`)

12. Subparser `task run`: `task_id`, `--note TEXT`, `--force` („run even if depends_on are not done in base; never overrides a running task“), `--json`, `--repo`. Dispatch v `_task` před `_task_write`. `_task_run`:
    - s `--json` přesměruj stdout enginu na stderr (`contextlib.redirect_stdout(sys.stderr)`) a na stdout vypiš jen `{"ok", "run": row.to_json(), "warnings": [...]}`;
    - bez `--json`: varování na stderr, `run <id> <state>: branch <b>, worktree <w>`, chyba na stderr;
    - `TaskRunError` → exit **2**, JSON `{"ok": false, "errors": [{"code", "message"}]}`, text `factory task run: <code>: <message>`;
    - běh `failed` → exit 1, `succeeded` → 0.
13. `_task_show`: přidej běhy z `task_runs_for(root, task_id)`. JSON dostane klíč `"runs": [row.to_json(), …]`. Text za dosavadní výstup vypíše `runs:` a řádky `  <started_at>  <run_id>  <state>  <branch>  <head[:7] or ->` nebo `no runs`. `TaskRunError` v show → vypiš jako chybu s exit 2. Stávající testy `show` musí dál projít; když porovnávají celý výstup, uprav je jen o nový blok.
14. `TASK_EPILOG` doplň o kódy `task run` (exit 2): `already_running, task_not_in_base, unmet_dependencies, no_writes, no_workflow, unknown_workflow, invalid_workflow, worktree_failed` a o „run failed (exit 1)“. Aktualizuj docstring modulu (seznam příkazů).

### `pyproject.toml`

15. Jen komentář nad `extend-exclude` a mypy override (bod „Engine není lintovaný“). Seznamy nech beze změny.

## Testy (`aifactory/tests/`, bez modelu)

Nový adresář `tests/run/`:

- **`run_repo.py`** (helper, ne fixture):
  - `make_run_repo(path, harness="claude") -> Path`: `git init -b main`, `.gitignore` s `.factory/local.yaml`, `.factory/config.yaml` (`base: main`), `.factory/agents.yaml` (planner, builder, documenter, `harness: <harness>`, `model: sonnet`), prompty `.factory/prompts/<agent>/{system,user}.md`. User prompt obsahuje `{{prompt}}`, `ctx={{context_handoff_dir}}`, `spec={{spec_path}}` a `PREV<<{{previous_envelope}}>>PREV`. Workflow `.factory/workflows/plan-commit.yaml` (`name: plan-commit`, `steps: [plan, commit]`, `accept` bez podmínky nebo `plan.ran`, podle toho, co parser dovolí). Backlog `backlog/M01-core/index.md` (`workflow: plan-commit`), `backlog/M01-core/S01-model/index.md` (`writes: [src/app/]`), tasky `M01-S01-T01-schema.md` (todo, bez závislostí) a `M01-S01-T02-loader.md` (`depends_on: [M01-S01-T01]`). Soubory `README.md` a `src/app/__init__.py`. Vše commitnuté. Formát hlaviček převezmi z `tests/backlog/fixtures/sample/`.
  - `fake_harnesses(monkeypatch) -> Script`: vytáhni z `workflow_fakes.make_engine_env` část, která registruje `FakeHarness` pro claude/codex/pi (+ alias `claude_code`) a blokuje skutečné adaptéry, do sdílené funkce `install_fake_harnesses(monkeypatch) -> tuple[Script, dict[str, FakeHarness]]` v `workflow_fakes.py`. `make_engine_env` ji pak použije. Rozšiř `Call` o `system: str = ""` (z `request.system_prompt`).
  - Nastav `ENGINEER_NAME` a po testu vrať handlery signálů (jako `make_engine_env`).
- **`test_task_run.py`:**
  1. `test_run_creates_worktree_branch_and_row`: planner zapíše `spec_path` (efekt `lambda wt: write(wt, "specs/M01-S01-T01-schema.md", ...)`) a vrátí envelope s artefaktem `specs/M01-S01-T01-schema.md`. Ověř, že `state == "succeeded"`, worktree existuje v `.factory/worktrees/<run_id>`, větev je `factory/M01-S01-T01-1`, `git show factory/M01-S01-T01-1:specs/M01-S01-T01-schema.md` projde, `git status --porcelain` v hlavním checkoutu je prázdný a řádek v `task_runs` má stav `succeeded` a `head_sha`. Druhý běh dostane větev `…-2`.
  2. `test_outputs_are_named_by_task`: prompt, který dostal planner, obsahuje `specs/M01-S01-T01-schema.md` a `app_docs/M01-S01-T01-schema.md` a nikde ne `run_id`. Zpráva commitu v worktree nezačíná `sssf(`. Planner, který zapíše `specs/<run_id>_plan.md`, způsobí `failed`, soubor je smazaný a `error` ho jmenuje.
  3. `test_write_to_main_checkout_is_reverted[claude|codex|pi]` (parametrizace přes harness agenta v `agents.yaml`): efekt planneru zapíše do hlavního checkoutu nový soubor `app_docs/x.md` a změní sledovaný `README.md`. Běh skončí `failed`, `error` obsahuje `main checkout`, `app_docs/x.md` i `README.md`, soubor v main neexistuje a `README.md` má původní obsah. Ověř i to, že fake byl volán s `cwd == worktree`.
  4. `test_write_outside_writes_is_reverted`: efekt zapíše `src/other.py` ve worktree. `failed`, soubor ve worktree neexistuje, `error` jmenuje `src/other.py`.
  5. `test_agent_commit_outside_writes_is_reverted`: efekt ve worktree vytvoří `src/other.py` a `git commit`. `failed`, HEAD worktree = base sha, soubor pryč, `error` zmíní `HEAD` i `src/other.py`.
  6. `test_breach_is_reverted_even_when_gate_fails`: planner zapíše do main a vrátí artefakt, který neexistuje. `retries` role vyčerpá gate a skončí `GateFailure`. Soubor v main je i tak pryč a `error` ho jmenuje.
  7. `test_empty_commit_does_not_fail`: planner nic nezapíše (envelope s `artifacts: []`). `succeeded`, `results["commit"]["committed"] is False`. Použij reálný `EngineCodeRunner` (`code=None`).
  8. `test_second_start_of_running_task_fails`: `TaskRunStore(...).claim(row s pid=os.getpid(), state running)`, pak `run_task` → `TaskRunError` s kódem `already_running`. I s `force=True`. CLI `main(["task","run",id,"--json","--repo",repo])` → exit 2 a `errors[0].code == "already_running"`. Varianta s mrtvým pid (např. pid podřízeného procesu, který už skončil) → řádek je `aborted` a běh projde.
  9. `test_prompt_paths_stay_in_worktree_or_session`: po běhu projdi `script.calls` (`prompt` i `system`). Každý výskyt `str(main_root)` (a varianty přes `/private`, když se liší) musí pokračovat prefixem `str(worktree)` nebo `str(session_dir)`. Regex `re.escape(root) + r"[^\s`'\"<>)]*"`.
  10. Kontroly před startem: `unmet_dependencies` pro T02 (a s `force=True` běh proběhne), `task_not_in_base` (task přidaný jen do pracovního stromu), `unknown_task`, `no_writes` (task v kroku bez `writes`), `unknown_workflow`. Pro každou ověř, že se nevytvořil worktree ani větev.
  11. `test_config_comes_from_base`: necommitnutá změna promptu planneru v pracovním stromu se do promptu nedostane a `result.warnings` není prázdné.
- **`test_task_run_cli.py`:** `task run --json` úspěch (exit 0, `run.state`), selhání běhu (exit 1), `task show --json` obsahuje `runs` s `run_id`, textový `task show` vypíše run_id, `task run` bez `--json` vypíše `run <id> succeeded`.
- **`tests/engine/`:** (a) `artifacts_exist` s `SimpleNamespace(repo_root=wt, session_dir=sd)`: relativní cesta ve wt projde, absolutní v `sd` projde, absolutní v jiném adresáři (existující) selže se zprávou `outside`, `../x` selže. (b) `agents.execute`: agent s `writes: [a/]` zapíše `b.txt` a pak neprojde gate → `PermissionBreach` a `b.txt` je pryč. (c) `run.write_guard` s vlastním objektem se zavolá místo `permissions` (snapshot i enforce). (d) `prompt_variables` se dosadí do šablony.
- Existující testy, které deklarují artefakty mimo repo i mimo session dir, přepiš tak, aby artefakt ležel v session dir nebo v repu. Smysl testu nesmí oslabit.

## Ověření

```bash
just test
just typecheck
just lint
```

Všechny tři musí skončit s exit status 0 (posuzuj podle návratového kódu). Ručně (volitelně): `just factory task run --help` a `just factory task --help` ukážou nové volby a kódy chyb.

## Poznámky pro buildera

- Testy nesmí volat `claude`, `codex` ani `pi`. Každá sada, která spouští `run_task`, musí mít registrované falešné harnessy (`install_fake_harnesses`) dřív, než proběhne `preflight`.
- `tmp_path` na macOS: porovnávej `.resolve()` cesty. `main_root` bere `git rev-parse --show-toplevel`.
- `session.ensure` instaluje handlery signálů. V testech i v `run_task` je vracej.
- Engine soubory zůstávají mimo ruff a mypy. Nové moduly v `aifactory/run/` musí projít `mypy --strict` a ruff.
- `prototype/` a `vendor/` neupravuj ani kvůli testům.
