---
id: HEAL-TODO-T01
title: Doplnit rozhodnutí „Prázdný commit“ v docs/decisions.md o already_done a Hotovo u nothing_to_do
status: done
archived: true
workflow: build-review
depends_on: []
related: [HEAL-S02-T02]
writes: [docs/decisions.md]
---

## Zadání
V docs/decisions.md doplnit k rozhodnutí „Prázdný commit“: builder, který najde práci už hotovou, vrátí `already_done` s důkazem (commit nebo soubor). První build běhu s ním ukončí workflow bez testů, review a `accept`. Běh bez commitu skončí úspěšně bez PR a task dostane `done` v base se záznamem „bez změn … už hotovo: <důkaz>“. Když zadání žádá jen změnu backlogu, builder vrátí `nothing_to_do`. Karta selhání pak nabídne Hotovo (`POST /api/runs/{id}/done`, záznam „bez změn … důvod: <agent>: <shrnutí>“) nebo Zrušit task.

### Původ

Vznikl při běhu `54781ad6` tasku `HEAL-S02-T02` (Builder bez práce ukončí běh jako hotový bez změn), v kroku `build` (agent builder).
Důvod: HEAL-S02-T02 rozšířilo chování popsané rozhodnutím „Prázdný commit“. Builder teď vrací `already_done` s důkazem, workflow končí po prvním buildu a záznam v `## Běhy` nese důkaz. Běh `nothing_to_do` jde v dashboardu označit jako Hotovo. docs/decisions.md ale neleží v povolených cestách tohoto tasku.

<!-- factory: follow-up-of=HEAL-S02-T02 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-16 · workflow build-review · PR https://github.com/janbkrejci/HAIFA/pull/79 · náklady $0.32
