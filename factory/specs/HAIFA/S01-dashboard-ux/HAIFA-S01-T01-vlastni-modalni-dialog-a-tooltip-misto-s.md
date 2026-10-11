# HAIFA-S01-T01 — Vlastní modální dialog a tooltip místo systémových

## Cíl
Dashboard (`aifactory/web/src/`) nesmí volat `window.confirm` / `alert` / `prompt` a žádný prvek nesmí mít nativní tooltip (atribut `title`, SVG `<title>`). Místo nich vzniknou dvě sdílené komponenty — `ConfirmDialog` a `Tooltip` — ve vzhledu dashboardu.

## Současný stav (zjištěno)
- `window.confirm`: `components/review/ReviewActions.vue:16` (Schválit, text obsahuje `detail.approve_note`), `components/runs/RunDetail.vue:38` (Zastavit).
- Testy podvrhující `window.confirm`: `ReviewActions.test.ts:17`, `RunDetail.test.ts:39`, `views/ReviewView.test.ts:104,168`, `views/RunsView.test.ts:83,105`.
- Nativní tooltipy:
  - `App.vue:94` přepínač motivu (`:title`), `App.vue:110` `.repo-chip` (`:title="health.repo"`); `App.test.ts:63` testuje `chip.attributes('title')`.
  - `components/backlog/TreeNode.vue:15` odznak `auto`.
  - `components/backlog/TaskDetail.vue:182,220` tlačítka „Odebrat vazbu“ (ikonová, `X`).
  - `components/backlog/DependencyGraph.vue:73,89` SVG `<title>` v uzlech grafu (uzly `task` jsou `<a>`, ostatní `<g>`), graf je v kontejneru s `overflow: auto` (ř. 117).
  - `components/runs/PhaseDots.vue:26` tečky fází.
  - `components/runs/StatChip.vue:36` statistiky (`TITLES[kind]`).
  - `title` u `DetailSection` (ReviewDetail, PhaseDetail, DiffView) je **prop komponenty**, nevykresluje atribut — neměnit.
- Horní lišta: `App.vue` `.topbar { position: sticky; z-index: 10 }`.
- Žádné nové závislosti (frontend: vue, lucide-vue-next, @fontsource/play; dev: vitest, @vue/test-utils, happy-dom). `tsconfig` má `types: ["vite/client"]`.
- Build: `just web-build` (= `cd aifactory/web && bun install --frozen-lockfile && bun run build`) zapisuje do `aifactory/src/aifactory/web/static/` (emptyOutDir).
- `just test` spouští i `web-test` (vue-tsc + vitest), pak pytest. `just e2e` = Playwright `tests/e2e`.

## Návrh

### 1. `aifactory/web/src/components/ui/ConfirmDialog.vue` (nový, sdílený)
Props:
```ts
open: boolean
title: string
message?: string          // víceřádkový text, renderovat s white-space: pre-wrap
confirmLabel?: string     // default 'Potvrdit'
cancelLabel?: string      // default 'Zrušit'
tone?: 'default' | 'danger'  // danger = červené tlačítko Potvrdit (Zastavit)
```
Emits: `confirm`, `cancel`.

Šablona (vše uvnitř `<Teleport to="body">`, `v-if="open"` — zavřený dialog v DOM není):
```html
<div class="modal-backdrop" data-test="confirm-backdrop" @mousedown.self="emit('cancel')">
  <div ref="panel" class="modal" role="dialog" aria-modal="true"
       :aria-labelledby="titleId" :aria-describedby="message ? msgId : undefined"
       data-test="confirm-dialog" @keydown="onKeydown">
    <h2 :id="titleId" class="modal-title">{{ title }}</h2>
    <p v-if="message" :id="msgId" class="modal-message" data-test="confirm-message">{{ message }}</p>
    <div class="modal-actions">
      <button type="button" class="btn" data-test="confirm-cancel" @click="emit('cancel')">{{ cancelLabel }}</button>
      <button ref="okBtn" type="button" class="btn primary" :class="tone" data-test="confirm-ok" @click="emit('confirm')">{{ confirmLabel }}</button>
    </div>
  </div>
</div>
```
Chování:
- `watch(() => props.open, …, { immediate: true })`: při otevření uložit `returnTo = document.activeElement as HTMLElement | null`, po `nextTick` dát fokus na `okBtn`. Při zavření (open → false) a v `onBeforeUnmount`, pokud byl otevřený, po `nextTick` `returnTo?.focus()` (jen když je `returnTo` stále v dokumentu: `returnTo.isConnected`).
- `onKeydown(e)`:
  - `Escape` → `preventDefault`, `stopPropagation`, `emit('cancel')`.
  - `Enter` → pokud `e.target` je tlačítko `confirm-cancel`, nechat výchozí chování (aktivuje Zrušit); jinak `preventDefault` + `emit('confirm')`. (Fokus je výchozí na Potvrdit, takže Enter potvrdí.)
  - `Tab` / `Shift+Tab` → past na fokus: seznam fokusovatelných prvků v `panel` (`button:not([disabled]), [href], input, textarea, select, [tabindex]:not([tabindex="-1"])`); z posledního na první a naopak, `preventDefault`. Pokud je fokus mimo panel, vrátit ho na první.
- Také zachytit `focusin` na `document` (listener registrovaný jen když je open, odregistrovat při zavření/unmountu): když `e.target` není uvnitř panelu, vrátit fokus na `okBtn`.
- id generovat počítadlem na úrovni modulu (`let seq = 0`), ne `useId` (kvůli jednoduchosti; obojí je ok ve Vue 3.5).
- Styl (scoped): backdrop `position: fixed; inset: 0; z-index: var(--z-modal); background: rgba(3,6,12,.6); backdrop-filter: blur(3px); display:grid; place-items:center`. Panel: `background: var(--surface)` / `var(--panel)`, `border: 1px solid var(--border)`, `border-radius: 12px`, `padding: 20px 22px`, `max-width: min(560px, calc(100vw - 32px))`, stín, `color: var(--text)`. Tlačítka ve stylu dashboardu (`.btn` jako v ReviewActions: border, `var(--panel-2)`, radius 8px; `.primary` zelený akcent `var(--green)`, `.primary.danger` `var(--red)`). Respektovat světlý motiv (proměnné to řeší; backdrop ve světlém motivu `rgba(20,30,50,.35)` přes `[data-theme="light"]` — ve scoped stylu použít `:global([data-theme="light"]) .modal-backdrop`).

### 2. `aifactory/web/src/lib/confirm.ts` (nový) — promise API pro komponenty
```ts
import { reactive } from 'vue'
export interface ConfirmOptions { title: string; message?: string; confirmLabel?: string; cancelLabel?: string; tone?: 'default' | 'danger' }
export function useConfirm() {
  const dialog = reactive({ open: false, title: '', message: '', confirmLabel: 'Potvrdit', cancelLabel: 'Zrušit', tone: 'default' as 'default' | 'danger' })
  let resolver: ((ok: boolean) => void) | null = null
  function settle(ok: boolean) { dialog.open = false; const r = resolver; resolver = null; r?.(ok) }
  function ask(opts: ConfirmOptions): Promise<boolean> {
    settle(false) // případný předchozí dotaz = zrušen
    Object.assign(dialog, { message: '', confirmLabel: 'Potvrdit', cancelLabel: 'Zrušit', tone: 'default' }, opts, { open: true })
    return new Promise((resolve) => { resolver = resolve })
  }
  return { dialog, ask, confirm: () => settle(true), cancel: () => settle(false) }
}
```
Použití v komponentě: `<ConfirmDialog v-bind="dialog" @confirm="confirm" @cancel="cancel" />`. (Pozor: `ask` nepojmenovávat `confirm` na úrovni volání tak, aby to vypadalo jako `confirm(` globálně — viz guard test v bodě 7; destrukturovat jako `const { dialog, ask, confirm: onDialogConfirm, cancel: onDialogCancel } = useConfirm()`.)

### 3. `aifactory/web/src/components/ui/Tooltip.vue` (nový, sdílený)
Props:
```ts
text: string
anchor?: Element | null      // řízený režim (SVG graf): pokud je zadán, tooltip se ukáže u tohoto prvku a slot se nepoužije
placement?: 'bottom' | 'top' // default 'bottom'; automaticky se překlopí, když se nevejde
```
Dva režimy:
- **Obal (slot)**: `<span ref="anchorEl" class="tip-anchor" data-test="tip-anchor" @mouseenter="show" @mouseleave="hide" @focusin="show" @focusout="hide" @keydown.esc="hide"><slot /></span>`; `.tip-anchor { display: inline-flex; }` (nesmí rozbít layout — `display: contents` nepoužívat, getBoundingClientRect by vrátil nuly). Když je bublina vidět, nastavit na první fokusovatelný potomek / obal `aria-describedby` — jednoduše: obal dostane `:aria-describedby="visible ? id : undefined"`.
- **Řízený (`anchor` prop)**: bez slotu; `visible = computed(() => !!props.anchor)`; pozice se počítá z `props.anchor`.
- Bublina: `<Teleport to="body"><div v-if="visible" :id="id" ref="bubble" role="tooltip" class="tooltip" data-test="tooltip" :style="{ top: `${pos.top}px`, left: `${pos.left}px` }">{{ text }}</div></Teleport>`.
- Pozicování (`position: fixed`, tedy nad sticky lištou a mimo rolovací kontejnery i SVG): po zobrazení `await nextTick()`, `r = anchor.getBoundingClientRect()`, `b = bubble.getBoundingClientRect()`; `top = r.bottom + 8`; když `top + b.height > innerHeight - 8` (nebo `placement === 'top'` a nahoře je místo) → `top = r.top - b.height - 8`; `left = clamp(r.left + r.width/2 - b.width/2, 8, innerWidth - b.width - 8)`. Před změřením bublinu vykreslit s `visibility: hidden` (stav `measured`), aby neproblikla v rohu.
- Při otevření registrovat `window.addEventListener('scroll', hide, true)` a `resize` → skrýt (v řízeném režimu emitovat nic — rodič při scrollu stav stejně ztratí přes mouseleave; stačí `hidden` lokální flag resetovaný při změně `anchor`). Odregistrovat při skrytí a v `onBeforeUnmount`.
- Bez zpoždění (deterministické testy). CSS fade-in přes `@keyframes` je volitelný.
- Styl: `position: fixed; z-index: var(--z-tooltip); max-width: 320px; padding: 6px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--panel-2); color: var(--text); font-size: 13px; line-height: 1.35; box-shadow: 0 8px 24px rgba(0,0,0,.35); pointer-events: none; white-space: pre-line; overflow-wrap: anywhere;`.

### 4. `aifactory/web/src/style.css`
Do `:root` přidat `--z-modal: 1000; --z-tooltip: 1100;` (tooltip nad modálem i nad lištou s `z-index: 10`). Případně sdílený `--shadow-pop`. Nic dalšího.

`main.ts`: změna není nutná (komponenty se importují lokálně, nic se neregistruje globálně). Neměnit, pokud k tomu nevznikne důvod.

### 5. Napojení modálu
- `ReviewActions.vue`:
  ```ts
  const { dialog, ask, confirm: onDialogConfirm, cancel: onDialogCancel } = useConfirm()
  async function onApprove() {
    const ok = await ask({
      title: `Schválit a mergovat PR ${props.detail.task_id} do ${props.detail.pr.base}?`,
      message: props.detail.approve_note,
      confirmLabel: 'Potvrdit', cancelLabel: 'Zrušit',
    })
    if (ok) emit('approve')
  }
  ```
  V šabloně (kdekoli uvnitř kořene): `<ConfirmDialog v-bind="dialog" @confirm="onDialogConfirm" @cancel="onDialogCancel" />`.
- `RunDetail.vue`: obdobně, `title: \`Zastavit běh ${run.value.run_id} tasku ${run.value.task_id}?\``, `tone: 'danger'`, tlačítka Potvrdit / Zrušit; `if (ok) emit('stop')`.
- Návrat fokusu: tlačítko Schválit/Zastavit dostane fokus při kliknutí (v prohlížeči) → `returnTo` ho zachytí. Pro jistotu v `onApprove`/`onStop` nic dalšího netřeba.

### 6. Napojení tooltipu (odstranit všechny `title=`/`:title=` atributy a SVG `<title>`)
- `App.vue`: přepínač motivu obalit `<Tooltip :text="themeLabel">…button…</Tooltip>`, kde `themeLabel = computed(() => theme.value === 'dark' ? 'Přepnout na světlý motiv' : 'Přepnout na tmavý motiv')`; tlačítku přidat `:aria-label="themeLabel"` (jinak by ikonové tlačítko ztratilo přístupné jméno). `.repo-chip` obalit `<Tooltip :text="health.repo">`; aby šel chip fokusovat z klávesnice, dát mu `tabindex="0"`. Pozor, že `.topbar-right` je flex — obal `inline-flex` to nerozbije; ověřit vizuálně.
- `TreeNode.vue`: `<Tooltip text="auto-continue zapnuto"><span class="auto" data-test="auto-badge" tabindex="0">auto</span></Tooltip>`.
- `TaskDetail.vue` (2×): `<Tooltip text="Odebrat vazbu"><button … aria-label="Odebrat vazbu">…</button></Tooltip>` (bez `title`).
- `PhaseDots.vue`: každou tečku obalit `<Tooltip :text="`${p.name} — ${p.status}`">`, tečce `tabindex="0"` a `:aria-label` se stejným textem. `:key` přesunout na `Tooltip`.
- `StatChip.vue`: kořen `<Tooltip :text="TITLES[kind]"><span class="stat" :data-stat="kind" tabindex="0">…</span></Tooltip>` (pozor: `data-stat` zůstává na `.stat`, testy ho hledají).
- `DependencyGraph.vue`: odstranit oba `<title>`. Přidat stav `const tip = ref<{ el: Element; text: string } | null>(null)`; funkce `nodeLabel(node) = \`${node.id} ${node.title ?? ''} (${stateText(node)})\``; na `<a>` (task) i `<g>` (ostatní) `@mouseenter="tip = { el: $event.currentTarget, text: nodeLabel(node) }"`, `@mouseleave="tip = null"`, `@focus`/`@blur` totéž (u `<a>` fungují nativně; `<g>` doplnit `tabindex="0"`), plus `:aria-label="nodeLabel(node)"`. Mimo `<svg>` (např. hned za ním, uvnitř kořene komponenty) `<Tooltip :text="tip?.text ?? ''" :anchor="tip?.el ?? null" />`. Typově `$event.currentTarget as Element` udělat v metodě `showTip(e: Event, node)`.
- `DiffView.vue` / `ReviewDetail.vue` / `PhaseDetail.vue`: `title` je prop `DetailSection`, nic neměnit.
- Po úpravách: `grep -rnE '(^|\s)(:)?title="' aifactory/web/src --include=*.vue` smí najít jen `DetailSection` props; `grep -rn '<title>' aifactory/web/src` nic.

### 7. Unit testy (vitest)
Nové:
- `components/ui/ConfirmDialog.test.ts` — mount s `attachTo: document.body`, dialog je teleportovaný do `document.body`, hledat přes `document.body.querySelector`. Případy:
  1. `open=false` → `[data-test="confirm-dialog"]` neexistuje.
  2. klik na `confirm-ok` → emit `confirm`; klik na `confirm-cancel` → emit `cancel`.
  3. `keydown` Escape na dialogu → `cancel`; Enter → `confirm`.
  4. `mousedown` na backdrop → `cancel`; `mousedown` uvnitř panelu nic.
  5. Fokus: před otevřením fokusovat tlačítko mimo (vytvořené v testu), otevřít (`setProps({open:true})`, `await nextTick()` ×2 / `flushPromises`) → `document.activeElement` je `confirm-ok`; Tab z posledního tlačítka → fokus na první (cancel); zavřít (`setProps({open:false})`) → fokus zpět na původní tlačítko.
  Každý test `wrapper.unmount()`.
- `lib/confirm.test.ts` — `ask()` vrací promise: `confirm()` → `true`, `cancel()` → `false`; druhý `ask()` během otevřeného zruší první (`false`).
- `components/ui/Tooltip.test.ts` — obalový režim: `trigger('mouseenter')` na `.tip-anchor` → v `document.body` je `[data-test="tooltip"][role="tooltip"]` s textem; `mouseleave` → zmizí; `focusin` → ukáže, `focusout` → skryje; Escape skryje. Řízený režim: `anchor` = element → viditelný; `anchor=null` → skrytý. Ověřit, že tooltip je přímým potomkem `body` (teleport), tj. mimo rolovací kontejner.
- `lib/noNativeUi.test.ts` (guard): `import.meta.glob('/src/**/*.{vue,ts}', { query: '?raw', import: 'default', eager: true })`, vynechat `*.test.ts` a sám sebe; pro každý soubor očekávat, že neobsahuje `/window\.(confirm|alert|prompt)\b/` ani `/(?<![\w.$])(alert|prompt)\s*\(/`, a `.vue` soubory neobsahují `<title>`. (Volání `confirm(` bez `window.` regex nechytá záměrně kvůli `useConfirm`; `window.confirm` stačí.)

Úpravy:
- `ReviewActions.test.ts` „approves after a confirm“: bez `vi.spyOn(window,'confirm')`. Klik na `approve` → v `document.body` je `confirm-dialog`, jeho `confirm-message` obsahuje `approve_note` (OB3 text); klik `confirm-cancel` → `flushPromises` → žádný emit `approve`, dialog zmizel; znovu klik `approve` → `confirm-ok` → `flushPromises` → `emitted('approve')` délky 1. `wrapper.unmount()` na konci.
- `RunDetail.test.ts` „emits stop after confirmation“: stejně (Zrušit → nic, Potvrdit → `stop`).
- `views/ReviewView.test.ts:104,168` a `views/RunsView.test.ts:83,105`: odstranit spy, po kliknutí na approve/stop zavolat helper a pak `flushPromises`.
- Helper `src/test/modal.ts`:
  ```ts
  import { flushPromises } from '@vue/test-utils'
  export function openDialog(): HTMLElement | null { const all = document.body.querySelectorAll<HTMLElement>('[data-test="confirm-dialog"]'); return all[all.length - 1] ?? null }
  export async function answerDialog(ok: boolean) {
    await flushPromises()
    const d = openDialog(); if (!d) throw new Error('confirm dialog is not open')
    d.querySelector<HTMLButtonElement>(ok ? '[data-test="confirm-ok"]' : '[data-test="confirm-cancel"]')!.click()
    await flushPromises()
  }
  ```
  Ve view testech přidat `wrapper.unmount()`, aby v `body` nezůstaly teleporty (pokud tam ještě není).
- `App.test.ts:63`: místo `attributes('title')` ověřit, že `.repo-chip` nemá atribut `title`, a po `trigger('mouseenter')` na jeho `.tip-anchor` (nebo `focusin` na chipu — bublá) je v `document.body` `[data-test="tooltip"]` s textem `/work/HAIFA`. Přidat test, že přepínač motivu nemá `title`, má `aria-label` a ukáže tooltip na `focusin`. Mount s `attachTo: document.body`, na konci `unmount`.
- Testy `PhaseDots`/`StatChip`/`TreeNode`/`TaskDetail`/`DependencyGraph`: tam, kde existují test soubory (BacklogTree, TaskDetail, DependencyGraph, RunDetail/RunsList), přidat po jednom asertu: prvek nemá `title`, graf neobsahuje `title` element, a v DependencyGraph `mouseenter` na `[data-node]` ukáže tooltip s id uzlu. Ověřit, že existující selektory (`[data-stat]`, `[data-test="auto-badge"]`, `[data-node]`, `unlink-*`) dál fungují.

### 8. Prohlížečový test `aifactory/tests/e2e/test_f3_browser.py`
- Ve fixture (ř. ~109) nahradit `page.on("dialog", lambda dialog: dialog.accept())` za záznam a odmítnutí:
  ```python
  native_dialogs: list[str] = []
  def _on_dialog(dialog: Dialog) -> None:
      native_dialogs.append(f"{dialog.type}: {dialog.message}")
      dialog.dismiss()
  page.on("dialog", _on_dialog)
  try:
      yield page
  finally:
      context.close(); browser.close()
  assert not native_dialogs, f"system dialogs appeared: {native_dialogs}"
  ```
  (`Dialog` importovat z `playwright.sync_api`.) Lépe navíc uložit seznam na stránku/objekt, aby ho `_approve` mohl hned zkontrolovat — např. `page._haifa_native_dialogs` ne; jednodušší: vlastní fixture `native_dialogs` vrácená testu, nebo modulová proměnná. Doporučení: udělat fixture `page` tak, aby po `yield` assertovala (selže teardown → test se hlásí jako ERROR → `just e2e` neprojde) a zároveň v `_approve` po kliknutí ověřit, že modál je vidět (pokud by se otevřel systémový dialog, `dismiss` → nic se nesloučí → test selže na `notice`).
- `_approve`: po `approve.click()`:
  ```python
  modal = page.locator('[data-test="confirm-dialog"]')
  expect(modal).to_be_visible()
  expect(modal).to_contain_text("Schválit a mergovat")
  modal.locator('[data-test="confirm-ok"]').click()
  expect(modal).to_have_count(0)
  ```
  a smazat komentář o `window.confirm`.
- Kontrola nativních tooltipů: po načtení každé obrazovky, kterou test navštíví (backlog, běhy, review), `expect(page.locator("[title]")).to_have_count(0)` (např. v `_nav` nebo jednou v testu na backlogu/detailu běhu/review). SVG `<title>` elementy selektor `[title]` nechytá — ty kryje unit guard.
- Volitelně: na review detailu najet na statistiku/tečku fáze a ověřit `[role="tooltip"]` viditelný; ne povinné.
- Ruff: `just lint` kontroluje i formát — po úpravě spustit `cd aifactory && uv run ruff format tests/e2e/test_f3_browser.py`.

### 9. Build
`just web-build` — přegeneruje `aifactory/src/aifactory/web/static/` (hashované assety; staré soubory zmizí díky `emptyOutDir`). Výsledek nechat v pracovním stromu (necommitovat — to dělá workflow).

### 10. Dokumentace
`app_docs/HAIFA-S01-T01-vlastni-modalni-dialog-a-tooltip-misto-s.md` — krátce: `ConfirmDialog` + `useConfirm` (API, klávesy, fokus), `Tooltip` (obalový a řízený režim, teleport + fixed pozice, z-index proměnné), pravidlo „žádné `title`/`window.confirm`“ a jeho guard test.

## Soubory
Nové: `web/src/components/ui/ConfirmDialog.vue`, `web/src/components/ui/ConfirmDialog.test.ts`, `web/src/components/ui/Tooltip.vue`, `web/src/components/ui/Tooltip.test.ts`, `web/src/lib/confirm.ts`, `web/src/lib/confirm.test.ts`, `web/src/lib/noNativeUi.test.ts`, `web/src/test/modal.ts`, `app_docs/HAIFA-S01-T01-…md`.
Upravené: `web/src/style.css`, `web/src/App.vue`, `web/src/App.test.ts`, `components/review/ReviewActions.vue(+test)`, `components/runs/RunDetail.vue(+test)`, `components/runs/PhaseDots.vue`, `components/runs/StatChip.vue`, `components/backlog/TreeNode.vue`, `components/backlog/TaskDetail.vue`, `components/backlog/DependencyGraph.vue` (+ jejich testy podle bodu 7), `views/ReviewView.test.ts`, `views/RunsView.test.ts`, `tests/e2e/test_f3_browser.py`, `src/aifactory/web/static/**` (build).
(Cesty relativně k `aifactory/`.) Neměnit `vendor/`, `prototype/`, `package.json`, `bun.lock`.

## Ověření
1. `cd aifactory/web && bun run typecheck && bun run test` — vše zelené.
2. `grep -rnE 'window\.(confirm|alert|prompt)' aifactory/web/src` → nic; `grep -rn '<title>' aifactory/web/src` → nic; `grep -rnE '\s:?title="' aifactory/web/src --include=*.vue` → jen `DetailSection`.
3. `just web-build` → `aifactory/src/aifactory/web/static/` aktualizováno; `grep -l "window.confirm" aifactory/src/aifactory/web/static/assets/*.js` → nic.
4. `just test`, `just typecheck`, `just lint`, `just e2e` projdou.
5. Ruční kontrola (volitelně `just dash`): tooltip u statistik v detailu běhu i u uzlů grafu v rolovaném kontejneru se vykreslí celý; tooltip přepínače motivu leží nad lištou; modál Schválit: Esc / klik mimo zruší, Enter potvrdí, Tab neopustí dialog, po zavření fokus na Schválit.

## Rizika / poznámky
- happy-dom: `getBoundingClientRect` vrací nuly — pozicování v unit testech netestovat, jen viditelnost.
- Teleportovaný obsah ve VTU: `wrapper.find` ho nenajde, hledat v `document.body`; vždy `unmount()`, jinak zbydou uzly mezi testy.
- Obal `Tooltip` mění strukturu DOM (přidává `span.tip-anchor`) — zkontrolovat CSS selektory typu `.stats > .stat`, `.dots > .d`, flex `gap` (obal je `inline-flex`, gap rodiče se aplikuje na obaly — v pořádku).
- Fokus z klávesnice na ne-interaktivní prvky (statistika, tečka, odznak, repo chip, externí uzel grafu) vyžaduje `tabindex="0"`.
