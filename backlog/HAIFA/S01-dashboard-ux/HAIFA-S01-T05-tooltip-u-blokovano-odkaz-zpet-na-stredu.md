---
id: HAIFA-S01-T05
title: "Tooltip u Blokováno, odkaz zpět na středu, „ID: Název“"
status: done
workflow: plan-build-test
depends_on: [HAIFA-S01-T04]
---

## Zadání
Udělej tři drobnosti v UI. Badge Blokováno má tooltip, co task blokuje. Odkaz zpět (← backlog, ← všechny běhy, ← všechny PR) je svisle na středu vedlejšího nadpisu. Mezi kódem tasku a názvem je dvojtečka jako v seznamu PR v detailu tasku, tedy `M01-S01-T02: Loader`.

Where: `aifactory/web/src/` (`components/backlog/StateChip.vue`, `components/backlog/TreeNode.vue`, `components/backlog/TaskDetail.vue`, `views/BacklogView.vue`, `views/RunsView.vue`, `views/ReviewView.vue`, `components/runs/RunsList.vue`, `components/runs/RunDetail.vue`, `components/runs/CostTotals.vue`, `components/review/ReviewList.vue`, `components/review/ReviewDetail.vue`, `test/backlogFixtures.ts` a testy), build v `aifactory/src/aifactory/web/static/`.

Done means:
- Badge Blokováno ve stromu i v detailu tasku má tooltip dashboardu se seznamem z `blocked_by`: kód blokující položky a důvod česky (task není hotový, task je zrušený, položka neexistuje, step nebo projekt je prázdný, step nebo projekt má nehotové tasky s jejich kódy).
- Odkaz zpět je jedna sdílená komponenta ve všech třech obrazovkách: ikona šipky místo znaku ← a text, obojí svisle na středu nadpisu.
- Kód a název tasku mají formát `ID: Název` v seznamu běhů, v hlavičce běhu, v nákladech po tascích, v seznamu PR a v hlavičce PR. Bez názvu se ukáže jen kód.
- Unit testy (vitest): text tooltipu pro každý důvod, přesný text `M01-S01-T02: Loader` na všech pěti místech, odkaz zpět obsahuje ikonu. Blokovaný task ve fixtures má vyplněné `blocked_by`.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: názvy blokujících položek v tooltipu a tooltipy s názvy u ostatních kódů (samostatný úkol), změny API.

Pevná omezení:
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow plan-build-test · PR https://github.com/janbkrejci/HAIFA/pull/18 · náklady $1.48
