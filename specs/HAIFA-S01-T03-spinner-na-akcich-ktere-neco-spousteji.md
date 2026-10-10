# HAIFA-S01-T03: Spinner na akcích, které něco spouštějí

## Cíl
Kliknuté akční tlačítko ukáže sdílený spinner, dokud akce na serveru neskončí; kolidující akce jsou mezitím zakázané. Ikona Obnovit se točí při načítání. Seznamy při prvním načtení neukazují falešný prázdný stav. Rozjíždějící se běh (`pending`) drží spinner do živé události a pak ukáže odkaz na běh. Bez změn API a bez nových závislostí (`vendor/`, `prototype/` se nemění).

Všechny cesty níže jsou relativní k `aifactory/web/src/`, pokud není uvedeno jinak.

## 1. Sdílená komponenta a CSS

### `components/ui/Spinner.vue` (nový)
```vue
<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 14 })
</script>
<template>
  <span class="spinner" data-test="spinner" aria-hidden="true"
        :style="{ width: `${size}px`, height: `${size}px` }" />
</template>
```
Žádný scoped styl – vzhled je v `style.css` (aby byl stejný všude).

### `style.css` (doplnit na konec)
```css
@keyframes spin { to { transform: rotate(360deg); } }
.spinner {
  display: inline-block; flex: none; box-sizing: border-box;
  border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%;
  vertical-align: -0.125em; animation: spin 0.7s linear infinite;
}
.spin { animation: spin 1s linear infinite; }   /* ikona RefreshCw při načítání */
@media (prefers-reduced-motion: reduce) {
  .spinner, .spin { animation-duration: 2s; }
}
```
Tlačítka, do kterých se spinner vkládá, musí zarovnat obsah: kde to scoped CSS nemá, přidej `display: inline-flex; align-items: center; gap: 6px;` (RunDialog, ReviewActions `.btn`, TaskForm/SettingsForm `button`, TaskDetail tlačítka, AutoContinueToggle `button`, RunDetail `.stop`).

### Konvence v tlačítkách
- Tlačítko v běhu dostane `:aria-busy="<pending>"` a `<Spinner v-if="<pending>" />`.
- Tlačítko s ikonou (Play, X, CircleStop): spinner **nahradí** ikonu (`<Spinner v-if=… /><Play v-else … />`).
- Textové tlačítko: spinner před textem.
- Spinner je jen v kliknutém tlačítku → stav akce se v pohledech drží jako **klíč akce**, ne jen boolean.
- „Načítám…“ texty spinner nedostávají (testy počítají `[data-test="spinner"]` == 1).

## 2. Obnovit + první načtení seznamů

### Ikona Obnovit
V `views/BacklogView.vue`, `views/RunsView.vue`, `views/ReviewView.vue`:
`<RefreshCw :size="16" :class="{ spin: loading }" />` (Lucide předá class do `<svg>`).

### Žádný falešný prázdný stav
- **BacklogView**: v list větvi (`<template v-else>`) obal `KanbanBoard`/`BacklogTree` do `v-if="data"`; jinak `<p v-else-if="loading" class="faint" data-test="list-loading">Načítám…</p>`. (`data` je `null` do prvního úspěšného načtení; filtry a `problems` mohou zůstat.)
- **RunsView** + `components/runs/RunsList.vue`: ve view `const listReady = ref(false)`, nastav `true` po úspěšném `loadList`/`refreshList`. `RunsList` dostane props `ready: boolean` a `loading?: boolean`; „Žádné běhy“ (`data-test="no-runs"`) i tabulka jen když `ready`; když `!ready && loading` → `<p class="faint" data-test="list-loading">Načítám…</p>`. Filtry zůstávají vidět. `CostTotals` renderuj jen při `listReady`.
- **ReviewView** + `components/review/ReviewList.vue`: stejně – `listReady` (true po úspěšném `loadList`/`refreshList`), `ReviewList` props `ready: boolean`, `loading?: boolean`; „Žádné otevřené PR“ až při `ready`.
- Při chybě prvního načtení se ukáže jen error bar (žádné „Žádné …“).

## 3. Backlog (`views/BacklogView.vue`, `lib/backlog.ts`, `components/backlog/*`)

### `lib/backlog.ts`
- Rozšiř `RunPanel`:
  ```ts
  export type RunAction = 'start' | 'force' | 'commit'
  export interface RunPanel { open; check; loading; busy; error; result;
    /** which dialog button is running (spinner) */ action: RunAction | null
    /** start answered `pending`: waiting for the run to show up in live updates */ waiting: boolean }
  ```
- Přidej čistý helper klíče zápisové akce:
  ```ts
  export function linkActionKey(input: LinkInput): string
  // remove → `unlink:${kind}:${ids[0]}`, jinak `link:${kind}`; kind = 'depends_on' | 'related'
  ```
  a čistý helper `newRun<T extends { run_id: string }>(runs: T[], known: Set<string>): T | null` (první běh, jehož id není v `known`; preferuj stav `running`). Oba otestuj v `lib/backlog.test.ts`.

### `views/BacklogView.vue`
- `busy` (boolean) nahraď `const busyAction = ref<string | null>(null)` a `const busy = computed(() => busyAction.value !== null)`. `write(key, run)` nastaví `busyAction = key` místo `busy = true`, ve `finally` `null`.
  - `onAdd` → klíč `'add'`, `onEdit` → `'edit'`, `onLink(input)` → `linkActionKey(input)`, `onAssign` → `'assign'`.
- Auto-continue: `autoBusy` nahraď `const autoPending = ref<AutoMode | null>(null)` + `autoBusy = computed(() => autoPending.value !== null)`; `onAutoContinue(mode)` nastaví `autoPending = mode`. `writing()` dál používá `autoBusy`.
- `closedRun()` vrací i `action: null, waiting: false`.
- `onRunStart({ note, force })`:
  - před startem `knownRuns = new Set(detail.value?.runs.map(r => r.run_id) ?? [])` (modulová proměnná),
  - `run = { ...run, busy: true, action: force ? 'force' : 'start', error: null, result: null }`,
  - po odpovědi: když `result.run` → `busy:false, action:null, result`; když `result.pending && !result.run` → `busy:false, waiting:true, action` **zůstává**, `result` uložen. Pak `await loadDetail(id)`.
  - chyba → `busy:false, action:null, waiting:false`.
- `onRunCommit` → `action: 'commit'` po dobu akce, ve všech koncích `action: null`.
- `claimPending(task: TaskDetailData)`: když `run.value.waiting && task.task.id === taskId.value`, najdi `newRun(task.runs, knownRuns)`; pokud existuje → `run.value = { ...run.value, waiting:false, action:null, result: { ...run.value.result!, run: found, pending:false } }`. Volat všude, kde se nastavuje `detail.value` (v `loadDetail` i v `liveRefresh` po `fetchTask`). Server po zaregistrování běhu pošle `trace` s `runs_changed: true` a `task_ids` obsahujícím task (viz `src/aifactory/web/live.py`), takže stávající `onTrace → liveRefresh → fetchTask` dodá detail.
- `writing()` **nesmí** zahrnovat `run.waiting` (jinak by se živá aktualizace odložila navždy) – `run.busy` je během čekání `false`, takže stačí nic neměnit.
- Předej do komponent: `TaskForm` (add) `:pending="busyAction === 'add'"`; `TaskDetail` `:action="busyAction"`; `AutoContinueToggle` `:pending="autoPending"`.

### `components/backlog/TaskDetail.vue`
- Nová prop `action?: string | null`.
- „Spustit“ (`data-test="run"`): spinner místo `Play`, když `run?.loading` (kontrola před startem).
- „Odebrat vazbu“ (`unlink-<id>`, `unrelate-<r>`): spinner místo `X`, když `action === linkActionKey({ depends_on|related: [id], remove: true })`.
- „Přidat“ (`link-add`, `related-add`): spinner, když `action === 'link:depends_on'` / `'link:related'`.
- „Přiřadit“ (`assign`): spinner, když `action === 'assign'`.
- Edit `TaskForm`: `:pending="action === 'edit'"`.
- Předej do `RunDialog` `:action="run.action"` a `:waiting="run.waiting"`.
- Disabled logiku ponech (`busy` už zakazuje kolidující zápisy).

### `components/backlog/RunDialog.vue`
- Props `action?: RunAction | null`, `waiting?: boolean`.
- `blocked` navíc `|| props.waiting || props.result !== null` (po úspěšném spuštění je Spustit i Spustit přesto zakázané).
- Spinner: `run-start` při `action === 'start'`, `run-force` při `action === 'force'`, `commit-backlog` při `action === 'commit'`; `commit-backlog` disabled i při `waiting`.
- Výsledek (`data-test="run-result"`): s `result.run` odkaz jako dnes; bez něj (čekání) text „Běh se spouští…“ (bez výzvy k obnovení). Zavřít zůstává povolené i během čekání (zavření zahodí panel).

### `components/backlog/TaskForm.vue`
- Prop `pending?: boolean`; v submit tlačítku (`data-test="save"`, Založit/Uložit) `<Spinner v-if="pending" />`.

### `components/backlog/AutoContinueToggle.vue`
- Prop `pending?: AutoMode | null`; spinner v tlačítku `option.mode === pending`.

## 4. Běhy (`views/RunsView.vue`, `components/runs/RunDetail.vue`, `RunsList.vue`)
- `RunDetail`: v `stop-run` spinner místo `CircleStop`, když `stopping`.
- RunsList/obnovit viz bod 2.

## 5. Review (`views/ReviewView.vue`, `components/review/ReviewActions.vue`, `ReviewList.vue`, `lib/review.ts`)
- Typ `export type ReviewAction = 'approve' | 'return' | 'resolve'` v `lib/review.ts`.
- View: `const pendingAction = ref<ReviewAction | null>(null)`, `const waiting = ref(false)`, `let knownRuns = new Set<string>()`.
- `act(key, run, failure)`: nastaví `busy = true`, `pendingAction = key`, `knownRuns = set(detail.runs.run_id)`; po `run()` → když `started.value?.pending && !started.value.run` → `waiting = true` a `pendingAction` **ponech**; jinak `pendingAction = null`. Při chybě `pendingAction = null, waiting = false`. `busy = false` ve finally (aby `idle()` pouštělo živé události).
- `claimPending(data: ReviewDetailData)`: když `waiting` a `newRun(data.runs, knownRuns)` (helper z `lib/backlog.ts`, nebo zkopíruj do `lib/review.ts`) najde běh → `started.value = { ...started.value!, run: { run_id, workflow, branch: data.pr.branch }, pending: false }`, `waiting = false`, `pendingAction = null`. Volat v `loadDetail` a `refreshDetail` po přijetí dat. `onTrace` už volá `refreshDetail`, když `task_ids` obsahuje task.
- Změna route (`watch(taskId)`) resetuje `waiting`, `pendingAction`.
- Hláška: `<template v-else>Běh se spouští…</template>` (zmizí „obnov stránku za chvíli“); po nalezení běhu se ukáže odkaz.
- `ReviewDetail` → `ReviewActions` předá `:busy="busy || waiting"` a `:pending="pendingAction"` (projdi `components/review/ReviewDetail.vue`, přidej prop `pending?: ReviewAction | null` a prosměruj; `busy` u ReviewDetail předávej `busy || waiting`).
- `ReviewActions`: prop `pending?: ReviewAction | null`; spinner v `approve` (Schválit) při `'approve'`, `return` (Vrátit) při `'return'`, oba `resolve` tlačítka (Vyřešit konflikt / Dorovnat s base – vždy se renderuje jen jedno) při `'resolve'`. Disabled zůstává přes `blocked`.

## 6. Nastavení (`views/SettingsView.vue`, `components/settings/SettingsForm.vue`)
- `SettingsForm`: v `save` (Uložit) `<Spinner v-if="busy" />`; `reset` už je disabled při busy.

## 7. Testy (vitest, happy-dom; žádné volání modelu)
- Nový helper `test/deferred.ts`:
  ```ts
  export function deferred<T>() { let resolve!: (v: T) => void; let reject!: (e: unknown) => void
    const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej }); return { promise, resolve, reject } }
  ```
  Ve fetch mocku vracej pro testovaný POST/PUT `gate.promise` (Response), ostatní URL odpovídají hned.
- `components/ui/Spinner.test.ts`: renderuje `[data-test="spinner"]` s velikostí z propu.
- `views/BacklogView.test.ts` (přidat):
  1. Spustit v detailu: odložený `GET …/run-check` (zjisti URL z `fetchRunCheck`) → spinner v `[data-test="run"]`, po resolve zmizí.
  2. `run-start` s odloženým POST: spinner jen v `run-start` (`findAll('[data-test="spinner"]')` délky 1), `run-force`/`commit-backlog` disabled; po resolve s `run` spinner zmizí, `run-result` má odkaz a `run-start` je disabled.
  3. Pending: POST vrátí `runStart({ run: null, pending: true })` → spinner v `run-start` trvá, text „Běh se spouští…“ bez „obnov“; pak fetch detailu tasku začne vracet task s novým během, `FakeEventSource.latest().emit('trace', traceEvent({ runs_changed: true, task_ids: [id] }))`, `await debounce(); await flushPromises()` → spinner zmizí, `run-result a` má id nového běhu, `run-start` disabled.
  4. `commit-backlog` spinner; Přidat vazbu (`link-add`) spinner jen v něm, `related-add`/`assign`/`unlink-*` disabled; Odebrat vazbu spinner místo X; Přiřadit; Uložit (edit) a Založit (`#/backlog/new`) spinner v `save`.
  5. Auto-continue: odložený POST → spinner v `auto-on`, ostatní volby disabled, po odpovědi pryč.
  6. Obnovit: při odloženém `GET /api/backlog` má `[data-test="refresh"] svg` třídu `spin` a není vidět `empty-tree`; po resolve třída zmizí.
- `views/RunsView.test.ts`: Zastavit s odloženým stop POST (potvrď dialog přes `answerDialog`) → spinner v `stop-run`, disabled; po odpovědi pryč. Odložený `GET /api/runs` → žádné `no-runs`, `refresh svg.spin`; po resolve s prázdnými daty `no-runs` se ukáže.
- `views/ReviewView.test.ts`: Schválit (přes confirm), Vrátit, Vyřešit konflikt s odloženým POST → spinner jen v kliknutém, ostatní akce disabled, po odpovědi pryč. Pending Vrátit/Vyřešit: odpověď `{ run: null, pending: true }` → spinner trvá; detail pak vrací nový běh v `runs`, emit `trace` s `task_ids: [id]` → `[data-test="started"] a` s run id, spinner pryč, text „obnov stránku“ nikde. Odložený `GET /api/review` → žádné `no-prs`.
- `views/SettingsView.test.ts`: odložené uložení → spinner v `save`, `reset` disabled, po odpovědi pryč.
- `lib/backlog.test.ts`: `linkActionKey`, `newRun`.
- Uprav existující testy, které by kvůli novým props/stavům padly (např. přímé mounty `RunsList`/`ReviewList` potřebují `ready: true`; `runStart` fixture se nemění).

## 8. E2E (`aifactory/tests/e2e/test_f3_browser.py`, ~ř. 240–250)
Větev pending dnes očekává trvalé „Běh se spouští“ bez odkazu. Změň: po zjištění `run_id` vždy čekej na odkaz:
```python
link = result.locator("a")
expect(link).to_have_text(run_id, timeout=SERVER_TIMEOUT_MS)
href = link.get_attribute("href") or ""
assert href.endswith(f"#/runs/{run_id}"), ...
```
(odstraň `else` větev s „Běh se spouští“; zachovej `server.report` v chybových zprávách přes try/except jako okolní kód).

## 9. Build
Spusť `just web-build` (vue-tsc + vite build do `aifactory/src/aifactory/web/static/`, `emptyOutDir`) a nech vygenerované soubory (nové hash názvy v `static/assets/`, `index.html`) v pracovním stromu; staré `index-*.js/css` zmizí.

## 10. Ověření
1. `just web-test` (vue-tsc + vitest) – zelené.
2. `just web-build` – projde, `static/` aktualizované.
3. `just test`, `just typecheck`, `just lint`, `just e2e` – projdou (spouštěj z kořene worktree).
4. Rychlý grep: `grep -rn "obnov stránku" aifactory/web/src` nic nenajde (kromě případných negativních asercí v testech).

## Mimo rozsah
Procentuální průběh běhu, změny API, nové závislosti, `vendor/`, `prototype/`.
