---
id: HAIFA-S01-T07
title: "Backlog: skládání stromu, filtr kanbanu, klik na řádek"
status: done
depends_on: [HAIFA-S01-T06]
---

## Zadání
Na obrazovce Backlog: strom jde skládat po projektech a stepech, kanban jde filtrovat podle projektu a stepu a klik kamkoli na řádek projektu nebo stepu otevře jeho graf.

Where: `aifactory/web/src/` (`views/BacklogView.vue`, `components/backlog/BacklogTree.vue`, `components/backlog/TreeNode.vue`, `components/backlog/BacklogFilters.vue`, `components/backlog/KanbanBoard.vue`, `lib/backlog.ts`, `lib/router.ts` a testy), `aifactory/tests/e2e/test_f3_browser.py`, build v `aifactory/src/aifactory/web/static/`.

Done means:
- Řádek projektu a stepu má šipku, která skládá a rozkládá jeho obsah. Podle rozhodnutí v `docs/decisions.md`: strom začne sbalený s viditelnými projekty, prohlížeč si pamatuje, co uživatel rozbalil, a aktivní filtr stavu rozbalí větve se shodou.
- Stav skládání vydrží přechod do detailu tasku a zpět.
- Kanban má filtry Projekt a Step s popisky podle `levels` (dropdown dashboardu). Step nabízí jen stepy vybraného projektu. Filtry se kombinují s filtrem stavu a prázdný filtr znamená vše. Při méně než třech úrovních filtr stepu chybí.
- Klik kamkoli na řádek projektu nebo stepu otevře `#/backlog/graph/<id>`. Klik na šipku jen skládá. Řádek jde otevřít i klávesnicí a při najetí myší vypadá klikatelně.
- Unit testy (vitest): složení skryje tasky, stav vydrží návrat z detailu, filtr kanbanu vrací správné tasky i se stavem, klik na řádek změní adresu a klik na šipku ne.
- Prohlížečový test najde tasky ve sbaleném stromu.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: filtr projektu a stepu ve stromu, klik na řádek tasku, změny API.

Pevná omezení:
- Žádná nová závislost frontendu.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/36 · náklady $1.98
