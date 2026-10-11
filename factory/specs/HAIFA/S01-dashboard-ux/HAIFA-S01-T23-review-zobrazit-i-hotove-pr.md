# HAIFA-S01-T23 — Review: zobrazit i hotové PR

## Cíl
Na obrazovce Review přibude volba „Zobrazit hotové“ (výchozí vypnuto, pamatuje se v `localStorage`).
Když je zapnutá, pod otevřenými PR se zobrazí sekce „Hotové“ se sloučenými a zavřenými PR tasků
z `task_prs` (nejnovější nahoře, stav, datum, odkaz na PR). Detail hotového PR je jen pro čtení.
API `GET /api/review` vrací hotové PR jen s parametrem `?done=1`; bez něj se odpověď nemění.

Out of scope: mazání/archivace PR, změna toku schválení. `vendor/` a `prototype/` neměnit. Testy bez sítě a modelu.

## Rozhodnutí
- **Parametr API:** `GET /api/review?done=1` (přijmout `1`, `true`, `yes`, case-insensitive). Jiná hodnota / chybějící → stávající odpověď **bez** klíče `done` (ani prázdný seznam).
- **Výběr hotových PR:** řádky `task_prs` se `state IN ('merged','closed')`, **jeden na task** (nejnovější hotový PR tasku) a **vynechat tasky, které mají otevřený PR** (ty už jsou v otevřených sekcích; detail `/api/review/{task_id}` čte `latest_pr`, takže by ukázal otevřený PR). Tím odkaz z „Hotové“ do detailu vždy ukáže právě ten hotový PR.
- **Datum (`done_at`):** `merged_at` u sloučeného, jinak `updated_at` (tabulka nemá `closed_at`). Řazení `done_at DESC`, při shodě `created_at DESC`.
- **Žádné volání provideru pro hotové PR:** `_status()` pro `row.state != OPEN` už vrací `row.state` bez sítě — využít `_pr_summary`, nebo položku sestavit přímo.
- **Klíč localStorage:** `haifa.review.showDone`, hodnota `'1'` / `'0'`.
- Řádky sekce „Hotové“ mají atribut `data-done-pr` (ne `data-pr`), aby se nemíchaly se stávajícími selektory `tr[data-pr]` v testech a e2e.

## Změny — backend

### `aifactory/src/aifactory/run/store.py`
Přidat do `TaskRunStore` (vedle `open_prs`):
```python
def done_prs(self) -> list[TaskPrRow]:
    """Merged and closed pull requests, newest first (merged_at, else updated_at)."""
```
SQL: `SELECT ... FROM task_prs WHERE state IN ('merged','closed') ORDER BY COALESCE(merged_at, updated_at) DESC, created_at DESC, rowid DESC`. Podívej se na `_prs()` (ř. ~418) — buď ho rozšiř o volitelné `order`, nebo napiš dotaz zvlášť se stejným seznamem sloupců a převodem na `TaskPrRow`.

### `aifactory/src/aifactory/web/review.py`
- `review_list(repo: Path, include_done: bool = False)`.
- Když `include_done`: po sestavení otevřených (`seen` = task_id otevřených PR) projít `store.done_prs()`, přeskočit task v `seen` nebo už viděný, a pro každý vytvořit položku:
  ```python
  {
    "task_id", "task_title", "module_id",   # jako v _pr_summary (_task, _module_id)
    "provider_state": row.state,             # "merged" | "closed"
    "done_at": row.merged_at or row.updated_at,
    "cost", "tokens",                        # branch_cost(store.db_path, run_ids na větvi)
    "pr": row.to_json() bez "body",
  }
  ```
  (Lze použít `_pr_summary` a pak vyřadit nepotřebné klíče; podstatné je, že nevolá provider.) Seznam seřadit podle `done_at` desc (pořadí z `done_prs` to už splňuje, po dedupu se zachová). Bez store → `[]`.
- Do `data` přidat `"done": [...]` **jen** když `include_done`.
- Upravit docstring modulu/funkce (hotové PR na vyžádání).
- `review_detail` se nemění funkčně: pro merged/closed už `actions` = vše `False` (ověřit testem). Volitelně přidat `"read_only": state != OPEN` — ne nutné; frontend rozhoduje podle `provider_state`/`pr.state`.

### `aifactory/src/aifactory/web/app.py`
V `review_list` handleru:
```python
done = request.query_params.get("done", "").strip().lower() in ("1", "true", "yes")
data, warnings = await run_in_threadpool(review.review_list, repo, done)
```
Doplnit docstring modulu (ř. ~28): `GET /api/review` (`?done=1` přidá sloučené a zavřené PR v `done`).

## Změny — frontend (`aifactory/web/src/`)

### `lib/review.ts`
- Nový typ:
  ```ts
  /** One item of `done` in GET /api/review?done=1: a merged or closed task PR. */
  export interface ReviewDonePr {
    task_id: string; task_title: string | null; module_id: string | null
    provider_state: 'merged' | 'closed'; done_at: string
    cost: number; tokens: number; pr: TaskPr
  }
  ```
- `ReviewList` doplnit `done?: ReviewDonePr[]`.
- `fetchReviews(opts: { done?: boolean } = {})` → `getApi(opts.done ? '/review?done=1' : '/review')` (bez parametru přesně `'/review'` — stávající test čeká `'/api/review'`).
- Persistování:
  ```ts
  export const SHOW_DONE_KEY = 'haifa.review.showDone'
  export function loadShowDone(): boolean   // try { localStorage.getItem(KEY) === '1' } catch { false }
  export function saveShowDone(v: boolean): void  // try { setItem(KEY, v ? '1' : '0') } catch {}
  ```
  (hlídat `typeof localStorage !== 'undefined'` jako `lib/theme.ts`).
- Pomocník `doneLabel(state)` → `'sloučeno'` pro `merged`, `'zavřeno'` pro `closed`.
- Pomocník `isReadOnly(detail: { provider_state, pr })`: `true`, když `provider_state` nebo `pr.state` je `'merged'`/`'closed'`.

### `views/ReviewView.vue`
- `const showDone = ref(loadShowDone())`.
- `emptyList()` doplnit `done: []`; `normalise()` doplnit `done: Array.isArray(data?.done) ? data.done : []`.
- `loadList()` a `refreshList()` volají `fetchReviews({ done: showDone.value })`.
- `watch(showDone, (v) => { saveShowDone(v); if (!taskId.value) void loadList() })`.
- V `view-head` (jen na seznamu, `v-if="!taskId"`) checkbox:
  ```html
  <label class="show-done"><input type="checkbox" v-model="showDone" data-test="show-done" /> Zobrazit hotové</label>
  ```
  umístit před tlačítko Obnovit (tlačítko má `margin-left: auto`; label dát před něj nebo mu dát vlastní `margin-left:auto` a Obnovit nechat za ním — vizuálně vpravo vedle sebe).
- Předat `ReviewList` prop `:show-done="showDone"`.
- Akce `onApprove/onReturn/onResolve` se nemění.

### `components/review/ReviewList.vue`
- Nový prop `showDone?: boolean` (default `false`).
- `done = computed(() => Array.isArray(props.list.done) ? props.list.done : [])`, pro jistotu seřadit kopii podle `done_at` desc.
- Šablona: zachovat stávající chování otevřených sekcí („Žádné otevřené PR“, když `prs` prázdné – text neměnit, používá ho e2e/testy). Pod tím (mimo `v-else` větev, ale jen když `ready`) přidat:
  ```html
  <section v-if="ready && showDone" class="group" data-test="done">
    <h2>Hotové <span class="dim">({{ done.length }})</span></h2>
    <p v-if="!done.length" class="faint">Nic</p>
    <table v-else class="table"> Task | Modul | Stav | Datum | Náklady | PR
      <tr v-for="p in done" :key="p.pr.branch" :data-done-pr="p.task_id">
        Task: odkaz reviewHref(p.task_id) jako u otevřených (class task-link)
        Stav: <span class="chip" :data-state="p.provider_state" data-col="state">{{ doneLabel(p.provider_state) }}</span>
        Datum: <span data-col="done-at">{{ fmtTime(p.done_at) }}</span>
        Náklady: fmtCost
        PR: stejně jako u otevřených (local: → mono text, jinak <a target=_blank> #pr_id, data-col="pr")
  ```
  Barva chipu: sloučeno zeleně (`var(--green)`), zavřeno tlumeně (`var(--dim)`).

### `components/review/ReviewDetail.vue`
- `const readOnly = computed(() => isReadOnly(props.detail))`.
- V `actions-bar`: `<ReviewActions v-if="!readOnly" ... />`, jinak
  ```html
  <p v-else class="readonly" data-test="read-only">PR je {{ doneLabel(...) }} – jen pro čtení, akce nejsou dostupné.</p>
  ```
  Tím nejsou v DOM tlačítka `approve`, `return`, `resolve` (Vyřešit konflikt i Dorovnat s base mají `data-test="resolve"`) ani pole `return-note`.
- V meta řádku u hotového PR zobrazit i datum (`merged_at ?? updated_at`) — volitelné.

### `test/reviewFixtures.ts`
Přidat `donePr(over: Partial<ReviewDonePr> = {})` (merged, `done_at`, `pr` z `taskPr({ state: 'merged', merged_at: ... })`).

## Testy

### vitest
- `components/review/ReviewList.test.ts`:
  - bez `showDone` není `[data-test="done"]`, i když `list.done` má položky;
  - se `showDone` sekce „Hotové“ existuje, řádky `tr[data-done-pr]` jsou v pořadí nejnovější první (podej je schválně v opačném pořadí, pokud frontend řadí; jinak v pořadí z API), obsahují „sloučeno“ / „zavřeno“, datum (`fmtTime`) a odkaz na PR (`href` = `pr.url` u ne-local URL), odkaz na detail `#/review/<id>`;
  - se `showDone` a prázdnými `prs` je vidět „Žádné otevřené PR“ i sekce Hotové; prázdné `done` → „Nic“.
- `views/ReviewView.test.ts`:
  - výchozí: checkbox `[data-test="show-done"]` nezaškrtnutý, fetch `['/api/review']` (stávající test zůstává zelený);
  - zaškrtnutí → další fetch `/api/review?done=1`, `localStorage.getItem('haifa.review.showDone') === '1'`, sekce Hotové se vykreslí;
  - `localStorage.setItem('haifa.review.showDone','1')` před mountem → první fetch `/api/review?done=1` a checkbox zaškrtnutý;
  - na detailu (`#/review/<id>`) checkbox není.
- `components/review/ReviewDetail.test.ts`: detail s `provider_state: 'merged'` (a druhý `'closed'`, `actions` vše false, i s `mergeability: 'conflict'`) → `[data-test="read-only"]` existuje, `[data-test="approve"]`, `[data-test="return"]`, `[data-test="resolve"]`, `[data-test="return-note"]`, `[data-test="conflict-banner"]` neexistují. Otevřený PR dál ukazuje akce.
- Případně `lib/review` unit (fetchReviews URL, load/saveShowDone) — v `ReviewView.test.ts` stačí.

### pytest — `aifactory/tests/web/test_web_review.py`
- `test_list_done_only_on_request`: `run_both(repo, script)` (T01 merged, T02 open).
  - `GET /api/review` → `"done" not in data`, `[p["task_id"] for p in data["prs"]] == [T02]`.
  - `GET /api/review?done=0` → `"done" not in data`.
  - `GET /api/review?done=1` → `prs` stejné, `done` = jedna položka T01: `provider_state == "merged"`, `done_at == pr["merged_at"]`, `"body" not in pr`, `task_title`, `module_id == "M01"`, `cost` float, `tokens` int.
- `test_done_lists_closed_newest_first`: `run_both`, pak přes `TaskRunStore(repo/".factory"/"trace.db")` `update_pr(<větev T02>, state="closed", updated_at="2999-01-01T00:00:00Z")` (větev vzít z `store.open_pr(T02).branch`), store zavřít. `GET /api/review?done=1` → `prs == []`, `done` task ids `[T02, T01]`, stavy `closed`, `merged`; `done[0]["done_at"] == "2999-01-01T00:00:00Z"`.
- `test_done_detail_is_read_only`: `run_both`, `GET /api/review/{T01}` → `provider_state == "merged"`, `actions == {"approve": False, "return": False, "resolve": False}`.
- Volitelně unit test `TaskRunStore.done_prs` v `aifactory/tests/run/` (pokud tam je test store).

## Build
`just web-build` → regeneruje `aifactory/src/aifactory/web/static/` (index.html + assets). Výsledné soubory nechat v pracovním stromu (staré hashované assety smazané buildem nevracet).

## Ověření
1. `just test` (včetně `web-test`: vue-tsc + vitest, pak pytest)
2. `just typecheck` (mypy)
3. `just lint` (ruff check + format --check — spustit `cd aifactory && uv run ruff format` na změněné py soubory)
4. `just web-build` a pak `just e2e`
Všechny musí skončit exit 0.

## Soubory
- `aifactory/src/aifactory/run/store.py` — `done_prs()`
- `aifactory/src/aifactory/web/review.py` — `review_list(include_done)`
- `aifactory/src/aifactory/web/app.py` — parametr `done`
- `aifactory/web/src/lib/review.ts`
- `aifactory/web/src/views/ReviewView.vue`, `ReviewView.test.ts`
- `aifactory/web/src/components/review/ReviewList.vue`, `ReviewList.test.ts`
- `aifactory/web/src/components/review/ReviewDetail.vue`, `ReviewDetail.test.ts`
- `aifactory/web/src/test/reviewFixtures.ts`
- `aifactory/tests/web/test_web_review.py`
- `aifactory/src/aifactory/web/static/**` (build)
