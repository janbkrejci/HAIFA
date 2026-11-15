---
id: HAIFA-TODO-T33
title: "T54: Lokalizovat Knihovnu a nastavení počítače"
status: done
depends_on: []
related: [HAIFA-S01-T54]
writes: [aifactory/web/, aifactory/src/aifactory/web/, aifactory/tests/]
---

## Zadání
Převést správu knihovny, synchronizaci, import, historii, kopie repozitářů, nálezy, dashboard settings a harnessy do EN/CS. Zahrnout backendové hlášky a potvrzení bez parsování českých vět. Doplnit testy izolace locale klientů a zachování rozepsaných formulářů.

### Původ

Vznikl při běhu `dc9c566b` tasku `HAIFA-S01-T54` (Dokončit anglické a české UI dashboardu a zapnout výchozí EN), v kroku `build` (agent builder).
Důvod: SetupView, LibrarySection, kontrola počítače a dialog harnessů používají české texty.
Závažnost: defect
Task `HAIFA-S01-T54` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-S01-T54 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-15 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/241 · náklady $0.00
