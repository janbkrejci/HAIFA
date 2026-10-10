# HAIFA-S02-T03 — Waterfall běhu podle sssf

## Cíl

V detailu běhu (`#/runs/<běh>`) nahradit tabulku fází (`table.phases` v `RunDetail.vue`)
waterfallem (gantt) převzatým z `vendor/sssf/apps/visualizer/src/components/SessionTrace.vue`
(řádky „Lanes“, „Timeline geometry“, šablona `.waterfall`, CSS bloků). Hlavička běhu (task,
StatusChip, Zastavit, `dl.meta`, statistiky, `run-error`) a `PhaseDetail` panel zůstávají.

Pevná omezení: žádná nová závislost (jen `vue`, `lucide-vue-next`), `vendor/` a `prototype/` se
nemění (kód se kopíruje/portuje), testy nevolají model, žádný nativní `title` atribut
(hlídá `lib/noNativeUi.test.ts` i e2e `_no_native_tooltips`) — tooltipy jen přes
`components/ui/Tooltip.vue`.

## Kontext (co existuje)

- `lib/runs.ts`: typy `RunDetail`, `PhaseRow` (`kind`: `'engineer' | 'agent' | 'code'`, `owner`,
  `status`: `success|fail|running|queued`, `harness`, `model`, `description`, `started_at`,
  `ended_at`, `duration_s`), `AgentSession` (`color?`, `context_tokens?`, `context_window?`),
  `TraceEvent` (payload už parsovaný objekt), `AgentStartPayload` (`model`, `color`).
- `lib/events.ts`: `parseAgentStart`, `eventOk(e)` (false při `ok:false`, `passed:false` nebo
  nenulovém `returncode` → pokrývá `quality:*` kódových fází).
- `lib/format.ts`: `fmtDuration(seconds)` (SEKUNDY), `fmtTime`, …; chybí `ts`, `fmtOffset`, `axisTicks`.
- `lib/models.ts`: `modelIcon`, `modelName` (ikony v `public/models/`).
- `lib/router.ts`: `runHref(runId, phaseId?)`.
- `components/runs/StatChip.vue`: `kind='runtime'` bere sekundy; obaluje se `Tooltip` a má
  `tabindex="0"` → uvnitř `<button>` bloku nepoužitelné (vnořený interaktivní prvek a vnořený tooltip).
- `Tooltip.vue`: wrapper mód (span `.tip-anchor` + Teleport — fragment, `class/style` nepropadají)
  a controlled mód (`:anchor="el"`); bublina má `white-space: pre-line` (víceřádkový text OK).
- `views/RunsView.vue`: načítá detail + events, tail přes SSE (`applyTail`) — data se doplňují bez
  reloadu; waterfall jen čte props.
- Fixtury `src/test/runsFixtures.ts`: `detail()` má fáze `p1` (agent, owner `planner`, success,
  10:00–10:03, harness `claude`, model `claude-opus`, description) a `p2` (code `test`, owner
  `tests`, fail, stejné časy!); `events()` a `moreEvents()` (`e5` = `quality:test` s `returncode: 1`
  ve fázi `p2`). `session.started_at` je `null`, `run.started_at` 10:00, `ended_at` 10:05.

## Změny

### 1. `aifactory/web/src/lib/format.ts` (+ `format.test.ts`)

Přidat (port z `vendor/sssf/apps/visualizer/src/lib/format.ts`):

```ts
/** Epoch ms, NaN pro chybějící/neplatné. */
export function ts(iso: string | null | undefined): number
/** Offset na ose: 45s, 2m, 2m05s, 1h, 1h05m. */
export function fmtOffset(ms: number): string
/** Ticky osy po kroku z [1,2,5,10,15,30,60,120,300,600,1200,1800,3600] s, ≤ maxTicks. */
export function axisTicks(spanMs: number, maxTicks = 8): { pct: number; label: string }[]
```

Testy: `ts(null)` je NaN, `fmtOffset(125000) === '2m05s'`, `axisTicks(60_000, 7)` začíná `{pct:0,label:'0s'}`,
počet ≤ 7, poslední pct ≤ 100.

### 2. `aifactory/web/src/lib/events.ts` (+ `events.test.ts`)

Přidat:

```ts
export const AGENT_FALLBACK_COLORS = ['#c89bff', '#5ad2dd', '#94a3ff', '#e8b64a', '#f2a2c4']
/** Barva z konfigurace, pak z agent_start, pak z palety podle indexu dráhy.
 *  Prázdný/whitespace řetězec (i null/undefined) se bere jako „nenastaveno“. */
export function agentColor(config: string | null | undefined, payload: string | null | undefined, index: number): string
/** "#rrggbb" + alfa → rgba(); neplatné → 'transparent'. */
export function hexAlpha(hex: string, alpha: number): string
```

Pozor: vendor používá `??`, což prázdný řetězec nepropustí do palety — tady
`const pick = (c) => (typeof c === 'string' && c.trim() ? c.trim() : null)`.
Testy: `agentColor('', null, 1) === AGENT_FALLBACK_COLORS[1]`, `agentColor('  ', '', 6)` = paleta[1],
`agentColor('#123456', '#abcdef', 0) === '#123456'`, `agentColor(null, '#abcdef', 0) === '#abcdef'`,
`hexAlpha('#ff0000', 0.5) === 'rgba(255, 0, 0, 0.5)'`, `hexAlpha('red', 1) === 'transparent'`.

### 3. Nový `aifactory/web/src/lib/waterfall.ts` (+ `waterfall.test.ts`) — čisté rozložení

Veškerá geometrie mimo komponentu, aby šla testovat bez DOM. Do `lib/runs.ts` přidat jen
`export type PhaseKind = 'engineer' | 'agent' | 'code'` (`PhaseRow.kind` zůstává `string | null`).

```ts
export const REQ_ZONE_PCT = 16
export const MIN_BLOCK_PCT = 3.5
export const RIGHT_MARGIN_PCT = 0.4
export const ENGINEER_COLOR = '#e8b64a'
export const CODE_COLOR = '#5ad2dd'

export interface LaneContext { used: number; window: number; pct: number }
export interface Lane {
  id: string            // 'engineer' | 'code' | `agent:${owner}`
  kind: PhaseKind
  label: string         // engineer: session.engineer ?? 'engineer'; kód: 'kód'; agent: owner
  model: string | null  // agent: agents[].model ?? agent_start.model ?? null
  context: LaneContext | null
  meta: string | null   // engineer: 'požadavek'; kód: 'workspace'; agent: null
  color: string
  phases: PhaseRow[]    // seřazené bySeq
}
export interface BlockGeom { left: number; width: number } // v % šířky dráhy

export function sortPhases(phases: PhaseRow[]): PhaseRow[]   // seq, pak rowid (jako bySeq v runs.ts — případně bySeq exportovat a použít)
export function laneContext(info?: AgentSession): LaneContext | null // null, když used nebo window chybí/0; pct = min(100, used/window*100)
export function contextLabel(ctx: LaneContext): string        // <1 % → '0.4%', jinak zaokrouhleno '37%'
export function contextFill(ctx: LaneContext): string         // `${max(pct,2)}%`
export function ownerStarts(phases: PhaseRow[], events: TraceEvent[]): Record<string, AgentStartPayload>
  // první agent_start na vlastníka (owner fáze dle phase_id, jinak e.name)
export function buildLanes(detail: RunDetail, events: TraceEvent[]): Lane[]
  // engineer vždy; 'code' jen pokud existuje kódová fáze (všechny kind==='code' v jedné dráze);
  // pak jedna dráha na owner agentních fází v pořadí prvního výskytu (podle seq);
  // barva agenta = agentColor(info?.color, start?.color, indexMeziAgenty)
export interface Timeline {
  t0: number; t1: number
  zonePct: number                 // REQ_ZONE_PCT, je-li request fáze, jinak 0
  requestId: string | null        // první engineer fáze se started_at
  origin: number; postSpan: number
  ticks: { pct: number; label: string }[] // axisTicks(postSpan, 7) přemapované do [zone,100]
  blocks: Record<string, BlockGeom>       // request → {left:0.4, width:zone-0.8}
}
export function buildTimeline(detail: RunDetail, now: number): Timeline
export function phaseEndMs(p: PhaseRow, now: number): number // running → now; jinak ended_at; jinak start
export function blockDurationMs(p: PhaseRow, now: number): number // NaN bez startu; running → now-start
export function toolTicks(p: PhaseRow, events: TraceEvent[], now: number): { x: number; ok: boolean }[]
  // tool_call události s phase_id === p.phase_id; ok = eventOk(e) (quality:* → returncode/passed);
  // x = clamp(((ts(e.started_at)-start)/max(end-start,1))*100, 1, 99); události bez času vynechat
```

`buildTimeline` — port `range`/`originMs`/`postSpan`/`blockLayout`/`blockGeom` ze SessionTrace:
- rozsah: `session.started_at/ended_at` a `run.started_at/ended_at` (fixtury mají session časy null),
  starty/konce fází; běží-li běh (`run.state === 'running'`) nebo nějaká fáze `running`, `t1 = max(t1, now)`;
  bez časů `t0 = now, t1 = now + 1000`; min. rozpětí 1000 ms.
- `origin` = nejdřívější start ne-engineer fáze (≥ t0), jinak konec request fáze, jinak t0.
- bloky: fáze se startem kromě request fáze, seřazené podle startu (shodný start → seq);
  `avail = 100 - zone - 0.4`; `left=(start-origin)/postSpan*avail`, `width=(end-start)/postSpan*avail`;
  průchod s kumulativním posunem: `left < prevEdge → posun`, `width = max(width, MIN_BLOCK_PCT)`,
  posun += rozšíření; nakonec škálovat `avail / max(prevEdge, avail)` a přičíst `zone`.
  Invariant: bloky (napříč všemi drahami) se nepřekrývají, `left ≥ zone`, `left+width ≤ 100`,
  šířka ≥ `MIN_BLOCK_PCT * scale` (při normálním počtu fází přesně ≥ MIN_BLOCK_PCT).
- fáze bez `started_at` nemají geometrii (vykreslí se jako čárkované „ve frontě“).

`waterfall.test.ts` (vitest, vlastní malé buildery fází — ne závislé na `detail()` časech):
1. pořadí drah: engineer, kód, agenti v pořadí prvního výskytu (`builder` seq 2 před `planner` seq 3 → `['engineer','code','agent:builder','agent:planner']`); bez kódové fáze není dráha `code`.
2. agent ve dvou fázích (planner seq 2 i seq 5) → jedna dráha `agent:planner` se 2 fázemi.
3. všechny kódové fáze (`git`, `quality:test`) v jedné dráze `code`.
4. bloky se nepřekrývají: 5 fází, některé s nulovou délkou a se shodným startem → po seřazení dle left `left[i+1] >= left[i] + width[i] - 1e-9`; vše v `[zone, 100]`.
5. minimální šířka: fáze 0 ms mezi dvěma dlouhými má `width >= MIN_BLOCK_PCT - 1e-9`.
6. request fáze leží v zóně `{left:0.4,width:15.2}`, ostatní `left >= 16`.
7. záložní barva: `agents: [{agent:'planner', color: ''}]` → barva = `AGENT_FALLBACK_COLORS[0]`; `color:'#112233'` vyhraje; barva z `agent_start` payloadu, když agents nemá.
8. `laneContext` null bez window; `contextLabel` `0.5%` / `37%`.
9. running fáze: `blockDurationMs(p, now)` roste s `now`; `buildTimeline` s `now` později → šířka running bloku roste.
10. `toolTicks`: `quality:test` s `returncode:1` → `ok:false`; `Read` s `ok:true` → `ok:true`.

### 4. `aifactory/web/src/lib/clock.ts` (nový, malý) — tik každou sekundu

```ts
/** Reaktivní „teď“: tiká po 1 s, jen když active() je true; po unmountu se zastaví. */
export function useNow(active: () => boolean, intervalMs = 1000): Ref<number>
```
`ref(Date.now())`, `watch(active, on => start/stop setInterval, { immediate: true })`
(při startu hned `now.value = Date.now()`), `onScopeDispose(stop)`. Žádné fetchování — jen čas.

### 5. `aifactory/web/src/components/runs/StatChip.vue`

Přidat prop `plain?: boolean`: renderuje stejnou pilulku **bez** `Tooltip` obalu a bez `tabindex`
(pro použití uvnitř tlačítka bloku). Přidat `kind` jednotky beze změny (runtime = sekundy; blok
předá `ms / 1000`). Šablona: `<Tooltip v-if="!plain" …><span …/></Tooltip><span v-else class="stat" :class="{compact}" :data-stat="kind">…</span>`
(obsah pilulky nejlépe sdílet, např. přes `<template>` nebo malou duplikaci).

### 6. Nový `aifactory/web/src/components/runs/RunWaterfall.vue` (+ `RunWaterfall.test.ts`)

Props: `detail: RunDetail`, `events: TraceEvent[]`, `phaseId?: string | null`, `now: number`.
Computed: `lanes = buildLanes(...)`, `timeline = buildTimeline(detail, now)`.

Šablona (port `.waterfall` ze SessionTrace, texty česky):
- `div.waterfall[data-test="waterfall"]` → `div.row.axis-row` (`.label` prázdný, `.track` s
  `span.zone-head` „požadavek“ šířky `zonePct%` a `span.axis-label` pro každý tick).
- pro každou dráhu `div.row.lane[data-lane=lane.id][:class="`kind-${lane.kind}`"]`:
  - `.label`: `span.lane-name` (ikona `UserRound`/`SquareTerminal`/`Bot`, barva dráhy, text label);
    `lane.model` → `span.lane-model[data-test="lane-model"]` s `<img class="model-icon" :src="modelIcon(model)" alt="">`
    (jen když ikona existuje) a `modelName(model)`, obaleno `<Tooltip :text="lane.model">`;
    `lane.context` → `span.lane-ctx[data-test="lane-ctx"]` (label „Kontext“, procento, bar s výplní
    v barvě dráhy), obaleno `<Tooltip>` s textem `„{used} / {window} tokenů · zbývá {window-used}“`
    (`fmtInt`); `lane.meta` → `span.lane-meta`.
  - `.track`: `span.zone-divider` (je-li zóna), `span.gridline` pro ticky; pro fáze dráhy s geometrií
    `button.block[data-phase=phase_id][data-name=name]` s třídami `[status, { selected: phase_id === phaseId, failed: isFail(status) }]`,
    styl jako `blockStyle` ve vendoru (gradient `hexAlpha(color, .2/.05)`, `borderColor` červený
    `rgba(255,111,103,.8)` pro `fail|failed`, jinak `hexAlpha(color,.55)`, `--lane-glow`).
    Obsah: `span.b-top` (`span.b-status` s glyfem `Check|X|LoaderCircle|Circle`, `span.b-name`,
    `StatChip plain compact kind="runtime" class="b-dur" :value="durMs/1000"` když konečné),
    `span.b-desc` (description), `span.tool-tick` pro `toolTicks` (`:class="{ err: !t.ok }"`, `left: x%`).
  - fáze dráhy bez `started_at`: `button.block.queued[data-phase]` (čárkovaný okraj, `right: 10+i*5 px`,
    `width: 170px`), popis „ve frontě“.
- prázdný stav: bez fází `p.faint` „Žádné fáze v trace.“ (zachovat text).
- Tooltip bloku: **jeden** `<Tooltip :text="tip.text" :anchor="tip.el" />` v controlled módu;
  blok má `@mouseenter/@focus` → `tip = { el: $event.currentTarget, text: blockTip(p) }`,
  `@mouseleave/@blur` → `tip = { el: null, text: '' }`. `blockTip(p)`:
  ```
  {name} — {statusLabel}
  {description}            (jen když je)
  Harness: {harness ?? '—'} · Model: {model ?? '—'}
  Pokus: {attempt ?? '—'} · Doba: {fmtDuration(dur/1000)}
  ```
  (statusLabel česky: úspěch/chyba/běží/čeká — malá mapa nebo export z StatusChip; žádný `title`.)
- klik: `select(p)` → `window.location.hash = runHref(run_id, p.phase_id === phaseId ? null : p.phase_id)`.
  `RunsView` už čte fázi z routy, takže panel se otevře/zavře sám.
- CSS: převzít `.waterfall`, `.row` (grid `240px 1fr`), `.axis-row`, `.zone-head`, `.axis-label`,
  `.label`, `.lane-*`, `.ctx-*`, `.track` (výška ~118 px), `.gridline`, `.zone-divider`, `.block`,
  `.b-*`, `.block.running` (pulse — ověřit, že `@keyframes pulse` existuje v `style.css`, jinak
  definovat lokálně), `.block.queued` (`border-style: dashed`), `.block.selected`, `.tool-tick`,
  `.tool-tick.err` (`background: var(--red)`). Použít CSS proměnné, které už `style.css` má
  (`--border-soft`, `--panel-2`, `--surface`/`--panel`, `--dim`, `--faint`, `--red`, `--green`,
  `--blue`, `--amber`, `--mono`) — co chybí, nahradit existující.

`RunWaterfall.test.ts` (fixtury z `runsFixtures` + lokální úpravy):
1. dráhy: `detail()` → `[data-lane]` = `['engineer','code','agent:planner']`; dráha planneru ukazuje
   model (`detail().agents = [{agent:'planner', model:'claude-opus-4', color:'', context_tokens: 50000, context_window: 200000, …}]`)
   s `img.model-icon`, `[data-test="lane-ctx"]` obsahuje `25%`; při `color: ''` je barva názvu dráhy
   z palety (`AGENT_FALLBACK_COLORS[0]`, porovnat přes `style` — happy-dom vrací `rgb(...)` nebo hex,
   proto porovnávat s `hexAlpha`/převodem, případně `data-color` atribut na `.lane-name`).
2. bloky: `button.block[data-phase="p1"]` i `p2` existují, obsahují název a `.b-desc`; `p2` má třídu
   `fail`/`failed`; fáze bez `started_at` → `.block.queued`.
3. chybná značka: `events: [...events(), ...moreEvents()]` → v bloku `p2` je `.tool-tick.err`, v bloku `p1` `.tool-tick` bez `err`.
4. klik vybírá a ruší: `phaseId: null`, klik na `p1` → `window.location.hash === '#/runs/r-ok/p1'`;
   `setProps({ phaseId: 'p1' })` → `.block.selected[data-phase="p1"]`; druhý klik → `'#/runs/r-ok'`.
   (Na konci `window.location.hash = ''`.)
5. tooltip: `trigger('mouseenter')` na `p1` (s `attachTo: document.body`) → `[data-test="tooltip"]`
   obsahuje `Harness: claude` a `Model: claude-opus`; žádný prvek s `[title]`.
6. růst: fáze `running` (start 10:00:00, `ended_at: null`), `now` = 10:00:10 → `.b-dur` „10.0s“;
   `setProps({ now: +20 s })` → „30.0s“ a šířka bloku se zvětší.

### 7. `aifactory/web/src/components/runs/RunDetail.vue` (+ `RunDetail.test.ts`)

- Odstranit tabulku `table.phases` a její CSS (`.table`, `th/td`, `.num`, `tr.selected`).
- `const live = computed(() => run.value.state === 'running' || phases.value.some(p => p.status === 'running'))`,
  `const now = useNow(() => live.value)`.
- Pod hlavičku: `<h3>Fáze</h3>` + `<RunWaterfall :detail :events :phase-id="phaseId" :now="now" />`.
- Hint `[data-test="phase-hint"]` „Vyber fázi pro detail.“ zůstává (když jsou fáze a není výběr).
- Statistika `runtime` v hlavičce: když `run.state === 'running'` a `duration_s` je null/zastaralé,
  ukazovat `(now - ts(run.started_at)) / 1000`, jinak `run.duration_s`.
- `PhaseDetail`, `onClose`, Stop + ConfirmDialog beze změny.
- Testy upravit: test „lists phases in seq order…“ přepsat na waterfall (`.block[data-phase]`
  obsahuje `p1`,`p2`; harness/model ověřit v tooltipu bloku nebo nechat na RunWaterfall testu);
  „shows the selected phase detail“: `.block.selected[data-phase="p2"]` místo `tr.selected`;
  „no phase panel“: `.block.selected` neexistuje. Ostatní testy (Stop, tooltip statistik,
  `[title]` neexistuje, task label, request a close) ponechat.
- Nový test „růst s falešnými časovači“: `vi.useFakeTimers(); vi.setSystemTime('2026-01-01T10:00:10Z')`,
  detail `state:'running'` s fází `p1` `status:'running'`, `ended_at:null`, `started_at 10:00:00`;
  mount → `.block[data-phase="p1"] .b-dur` „10.0s“; `vi.advanceTimersByTime(3000); await nextTick()`
  → „13.0s“; ověřit, že `fetch` nebyl volán (`vi.stubGlobal('fetch', vi.fn())`). Po testu
  `vi.useRealTimers()`. Ověřit také, že po unmountu interval neběží (`vi.getTimerCount() === 0`).

### 8. `aifactory/web/src/views/RunsView.vue`

Funkčně beze změny (data i tail už přicházejí). Jen pokud je waterfall v `max-width: 1400px`
příliš úzký, ponechat — žádná změna není nutná. `RunsView.test.ts` nepoužívá `table.phases`;
spustit a ověřit, že projde.

### 9. `aifactory/tests/e2e/test_f3_browser.py` — `_check_run_detail`

Nahradit `page.locator("table.phases").get_by_role("link", name="plan", exact=True).click()`:

```python
waterfall = page.locator('[data-test="waterfall"]')
expect(waterfall).to_be_visible()
expect(waterfall.locator('[data-lane="engineer"]')).to_have_count(1)
expect(waterfall.locator('[data-lane="agent:planner"]')).to_have_count(1)
expect(waterfall.locator("button.block").first).to_be_visible()
block = waterfall.locator('button.block[data-name="plan"]')
block.click()
expect(panel).to_be_visible()
expect(block).to_have_class(re.compile(r"\bselected\b"))
expect(page).to_have_url(re.compile(rf"#/runs/{re.escape(run_id)}/[^/]+$"))
```
Zbytek (sekce, prompty, `_no_native_tooltips`, zavření) beze změny. Volitelně na konci: znovu
klik na blok → panel otevřen, druhý klik → `panel` count 0. Agent v e2e je `planner`
(fixture `f3_repo.py`, workflow `plan-commit`); ověř `owner` fáze plan v trace, pokud by se lišil.

### 10. Build frontendu

`just web-build` (= `cd aifactory/web && bun install --frozen-lockfile && bun run build`) přegeneruje
`aifactory/src/aifactory/web/static/` (nové hashované `assets/index-*.js|css`, staré smazané buildem).
Commitovat výsledek buildu. Spustit až po všech změnách frontendu.

### 11. Dokumentace

`app_docs/HAIFA-S02-T03-waterfall-behu-podle-sssf.md` píše dokumentační fáze — builder ji nemusí
tvořit (allowed path, pokud ano: krátce popsat dráhy, rozložení, URL a živý tik).

## Ověření

1. `cd aifactory/web && bun run typecheck && bun run test` (vitest: nové `waterfall.test.ts`,
   `RunWaterfall.test.ts`, upravené `RunDetail.test.ts`, `events.test.ts`, `format.test.ts`,
   `noNativeUi.test.ts` — žádný `title=` v šablonách).
2. `just web-build` → `git status aifactory/src/aifactory/web/static` ukazuje nový build.
3. `just test`, `just typecheck`, `just lint`, `just e2e` (Playwright, system Chrome; testy nevolají
   model — e2e používá existující fake harness fixtury).
4. Ručně (volitelně): `just dash`, otevřít běh: dráhy engineer/kód/agent, zóna „požadavek“, klik
   na blok mění `#/runs/<běh>/<fáze>`, druhý klik vrací `#/runs/<běh>`.

## Mimo rozsah

Seznam běhů ve stylu karet sssf, archiv běhů, změny backendu (`aifactory/web/runs.py`).
