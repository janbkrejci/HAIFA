# HAIFA-S03-T16: Auto-continue: souběžné běhy s limitem a bez kolize zápisových cest

## Cíl

`run_chain` (`aifactory/src/aifactory/run/queue.py`) dnes spouští tasky jeden po druhém. Nově:

- konfigurace `max_parallel_runs` (výchozí 1) určuje, kolik běhů řetěz drží naráz;
- při hodnotě > 1 řetěz plní volné sloty dalšími připravenými tasky a po každém doběhnutém běhu doplní další;
- task se spustí souběžně jen tehdy, když se jeho efektivní `writes` nepřekrývají (prefixem cesty) s `writes` běžících běhů ani se soubory otevřených, nesloučených PR. Jinak ho řetěz přeskočí s důvodem `writes_overlap` a zkusí další;
- task se „širokými“ `writes` (celé repo nebo celý balíček, např. HAIFA `aifactory/`) běží jen samostatně, s ničím souběžně. Řetěz to uvede v přehledu;
- stav řetězu (běhy, volné sloty, přeskočené tasky s důvodem) se ukládá do trace DB a dashboard ho ukazuje. `max_parallel_runs` jde nastavit v Nastavení;
- `max_parallel_runs: 1` se chová **přesně jako dnes**: stejná cesta kódu, žádné kontroly překryvu.

Mimo rozsah: automatické zúžení `writes`, plánovač napříč projekty.
Pevná omezení: neměnit `vendor/` ani `prototype/`. Testy nevolají model ani síť. Měnit jen `aifactory/`, `justfile` a dva soubory úlohy (spec a `app_docs/HAIFA-S03-T16-auto-continue-soubezne-behy-s-limitem-a.md`).

## Klíčová zjištění z průzkumu (musíš respektovat)

1. **`run_task` není bezpečné spouštět ve více vláknech jednoho procesu.** Dělá `os.chdir(worktree)`, nastavuje `os.environ[basemoves.RUN_ENV]` a engine (`engine/git_helper.py`) závisí na cwd procesu. Signály se navíc obsluhují pod globálním `_SIGNAL_LOCK`. Souběžné běhy proto musí být **samostatné procesy**, stejně jako je spouští dashboard (`web/launcher.py`: `python -m aifactory task run ID --repo ROOT --json`, `start_new_session`). Současný souběh procesů už testuje `tests/run/test_parallel_runs.py`.
2. `TaskRunStore` (`run/store.py`):
   - poskytuje `live_runs()` (všechny `running` řádky, mrtvé pid reapuje), `open_prs()` (všechny otevřené PR), `claim`, `get`, `pr_for_branch` a `serialized()` (flock plus RLock, funguje napříč procesy);
   - nové tabulky se přidávají do `_SCHEMA` (`CREATE TABLE IF NOT EXISTS`);
   - sqlite spojení je jedno na vlákno (`check_same_thread`).
3. Provider nemá metodu „změněné soubory PR“. Lokálně je spočítá vzor z `web/review.py::_diff`: `git merge-base refs/heads/<base> refs/heads/<branch>` a pak `git diff --name-only -z <mb> refs/heads/<branch>` v hlavním checkoutu (`gitops.main_root`).
4. `try_auto_merge` potřebuje `result.workflow_run` (poslední review). Ten existuje jen v procesu, který běh provedl. **Auto-merge souběžného běhu proto dělá samotný podřízený proces**, ne rodič (viz níže).
5. HAIFA `backlog/HAIFA/index.md` dědí `writes: [aifactory/, justfile]` a `auto_merge: true`. Každý HAIFA task je tedy „široký“ a i při `max_parallel_runs > 1` poběží samostatně. To je očekávané a dokumentuj to.
6. Postavený frontend (`aifactory/src/aifactory/web/static/assets/*`) je commitnutý. Po změně frontendu spusť `just web-build`, nové hashované soubory nech v pracovním stromu a staré smaž. Build dělá vite sám, protože `outDir` míří do `static`.

## Návrh

### 1. Konfigurace: `aifactory/src/aifactory/config/settings.py`

Do `ProjectSettings` přidej vedle `test_slots`:
```python
# how many task runs one auto-continue chain keeps running at once (1 = one after another)
max_parallel_runs: int = Field(default=1, ge=1, strict=True)
```
Do `skill/skill.md` přidej do sekce auto-continue odstavec o `max_parallel_runs`, o pravidle `writes_overlap` a `exclusive`. Klíč v seznamu `{{settings_keys}}` se doplní sám.

### 2. Překryv cest: `aifactory/src/aifactory/run/scope.py`

Přidej čisté funkce bez I/O (kromě volitelného `root`):

- `literal_prefix(pattern: str) -> str`:
  1. `normalize`;
  2. když obsahuje `*`, `?` nebo `[`, uřízni od prvního takového znaku a pak zpět k poslednímu `/`;
  3. odstraň koncové `/`; `"."` se mapuje na `""`.

  Příklady: `src/app/` → `src/app`, `src/**/x.py` → `src`, `**` → `""`, `justfile` → `justfile`.
- `paths_overlap(a: str, b: str) -> bool`: `pa, pb = literal_prefix(a), literal_prefix(b)`. Překryv nastane, když platí kterákoli z podmínek:
  - jeden z prefixů je prázdný;
  - `pa == pb`;
  - `pa.startswith(pb + "/")`;
  - `pb.startswith(pa + "/")`.

  Funkce je konzervativní a stejně ji použij pro pattern×pattern i pattern×soubor.
- `overlaps(writes: Iterable[str], paths: Iterable[str]) -> list[str]`: seřazený seznam položek z `paths`, které se překrývají s některou z `writes`. Použije se do textu důvodu.
- `is_wide(writes: Iterable[str], root: Path | None = None) -> list[str]`: vrací ty `writes`, které pokrývají celé repo nebo balíček. Prázdný seznam znamená „není široký“. Pattern je široký, když:
  - `literal_prefix` je prázdný (repo), **nebo**
  - prefix má jediný segment (bez `/`) a jde o adresář. Adresář poznáš tak, že pattern končí `/`, nebo obsahuje wildcard za segmentem, nebo `root / prefix` je existující adresář.

  Příklady: `aifactory/` je široký, `src/` je široký, `justfile` sám široký není, `src/app/` není, `**` je.
- `effective_task_writes(task: Task) -> tuple[str, ...]` vrací `tuple(normalize(w) for w in effective_writes(task) if w.strip())`. Ať ji používá i `task_scope`, aby byla definice na jednom místě. Výstupy spec/doc se do překryvu **nepočítají**, protože jsou per-task unikátní.

### 3. Změněné soubory PR: `aifactory/src/aifactory/run/gitops.py`

`pr_changed_files(main: Path, base: str, branch: str, base_sha: str | None = None) -> list[str] | None`:
- spočítá merge-base `refs/heads/<base>` a `refs/heads/<branch>`; když `refs/heads/<base>` chybí, použije `base_sha`;
- potom `git diff --name-only -z <mb> refs/heads/<branch>`;
- při jakékoli chybě gitu (chybějící větev apod.) vrátí `None`, nikdy nevyhazuje.

### 4. Výběr: `aifactory/src/aifactory/run/queue.py`

- `SKIP_REASONS` rozšiř o `"writes_overlap"` a `"exclusive"`. Skill render je převezme automaticky, zkontroluj `tests/test_skill.py`.
- `select_next(...)` dostane nový volitelný parametr `conflict: Callable[[Task], Skip | None] | None = None`. Volá se **až po** všech dnešních kontrolách (no_workflow, running, in_review, blocked/waits_on_pr), jen pro jinak spustitelné kandidáty:
  - když vrátí `Skip`, přidá se do `skipped` a pokračuje se dalším kandidátem;
  - s `conflict=None` je chování beze změny, takže existující `test_select_next_rules` musí projít.
- Nová třída `Occupancy` (v `queue.py` nebo novém `run/occupancy.py`) se staví na začátku každého kola výběru a slouží jako `conflict`:
  - `runs: list[tuple[TaskRunRow, tuple[str, ...]]]`: všechny `store.live_runs()` (i běhy mimo tento řetěz, např. ruční z dashboardu). K nim `writes` přes `effective_task_writes(backlog.by_id[row.task_id])`. Když task v backlogu není, ber běh jako široký (`writes=("",)`).
  - `prs: list[tuple[TaskPrRow, list[str]]]`: všechny `store.open_prs()` a jejich soubory přes `gitops.pr_changed_files(main, pr.base, pr.branch, pr.base_sha)`. Když vrátí `None`, použij `effective_task_writes` tasku PR z backlogu. Když ani to nejde, `("",)` (konzervativně všechno), v detailu napiš „soubory PR nelze zjistit“. Soubory počítej jednou za kolo, ne pro každého kandidáta.
  - `root` = hlavní checkout (pro `is_wide`).
  - `__call__(task) -> Skip | None` postupuje takto:
    1. `w = effective_task_writes(task)`.
    2. Když `is_wide(w, root)` a existuje jakýkoli běžící běh: `Skip(task.id, "exclusive", "writes <wide…> pokrývají celý balíček/repo; běží jen samostatně (běží: <task_id run_id>, …)")`.
    3. Když některý běžící běh je široký: `Skip(task.id, "exclusive", "běží <task_id> (<run_id>) se širokými writes <…>; souběžně nic jiného")`.
    4. Pro každý běžící běh, kde `overlaps(w, run_writes)` není prázdné: `Skip(task.id, "writes_overlap", "běh <run_id> (<task_id>): <cesty>")`.
    5. Pro každý otevřený PR, kde `overlaps(w, pr_files)` není prázdné: `Skip(..., "writes_overlap", "PR <url> (<task_id>): <cesty, max 5 + „…“>")`.
    6. Detaily více kolizí spoj `"; "`. Do `waits_on` dej task_id kolidujících běhů a PR.
- Kontrola otevřených PR se týká **všech** otevřených PR v repu, včetně PR tasků tohoto řetězu, které už doběhly a nebyly sloučeny.

### 5. Řetěz: `run_chain`

Signatura (zpětně kompatibilní):
```python
def run_chain(repo, task_id, *, auto=False, note=None, force=False, code=None, provider=None,
              max_parallel: int | None = None, runner: ChainRunner | None = None,
              pr_files: Callable[[TaskPrRow], list[str] | None] | None = None) -> ChainResult
```
- `max_parallel`: když je `None`, čti `task_mod._load(gitops.main_root(repo)).config.settings.max_parallel_runs`.
- **`max_parallel == 1`**: dnešní smyčka beze změny chování. Přesuň ji do `_run_sequential(...)`, logiku nech nedotčenou. Jediný doplněk je zápis stavu řetězu do store (viz bod 6), selhání zápisu nesmí běh ovlivnit.
- **`max_parallel > 1`**: `_run_parallel(...)` probíhá takto:
  1. Řetěz založí řádek `task_chains`.
  2. `runner.start(task_id, note=note, force=force)` spustí první task. `TaskRunError` z prvního startu propaguje (jako dnes) a řádek řetězu se smaže.
  3. `cont0 = auto or auto_continue_enabled(first_task)` (z base backlogu). Když platí, hned doplní sloty: `_fill(after=first_task)`.
  4. `_fill(after)`:
     - dokud `len(active) < max_parallel` a řetěz není zastavený: načte čerstvý `_base_backlog`, postaví `Occupancy` a zavolá `select_next(backlog, after, open_pr=…, running=…, exclude=started_ids, conflict=occupancy)`;
     - když `next is None`, uloží `selection.skipped` jako aktuální „waiting“ a skončí;
     - jinak `runner.start(next.id)`. `TaskRunError` se stane `Skip(next.id, "cannot_start", …)`, id se přidá do `exclude` a pokračuje se.
     - `start` čeká, až je běh **claimnutý** v `task_runs`, takže další `Occupancy` ho už vidí.
  5. Hlavní smyčka: dokud je něco aktivní, `result = runner.wait_any()`, výsledek přidá do `runs` (pořadí dokončení; `runs[0]` musí zůstat první task, viz níže), pak se rozhodne:
     - `not result.ok or result.pr is None` → `halt = STOP_FAILED` (už nic nespouštět, aktivní běhy nechat doběhnout, nezabíjet).
     - `cont = auto or auto_continue_enabled(after)`, kde `after` je task z čerstvého base backlogu.
     - Když `auto_merge_enabled(after)` a `result.auto_merge` je `None` nebo `merged == False`: `halt = STOP_NOT_MERGED if cont else STOP_DISABLED` (stejná sémantika jako dnes; merge provedl podřízený proces).
     - Když `not cont`, tento doběhnutý běh nedoplňuje (pamatuj si `last_disabled = True`).
     - Jinak `_fill(after)`.
  6. Konec: když nic není aktivní, stop se určí takto:
     - je-li nastaven `halt` (první zastavení vyhrává), stop je `halt`;
     - jinak když poslední doběhnutý běh neměl `cont`, stop je `STOP_DISABLED`;
     - jinak `STOP_EXHAUSTED`, a `waiting` = skipy posledního výběru plus `cannot_start` skipy.
- `ChainResult` dostane:
  - `max_parallel: int = 1`;
  - `exclusive: list[str]` = id tasků, které běžely samostatně kvůli širokým `writes` (včetně prvního, pokud je široký);
  - `chain_id: str | None`.

  `to_json` je přidá (`max_parallel_runs`, `exclusive`, `chain_id`). `runs` drž v pořadí **startu**, aby `runs[0]` byl první task (CLI z něj staví envelope).

### 6. Podřízené procesy: `ChainRunner` (nový `aifactory/src/aifactory/run/members.py`)

```python
class ChainRunner(Protocol):
    def start(self, task_id: str, *, note: str | None = None, force: bool = False) -> TaskRunRow: ...
    def wait_any(self) -> TaskRunResult: ...
    def active(self) -> list[str]: ...  # task ids
```
`ProcessRunner(repo, code=None, provider=None, command: Sequence[str] | None = None)` je výchozí implementace.

**`start`** spustí `[*prefix, "task", "run", ID, "--repo", ROOT, "--json", "--member", (--note=…), (--force)]`:
- prefix je `aifactory.web.launcher.command_prefix()`. Ať nevzniká import web → run, přesuň `command_prefix`/`set_command_prefix`/`DEFAULT_COMMAND`, `_parse_envelope`, `_tail` a `_launch_error` do `run/members.py` (nebo `run/process.py`) a `web/launcher.py` je reexportuje a importuje odtud, API launcheru se nemění.
- Spouští se s `start_new_session=True`, cwd=ROOT, stdout/stderr do souborů v `home.logs_dir()` přes `home.create_private` (jako launcher).
- Čeká na claim: nový řádek `task_runs_for(repo, task_id)`, který předtím neexistoval.
- Když proces skončí před claimem, vyhodí `TaskRunError` z envelope.
- `code`/`provider` se do procesů nepředávají. Zdokumentuj, že platí jen pro sekvenční režim.

**`wait_any`** polluje `Popen.poll()` aktivních procesů (interval ~0.2 s). Po skončení procesu:
- přečte envelope (`data.run.run_id`, `pr_error`, `auto_merge`);
- načte `TaskRunRow` přes store `get(run_id)` a PR přes `pr_for_branch(row.branch)`;
- postaví `TaskRunResult(run=row, workflow_run=None, warnings=tuple(envelope warnings), trace_db=…, pr=pr, pr_error=…, auto_merge=AutoMergeResult z JSON)`. Do `review/automerge.py` přidej `AutoMergeResult.from_json`, pokud chybí.
- Při nečitelném envelope použije stav řádku a `pr_error=None`. Když řádek chybí, vznikne syntetický failed výsledek s chybou z tailu logu.

**CLI `--member`** (v `cli.py` u `task run`, `help=argparse.SUPPRESS`): spustí `run_task(...)` místo `run_chain`. Když je `auto_merge_enabled(task)` (task z base backlogu, `_base_backlog`), zavolá `try_auto_merge` **pod mezi-procesním zámkem** `<trace_db>.merge.lock`, vytvořeným přes `_PathLock` ze store (přidej např. `TaskRunStore.merge_lock()`, nebo veřejný helper v store). Souběžné merge do `main` tak jdou jeden po druhém. Vypíše `_run_json(result)` stejným `_emit_runs` jako dnes. Nikdy nespouští další tasky.

**Testovací double** `FakeRunner` patří do testů (viz Testy), ne do `src`.

### 7. Stav řetězu v trace DB: `run/store.py`

Nová tabulka v `_SCHEMA`:
```sql
CREATE TABLE IF NOT EXISTS task_chains (
  chain_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, pid INTEGER, max_parallel INTEGER NOT NULL,
  state TEXT NOT NULL,            -- running | finished | aborted
  stop TEXT, started_at TEXT NOT NULL, updated_at TEXT NOT NULL, ended_at TEXT,
  run_ids TEXT NOT NULL DEFAULT '[]',     -- JSON, v pořadí startu
  skipped TEXT NOT NULL DEFAULT '[]',     -- JSON list Skip.to_json() posledního výběru (+ cannot_start)
  exclusive TEXT NOT NULL DEFAULT '[]'    -- JSON list task id
);
```
- Dataclass `TaskChainRow` s `to_json()`.
- Metody: `start_chain(row)`, `update_chain(chain_id, *, run_ids=None, skipped=None, exclusive=None, state=None, stop=None)` (vždy nastaví `updated_at`), `delete_chain(chain_id)` a `chains(limit=10) -> list[TaskChainRow]` (běžící + nejnovější ukončené).
- `chains` reapuje: řádek `running`, jehož `pid` už neběží, se stane `aborted`. Použij stejnou kontrolu pid jako `live_runs`.
- Řetěz zapisuje stav při: založení, každém startu, každém dokončení, každém výběru (skipped) a konci (`finished` + `stop`).
- `chain_id` = `secrets.token_hex(4)` nebo podle konvence run_id.
- Store otevírej per volání (`TaskRunStore(trace_db)`, `close()` ve `finally`). Zápisy obal tak, aby `sqlite3.Error` nikdy neshodil řetěz (warning na stderr).
- Sekvenční režim zapisuje taky: řádek se založí před prvním `run_task` (trace DB získáš přes `existing_store`; když ještě neexistuje, založ ho až po prvním běhu z `first.trace_db`), na `TaskRunError` prvního běhu se smaže.

### 8. Dashboard: backend

- Nový `aifactory/src/aifactory/web/chains.py`: `list_chains(repo) -> JsonDict`, tedy `{"max_parallel_runs": <z config settings>, "chains": [...]}`. Každý řetěz obsahuje:
  - `chain_id, task_id, state, stop, max_parallel, started_at, updated_at, ended_at`;
  - `runs: [{run_id, task_id, state}]` (stav přes `store.get`);
  - `running` (počet `running`);
  - `free_slots = max(0, max_parallel - running)` jen pro `state == "running"`, jinak 0;
  - `skipped`, `exclusive`.

  Když trace DB neexistuje, vrátí `chains: []`.
- `web/app.py`: přidej `Route("/chains", chains_get, methods=["GET"])` (async přes `run_in_threadpool`) a aktualizuj docstring se seznamem rout.
- `web/settings.py`: přidej `"max_parallel_runs"` do `SHARED_FIELDS`. Validace jde přes `ProjectSettings` (`strict`, `ge=1`), takže `0` a `"2"` dají 422 `invalid_value`.

### 9. Dashboard: frontend (`aifactory/web/src`)

- `lib/settings.ts`:
  - `SharedSettings.max_parallel_runs: number | string`;
  - `SettingsFormValues.max_parallel_runs: string`;
  - `formValues` a `settingsDiff` s numerickou větví podle `port`/`portValue`.
- `components/settings/SettingsForm.vue`: pole „Souběžné běhy auto-continue“ (`data-test="max_parallel_runs"`, `data-test="error-max_parallel_runs"`) ve sdíleném fieldsetu za `test_command`. Nápověda: „Kolik běhů řetěz auto-continue drží naráz (1 = jeden po druhém). Tasky s překrývajícími se writes neběží souběžně.“
- `lib/chains.ts`: typy `ChainSkip`, `Chain`, `ChainsResponse`, `fetchChains()` (podle `fetchRuns` v `lib/runs.ts`) a `skipReasonLabel(reason)` s českými popisky:
  - `writes_overlap` → „překryv writes“;
  - `exclusive` → „jen samostatně“;
  - `waits_on_pr` → „čeká na PR“;
  - `blocked` → „blokováno“;
  - `no_workflow` → „bez workflow“;
  - `in_review` → „v review“;
  - `running` → „běží“;
  - `cannot_start` → „nelze spustit“.
- `components/runs/ChainPanel.vue`: zobrazí se jen když `chains.length > 0`, nad `<RunsList>` v `views/RunsView.vue`. Pro každý řetěz ukáže:
  - hlavičku „Řetěz od <task_id> · <běží|skončil: stop>“;
  - „Sloty: <running>/<max_parallel> (volné <free_slots>)“;
  - seznam běhů (task_id + StatusChip/stav, odkaz na `/runs/<run_id>` stejným způsobem jako RunsList);
  - „Samostatně: …“, pokud `exclusive`;
  - seznam přeskočených: task_id, štítek důvodu, detail.

  Načítá se spolu s `fetchRuns` při resync z `useLive`, tedy při stejném refreshi jako seznam běhů. Chyba načtení řetězů nesmí rozbít seznam běhů.
- Fixtures/testy: `test/settingsFixtures.ts` (`max_parallel_runs: 1`), `lib/settings.test.ts`, `components/settings/SettingsForm.test.ts`, nový `lib/chains.test.ts` (labely), nový `components/runs/ChainPanel.test.ts` (sloty, skipy s důvodem, exclusive) a `views/RunsView*.test.ts` (fetch mock pro `/api/chains`; existující testy musí projít).
  - Dodrž existující lint `noNativeUi.test.ts`: žádné nativní `title`/`select`, použij komponenty z `components/ui`, jak to dělají ostatní.
- Spusť `just web-build` a nech nové assety v `aifactory/src/aifactory/web/static/assets/`; staré `index-*.js/css` smaž (vite je přepíše).

### 10. CLI výpis (`cli.py::_task_run`)

- `data["chain"]` rozšiř o `max_parallel_runs`, `exclusive`, `chain_id`.
- Textový výstup: když `max_parallel > 1`, vypiš `auto-continue: up to N parallel runs`, pro každé `exclusive` `exclusive: <id> ran alone (wide writes)`, a skipy jako dnes (`waiting: <id> <reason>: <detail>`).

## Testy (bez modelu a sítě)

**`aifactory/tests/run/test_scope_overlap.py`** (nový): `literal_prefix`, `paths_overlap` (prefix na hranici `/`: `src/app` vs `src/application` se nepřekrývá; `src/app/` vs `src/app/x.py` ano; `**` vs cokoli ano; glob `src/*/x.py` vs `src/other/`), `overlaps`, `is_wide` (`aifactory/`, `src/`, `**`, `.` jsou široké; `justfile`, `src/app/` nejsou; bare `pkg` existující adresář s `root` je široký).

**`aifactory/tests/run/test_parallel_chain.py`** (nový) s `FakeRunner`:
- staví na `make_run_repo`/`setup_chain`/`_task`/`_index` z `tests/run/test_auto_continue.py` (a `run_repo.py`);
- `FakeRunner.start` zapíše `running` řádek přes store (`claim`), `wait_any` dokončí běhy v pořadí řízeném testem (např. FIFO nebo seznam). Na dokončení nastaví `succeeded` (`store.finish`) a uloží otevřený `TaskPrRow` (`save_pr`). Sleduje maximum současně aktivních. Pro `auto_merge` volitelně vrátí `AutoMergeResult`;
- soubory PR injektuj přes `pr_files=`, ať test nepotřebuje větve;
- `max_parallel` předávej parametrem a jeden test ho čte z committed `.factory/config.yaml`.

Případy:
1. **Limit**: 4 nezávislé tasky s disjunktními `writes` (`src/a/`, `src/b/`, …) a `max_parallel=2` → nikdy víc než 2 aktivní, všechny 4 proběhnou, `stop == "exhausted"`.
2. **Překryv s během**: T01 `src/app/`, T02 `src/app/sub/`, T03 `src/other/`, `max_parallel=3` → T02 je ve skipech `writes_overlap` s detailem obsahujícím run_id/T01 a `src/app/sub`, T03 běží souběžně s T01.
3. **Překryv s otevřeným PR**: předem uložený otevřený PR jiného tasku, `pr_files` vrací `["src/other/x.py"]` → task s `writes: [src/other/]` se přeskočí `writes_overlap` s URL PR a cestou. Task s jinými writes běží.
4. **Doplnění po doběhnutí**: `max_parallel=2`, 3 tasky → po dokončení prvního se spustí třetí (pořadí startů a to, že třetí startuje až po prvním `wait_any`).
5. **Široké writes**: task s `writes: [src/]` (nebo `[aifactory/, justfile]` s adresářem v repu) se nespustí, dokud něco běží (`exclusive`). Když běží široký task, ostatní jsou `exclusive`. `ChainResult.exclusive` ho uvádí.
6. **Selhání**: neúspěšný běh zastaví plnění, aktivní běhy doběhnou, `stop == "failed"`.
7. **`max_parallel_runs: 1` jako dnes**:
   - `run_chain(..., max_parallel=1, runner=ExplodingRunner())` runner nikdy nevolá;
   - s otevřeným PR, který by se překrýval, se nic nepřeskočí kvůli `writes_overlap`;
   - výsledek je shodný s existujícím `test_auto_continue` scénářem.
   - Celý existující `tests/run/test_auto_continue.py`, `test_auto_merge.py` a `test_parallel_runs.py` projde beze změny.
8. `select_next` s `conflict` callable: skip a pokračování na dalšího kandidáta, `conflict` se nevolá pro tasky blokované jinak.

**Store** (`tests/run/test_store*.py` nebo nový test): `task_chains` CRUD, reap mrtvého pid na `aborted`, idempotentní schéma na existující DB.

**`gitops.pr_changed_files`**: reálné git repo v `tmp_path` (větev s commitem měnícím 2 soubory → přesně ty dva). Chybějící větev → `None`.

**CLI `--member`**: na fake harness (`fake_env`) `task run T --member --json` spustí jen jeden task, ani s `auto_continue` nepokračuje. Použij existující vzor CLI testů v `tests/run/` (najdi test `--auto`).

**Web**:
- `tests/web/test_web_settings.py`: GET vrací `max_parallel_runs == 1`; uložení 3; 0 a `"2"` dají 422.
- Nový `tests/web/test_web_chains.py`: prázdné bez DB; řádek řetězu se 2 běhy, `max_parallel=3` → `free_slots == 1`, skipy projdou.

**Config**: `tests/config/test_config_settings.py`: default 1, `0` a `"2"` odmítnuté.

**ProcessRunner**: aspoň unit test parsování envelope a stavby `TaskRunResult` z envelope a store (bez spouštění modelu). Volitelně integrační test přes prefix fake harnessu, jako to dělá `validation.worker`/`set_command_prefix`, ale jen pokud jde snadno a deterministicky.

## Dokumentace

- `app_docs/HAIFA-S03-T16-auto-continue-soubezne-behy-s-limitem-a.md` popíše:
  - `max_parallel_runs`;
  - pravidlo překryvu (prefix cesty, běžící běhy, otevřené PR, fallback při neznámých souborech PR);
  - široké `writes` (definice; HAIFA dnes `aifactory/` + `justfile`, takže HAIFA tasky běží samostatně);
  - procesní model (`--member`, auto-merge v podřízeném procesu pod zámkem);
  - tabulku `task_chains`, `/api/chains` a panel v Běhy;
  - nastavení v Nastavení (zapisuje `.factory/config.yaml`, platí po commitu do base).
- Aktualizuj docstringy `run/queue.py` (modul), `run/__init__.py` (exporty: `ChainRunner`, `ProcessRunner`, nové konstanty) a `web/launcher.py`.

## Ověření

```
just test        # včetně web-test (vue-tsc + vitest)
just typecheck
just lint        # ruff check + ruff format --check
just web-build   # a nechat nové assety v pracovním stromu
```
Všechny tři (`test`, `typecheck`, `lint`) musí projít (exit 0).

## Pořadí práce

1. settings + scope helpery + testy;
2. gitops.pr_changed_files;
3. store `task_chains`;
4. `select_next(conflict)` + `Occupancy`;
5. `run/members.py` + přesun helperů z launcheru + CLI `--member`;
6. `run_chain` rozdělení sekvenční/paralelní + `ChainResult`;
7. testy řetězu;
8. web backend (`/api/chains`, settings);
9. frontend + build;
10. docs, skill.md;
11. `just test typecheck lint`.
