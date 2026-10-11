# HAIFA-S02-T02: Panel fáze běhu podle sssf

## Cíl

Nahradit dnešní zjednodušený `PhaseDetail.vue` v detailu běhu plným portem panelu fáze z
visualizeru sssf (`vendor/sssf/apps/visualizer/src/components/PhaseDetail.vue`, ~1280 řádků).
Panel má hlavičku, dvousloupcovou mřížku (vlevo sbalitelné sekce, vpravo vždy viditelné
Události), české popisky a vzhled visualizeru. Panel se ukáže až po výběru fáze, jde zavřít
a všechny sekce začínají sbalené (i po změně fáze; živé aktualizace stav nemění).

Backend je hotový (HAIFA-S02-T01): `GET /api/runs/{run_id}/phases/{phase_id}/prompts`
vrací v envelope `data` = `{run_id, phase_id, phase, agent, kind, source: "phase"|"agent"|"none",
legacy: bool, system: string|null, user: string|null, truncated: {system: bool, user: bool},
max_bytes: number}` (viz `aifactory/src/aifactory/web/runs.py::phase_prompts`). Python se
v tomto úkolu nemění, kromě e2e testu.

## Pevná omezení

- Panel nemá vlastní polling. Data dostává z props (dnešní `fetchRun` + `fetchAllEvents` v
  `RunsView.vue` a živé `applyTail`). Jediný vlastní request je jednorázové načtení promptů
  při výběru fáze (žádný interval/opakování).
- Žádná nová závislost frontendu (`package.json`/`bun.lock` beze změny). Ikony `lucide-vue-next`
  už jsou k dispozici.
- `vendor/` a `prototype/` se nemění (jen se z nich čte / kopírují PNG).
- Testy nevolají model.
- **Žádný nativní `title` atribut** v šablonách (`src/lib/noNativeUi.test.ts` to hlídá; e2e
  `_no_native_tooltips` kontroluje `[title]` count 0). Kde vendor používá `:title`, buď ho
  vynech, nebo použij `components/ui/Tooltip.vue` (jako `StatChip`). `title` je povolen jen
  jako prop `<DetailSection`.
- Měnit jen v `aifactory/`, `justfile`, spec a doc soubor úkolu. `THIRD_PARTY_NOTICES` se
  neměni (už pokrývá `aifactory/web/` i `static/`).

## Soubory a změny

### 1. Ikony modelů — `aifactory/web/public/models/`

Zkopírovat (`cp`) `vendor/sssf/apps/visualizer/public/models/{claude,gemini,kimi,openai,zai}.png`
do `aifactory/web/public/models/`. Vite je při buildu přenese do `static/models/`, StaticFiles
je servíruje na `/models/*.png`.

### 2. `aifactory/web/src/lib/models.ts` (nový) + `models.test.ts`

Port `vendor/.../lib/models.ts` 1:1 (`MODEL_ICONS`, `modelIcon(model)`, `modelName(model)`),
hlavičkový komentář `// Port of the sssf visualizer's lib/models.ts.`
Test: `claude-opus` → `/models/claude.png`, `gpt-5` → openai, `openrouter/z-ai/glm-4.6` →
zai a `modelName` → `glm-4.6`, neznámý model → `null`, `null` → `null` / `''`.

### 3. `aifactory/web/src/lib/format.ts` (+ `format.test.ts`)

Přidat:
- `fmtClock(iso)` – jen čas: `new Date(t).toLocaleTimeString('cs-CZ', { hour12: false })`,
  `—` pro chybějící/nevalidní.
- `fmtMoney4(n)` – `$${(n ?? 0).toFixed(4)}` (náklady po složkách na 4 desetinná místa;
  `0` → `$0.0000`).
- `fmtInt(n)` – `new Intl.NumberFormat('cs-CZ').format(n ?? 0)` (pozor: oddělovač tisíců je
  nedělitelná mezera ` `; v testech normalizovat nebo použít čísla < 1000).
- `plural(n, one, few, many)` – česká plurála (1 → one, 2–4 → few, jinak many); použije se
  pro „1 řádek / 3 řádky / 12 řádků“.
- `secondsBetween(startIso, endIso)` – rozdíl v sekundách nebo `null` (pro dobu události a
  běžící fázi).

Testy pro každou novou funkci.

### 4. `aifactory/web/src/lib/highlight.ts`

Přidat `highlightValue(value: unknown): string` – `null/undefined` → `''`; string →
`highlightJson(value)` (string může být JSON); jinak `highlightJsonText(JSON.stringify(value, null, 2))`.
Payloady v HAIFA přicházejí už naparsované (`TraceEvent.payload: unknown`,
`TraceEnvelope.payload`), proto tento helper místo vendorového `highlightJson(payload_json)`.

### 5. `aifactory/web/src/lib/events.ts` (+ `events.test.ts`)

- `parseAgentStart(e): AgentStartPayload | null` – payload jako record, jinak null.
- `parseAgentEnd(e): AgentEndPayload | null` – totéž pro `agent_end`.
- `parseQualityCall(e): QualityPayload | null` – pro `type === 'tool_call'` bez `tool` v payloadu
  a s `typeof payload.command === 'string'` (událost `quality:<name>` z
  `aifactory/src/aifactory/engine/quality.py`: payload `{area, operation, command, returncode,
  passed, timeout_seconds, output_artifact}`).
- `eventOk(e): boolean` – `false` když payload má `ok === false` nebo `passed === false`
  (nebo `returncode` je číslo ≠ 0); jinak `true`.
- `EVENT_TYPE_CLASS: Record<string,string>` – z vendoru `typeClass`
  (`gate_fail`/`error` → `t-red`, `gate_pass`/`agent_end` → `t-green`, `tool_call` → `t-cyan`,
  `handoff` → `t-violet`, `agent_start` → `t-purple`).
- `eventLabel`: doplnit vendorovou legacy větev (`pi_event`) není nutné; zachovat dnešní chování.

Testy: `parseQualityCall` na quality události, `eventOk` pro `ok:false`, `passed:false`,
`returncode: 2`, a obyčejný tool call.

### 6. `aifactory/web/src/lib/runs.ts` (+ `runs.test.ts`)

- Rozšířit `AgentStartPayload` o `color?`, `purpose?: string`, `tools?: string[] | null`,
  `harness_engineering?: string[]`.
- Přidat `AgentEndPayload { cost?: number; usage?: Partial<UsageBreakdown>; context_tokens?; context_window? }`.
- Přidat `QualityPayload { command: string; returncode?: number | null; passed?: boolean; area?; operation?; timeout_seconds?; output_artifact? }`.
- Přidat `PhasePrompts` (tvar výše) a
  `fetchPhasePrompts(runId, phaseId): Promise<PhasePrompts>` →
  `getApi('/runs/${enc(runId)}/phases/${enc(phaseId)}/prompts')`.
- Test: `fetchPhasePrompts` volá správnou URL (vzor ostatních testů v `runs.test.ts` s mockem
  `fetch`).

### 7. `components/runs/DetailSection.vue`

Ponechat API, doplnit:
- volitelný prop `id?: string` → `data-section="<id>"` na `<section>`;
- `:aria-expanded="open"` a `data-test="dsec-toggle"` na tlačítku hlavičky.
Vzhled srovnat s `vendor/.../components/DetailSection.vue` (pokud se liší).

### 8. `components/runs/StatChip.vue`

Přidat prop `compact?: boolean` (třída `.compact`: menší padding `1px 8px`, font 14px, ikona 15)
jako ve vendorovém `StatChip` – použije se u řádků událostí a v detailu tool callu. Jednotky
zůstávají: `runtime` v sekundách.

### 9. `components/runs/PhaseDetail.vue` — přepsat jako port vendoru

Props:
```ts
{
  runId: string
  phase: PhaseRow
  request: string | null        // zadání běhu (detail.session?.request)
  gates: GateResult[]           // už vyfiltrované na fázi (RunDetail), seřadit uvnitř
  envelopes: TraceEnvelope[]
  events: TraceEvent[]
}
emits: { close: [] }
```
Kořen: `<section class="detail phase-detail" :data-phase="phase.phase_id">`.

Řazení uvnitř (jako vendor): events podle `rowid`, gates podle `(attempt, id)`, envelopes podle
`attempt`.

**Hlavička** (`.d-head`, styl vendoru):
- `.d-name` = `phase.name`, `<StatusChip :status="phase.status ?? 'queued'">`,
  `<StatChip kind="runtime">` s dobou fáze: `phase.duration_s`, u běžící fáze
  `secondsBetween(started_at, now)` (computed; bez vlastního timeru – aktualizuje se s živými daty);
  skrýt, když doba není konečná.
- `.d-tags`: štítky `agent` = `phase.owner ?? '—'`, `druh` = `phase.kind ?? '—'`,
  `pokus` = `${attempt ?? 0}/${retries ?? 0}` (data-test `tag-agent`, `tag-kind`, `tag-attempt`).
- Zavírací tlačítko `.close` s ikonou `X`, `aria-label="Zavřít"`, `data-test="phase-close"`,
  emit `close`. Bez `title`.
- Pod hlavičkou `phase.error` v `.error-bar.d-error` (`data-test="phase-error"`).

**Mřížka** `.d-grid` (2fr / 3fr, pod 1100px jeden sloupec).

**Levý sloupec** – sekce přes `DetailSection` s `id`, všechny řízené `openSections: Set<string>`:

| id | title | ikona | zobrazit když | obsah |
|---|---|---|---|---|
| `request` | Požadavek | `Inbox` | `request?.trim()` | `<MarkdownView :source="request" />` (má záložky Náhled/Zdroj) |
| `config` | Konfigurace agenta | `SlidersHorizontal` | `agentConfig` | viz níže |
| `description` | Popis | `AlignLeft` | `phase.description` | `<p class="d-desc">` |
| `prompts` | Sestavené prompty | `MessagesSquare` | `phase.kind === 'agent'` | viz níže; count = počet promptů až po načtení |
| `gates` | Gates | `ShieldCheck` | vždy | viz níže; count = počet gates |
| `cost` | Náklady | `Receipt` | `phase.kind === 'agent'` a existují data | viz níže |
| `outputs` | Výstupy | `Package` | vždy | viz níže; count = počet envelopes |

Prázdné stavy česky: „Žádné gates.“, „Žádné výstupy.“, „Žádné události.“.

*Konfigurace agenta* (`agentConfig` computed): jen pro `kind === 'agent'`; z prvního
`agent_start` eventu fáze (`parseAgentStart`); když chybí, fallback
`{ coding_agent: phase.harness, model: phase.model }` (jen pokud aspoň jedno není null).
Řádky `.cfg-row` s `.cfg-k` popisky: `coding agent` (ikona `SquareTerminal`), `model`
(`<img class="cfg-model-icon" :src="modelIcon(model)" alt="">` + `modelName(model)`; plné ID
modelu přes `Tooltip`, ne `title`), `thinking` (`Brain`), `tools` (`null` → „všechny nástroje“,
jinak chips), `harness engineering` (prázdné → „žádné“, jinak chips), `purpose`, `session`
(`Fingerprint`, `session_id`). Řádek se vykreslí jen když hodnota existuje (u tools/harness
když klíč není `undefined`). `data-test="cfg-<klíč>"` na řádcích.

*Sestavené prompty*: stav `promptsState: 'idle'|'loading'|'ready'|'error'`, `prompts`,
cache `Map<string, PhasePrompts>` s klíčem `${runId}:${phase_id}`. `watch(() => [runId,
phase.phase_id, phase.kind], …, { immediate: true })` – reaguj jen při změně klíče (tail
nahrazuje objekt fáze!), pro `kind !== 'agent'` stav `idle`; jinak z cache nebo
`fetchPhasePrompts` s ochranou proti závodu (výsledek zahodit, pokud se klíč mezitím změnil).
Chyba se necachuje (při dalším výběru fáze se zkusí znovu). Žádné opakování/polling.
Obsah:
- loading: „Načítám prompty…“, error: „Prompty se nepodařilo načíst.“;
- `prompts.legacy` (nebo `source === 'agent'`): poznámka `data-test="prompts-legacy"`
  „Běh nemá prompty jednotlivých fází – zobrazuji poslední prompty agenta.“;
- žádný prompt: „Žádné sestavené prompty.“;
- panel na každý nenulový prompt (`system` → „system prompt“, `user` → „user prompt“),
  `data-test="prompt-panel"` + `data-prompt="system|user"`: tlačítko `.prompt-head`
  (`data-test="prompt-toggle"`, `aria-expanded`) s chevronem, názvem a počtem řádků
  (`${n} ${plural(n,'řádek','řádky','řádků')}`); po rozbalení `.prompt-body` s
  `<MarkdownView :source="text" />` (Náhled/Zdroj; Náhled výchozí); `truncated[id]` →
  poznámka „Zkráceno na {max_bytes} B.“. Rozbalení řízeno `openPrompts: Set<string>`.

*Gates*: pro každý gate `.gate.pass|.fail` (`data-test="gate"`, `data-gate-id`). Řádek je
tlačítko `.gate-line.gate-toggle` (`data-test="gate-toggle"`, `aria-expanded`) – rozbalitelné
vždy (i když `checks` je null, aby šly vidět porušení), obsah:
chevron, ikona `Check`/`X`, `.gate-name`, výsledek `prošel`/`neprošel` (`.gate-verdict`),
štítek `kontroly` = `checksLabel(checks)` (jen když `checks` není null; „`k z N selhalo`“
při selháních, jinak `N`; štítek `.tag-fail` když gate neprošel), štítek `pokus` =
`attempt ?? 0`, `.gate-time` = `fmtClock(created_at)`.
Rozbalené (`openGates: Set<number>`) `.gate-checks`:
- `checks === []` → „Nic ke kontrole – gate neprověřil žádnou položku.“;
- každá kontrola `.gate-check.pass|.fail` (`data-test="gate-check"`): značka, `.check-item`,
  poznámka – jednořádková inline `.check-note`, víceřádková (`includes('\n')`) jako
  `<pre class="check-note-block">`;
- `violations` jako `<ul class="violations">` (`data-test="violations"`).
`checksLabel` vytáhnout jako exportovanou funkci (např. do `lib/runs.ts` nebo `lib/events.ts`)
a otestovat.

*Náklady* (`phaseUsage` computed, jen `kind === 'agent'`): zdroj usage =
`phase.usage` (když má aspoň jednu číselnou složku), jinak `parseAgentEnd(agent_end).usage`.
Řádky: `vstup`, `výstup`, `thinking` (jen když `reasoning_tokens` > 0; `kind: 'nested'`,
odsazený pod výstupem, cena = `output_cost * reasoning / output_tokens`, poznámka přes
Tooltip/řádek, že je součástí výstupu a nepřičítá se), `cache čtení`, `cache zápis`,
`celkem` (`kind: 'total'`; `total_tokens`/`total_cost`, když chybí, součet
vstup+výstup+cache, resp. `phase.tokens`/`phase.cost`). Chybějící složky = 0. Bez breakdownu
(žádné usage, ale `phase.tokens || phase.cost` nebo `agent_end`) → jen řádek `celkem` a
poznámka „Běh nemá rozpis po složkách – zaznamenán jen součet.“. Bez dat sekci nezobrazit.
Tabulka `.usage` s hlavičkou `tokeny` / `cena`, tokeny `fmtInt`, ceny `fmtMoney4`,
řádky `data-row="vstup|výstup|thinking|cache-cteni|cache-zapis|celkem"`.

*Výstupy*: každý envelope `.output` (`data-test="envelope"`): `.output-type`, štítky `agent`,
`pokus`, `.output-valid.pass|.fail` „platný“/„neplatný“; pod tím
`<pre v-html="highlightValue(e.payload ?? e.payload_raw)">` (bezpečné – highlight escapuje).

**Pravý sloupec Události** – žádná DetailSection, vždy vidět:
`<h3><Activity/> Události ({{ n }})</h3>`, prázdné „Žádné události.“. Každá událost
`<div class="event" :data-event="event_id" :data-type="type">` (atributy zachovat – používá je
`RunsView.test.ts`), řádek je tlačítko `.event-row` (`data-test="event-toggle"`,
`aria-expanded`, `.open`) se sloupci: `.e-time` `fmtClock(started_at)`, `.e-type` s
`EVENT_TYPE_CLASS[type]`, `.e-name` `eventLabel(e)` (`t-red` když `!eventOk(e)`, plný text bez
`title`), `.e-extra` s `StatChip compact kind="runtime"` (doba: `secondsBetween(started, ended)`,
u tool callu bez `ended_at` `duration_ms/1000`) a `StatChip compact kind="tokens"` když
`e.tokens`. Rozbalení (`expanded: Set<string>`) `.payload-panel` (`data-test="event-body"`):
1. `parseToolCall(e)` → `.p-meta`: `.p-tool` název nástroje, „chyba“ (`t-red`) při
   `ok === false`, doba; `<h4>argumenty</h4><pre class="p-pre" v-html="highlightValue(args ?? {})">`;
   `result_snippet` → `<h4>výsledek</h4><pre class="p-pre">` (text, ne v-html).
2. `parseQualityCall(e)` → `.p-meta` (`data-test="quality-meta"`): `příkaz` `<code>{{ command }}</code>`,
   `návratový kód` `{{ returncode ?? '—' }}` (`t-red` když ≠ 0), `prošel/neprošel`; pak
   `<h4>payload</h4>` se zvýrazněným celým payloadem.
3. jinak payload (ne null) → `<h4>payload</h4><pre class="p-pre" v-html="highlightValue(payload)">`;
4. jinak „Bez payloadu.“

**Reset stavu**: `watch(() => props.phase.phase_id, () => { openSections.clear();
openGates.clear(); openPrompts.clear(); expanded.clear() })`. Žádný jiný watch na objekt fáze
ani na pole gates/events/envelopes nesmí stav měnit (tail vytváří nové objekty/pole).
Zavření a znovuotevření panelu komponentu odmontuje → zase vše sbalené.

**Styly**: převzít scoped CSS z vendoru (`.detail` … `.t-violet`) – bez vnějšího `margin: 0 28px`
(panel je uvnitř `RunDetail`), `h3` bez `text-transform: lowercase` (české popisky s velkým
písmenem), zachovat `[data-theme="light"]` override pro `.cfg-chip` a `.p-pre`. `pre` a `.md`
styly existují globálně v `style.css` (zkontrolovat, případně doplnit lokálně). Barvy přes
existující CSS proměnné (`--purple`, `--violet`, `--cyan`, `--green`, `--red`, `--panel-2/3`, …).

### 10. `components/runs/RunDetail.vue`

- `selected = phases.find(p => p.phase_id === props.phaseId) ?? null` – **nevybírat první fázi**.
- `<PhaseDetail v-if="selected" :key? (nekeyovat – reset řeší watch)` s props
  `run-id`, `phase`, `request = detail.session?.request ?? null`, gates/envelopes/events
  fáze; `@close="onClose"`.
- `onClose`: `window.location.hash = runHref(run.run_id)` (router poslouchá `hashchange`).
- Tabulka fází: klik na řádek/odkaz vybírá fázi jako dnes (`runHref(run_id, phase_id)`); pokud
  žádná fáze vybraná, pod tabulkou krátký hint `faint` „Vyber fázi pro detail.“
  (`data-test="phase-hint"`).
- Kontejner `.phase-panel` (border/padding) nahradit stylem panelu vendoru (`.detail` má
  vlastní rámeček) – ponechat jen `margin-top`.

### 11. `views/RunsView.vue`

Funkčně beze změny (data panelu už plynou přes `detail`/`events`, živé tail aktualizuje
props). Ověřit, že se při změně `phaseId` nevolá reload (dnes ne). Žádný nový polling.

### 12. Unit testy (vitest)

Fixtures `src/test/runsFixtures.ts` rozšířit (bez rozbití stávajících testů):
- `detail().session` → `{ ..., request: '# Zadání\n\nNavrhnout **schéma**.' }` (ostatní pole null);
- fáze `p1`: `description: 'Naplánuj práci'`, `retries: 2`, usage s
  `cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens: 10`, `total_tokens`, ceny;
- gates: přidat k `tests_pass` `checks` s jednou selhanou kontrolou s víceřádkovou poznámkou
  (`'exit 1\nFAILED test_x'`) a jednou prošlou → label „1 z 2 selhalo“;
- events: `agent_start` payload `{ coding_agent: 'claude', model: 'claude-opus-4', thinking:
  'high', tools: ['Read','Edit'], harness_engineering: [], purpose: 'plánuje', session_id: 'sess-1' }`,
  `agent_end` s usage, `quality:test` událost ve fázi `p2`
  (`type: 'tool_call', name: 'quality:test', payload: { command: 'uv run pytest', returncode: 1, passed: false }`),
  událost `phase_start` s payloadem.
- helper `prompts(over)` pro odpověď API a `mockFetch(routes)`/`vi.stubGlobal('fetch', …)`
  vracející envelope `{ ok: true, data, error: null, warnings: [] }`.

`components/runs/PhaseDetail.test.ts` (přepsat):
- hlavička: název, stav, štítky agent/druh/pokus `1/2`, chyba fáze, klik na `phase-close`
  emituje `close`;
- všechny sekce sbalené po mountu (`.dsec-body` count 0), viditelné sekce
  `request, config, description, prompts, gates, cost, outputs` u p1; u p2 (kód) chybí
  `config`, `prompts`, `cost`;
- rozbalení sekce + `setProps({ phase: p2 })` → znovu vše sbalené; `setProps` s novým objektem
  stejné fáze (kopie p1 + nová událost v `events`) → otevřená sekce zůstane otevřená;
- Požadavek: Náhled renderuje `<strong>`, záložka Zdroj ukáže surový text;
- konfigurace: coding agent, model s `img[src="/models/claude.png"]`, thinking, tools chips,
  harness „žádné“, purpose, session;
- prompty: mock fetch → po otevření sekce dva panely sbalené s „N řádků“, rozbalení ukáže
  text; `legacy: true` → `prompts-legacy` hláška; fetch voláno jednou na fázi a URL
  `/api/runs/r-ok/phases/p1/prompts`; chyba API → hláška;
- gates: sbalené řádky, „1 z 2 selhalo“, pokus, rozbalení ukáže kontroly, víceřádková poznámka
  v `pre.check-note-block`, porušení;
- náklady: řádky vstup/výstup/thinking/cache čtení/cache zápis/celkem, ceny `$0.1000` formát,
  thinking má třídu `u-nested`; u fáze `code` sekce chybí; fáze bez usage → jen celkem + poznámka;
- výstupy: typ, agent, pokus, „platný“, zvýrazněný JSON (`.j-key`);
- události: pravý sloupec viditelný bez rozbalování, tool call → `argumenty` se zvýrazněním a
  `výsledek`; quality událost → příkaz `uv run pytest` a návratový kód `1`; jiná událost →
  payload; žádný element s atributem `title`.

`components/runs/RunDetail.test.ts`: upravit „shows the selected phase detail“; přidat
„bez phaseId se panel nezobrazí“ (`.phase-detail` neexistuje, `tr.selected` neexistuje) a
„close nastaví hash na `#/runs/r-ok`“. Stub `fetch` pro prompty (nebo `vi.mock('@/lib/runs')`
jen pro `fetchPhasePrompts`).

`views/RunsView.test.ts`: test s `#/runs/r-ok/p1` teď navíc volá prompts endpoint – rozšířit
mock fetch, aby `/prompts` vracel validní envelope (a ověření počtu volání `tail` nezapočítávalo
prompty). Ostatní testy RunsView musí projít beze změny chování.

Lib testy: `models.test.ts`, `format.test.ts`, `events.test.ts`, `runs.test.ts` (viz výše).
`noNativeUi.test.ts` musí projít.

### 13. Prohlížečový test — `aifactory/tests/e2e/test_f3_browser.py`

Nová pomocná funkce `_check_run_detail(page, server, run_id, task_id)` volaná v
`test_f3_task_lifecycle_in_browser` hned po `_watch_run(page, server, run1, first)` (před
`_approve`):
1. Na obrazovce Běhy kliknout odkaz běhu `tr[data-run="{run_id}"] a` (ověř selektor v
   `RunsList.vue`), `expect(page).to_have_url(re.compile(rf"#/runs/{run_id}$"))`.
2. `expect(page.locator(".phase-detail")).to_have_count(0)` (žádná fáze předvybraná).
3. Kliknout `table.phases a` s textem `plan` (`get_by_role("link", name="plan", exact=True)`
   v `table.phases`), ověřit `.phase-detail` viditelný a `.phase-detail .dsec-body` count 0;
   sekce `[data-section="prompts"]`, `gates`, `outputs` existují; `_no_native_tooltips(page)`.
4. Kliknout `[data-section="prompts"] [data-test="dsec-toggle"]`, počkat na
   `[data-test="prompt-panel"]` (count ≥ 1, `SERVER_TIMEOUT_MS`), ověřit že žádný
   `.prompt-body` není otevřený, rozbalit `[data-prompt="system"] [data-test="prompt-toggle"]`
   a `expect(...prompt-body).to_contain_text("You are the planner.")` (system prompt planneru
   z `tests/run/run_repo.py`: `.factory/prompts/planner/system.md`). Pokud by system prompt
   nebyl, alternativně user prompt obsahuje text zadání „Zadání prvního tasku.“ – ale primárně
   hledat `You are the planner.`.
5. Zavřít panel `[data-test="phase-close"]` → `.phase-detail` count 0 a URL bez fáze.
Při selhání přidat `server.report(task_id)` do zprávy (vzor `_watch_run`). Další průběh testu
(`_approve` naviguje přes `_nav`) se nemění.

Ověř, že fake harness/engine skutečně zapíše prompty do
`<session>/planner/prompts/phases/plan/` (zapisuje `engine/prompts.py` nezávisle na harnessu);
když ne, API vrátí `source: "agent"` s posledními prompty agenta a test projde také (text je
stejný) – panel pak ukáže legacy hlášku.

### 14. Build — `aifactory/src/aifactory/web/static/`

`just web-build` (vue-tsc + vite build, `emptyOutDir`) a výsledek (`index.html`, `assets/*`,
`logo.svg`, `models/*.png`) nechat v pracovním stromu; staré hashované assety odstraní build sám.
Ověř, že `aifactory/pyproject.toml` balí i `static/models/*.png` (hatch/setuptools package data);
pokud je tam whitelist přípon, doplnit `png`.

### 15. Dokumentace

`app_docs/HAIFA-S02-T02-panel-faze-behu-podle-sssf.md` (česky): co panel ukazuje, odkud bere
data (props + jednorázový `/prompts`), chování sbalení, testy. (Píše documenter; builder jen
pokud to workflow vyžaduje.)

## Pořadí práce

1. Ikony + `models.ts`, `format.ts`, `highlight.ts`, `events.ts`, `runs.ts` s testy.
2. `DetailSection.vue`, `StatChip.vue`.
3. `PhaseDetail.vue` (port), fixtures, `PhaseDetail.test.ts`.
4. `RunDetail.vue` + test, úprava `RunsView.test.ts`.
5. `just web-test`, `just web-build`.
6. e2e test, `just e2e`.
7. `just test`, `just typecheck`, `just lint`.

## Ověření

- `just web-test` (vue-tsc + vitest) projde, včetně `noNativeUi.test.ts`.
- `just web-build` → `aifactory/src/aifactory/web/static/` aktualizován, obsahuje `models/claude.png`.
- `just test` (spouští i `web-test` + pytest), `just typecheck`, `just lint`, `just e2e` projdou.
- `git status` ukazuje změny jen v `aifactory/` a spec/doc souborech úkolu; `vendor/` a
  `prototype/` beze změny; `aifactory/web/package.json` a `bun.lock` beze změny.
- Ručně (volitelně `just dash`): detail běhu bez vybrané fáze nemá panel; po kliknutí na fázi
  panel se sbalenými sekcemi, Události vpravo; zavření křížkem vrátí `#/runs/<id>`.

## Mimo rozsah

Waterfall běhu, soubory z `context_handoff/`, surový výstup harnessu (`output_artifact` se jen
zobrazí jako hodnota v payloadu, neotevírá se), změny backendu API.
