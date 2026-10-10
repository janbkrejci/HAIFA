# HAIFA-S01-T26: Stabilní prohlížečový test F3 pod zátěží

## Cíl
Prohlížečový test F3 (`aifactory/tests/e2e/test_f3_browser.py`) nesmí padat, když je stroj vytížený
(typicky `just test`, který spouští celou sadu včetně `tests/e2e` přes `-n auto`). Kroky, které čekají
na podproces `factory task` (start běhu, jeho konec) nebo na serverovou práci s gitem (commit backlogu,
merge), mají mít limit podle skutečné doby a čekat na stav v API/UI, ne na pevné pauzy. Při selhání
test vypíše stav běhu z API.

Mimo rozsah: chování dashboardu (Vue, `src/aifactory/web/*`), zrychlení startu běhu. `vendor/`,
`prototype/` se nemění. Žádný model ani síť (jen `127.0.0.1` serveru testu).

## Co dnes selhává a proč
- `_start_run` čeká na `[data-test="run-result"] a` s výchozím limitem 15 s (`DEFAULT_TIMEOUT_MS`).
- `POST /api/backlog/tasks/{id}/run` (viz `src/aifactory/web/launcher.py`, `backlog.start_run`) spustí
  samostatný proces a **až 30 s** čeká, než si proces zabere řádek v `task_runs`. Pak vrátí buď
  `run` (odkaz v dialogu), nebo `run: null, pending: true` — dialog pak ukáže jen text
  „Běh se spouští…“ **bez odkazu** a už se neaktualizuje (`web/src/components/backlog/RunDialog.vue`).
- Pod zátěží tedy (a) 15 s nestačí ani na odpověď POST, (b) při `pending` se odkaz nikdy neobjeví.
- `_watch_run` čeká na čip 90 s v UI a pak naslepo klikne „refresh“ s dalšími 15 s.
- `_approve` čeká na notice „Sloučeno“ 15 s, ačkoli merge dělá server synchronně v gitu; totéž
  `commit-backlog` v dialogu.

## Soubory
- `aifactory/tests/e2e/f3_repo.py` — nové pomocné funkce pro API (urllib, bez Playwright).
- `aifactory/tests/e2e/test_f3_browser.py` — limity, čekání přes API, diagnostika.
- `app_docs/HAIFA-S01-T26-stabilni-prohlizecovy-test-f3-pod-zatezi.md` — krátká dokumentace změny.
- `justfile` neměnit (není potřeba).

## Změny

### 1. `aifactory/tests/e2e/f3_repo.py`
Přidat (a zařadit do `__all__`):

```python
API_TIMEOUT_S = 10.0

def api_get(url: str, path: str) -> dict[str, Any]:
    """`data` of a successful `/api` envelope; AssertionError with the envelope otherwise."""
    # urllib.request.urlopen(f"{url}{path}", timeout=API_TIMEOUT_S), json.loads,
    # při HTTPError přečíst tělo (envelope_fail) a zahrnout ho do AssertionError;
    # při ok != True AssertionError s celým envelope.

def task_runs(url: str, task_id: str) -> list[dict[str, Any]]:
    """Runs of one task, newest first (`GET /api/runs?task=`)."""
    return list(api_get(url, f"/api/runs?task={urllib.parse.quote(task_id)}")["runs"])

def run_state(url: str, run_id: str) -> dict[str, Any]:
    """`run` of `GET /api/runs/{id}` (the detail reaps a dead `running` row into `aborted`)."""

def wait_for(check: Callable[[], T | None], timeout_s: float, what: str,
             report: Callable[[], str], interval_s: float = 0.25) -> T:
    """Poll `check` until it returns a non-None value; on timeout AssertionError
    f"{what}: not within {timeout_s:.0f} s\n{report()}". Výjimky z `check` (AssertionError,
    URLError, OSError) během čekání neukončují čekání — poslední z nich se přidá do zprávy."""

def runs_report(url: str, task_id: str | None) -> str:
    """Stav běhů z API pro diagnostiku; nikdy nevyhazuje výjimku."""
    # Pro task_id (nebo všechny běhy, je-li None) vypsat každý běh na řádek(y):
    # run_id, task_id, state, started_at, ended_at, error, pr, a fáze
    # (z `phases` souhrnu: jméno + stav, ať je vidět, na které fázi visí).
    # Nejnovější běh navíc přes run_state (aktuální stav po reapu).
    # Selže-li API: "(API unavailable: <exc>)". Začínat hlavičkou "--- runs from API".
```
`time.sleep` v `wait_for` je polling interval, ne pevná pauza — to je v pořádku.
Typování: `TypeVar T`, `Callable` z `collections.abc`; projít `mypy` (strict dle `pyproject`).

### 2. `aifactory/tests/e2e/test_f3_browser.py`

Konstanty (nahradit `RUN_TIMEOUT_MS`):
```python
DEFAULT_TIMEOUT_MS = 15_000      # čistě UI (navigace, formuláře, dropdown)
SERVER_TIMEOUT_MS = 60_000       # UI čeká na serverovou práci s gitem (commit backlogu, merge, seznamy z API)
RUN_START_TIMEOUT_S = 90.0       # start podprocesu `factory task run` až po zabrání řádku v task_runs
RUN_TIMEOUT_S = 240.0            # celý běh fake harnessu (podproces) pod zátěží
```
Komentář u konstant: od HAIFA-S01-T09 je běh samostatný proces; POST čeká na zabrání ≤ 30 s
a pak vrátí `pending`.

`Server`:
- `tail()` rozšířit na `report(task_id: str | None = None) -> str` =
  `runs_report(self.url, task_id)` + log serveru + `run_logs_tail`. Všechna místa, která dnes
  připojují `server.tail()`, používají `server.report(task_id)`.

`_start_run(page, server, task_id, *, commit_first)`:
1. Otevřít task a dialog jako dnes. `commit-backlog` → `expect(not_in_base).to_have_count(0, timeout=SERVER_TIMEOUT_MS)`;
   `run-loading` count 0 také se `SERVER_TIMEOUT_MS` (run-check volá git).
2. Před kliknutím: `known = {r["run_id"] for r in task_runs(server.url, task_id)}`.
3. `start.click()`; pak `expect(dialog.locator('[data-test="run-result"]')).to_be_visible(timeout=RUN_START_TIMEOUT_S*1000)`.
   Pokud místo toho dialog ukáže chybu (IssueList), selže to s reportem — celé čekání obalit
   `try/except AssertionError` → `AssertionError(f"{exc}\n{server.report(task_id)}")`.
4. `run_id = wait_for(lambda: nový run_id z task_runs(...) není-li v known, jinak None,
   RUN_START_TIMEOUT_S, f"run of {task_id} claimed", lambda: server.report(task_id))`.
   (Deadline počítat od kliknutí, tj. zbytek z 90 s; stačí jednoduše znovu 90 s.)
5. Odkaz: pokud `dialog.locator('[data-test="run-result"] a').count() > 0`, ověřit
   `inner_text().strip() == run_id` a `href` končí na `#/runs/{run_id}`; jinak (pending)
   ověřit text „Běh se spouští…“ a pokračovat — dashboard se nemění, běh je ověřen přes API.
6. Vrátit `run_id`.

`_watch_run(page, server, run_id, task_id)`:
1. `state = wait_for(lambda: s if (s := run_state(server.url, run_id)["state"]) != "running" else None,
   RUN_TIMEOUT_S, f"run {run_id} finished", lambda: server.report(task_id))`.
2. `assert state == "succeeded", f"run {run_id} ended {state}:\n{server.report(task_id)}"`.
3. UI: `_nav(page, "runs")`, `page.locator('[data-test="refresh"]').click()`,
   `expect(chip).to_have_attribute("data-status", "succeeded", timeout=SERVER_TIMEOUT_MS)`
   (chip = `tr[data-run="{run_id}"] .chip[data-status]`), při selhání report.
   Odstranit dnešní fallback „počkat 90 s → refresh → 15 s“.

`_approve(page, server, net, task_id)`:
- Řádek `tr[data-pr="{task_id}"] a.task-link` čekat `to_be_visible(timeout=SERVER_TIMEOUT_MS)` před klikem.
- `approve` `to_be_enabled(timeout=SERVER_TIMEOUT_MS)`.
- `notice` „Sloučeno“ s `timeout=SERVER_TIMEOUT_MS`; report při selhání (s `task_id`).
- Zbytek (modální dialog, focus, žádné systémové dialogy) beze změny.

Test `test_f3_task_lifecycle_in_browser`:
- Volání upravit na nové signatury (`_watch_run(page, server, run1, first)`).
- Závěrečný blok Backlog: čip `data-state="done"` po refresh čekat se `SERVER_TIMEOUT_MS`.
- Žádné `page.wait_for_timeout` / `time.sleep` v testu (dnes žádné nejsou; nepřidávat).
- Ostatní asserty (git, envelopes, `_calls`, tripwire, `net.aborted`) beze změny.

Docstring modulu doplnit o odstavec: na podproces se čeká přes API (`/api/runs`), limity
`RUN_START_TIMEOUT_S`/`RUN_TIMEOUT_S`, při selhání se vypíše stav běhů z API + logy.

### 3. `app_docs/HAIFA-S01-T26-stabilni-prohlizecovy-test-f3-pod-zatezi.md`
Krátce česky: proč test padal (15 s vs. start podprocesu, `pending` bez odkazu), nové limity a
helpery, jak číst diagnostiku, jak ověřit 5× za sebou.

## Ověření
Vše z kořene worktree, posuzovat podle exit statusu:
1. `just lint` (ruff check + format --check; případně `uv run ruff format` v `aifactory/`).
2. `just typecheck`.
3. `just test`.
4. Pětkrát po sobě: `for i in 1 2 3 4 5; do just e2e || exit 1; done` — musí projít všech 5.
5. Doporučeno (zátěž): spustit `just e2e` souběžně s `just test` a ověřit, že projde.
6. Ruční kontrola diagnostiky (neukládat): dočasně snížit `RUN_START_TIMEOUT_S` na 0.01 a
   ověřit, že chybová hláška obsahuje „--- runs from API“ se stavem běhu; pak vrátit.

## Rizika / poznámky
- `pending` větev nemusí v běžném běhu nastat; nesmí ale padat, pokud nastane.
- `urllib` požadavky jdou mimo Playwright, takže je `context.route` nezapočítá do `net.aborted`
  (jdou jen na `127.0.0.1` serveru testu — žádná síť).
- `run_state` přes detail endpoint převede mrtvý `running` řádek na `aborted`, takže zabitý
  podproces neskončí čekáním do limitu, ale okamžitou chybou s reportem.
