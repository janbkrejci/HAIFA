---
id: HAIFA-REFINEMENT-T62
title: "Dashboard: běžící ani blokovaný task nejde Spustit, běžící nejde Upravit, další akce jen v povoleném stavu"
status: done
archived: true
workflow: build-test-review
depends_on: []
writes: [aifactory/web/src/components/backlog/TaskDetail.vue, aifactory/web/src/components/backlog/TaskDetail.test.ts, aifactory/web/src/lib/backlog.ts, aifactory/web/src/components/runs/RunDetail.vue, aifactory/web/src/components/runs/RunDetail.test.ts, aifactory/web/src/components/runs/FailureCard.vue, aifactory/web/src/components/runs/FailureCard.test.ts, aifactory/web/src/components/backlog/KanbanBoard.vue, aifactory/web/src/components/backlog/KanbanBoard.test.ts, aifactory/web/src/components/backlog/RunDialog.vue, aifactory/web/src/components/backlog/RunDialog.test.ts, aifactory/src/aifactory/web/static/, aifactory/web/src/views/BacklogView.test.ts, aifactory/web/src/views/BacklogView.spinner.test.ts, aifactory/src/aifactory/guide/, aifactory/tests/test_guide_consistency.py]
---

## Zadání
V detailu tasku (`aifactory/web/src/components/backlog/TaskDetail.vue`) je u tasku ve stavu `running` povolené tlačítko Spustit, protože `runBlocked` počítá jen s `noWorkflow`, `finished` a `forHuman`. Povolené je i Upravit (`data-test="edit"` hlídá jen `busy`). Totéž platí pro `in review` a `awaiting merge`. Spustit je povolené i u blokovaného tasku (`board_state == 'blocked'`, nesplněné závislosti) a dialog `components/backlog/RunDialog.vue` ho pak nabídne spustit i tak (`data-test="run-force"`).

Co udělat v `TaskDetail.vue`:
- Zaveď jeden computed pro stav, kdy task běží nebo má otevřený PR (`running`, `in review`, `awaiting merge`; dnes to dělá `adviceBlocked`). Použij ho pro:
  - Spustit: zakázané, s tooltipem podle stavu, např. „Task právě běží.“ nebo „Task čeká na review/merge PR.“.
  - Upravit: zakázané, s tooltipem „Task už nejde měnit.“, stejně jako Vylepšit agentem. Otevřený formulář úprav se zavře, když task při živém obnovení přejde do `running`.
  - Hotovo (`mark-done`) a odebrání vazeb (`unlink-*`, `unrelate-*`): zakázané.
- Blokovaný task: Spustit je zakázané, tooltip vypíše, na co čeká (`blocked_by`, stejné řádky jako `unmetLine` v banneru připravenosti). Výjimka: když všechny nesplněné závislosti čekají jen v otevřeném PR (stav `in review`/`awaiting merge`), Spustit nech povolené, protože běh se může skládat na jejich PR (stacked PRs). Pokud to repo nemá zapnuté, dialog ukáže chybu z backendu. Upravit, vazby a Vylepšit agentem zůstávají u blokovaného tasku povolené, protože jimi se blokace řeší.
- Kód stavů dej do sdílených funkcí v `aifactory/web/src/lib/backlog.ts` vedle `DEFERRABLE_STATES`, ať se stavy nepočítají na více místech.

V `RunDialog.vue`: odstraň možnost spustit task s nesplněnými závislostmi (tlačítko `run-force` pro `unmet`/`unmet_dependencies`). Varování s výpisem závislostí zůstane a Spustit je zakázané. Skládaný start (`stack`) dál funguje. Pokud `force` v dialogu slouží i jiným varováním (D4, task není v base), pro ně ho nech.

Projdi i další akce v UI, které jsou povolené ve chvíli, kdy být nemají, a oprav je. Hlavně:
- `components/runs/RunDetail.vue` a `components/runs/FailureCard.vue`: Opakovat, Pokračovat, Přepnout harness a Povolit writes u staršího selhaného běhu, když stejný task právě běží jiným během (backend vrátí `already_running`). Pokud detail běhu nezná stav tasku, nech akci povolenou a jen srozumitelně ukaž chybu 409.
- `components/backlog/KanbanBoard.vue` (`canDrag`): ověř, že běžící task nejde přetáhnout.
- Každou další nalezenou nekonzistenci, kterou neopravíš, popiš v reportu běhu jako follow_up.

Tvrdá omezení:
- Neměň backend, ten řeší HAIFA-REFINEMENT-T61.
- Po změně Vue zdrojů přegeneruj statický build dashboardu v `aifactory/src/aifactory/web/static/` přes `just web-build` a commitni ho.

Hotovo znamená:
- `TaskDetail.test.ts` ověří, že u tasku v `running`, `in review` a `awaiting merge` jsou Spustit, Upravit, Vylepšit agentem, Hotovo a odebrání vazby zakázané a mají tooltip. Pro `ready` zůstávají povolené.
- `TaskDetail.test.ts` ověří, že u tasku v `blocked` je Spustit zakázané s tooltipem se seznamem blokátorů a Upravit je povolené. Když všechny blokátory čekají v otevřeném PR, Spustit je povolené.
- Test ověří, že otevřený formulář úprav se zavře, když detail přijde se stavem `running`.
- `RunDialog.test.ts` ověří, že při nesplněných závislostech bez `stack` nejde task spustit žádným tlačítkem a se `stack` jde spustit normálně.
- Testy upravených komponent (`RunDetail.test.ts`, `FailureCard.test.ts`, `KanbanBoard.test.ts`) pokrývají nové chování a projdou.
- Statický build v `aifactory/src/aifactory/web/static/` odpovídá zdrojům.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-20 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/131 · náklady $0.00
