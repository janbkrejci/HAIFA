---
id: HAIFA-TODO-T29
title: "T54: Lokalizovat Backlog a všechny jeho dialogy"
status: todo
depends_on: []
related: [HAIFA-S01-T54]
writes: [aifactory/web/, aifactory/src/aifactory/web/, aifactory/tests/]
---

## Zadání
Převést strom, kanban, filtry, stavy, detaily, dokumenty, formuláře kontejnerů a tasků, Intent, follow-up, workflow advice a spouštěcí dialog. Nahradit české plurálové literály katalogy. Přepnutí musí zachovat rozepsaný Intent, formuláře a otevřené panely. Aktualizovat české testy na explicitní cs a přidat regresní EN/CS scénáře.

### Původ

Vznikl při běhu `dc9c566b` tasku `HAIFA-S01-T54` (Dokončit anglické a české UI dashboardu a zapnout výchozí EN), v kroku `build` (agent builder).
Důvod: BacklogView a komponenty Backlogu včetně Intentu mají rozsáhlé české formuláře, validace a odvozené texty.
Závažnost: defect
Task `HAIFA-S01-T54` na tomto tasku závisí a do jeho dokončení zůstává blokovaný.

<!-- factory: follow-up-of=HAIFA-S01-T54 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
