# Plán: úkol 3.2 – obrazovka Běhy (seznam, detail, trace, náklady, zastavení)

## Kontext (co už existuje)

- Backend dashboardu: `aifactory/src/aifactory/web/app.py` (Starlette, `/api/health`, odpovědi v obálce `envelope_ok` / `envelope_fail` z `aifactory.skill.envelope`, `app.state.repo` = kořen repa). Chyby HTTP se na `/api/*` převádějí na obálku (`_http_error`, `_internal_error`).
- Frontend: `aifactory/web/src/` (Vue 3 + vitest + happy-dom, alias `@` → `src`). `views/RunsView.vue` je zatím `EmptyScreen`. Router `lib/router.ts` zná jen `#/<screen>`. API klient `lib/api.ts` má jen `getApi`.
- Build frontendu jde do `aifactory/src/aifactory/web/static/` a **je commitnutý v gitu** (test `test_packaged_build_is_served`). Po změnách frontendu spusť `just web-build` a commitni nový build (staré hashované assety smaž – `emptyOutDir: true` to udělá).
- Tabulka `task_runs` (a `task_prs`) v trace DB: `aifactory/src/aifactory/run/store.py` (`TaskRunStore`, stavy `running|succeeded|failed|aborted`, `all_runs()`, `get()`, `pr_for_branch()`, `_reap()` přepíše mrtvé `running` na `aborted`). Cesta k DB: `load_local(main).trace_db_path(main)` (výchozí `.factory/trace.db`); vzor otevření bez vytvoření DB je `_existing_store(repo)` v `run/task.py`.
- **`run_id` z `task_runs` == `adw_id` v trace tabulkách** (`run_task` volá `run_workflow(..., adw_id=row.run_id)`).
- Trace tabulky (`engine/tracer.py`): `sessions(total_tokens,total_cost,status,...)`, `phases(seq,name,kind,owner,status,attempt,retries,error,started_at,ended_at)`, `events(type: phase_start|phase_end|agent_start|agent_end|tool_call|handoff|gate_pass|gate_fail|log|error; payload_json; tokens)`, `envelopes`, `gate_results(violations_json, checks_json)`, `processes(kind 'adw'|'agent', pid, command, ended_at NULL = živý)`, `agent_sessions(agent, coding_agent, model, ...)`.
  - Náklady fáze: event `agent_end` fáze má `tokens` (součet fáze) a `payload.cost`, `payload.usage` (UsageBreakdown).
  - Harness a model fáze: payload eventu `agent_start` fáze (`coding_agent`, `model`); záloha `agent_sessions` podle `phases.owner`. Fáze `kind == "code"` harness/model nemá (null).
- **V CLI zatím žádné zastavení běhu neexistuje.** Zastavení při SIGTERM: engine (`engine/session.py::_finalize_when_killed`) převede SIGTERM na `SystemExit`, uzavře session (`status=fail`) a řádky `processes`; `run/task.py::_execute` v `except BaseException` zavolá `store.finish(run_id, FAILED, ..., "interrupted: ...")`. Dětské procesy agentů (claude/codex/pi) engine sám nezabíjí – sssf `just kill` zabíjí nejdřív děti, pak rodiče, a ověřuje `command` pidu.
- Visualizer (zdroj pohledů, jen ke čtení): `vendor/sssf/apps/visualizer/` – `server/db.ts` (SQL), `shared/types.ts` (typy), `src/components/{SessionTrace,PhaseDetail,StatusChip,StatChip,DetailSection,PhaseDots}.vue`, `src/lib/{format,events,highlight}.ts`. Nemá testy.
- Chybové kódy: každý literál `code` u raise musí být v `aifactory/src/aifactory/skill/codes.py` (`tests/test_skill.py` to hlídá). Skill (`factory --skill`) si nové podpříkazy CLI najde sám.

## Rozhodnutí

1. **Nový stav běhu `stopped`** (`STOPPED` v `run/store.py`). Běh zastavený uživatelem už nesmí přepsat umírající proces na `failed`.
2. **Jedna funkce core `stop_run(repo, run_id)`** v novém `aifactory/src/aifactory/run/stop.py`. Volá ji nový CLI příkaz `factory task stop` i endpoint `POST /api/runs/{run_id}/stop`. Tím je splněno „stejnou funkcí core, jakou používá CLI“.
3. Čtecí API je v novém modulu `aifactory/src/aifactory/web/runs.py` (čisté funkce nad sqlite, bez Starlette), handlery v `app.py` jsou synchronní `def` (Starlette je pouští v threadpoolu – sqlite i čekání při stopu neblokují event loop).
4. Frontend: vlastní komponenty v `web/src/components/runs/`, převzaté a zjednodušené z visualizeru (žádný polling – živé aktualizace jsou 3.7; tlačítko „Obnovit“ stačí).

## Část A – core: zastavení běhu

### A1. `aifactory/src/aifactory/run/store.py`
- Přidej `STOPPED = "stopped"` vedle `RUNNING, SUCCEEDED, FAILED, ABORTED`.
- `finish()`: `UPDATE ... WHERE run_id = ? AND state != 'stopped'` (zastavený běh zůstane zastavený; docstring to řekne).
- Nová metoda `mark_stopped(run_id: str, note: str) -> bool`: v `_txn()` provede `UPDATE task_runs SET state='stopped', ended_at=?, error=? WHERE run_id=? AND state='running'` a vrátí, zda se změnil řádek (`cursor.rowcount == 1`).
- Nová metoda `live_processes(run_id) -> list[tuple[str, str, int, str]]` (kind, name, pid, command) z tabulky `processes` (`adw_id = run_id AND ended_at IS NULL`, `ORDER BY id DESC`). Tabulka nemusí existovat (engine ještě neběžel) → vrať `[]` (ověř přes `sqlite_master`).
- Nová metoda `close_processes(run_id)`: `UPDATE processes SET ended_at=? WHERE adw_id=? AND ended_at IS NULL` (jen když tabulka existuje), a `UPDATE sessions SET status='fail', ended_at=? WHERE adw_id=? AND status='running'` (jen když tabulka `sessions` existuje) – pro případ, že proces už nestihl trace uzavřít sám.
- Uprav module docstring (stav `stopped`).

### A2. `aifactory/src/aifactory/run/stop.py` (nový)
```python
@dataclass
class StopResult:
    run: TaskRunRow            # řádek po zastavení (state == "stopped")
    signalled: list[int]       # pidy, kterým šel SIGTERM
    killed: list[int]          # pidy, které musely dostat SIGKILL
    def to_json(self) -> dict[str, object]: ...

def stop_run(repo: Path, run_id: str, *, timeout: float = 10.0) -> StopResult
def running_run(repo: Path, task_id: str) -> TaskRunRow | None   # pro CLI
```
Postup `stop_run`:
1. Otevři store bez vytváření DB (zveřejni `_existing_store` z `run/task.py` jako `existing_store` a použij ho; `None` → `TaskRunError("unknown_run", ...)`).
2. `store.all_runs()`/`_reap` přes `store.for_task` není potřeba – použij `row = store.get(run_id)`; `None` → `TaskRunError("unknown_run", f"no run {run_id}")`. Pak reap: pokud `row.state == RUNNING` a proces je mrtvý (`_alive(row.pid)` je False), zavolej `store.for_task(row.task_id)` (reapne) a načti znovu.
3. `row.state != RUNNING` → `TaskRunError("run_not_running", f"run {run_id} of task {row.task_id} is {row.state}")`.
4. `row.pid == os.getpid()` → `TaskRunError("run_not_running", "... runs in this process")` (ochrana, aby se dashboard nezabil sám).
5. `store.mark_stopped(run_id, "stopped by user")`; vrátí-li False (souběh – běh právě skončil) → `run_not_running`.
6. Signály – nejdřív děti, pak rodič (jako sssf `just kill`):
   - pro každý řádek `live_processes` s `kind == "agent"`: pokud pid žije a `ps -p <pid> -o command=` (přes `subprocess.run`, exit status 0) obsahuje první slovo uloženého `command`u (název harnessu, např. `claude`/`codex`/`pi`) – jinak pid přeskoč (recyklovaný pid) – pošli `SIGTERM`;
   - pak `SIGTERM` na `row.pid` (proces `factory task run`); `ProcessLookupError` ignoruj.
7. Počkej až `timeout` s (poll po 0,1 s přes `os.kill(pid, 0)`), až všechny signalizované pidy zmizí; co přežije, dostane `SIGKILL` (zapiš do `killed`). Pozn.: zombie potomek testu – viz testy; pro `row.pid` se čeká jen do `timeout`, `ProcessLookupError`/`PermissionError` řeš jako v `_alive`.
8. `store.close_processes(run_id)`; načti `store.get(run_id)`, zavři store, vrať `StopResult`.
- Worktree a větev se nemažou (uklidí `factory task clean` – zastavený běh je `!= RUNNING`, takže ho `clean_worktrees` bere jako ostatní neúspěšné běhy; nic neměň).
- Exportuj `STOPPED`, `StopResult`, `stop_run`, `running_run` z `aifactory/run/__init__.py` (a `__all__`), doplň odstavec do module docstringu.

### A3. `aifactory/src/aifactory/skill/codes.py`
V sekci `# Runs.` přidej:
- `("unknown_run", "2", "no run with this id in the trace database")`
- `("run_not_running", "2", "the run is not running (finished, stopped or aborted)")`
- (pro CLI) `("not_running", "2", "the task has no running run")` – nebo použij `run_not_running`; drž jeden z nich konzistentně a registruj každý použitý literál.

### A4. CLI `factory task stop ID [--run RUN_ID]` (`aifactory/src/aifactory/cli.py`)
- V `_add_task_commands` přidej podpříkaz `stop` (help: „stop the running run of a task“; description: SIGTERM agentům a procesu běhu, běh se označí `stopped`, worktree zůstává). Argumenty: `task_id` (ID), volitelně `--run RUN_ID` (zastaví přesně tento běh; musí patřit tasku, jinak `invalid_value`). Přidej `stop` do smyčky, která přidává `--json` a `--repo`.
- `_task_stop(args, root)`: `run_id = args.run or running_run(root, args.task_id).run_id` (žádný běžící → `TaskRunError("run_not_running", ...)`), pak `stop_run(root, run_id)`. `--json` → `_emit_ok(result.to_json())`, jinak `print(f"stopped run {run_id} of {task_id}")`. Dispatch v `_task` (`if command == "stop"`). Chyby jdou přes stávající `_fail_from_exception` (TaskRunError → exit 2).
- Doplň `TASK_EPILOG`, pokud vyjmenovává příkazy.

## Část B – backend API (`aifactory/src/aifactory/web/`)

### B1. `web/runs.py` (nový) – čtení běhů
Funkce (vše nad `TaskRunStore` z `existing_store(repo)`; když DB neexistuje → prázdné výsledky; trace tabulky mohou chybět → kontrola `sqlite_master`, chybějící tabulka = prázdno; volitelné sloupce přes `PRAGMA table_info` jako `optionalColumn` ve visualizeru `server/db.ts:152`):

- `RUN_STATES = ("running", "succeeded", "failed", "aborted", "stopped")`.
- `list_runs(repo, *, state: str | None, task: str | None) -> dict`:
  - `store.all_runs()` (reapne mrtvé), filtr `state` (neznámý stav → `TaskRunError("invalid_status", ...)` → HTTP 400) a `task` (přesná shoda `task_id`; prázdný řetězec = bez filtru).
  - Každý běh → `run_summary(...)`:
    ```
    {run_id, task_id, task_title|null, workflow, state, branch, started_at, ended_at,
     duration_s (ended_at nebo now − started_at, float|null), tokens (sessions.total_tokens|0),
     cost (sessions.total_cost|0.0), error, note,
     pr: {url, pr_id, state}|null (store.pr_for_branch(branch)),
     phases: [{seq, name, status}]  # pro PhaseDots
    }
    ```
    Sessions a phases dotaž dávkově (`WHERE adw_id IN (...)`), ne N dotazů.
  - `task_title`: načti backlog `load_backlog`/`load_for_edit` z `aifactory.backlog` (jen pokud jde; jakákoli `ConfigError`/`TaskEditError`/OSError → titulky `null`, přidej warning do obálky).
  - Návrat: `{"runs": [...filtrované], "tasks": [id tasků, které mají běh – pro select filtru], "totals": {"backlog": {"cost", "tokens", "runs"}, "tasks": [{"task_id","task_title","cost","tokens","runs"}]}}`. **Součty se počítají ze všech běhů (nefiltrované)**, `tasks` řazené podle `task_id`.
- `run_detail(repo, run_id) -> dict` (neznámý → `TaskRunError("unknown_run")` → 404):
  ```
  {run: run_summary, session: Session|null, usage: {read, written},
   agents: [AgentSession], phases: [PhaseRow], gates: [GateResult], envelopes: [Envelope]}
  ```
  - `PhaseRow` = sloupce `phases` (`ORDER BY seq, rowid`) + `harness`, `model` (z `agent_start` eventu fáze, jinak `agent_sessions` podle `owner`, u `kind=="code"` null), `tokens` a `cost` (z `agent_end` eventu fáze: `tokens`, `payload.cost`; více `agent_end` → sečíst), `usage` (payload.usage nebo null), `duration_s`.
  - `usage` session: jako visualizer `db.ts:486` (`read += input_tokens + cache_write_tokens`, `written += output_tokens` přes všechny `agent_end`).
  - `gates`: `SELECT id, adw_id, phase_id, attempt, gate, passed, violations_json, checks_json, created_at FROM gate_results WHERE adw_id=? ORDER BY id` – JSON sloupce rozparsuj na `violations: list[str]`, `checks: list[{item,ok,note}] | null`.
  - `envelopes`: `... FROM envelopes WHERE adw_id=? ORDER BY created_at, rowid`; `payload` rozparsovaný (nevalidní JSON → ponech řetězec v `payload_raw`).
- `run_events(repo, run_id, *, after: int, limit: int) -> {"events": [...], "cursor": int, "has_more": bool}` – přesně jako visualizer `db.ts:517` (`rowid > after ORDER BY rowid LIMIT limit+1`, limit omez na 1..1000, výchozí 500), `payload` rozparsovaný. Tool calls = eventy `type == "tool_call"`.
- Typy výstupu drž jako `dict[str, Any]`/`TypedDict`; mypy strict musí projít.

### B2. `web/app.py` – routy
Pod `Mount("/api", ...)` přidej:
- `GET /api/runs?state=&task=` → `list_runs`
- `GET /api/runs/{run_id}` → `run_detail`
- `GET /api/runs/{run_id}/events?after=&limit=` → `run_events` (neceločíselné parametry → 400 `usage_error`)
- `POST /api/runs/{run_id}/stop` → `aifactory.run.stop_run(repo, run_id)` a vrať `{"run": run_summary(...)}` (+ `signalled`, `killed`). **Volej přes modulový atribut `aifactory.run.stop.stop_run`** (resp. import modulu), aby test mohl ověřit, že web volá stejnou funkci jako CLI.
- Mapování `TaskRunError` → obálka: `unknown_run` 404, `run_not_running` 409, `invalid_status`/`invalid_value` 400, `invalid_config`/`trace_db_locked` 500/503 – helper `_run_error(exc) -> JSONResponse` v `app.py`. `ConfigError` → 500 `invalid_config`.
- Handlery jako synchronní `def` (Starlette je spustí v threadpoolu).
- Uprav docstring modulu `web/__init__.py`, pokud vyjmenovává endpointy.

## Část C – frontend (`aifactory/web/src/`)

### C1. `lib/api.ts`
- Přidej `postApi<T>(path, body?)` (method POST, JSON) se stejným zpracováním obálky jako `getApi` (vytáhni společnou funkci `readEnvelope`).
- Rozšiř testy v `lib/api.test.ts` o `postApi` (úspěch + chyba s `code`).

### C2. `lib/runs.ts` (nový) – typy a volání
- TS rozhraní odpovídající B1: `RunState`, `RunSummary`, `RunsResponse`, `RunTotals`, `RunDetail`, `PhaseRow`, `GateResult` (s `violations`, `checks`), `Envelope`, `TraceEvent`, `EventsPage`, `AgentSession`, `UsageBreakdown`, `ToolCallPayload`, `AgentStartPayload` (převzít z `vendor/sssf/apps/visualizer/shared/types.ts`, upravit na naše pole).
- `fetchRuns({state, task})`, `fetchRun(id)`, `fetchAllEvents(id)` (stránkuje `after=cursor` dokud `has_more`), `stopRun(id)`.

### C3. `lib/format.ts` a `lib/events.ts` (převzaté z visualizeru `src/lib/format.ts`, `src/lib/events.ts`)
- `fmtDuration(seconds|ms)`, `fmtTokens` (raw < 1k, `1.2k`, `1.23M`), `fmtCost` (`$x.xx` od $1, jinak `$x.xxxx`), `fmtTime` (lokální datum+čas), `prettyJson`.
- `eventLabel(e)`, `argsSummary(args)` pro tool calls.
- Unit testy `lib/format.test.ts`, `lib/events.test.ts`.

### C4. `lib/router.ts` – detail běhu
- Přidej parsování parametru obrazovky: `#/runs/<run_id>` (a volitelně `#/runs/<run_id>/<phase_id>`). Např. `parseRoute(hash) -> { screen, params: string[] }`, `useRouteParams(): Ref<string[]>`, `runHref(runId, phaseId?)`. `parseHash` a stávající chování (`#/runs` → screen runs, neznámé → backlog) zachovej; rozšiř `lib/router.test.ts`.

### C5. Komponenty (`components/runs/`), vzhled podle visualizeru a `style.css`
- `StatusChip.vue` (port `StatusChip.vue`; stavy běhů `running|succeeded|failed|aborted|stopped` i fází `queued|running|success|fail`, česky: běží, úspěch, chyba, přerušeno, zastaveno).
- `StatChip.vue` (port; `cost|tokens|runtime`).
- `PhaseDots.vue` (port).
- `RunsList.vue`: props `runs`, `tasks`, filtry; emituje změnu filtrů. Filtr **stav** (`<select data-test="state-filter">`: vše + 5 stavů) a **task** (`<select data-test="task-filter">` z `tasks`). Tabulka sloupců: Task (id + titul), Workflow, Stav (StatusChip), Začátek, Doba, Tokeny, Náklady, PR (odkaz `target="_blank" rel="noopener"` nebo „—“), fáze (PhaseDots). Řádek/odkaz vede na `runHref(run_id)`. Prázdný stav „Žádné běhy“.
- `CostTotals.vue`: celkem za backlog (náklady, tokeny, počet běhů) + tabulka za tasky.
- `RunDetail.vue`: props `detail: RunDetail`, `events: TraceEvent[]`, `phaseId?`. Hlavička: task, workflow, StatusChip, začátek, doba, tokeny, náklady, read/written, PR odkaz, větev, chyba. **Tlačítko „Zastavit“** (`data-test="stop-run"`) jen pro `state === 'running'`; po `window.confirm` emituje `stop`. Tabulka fází v pořadí `seq`: #, název, stav, harness, model, pokusy, doba, tokeny, náklady; klik vybere fázi (`runHref(runId, phaseId)`).
- `PhaseDetail.vue` (zjednodušený port `PhaseDetail.vue`): pro vybranou fázi sekce **Gates** (gate, prošel/neprošel, pokus, checks `item/ok/note`, violations), **Envelopes** (output_type, agent, pokus, valid, `prettyJson(payload)` v `<pre>`), **Náklady** (rozpad `usage`, pokud je), **Události a tool calls** (čas, typ, `eventLabel`, tokeny; `tool_call` rozbalitelný: args, `result_snippet`, `ok`). `DetailSection.vue` port pro sbalitelné sekce.
- `views/RunsView.vue`: podle `useRouteParams()` zobrazí seznam (načte `fetchRuns` při mountu a při změně filtrů; `<h1>Běhy</h1>`; tlačítko „Obnovit“) nebo detail (`fetchRun` + `fetchAllEvents`; odkaz zpět `#/runs`; na `stop` zavolá `stopRun`, pak detail znovu načte; chybu API (`ApiError.message`) ukáže v banneru). Chyby načtení ukázat, ne spadnout; data bez očekávaných polí (`runs` chybí) → prázdný seznam.
- Pozor: `App.test.ts` stubuje `fetch` tak, že **každá** URL vrací health data a test „switches screens“ čeká `main h1` = „Běhy“. Buď RunsView musí s takovou odpovědí přežít (h1 se renderuje vždy), nebo uprav `stubHealth` v `App.test.ts`, aby vracel data podle URL (`/api/runs` → `{runs:[],tasks:[],totals:{backlog:{cost:0,tokens:0,runs:0},tasks:[]}}`).

### C6. Unit testy komponent (vitest + @vue/test-utils, vzor `App.test.ts`)
- `components/runs/RunsList.test.ts`: vykreslí sloupce a hodnoty (fmtCost/fmtTokens), odkaz na PR, změna selectu stavu/tasku emituje filtr, prázdný stav.
- `components/runs/CostTotals.test.ts`: součet za backlog a řádky tasků.
- `components/runs/RunDetail.test.ts`: fáze v pořadí `seq` se stavem, harnessem a modelem; tlačítko Zastavit jen u `running`; po potvrzení (`vi.spyOn(window,'confirm').mockReturnValue(true)`) emituje `stop`.
- `components/runs/PhaseDetail.test.ts`: gates (passed/failed, checks, violations), envelope JSON, rozbalení tool callu ukáže args a result.
- `views/RunsView.test.ts`: se stubnutým `fetch` načte seznam; v detailu klik na Zastavit volá `POST /api/runs/<id>/stop` a pak znovu `GET /api/runs/<id>`.

### C7. Build
`just web-build` → commitni nový obsah `aifactory/src/aifactory/web/static/` (staré assety zmizí).

## Část D – Python testy

### D1. Fixture trace DB – `aifactory/tests/web/trace_fixture.py` (nový)
Funkce `make_trace_db(repo: Path) -> Path`, která:
- vytvoří `repo/.factory/trace.db` (výchozí `trace_db`; ověř, že `load_local` bez `.factory/local.yaml` dá výchozí cestu – jinak zapiš minimální konfiguraci podle `tests/repo_templates.py`);
- otevře `TaskRunStore` (vytvoří `task_runs`, `task_prs`) a `engine.tracer.Tracer` (vytvoří trace schéma) – nebo `executescript(tracer.SCHEMA)`;
- vloží deterministická data: task `T1` se dvěma běhy (`r-ok` succeeded s PR v `task_prs`, `r-fail` failed), task `T2` s během `r-run` running (pid = pid živého pomocného procesu nebo `os.getpid()` pro čtecí testy – pozor, `all_runs()` reapne běh s mrtvým pidem na `aborted`), sessions s `total_tokens`/`total_cost`, fáze (seq 1 `plan` agent / seq 2 `test` code), eventy `agent_start` (coding_agent `claude`, model), `agent_end` (tokens, cost, usage), `tool_call`, `gate_results` (jeden passed s checks, jeden failed s violations), `envelopes`.

### D2. `aifactory/tests/web/test_web_runs.py` (nový) – testy API přes `TestClient` (vzor `test_web_app.py`, `base_url="http://127.0.0.1:4700"`, `static_dir=tmp_path/"nostatic"`; ke každé odpovědi `envelope_problems(body) == []`)
- seznam: všechna pole (task, workflow, stav, začátek, doba, tokeny, náklady, PR url), řazení od nejnovějšího;
- filtr `?state=failed`, `?task=T1`, neznámý stav → 400 `invalid_status`;
- `totals`: součty za task a za backlog (nefiltrované i při filtru);
- repo bez trace DB → `runs: []`, nuly (a DB se nevytvoří);
- detail: fáze v pořadí se `status`, `harness`, `model`, `tokens`, `cost`; gates s `checks`/`violations`; envelopes; neznámý běh → 404 `unknown_run`;
- events: stránkování `after`/`limit`, `has_more`, tool call payload;
- stop: spusť `subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])`, jeho pid dej do `running` řádku, `POST /api/runs/<id>/stop` → 200, proces skončí (`proc.wait(timeout=...)` – Popen rodič reapne zombie; použij malý `timeout` stopu nebo ověř `proc.poll() is not None`), řádek má `state == "stopped"`; druhý stop → 409 `run_not_running`; stop dokončeného běhu → 409;
- web volá stejnou funkci jako CLI: `monkeypatch.setattr("aifactory.run.stop.stop_run", spy)` (podle toho, jak ji `app.py` referencuje) a ověř volání s `(repo, run_id)`.

### D3. `aifactory/tests/run/test_task_stop.py` (nový) – core + CLI
- `stop_run` zastaví živý proces, označí `stopped`, uzavře `processes`/`sessions` řádky; dětský proces agenta z `processes` (se sedícím `command`, např. `python ...` → uložený command začíná `python`/`sys.executable` basename) dostane SIGTERM dřív; recyklovaný pid (command nesedí) se nezabíjí.
- `store.finish(...)` po `mark_stopped` stav nepřepíše.
- mrtvý pid → `run_not_running` (řádek je `aborted`); neznámý run → `unknown_run`.
- CLI: `factory task stop T2 --json --repo <repo>` → exit 0, obálka `ok`, `data.run.state == "stopped"`; bez běžícího běhu → exit 2, `error.code == "run_not_running"`. Použij existující helpery (`tests/cli_json.py`, `tests/run/run_repo.py`) – podívej se, jak `test_task_run_cli.py` volá CLI.

## Ověření
Z kořene repa (exit status 0 u každého):
1. `just lint` (ruff check + ruff format --check – nové soubory zformátuj `cd aifactory && uv run ruff format .`)
2. `just typecheck` (mypy)
3. `just test` (spouští i `web-test` = `vue-tsc` + vitest, pak pytest)
4. `just web-build` a zkontroluj, že `git status` ukazuje nový build ve `static/`.
5. Ručně (volitelně): `just factory obs` (nebo `just dash`) nad repem s trace DB, `#/runs` a `#/runs/<id>`.

## Pevná omezení
- `vendor/` a `prototype/` se nemění (visualizer jen čti a kopíruj kód do `aifactory/web/src/`).
- Žádný polling/SSE (3.7), žádné spouštění běhů z UI (3.4).
- Nerozbij stávající testy `tests/web/*`, `tests/run/*`, `tests/test_skill.py` (registr kódů), `App.test.ts`.
