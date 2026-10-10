# HAIFA-S01-T26: Stabilní prohlížečový test F3 pod zátěží

## Proč test padal
Od HAIFA-S01-T09 dashboard spouští každý běh jako samostatný proces `factory task`.
`POST /api/backlog/tasks/{id}/run` čeká nejvýš 30 s, než si proces zabere řádek v `task_runs`.
Pak vrátí buď běh, nebo `pending`. V tom případě dialog ukáže jen „Běh se spouští…“ bez odkazu.
Test čekal na odkaz jen 15 s. Pod zátěží (`just test` spouští `tests/e2e` přes `-n auto`)
to nestačilo a při `pending` se odkaz neobjevil vůbec.

## Co se změnilo
Dashboard se nemění, upravil se jen test (`aifactory/tests/e2e/`).

- Limity v `test_f3_browser.py`:
  - `DEFAULT_TIMEOUT_MS = 15 s` pro čisté UI.
  - `SERVER_TIMEOUT_MS = 60 s` pro kroky, kde server pracuje s gitem: kontrola běhu, commit backlogu, merge, seznam PR a stav v backlogu.
  - `RUN_START_TIMEOUT_S = 90 s` pro start podprocesu.
  - `RUN_TIMEOUT_S = 240 s` pro celý běh.
- Start běhu: test si před kliknutím zapamatuje známé běhy tasku. Pak čeká na výsledek v dialogu
  a ID nového běhu vezme z `GET /api/runs?task=`. Odkaz kontroluje, jen když v dialogu je
  (text i `href`). Při `pending` ověří text „Běh se spouští…“.
- Konec běhu: polling `GET /api/runs/{id}`, dokud stav není `running`. Detail převede mrtvý běh na
  `aborted`, takže spadlý proces selže hned a ne až po vypršení limitu. Pak se čip na obrazovce
  Běhy ověří po refresh. Pevné pauzy ani slepý refresh už v testu nejsou.
- Nové pomocné funkce v `f3_repo.py`: `api_get`, `task_runs`, `run_state`, `wait_for` a `runs_report`.
  API se volá přes urllib, ne přes Playwright, a jde jen na `127.0.0.1` serveru testu.

## Diagnostika
Při selhání obsahuje chybová hláška `Server.report(task_id)`:
- `--- runs from API (<task>)`: každý běh se stavem, časy, PR, chybou a fázemi
  (např. `phases: request=success, plan=running`), plus aktuální stav nejnovějšího běhu z detailu.
- `--- server log`: konec logu `factory obs`.
- konec výstupu nejnovějších procesů běhu z `HAIFA_HOME/logs`.

## Ověření
```sh
just lint && just typecheck && just test
for i in 1 2 3 4 5; do just e2e || exit 1; done
```
