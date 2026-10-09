---
id: HAIFA-S02-T02
title: Panel fáze běhu podle sssf
status: done
depends_on: [HAIFA-S01-T05, HAIFA-S02-T01]
---

## Zadání
Převezmi z visualizeru sssf celý panel fáze do detailu běhu: vlevo požadavek, konfigurace agenta, popis, sestavené prompty, gates, náklady a výstupy, vpravo události. Všechny sekce začínají sbalené.

Where: `aifactory/web/src/` (`components/runs/PhaseDetail.vue`, `components/runs/RunDetail.vue`, `components/runs/StatChip.vue`, `components/runs/DetailSection.vue`, `views/RunsView.vue`, `lib/runs.ts`, `lib/events.ts`, `lib/format.ts`, `public/` a testy), `aifactory/tests/e2e/test_f3_browser.py`, build v `aifactory/src/aifactory/web/static/`. Zdroj: `vendor/sssf/apps/visualizer/src/components/PhaseDetail.vue`, `vendor/sssf/apps/visualizer/src/lib/` (`models.ts`, `events.ts`, `format.ts`, `highlight.ts`) a ikony `vendor/sssf/apps/visualizer/public/models/`.

Done means:
- Panel se ukáže až po výběru fáze a jde zavřít. Detail běhu už sám nevybírá první fázi.
- Hlavička panelu: název, stav a doba fáze, štítky agent, druh a pokus z povolených opakování, chyba fáze.
- Levý sloupec: Požadavek (zadání běhu jako markdown s Náhledem a Zdrojem), Konfigurace agenta (coding agent, model s ikonou poskytovatele, thinking, tools, harness engineering, purpose, session), Popis, Sestavené prompty, Gates, Náklady a Výstupy. Sekce jsou sbalené po otevření panelu i po změně fáze a živé aktualizace jejich stav nemění.
- Sestavené prompty: system a user prompt fáze z `GET /api/runs/{run_id}/phases/{phase_id}/prompts`, každý sbalený, s počtem řádků a záložkami Náhled a Zdroj. Když API vrátí poslední prompt agenta, panel to řekne.
- Gates: jeden sbalený řádek na gate s výsledkem, počtem kontrol nebo „k z N selhalo“, pokusem a časem. Rozbalený řádek ukáže kontroly s poznámkami (víceřádková poznámka jako blok) a porušení.
- Náklady jen u fází agenta: vstup, výstup, thinking pod výstupem, cache čtení, cache zápis a celkem, dolary na 4 desetinná místa.
- Výstupy jsou envelopes se zvýrazněným JSON, agentem, pokusem a platností.
- Pravý sloupec Události je vždy vidět. Řádek má čas, barevný typ, popisek, dobu a tokeny a rozbalí se: tool call na nástroj, zvýrazněné argumenty a výsledek, ostatní události na zvýrazněný payload, i `quality:test` s příkazem a návratovým kódem.
- Popisky jsou česky, vzhled odpovídá visualizeru sssf.
- Unit testy (vitest) sekcí, sbalení po změně fáze, gates, nákladů a výstupů. Prohlížečový test po běhu otevře jeho detail, vybere fázi plan, ověří sbalené sekce a v Sestavených promptech najde text promptu planneru.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: waterfall běhu (samostatný úkol), soubory z `context_handoff/`, surový výstup harnessu.

Pevná omezení:
- Panel nemá vlastní polling. Data dostává z dnešního načtení běhu a živých aktualizací.
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/23 · náklady $5.37
