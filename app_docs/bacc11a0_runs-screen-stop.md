# Obrazovka Běhy a zastavení běhu (bacc11a0)

Dashboard má teď funkční obrazovku **Běhy**: seznam běhů tasků s filtrem, detail běhu
s fázemi, gates, envelopes a tool calls (port pohledů visualizeru sssf), součty nákladů
a tlačítko **Zastavit**. Zastavení je nová funkce core `aifactory.run.stop.stop_run`,
kterou volá jak nový příkaz `factory task stop`, tak endpoint dashboardu.
Živé aktualizace a spouštění běhů do této změny nepatří.

## Core: zastavení běhu

- `src/aifactory/run/stop.py` (nový) – `stop_run(repo, run_id, timeout=10.0)`:
  1. běh, který je `running`, ale jeho proces už neexistuje, se nejdřív převede na `aborted`;
     běh, který neběží, skončí chybou `run_not_running`, neznámý běh chybou `unknown_run`.
     Proces nemůže zastavit sám sebe.
  2. **Nejdřív** označí běh jako `stopped` (`mark_stopped`, poznámka `stopped by user`),
     aby ho `finish(FAILED)` umírajícího procesu nepřepsal.
  3. Pošle SIGTERM coding agentům z trace tabulky `processes` (jen `kind == "agent"`
     a jen pokud živý pid stále spouští zaznamenaný příkaz – ochrana proti recyklovaným pid),
     potom procesu samotného běhu. Co do timeoutu neskončí, dostane SIGKILL.
  4. Uzavře řádky v `processes` a session ve stavu `running` přepne na `fail`.
  Worktree i větev zůstávají (maže je `factory task clean`). Vrací `StopResult`
  (`run`, `signalled`, `killed`). `running_run(repo, task_id)` vrátí běžící běh tasku.
- `src/aifactory/run/store.py` – nový stav `STOPPED`; `finish()` už stav `stopped`
  nepřepíše; nové metody `mark_stopped`, `live_processes`, `close_processes`.
- `src/aifactory/run/task.py` – `_existing_store` přejmenováno na veřejné `existing_store`.
- `src/aifactory/run/__init__.py` – exportuje `STOPPED`, `StopResult`, `running_run`, `stop_run`.
- `src/aifactory/skill/codes.py` – nové chybové kódy `unknown_run` a `run_not_running`.
- `src/aifactory/cli.py` – `factory task stop <ID> [--run RUN_ID] [--json]`. Bez `--run`
  zastaví běžící běh tasku; `--run` musí patřit danému tasku (jinak `invalid_value`).

## API (`src/aifactory/web/app.py`, `src/aifactory/web/runs.py`)

`web/runs.py` jen čte `task_runs` a trace tabulky (`sessions`, `phases`, `events`,
`envelopes`, `gate_results`, `agent_sessions`); chybějící trace DB nebo tabulka = prázdný výsledek.

| Endpoint | Obsah |
|---|---|
| `GET /api/runs?state=&task=` | běhy od nejnovějšího: task (+ titulek z backlogu), workflow, stav, začátek/konec, doba, tokeny a náklady (ze `sessions`), PR (`pr_for_branch`), tečky fází; seznam tasků pro filtr; `totals` za backlog a po tascích (vždy přes **všechny** běhy, ne jen filtrované). Neplatný `state` → 400 `invalid_status`. |
| `GET /api/runs/{run_id}` | souhrn + session, usage, agenti, fáze v pořadí `seq` (stav, harness, model, tokeny, náklady, usage, doba), gates, envelopes. Harness/model fáze bere z `agent_start` eventů, u ne-code fází fallback na `agent_sessions` podle `owner`; code fáze harness nemají. |
| `GET /api/runs/{run_id}/events?after=&limit=` | trace eventy stránkované kurzorem `rowid` (výchozí limit 500, max 1000), `has_more`. |
| `POST /api/runs/{run_id}/stop` | volá `run.stop.stop_run`, vrací souhrn běhu + `signalled`/`killed`. |

Mapování chyb na HTTP: `unknown_run` 404, `run_not_running` 409, `invalid_status`/`invalid_value` 400,
`trace_db_locked` 503, `ConfigError` 500 `invalid_config`. Odpovědi jsou v JSON envelope CLI.

## Frontend (`web/src/`)

- `views/RunsView.vue` – načte seznam, nebo detail podle hash routy `#/runs/<run_id>/<phase_id>`;
  stop přes `stopRun` a pak znovu načte data. Tlačítko pro obnovení (bez živých aktualizací).
- `components/runs/`: `RunsList` (tabulka + filtry stav/task), `CostTotals` (součty),
  `RunDetail` (hlavička, statistiky, fáze, tlačítko Zastavit s `window.confirm`, jen pro běžící běh),
  `PhaseDetail` (sekce gates, envelopes, náklady po typech tokenů, eventy/tool calls),
  a porty z visualizeru `DetailSection`, `PhaseDots`, `StatChip`, `StatusChip` (české popisky).
- `lib/runs.ts` – typy a klient (`fetchRuns`, `fetchRun`, `fetchAllEvents` – stránkuje po 1000,
  `stopRun`); `lib/api.ts` – nové `postApi` se sdíleným zpracováním envelope;
  `lib/router.ts` – `parseRoute` s parametry, `runHref`, `useRouteParams`;
  `lib/events.ts` (barvy, parsování tool callů, popisky eventů); `lib/format.ts` (doba, tokeny, cena, čas, JSON).
- Přestavěný bundle v `src/aifactory/web/static/` (nové hashované `index-*.js/css`, `index.html`).

## Testy a ověření

- `tests/run/test_task_stop.py` – pořadí signálů (agenti, pak běh), SIGKILL pro proces ignorující
  SIGTERM, `finish` nepřepíše `stopped`, odmítnutí zastavit vlastní proces, mrtvý/neznámý běh, CLI.
- `tests/web/test_web_runs.py` + `tests/web/trace_fixture.py` (trace DB z fixture) – sloupce
  a řazení, filtry, 400 pro neznámý stav, součty, repo bez trace DB, detail, fallback harnessu, 404,
  stránkování eventů, stop (včetně 409 a ověření, že web volá stejnou funkci jako CLI).
- Unit testy komponent a knihoven: `CostTotals`, `PhaseDetail`, `RunDetail`, `RunsList`, `RunsView`,
  `api`, `events`, `format`, `router` (fixtures v `web/src/test/runsFixtures.ts`).

Spuštění: `just test`, `just typecheck`, `just lint`. Ručně: `factory task stop <ID>` nebo
v dashboardu `#/runs` → běžící běh → **Zastavit**; běh pak má stav „zastaveno“.

Specifikace: `specs/bacc11a0_runs-screen-stop.md`.
