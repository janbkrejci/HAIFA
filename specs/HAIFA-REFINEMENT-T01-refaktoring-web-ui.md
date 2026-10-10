# HAIFA-REFINEMENT-T01: Refaktoring web UI (ergonomie, úklid, řízení výroby)

Plán pro buildera. Všechny cesty jsou relativní ke kořeni worktree. Měnit smíš jen `aifactory/`, tento spec a `app_docs/HAIFA-REFINEMENT-T01-refaktoring-web-ui.md`.
Frontend: `aifactory/web/src` (Vue 3 + TS, vitest, happy-dom). API: `aifactory/src/aifactory/web/` (routy v `app.py`, `_repo_routes()` ~ř. 1247, multi app `create_multi_app` ~ř. 1692). UI texty jsou česky.

## 0. Pořadí práce a pravidla

1. Backend fronta (oddíl 3A) → limity (oddíl 5) → per-run harness (3B) → frontend cesty (oddíly 1–4) → úklid (oddíl 6) → build statiky (oddíl 8).
2. Každá změna chování má test: backend `aifactory/tests/...` (pytest), frontend `*.test.ts` vedle komponenty / v `lib/`.
3. Při odstranění kódu nejdřív `grep -rn` celého `aifactory/` (včetně `tests/` a `tests/e2e/`), odstraň i testy jen toho kódu.
4. Statika `aifactory/src/aifactory/web/static/` je commitovaný build a e2e testy (`aifactory/tests/e2e/*_browser.py`) jedou nad ním. Po změnách frontendu ji přegeneruj `just web-build` (oddíl 8).
5. Nekomituj. Do `app_docs/HAIFA-REFINEMENT-T01-refaktoring-web-ui.md` sepiš (a) co bylo odstraněno a proč, (b) seznam opravených drobných chyb. Tyto dva seznamy jdou do popisu PR. Vyplň je průběžně podle oddílů 6 a 7.

---

## 3A. Řízení výroby: pořadí a vyloučení z auto continue (akceptační kritéria 3 a 4)

### Současný stav
- `aifactory/src/aifactory/run/queue.py`: `candidates(after)` (~ř. 144) vrací `todo` tasky kroku, pak projektu, v pořadí cest (`backlog/derived.py:77 descendant_tasks` řadí podle `t.path`). `select_next(...)` (~ř. 159) má parametr `exclude`. Volají ho `_sequential` (~ř. 548–633, otevírá `TaskRunStore(last.trace_db)` ~ř. 607) a `_run_parallel.fill` (~ř. 683, `TaskRunStore(db)` ~ř. 690).
- Neexistuje žádné pole pořadí ani vyloučení. Kanban `components/backlog/KanbanBoard.vue` nemá drag&drop. Sloupce: `lib/backlog.ts:16 BOARD_STATES`, stav počítá `web/backlog.py:131 board_state`.

### Rozhodnutí: úložiště v trace DB
Pořadí a vyloučení jsou provozní preference operátora, ne obsah tasku. Nesmí vyžadovat commit backlogu, protože běh čte backlog z base. Uložit je do trace DB (`run/store.py`), stejně jako `task_chains`.

1. `run/store.py`: do schématu (`CREATE TABLE IF NOT EXISTS`, starší DB tabulku dostanou při otevření) přidej:
   ```sql
   CREATE TABLE IF NOT EXISTS task_queue (
     task_id TEXT PRIMARY KEY,
     rank INTEGER,            -- NULL = bez ručního pořadí
     excluded INTEGER NOT NULL DEFAULT 0,
     updated_at TEXT NOT NULL
   );
   ```
   Metody na `TaskRunStore` (zápisy v `self._txn()`):
   - `queue_prefs() -> QueuePrefs`, kde `@dataclass(frozen=True) class QueuePrefs: order: tuple[str, ...]` (task_id seřazené podle rank, jen rank není NULL) a `excluded: frozenset[str]`. Když tabulka chybí (`_has_table`), vrať prázdné.
   - `set_queue_order(task_ids: Sequence[str]) -> None`: všem řádkům nastav `rank = NULL`, pak `rank = index` pro předané id (upsert). Duplicitní id → `ValueError`.
   - `set_excluded(task_id: str, excluded: bool) -> None`: upsert.
   - Řádky s `rank IS NULL AND excluded = 0` smaž (úklid).
2. `run/queue.py`:
   - `candidates(after, order: Sequence[str] = ())`: nejdřív kandidáti (todo, ve scope projektu `after`, stejná množina jako dnes) v pořadí `order`, pak zbytek v dnešním pořadí (krok `after`, pak projekt). Ruční pořadí má přednost i před „nejdřív stejný krok“. Tasky z `order` mimo projekt `after` se ignorují.
   - `select_next(..., prefs: QueuePrefs | None = None)`: `order = prefs.order`. Vyloučené (`prefs.excluded`) se nespustí a zapíšou se jako `Skip(task.id, "excluded", "vyloučeno z auto continue v kanbanu")`. Přidej `"excluded"` do `SKIP_REASONS` a do mapování textů skipů ve frontendu (`ChainPanel.vue` / `lib/chains.ts`, kde se mapují důvody). Vyloučení platí i s `--auto`.
   - V `_sequential` i `fill` načti `store.queue_prefs()` při každém výběru (stejný store, ze kterého se čte `open_pr`/`running`) a předej ho do `select_next`.
   - Ruční `factory task run ID` (`run_task`) vyloučení neřeší. Ručně spustit jde dál.
3. Web API (`web/backlog.py` + routy v `app.py` `_repo_routes`):
   - `POST /api/repos/{id}/backlog/queue/order` body `{"order": ["ID", ...]}`. Validace: list neprázdných stringů, existující task id (jinak 422 `unknown_task`). Volá `store.set_queue_order`. Vrací `{"order": [...]}`.
   - `POST /api/repos/{id}/backlog/tasks/{task_id}/auto-exclude` body `{"excluded": bool}`. Vrací `{"task_id", "excluded"}`.
   - Store otevři stejně jako `_runtime` (`existing_store(repo)`). Když trace DB ještě neexistuje, vytvoř ji (`TaskRunStore(rc.local.trace_db_path(main))`, jak to dělá `run_task`).
   - Obě routy musí projít zápisovým guardem `web/guard.py` stejně jako ostatní POST na backlogu. Zkontroluj, jestli guard nepouští jen allowlist cest.
   - `GET /api/backlog`: `_runtime` načte i `queue_prefs()`. `_task_json` přidá `queue_rank: int | null` a `auto_excluded: bool`. `tasks` v odpovědi seřaď: ranked podle rank, pak zbytek v dnešním pořadí. Kanban pak ukazuje stejné pořadí, jaké použije auto continue.
4. Frontend:
   - `lib/backlog.ts`: typ `TaskNode` + `queue_rank`, `auto_excluded`. Funkce `setQueueOrder(order)` a `setAutoExcluded(id, excluded)`.
   - `KanbanBoard.vue`:
     - Ve sloupci „Připraveno“ jde měnit pořadí: HTML5 drag&drop (`draggable`, `dragstart`/`dragover`/`drop`) plus tlačítka ↑/↓ na kartě (přístupnost, testovatelnost; `aria-label="Posunout výš"`/`"Posunout níž"`). Po změně emituj `reorder(ids: string[])` s celým novým pořadím sloupce „Připraveno“.
     - Nový sloupec **„Odloženo“** (`deferred`) hned za „Připraveno“: ready i ostatní todo tasky s `auto_excluded = true`, které ještě neběží, nejsou v review ani hotové. Přetažení karty Připraveno → Odloženo emituje `exclude(id, true)`, opačně `exclude(id, false)`.
     - Na každé kartě ve stavu ready/blocked/todo je přepínač (ikona `lucide` `PauseCircle`/`PlayCircle`, tooltip „Vyloučit z auto continue“ / „Vrátit do auto continue“), emituje `exclude`.
     - Karty mají pořadové číslo fronty (1., 2., …) ve sloupci Připraveno.
     - Pod hlavičkou kanbanu krátký text: „Auto continue bere tasky ze sloupce Připraveno shora dolů. Odložené tasky nespustí, ručně je spustit jde.“
   - `lib/backlog.ts BOARD_STATES`: přidej `deferred: "Odloženo"`. Mapování karty do „Odloženo“ dělej ve frontendu: `board_state` z backendu zůstává, `auto_excluded && board_state in (ready, blocked, todo)` → sloupec deferred. `presentStates` ukáže „Odloženo“ vždy, když je kanban zobrazen (cíl pro drop).
   - `BacklogView.vue`: obsluha `reorder`/`exclude` volá API a znovu načte backlog. Chyba se ukáže stejně jako ostatní chyby view. Optimisticky přeuspořádej lokálně, při chybě vrať.
   - `TaskDetail.vue`: řádek „Auto continue: ve frontě / odloženo“ s tlačítkem přepnutí.
5. Testy:
   - `aifactory/tests/run/test_auto_continue.py`:
     - `select_next` respektuje `order`, i přes hranici kroku.
     - Vyloučený task se přeskočí se skipem `excluded`, i s `--auto` (`require_auto_continue=False`).
     - Sekvenční řetěz (stávající fixture) po nastavení pořadí spustí tasky v tom pořadí.
   - `aifactory/tests/run/test_parallel_chain.py`: `fill` přeskočí vyloučený.
   - Nový `aifactory/tests/run/test_queue_prefs.py`: store CRUD, starší DB bez tabulky, duplicitní id.
   - `aifactory/tests/web/test_web_backlog_queue.py` (nový): obě routy (ok, neznámý task, špatný typ), `GET /api/backlog` vrací `queue_rank`/`auto_excluded` a pořadí. Použij `create_app` jako ostatní `tests/web`.
   - Ruční spuštění vyloučeného tasku přes `POST /backlog/tasks/{id}/run` (launcher fake jako v `tests/web/test_web_task_run.py`) projde.
   - Frontend `KanbanBoard.test.ts`: sloupec Odloženo, ↑/↓ emituje `reorder` se správným pořadím, přepínač emituje `exclude`, drop emituje. `BacklogView.test.ts`: volání API po reorder/exclude.

## 3B. Řízení výroby: ad-hoc harness a příprava běhu

### Per-run přepis harnessu/modelu
- CLI `aifactory/src/aifactory/cli.py` (`task run` parser ~ř. 2465): přidej `--harness NAME`, `--model NAME`, `--thinking LEVEL` (choices `harness/override.py THINKING_LEVELS`).
- `run/task.py run_task(..., agents_override: dict[str, str] | None = None)`: hned po `rc = _load(main)` přepiš všem agentům roster `rc.config.agents` (defaults i každý role-level `coding_agent`/`model`/`thinking`) danými hodnotami. Použij stejnou sémantiku jako `config/roster.py roster(change=True, preset=None, agent=None)` s odstraněním role-level klíčů. Přepis dělej jen v paměti (pydantic `model_copy(deep=True)`), nic nezapisuj.
  - Harness kanonizuj `harness.canonical`. Neznámý harness nebo thinking → `TaskRunError("invalid_override", ...)`.
  - Přepisy na kroku workflow (`harness/override.py step_override`) dál platí a mají přednost, takže jeden workflow může dál míchat harnessy. Napiš to do helpu.
  - Přepis platí jen pro tento běh. U `--auto` řetězu se předá jen prvnímu běhu (zdokumentuj v helpu).
  - Hodnoty přepisu zapiš do poznámky běhu (trace/`note` metadata), ať je v RunDetail vidět. Stačí, když RunDetail ukáže harness/model z fází, které už zobrazuje. Ověř, že je zobrazuje.
- `web/launcher.py Launcher.start(..., harness=None, model=None, thinking=None, auto=False)` přidá flagy. `auto=True` → `--auto`.
- `web/backlog.py start_run`: `RUN_KEYS` rozšiř o `harness`, `model`, `thinking`, `auto`, s validací typů.
- Testy:
  - `aifactory/tests/run/test_task_run_cli.py`: argumenty se dostanou do `run_task`.
  - `aifactory/tests/run/test_task_run.py`: override změní harness všech rolí, step override vyhraje, neplatný harness → `invalid_override`.
  - `aifactory/tests/web/test_web_task_run.py`: launcher dostane flagy.

### Editor rosteru (harnessy a modely repa)
- Backend: `web/factory.py` již má `roster(root)` (~ř. 722, GET `/factory/roster`). Přidej `POST /api/repos/{id}/factory/roster` body `{preset?, agent?, harness?, model?, thinking?, dry_run: bool}`. Volá `config/roster.roster(repo, change=True, ...)` a vrací `{agents, before, diff, changed}`. `ConfigError` mapuj na 422.
  - Do GET odpovědi přidej `presets` (`config/roster.PRESETS`), `thinking_levels` a `workflow_overrides`: seznam `{workflow, step, harness, model, thinking}` z workflows repa. Použij parser workflow (`workflow/parse.py`), stačí kroky s overridem.
  - Test `aifactory/tests/web/test_web_factory_roster.py`.
- Frontend: nová komponenta `components/factory/RosterEditor.vue` v záložce Factory (`views/FactoryView.vue`), sekce „Harnessy a modely“. Nahrazuje volnotextové „Nastavit“ pro agenty ve `FactoryItems.vue` (to odstraň, viz oddíl 6):
  - tlačítka presetů (Claude / Codex),
  - tabulka agentů (jméno, harness `SelectMenu` z detekovaných harnessů stroje, model input s `<datalist>` návrhů z presetů, thinking `SelectMenu`),
  - read-only seznam přepisů na krocích workflow,
  - náhled diffu (`dry_run: true`) → „Uložit“ → hláška „Běhy použijí změnu až po commitu konfigurace“ s odkazem na stávající `config_commit` (factory sub-route).
  - Test `RosterEditor.test.ts`.

### RunDialog (příprava běhu): `components/backlog/RunDialog.vue`
- Zobraz souhrn: efektivní workflow, `writes`, testovací příkaz, base sha (už je v `check`), sbalitelný náhled zadání (`MarkdownView`, `task.body`). Data jsou v `fetchTask`/`fetchRunCheck`. Pokud v `run-check` odpovědi něco chybí, doplň backend `web/backlog.py` run-check o `workflow`, `writes`, `test` (efektivní hodnoty z base) a test.
- Sekce „Harness pro tento běh“ (sbalená): harness/model/thinking. Prázdné = podle rosteru. Ukaž aktuální roster (`/factory/roster`).
- Checkbox „Po úspěchu pokračovat dalšími tasky (auto continue)“ → `auto: true`. Pod ním věta, že pořadí a vyloučení řídí kanban.
- Chyby a texty:
  - `blocked` musí zahrnout `!check.in_base` (dnes jen varování ~ř. 43–53, 75).
  - U varování necommitnuté konfigurace přidej odkaz/tlačítko na commit konfigurace (jako je u backlogu).
  - `launcher_busy` hláška s odkazem na běžící běh (`runHref`).
  - Text „Spustit přesto (--force)“ → „Spustit přesto (ignorovat nesplněné závislosti)“.
- Po startu přejdi na detail běhu (`#/r/<id>/runs/<run_id>`, router helper), resp. ukaž tlačítko „Otevřít běh“, pokud `pending`.
- `TaskDetail.vue:139`: Spustit zakázané i pro `done`/`cancelled` s tooltipem.
- Testy: `RunDialog.test.ts` (existuje-li, jinak nový): blocked při `!in_base`, payload s harness/auto, navigace po startu.

### Sledování běhů
- `RunDetail.vue`: task id jako odkaz do backlogu (`taskHref`). PR odkaz i na obrazovku Review (`reviewHref`). PR stav česky.
- `ChainPanel.vue`: id tasků a „Řetěz od X“ jako odkazy (~ř. 25, 67), PR stav česky (~ř. 46), důvod `excluded` česky.

---

## 1. Cesta „první návštěva“

- **Průvodce:** nová komponenta `components/GettingStarted.vue`, kterou ukazuje `OverviewView.vue` (nahoře, sbalitelná; když je vše hotovo, jen jeden řádek „Vše připraveno“) a `SetupView.vue`. Kroky se stavem (✓ / další krok zvýrazněný s tlačítkem):
  1. Tento počítač: `machine/check` bez chyb → `#/setup`.
  2. Knihovna připravena → `#/setup` (sekce knihovny) / `#/library`.
  3. Harnessy přihlášené: z machine checku detekované harnessy, alespoň jeden.
  4. Repozitář přidaný: alespoň jeden v `/repos` → `#/repos/add`.
  5. Factory nainstalovaná: některé repo ve stavu ok → Factory záložka repa.
  6. Harnessy a modely repa zkontrolované → Factory záložka (RosterEditor). Označ hotové, když roster existuje.
  7. Backlog má projekt → `#/r/<id>/backlog/new-container`.

  Logiku stavů dej do čisté funkce `lib/gettingStarted.ts` (vstupy: machine check, library, repos, overview) a otestuj ji v `gettingStarted.test.ts`.
- `App.vue` (~ř. 72–82): bez repozitářů přesměruj vždy na `#/overview`, kde je průvodce. `#/setup` zůstává pro chyby stroje.
- `SetupView.vue`:
  - Chyby nahrazuj, ne `+=` (~ř. 23). `load()` maže `error`.
  - Při zápisu text „Ukládám…“ místo „Načítám…“ (~ř. 63).
  - Copy jen pokud finding má `fix` (~ř. 73).
  - Severity česky.
  - „claude · 0 rep“ → správné tvary přes `plural` z `lib/format.ts`.
  - Pull/Push → „Stáhnout“/„Odeslat“; volání přesuň do `lib/library.ts` (`syncLibrary(action)`).
  - Na konci tlačítko „Další krok: Přidat repozitář“.
  - Přesuň sem `components/repos/DashboardSettings.vue` (nastavení dashboardu je nastavení stroje), viz oddíl 6.
- `ReposAddView.vue` + `App.vue onAdded` (~ř. 94–97): po přidání/instalaci nepřesměrovávej. Ukaž kartu „Repozitář X přidán“ s tlačítky „Otevřít repo“ (Factory, pokud není nainstalováno, jinak Backlog) a „Přidat další repozitář“ (vyčistí formulář). BackLink → `#/overview`.
- `InspectCard.vue`: „Otevřít“ vede na Factory, pokud repo není ok (~ř. 104). Registrované repo bez factory (`state none`) dostane tlačítko instalace (~ř. 101–105).
- `InstallForm.vue` + `lib/api.ts FactoryOptions`:
  - Přidej `test_command` (předvyplněný návrhem z inspect/plan, pokud ho backend vrací; jinak prázdný = návrh instalátoru). Ověř `web/factory.py`, jestli option `test_command` projde do instalátoru (CLI má `--test-command`, `cli.py:495`). Pokud ne, doplň backend + test.
  - Labely česky (`backlog_dir` → „Adresář backlogu“ atd., „Git provider“ → „Git hosting“, „Thinking“ → „Přemýšlení“).
  - Model: input s `<datalist>`.
- `FactoryView.vue`:
  - Po instalaci box „Co dál“: 1) zkontroluj harnessy a modely (RosterEditor), 2) commitni konfiguraci (`config_commit`), 3) založ první projekt.
  - „Aktualizovat z knihovny“ skryj při stavu `none` (~ř. 110).
  - Přejmenuj „Dorovnat base“ → „Stáhnout konfiguraci z base“ (kolize s Review).
- `FactoryOperation.vue`:
  - Plurál „V repu běží N běhů“ (~ř. 145).
  - Text prázdného plánu podle akce (~ř. 150).
  - Když `runsKnown` nejde zjistit, tlačítko „Zkusit znovu“ (~ř. 82–86, 143).
- `OnboardingPanel.vue`: prázdný `code` bez „: “ (~ř. 91), Base/PR česky, kódy blokátorů a akcí přes mapu textů.
- Externí odkazy (PR, hosting) `target="_blank" rel="noopener"`:
  - `InspectCard.vue:72`
  - `FactoryView.vue:104`
  - `OnboardingPanel.vue:95,123`
  - `FactoryOperation.vue:154`
  - `LibraryView.vue:153`
  - `RunDetail`, `TaskDetail`, `ChainPanel`
- `LibraryView.vue`: stavy česky. Když prohlížíš starší verzi, akce zakaž s vysvětlením (~ř. 135). Chyby přes `errorText`.
- Limity v horní liště i na globálních stránkách (oddíl 5).

## 2. Cesta „tvorba backlogu“

- `BacklogTree.vue` (~ř. 11): prázdný backlog → „Backlog je prázdný. Založ první {levelNoun(0)}.“ s tlačítkem. Když vše skryje filtr → „Filtru nic neodpovídá“ + „Zrušit filtr“. Použij `levelNoun`.
- `TaskForm.vue`:
  - Krok předvyplň z kontextu: router `new` přijme volitelný parametr kroku (`#/r/<id>/backlog/new/<stepId>`). Úprava `lib/router.ts`, tlačítko v grafu kroku (`BacklogView.vue` ~ř. 643) ho předá.
  - Bez kroků ukaž hlášku s odkazem „Založit krok“ místo tiše zakázaného Založit (~ř. 51, 234).
  - Sekce parametrů (`<details>` ~ř. 313) je dostupná vždy, ne jen po AI návrhu. Labely česky.
  - Zadání (body) přesuň před AI tlačítka. U zakázaných AI tlačítek text proč („Vyplň název“).
  - Status options česky (~ř. 147–151).
  - Sjednoť sémantiku testovacího příkazu s `ContainerSettings.vue` (~ř. 49, ~100). Zjisti v `testing/`/`run/task.py`, jak se interpretuje `test` jako string a jako list, a použij v obou formulářích stejný převod a stejnou nápovědu. Společný převod dej do `lib/backlog.ts` (`parseTestField`/`formatTestField`) + test.
- `TaskAdvice.vue`: prázdný výběr agentů → vysvětlení. `WorkflowAdvice.vue` zobrazí cenu jako TaskAdvice.
- `TaskDetail.vue`:
  - „Navrhnout workflow“ (~ř. 309) → „Upravit a navrhnout workflow“.
  - PR seznam (~ř. 353–363) odkazuje i na Review (`reviewHref`), stav česky.
- `BacklogView.vue`:
  - Problémy backlogu (~ř. 790): místo odkazu na CLI ukaž seznam přes existující `components/backlog/IssueList.vue`, pokud ho `/api/backlog` vrací. Ověř a případně doplň backend o seznam issues + test. Text „{n} problém/problémy/problémů“ přes `plural`.
  - Oznámení o novém workflow (~ř. 610–613): uvnitř `<section>`, styl jako ostatní notice, text odkazu „Commitnout konfiguraci“, vymaž při navigaci. Pokud už stejnou informaci dává `ConfigStatusBanner`, oznámení odstraň a nech jen banner.
  - Graf kontejneru (~ř. 752): odstraň duplicitní `AutoContinueToggle` a auto-merge toggle v hlavičce. Na stránce zůstává `ContainerSettings`. `AutoContinueToggle` zůstává ve stromu (`TreeNode.vue`).
- `ContainerSettings.vue`: labely viditelně česky (ne jen sr-only), null ≠ „off“ (~ř. 61; null = zděděno). Popisky jednotně „Zděděno / Zapnuto / Vypnuto“ ve všech komponentách (`AutoContinueToggle`, `TaskForm` ~ř. 65–69, `ContainerSettings`).
- `ContainerForm.vue` (~ř. 27): placeholdery podle kódů úrovní z backlog settings, ne natvrdo „M01“.

## 4. Cesta „schvalování PR“

- `ReviewView.vue` (~ř. 111–115): po sloučení box „Sloučeno“ + tlačítka „Další PR ke schválení“ (první další otevřený PR ze seznamu, jinak skryté) a „Zpět na seznam“. Věta: „Pokud má krok zapnuté auto continue, další task se spustí automaticky; pořadí určuje kanban.“
- `ReviewActions.vue`:
  - Po úspěšném vrácení vymaž poznámku (~ř. 33–35).
  - Vrácení potvrď přes `lib/confirm.ts` / `ConfirmDialog`.
  - Tlačítko konfliktu sjednoť s bannerem: „Vyřešit konflikt s base“ (~ř. 41, ~110).
- `ReviewList.vue` (~ř. 49): prázdný seznam → „Žádné PR ke schválení“ + odkazy na Backlog a Běhy.
- Testy v existujících `ReviewView`/`ReviewActions` testech (fixtures `src/test/reviewFixtures.ts`).

## 5. Limity Claude v `LimitsBar` (akceptační kritérium 5)

Příčina: `web/limits.py _claude_token_json()` (~ř. 100) čte nejdřív `~/.claude/.credentials.json`, kde leží prošlý token. Keychain se tak nepoužije, API vrací 429, žádná okna, bar ukazuje „nedostupné“. Druhá příčina: `used_harnesses(repo)` ukazuje jen harnessy z rosteru repa, takže po přepnutí rosteru zmizí druhý provider. Bar je navíc jen na stránce repa (`App.vue` ~ř. 128–130).

Oprava:
1. `_claude_token_candidates() -> list[str]`: keychain (na darwin, první) a soubor `$CLAUDE_CONFIG_DIR|~/.claude/.credentials.json`. `claude_token(now=time.time)`:
   - vyhodí kandidáty, jejichž `claudeAiOauth.expiresAt` (ms) je v minulosti,
   - vybere ten s nejpozdějším `expiresAt` (chybějící `expiresAt` = platný, s nejnižší prioritou),
   - když existují jen prošlé, `claude_limits` vrátí chybu „přihlášení Claude Code vypršelo, spusť claude“ bez síťového volání.

   Rozhraní: `claude_token` vrací `str | None` + oddělená funkce `claude_token_state()` → `("ok", token) | ("expired", None) | ("missing", None)`. `claude_limits` použije stav.
2. HTTP 429: chyba „Claude usage API omezuje dotazy, zkus za N min“ (z `Retry-After`, pokud je). `LimitsSource._read` u 429 drží cache `max(ttl, retry_after)`. Předání: reader vrátí v entry `retry_after` sekundy. Stale okna se dál ukazují (`_stale`).
3. Viditelnost: `LimitsSource.get(repo: Path | None)` ukáže sjednocení `used_harnesses(repo)` (pokud repo) a `available_harnesses()`, v pořadí `LIMITED_HARNESSES`. `available_harnesses()`:
   - claude, pokud `claude_token_state()` není `missing` nebo `shutil.which("claude")`,
   - codex, pokud je dostupná binárka (`CODEX_PATH`/`shutil.which("codex")`) nebo existují Codex přihlašovací/session soubory, které už čte `codex_limits`.
4. Globální `GET /api/limits` v `create_multi_app` (`LimitsSource.get(None)`). `lib/limits.ts` použije repo endpoint na stránce repa, jinak globální. `App.vue` renderuje `LimitsBar` všude.
5. Testy `aifactory/tests/web/test_web_limits.py`:
   - prošlý soubor + platný keychain → keychain (monkeypatch `subprocess.run`, `sys.platform`, `Path.home`/`CLAUDE_CONFIG_DIR`),
   - jen prošlé → chyba bez fetch,
   - 429 s Retry-After → text + delší cache,
   - `get()` s Codex rosterem ukáže i Claude, když je dostupný,
   - globální endpoint.

   Frontend `LimitsBar.test.ts` / `lib/limits` test: globální URL mimo repo. `tests/e2e/test_limits_layout.py` musí dál projít.

## 6. Úklid: mrtvé a duplicitní věci (zapiš do app_docs s důvodem)

Odstranit:
- `lib/repos.ts` `ADD_REPO_COMMAND` (nikde nepoužité). `EmptyScreen.vue` prop `code` a blok `empty-code` (nikdo nepředává).
- Exporty používané jen testy: `lib/router.ts parseHash`, `lib/format.ts prettyJson`, `lib/events.ts dotColor`, `lib/live.ts reopenLive`, i jejich testy. Pokud je funkce použitá uvnitř modulu, jen ji přestaň exportovat a test smaž.
- `lib/router.ts hrefFor` (triviální obal `here`), nahraď voláním `here`.
- Repo-scoped `/api/repos/{id}/code` a `/api/repos/{id}/restart` (`app.py` ~ř. 269, 277; frontend volá jen globální). Odstraň i `guard.py _REPO_RESTART` (~ř. 72) a test `tests/web/test_web_repos.py` (~ř. 542) a další, které je volají (grep `"/code"`, `"/restart"` v `tests/web`). Jednorepová `create_app` testová `/api/health` zůstává (testovací infrastruktura).
- Stránka `#/repos` (`views/ReposView.vue`, `components/RepoList.vue`): duplikuje Přehled (seznam + odebrání). `DashboardSettings` přesuň do `SetupView` („Tento počítač“). Položku „Spravovat…“ v `RepoSwitcher.vue` odstraň. Route `repos` smaž z `lib/router.ts` (neznámý hash už padá na overview). Uprav `router.test.ts`, `App.test.ts` a e2e testy, které `#/repos` používají (grep `#/repos'`/`"#/repos"` bez `/add`).
- `FactoryItems.vue`: volnotextová akce „Nastavit“ harness/model/thinking u agentů. Nahrazuje ji RosterEditor.
- `AutoContinueToggle` + auto-merge toggle v hlavičce grafu kontejneru (duplicita s `ContainerSettings`).

Sloučit duplicity:
- `ConfigStatusBanner.vue` + `BacklogStatusBanner.vue` → jedna `components/UncommittedBanner.vue` (props: titulek, status, akce commitu). `toBacklogStatus` (`lib/backlog.ts` ~ř. 510) a `toConfigStatus` (`lib/settings.ts` ~ř. 96) → jedna `toCommitStatus` v novém `lib/commitStatus.ts`. Zachovej stávající chování obou bannerů. Testy obou bannerů převeď na testy nové komponenty.
- Náhled plánu: `components/LibraryPlanView.vue`, `components/factory/FactoryPlanView.vue` a inline markup v `OnboardingPanel.vue` (~ř. 97–117) → jedna `components/factory/PlanView.vue` (blockers, warnings string|object, soubory s `DiffContent`). Sjednoť typy `OnboardingPlan`/`LibraryChanges` vs `LibraryPlan`/`RepoPlan`, kde mají stejný tvar.
- `lib/library.ts ITEM_TABS/ItemType` → použij `FactoryItemType` z `lib/api.ts`. `applyRepo` whitelist → `factoryItemChoices`.
- `lib/api.ts`: `fetchFactoryPlan` použije `factoryEnvelope`. Opakovaný merge warnings (~ř. 519, 526, 533) → helper.
- `RepoSwitcher.vue LABELS` → `REPO_STATUS_TEXT` z `lib/repos.ts`.
- `lib/format.ts`: nové `shortSha(sha, n = 7)` a `errorText(err: unknown)` (`err instanceof Error ? err.message : String(err)`). Nahraď ad-hoc `.slice(0,7|8)` (bannery, `RunDialog`, `FactoryPlanView`, `ReviewView`, `FactoryView short()`, `repos.ts`, `library.ts`) a všechny `instanceof Error ? … : String(…)` / `String(e)` v catch. Test ve `format.test.ts`.
- `limits.ts fmtAt` → `format.ts` helper, pokud jde o stejný formát; jinak nech a přejmenuj srozumitelně.
- Deep-clone `JSON.parse(JSON.stringify(...))` (`InstallForm.vue:7`, `UpdateChoices.vue:8`, `FactoryOperation.vue:91`) → `structuredClone`.
- `OverviewView`/`ReposView` duplicitní EmptyScreen odpadne se smazáním ReposView.
- `lib/router.ts` hlavičkový komentář (ř. 3–7) aktualizuj.

## 7. Drobné chyby (seznam do app_docs a PR)

Všechny výše označené. Shrnutí:
1. Claude limity se nezobrazují (prošlý token ze souboru má přednost před keychainem; roster skrývá providera).
2. Chyby v SetupView se hromadí.
3. Text „Načítám…“ při zápisu.
4. Copy kopíruje text bez příkazu.
5. RunDialog povolí start tasku, který není v base.
6. ContainerSettings převádí zděděné (null) na „vypnuto“.
7. Plurál „běží N běhů“.
8. „: “ před chybou bez kódu v OnboardingPanel.
9. Poznámka vrácení PR se nemaže.
10. Externí odkazy otevírají ve stejném tabu.
11. „Otevřít“ u nenainstalovaného repa vede do Backlogu.
12. Spustit u hotového/zrušeného tasku.
13. Nekonzistentní popisky Zděděno/zděděné.
14. Kolize názvů „Dorovnat base“ / „Dorovnat s base“.
15. Prázdný backlog a filtr hlásí totéž.
16. Oznámení o workflow se nemaže při navigaci.

Další nalezené chyby oprav a připiš do seznamu.

## 8. Ověření

1. `cd aifactory/web && bun run typecheck && bun run test` (= `just web-test`).
2. `just web-build`: přegeneruje `aifactory/src/aifactory/web/static` (smaže staré hashované assety, `emptyOutDir`). Přidané/smazané soubory statiky jsou součástí změny.
3. `uv run --project aifactory pytest aifactory/tests/run/test_auto_continue.py aifactory/tests/run/test_parallel_chain.py aifactory/tests/run/test_queue_prefs.py aifactory/tests/web -q`.
4. `just check-scoped`: musí projít, rozhoduje exit status. Změna `run/` spustí širší sadu, včetně e2e browser testů nad statikou. Pokud e2e testy odkazují na odstraněné texty/route (`#/repos`, „Spravovat…“, „Nastavit“ u agentů), uprav je.
5. Ručně (volitelně, `just dash`) projdi čtyři cesty:
   - první návštěva: průvodce na Přehledu, Setup, přidání dvou repo, instalace, roster, commit konfigurace, nový projekt,
   - backlog: projekt, krok, task s předvyplněným krokem,
   - výroba: kanban přeřadit, odložit, RunDialog s auto, běh,
   - Review: schválit, další PR.

## Akceptační kritéria → kde

| Kritérium | Oddíl |
|---|---|
| Čtyři cesty bez slepých míst | 1, 2, 3B, 4 + GettingStarted |
| Odstraněno vč. testů, popsáno | 6 + app_docs |
| Pořadí ready tasků uložené a použité | 3A |
| Vyloučený task se automaticky nespustí, ručně ano | 3A (+ test ručního startu) |
| Claude limity vedle Codexu | 5 |
| Drobné chyby opravené a vyjmenované | 7 + app_docs |
| `just check-scoped` + FE i BE testy | 8 |
