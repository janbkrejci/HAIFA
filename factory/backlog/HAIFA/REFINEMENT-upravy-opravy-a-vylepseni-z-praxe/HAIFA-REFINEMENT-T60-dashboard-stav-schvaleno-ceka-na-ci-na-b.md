---
id: HAIFA-REFINEMENT-T60
title: "Dashboard: stav „Schváleno, čeká na CI“ na Backlogu, Přehledu a v Review"
status: todo
workflow: build-test-review
depends_on: [HAIFA-REFINEMENT-T59]
writes: [aifactory/web/src/, aifactory/src/aifactory/web/static/, aifactory/src/aifactory/guide/, aifactory/tests/test_guide_consistency.py, aifactory/tests/e2e/test_f3_browser.py, aifactory/tests/e2e/test_multi_repo_browser.py]
---

## Zadání
Navazuje na T59: backend vrací board state `approved`, seznam a počet `approved` v přehledu a pole `approved` / `approved_at` v Review.

## Co udělat (`aifactory/web/src/`)
- `lib/backlog.ts`: nový `BoardState` `approved` za `in review`. Popisek „Schváleno, čeká na CI“, tooltip „Schválil jsi pull request. Factory čeká na zelené CI a potom ho mergne sama.“ Stav dej do `OPTIONAL_STATES`, takže sloupec kanbanu a volba filtru se ukážou, jen když v nich je task. Přidej barvu chipu (`style.css`) a uzlu/legendy v `DependencyGraph.vue`, odlišnou od `in review` i `awaiting merge`.
- `lib/api.ts`, `lib/overview.ts`, `lib/review.ts`: typy pro `approved`. `fetchOverview` doplní chybějící `approved` na `[]`. Přidej počet do `repoCounts`/`totals` a urgenci jako u `automerge`, tedy mezi repa čekající na uživatele nepatří.
- `components/overview/RepoCard.vue` / `RepoWork.vue`: sekce „Schváleno, čeká na CI“ (`data-test="approved"`), řádky odkazují do Review. `RepoSwitcher.vue`: počet u repa.
- `components/review/ReviewList.vue`: skupina „Schváleno, čeká na CI“ mezi „Čeká na review“ a „Čeká na automerge PR“. `views/ReviewView.vue`: po schválení s odpovědí `started` se PR po obnovení seznamu přesune do této skupiny. Nabídka dalšího PR ho přeskočí. V detailu (`ReviewDetail.vue`) ukaž, kdy bylo schváleno. Tlačítko Schválit zůstane dostupné pro opakování.
- `components/backlog/TaskDetail.vue`, `TaskForm.vue`: `approved` je, stejně jako `in review`, stav, ve kterém task nejde upravit ani spustit.
- Uprav fixtures a testy (`overview.test.ts`, `RepoCard.test.ts`, `ReviewList.test.ts`, `ReviewView.test.ts`, `StateChip.test.ts`, `KanbanBoard.test.ts`, `App.test.ts` a další, které stav vyjmenovávají).
- Přebuilduj `aifactory/src/aifactory/web/static/`.
- Příručka `aifactory/src/aifactory/guide/`: doplň stav do tabulky stavů (`04-backlog.md`) a do popisu schválení (`05-behy-a-review.md`, `03-prvni-beh.md`). Test souladu příručky s UI musí projít.

## Mimo rozsah
Backend se nemění.

Hotovo znamená:
- `just web-test` projde.
- Testy příručky (`uv run pytest tests -k guide -n0` v `aifactory/`) projdou.
- Ručně: po Schválit u PR bez auto-merge na hostingu s CI se task na Backlogu, na Přehledu, v přepínači rep i v Review ukazuje jako „Schváleno, čeká na CI“. Po merge je Hotovo, po červeném CI znovu „Čeká na review“.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
