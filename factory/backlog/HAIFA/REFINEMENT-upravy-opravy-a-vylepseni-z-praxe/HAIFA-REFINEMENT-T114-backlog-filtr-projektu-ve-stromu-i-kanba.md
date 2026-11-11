---
id: HAIFA-REFINEMENT-T114
title: "Backlog: filtr projektu ve stromu i kanbanu, bez filtru stepu, zapamatovaný"
status: todo
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T116]
writes: [aifactory/web/src/lib/backlog.ts, aifactory/web/src/lib/backlog.test.ts, aifactory/web/src/components/backlog/BacklogFilters.vue, aifactory/web/src/components/backlog/BacklogFilters.test.ts, aifactory/web/src/views/BacklogView.vue, aifactory/web/src/views/BacklogView.test.ts, aifactory/src/aifactory/guide/04-backlog.md, aifactory/tests/e2e/test_f3_browser.py, aifactory/src/aifactory/web/static/]
---

## Zadání
## Zadání
Na stránce Backlog (`aifactory/web/src/views/BacklogView.vue`) se teď filtr projektu a stepu zobrazuje jen v režimu kanban (`components/backlog/BacklogFilters.vue`, `v-if="kanban"`) a strom (`treeItems`) se podle projektu nefiltruje.

Upravit takto:
- Filtr projektu (výběr „vše“ nebo projekt z `projectOptions`) ukazovat ve stromu i v kanbanu. Ve stromu filtr ponechá jen kořenový kontejner vybraného projektu (u backlogu s méně než třemi úrovněmi odpovídající kontejner), v kanbanu jen tasky projektu jako dosud přes `filterKanban`. Prázdný výsledek ve stromu ukáže dosavadní stav „Filtru nic neodpovídá.“ a „Zrušit filtr“ filtr projektu také zruší.
- Filtr stepu z kanbanu odstranit: select `step-filter`, `setStep` a pole `step` v `BacklogFilters` (`lib/backlog.ts`) včetně jeho použití ve `filterKanban`. `stepOptions` zůstává, používá ho `TaskForm.vue`.
- Jeden společný filtr pro strom i kanban: přepnutí Strom/Kanban filtr zachová. Filtr se pamatuje v prohlížeči (localStorage, po vzoru `HIDE_DONE_KEY` a `setHideDone`) zvlášť pro každé repo (klíč obsahuje id repa z `useRepoId`/`currentRepoId`), takže přežije odchod z backlogu, návrat i reload. Uložený projekt, který už v backlogu není, se ignoruje jako „vše“.
- Nabídnout v `lib/backlog.ts` exportované funkce pro čtení a zápis uloženého filtru projektu (např. `backlogProject(repoId)` a `setBacklogProject(repoId, project)`), aby na ně mohl navázat proklik z Přehledu (HAIFA-REFINEMENT-T115).
- V příručce `aifactory/src/aifactory/guide/04-backlog.md` v části „Strom a kanban“ jednou větou popsat filtr projektu společný pro strom a kanban.

Před změnou dohledat přímé volající `BacklogFilters`, `filterKanban`, `stepOptions` a selektorů `step-filter`/`project-filter` v `aifactory/web/src/` i `aifactory/tests/` (mimo jiné `BacklogFilters.test.ts`, `BacklogView.test.ts`, `lib/backlog.test.ts`, `tests/e2e/test_f3_browser.py`) a upravit jejich očekávání.

Mimo rozsah: Přehled a proklik na projekt (HAIFA-REFINEMENT-T115), změny API backlogu.

Hotovo znamená:
- Ve stromu i kanbanu je výběr projektu, výběr stepu na stránce Backlog není.
- Webový test: výběr projektu ve stromu zobrazí jen tento projekt, po přepnutí na Kanban jsou vidět jen jeho tasky a filtr zůstává vybraný, po přepnutí zpět na Strom také.
- Webový test: filtr se uloží do localStorage pod klíčem repa a po novém připojení `BacklogView` se obnoví. Jiné repo ho nepřebírá a neznámý uložený projekt znamená „vše“.
- Unit testy v `lib/backlog.test.ts` pokrývají `filterKanban` bez stepu a čtení i zápis uloženého filtru.
- Projdou `just lint`, `just typecheck`, `just web-test`, všechny editované testovací soubory a změněný browser test přes `just pytest tests/e2e/test_f3_browser.py -n0`, pokud se měnil.
- Proběhne `just web-build` a aktualizuje se distribuovaný statický frontend.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
