---
id: HAIFA-TODO-T34
title: "T54: Lokalizovat přidání repozitáře a panely pomocníků"
status: todo
depends_on: []
related: [HAIFA-S01-T54]
writes: [aifactory/web/, aifactory/src/aifactory/web/, aifactory/tests/]
---

## Zadání
Převést přidání a odebrání repozitáře, onboarding, procházení složek, AI průvodce a terminálové ovládání do EN/CS. Neměnit jazyk generovaných zadání, zprávy uživatele, uložené odpovědi ani výstupy terminálu. Ověřit zachování rozepsaných cest, zpráv a otevřených panelů.

### Původ

Vznikl při běhu `dc9c566b` tasku `HAIFA-S01-T54` (Dokončit anglické a české UI dashboardu a zapnout výchozí EN), v kroku `build` (agent builder).
Důvod: ReposAddView, procházení složek, AI průvodce a terminálové ovládání dosud obsahují české UI literály.
Závažnost: defect
Task `HAIFA-S01-T54` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-S01-T54 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
