# HAIFA-S02-T02: Panel fáze běhu podle sssf

## Co se změnilo

Detail běhu převzal z visualizeru sssf celý panel fáze. Šablona `PhaseDetail.vue` je přepsaná podle předlohy: nahoře hlavička, vlevo sbalitelné sekce, vpravo sloupec událostí, který je vidět vždycky.

- **Panel až po výběru fáze.** `RunDetail.vue` už sám nevybírá první fázi. `selected` je `null`, dokud `phaseId` z URL neukazuje na existující fázi. Do té doby se zobrazí nápověda „Vyber fázi pro detail.“ (`data-test="phase-hint"`). Křížek v panelu (`data-test="phase-close"`) vyšle `close` a `RunDetail` přepne hash zpátky na `runHref(run_id)`.
- **Hlavička:** název fáze, `StatusChip`, doba fáze (u běžící fáze se dopočítává do teď), štítky `agent` (owner), `druh` (kind) a `pokus` jako `attempt/retries`. Chyba fáze se ukáže v červeném pruhu.
- **Levý sloupec** (sekce se zobrazí, jen když je co ukázat):
  - **Požadavek** – `session.request` vykreslený přes `MarkdownView` (Náhled / Zdroj).
  - **Konfigurace agenta** – bere se z payloadu události `agent_start`: coding agent, model s ikonou poskytovatele, thinking, tools, harness engineering, purpose a session. Když `agent_start` chybí, ukáže se aspoň `harness` a `model` z řádku fáze. Jen u fází `kind === 'agent'`.
  - **Popis** – `phase.description`.
  - **Sestavené prompty** – jen u fází agenta. Načítají se jednou pro dvojici `run:phase` přes `GET /api/runs/{run_id}/phases/{phase_id}/prompts` (`fetchPhasePrompts`) a výsledek se ukládá do mezipaměti v komponentě. Chyba se do mezipaměti neukládá a odpověď pro fázi, která už není zobrazená, se zahodí. System a user prompt jsou samostatně sbalené panely s počtem řádků (české skloňování) a vykreslují se přes `MarkdownView`. Když API vrátí `legacy` nebo `source === 'agent'`, panel napíše „Běh nemá prompty jednotlivých fází – zobrazuji poslední prompty agenta.“ U oříznutého promptu uvede `max_bytes`.
  - **Gates** – jeden sbalený řádek na gate s výsledkem, `checksLabel` (počet kontrol, nebo „k z N selhalo“), pokusem a časem. Rozbalený řádek ukáže kontroly s poznámkami (víceřádková poznámka jako blok) a porušení.
  - **Náklady** – jen u fází agenta. Řádky vstup, výstup, thinking (odsazený pod výstupem, s tooltipem; do součtu se nepočítá), cache čtení, cache zápis a celkem. Dolary jsou na 4 desetinná místa (`fmtMoney4`). Rozpis bere z `phase.usage`, jinak z `agent_end.usage`. Bez rozpisu ukáže jen řádek celkem s poznámkou „Běh nemá rozpis po složkách – zaznamenán jen součet.“
  - **Výstupy** – envelopes se zvýrazněným JSON (`highlightValue`), agentem, pokusem a štítkem platný/neplatný.
- **Pravý sloupec Události:** řádek má čas (`fmtClock`), barevný typ (`EVENT_TYPE_CLASS`), popisek (červeně, pokud `eventOk` vrátí false), dobu a tokeny jako kompaktní `StatChip`. Po rozbalení:
  - tool call ukáže nástroj, zvýrazněné argumenty a výsledek,
  - `quality:*` (tool_call s `command` a bez `tool`) ukáže příkaz, návratový kód a prošel/neprošel,
  - ostatní události ukážou zvýrazněný payload.
- **Stav sbalení.** Všechny sekce, gates, prompty i události začínají sbalené. Vynulují se jen při změně `phase.phase_id`. Živé aktualizace nahrazují objekty a pole, ale stav sbalení nemění. Panel nemá vlastní polling.

## Soubory

| Soubor | Role |
|---|---|
| `aifactory/web/src/components/runs/PhaseDetail.vue` | Celý panel (nové props `runId`, `request`, emit `close`) |
| `aifactory/web/src/components/runs/RunDetail.vue` | Žádný předvýběr fáze, nápověda, předání `run-id`/`request`, zavírání |
| `aifactory/web/src/components/runs/DetailSection.vue` | Prop `id` → `data-section`, `data-test="dsec-toggle"`, `aria-expanded`, o něco větší hlavička |
| `aifactory/web/src/components/runs/StatChip.vue` | Prop `compact` pro řádky událostí |
| `aifactory/web/src/lib/runs.ts` | Typy `PhasePrompts`, `AgentEndPayload`, `QualityPayload`, rozšířený `AgentStartPayload`; `fetchPhasePrompts`, `checksLabel` |
| `aifactory/web/src/lib/events.ts` | `parseAgentStart`, `parseAgentEnd`, `parseQualityCall`, `eventOk`, `EVENT_TYPE_CLASS` |
| `aifactory/web/src/lib/format.ts` | `fmtClock`, `fmtMoney4`, `fmtInt`, `plural`, `secondsBetween` |
| `aifactory/web/src/lib/highlight.ts` | `highlightValue` pro už rozparsované hodnoty |
| `aifactory/web/src/lib/models.ts` (nový) | Port `models.ts` ze sssf: `modelIcon`, `modelName` |
| `aifactory/web/public/models/*.png` | Ikony poskytovatelů (claude, gemini, kimi, openai, zai) |
| `aifactory/src/aifactory/web/static/` | Přestavěný frontend (nové `index-*.js/css`, `index.html`, `models/*.png`) |
| `aifactory/web/src/test/runsFixtures.ts` | Fixtures včetně `prompts()` a `okResponse` |
| `*.test.ts` u změněných modulů, `views/RunsView.test.ts` | Unit testy |
| `aifactory/tests/e2e/test_f3_browser.py` | Nový krok `_check_run_detail` |

## Jak ověřit

- `just test` – vitest pokrývá hlavičku a zavírání, výchozí sbalení, sbalení po změně fáze (a jeho zachování při živé aktualizaci), požadavek, konfiguraci (včetně záložního řešení bez `agent_start`), prompty (jedno načtení, legacy, chyba, zastaralá odpověď, žádný fetch u fáze typu code), gates, náklady (plné, jen součet, z `agent_end`), výstupy, události (tool call, quality, obecný payload) a absenci nativních `title`. `RunsView.test.ts` ověřuje, že živý tail prompty znovu nenačítá.
- `just e2e` – po dokončení běhu otevře jeho detail a ověří, že panel chybí. Pak vybere fázi `plan`, ověří, že žádná sekce není rozbalená a že existují sekce `prompts`, `gates` a `outputs`. Rozbalí Sestavené prompty a system prompt, v něm najde „You are the planner.“ Nakonec panel zavře.
- `just typecheck`, `just lint`.
- Ručně: v dashboardu otevřete `#/runs/<run_id>`, klikněte na fázi v tabulce a projděte sekce.
- Po změně frontendu přestavte statiku příkazem `just web-build`.
