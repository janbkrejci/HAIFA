---
id: HAIFA-TODO-T27
title: "T54: Lokalizovat navigaci, topbar a sdílené komponenty dashboardu"
status: todo
depends_on: []
related: [HAIFA-S01-T54]
writes: [aifactory/web/, aifactory/src/aifactory/web/, aifactory/tests/]
---

## Zadání
Převést navigaci, topbar, přepínač repozitářů, čipy, bannery, potvrzení, sdílené ovládání a stavové popisky do EN/CS katalogů. Zajistit reaktivní popisky bez remountu, lokalizovaný titulek a html lang. Zahrnout tooltipy, aria-label a odpovídající testy; nezpřístupňovat nehotovou celkovou lokalizaci jako dokončenou.

### Původ

Vznikl při běhu `dc9c566b` tasku `HAIFA-S01-T54` (Dokončit anglické a české UI dashboardu a zapnout výchozí EN), v kroku `build` (agent builder).
Důvod: App.vue, router a sdílené komponenty stále obsahují české UI literály. Katalog před migrací obsahoval pouze pět klíčů; rozsah vyžaduje rozdělení povolené zadáním.
Závažnost: defect
Task `HAIFA-S01-T54` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-S01-T54 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
