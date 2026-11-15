---
id: HAIFA-TODO-T30
title: "T54: Lokalizovat obrazovku běhů"
status: done
depends_on: []
related: [HAIFA-S01-T54]
writes: [aifactory/web/, aifactory/src/aifactory/web/, aifactory/tests/]
---

## Zadání
Převést seznamy, ovládání běhů, fáze, náklady, řetězy, selhání a retry nabídky do EN/CS. Lokalizovat backendové stavové hlášky přes kódy nebo explicitní locale; logy, prompty a uložené odpovědi zachovat. Testovat přepnutí jazyka během sledování běhu bez ztráty výběru a živých aktualizací.

### Původ

Vznikl při běhu `dc9c566b` tasku `HAIFA-S01-T54` (Dokončit anglické a české UI dashboardu a zapnout výchozí EN), v kroku `build` (agent builder).
Důvod: RunsView, detaily běhů, waterfall a karty selhání zůstávají česky.
Závažnost: defect
Task `HAIFA-S01-T54` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-S01-T54 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-15 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/238 · náklady $0.00
