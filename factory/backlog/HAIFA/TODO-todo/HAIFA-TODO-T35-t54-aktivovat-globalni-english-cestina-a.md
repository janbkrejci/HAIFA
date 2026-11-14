---
id: HAIFA-TODO-T35
title: "T54: Aktivovat globální English/Čeština a ověřit úplnou lokalizaci"
status: todo
depends_on: []
related: [HAIFA-S01-T54]
writes: [aifactory/web/, aifactory/src/aifactory/web/, aifactory/src/aifactory/guide/, aifactory/tests/]
---

## Zadání
Navázat na všechny migrační díly T54. Zpřístupnit English/Čeština i bez repozitáře, zachovat EN bez detekce prohlížeče a ověřit persistence napříč repozitáři. Auditovat katalogy, nepřeložené literály a shodu příručky s výslednými popisky. Přidat browser scénáře default EN, CS, persistence, návrat EN, rozepsaný Intent/formulář, otevřený panel, sledovaný běh, chybu API v obou jazycích a úzké okno. Upravit distribuovaný frontend a provést všechny požadované kontroly před uzavřením T54.

### Původ

Vznikl při běhu `dc9c566b` tasku `HAIFA-S01-T54` (Dokončit anglické a české UI dashboardu a zapnout výchozí EN), v kroku `build` (agent builder).
Důvod: Globální přepínač nelze vydat jako dokončenou lokalizaci před migrací všech obrazovek. Distribuované assety zatím zůstávají původní.
Závažnost: defect
Task `HAIFA-S01-T54` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-S01-T54 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
