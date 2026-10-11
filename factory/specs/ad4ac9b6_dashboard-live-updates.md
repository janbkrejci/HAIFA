# Plán: živé aktualizace dashboardu (SSE + kurzorový tail trace)

## Zadání

Dashboard (`factory obs` / `just dash`) má bez obnovení stránky ukazovat:
- změny souborů v `backlog/**` a `.factory/**` (z CLI i z editoru) do 2 s,
- nové fáze a události z trace DB na obrazovce Běhy, načítané kurzorem na `rowid` (žádné opakované čtení celé tabulky),
- obrazovky Backlog a Review se po události obnoví jen v dotčené části.

Mimo rozsah: vzdálený přístup, více uživatelů. **`vendor/` a `prototype/` se nemění.**
Hotovo = testy (změna souboru → událost; nový řádek v trace → objeví se v odpovědi s kurzorem) + `just test`, `just typecheck`, `just lint` projdou.

## Co už existuje (zjištěno z kódu)

- `aifactory/src/aifactory/web/app.py` – Starlette app, `create_app(repo, *, static_dir=None)`, `app.state.repo`, `app.state.launcher`. Všechny API odpovědi v obálce `envelope_ok/envelope_fail`. `TrustedHostMiddleware` (127.0.0.1, localhost).
- `web/runs.py` – `run_events(repo, run_id, after, limit)` už stránkuje `events` přes `rowid > ?` (vrací `events`, `cursor`, `has_more`). `run_detail` čte vše (phases, gates, envelopes, agent_sessions, agent events). `_phases(conn, run_id, agents, agent_events)` počítá tokeny/cost/harness z `agent_start`/`agent_end` událostí. `_open_run` otevírá `TaskRunStore` přes `existing_store(repo)` (vrací `None`, když DB neexistuje).
- `web/server.py` – `serve()` spouští `uvicorn.Server` na 127.0.0.1.
- Trace DB: `aifactory/engine/tracer.py` (WAL, `isolation_level=None`). Tabulka `phases` se **upsertuje** (`phase_upsert`, `ON CONFLICT(phase_id) DO UPDATE` status/attempt/error/ended_at) – rowid fáze se nemění, změna stavu se kurzorem nepozná. Runner (`engine/runner.py`) zapisuje `phase_start` event → upsert; na konci `phase_end` event **před** upsertem stavu. `gate_results` má `id` autoincrement, `envelopes` rowid.
- `task_runs`, `task_prs` (`aifactory/run/store.py`) jsou ve **stejné** DB.
- Výchozí cesty (`aifactory/config/settings.py`): `backlog_dir = "backlog"`, `worktrees_dir = ".factory/worktrees"`, `trace_db = ".factory/trace.db"` (`LocalSettings.trace_db_path(root)`), session runtime `.factory/data` (`aifactory/run/task.py: FACTORY_DATA_DIR`). **Trace DB, worktrees i data leží uvnitř `.factory/`** – watcher je musí vynechat (worktrees = celé checkouty, data = neustále psané logy).
- Frontend `aifactory/web/src/`: Vue 3 + vitest + happy-dom. `lib/api.ts` (`getApi`, `postApi`), `lib/runs.ts` (`fetchRun`, `fetchAllEvents` – smyčka přes `/events?after=`), `views/RunsView.vue`, `views/BacklogView.vue`, `views/ReviewView.vue`, `App.vue` (config status banner obnovovaný na `focus`), `components/backlog/TaskDetail.vue` (watch na `props.detail` resetuje `editing` – živá obnova by zavřela rozeditovaný formulář, viz níže).
- Testy `aifactory/tests/web/`: `trace_fixture.py` (`make_trace_db(path, pid)`, `make_repo`, `T1`, `T2`, běhy `r-ok`, `r-fail`, `r-run`), `web_repo.py` (`git_repo`), klient `TestClient(create_app(root, static_dir=tmp_path/"nostatic"), base_url="http://127.0.0.1:4700")`. Pytest běží s `-n auto`.
- Závislosti: stdlib + starlette + uvicorn; žádný `watchfiles`. **Nepřidávej novou runtime závislost** – watcher je polling (stdlib), interval 0,5 s splní limit 2 s.

## Návrh

### 1. Backend: `aifactory/src/aifactory/web/live.py` (nový modul)

#### 1a. `LiveWatcher` – synchronní, deterministicky testovatelný

```python
@dataclass(frozen=True)
class LiveEvent:
    kind: str            # "files" | "trace"
    data: dict[str, Any]

class LiveWatcher:
    def __init__(self, repo: Path) -> None: ...
    def poll(self) -> list[LiveEvent]: ...   # první volání = baseline, vrací []
    def close(self) -> None: ...
```

- Kořen: `gitops.main_root(repo)`, při `TaskRunError` `repo.resolve()` (stejně jako `existing_store`).
- Sledované kořeny: `<root>/<backlog_dir>` (area `"backlog"`) a `<root>/.factory` (area `"factory"`). `backlog_dir` z `.factory/config.yaml` (načti přes existující loader settings, při chybě konfigurace fallback `"backlog"`); nastavení načítej při každém `poll`, jen pokud se změnil `.factory/config.yaml` (nebo prostě v konstruktoru + při změně configu – stačí jednoduché řešení).
- Vyloučit (prune při `os.walk`/`os.scandir`, nesestupovat dovnitř): `worktrees_dir`, `.factory/data`, trace DB soubor a jeho `-wal`, `-shm`, `-journal` (cesta z `load_local(root).trace_db_path(root)`; pokud leží mimo sledované kořeny, nic nevadí). Dále skryté dočasné soubory editorů netřeba řešit – stačí ignorovat názvy končící `~`, `.swp`, `.swx` a adresáře `__pycache__`.
- Snapshot: `dict[relposix, (st_mtime_ns, st_size)]`. Diff proti předchozímu → změněné/nové/smazané cesty. Pokud neprázdné: `LiveEvent("files", {"areas": sorted(areas), "paths": sorted(paths)[:200], "truncated": len(paths) > 200})`. Cesty relativní ke kořeni repa (`backlog/M01-core/...md`, `.factory/config.yaml`).
- Trace: pokud DB existuje, drž **jedno** read-only spojení `sqlite3.connect(f"file:{db}?mode=ro", uri=True, check_same_thread=False)` (poll běží v threadpoolu, nemusí to být vždy stejné vlákno). Pokud DB zatím neexistuje, zkus ji otevřít v dalším pollu. Chyby `sqlite3.Error` → zavři spojení, zkus znovu příště, nevyhazuj.
  - `PRAGMA data_version` – když se nezměnil, nic nedělej (levné). Při změně:
    - `SELECT MAX(rowid) FROM events` a `SELECT MAX(rowid) FROM phases` (tabulky nemusí existovat – ošetři `_has_table` z `runs.py`, případně ho přesuň/importuj).
    - `run_ids`: `SELECT DISTINCT adw_id FROM events WHERE rowid > ?` s posledním známým maximem (kurzor, ne celá tabulka).
    - `task_ids`: otisk malých tabulek `task_runs` (`run_id, task_id, state, ended_at, head_sha`) a `task_prs` (`branch, task_id, state, updated_at`) – načti, porovnej s předchozím dictem po řádcích a vrať `task_id` změněných/nových/smazaných řádků. Doplň i `task_id` běhů z `run_ids` (mapuj přes načtený `task_runs`).
    - Pokud cokoli z toho je nové/změněné, emituj `LiveEvent("trace", {"events": max_ev, "phases": max_ph, "run_ids": [...], "task_ids": [...], "runs_changed": bool})`. `runs_changed` = změnil se otisk `task_runs`/`task_prs`.
  - Pozor: WAL změny jiného procesu `data_version` spolehlivě zachytí; spojení nesmí držet otevřenou read transakci (po každém dotazu `fetchall`, autocommit).

#### 1b. `LiveHub` – asynchronní rozesílání

```python
class LiveHub:
    def __init__(self, repo: Path, *, interval: float = 0.5) -> None
    async def subscribe(self) -> asyncio.Queue[LiveEvent | None]
    def unsubscribe(self, queue) -> None
    async def aclose(self) -> None
    def publish(self, event: LiveEvent) -> None     # i pro zápisy přímo z API (volitelné)
```

- Polling task (`asyncio.create_task`) se spustí při prvním odběrateli a zastaví, když odejde poslední (ať ostatní testy a nečinný server nic nepollují). Smyčka: `events = await run_in_threadpool(watcher.poll)`; pro každý `publish`; `await asyncio.sleep(interval)`. Watcher vytvoř při startu tasku (baseline), `close()` při zastavení.
- Každá událost dostane rostoucí `seq` (int) a přidá se do `data` jako `"seq"`.
- Fronty `asyncio.Queue(maxsize=100)`; při plné frontě frontu vyprázdni a vlož jedinou událost `LiveEvent("resync", {})` (klient pak znovu načte aktuální obrazovku) – pomalý klient nesmí blokovat ostatní.
- `aclose()` pošle všem `None` (konec streamu) a zruší polling task. Volá se z lifespanu při shutdownu.

#### 1c. SSE endpoint v `app.py`

- `GET /api/live` → `StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})`.
- Generátor: nejdřív `retry: 2000\n\n` a `event: hello\ndata: {"interval": ...}\n\n`; pak smyčka `await asyncio.wait_for(queue.get(), timeout=15)` → při timeoutu `: ping\n\n`; `None` → konec. Formát události: `event: <kind>\ndata: <json.dumps(data)>\n\n`. `finally: hub.unsubscribe(queue)`.
- `create_app(repo, *, static_dir=None, live_interval: float = 0.5)`: `app.state.live = LiveHub(app.state.repo, interval=live_interval)`; Starlette `lifespan` (asynccontextmanager) na shutdown volá `await app.state.live.aclose()`.
- Doplň docstring modulu `app.py` o `/api/live` a nový tail endpoint (viz 2).
- `server.py`: v `uvicorn.Config` nastav `timeout_graceful_shutdown=2`, jinak otevřené SSE spojení drží Ctrl+C `factory obs`.

### 2. Backend: kurzorový tail běhu (`web/runs.py` + route)

Nová funkce `run_tail(repo, run_id, *, events_after, phases_after, gates_after, envelopes_after, open_phases: list[str], limit=DEFAULT_EVENTS_LIMIT) -> JsonDict` a route `GET /api/runs/{run_id}/tail?events=&phases=&gates=&envelopes=&open=<phase_id,...>&limit=` (parsování přes `_int_param`; `open` čárkami oddělený seznam, max 50 položek).

Vrací:
```json
{
  "run": <summary jako list_runs/run_summary – jeden řádek>,
  "session": <řádek sessions pro run nebo null>,
  "events": [...],            // rowid > events, ORDER BY rowid LIMIT limit (+has_more), jako run_events
  "phases": [...],            // viz níže, stejný tvar jako run_detail.phases
  "gates": [...],             // gate_results.id > gates, stejný tvar jako _gates
  "envelopes": [...],         // envelopes.rowid > envelopes, stejný tvar jako _envelopes (+ vrať rowid)
  "agents": [...],            // _agent_sessions (malá tabulka, per run)
  "usage_delta": {"read": n, "written": n},   // _usage jen z nových agent_end událostí této stránky
  "cursors": {"events": n, "phases": n, "gates": n, "envelopes": n},
  "has_more": bool
}
```

- Fáze: vrať řádky `phases` (s `rowid`) kde `adw_id = ? AND (rowid > :phases_after OR phase_id IN (<phase_id z nově vrácených událostí>) OR phase_id IN (<open>) OR status = 'running')`. Důvod: upsert nemění rowid; `open` = fáze, které klient drží jako `running` – tím se zachytí i přechod running→success, který runner zapíše až **po** `phase_end` eventu. Tokeny/cost/harness pro tyto fáze spočítej jako `_phases`, ale agent eventy načti jen `WHERE adw_id = ? AND phase_id IN (...) AND type IN ('agent_start','agent_end')` – refaktoruj `_agent_events(conn, run_id, phase_ids: list[str] | None = None)` a `_phases(..., phase_filter)` tak, aby `run_detail` fungoval beze změny výstupu.
- Kurzor fází = `MAX(rowid)` ze všech vrácených řádků nebo `phases_after`. Stejně pro gates (`id`) a envelopes (`rowid`). `_gates`/`_envelopes` rozšiř o volitelný parametr `after` (výchozí 0 → dnešní chování) a do výstupu přidej `rowid`/`id` (id už tam je).
- `run_detail` rozšiř o `"cursors": {...}` (maxima vrácených řádků), aby klient mohl po prvním plném načtení přejít na tail. Existující klíče se nemění (testy `test_web_runs.py` musí dál procházet).
- Neexistující tabulka = prázdný výsledek, kurzor beze změny. Neznámý běh = `unknown_run` 404 (přes `_open_run`).

### 3. Frontend

#### 3a. `web/src/lib/live.ts` (nový)
- Typy `LiveFilesEvent {seq, areas: ('backlog'|'factory')[], paths: string[], truncated: boolean}`, `LiveTraceEvent {seq, events, phases, run_ids, task_ids, runs_changed}`.
- Jedno sdílené `EventSource('/api/live')` pro celou aplikaci (lazy, reference counting): `onLive(handler: {files?, trace?, resync?}): () => void` (vrací unsubscribe). Při `error`/reconnectu EventSource (prohlížeč se sám znovu připojí díky `retry`) zavolej po znovupřipojení `resync` handlery (po `hello`, které nepřišlo jako první), protože mezitím mohly události propadnout.
- `useLive(handlers)` composable: `onMounted` subscribe, `onBeforeUnmount` unsubscribe.
- Pomocné čisté funkce (unit-testovatelné): `touchesTask(paths, taskId)` (některá cesta má basename začínající `taskId` – soubory tasků jsou `<id>-<slug>.md`), `touchesContainer(paths, containerId)` (některý segment cesty začíná `containerId-` nebo je `containerId`), `touchesWorkflows(paths)` (`.factory/workflows/` nebo `.factory/config.yaml`).
- Debounce: více událostí do 300 ms sluč do jedné obnovy (editor zapisuje víc souborů naráz).
- Když `EventSource` v prostředí není (happy-dom v testech), `onLive` nic nedělá – testy si ho mockují přes `vi.stubGlobal('EventSource', FakeEventSource)`.

#### 3b. Běhy (`views/RunsView.vue`, `lib/runs.ts`)
- `lib/runs.ts`: typ `RunTail`, `RunCursors`, funkce `fetchRunTail(runId, cursors, openPhases)`; `RunDetail` rozšířit o `cursors`.
- `lib/runs.ts` (nebo nový `lib/runTail.ts`): čistá funkce `applyTail(detail, events, tail) -> {detail, events}` – merge fází podle `phase_id` (nahradit/přidat, řadit dle `seq`), append gates/envelopes (dedupe podle id), `run` a `session` nahradit, `agents` nahradit, `usage` sečíst s `usage_delta`, eventy appendnout (dedupe podle `rowid`). Unit testy.
- RunsView detail: po `loadDetail` ulož cursors. `useLive({trace})`: když je otevřený detail a `trace.run_ids` obsahuje `runId` **nebo** `trace.task_ids` obsahuje úlohu běhu **nebo** v detailu je nějaká fáze `running` → `fetchRunTail` (smyčka, dokud `has_more`), `applyTail`. Nezapínat `loading` (žádné blikání „Načítám…“), chybu tailu jen do `error` bez mazání detailu. Souběh: pokud tail právě běží, nastav příznak „ještě jednou“ a po dokončení zopakuj.
- RunsView seznam: na `trace` s `runs_changed` nebo neprázdným `run_ids` tiše přenačti `fetchRuns(filters)` (seznam je malý; to není čtení `events`).
- `resync` → `reload()`.
- `RunDetail.vue` beze změny API (dostává `detail` a `events`).

#### 3c. Backlog (`views/BacklogView.vue`)
- `useLive`:
  - `files` s area `backlog`, nebo `factory` a `touchesWorkflows`, nebo `trace` s `runs_changed` (board_state závisí na bězích):
    - seznam/kanban (`!taskId && !isGraph && !isNew`): tiché `fetchBacklog(filters)` → `data`.
    - detail tasku: vždy tiše obnov `data` (strom vpravo/levé menu); `fetchTask(id)` jen když `touchesTask(paths, id)` nebo trace `task_ids` obsahuje `id` nebo `truncated`.
    - graf: `fetchGraph(graphId)` jen když `touchesContainer(paths, graphId)` nebo trace `task_ids` má nějaký task s prefixem `graphId` nebo `truncated`.
    - formulář nového tasku (`isNew`): neobnovovat nic kromě `data` (workflows/steps do selectů).
  - Během `busy` (zápis z UI) obnovu odlož na po dokončení zápisu (zápis sám data obnovuje).
- „Tiché“ = nenastavuj `loading`, nemaž `error` z předchozí akce uživatele, chyby tiché obnovy zobraz do `error`.
- `components/backlog/TaskDetail.vue`: watch na `props.detail` smí resetovat `editing` a `workflowChoice` jen při změně `task.id`; při stejném id a `editing === true` nesahat na rozepsaný stav, při `editing === false` aktualizuj `workflowChoice`. (Jinak živá obnova zavře rozeditovaný formulář.) Uprav/doplň test v `TaskDetail.test.ts`.

#### 3d. Review (`views/ReviewView.vue`)
- `useLive`:
  - `trace` s `runs_changed` nebo `files` area `backlog` (vlastníci modulů) → tichý `fetchReviews(owner)` → `list` (bez logiky „me“ defaultu – ta běží jen při prvním načtení).
  - Otevřený detail `taskId`: `fetchReview(taskId)` jen když `trace.task_ids` obsahuje `taskId`, nebo `files` a `touchesTask(paths, taskId)`. Ne pokud právě běží akce (`busy`).
  - `resync` → dosavadní reload.

#### 3e. App.vue
- `useLive({files: e => e.areas.includes('factory') && refreshConfig()})` – banner uncommitted config se obnoví živě. Volitelně malý indikátor spojení není nutný.

### 4. Testy

#### Python (`aifactory/tests/web/`)
Nový `test_web_live.py`:
1. `LiveWatcher` na repu z `make_repo`/`make_trace_db` (tmp_path):
   - první `poll()` → `[]`; zápis do `backlog/M01-core/S01-model/M01-S01-T01-schema.md` (změň obsah i délku – mtime granularita!) → `poll()` vrátí `files` s `areas == ["backlog"]` a danou cestou; další `poll()` → `[]`.
   - zápis do `.factory/config.yaml` → area `factory`.
   - zápis do `.factory/worktrees/x/foo`, `.factory/data/x.jsonl`, do trace DB (`-wal`) → **žádná** `files` událost.
   - `INSERT INTO events` pro `r-run` (samostatné `sqlite3` spojení s commitem) → `poll()` vrátí `trace` s `run_ids == ["r-run"]`, `task_ids` obsahuje `T2`, `events` = nový max rowid.
   - `UPDATE task_runs SET state=...` → `trace` s `runs_changed` True a příslušným `task_id`.
   - repo bez trace DB: `poll()` nepadá; po vytvoření DB začne hlásit.
2. `run_tail` přes `TestClient`: `GET /api/runs/r-ok` → vezmi `cursors`; `GET /api/runs/r-ok/tail?events=<c>&phases=<c>...` → prázdné `events`, stejné kurzory; vlož nový řádek `events` a novou fázi → tail vrátí právě ty řádky a posune kurzory; druhé volání s novými kurzory je prázdné. Upsert (`UPDATE phases SET status='success'`) fáze předané v `open=` → fáze je ve výsledku se novým stavem. `usage_delta` z nového `agent_end`. Neznámý běh → 404 `unknown_run`. `envelope_problems(body) == []`.
3. SSE end-to-end: spusť `uvicorn.Server(uvicorn.Config(create_app(repo, static_dir=..., live_interval=0.1), host="127.0.0.1", port=<volný port z socket.bind(("127.0.0.1",0))>, log_level="warning"))` ve vlákně (počkej na `server.started`), otevři `http.client.HTTPConnection(...).request("GET", "/api/live", headers={"Host": "127.0.0.1"})`, přečti `hello`, pak změň soubor backlogu a čti řádky, dokud nepřijde `event: files` (timeout socketu 5 s; assert do 2 s od zápisu). Nakonec `server.should_exit = True`, `join(timeout=5)`. **Nepoužívej `TestClient` pro nekonečný stream** – bufferuje celé tělo a zasekne se. Test označ `@pytest.mark.xdist_group("live")` pro jistotu.
4. Rozšiř `test_web_runs.py` (nebo nový test): `run_detail` obsahuje `cursors` a dosavadní výstup je beze změny.
5. `test_web_server.py`: pokud testuje `uvicorn.Config`, uprav na `timeout_graceful_shutdown`.

#### Frontend (vitest)
- `lib/live.test.ts`: `touchesTask`, `touchesContainer`, `touchesWorkflows`; `onLive` s `FakeEventSource` (dispatch `files`/`trace`/`hello`, unsubscribe zavře zdroj při 0 odběratelích, debounce s `vi.useFakeTimers`).
- `lib/runs.test.ts` (nový): `applyTail` – merge fází podle `phase_id`, dedupe eventů podle `rowid`, sčítání usage.
- `views/RunsView.test.ts`: po `trace` události s `run_ids: [runId]` se volá `/api/runs/<id>/tail?events=...` (ne `/events` celé), nová událost je v DOM.
- `views/BacklogView.test.ts`: `files` událost se změnou jiného tasku obnoví seznam, ale **ne** `fetchTask` otevřeného detailu; změna vlastního souboru detail obnoví.
- `views/ReviewView.test.ts`: `trace` s cizím `task_ids` neobnoví detail, s vlastním ano.
- `TaskDetail.test.ts`: nový `detail` se stejným id při `editing` nezavře formulář.
- Existující testy, které mountují views bez `EventSource`, musí dál projít (lazy/no-op bez `EventSource`).

### 5. Build a dokumentace
- Po změně frontendu spusť `just web-build` – `aifactory/src/aifactory/web/static/` je commitnutý build (index.html + assets); nový build nahradí `index-*.js/css`. Staré hashované soubory smaž (build to dělá, ověř `git status`).
- `app_docs/` / `docs/`: pokud existuje dokument dashboardu (`grep -rl "factory obs" ../docs ../app_docs`), doplň odstavec o živých aktualizacích a endpointech `/api/live`, `/api/runs/{id}/tail`. Není povinné pro gate.

## Soubory

| Soubor | Změna |
|---|---|
| `aifactory/src/aifactory/web/live.py` | nový: `LiveEvent`, `LiveWatcher`, `LiveHub` |
| `aifactory/src/aifactory/web/app.py` | `/api/live` (SSE), `/api/runs/{run_id}/tail`, lifespan, `live_interval`, docstring |
| `aifactory/src/aifactory/web/runs.py` | `run_tail`, `cursors` v `run_detail`, parametry `after`/`phase_ids` v helperech |
| `aifactory/src/aifactory/web/server.py` | `timeout_graceful_shutdown=2` |
| `aifactory/web/src/lib/live.ts` (+ test) | nový |
| `aifactory/web/src/lib/runs.ts` (+ `runs.test.ts`) | `fetchRunTail`, `applyTail`, typy |
| `aifactory/web/src/views/RunsView.vue`, `BacklogView.vue`, `ReviewView.vue` (+ testy) | živé obnovy dle 3b–3d |
| `aifactory/web/src/App.vue` | banner config status na `files`/`factory` |
| `aifactory/web/src/components/backlog/TaskDetail.vue` (+ test) | nereset editace při stejném task id |
| `aifactory/tests/web/test_web_live.py` | nový |
| `aifactory/src/aifactory/web/static/**` | rebuild (`just web-build`) |

## Ověření

1. `just test` (spouští i `web-test`: vue-tsc + vitest, pak pytest).
2. `just typecheck` (mypy – `live.py` plně anotovat; `asyncio.Queue[LiveEvent | None]`).
3. `just lint` (ruff check + format --check; spusť `cd aifactory && uv run ruff format .` před kontrolou).
4. Ruční kontrola: `just dash`, otevřít Backlog, v jiném terminálu `just factory task edit ...` nebo upravit `.md` v editoru → do 2 s se změní strom; během `factory task run` sledovat Běhy → přibývají události bez F5; v DevTools Network jen `/tail?events=N` požadavky, žádné `/events?after=0`.

## Rizika / poznámky pro buildera
- Nepoužívej `TestClient` na `/api/live` (nekonečný stream) – end-to-end test přes skutečný uvicorn ve vlákně.
- mtime na macOS/APFS má ns rozlišení, ale v testech měň i velikost souboru, ať diff nezávisí na granularitě.
- Polling nesmí sestoupit do `.factory/worktrees` ani `.factory/data` (výkon + falešné události z vlastních běhů).
- Read-only SQLite spojení nesmí držet transakci (jinak blokuje checkpoint WAL); žádné `BEGIN`.
- `vendor/` a `prototype/` neměnit.
