# Plán: auto-continue a bezpečné paralelní běhy v `aifactory` (backlog 2.15, D10, Q9)

## Cíl

Přenést do `aifactory` auto-continue a paralelní běhy z prototypu (`prototype/src/haifa_proto/queue.py`,
testy `prototype/tests/test_auto_continue.py`) a doplnit přepínač auto-continue u modulu nebo stepu:

1. `factory task run <ID> --auto` a `auto_continue: true` v `index.md` modulu/stepu (zděděné na task):
   po úspěšném běhu (stav `succeeded` a PR vytvořen, `result.ok and result.pr is not None`) se spustí
   další připravený task v pořadí backlogu: nejdřív ze stejného stepu, pak ze zbytku téhož modulu.
   Selhání řetěz zastaví. Řetěz **nikdy** neschvaluje ani nemerguje a nikdy nečeká (nepolluje).
2. Task, jehož nesplněné závislosti čekají jen v otevřených (nemergnutých) PR, se přeskočí
   (`waits_on_pr`) a spustí se další, který jde (Q9). Po skončení se vypíše, na co řetěz čeká.
3. Dva běhy různých tasků běží současně, dva běhy téhož tasku ne (`already_running`). Trace DB je ve
   WAL a první souběžné běhy nad dosud neexistující DB nekončí `database is locked`.
4. Přepínač: `factory backlog auto-continue <ID> --on|--off|--inherit` zapíše/odebere
   `auto_continue` v `index.md` modulu nebo stepu.

Mimo rozsah: plánovač napříč moduly, limit paralelity, dashboard, čekání na schválení.
**`vendor/` a `prototype/` se nemění. Testy nevolají model** (falešné harnessy z
`aifactory/tests/workflow/workflow_fakes.py`, provider `local`).

## Co už v `aifactory` existuje (nezkoumej znovu)

- `run/store.py`: `TaskRunStore` — `claim()` v `BEGIN IMMEDIATE` (+ `_reap` mrtvých pidů) → souběžný
  start téhož tasku skončí `already_running`; `serialized()` drží zápisový zámek kolem `git worktree add`;
  **WAL oprava z úkolu 1.12 je už přenesená** (`_ensure_wal`, chyba `trace_db_locked`). Metody
  `running(task_id)`, `open_pr(task_id)`, `for_task`, `pr_for_branch`. Chybí jen testy (žádný test v
  `aifactory/tests` WAL/souběh neověřuje).
- `run/task.py`: `run_task(repo, task_id, *, note, force, code, provider, branch, resolve_onto)` →
  `TaskRunResult(run, workflow_run, warnings, trace_db, pr, pr_error)`, `.ok` = succeeded a bez
  `pr_error`. Backlog se čte z commitu `base`: `rc = load_run_config(main)` (`run/task.py::_load`),
  `gitops.extract_backlog(main, rc.commit, settings.backlog_dir, tmp)`, `load_backlog(tmp, settings)`.
  `gitops.main_root(repo)`.
- `backlog/model.py`: `INHERITED_KEYS` už obsahuje `auto_continue`; `backlog/derived.py`:
  `effective(task)`, `ancestors(task)` (poslední = modul), `descendant_tasks(container)` (seřazeno podle
  `path` = pořadí backlogu), `unmet(backlog, task)` → `Unmet(id, reason, missing)`; reason
  `unknown|cancelled|not_done|empty|incomplete`.
- `backlog/edit.py`: `_commit(...)` (validace na kopii + atomický zápis, ale vrací `WriteResult` s
  `Task`), `TaskEditError`, `_guard`, `load_for_edit`. `backlog/taskfile.py`: `set_field`,
  `remove_field` — `set_field` dnes umí jen `str | list[str]` (řetězec `"true"` by zapsal v uvozovkách).
- `engine/tracer.py`: `Tracer(db_path, events_jsonl)` nastavuje WAL před `busy_timeout` (proto oprava).
- CLI `cli.py`: `task run` (ř. ~456), `_run_output(args, start)` (ř. ~731), `_task_run` (ř. ~762),
  dispatch `_task` (ř. ~811, mapuje `TaskRunError` → exit 2), `TASK_EPILOG` (ř. ~370),
  `_add_backlog_commands` (ř. ~201), `_backlog` (ř. ~296, `sync` se obsluhuje před `load_backlog`).
- Testovací pomůcky: `aifactory/tests/run/run_repo.py` (`make_run_repo`, `fake_env`, `git`, `write`,
  `commit_all`, `ok`, `Script`; workflow `plan-commit` = krok `plan` (agent `planner`) + `commit`;
  step `M01-S01` má `writes: [src/app/]`; výchozí `git_provider` = `local`, PR url `local:<branch>`,
  trace DB `repo/.factory/trace.db`). Vzor: `tests/run/test_task_pr_flow.py`
  (`approve_task(repo, T01)` funguje s providerem `local` bez remote).

## Návrh

### 1. `aifactory/src/aifactory/run/queue.py` (nový)

Port `prototype/src/haifa_proto/queue.py` s úpravami pro `aifactory` (bez `cfg`, `load_config`):

```python
STOP_FAILED, STOP_EXHAUSTED, STOP_DISABLED = "failed", "exhausted", "disabled"
_HARD_REASONS = ("unknown", "cancelled", "empty")

@dataclass
class Skip:            # task_id, reason (waits_on_pr|blocked|in_review|running|cannot_start), detail, waits_on
    def to_json(self) -> dict[str, object]: ...

@dataclass
class Selection:       # next: Task | None, skipped: list[Skip]

def auto_continue_enabled(task: Task) -> bool:
    return effective(task).get("auto_continue") is True

def candidates(after: Task) -> list[Task]        # todo tasky stepu `after.parent`, pak zbytek modulu
                                                  # (ancestors(after)[-1]); bez `after`, bez duplicit
def select_next(backlog, after, *, open_pr, running, exclude=frozenset()) -> Selection
                                                  # přesně logika prototypu (pořadí kontrol:
                                                  # exclude → running → in_review (vlastní open PR)
                                                  # → unmet: všechny chybějící tasky mají open PR
                                                  #   a žádný reason v _HARD_REASONS → waits_on_pr,
                                                  #   jinak blocked → první zbylý = next)
@dataclass
class ChainResult:     # runs: list[TaskRunResult], stop: str, waiting: list[Skip]
    ok (all r.ok), to_json() -> {"ok","runs":[{"ok","run","pr","pr_error"}],"stop","waiting"}

def run_chain(repo, task_id, *, auto=False, note=None, force=False,
              code: CodeRunner | None = None, provider: GitProvider | None = None) -> ChainResult
```

`run_chain`:
- První běh: `task_mod.run_task(repo, task_id, note=note, force=force, code=code, provider=provider)`
  (import `from aifactory.run import task as task_mod` a volání přes atribut modulu, ať jde v testech
  monkeypatchnout). `TaskRunError` prvního běhu **propaguje** (CLI jako dnes exit 2).
- Smyčka: když `not last.ok or last.pr is None` → `ChainResult(runs, STOP_FAILED)`.
  Jinak v `tempfile.TemporaryDirectory(prefix="factory-chain-")` načti čerstvý backlog z `base`
  (helper `_base_backlog(repo, dest)`: `main = gitops.main_root(repo)`, `rc = task_mod._load(main)`
  (nebo `load_run_config` s mapováním `ConfigError` → `TaskRunError("invalid_config")`),
  `gitops.extract_backlog(main, rc.commit, rc.config.settings.backlog_dir, dest)` s mapováním
  `OSError/RuntimeError` → `TaskRunError("invalid_config", ...)` jako v `run_task`,
  `load_backlog(dest, rc.config.settings)`).
  `after = backlog.by_id.get(last.run.task_id)`; není-li `Task` nebo `not (auto or
  auto_continue_enabled(after))` → `STOP_DISABLED`.
  `store = TaskRunStore(last.trace_db)`; `select_next(..., open_pr=store.open_pr,
  running=store.running, exclude=exclude)`; `store.close()` ve `finally`.
  `next is None` → `ChainResult(runs, STOP_EXHAUSTED, [*start_skips, *selection.skipped])`.
  Jinak `exclude.add(next.id)`, `run_task(repo, next.id, code=code, provider=provider)` (bez `note`
  a `force`); `TaskRunError` → `start_skips.append(Skip(id, "cannot_start", f"{code}: {message}"))`
  a `continue` (zkusí další); jinak `runs.append(result); last = result`.
- Nastavení `auto` platí pro celý řetěz; bez `--auto` rozhoduje `auto_continue` zděděný **právě
  dokončeným** taskem (tj. `auto_continue: true` na stepu S01 předá poslední task S01 dál do jiného
  stepu modulu a tam řetěz skončí `disabled`). Popiš v docstringu modulu (převezmi z prototypu).
- Poznámka k Q9: task čekající na PR se v řetězu už nespustí; po `task approve` ho operátor spustí
  ručně (případně s `--auto`). Nepolluj.

Export v `run/__init__.py`: `ChainResult`, `Skip`, `run_chain`, `select_next`, `STOP_*`; do
docstringu balíčku přidej odstavec o `queue.py` (auto-continue, souběh: různé tasky paralelně díky
`claim` + `serialized`, WAL přepíná store dřív než Tracer).

### 2. CLI `task run --auto`

- `run.add_argument("--auto", action="store_true", help="after a successful run (PR opened) start "
  "the next ready task of the step, then of the module (auto-continue); a failure stops the chain")`.
  Upravit `description` `task run` o větu o auto-continue a `auto_continue` v `index.md`.
- `_task_run` přepsat (ne přes `_run_output`, ten zůstává pro `return`/`resolve`):
  ```python
  chain = run_chain(root, args.task_id, note=args.note, force=args.force, auto=args.auto)
  ```
  `--json` (engine vypráví na stdout → `contextlib.redirect_stdout(sys.stderr)` jako v
  `_run_output`): výstup = dosavadní klíče pro **první** běh (`ok`, `run`, `pr`, `pr_error`,
  `warnings`) — ale `ok` = `chain.ok` — plus klíč `"chain": {"runs": [...], "stop": ..., "waiting":
  [...]}` (vždy). Pomocnou funkci `_run_json(result)` vytáhni z `_run_output` a použij v obou.
  Text: pro každý běh řádky jako dnes (`run … state: branch …, worktree …`, `pr …`, chyby na stderr,
  warnings jen jednou z prvního běhu); pak když `len(runs) > 1 or stop == STOP_EXHAUSTED`:
  `auto-continue: stopped (<stop>)`, pro každý skip `waiting: <task_id> <reason>: <detail>`, a
  `auto-continue: nothing left to run` pokud exhausted a žádný skip.
  Exit: `0 if chain.ok else 1` (chyba startu prvního běhu → 2 jako dnes přes `_task`).
- `TASK_EPILOG`: doplnit řádky o `--auto` (stop `failed|exhausted|disabled`, skip reasons,
  „never approves nor merges“).
- Existující testy v `tests/run/test_task_run_cli.py` a `test_task_run.py` musí projít beze změny
  (JSON dostane jen navíc `chain`; ověř, že žádný test neporovnává celý dict — grep to nenašel).

### 3. Přepínač u modulu/stepu: `factory backlog auto-continue <ID> (--on | --off | --inherit)`

- `backlog/taskfile.py`: `set_field` a `_format_value` přijmou i `bool` (`true`/`false` bez uvozovek);
  typ `str | list[str] | bool`. Kontrola `parsed != value` funguje i pro bool. Pozor: `bool` testuj
  před `str` (a `isinstance(value, list)` zůstává první).
- `backlog/edit.py`:
  - Z `_commit` vytáhni validovaný zápis do `_write_checked(backlog, baseline, changes) -> bool`
    (vrací, zda se něco zapsalo) a `_commit` na něm postav (chování beze změny).
  - Nový `@dataclass ContainerWriteResult(action, changed, path, container: Container, backlog, issues)`
    a funkce
    ```python
    def set_auto_continue(root: Path, container_id: str, enabled: bool | None) -> ContainerWriteResult
    ```
    najde kontejner (`iter_containers(backlog.containers)`, `container.id == container_id`);
    neexistuje → `TaskEditError("unknown_container", ...)` (exit 2); nemá `index_path` →
    `TaskEditError("no_index", ...)`; `enabled is None` → `remove_field(text, "auto_continue")`,
    jinak `set_field(text, "auto_continue", enabled)` (přes `_apply`, rozšiř typ). Zapisuje do
    pracovního stromu (běhy čtou `base` → uživatel musí commitnout; uveď v help/description).
    Po zápisu znovu načti backlog a vrať kontejner z nového backlogu.
  - Doplň oba kódy do tabulky v docstringu modulu; export z `backlog/__init__.py`.
- `backlog/loader.py`: u kontejneru i tasku, když `auto_continue` není `None` ani `bool`, vydej
  issue `invalid_field` („field 'auto_continue' must be true or false“) a hodnotu nepřebírej
  (stejný vzor jako `writes` u kontejneru). `auto_continue_enabled` stejně bere jen `is True`.
- `cli.py`: v `_add_backlog_commands` nový subparser `auto-continue` (`id` metavar `ID`, vzájemně
  výlučná povinná skupina `--on/--off/--inherit`, `--json`, `--repo`); v `_backlog` obsluž
  `command == "auto-continue"` před `load_backlog` funkcí `_backlog_auto_continue(args)` s mapováním
  `ConfigError` (exit 2, jako jinde) a `TaskEditError` (`exc.errors()`, `exc.exit_code`).
  Text: `auto_continue <on|off|inherited> for <ID> (<path>)` nebo `unchanged <ID>`.
  JSON: `{"ok": true, "changed", "id", "level", "path", "auto_continue": true|false|null,
  "issues": [...]}`.

### 4. Souběh — kód

Kód souběhu už je; nic neměň, jen pokud test níže odhalí problém. Kdyby paralelní test padal na git
zámku (`index.lock`, `packed-refs`) v `publish`/`provider.push`, obal `provider.push` v `publish`
do `store.serialized()` — jen tehdy.

## Testy (nové soubory v `aifactory/tests/run/`)

Společná příprava (v testovém souboru, případně helper v `run_repo.py`): repozitář `make_run_repo`,
v `backlog/M01-core/S01-model/` nahradit T01/T02 tasky T01, T02, T03 (volitelně `depends_on`),
`index.md` stepu s `writes: [src/app/]` a volitelně `auto_continue: true`, `commit_all`. Každý běh
spotřebuje jednu obálku `planner`: helper
`_build(script, name, path=None)`: `script.on("planner", lambda wt: write(wt, rel, ...))` +
`script.add("planner", ok(artifacts=[], changed_files=[rel], commit_message=f"Add {name}"))`
(ověř, že `plan-commit` s `ok(...)` projde — vzor `succeed()` v `test_task_pr_flow.py`, případně
zapisuj i SPEC tasku). Fixture `script` přes `fake_env(monkeypatch)`.

### `test_auto_continue.py` (port z prototypu)
1. `test_three_independent_tasks_run_in_order` — step `auto_continue: true`; `run_chain(repo, T01)`
   → runy `[T01, T02, T03]`, všechny ok, `stop == exhausted`, `waiting == []`, každý má open PR,
   `main` nezměněný, v base jsou všechny `todo`.
2. `test_without_auto_one_run_only` — bez přepínače → jen T01, `stop == disabled`, T02 bez běhů.
3. `test_auto_flag_continues` — `auto=True` bez přepínače → `[T01, T02, T03]`.
4. `test_module_switch_continues_across_steps` — `auto_continue: true` v `index.md` modulu, druhý step
   `M01-S02` (vlastní `writes`) s taskem → řetěz projde S01 a pak S02 (pořadí stepu první).
5. `test_dependent_task_skipped_until_approve` (Q9) — T02 `depends_on: [T01]`; `--auto` → `[T01, T03]`,
   `waiting == [Skip(T02, "waits_on_pr", f"{T01} (PR {url})", [T01])]`; `run_task(T02)` →
   `unmet_dependencies`; `approve_task(repo, T01)`; `run_chain(T02, auto=True)` → `[T02]`, waiting
   `[(T03, "in_review")]`.
6. `test_failure_stops_chain` — přes CLI `--auto --json`; druhý běh zapíše mimo `writes`
   (`README.md`) → exit 1, `ok false`, `chain.runs` = `[T01 ok, T02 fail]`, `stop == failed`,
   T03 bez běhů.
7. `test_task_that_cannot_start_is_reported` — další step bez `writes` s taskem → `cannot_start`,
   `detail` začíná `no_writes:`.
8. `test_select_next_rules` — čistý unit test `select_next` s `open_pr`/`running` jako dict/lambda
   (pořadí `waits_on_pr`, `blocked`, `in_review`, `running`, výběr, `exclude`, přechod do jiného
   stepu). `TaskPrRow`/`TaskRunRow` stav poskládej ručně jako v prototypu.
9. `test_cli_auto_json` a `test_cli_auto_text_reports_waiting` — `main(["task","run",T01,"--repo",
   str(repo),"--auto"(,"--json")])`; JSON má `run.task_id == T01`, `chain.runs` tři, `chain.stop`;
   text obsahuje `auto-continue: stopped (exhausted)` a `waiting: {T02} waits_on_pr: {T01} (PR `.

### `test_parallel_runs.py` (port z prototypu)
Pomocí `multiprocessing.get_context("fork")` (skip, když `fork` není v `get_all_start_methods()`);
fake harnessy nainstalované v rodiči přes monkeypatch se forkem zdědí. Dítě si naskriptuje vlastní
`planner` obálku a efekt, volá `run_task`, výsledek posílá přes `ctx.Queue` (`ok`/`error <code>`/
`crash`). Timeouty (`Barrier(timeout=60)`, `Queue.get(timeout=120)`, `join(timeout=60)`).
1. `test_parallel_runs_of_different_tasks` — T01 a T03 současně, bariéra uvnitř efektu agenta ověří,
   že oba běží zároveň; oba ok, větve `factory/<id>-1`, oba open PR, různé worktree.
2. `test_parallel_runs_on_fresh_trace_db` — trace DB ještě neexistuje; bariéra před `run_task` i
   uvnitř; oba ok (žádné `database is locked`); poté `PRAGMA journal_mode` == `wal`.
3. `test_concurrent_start_of_same_task_one_refused` — dva procesy na T01; vítěz v efektu čeká na
   `Event`, poražený dostane `already_running`; výsledky `{ok, error already_running}`, jeden běh
   `succeeded`.
4. `test_tracer_opens_fresh_trace_db_while_store_holds_lock` — `TaskRunStore(db)` nad novou DB, ve
   `with store.serialized():` otevři ve vlákně `aifactory.engine.tracer.Tracer(db, tmp/"events.jsonl")`
   (zavři `tracer.conn` ve vlákně), vlákno doběhne bez výjimky, DB je `wal`.

### `tests/backlog/` — přepínač
V `test_task_edit.py` nebo novém `test_backlog_auto_continue.py` (repo z `backlog_repo.py`):
`--on` na stepu zapíše `auto_continue: true` (bez uvozovek, ostatní řádky beze změny), `effective`
tasku vrací `True`; `--off` → `false`; `--inherit` odebere řádek; opakování → `changed false`;
neznámé ID → exit 2 `unknown_container`; `--json` tvar; `set_field(..., True)` unit test; loader
hlásí `invalid_field` pro `auto_continue: yes-please`.

## Ověření

```
just test
just typecheck
just lint        # ruff check + ruff format --check (spusť `cd aifactory && uv run ruff format .` před tím)
```
Všechny tři musí skončit exit 0. Rozhoduj podle exit statusu. Paralelní testy spusť několikrát
(`just test tests/run/test_parallel_runs.py -p no:randomly --count` není k dispozici → prostě 3×),
ať je vidět, že nejsou flaky.

## Soubory

- nový `aifactory/src/aifactory/run/queue.py`
- `aifactory/src/aifactory/run/__init__.py` (export, docstring)
- `aifactory/src/aifactory/cli.py` (`--auto`, `_task_run`, `_run_json`, `TASK_EPILOG`,
  `backlog auto-continue`)
- `aifactory/src/aifactory/backlog/edit.py`, `taskfile.py`, `loader.py`, `__init__.py`
- nové `aifactory/tests/run/test_auto_continue.py`, `aifactory/tests/run/test_parallel_runs.py`,
  testy přepínače v `aifactory/tests/backlog/`
- (jen pokud test ukáže potřebu) `aifactory/src/aifactory/review/publish.py`

Neměnit: `vendor/`, `prototype/`.
