# HAIFA-S01-T02 — Vlastní dropdown místo nativního selectu

## Cíl
Všech devět nativních `<select>` v dashboardu (`aifactory/web/src`) nahradit jednou sdílenou komponentou
`components/ui/SelectMenu.vue` ve vzhledu dashboardu. Žádná nová závislost (ikona `ChevronDown` z `lucide-vue-next`,
který už je v `dependencies`). `vendor/` a `prototype/` se nemění. Testy nevolají model.

Out of scope: vyhledávání v seznamu, multi-select.

## Inventura (9 míst, `data-test` musí zůstat)
| soubor | data-test | vazba |
|---|---|---|
| `components/backlog/BacklogFilters.vue` | `state-filter` | `:value`+`@change` → emit `update:filters` |
| `components/runs/RunsList.vue` | `state-filter` | `setFilter('state', …)` |
| `components/runs/RunsList.vue` | `task-filter` | `setFilter('task', …)` |
| `components/backlog/TaskForm.vue` | `step` | `v-model="step"` (+`required`, jen mode add) |
| `components/backlog/TaskForm.vue` | `status` | `v-model="status"`, `:disabled="isDone"`, volba `done` jen když isDone |
| `components/backlog/TaskForm.vue` | `workflow` | `v-model="workflow"`, `''` = „zděděné“ |
| `components/backlog/TaskDetail.vue` | `workflow-select` | `v-model="workflowChoice"`, `''` = „zděděné“ |
| `components/settings/SettingsForm.vue` | `git_provider` | `v-model`, `invalid`, volba s neznámou aktuální hodnotou |
| `components/settings/SettingsForm.vue` | `merge_strategy` | dtto |

## 1. Komponenta `aifactory/web/src/components/ui/SelectMenu.vue`

Vzor: `components/ui/Tooltip.vue` (Teleport do `body`, `position: fixed`, poslech scroll/resize).
ARIA vzor „select-only combobox“ (WAI-ARIA APG): fokus zůstává na spouštěči, aktivní položka přes `aria-activedescendant`.

### API
```ts
export interface SelectOption { value: string; label: string }
props: {
  modelValue: string
  options: SelectOption[]
  label: string            // přístupný název → aria-label spouštěče (popisek pro čtečky)
  disabled?: boolean       // default false
  invalid?: boolean        // default false → aria-invalid="true" + třída .invalid (červený okraj)
  placeholder?: string     // text, když modelValue neodpovídá žádné volbě (default '')
}
emits: { 'update:modelValue': [value: string] }
```
Typ `SelectOption` exportovat z `<script lang="ts">` bloku (vedle `<script setup>`), nebo z nového `lib/select.ts`
(doporučeno `lib/select.ts` — čistá logika typeahead je tam i testovatelná, viz níže).

`defineOptions({ inheritAttrs: false })` a `v-bind="$attrs"` na spouštěcí `<button>` — tím `data-test`, `class`, `id`
apod. skončí na poli samotném (komponenta má fragmentový root: button + Teleport).

### Šablona
```html
<button type="button" ref="trigger" class="select-trigger" :class="{ open, invalid }" v-bind="$attrs"
  role="combobox" aria-haspopup="listbox" :aria-expanded="open ? 'true' : 'false'" :aria-controls="listId"
  :aria-activedescendant="open && active >= 0 ? optionId(active) : undefined"
  :aria-label="label" :aria-invalid="invalid ? 'true' : undefined" :disabled="disabled"
  :data-value="modelValue"
  @click="toggle" @keydown="onKeydown" @blur="onBlur?">
  <span class="select-value" :class="{ faint: !current }">{{ current?.label ?? placeholder }}</span>
  <ChevronDown :size="16" aria-hidden="true" />
</button>
<Teleport to="body">
  <ul v-if="open" :id="listId" ref="list" role="listbox" class="select-list" data-test="select-list"
      :aria-label="label" :style="{ top, left, minWidth, maxHeight, visibility: measured ? 'visible':'hidden' }">
    <li v-for="(opt, i) in options" :key="opt.value" :id="optionId(i)" role="option"
        :aria-selected="opt.value === modelValue ? 'true' : 'false'" :data-value="opt.value"
        :class="{ active: i === active, selected: opt.value === modelValue }"
        @mousedown.prevent  @mousemove="active = i" @click="choose(i)">{{ opt.label }}</li>
  </ul>
</Teleport>
```
- `listId = select-${++seq}` (modulový čítač jako v Tooltipu).
- `@mousedown.prevent` na položkách → fokus zůstane na spouštěči.
- Pokud chceš, `✓`/`Check` ikonu u vybrané položky (lucide `Check`), jinak stačí zvýraznění.

### Chování
- **Myš:** klik na spouštěč přepíná otevření (ne při `disabled`). Klik na položku → `emit('update:modelValue', value)`
  jen když se liší od aktuální, zavřít, fokus zpět na spouštěč. Hover nastaví aktivní položku.
- **Klik mimo:** při otevření `document.addEventListener('pointerdown', onOutside, true)` (+ `mousedown` jako fallback
  pro happy-dom je OK – stačí jeden typ, ale testy musí triggerovat ten samý; doporučeno `mousedown`, který Playwright
  i happy-dom spolehlivě posílají). Pokud cíl není uvnitř `trigger` ani `list` → zavřít (bez změny hodnoty).
  Při zavření/odmontování posluchače odebrat (`onBeforeUnmount`).
- **Scroll/resize:** při otevření `window.addEventListener('scroll', onScroll, true)` a `resize`. Scroll, jehož
  `event.target` je uvnitř seznamu, ignorovat; jinak seznam zavřít (jako Tooltip). Resize zavře.
- **Pozice:** po otevření `await nextTick()`, změřit `trigger.getBoundingClientRect()`; `left = r.left`,
  `minWidth = r.width`, `top = r.bottom + 4`; pokud se dolů nevejde (`top + listHeight > innerHeight - 8`) a nahoru ano,
  dát nad (`r.top - listHeight - 4`). `left` oříznout do okna. `max-height: min(320px, …)`, `overflow-y: auto`.
  Seznam je v `body` s `position: fixed` → nad horní lištou (z-index 10) a neořízne ho žádný `overflow` kontejner.
- **Klávesnice na spouštěči — zavřeno:**
  - `ArrowDown`, `ArrowUp`, `Enter`, ` ` (Space), `Alt+ArrowDown` → `preventDefault`, otevřít; aktivní = index vybrané
    volby (nebo 0).
  - Tisknutelný znak (`key.length === 1`, bez Ctrl/Meta/Alt) → typeahead (viz níže) a nalezenou volbu rovnou
    **vybrat** (emit), jako nativní select. Seznam se neotevírá.
- **Klávesnice — otevřeno:**
  - `ArrowDown`/`ArrowUp` posun o 1 (bez zacyklení, clamp), `Home`/`End` první/poslední, `PageDown`/`PageUp` ±10 (clamp).
    Vždy `preventDefault`; aktivní položku `scrollIntoView?.({ block: 'nearest' })` (volitelné volání — happy-dom).
  - `Enter` / `Space` → vybrat aktivní, zavřít, `preventDefault` (Enter nesmí odeslat formulář).
  - `Escape` → zavřít bez změny, `preventDefault` + `stopPropagation` (ať nezavře nadřazený dialog).
  - `Tab` → vybrat aktivní (APG), zavřít, **nebránit** výchozí akci (fokus jde dál).
  - Tisknutelný znak → typeahead přesune **aktivní** položku (nevybírá).
- **Typeahead** (čistá funkce v `lib/select.ts`):
  `export function typeaheadIndex(labels: string[], query: string, from: number): number` — case-insensitive
  `startsWith` (použij `toLocaleLowerCase('cs')`), hledá od `from + 1` dokola, vrací -1 když nic.
  V komponentě buffer znaků s resetem po 500 ms (`setTimeout`); když buffer obsahuje jediný opakovaný znak
  (např. „tt“), hledat jen ten znak → cyklení mezi položkami se stejným začátkem. Při prvním znaku nového bufferu
  hledat od aktuální pozice (`from = active`), při delším bufferu od `active - 1` (aby zůstala aktuální, pokud stále sedí).
- **Disabled:** `<button disabled>` — nelze otevřít ani měnit; když se `disabled` za otevření změní na true, zavřít.
- Když se `options` změní a otevřený `active` je mimo rozsah, clamp.

### Styl (scoped v komponentě; proměnné ze `style.css`)
- Spouštěč: `display: inline-flex; align-items: center; justify-content: space-between; gap: 8px; min-width: 120px;`
  `padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--panel); color: var(--text);`
  `font: inherit; text-align: left; cursor: pointer;` hover/focus-visible `border-color: var(--blue)`,
  `.open` šipka otočená (`transform: rotate(180deg)`), `.invalid { border-color: var(--red) }`,
  `:disabled { opacity: .5; cursor: default }`. Text hodnoty `overflow: hidden; text-overflow: ellipsis; white-space: nowrap`.
  Kompaktní velikost pro filtry: místa si případně doladí `padding` přes vlastní třídu — ale scoped styl rodiče na
  fragmentový root nedosáhne, proto raději prop **ne**; místo toho dej komponentě rozumný default `padding: 5px 8px`
  a nepřizpůsobuj per místo (vizuálně dostačuje). Šířku řeší rodič přes layout (ve formulářích je label `flex-direction:
  column` → spouštěč se roztáhne, když dáš `.select-trigger { width: 100% }`? NE — ve filtrech by se roztáhl. Řešení:
  `align-self` neřešit, šířka = obsah, ve formulářích (TaskForm, SettingsForm) je OK roztažení díky `align-items: stretch`
  flex sloupce, ve filtrech (`inline-flex` řádek) zůstane na šířku obsahu.)
- Seznam: `position: fixed; z-index: var(--z-dropdown); margin: 0; padding: 4px; list-style: none;`
  `border: 1px solid var(--border); border-radius: 8px; background: var(--panel-2); box-shadow: var(--shadow-pop);`
  `font-family: var(--sans); font-size: 16px; overflow-y: auto;` krátká animace jako `tip-in`.
  Položka: `padding: 6px 10px; border-radius: 6px; cursor: pointer; white-space: nowrap; color: var(--text)`;
  `.active { background: var(--panel-3) }` (v obou tématech viditelné; případně `color-mix`/`rgba(108,182,255,.12)`),
  `.selected { color: var(--blue); font-weight: 600 }`.
- Teleportovaný obsah: scoped styly Vue fungují i pro Teleport (scope atribut se přidá), takže styl seznamu může být
  ve scoped bloku.

### `style.css`
Do `:root` přidat `--z-dropdown: 1050;` a upravit komentář („Layers above the sticky topbar (z-index 10): the modal,
the dropdown list over it, and the tooltip on top.“). Pořadí: modal 1000 < dropdown 1050 < tooltip 1100.

## 2. Nahrazení devíti míst
Ve všech souborech: `import SelectMenu from '@/components/ui/SelectMenu.vue'` (a typ z `@/lib/select`), opcí pole jako
`computed<SelectOption[]>`. Ze scoped stylů odstranit selektor `select` (v `BacklogFilters.vue`, `RunsList.vue`,
`TaskForm.vue` — jen z výčtu `input[type='text'], select, textarea`, `TaskDetail.vue` — z `input, select`,
`SettingsForm.vue` — z výčtu). Obalující `<label>` s viditelným textem ponechat (layout), `label` prop nese stejný text.

- **BacklogFilters.vue:** `options = [{value:'', label:'vše'}, ...BOARD_STATES.map(s => ({value:s, label:STATE_LABELS[s]}))]`;
  `<SelectMenu data-test="state-filter" label="Stav" :model-value="status" :options="statusOptions" @update:model-value="setStatus" />`;
  `setStatus(value: string)` místo eventu.
- **RunsList.vue:** dvě volby (`stateOptions` z `RUN_STATES`/`STATE_LABELS`, `taskOptions` z `tasks`, obě s `''`/„vše“
  na začátku); `setFilter(key, value: string)`. `label="Stav"`, `label="Task"`.
- **TaskForm.vue:**
  - step: `stepOptions = steps.map(s => ({ value: s.id, label: s.title ? `${s.id} · ${s.title}` : s.id }))`,
    `<SelectMenu v-model="step" data-test="step" label="Step" :options="stepOptions" />` (`required` odpadá — `canSubmit`
    už prázdný step hlídá).
  - status: `statusOptions = [...(isDone ? [{value:'done',label:'done'}] : []), {todo}, {cancelled}]`,
    `<SelectMenu v-model="status" data-test="status" label="Status" :options="statusOptions" :disabled="isDone" />`.
    Pozor na typ `status` ref (`initialStatus` může být union typ) — pokud vue-tsc hlásí, dej `ref<string>(initialStatus)`.
  - workflow: `[{value:'', label:'zděděné'}, ...workflows]`, `label="Workflow"`.
- **TaskDetail.vue:** `<SelectMenu v-model="workflowChoice" data-test="workflow-select" label="Workflow" :options="workflowOptions" />`.
  Kontejner `.add` je `display:flex` — OK.
- **SettingsForm.vue:** pro oba: `options = (current not in list ? [current] : []).concat(list).map(v => ({value:v,label:v}))`
  (zachovat dnešní chování „neznámá hodnota se ukáže“). `<SelectMenu v-model="values.git_provider" data-test="git_provider"
  label="Git provider" :options="gitProviderOptions" :invalid="invalid('git_provider')" />`, obdobně `merge_strategy`
  s `label="Merge strategie"`. Hint `azure-hint` a `error-*` spany beze změny. Zkontroluj typ `values` (možná
  `reactive` s `string` poli) — `v-model` na komponentě s `modelValue: string` musí projít vue-tsc.

## 3. Testy (vitest, `aifactory/web`)

### Pomocník `aifactory/web/src/test/select.ts`
```ts
import type { DOMWrapper, VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
export function listOptions(): HTMLElement[]  // document.body.querySelectorAll('[data-test="select-list"] [role="option"]')
export async function openSelect(wrapper, selector): Promise<HTMLElement[]>  // klik na trigger, flushPromises, vrátí options
export async function chooseOption(wrapper: VueWrapper, selector: string, value: string): Promise<void>
  // klik na trigger → najde li[data-value=value] v body → dispatch click → await flushPromises()
export function optionLabels(): string[]
```
Teleport do `body` funguje i bez `attachTo`; přesto v testech, kde se otevírá seznam, po testu `wrapper.unmount()` a
`document.body.innerHTML = ''` (afterEach, jako `Tooltip.test.ts`), aby nezůstávaly seznamy z předchozího testu.

### Nový `components/ui/SelectMenu.test.ts`
Mount s `attachTo: document.body`, harness s `v-model` (např. `h(SelectMenu, { modelValue, 'onUpdate:modelValue': v => wrapper.setProps({modelValue: v}) })`
nebo `defineComponent` s ref). Pokrýt:
1. Render: trigger má `role="combobox"`, `aria-label`, `aria-expanded="false"`, zobrazuje label vybrané volby; `data-test`
   z atributů skončí na buttonu; neexistuje žádný `<select>`.
2. Myš: klik otevře (`aria-expanded="true"`, seznam v `document.body`, `aria-controls` = id seznamu, vybraná má
   `aria-selected="true"`); klik na volbu emituje `update:modelValue` a zavře; klik na již vybranou nic neemituje.
3. Klik mimo (mousedown/pointerdown na `document.body`) zavře bez emitu; klik do seznamu ho nezavře.
4. Klávesnice: ArrowDown otevře s aktivní = vybraná; ArrowDown/ArrowUp mění `aria-activedescendant`; Home/End;
   Enter vybere a zavře; Escape zavře bez změny; Tab vybere aktivní a zavře; Space otevře.
5. Typeahead: otevřeno — psaní „c“ přesune aktivní na první volbu začínající „c“, opakované „c“ cyklí; zavřeno —
   znak rovnou emituje hodnotu. Použij `vi.useFakeTimers()` pro reset bufferu (500 ms) nebo test jen jednoho bufferu.
6. Vázaná hodnota: změna `modelValue` z rodiče změní zobrazený text; neznámá hodnota ukáže `placeholder`.
7. `disabled`: button má atribut `disabled`, klik ani klávesy neotevřou.
8. `invalid`: `aria-invalid="true"` a třída `invalid`.
9. Scroll mimo seznam zavře (dispatch `scroll` na `window`/`document`).

`lib/select.test.ts`: unit testy `typeaheadIndex` (case-insensitive, diakritika přes `toLocaleLowerCase`, wrap-around,
-1 když nic).

### Úprava existujících testů (místo `setValue` na selectu → `chooseOption`, místo `findAll('option')` → `openSelect`/`optionLabels`)
- `components/backlog/BacklogFilters.test.ts` (ř. 8–13): 8 voleb, výběr `blocked` a `''`.
- `components/runs/RunsList.test.ts` (ř. ~33–37): `task-filter` labely, `state-filter` → `failed`, `task-filter` → `''`.
- `components/backlog/TaskForm.test.ts` (ř. 30, 49, 61, 68, 70 a test „disables the status of a done task“ — `attributes('disabled')`
  funguje dál na buttonu).
- `components/backlog/TaskDetail.test.ts` (ř. 73, 75).
- `components/settings/SettingsForm.test.ts` (ř. 26 labely `merge_strategy`, ř. 62, ř. 107 `azure`); přidat aserci, že při
  chybě pole má trigger `aria-invalid="true"` (pokud tam už test chybových stavů je, rozšířit ho pro select pole).
- `views/BacklogView.test.ts` (ř. 59), `views/RunsView.test.ts` (ř. 48).
- Projdi `grep -rn "setValue\|option" src --include='*.test.ts'` a ověř, že žádný test nevolá `setValue` na jednom z 9
  `data-test` výše.

### Strážce `lib/noNativeUi.test.ts`
Přidat test: žádná `.vue` šablona (po odstranění `<script>`/`<style>`, stejně jako u tooltipů) neobsahuje `<select`
(`/<select[\s>]/`), a popis/komentář souboru doplnit („…own ConfirmDialog, Tooltip and SelectMenu…“).

## 4. E2E `aifactory/tests/e2e/test_f3_browser.py`
V `_create_task` (ř. 139) nahradit `select_option` za:
```python
step = page.locator('[data-test="step"]')
step.click()
listbox = page.get_by_role("listbox")
expect(listbox).to_be_visible()
listbox.locator('[role="option"][data-value="M01-S01"]').click()
expect(listbox).to_have_count(0)
expect(step).to_have_attribute("data-value", "M01-S01")
```
(`data-value` na triggeru je v šabloně výše.) Volitelně v jiném testu krátce klávesnicí (`focus` + `ArrowDown` + `Enter`),
není nutné. Pozor na `_no_native_tooltips` — komponenta nesmí mít `title` atribut.
Python kód musí projít `ruff check` a `ruff format --check` a `mypy`.

## 5. Build
`just web-build` (= `cd aifactory/web && bun install --frozen-lockfile && bun run build`) přegeneruje
`aifactory/src/aifactory/web/static/` (emptyOutDir — staré hash soubory zmizí, nové vzniknou; to je očekávané).
Build spustit **až po** finálních změnách ve frontendu. `bun.lock`/`package.json` se nesmí změnit.

## 6. Ověření (vše musí projít, posuzuj podle exit kódu)
1. `just web-test` (typecheck vue-tsc + vitest) — součást `just test`.
2. `just test`
3. `just typecheck`
4. `just lint`
5. `just web-build` → `git status aifactory/src/aifactory/web/static` ukazuje nové assety.
6. `just e2e` (Playwright nad `factory obs`, systémový Chrome; když chybí, `just e2e-install`).
7. `grep -rn "<select" aifactory/web/src` → nic.
8. `git status` — změny jen v `aifactory/`, `justfile` (neměnit, není potřeba), spec a app_docs.

## Soubory
Nové: `aifactory/web/src/components/ui/SelectMenu.vue`, `aifactory/web/src/components/ui/SelectMenu.test.ts`,
`aifactory/web/src/lib/select.ts`, `aifactory/web/src/lib/select.test.ts`, `aifactory/web/src/test/select.ts`.
Měněné: `style.css`, `BacklogFilters.vue/.test.ts`, `RunsList.vue/.test.ts`, `TaskForm.vue/.test.ts`,
`TaskDetail.vue/.test.ts`, `SettingsForm.vue/.test.ts`, `views/BacklogView.test.ts`, `views/RunsView.test.ts`,
`lib/noNativeUi.test.ts`, `aifactory/tests/e2e/test_f3_browser.py`, `aifactory/src/aifactory/web/static/**` (build).
