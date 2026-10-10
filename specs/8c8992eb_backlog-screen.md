# Plán: obrazovka Backlog v dashboardu (úkol 3.3)

## Zadání

Obrazovka Backlog v dashboardu HAIFA:

- strom modul → step → task podle `levels` z konfigurace,
- kanban podle stavu (todo, ready, blocked, running, in review, done, cancelled),
- filtr stavu a vlastníka modulu,
- detail tasku: hlavička, zadání, vazby oběma směry, běhy a PR,
- založení a editace tasku, přidání a odebrání vazby, přiřazení workflow.

Zápisy volají tytéž funkce core jako `factory task add|edit|link` (`aifactory.backlog.add_task`, `edit_task`, `link_task`). Zápis, který by backlog rozbil, core odmítne (`TaskEditError("backlog_invalid", issues=…)`). API vrátí chybovou obálku s `error.issues` a UI tyto problémy zobrazí.

Kde se pracuje: `aifactory/src/aifactory/web/`, `aifactory/web/src/`, `aifactory/tests/web/`.

Mimo rozsah:

- graf závislostí, spuštění tasku, přepínač auto-continue (3.4),
- editor workflow (F4),
- editace těla (`## Zadání`) existujícího tasku, protože core ani CLI ji nemají,
- živé aktualizace (3.7).

Pevná omezení:

- Zapisují se jen soubory backlogu v hlavním checkoutu. To hlídá core (`_guard` v `backlog/edit.py`).
- Nic se necommituje.
- `vendor/` a `prototype/` se nemění.
- Neměnit `aifactory/src/aifactory/backlog/**`, `cli.py` ani `skill/codes.py`. Používají se jen existující chybové kódy.

## Co už existuje (nečíst znovu, jen pro orientaci)

- `aifactory/src/aifactory/web/app.py`: Starlette app, `create_app(repo, static_dir=)`, routy pod `Mount("/api")`, obálka přes `aifactory.skill.envelope.envelope_ok/envelope_fail`. Vzor mapování chyb na HTTP status je `_run_error` a `_RUN_ERROR_STATUS`. `request.app.state.repo` je kořen repa.
- `aifactory/src/aifactory/web/runs.py`: vzor modulu s čistými funkcemi, které vrací `(data, warnings)`.
- Core backlogu (`aifactory.backlog`):
  - `load_for_edit(root)`, `check_backlog(backlog)`, `find_task(backlog, id, issues)`,
  - `blocks(backlog)` (reverzní mapa „blokuje“), `derived_state(backlog, task)` (`ready|blocked|done|cancelled|invalid`),
  - `unmet`, `effective(task)` (dědí `owner`, `workflow`, `writes`…), `effective_workflow`, `progress(container)`, `is_done`,
  - `iter_containers`, `iter_tasks`,
  - `render.task_to_json(backlog, task, reverse)`: klíče `id, title, level, path, status, state, workflow, effective, depends_on, related, writes, own_writes, blocked_by, blocks`,
  - `add_task(root, step, title, *, task_id, slug, workflow, writes, depends_on, related, body)`,
  - `edit_task(root, id, *, title, status, workflow, clear_workflow, writes, clear_writes)`,
  - `link_task(root, id, *, depends_on, related, remove)`.
  
  Zápisové funkce vrací `WriteResult(action, changed, path, task, backlog, issues)`. Chyba je `TaskEditError` s atributy `.code`, `.message`, `.path`, `.id` a `.issues: list[Issue]` (`Issue.to_dict()`).
- Kontejner: `Container(id, title, level, path, defaults, children, tasks, parent)`. `backlog.settings.levels` je n-tice názvů úrovní, poslední úroveň je task. Step je `levels[-2]`.
- Běhy a PR:
  - `aifactory.run.task.existing_store(repo)` vrací `TaskRunStore | None`,
  - `store.all_runs()` odklidí mrtvé `running` záznamy a vrací `TaskRunRow` od nejnovějšího,
  - `store.open_prs()` vrací `TaskPrRow`, `store.close()` store zavře,
  - `aifactory.run.task_runs_for(repo, id)` a `task_prs_for(repo, id)` jsou totéž, co používá `factory task show`,
  - `TaskRunRow.to_json()` a `TaskPrRow.to_json()`.
- Workflow:
  - balená jsou v `aifactory.workflow.DEFAULT_WORKFLOWS_DIR` (`*.yaml`),
  - repo má vlastní v `.factory/workflows/*.yaml` (konstanta `aifactory.config.loader.WORKFLOWS_DIR`).
- CLI `factory task show --json` (`cli.py::_task_show`) vrací `{task, body, issues, runs, prs}`. `factory task add|edit|link --json` (`cli.py::_task_write`) vrací `{action, changed, path, task, issues}`. API vrací stejné tvary a pole navíc jen přidává.
- Frontend (`aifactory/web/src`):
  - `lib/api.ts`: `getApi`, `postApi`, `ApiError(code, message)`,
  - `lib/router.ts`: hash routy `#/<screen>/<params…>`, `useRouteParams()`, `runHref()`,
  - `views/BacklogView.vue` je zatím `EmptyScreen`,
  - vzor obrazovky je `views/RunsView.vue` + `components/runs/*` + `test/runsFixtures.ts` + testy `*.test.ts` (vitest, happy-dom, `@vue/test-utils`, `vi.stubGlobal('fetch', …)`),
  - ikony `lucide-vue-next`, CSS proměnné (`--panel-2`, `--border`, `--dim`, `--red`, …) ve `style.css`.
- Testy Pythonu:
  - `pytest` s `pythonpath = ["tests", "."]` a xdist,
  - soubory v `tests/web/` importují sourozence přímo (`from web_repo import git_repo`, `from trace_fixture import …`),
  - `tests/web/trace_fixture.py` ukazuje, jak vyrobit trace DB přes `TaskRunStore` (`claim`, `finish`, `save_pr`),
  - obálku ověřuje `aifactory.skill.envelope_problems(body) == []`.
- `mypy --strict` běží i nad `tests/`. Recepty: `just test` (spouští i `bun run typecheck && bun run test`), `just typecheck` (mypy), `just lint` (ruff check + ruff format --check).

## Rozhodnutí

### Stav na kanbanu (`board_state`)

Stav se spočítá pro každý task v tomto pořadí (první shoda vyhrává):

1. `status == "done"` → `done`
2. `status == "cancelled"` → `cancelled`
3. task má běh ve stavu `running` (po `all_runs()`, které mrtvé běhy odklidí) → `running`
4. task má otevřený PR (`store.open_prs()`) → `in review`
5. `derived_state == "blocked"` → `blocked`
6. `derived_state == "ready"` a task má efektivní workflow → `ready`
7. jinak → `todo`. Sem patří task bez přiřazeného workflow, který se proto ještě nedá spustit. Patří sem i task s neplatným `status` (`derived_state == "invalid"`), s příznakem `invalid: true`.

Konstanta `BOARD_STATES = ("todo", "ready", "blocked", "running", "in review", "done", "cancelled")` v `web/backlog.py` určuje i pořadí sloupců.

Chybějící trace DB znamená, že žádné běhy ani PR nejsou. Když je DB zamčená (`TaskRunError`), obrazovka se nerozbije: stavy 3 a 4 se vynechají a do `warnings` se přidá hláška.

### Filtry

- `status` přijímá hodnotu z `BOARD_STATES`. Jinak vrací 400 `invalid_status`.
- `owner` porovnává efektivního vlastníka tasku (`effective(task).get("owner")`, typicky z `index.md` modulu).
- Filtruje server. Ve stromu se vynechají kontejnery bez shodného tasku. Kanban dostává plochý seznam už vyfiltrovaný.
- `owners` v odpovědi je vždy seznam všech vlastníků napříč celým backlogem, i při aktivním filtru, seřazený.

### Seznam workflow pro výběr

Seznam tvoří sjednocení názvů (stem) souborů `.factory/workflows/*.yaml` v pracovním stromu a `DEFAULT_WORKFLOWS_DIR/*.yaml`, seřazené a bez duplicit. Soubory se neparsují.

### API a HTTP stavy

| Metoda | Cesta | Core | Odpověď `data` |
|---|---|---|---|
| GET | `/api/backlog?status=&owner=` | `load_for_edit`, `check_backlog`, `blocks`, `derived_state`, `effective`, store | viz „Tvar stromu“ |
| GET | `/api/backlog/tasks/{task_id}` | `find_task`, `task_to_json`, `task_runs_for`, `task_prs_for` | `{task, body, issues, runs, prs, depends, blocks}` |
| POST | `/api/backlog/tasks` | `add_task` | `{action, changed, path, task, issues}` jako CLI |
| POST | `/api/backlog/tasks/{task_id}/edit` | `edit_task` | totéž |
| POST | `/api/backlog/tasks/{task_id}/link` | `link_task` | totéž |

Přiřazení workflow je `edit` s `workflow` nebo `clear_workflow`.

Mapování `TaskEditError.code` → HTTP stav:

| Kód | HTTP |
|---|---|
| `backlog_invalid` | 422 |
| `unknown_task`, `unknown_step`, `missing_backlog_dir` | 404 |
| `file_exists`, `duplicate_id` | 409 |
| `write_failed` | 500 |
| cokoli jiného | 400 |

Chybová obálka: `envelope_fail(exc.code, exc.message, path=exc.path, id=exc.id, issues=[i.to_dict() for i in exc.issues])`, stejně jako CLI v `_fail_from_exception`.

Další chyby:

- `ConfigError` → 500 `invalid_config` s issues jako v CLI (`{"code": "invalid_config", "message", "path", "id": None}`).
- Tělo POST, které není JSON objekt, → 400 `usage_error`.
- Pole se špatným typem (např. `title` není řetězec, `writes` není seznam řetězců) → 400 `invalid_value`.
- Neznámý klíč v těle → 400 `usage_error` se zprávou, který klíč to je.

## Kroky implementace

### 1. Backend: `aifactory/src/aifactory/web/backlog.py` (nový)

Modul docstring popisuje, co modul dělá, a uvádí, že zapisuje jen přes core.

Import core jako modulu: `from aifactory import backlog as core` a volání `core.add_task(...)`, `core.edit_task(...)`, `core.link_task(...)`. Test pak může přes `monkeypatch.setattr("aifactory.backlog.add_task", spy)` ověřit, že API volá právě funkci core.

Obsah:

- `JsonDict = dict[str, Any]`, `BOARD_STATES`.
- `class _Runtime`: `running: set[str]`, `in_review: set[str]`, `last_run: dict[str, str]` (task_id → stav posledního běhu).
  - `def _runtime(repo) -> tuple[_Runtime, list[str]]` používá `existing_store` a `try/finally store.close()`.
  - Zachytává `TaskRunError` (kód `invalid_config` nechat propadnout jako chybu, protože jde o chybu konfigurace) a `sqlite3.Error`, obojí → warning.
- `def board_state(backlog, task, rt) -> str` podle pravidel výše.
- `def _task_json(backlog, task, reverse, rt) -> JsonDict` = `core.task_to_json(...)` a navíc:
  - `board_state`,
  - `owner` (efektivní, `str | None`),
  - `invalid: bool`,
  - `last_run: str | None`.
- `def _container_json(backlog, container, reverse, rt, keep) -> JsonDict | None`. `keep` je predikát nad taskem. Klíče: `kind: "container"`, `id`, `title`, `level`, `path`, `owner` (`defaults.get("owner")`), `progress {done,total}` (přes `core.progress` nad celým kontejnerem, ne nad filtrem), `done`, `blocks`, `children`. Děti jsou nejdřív podkontejnery, pak tasky. Při aktivním filtru vrací `None`, když nic neprošlo.
- `def backlog_view(repo, *, status, owner) -> tuple[JsonDict, list[str]]` validuje `status`, načte backlog a vrátí:

  ```
  {
    "levels": [...], "backlog_dir": str,
    "filters": {"status": ..., "owner": ...},
    "states": list(BOARD_STATES),
    "owners": [...], "workflows": [...],
    "steps": [{"id","title","path","module"}],   # kontejnery úrovně levels[-2] s id, pro formulář založení
    "items": [container...],
    "tasks": [task...],                           # plochý, vyfiltrovaný, v pořadí cesty (pro kanban)
    "issues": [Issue.to_dict()...],
    "counts": core.counts(backlog)
  }
  ```

  Mezi warnings patří i `"{n} problem(s), run 'factory backlog check'"`, když `issues` není prázdné.
- `def task_detail(repo, task_id) -> tuple[JsonDict, list[str]]` se chová jako `_task_show --json` a navíc vrací:
  - `depends`: `[{id, kind: "task"|"container"|"unknown", title, state}]`. U tasku je `state` jeho `board_state`. U kontejneru je `"done"`, pokud platí `is_done`, jinak `"{done}/{total}"`. U neznámého id je `state` `"unknown"`.
  - `blocks`: `[{id, title, board_state}]`, zdroj je `core.blocks(backlog).get(task.id)`.
  - `task` je `_task_json`, `body` je `task.body`, `issues` jsou jen issues tohoto souboru, `runs` jsou `[r.to_json() for r in task_runs_for]`, `prs` jsou `[p.to_json() for p in task_prs_for]`.
- `def _write_json(result: core.WriteResult, repo) -> JsonDict` vrací `{action, changed, path, task: _task_json(...), issues}`. `task_to_json` volat nad `result.backlog`. `rt` načíst přes `_runtime`.
- `def add(repo, body: JsonDict)`, `def edit(repo, task_id, body)`, `def link(repo, task_id, body)` validují typy a volají core.
  - Povolené klíče pro add: `step` (povinný), `title` (povinný), `id`, `slug`, `workflow`, `writes`, `depends_on`, `related`, `body`. Pro edit: `title`, `status`, `workflow`, `clear_workflow`, `writes`, `clear_writes`. Pro link: `depends_on`, `related`, `remove`.
  - Pro validaci typů použít pomocníky `_opt_str`, `_opt_str_list`, `_opt_bool`, které vyhazují `core.TaskEditError("invalid_value", …)`.
  - Neznámý klíč vyhodí `_UsageError(message)`. Je to vlastní výjimka v modulu a mapuje se na `usage_error`.
  - Prázdný řetězec u `workflow` v editu posílat do core tak, jak je, core vrátí `invalid_value`. Pro zrušení workflow slouží `clear_workflow: true`.

### 2. Backend: `aifactory/src/aifactory/web/app.py`

- Doplnit do docstringu modulu nové endpointy.
- Přidat `_EDIT_ERROR_STATUS` a `_edit_error(exc: TaskEditError | ConfigError) -> JSONResponse` podle tabulky výše.
- Přidat `async def _json_body(request) -> dict[str, Any]`, které při nevalidním JSON nebo ne-objektu vyhodí `_UsageError`, a `_usage_error` → 400.
- Handlery `backlog_list`, `backlog_task`, `backlog_add`, `backlog_edit`, `backlog_link`. Zápisové handlery jsou `async` kvůli `await request.json()` a samotné volání core dávají do `starlette.concurrency.run_in_threadpool`. Čtecí mohou zůstat sync jako u runs.
- Routy do `Mount("/api")`. Pořadí: `/backlog`, `/backlog/tasks` (POST), `/backlog/tasks/{task_id}` (GET), `/backlog/tasks/{task_id}/edit` (POST), `/backlog/tasks/{task_id}/link` (POST).

### 3. Frontend: API a typy

- `lib/api.ts`:
  - `ApiError` dostane `readonly issues: ApiIssue[]` (třetí nepovinný parametr konstruktoru, výchozí `[]`),
  - `ApiIssue = {code: string; message: string; path: string | null; id: string | null}`,
  - `readEnvelope` předá `error.issues`,
  - existující testy (`api.test.ts`, RunsView) nesmí přestat fungovat.
- `lib/backlog.ts` (nový):
  - typy `BoardState`, `TaskNode`, `ContainerNode`, `BacklogNode = TaskNode | ContainerNode` (rozlišené přes `kind`), `BacklogData`, `TaskDetail`, `DependsRef`, `BlocksRef`, `TaskRun`, `TaskPr`, `WriteResult`, `AddTaskInput`, `EditTaskInput`, `LinkInput`, `BacklogFilters {status?, owner?}`,
  - `BOARD_STATES` v pořadí sloupců a `STATE_LABELS` s českými popisky (todo „K přípravě“, ready „Připraveno“, blocked „Blokováno“, running „Běží“, in review „V review“, done „Hotovo“, cancelled „Zrušeno“),
  - funkce `fetchBacklog(filters)`: URL `/backlog` a query jen z neprázdných hodnot přes `URLSearchParams`, stejně jako `fetchRuns`,
  - `fetchTask(id)`, `addTask(input)`, `editTask(id, input)`, `linkTask(id, input)` (id přes `encodeURIComponent`),
  - pomocná `flattenIssues(e: unknown): {message: string; issues: ApiIssue[]}` pro UI.
- `lib/router.ts`: `taskHref(taskId)` → `#/backlog/<encoded id>`. Detail tasku je `params[0]`. Nový task je `#/backlog/new` (`params[0] === 'new'`, konstanta `NEW_TASK = 'new'`). Id tasku `new` neřešíme, protože id tasků mají tvar `M..-S..-T..`.

### 4. Frontend: komponenty `aifactory/web/src/components/backlog/`

Všechny komponenty mají `data-test` atributy pro testy a čeština s diakritikou platí i v UI.

- `StateChip.vue`: prop `state: BoardState`, zobrazí `STATE_LABELS[state]`, třída `state-<state s pomlčkou>`. Může převzít vzhled z `runs/StatusChip.vue`.
- `BacklogFilters.vue`:
  - props `filters`, `owners`, `mode: 'tree' | 'kanban'`,
  - emituje `update:filters` a `update:mode`,
  - selecty `[data-test="state-filter"]` (volba „vše“ a 7 stavů) a `[data-test="owner-filter"]` (volba „vše“ a vlastníci),
  - přepínač `[data-test="mode-tree"]` a `[data-test="mode-kanban"]`,
  - prázdná hodnota znamená `undefined`, stejně jako v `RunsList`.
- `BacklogTree.vue`:
  - props `items: BacklogNode[]`, `levels: string[]`,
  - rekurzivní vykreslení přes pomocnou komponentu `TreeNode.vue` s `depth`,
  - kontejner: `[data-node="<id|path>"]`, název úrovně z `levels[depth]` (malý štítek), id, titulek, vlastník, progress `done/total`,
  - task: řádek s odkazem `a.task-link` na `taskHref(id)`, titulek, `StateChip`, workflow nebo „bez workflow“,
  - prázdný strom: `[data-test="empty-tree"]` s textem „Žádné tasky“.
- `KanbanBoard.vue`:
  - props `tasks: TaskNode[]`, `states: BoardState[]`,
  - pro každý stav sloupec `[data-column="<state>"]` s nadpisem a počtem,
  - karty `[data-card="<id>"]` s id, titulkem, vlastníkem, workflow a odkazem na detail,
  - prázdný sloupec zobrazí „—“,
  - karta s `invalid` dostane varovný štítek.
- `IssueList.vue`: props `message: string`, `issues: ApiIssue[]`. Vykreslí `[data-test="write-error"]` se zprávou a seznamem `code: message (path)`.
- `TaskForm.vue`: jedna komponenta pro založení i editaci.
  - props `mode: 'add' | 'edit'`, `steps`, `workflows`, `task?: TaskNode`, `busy: boolean`, `error: {message, issues} | null`.
  - add obsahuje: select step (povinný), titulek (povinný), id (nepovinné, placeholder „další volné“), workflow (select „zděděné“ a seznam), writes (textarea, řádek = cesta, prázdné = nezadáno), depends_on (vstup s id oddělenými čárkou nebo mezerou), zadání (textarea → `body`).
  - edit obsahuje: titulek, status (`todo` nebo `cancelled`; když je task `done`, select je disabled s poznámkou, že done mění jen schválení PR), workflow (select „zděděné“ a seznam; když uživatel změní výběr na „zděděné“ z jiné hodnoty, pošle se `clear_workflow: true`, když zvolí název, pošle se `workflow`), writes (textarea; checkbox „dědit“ → `clear_writes`).
  - Edit posílá jen změněná pole. Když se nic nezměnilo, tlačítko Uložit je disabled.
  - Emituje `submit` s `AddTaskInput` nebo `EditTaskInput` a `cancel`. Pod formulářem je `IssueList`, když je `error`.
- `TaskDetail.vue`:
  - props `detail: TaskDetail`, `workflows`, `busy`, `error`,
  - emituje `edit` (uložení formuláře), `link` (`LinkInput`) a `assign-workflow` (`string | null`),
  - hlavička: id, titulek, `StateChip(board_state)`, cesta k souboru, vlastník, workflow a writes (efektivní),
  - sekce „Zadání“: `body` v `<pre class="body">` (bez markdown knihovny, nepřidávat závislosti),
  - sekce „Vazby“ má tři podsekce:
    - „Závisí na“: `depends` s id, názvem a stavem; každá položka má tlačítko `[data-test="unlink-<id>"]` → `link` s `{depends_on:[id], remove:true}`; vstup `[data-test="link-input"]` a tlačítko `[data-test="link-add"]` → `{depends_on:[id]}`,
    - „Blokuje“: `blocks`, jen ke čtení, s odkazy na detail,
    - „Související“: `task.related` s odebráním a přidáním stejně (`related`),
  - sekce „Workflow“: select `[data-test="workflow-select"]` („zděděné“ a seznam) a tlačítko Přiřadit → `assign-workflow`,
  - sekce „Běhy“: tabulka `runs` (run_id jako odkaz `runHref`, stav, větev, začátek), prázdná → „Žádné běhy“,
  - sekce „PR“: `prs` (stav, odkaz s `target="_blank" rel="noopener"`, větev), prázdná → „Žádné PR“,
  - `issues` tasku jako varování,
  - tlačítko „Upravit“ přepne do `TaskForm mode="edit"`.

### 5. Frontend: `views/BacklogView.vue`

Stav:

- `data: BacklogData | null`, `filters`, `mode` (výchozí `tree`),
- `detail`, `loading`, `error` (načítání),
- `writeError: {message, issues} | null`, `busy`.

Chování:

- Bez parametru v routě ukazuje hlavičku „Backlog“, tlačítka „Obnovit“ a „Nový task“ (odkaz `#/backlog/new`), `BacklogFilters` a pak `BacklogTree` nebo `KanbanBoard`. Když `data.issues` není prázdné, ukáže pruh s počtem problémů.
- `#/backlog/new` ukáže `TaskForm mode="add"` (steps a workflows z `data`; když `data` chybí, nejdřív ho načte). Po úspěchu nastaví `window.location.hash = taskHref(result.task.id)`. Při `ApiError` uloží `writeError` z `err.message` a `err.issues`. Formulář zůstane vyplněný a nic se nenaviguje.
- `#/backlog/<id>` načte `fetchTask(id)` a zobrazí `TaskDetail`. Každý zápis (edit, link, workflow) zavolá API, pak znovu načte detail i seznam. Chyba zápisu se zobrazí v `TaskDetail` (`IssueList`) a detail zůstane beze změny.
- Změna filtru znovu načte seznam s query.
- Chyby načítání: `[data-test="error"]` jako v RunsView.
- `watch` na route params s `immediate: true`, stejně jako v RunsView.

Pozor na `App.test.ts`: mountuje `App` na výchozí routě (backlog). BacklogView tam zavolá `fetch('/api/backlog')`. Ověř, že `stubHealth` v App.test vrací odpověď pro jakoukoli URL. Pokud ne, uprav stub v `App.test.ts` tak, aby na `/api/backlog` vracel prázdná data, nebo aby BacklogView chybu jen zobrazil. Test nesmí padat na neošetřenou promise.

### 6. Build frontendu

`aifactory/src/aifactory/web/static/` je v gitu. Po dokončení frontendu spusť `just web-build`, aby balíček servíroval novou obrazovku. Staré hashované soubory v `static/assets/` odstraní `emptyOutDir`.

## Testy

### Python: `aifactory/tests/web/backlog_fixture.py` (nový pomocník, ne test)

`make_backlog_repo(path, *, levels=None, with_trace=False) -> Path`:

- Vytvoří git repo přes `web_repo.git_repo`, zapíše soubory a udělá jeden počáteční commit. Použij `git -c user.name=t -c user.email=t@t commit -qam init` po `git add -A`, nebo nastav identitu přes `-c`. Počáteční commit je potřeba, aby šlo ověřit, že API nic necommitlo.
- `.factory/config.yaml`: `base: main`, `levels` (výchozí `[module, step, task]`) a `backlog_dir: backlog`.
- `.factory/workflows/custom-flow.yaml` s minimálním obsahem, např. `name: custom-flow\nsteps: [plan]\n`. Neparsuje se, jde jen o jméno.
- Backlog:
  - `M01` (owner `alice`, workflow `plan-build`) → step `M01-S01`:
    - `T01`: done,
    - `T02`: todo, depends_on `[M01-S01-T01]` → ready,
    - `T03`: todo, depends_on `[M01-S01-T02]` → blocked,
    - `T04`: cancelled.
  - `M02` (owner `bob`, bez workflow) → step `M02-S01`:
    - `T01`: todo bez workflow → todo,
    - `T02`: todo s `workflow: plan`,
    - `T03`: todo s `workflow: plan`.
  - Id ve tvaru `M01-S01-T01` atd., soubory `M01-S01-T01-<slug>.md` s `## Zadání`.
- `with_trace=True`: vytvoří `.factory/trace.db` přes `TaskRunStore`. `M02-S01-T02` dostane `claim` běh se stavem `running` a `pid=os.getpid()`. `M02-S01-T03` dostane dokončený běh `succeeded` a `save_pr(... state="open")`. Použij stejné pole jako `trace_fixture._run`, případně ho zkopíruj. Trace DB se nepřidává do commitu (zapiš ji až po commitu).
- Konstanty id jako moduly-level `str`.

### Python: `aifactory/tests/web/test_web_backlog.py` (nový)

Klient: `TestClient(create_app(root, static_dir=tmp_path/"nostatic"), base_url="http://127.0.0.1:4700")`. Každou odpověď ověř přes `envelope_problems(body) == []` a stavový kód.

1. `test_tree_follows_levels_and_board_states`: GET `/api/backlog` s `with_trace=True`. Ověř:
   - `levels`,
   - strom `items[0].level == "module"`, `children[0].level == "step"` a tasky pod ním,
   - `board_state` všech tasků: T01 done, T02 ready, T03 blocked, T04 cancelled, M02-T01 todo, M02-T02 running, M02-T03 in review,
   - `states == BOARD_STATES`, `owners == ["alice","bob"]`,
   - `workflows` obsahuje `custom-flow` i `plan-build`,
   - `steps` obsahuje obě stepy,
   - `blocks` u `M01-S01-T02` je `["M01-S01-T03"]`.
2. `test_custom_levels`: `levels=[area, task]` s tasky přímo pod `area`. Úroveň kontejneru je `area` a `steps` obsahuje oblasti.
3. `test_filters`: `status=ready` vrací jen T02 (strom obsahuje jen M01 a jeho step), `owner=bob` jen tasky M02, kombinace obou, `status=running` s trace. `status=bogus` → 400 `invalid_status`.
4. `test_no_trace_db_means_no_runtime_states`: bez trace DB je M02-T02 `ready` a M02-T03 `ready` a DB se nevytvoří.
5. `test_task_detail`:
   - `body` obsahuje zadání,
   - `depends` T03 → `[{id: T02, kind: "task", state: "ready", …}]`,
   - `blocks` T02 → T03,
   - `runs` a `prs` u M02-T03 (s trace) mají délku 1,
   - neznámé id → 404 `unknown_task`.
6. `test_add_task_writes_only_backlog_and_does_not_commit`:
   - POST `/api/backlog/tasks` `{step: "M01-S01", title: "Nový task", workflow: "plan", depends_on: ["M01-S01-T01"], body: "Text"}` → 200,
   - `data.task.id == "M01-S01-T05"`, soubor existuje a obsahuje `status: todo`,
   - `git status --porcelain` ukazuje jen cesty pod `backlog/`,
   - `git rev-list --count HEAD` je pořád 1.
7. `test_add_rejects_broken_backlog`: `depends_on: ["NOPE"]` → 422 `backlog_invalid`, `error.issues[0].code == "unknown_ref"`, žádný nový soubor (`git status --porcelain` je prázdný). Ověř skutečný kód issue v `backlog/validate.py`.
8. `test_edit_and_assign_workflow`:
   - edit `title` a `workflow: "custom-flow"` → soubor obsahuje obojí,
   - `clear_workflow: true` → klíč `workflow:` ze souboru zmizí,
   - `status: "cancelled"` → board_state cancelled,
   - `status: "done"` → 400 `invalid_status`,
   - `{}` → 400 `no_changes`.
9. `test_link_add_remove_and_cycle`:
   - link T01 `depends_on: [M01-S01-T03]` vytvoří cyklus → 422 `backlog_invalid`, issue `cycle`, bajty souboru se nezměnily,
   - link M02-T01 `depends_on: ["M01-S01-T02"]` → 200 a `blocks` u T02 ho obsahuje,
   - `remove: true` ho odebere.
10. `test_bad_bodies`:
    - ne-JSON → 400 `usage_error`,
    - JSON pole → 400 `usage_error`,
    - `title: 5` → 400 `invalid_value`,
    - neznámý klíč → 400 `usage_error`,
    - chybějící `step` → 400 (`usage_error` nebo `invalid_value`, jeden z nich zvol a dodrž).
11. `test_api_calls_core_functions`: `monkeypatch.setattr("aifactory.backlog.add_task", spy)` (a totéž pro `edit_task` a `link_task`). Spy zaznamená argumenty a zavolá originál. Ověř, že API předalo stejné keyword argumenty jako CLI (`task_id`, `slug`, `workflow`, `writes`, `depends_on`, `related`, `body`).

Všechny funkce mají typové anotace kvůli mypy strict. `Any` z `response.json()` stačí anotovat jako `Any`.

### Frontend (vitest)

- `lib/backlog.test.ts`: `fetchBacklog({status: 'in review', owner: 'bob'})` volá `/api/backlog?status=in+review&owner=bob` (nebo `%20`, podle `URLSearchParams`). `addTask` posílá POST s JSON. Chyba s `issues` vyhodí `ApiError` s `issues`.
- `lib/api.test.ts`: doplnit, že `ApiError.issues` se naplní z obálky.
- `lib/router.test.ts`: `taskHref` a `parseRoute('#/backlog/M01-S01-T01')`.
- `test/backlogFixtures.ts`: `backlogData()`, `taskNode(over)`, `taskDetail(over)` se stejnými tvary jako API.
- `components/backlog/BacklogTree.test.ts`: vykreslí úrovně z `levels` (štítek „module“ a „step“), odkazy `#/backlog/<id>`, stav a prázdný strom.
- `components/backlog/KanbanBoard.test.ts`: 7 sloupců v pořadí `BOARD_STATES`, karty ve správném sloupci, počty.
- `components/backlog/BacklogFilters.test.ts`: emituje `update:filters` (`{status:'blocked'}`, prázdná hodnota znamená `undefined`) a `update:mode`.
- `components/backlog/TaskDetail.test.ts`: hlavička, zadání, „Závisí na“ a „Blokuje“, běhy s `runHref`, PR odkaz. Klik na unlink emituje `link` s `remove: true`. Link-add emituje `{depends_on:[id]}`. Assign emituje workflow nebo `null`. `IssueList` se zobrazí při `error`.
- `components/backlog/TaskForm.test.ts`: add emituje správný `AddTaskInput` (writes z řádků, depends_on z čárek, bez prázdných polí). Edit posílá jen změněná pole. Status select je u done disabled. Výběr „zděděné“ vede na `clear_workflow: true`.
- `views/BacklogView.test.ts`:
  - načte `/api/backlog` a přepne kanban,
  - změna filtru pošle nový fetch s query,
  - `#/backlog/<id>` načte detail,
  - neúspěšný zápis (422 s `issues`) ukáže `[data-test="write-error"]` s kódem issue,
  - úspěšné založení naviguje na `#/backlog/<nové id>`.
  
  Po každém testu vrať hash na `#/backlog`, stejně jako RunsView.test.

## Ověření

Spouštěj z kořene repa a hodnoť podle exit kódu:

```bash
just test          # vitest + vue-tsc + pytest
just typecheck     # mypy --strict
just lint          # ruff check + ruff format --check
just web-build     # obnoví aifactory/src/aifactory/web/static
```

Ručně (volitelně): `just dash`, otevřít Backlog, přepnout strom a kanban, založit task s neexistující závislostí (chyba `unknown_ref` v UI), přidat vazbu a přiřadit workflow. `git status` pak ukáže jen změny v `backlog/` a `git log` žádný nový commit.

## Soubory

Nové:

- `aifactory/src/aifactory/web/backlog.py`
- `aifactory/tests/web/backlog_fixture.py`
- `aifactory/tests/web/test_web_backlog.py`
- `aifactory/web/src/lib/backlog.ts`
- `aifactory/web/src/lib/backlog.test.ts`
- `aifactory/web/src/test/backlogFixtures.ts`
- `aifactory/web/src/components/backlog/`: `StateChip.vue`, `BacklogFilters.vue`, `BacklogTree.vue`, `TreeNode.vue`, `KanbanBoard.vue`, `IssueList.vue`, `TaskForm.vue`, `TaskDetail.vue`, k nim testy `*.test.ts`
- `aifactory/web/src/views/BacklogView.test.ts`

Změněné:

- `aifactory/src/aifactory/web/app.py`
- `aifactory/web/src/lib/api.ts` (+ `api.test.ts`)
- `aifactory/web/src/lib/router.ts` (+ `router.test.ts`)
- `aifactory/web/src/views/BacklogView.vue`
- případně `aifactory/web/src/App.test.ts` (stub fetch)
- `aifactory/src/aifactory/web/static/**` (build)
