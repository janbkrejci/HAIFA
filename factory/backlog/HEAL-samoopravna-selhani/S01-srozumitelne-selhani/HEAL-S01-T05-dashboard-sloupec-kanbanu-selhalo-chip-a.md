---
id: HEAL-S01-T05
title: "Dashboard: sloupec kanbanu „Selhalo“, chip a příručka"
status: done
workflow: build-test-review
depends_on: [HEAL-S01-T04]
writes: [aifactory/web/src/, aifactory/src/aifactory/web/static/, aifactory/src/aifactory/guide/04-backlog.md, aifactory/tests/test_guide_consistency.py]
---

## Zadání
## Zadání
Navazuje na HEAL-S01-T04: backend vrací board state `failed` pro task, jehož poslední běh selhal nebo byl přerušen. Dashboard ho má ukázat jako vlastní sloupec kanbanu „Selhalo“, aby se selhaný task neschovával v Připraveno. Postupuj stejně jako u stavu `approved` (HAIFA-REFINEMENT-T60).

## Co udělat (`aifactory/web/src/`)
- `lib/backlog.ts`: přidej `BoardState` `failed` do typu i do `BOARD_STATES` za `blocked`. Popisek do `STATE_LABELS` bude „Selhalo“, tooltip do `STATE_TOOLTIPS` třeba „Poslední běh tasku selhal. Podrobnosti a akce najdeš v detailu tasku nebo běhu.“ Stav dej do `OPTIONAL_STATES`, takže se sloupec a volba filtru ukážou, jen když v nich je task. Do `DEFERRABLE_STATES` ho přidej, aby šel selhaný task odložit z auto-continue.
- `style.css`: barva chipu `.state-chip.state-failed`, odlišná od Blokováno a Zrušeno, ve smyslu chyby (červená z palety). Barva uzlu a legenda v `components/backlog/DependencyGraph.vue`.
- `components/backlog/KanbanBoard.vue`, `StateChip.vue`, `TaskDetail.vue`, `TaskForm.vue`, `views/BacklogView.vue`, `lib/overview.ts`: zkontroluj místa, která stavy vyjmenovávají nebo testují (např. povolené akce podle stavu). Selhaný task jde jako Připraveno upravit a spustit znovu nebo pokračovat (retry), jen není v řazení sloupce Připraveno.
- Souhrn stavů na Přehledu (`lib/overview.ts`, `RepoControls`) ukáže „Selhalo N“, když takový task je.
- Uprav fixtures a testy, které stavy vyjmenovávají (`StateChip.test.ts`, `KanbanBoard.test.ts`, `overview.test.ts`, `backlogQueue.test.ts`, `BacklogView`/`App.test.ts` a další podle grepu). Přidej test, že se task s `board_state: 'failed'` ukáže ve sloupci „Selhalo“ a ne v Připraveno.
- Přebuilduj `aifactory/src/aifactory/web/static/`.
- Příručka `aifactory/src/aifactory/guide/04-backlog.md`: doplň **Selhalo** do výčtu stavů. Test souladu příručky s UI (`aifactory/tests/test_guide_consistency.py`) musí projít; uprav ho jen tehdy, když stavy vyjmenovává.

## Mimo rozsah
Backend (HEAL-S01-T04) a chování auto-continue se nemění.

Hotovo znamená:
- `just web-test` projde.
- `uv run pytest tests -k guide -n0` v `aifactory/` projde.
- Ručně: task, jehož běh selhal, je na Backlogu ve sloupci „Selhalo“ s červeným chipem, ne v Připraveno. Ve filtru stavů je volba Selhalo a souhrn na Přehledu ho počítá. Po úspěšném opakování se task přesune dál (Běží, review, Hotovo).

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-02 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/201 · náklady $1.89
