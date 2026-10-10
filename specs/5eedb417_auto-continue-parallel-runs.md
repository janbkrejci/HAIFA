# Plán: auto-continue a bezpečné paralelní běhy (D10, Q9)

## Cíl

Po úspěšném běhu tasku (workflow splnil `accept` a PR byl vytvořen) HAIFA sama spustí další připravený
task, nejdřív ze stejného stepu, pak ze stejného modulu, v pořadí backlogu. Task, jehož závislost leží
jen v otevřeném (nemergnutém) PR, se přeskočí (Q9: „počkat na schválení a mezitím spustit, co jde“).
Když už nic spustit nejde, řetěz skončí a vypíše, na co čeká. Selhání běhu řetěz zastaví.
Dva procesy `task run` na různé tasky běží současně bez kolize, na týž task jeden skončí chybou
`already_running`. Zámek je transakce v trace DB (už existuje `TaskRunStore.claim` s `BEGIN IMMEDIATE`).

Mimo rozsah: plánovač napříč moduly, limit paralelity, web, automatické čekání na schválení
(řetěz nepolluje, jen skončí s výpisem). Auto-continue **nikdy** nevolá `approve`/`merge`.
`vendor/` se nemění. Testy nevolají model (falešné harnessy z `tests/workflow_fakes.py`).

## Kontext, který už existuje (nezkoumej znovu)

- `prototype/src/haifa_proto/run.py`: `run_task()` → `_run()`. Načte backlog z `base` do tempdiru
  (`load_base_backlog`), zkontroluje `store.running`, `unmet` (bez `--force`), pak
  `store.claim(row)` (atomicky v `BEGIN IMMEDIATE`, s `_reap` mrtvých pidů), vytvoří worktree
  (`ensure_excluded`, `git worktree add -b`), spustí workflow s `os.chdir(worktree)`, `publish()`
  vytvoří PR a zapíše `task_prs`. `TaskRunResult.ok` = `SUCCEEDED and pr_error is None`.
  `TaskRunStore.open_pr(task_id)` vrací otevřený PR tasku.
- `backlog.py`: `INHERITED_KEYS` už obsahuje `auto_continue` (dědí se z `index.md` modulu/stepu přes
  `effective(task)`). `ancestors(task)` = rodiče od nejbližšího k top-level (poslední = modul).
  `descendant_tasks(container)` = tasky seřazené podle `path` (= pořadí backlogu). `unmet(backlog, task)`
  vrací `Unmet(id, reason, missing)`; pro kontejnerovou závislost `missing` = nedokončené tasky.
- `review.py`: `approve_task` commitne `status: done` na PR větev a merguje do `base`.
- `cli.py`: `task run <id> [--note] [--force] [--json]` → `_task_run` → `run.run_task`, výstup
  `_run_output`. Stávající testy monkeypatchují `haifa_proto.run.run_task` přes
  `functools.partial(run.run_task, cfg=engine_env.cfg)` a volají `main([...])` — to musí fungovat dál.
- Testy: `tests/task_repo.py::make_task_repo` (T01, T02 závisí na T01, NO_WRITES v S02),
  `add_bare_remote`, `writer`; `tests/workflow_fakes.py` (`EngineEnv`, `Script.add/on`, `ok`);
  vzor e2e s providerem `local`: `tests/test_pr_flow_local.py`.

## Návrh

### 1. Nový modul `prototype/src/haifa_proto/queue.py`

Čistá logika výběru + smyčka řetězu.

```python
@dataclass
class Skip:
    task_id: str
    reason: str          # "waits_on_pr" | "blocked" | "in_review" | "running" | "cannot_start"
    detail: str          # lidsky čitelné: např. "M01-S01-T01 (PR /path/remote.git#factory/M01-S01-T01-1)"
    waits_on: list[str] = field(default_factory=list)   # id tasků, na které čeká
    def to_json(self) -> dict[str, object]: ...

@dataclass
class Selection:
    next: Task | None
    skipped: list[Skip]

def auto_continue_enabled(task: Task) -> bool:
    return effective(task).get("auto_continue") is True

def candidates(backlog: Backlog, after: Task) -> list[Task]:
    """Tasky stejného stepu (after.parent) v pořadí backlogu, pak zbytek modulu
    (ancestors(after)[-1]) v pořadí backlogu; bez duplicit, bez `after`,
    jen status == "todo". Když after.parent je sám modul, obě části splývají."""

def select_next(
    backlog: Backlog,
    after: Task,
    *,
    open_pr: Callable[[str], TaskPrRow | None],
    running: Callable[[str], TaskRunRow | None],
    exclude: set[str] = frozenset(),
) -> Selection:
```

Pravidla `select_next` pro každého kandidáta v pořadí (první spustitelný = `next`, ostatní před ním
i po něm se zaznamenají do `skipped`, aby výpis na konci řekl, na co se čeká — tj. projdi **všechny**
kandidáty, `next` je první vyhovující):

1. id v `exclude` → přeskoč bez záznamu (už v tomto řetězu zkoušen).
2. `running(id)` není None → `Skip(reason="running")`.
3. `open_pr(id)` není None → `Skip(reason="in_review", detail=URL PR)` (task už čeká na review;
   znovu ho nespouštěj).
4. `unmet(backlog, task)`: pro každé `Unmet` rozviň na seznam „chybějících tasků“
   (`missing` pro kontejner, jinak `[u.id]`). Pokud je `u.reason in ("unknown","cancelled","empty")`,
   nebo některý chybějící task nemá `open_pr` → `Skip(reason="blocked", waits_on=…)`.
   Jinak (všechny chybějící tasky mají otevřený PR) → `Skip(reason="waits_on_pr", waits_on=…,
   detail="<dep> (PR <url>)")`.
5. Jinak je task spustitelný.

`select_next` nesahá na git ani DB, dostává callbacky → jednoduše unit-testovatelné.

Smyčka řetězu:

```python
STOP_FAILED, STOP_EXHAUSTED, STOP_DISABLED = "failed", "exhausted", "disabled"

@dataclass
class ChainResult:
    runs: list[TaskRunResult]
    stop: str                    # jedna z konstant výše
    waiting: list[Skip]          # poslední výběr: na co řetěz čeká (prázdné u "failed"/"disabled")
    @property
    def ok(self) -> bool: return all(r.ok for r in self.runs)
    def to_json(self) -> dict[str, object]: ...

def run_chain(repo, task_id, *, auto=False, note=None, force=False,
              cfg=None, code=None, provider=None) -> ChainResult:
```

Algoritmus `run_chain`:

1. `first = run.run_task(repo, task_id, note=note, force=force, cfg=cfg, code=code, provider=provider)`
   — volat přes atribut modulu (`from haifa_proto import run` … `run.run_task(...)`), aby monkeypatch
   v CLI testech zasáhl i pokračování. `TaskRunError` prvního startu propaguj beze změny.
2. `runs=[first]`, `exclude={task_id}`. Smyčka:
   - Poslední výsledek `last`: když `not last.ok or last.pr is None` → `stop=STOP_FAILED`, konec.
   - Načti `root = run.main_root(repo)`, `config = load_config(root)`, `base_sha`
     (`git rev-parse <base>^{commit}`) a base backlog přes `run.load_base_backlog` do
     `tempfile.TemporaryDirectory`. Najdi `after = backlog.by_id[last.run.task_id]` (Task).
   - Když `not (auto or auto_continue_enabled(after))` → `stop=STOP_DISABLED`, konec
     (bez `--auto` a bez `auto_continue` je chování přesně jako dnes: jeden běh).
   - Otevři `TaskRunStore(first.trace_db)` (viz bod 2 níže – cesta k DB z výsledku, ne znovu z cfg)
     a zavolej `select_next(backlog, after, open_pr=store.open_pr, running=store.running,
     exclude=exclude)`; store zavři.
   - `next is None` → `stop=STOP_EXHAUSTED`, `waiting=selection.skipped`, konec.
   - Jinak `exclude.add(next.id)` a `run.run_task(repo, next.id, cfg=cfg, code=code,
     provider=provider)` (bez `note`, bez `force`). Pokud vyhodí `TaskRunError` (závod s jiným
     procesem: `already_running`, `unmet_dependencies`; nebo `no_writes`, `no_workflow` …), zapiš
     `Skip(next.id, "cannot_start", f"{code}: {message}")` do seznamu `start_skips` a pokračuj
     výběrem dalšího kandidáta (start, který nic nespustil, není „selhání běhu“). Tyto skipy připoj
     k `waiting` při `STOP_EXHAUSTED`.
   - Úspěšný start → `runs.append(result)` a opakuj.
3. Nikde nevolat `review.approve_task` ani provider `approve/merge`.

Pozn.: pravidlo „pokračovat?“ se vyhodnocuje po každém úspěšném běhu z `after` (právě dokončeného
tasku): `--auto` platí pro celý řetěz; jinak rozhoduje `auto_continue` zděděný k dokončenému tasku.
Tedy `auto_continue: true` jen na stepu S01 → po posledním tasku z S01 se ještě spustí task z jiného
stepu modulu, ale po něm (step bez `auto_continue`) řetěz skončí se `stop="disabled"`. Zapiš to do
docstringu modulu.

### 2. Úpravy `run.py`

- `TaskRunResult`: přidej pole `trace_db: Path | None = None`; v `_run` nastav
  `result.trace_db = store.db_path` (před `return`). Řetěz tak používá stejnou DB jako běh, i když
  CLI test předá `cfg` jen přes `functools.partial` na `run_task`.
- Serializace sdílených operací v hlavním checkoutu (bezpečný paralelismus různých tasků):
  přidej do `TaskRunStore` context manager `serialized()`, který jen drží `self._txn()`
  (`BEGIN IMMEDIATE` … `COMMIT`) — zámek v trace DB, ne v souboru. V `_run` obal jím blok
  `ensure_excluded(...)` + `worktree.parent.mkdir(...)` + `git worktree add ...` (krátká operace;
  `busy_timeout=5000` stačí). Odstraní to závod v read-modify-write `.git/info/exclude` a souběžné
  `git worktree add` nad společným `.git`. Chybová větev (`store.finish(..., FAILED ...)`) musí běžet
  **mimo** tuto transakci (jinak by `finish` psal uvnitř rollbacku) — tzn. `try: with store.serialized(): …
  except (RuntimeError, OSError): store.finish(...); raise TaskRunError(...)`.
- `next_branch` se počítá před `claim`; pro různé tasky nekoliduje, pro týž task druhý proces spadne
  na `claim` (`already_running`) ještě před vytvořením větve — beze změny, jen ověř testem.
- Aktualizuj docstring modulu: zmínka o `serialized()` a o tom, že souběžné běhy různých tasků jsou
  podporované.

### 3. CLI (`cli.py`)

- `task run` dostane `--auto` (`action="store_true"`, help: „po úspěšném běhu spustit další
  připravený task ve stejném stepu/modulu (auto-continue)“).
- `_task_run(repo, task_id, note, force, auto, as_json)` volá `queue.run_chain(repo, task_id,
  note=note, force=force, auto=auto)`; `TaskRunError` → `_task_error` jako dnes.
- Výstup:
  - text: pro každý běh stávající řádky (`run … : branch …, worktree …`, `pr …`, chyby na stderr —
    vytáhni tělo `_run_output` do pomocné funkce `_print_run(result)`). Pokud řetěz spustil víc než
    jeden běh nebo `stop != "disabled"`, na konec: `auto-continue: stopped (<stop>)` a pro každý
    `Skip` řádek `waiting: <task_id> <reason>: <detail>`; při `exhausted` a prázdném `waiting`
    `auto-continue: nothing left to run`.
  - `--json`: zachovej stávající top-level klíče `ok`, `run`, `pr`, `pr_error` popisující **první**
    běh (kompatibilita s testy), `ok` = `chain.ok`, a přidej `"chain": {"runs": [{run, pr, pr_error, ok}…],
    "stop": ..., "waiting": [Skip.to_json()…]}`.
  - Exit code: `0` iff `chain.ok` (žádný běh v řetězu neselhal), jinak `1`.
- `main()`: předej `args.auto`.
- Stávající testy (`test_cli_task.py`, `test_task_run.py::test_second_run_of_running_task_fails`)
  monkeypatchují `haifa_proto.run.run_task`; díky volání přes atribut modulu v `queue.run_chain`
  fungují dál. Zkontroluj, že v `run_chain` s `auto=False` a bez `auto_continue` se po prvním běhu
  nenačítá nic, co by v těchto testech padalo — načtení base backlogu je OK; pokud první běh
  selže, skonči hned (`STOP_FAILED`) bez načítání.

### 4. Testy

Nový soubor `prototype/tests/test_auto_continue.py`. Fixture: `make_task_repo(engine_env)` +
`add_bare_remote` (provider `local`, výchozí config), pak přepiš backlog pomocným builderem a
commitni (`git add -A && git commit`). Každý builder krok skriptuj přes
`env.script.add("builder", ok(summary=…, changed_files=[…], commit_message=…))` +
`env.script.on("builder", writer({…}))` — jeden pár na každý očekávaný běh, v pořadí běhů. Soubory
zapisuj jen do `writes` daného tasku (step S01 má `writes: [src/app/]`, takže nezávislé tasky
v S01 mohou psát `src/app/<jméno>.py`).

Pomocný backlog pro auto-continue (vytvoř v testu, přepiš soubory v `backlog/M01-core/S01-app/`):
- `M01-S01-T01` (todo), `M01-S01-T02` (todo, **bez** závislosti), `M01-S01-T03` (todo) — nezávislé;
- varianta se závislostí: T01, T02 `depends_on: [T01]`, T03 nezávislý.
- S02 v `make_task_repo` obsahuje `NO_WRITES` bez `writes` → při řetězu přes modul skončí jako
  `cannot_start: no_writes`; buď S02 v testech smaž, nebo to explicitně assertuj (doporučeno smazat
  v testech 1–3 a mít jeden test, který `cannot_start` ověří).

Testy (všechny bez modelu, `cfg=env.cfg`):

1. `test_three_independent_tasks_run_in_order` — `auto_continue: true` v `S01-app/index.md`;
   `run_chain(repo, T01, cfg=env.cfg)` → 3 běhy v pořadí T01, T02, T03, všechny `ok`, každý má PR
   (`store.open_pr`), `stop == "exhausted"`, `waiting == []`. `main` beze změny (nic se
   nemergovalo), task soubory na `main` stále `status: todo`.
2. `test_auto_flag_without_index_setting` — bez `auto_continue`; `run_chain(..., auto=False)` →
   jeden běh, `stop == "disabled"`; s `auto=True` (nový repo/fixture nebo další tasky) → pokračuje.
   Plus CLI: `main(["task","run",T01,"--repo",…,"--auto","--json"])` s monkeypatch
   `run.run_task = partial(run.run_task, cfg=env.cfg)`, ověř `data["chain"]["runs"]` délku a
   exit 0.
3. `test_dependent_task_skipped_until_approve` — T02 `depends_on: [T01]`, `auto=True`:
   řetěz spustí T01, přeskočí T02, spustí T03; `stop == "exhausted"`, `waiting` obsahuje
   `Skip(T02, "waits_on_pr", waits_on=[T01])` s URL PR T01 v `detail`. `run_task(repo, T02)` bez
   force → `TaskRunError("unmet_dependencies")`. Pak `approve_task(repo, T01, cfg=env.cfg)` (volá
   test, ne řetěz) a `run_chain(repo, T02, cfg=env.cfg, auto=True)` → T02 proběhne `ok`; další
   výběr: T01 done, T03 `in_review` → `stop == "exhausted"`, `waiting` = `[T03 in_review]`.
   Ověř také, že řetěz sám nezměnil `main` před approve (`git rev-parse main` stejné).
4. `test_failure_stops_chain` — tři nezávislé, `auto=True`; druhý builder zapíše soubor mimo
   `writes` (např. `README.md`) → T02 selže (scope) nebo vrať envelope, po kterém `accept` nesplní;
   `len(runs) == 2`, `runs[1].ok is False`, `stop == "failed"`, T03 se nespustil (žádný řádek v
   `task_runs` pro T03), CLI exit 1.
5. `test_blocked_dependency_reported` (volitelné, levné) — unit test `select_next` s ručně
   postaveným backlogem/callbacky: závislost ne-done bez PR → `blocked`; s PR → `waits_on_pr`;
   vlastní PR → `in_review`; `running` → `running`; pořadí step → modul.
6. `test_parallel_runs_of_different_tasks` — souběh přes `multiprocessing.get_context("fork")`
   (děti zdědí monkeypatchované falešné harnessy i `env.cfg`; v rodiči před forkem **nespouštěj
   žádný běh**, aby se nedědila otevřená sqlite spojení). Dva procesy: T01 a T03 (nezávislé,
   `auto=False`). Cílová funkce dítěte si sama naskriptuje builder (`env.script.add/on`) pro svůj
   task, v efektu builderu zavolá `barrier.wait(timeout=30)` (`ctx.Barrier(2)`) — tím se dokáže,
   že oba běhy byly uvnitř workflow současně — pak `run.run_task(repo, tid, cfg=env.cfg)` a pošle
   do `ctx.Queue` `(tid, result.ok, result.run.state)` nebo `(tid, "error", code)`. Rodič `join`
   s timeoutem (60 s), assert oba `ok`, oba mají PR a vlastní větev/worktree, v `task_runs` dva
   řádky `succeeded`. Na platformě bez `fork` (`"fork" not in multiprocessing.get_all_start_methods()`)
   `pytest.skip`.
7. `test_concurrent_start_of_same_task_one_refused` — dva forkované procesy na T01 odstartují
   současně (`ctx.Barrier(2)` těsně před `run_task`). Vítěz (ten, jehož builder efekt běží) v
   efektu nastaví `inside` event a čeká na `loser_done` event (timeout 30 s), aby poražený nezačal až
   po jeho dokončení. Poražený dostane `TaskRunError` s `code == "already_running"`, pošle ho do
   fronty a nastaví `loser_done`. (Protože nevíš předem, kdo vyhraje, obě děti dostanou stejný
   skript a efekt; poražený efekt nikdy nespustí.) Assert: přesně jeden `ok`, přesně jeden
   `already_running`, v `task_runs` pro T01 právě jeden řádek, jedna větev `factory/M01-S01-T01-1`.

Existující testy musí projít beze změny chování.

## Soubory

- nový: `prototype/src/haifa_proto/queue.py`
- upravit: `prototype/src/haifa_proto/run.py` (`TaskRunResult.trace_db`, `TaskRunStore.serialized`,
  obalení vytvoření worktree, docstring)
- upravit: `prototype/src/haifa_proto/cli.py` (`--auto`, `_task_run` → `run_chain`, výstup řetězu)
- nový: `prototype/tests/test_auto_continue.py` (+ případně malé pomocníky do `tests/task_repo.py`,
  např. `write_task(repo, step_dir, id, title, depends_on=None, writes=None)` a `commit_all(repo)`)
- nikdy: `vendor/`

## Ověření

Z adresáře `prototype/`:

```
uv run pytest -q
uv run pytest -q tests/test_auto_continue.py
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src   # pokud je v projektu nakonfigurován (viz pyproject.toml)
```

Úspěch = nulový exit status všech příkazů. Ručně (volitelně): v testovacím repu
`haifa-proto task run M01-S01-T01 --auto` vypíše běhy a `auto-continue: stopped (exhausted)` +
řádky `waiting:`.
