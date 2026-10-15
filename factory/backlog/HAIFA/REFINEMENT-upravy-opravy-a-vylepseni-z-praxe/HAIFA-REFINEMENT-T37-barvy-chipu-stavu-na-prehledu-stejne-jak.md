---
id: HAIFA-REFINEMENT-T37
title: Barvy chipů stavů na Přehledu stejné jako v backlogu/stromu
status: done
workflow: build-test-review
depends_on: []
related: [HAIFA-REFINEMENT-T30, HAIFA-REFINEMENT-T20]
writes: [aifactory/web/src/components/overview/, aifactory/web/src/components/backlog/StateChip.vue, aifactory/web/src/components/backlog/StateChip.test.ts, aifactory/web/src/lib/overview.ts, aifactory/web/src/lib/overview.test.ts, aifactory/web/src/style.css]
---

## Zadání
Chipy na Přehledu u jednotlivých rep, které ukazují stavy tasků (počet tasků v každém stavu), mají mít stejné barvy jako chipy stavů na stránce Backlog/strom.

## Současný stav
- Přehled: souhrn stavů vykresluje `aifactory/web/src/components/overview/RepoControls.vue` (`span.chip` s `data-test="task-summary-item"` a `data-state`, data z `taskSummary()` v `lib/overview.ts`). Chipy mají jen neutrální rámeček bez barvy podle stavu.
- Backlog/strom: `aifactory/web/src/components/backlog/StateChip.vue` barví chip podle stavu (todo s čárkovaným rámečkem, ready cyan, blocked amber, running blue, in review purple, done green, cancelled faint s přeškrtnutím).

## Požadavek
- Každý chip stavu na Přehledu má stejnou barvu textu, rámečku a pozadí jako chip stejného stavu v backlogu/stromu.
- Barvy mají mít jeden zdroj. Buď se na Přehledu použije `StateChip` (umí `count`), nebo se styly stavů sdílejí. Nemají vzniknout dvě ručně udržované kopie.
- Pořadí stavů, popisky a počty zůstanou stejné. Zachovat `data-test="task-summary-item"` a `data-state`, aby fungovaly stávající testy.

## Akceptační kritéria
- Na Přehledu má chip každého stavu stejné barvy jako odpovídající chip ve stromu backlogu.
- Vzhled chipů v backlogu/stromu se nezmění.
- Stávající testy Přehledu a StateChip projdou. Test ověří, že chip na Přehledu nese třídu nebo označení stavu, podle kterého se barví.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-15 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/50 · náklady $1.01
