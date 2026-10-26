---
id: HAIFA-REFINEMENT-T83
title: "Navazující úlohy z běhů dostávají duplicitní ID"
status: done
depends_on: []
writes: [aifactory/src/aifactory/backlog/edit.py, aifactory/src/aifactory/run/followups.py, aifactory/tests/, docs/decisions.md, aifactory/src/aifactory/providers/publish.py, aifactory/src/aifactory/review/flow.py, aifactory/src/aifactory/review/automerge.py]
---

## Zadání
Dva souběžné nebo po sobě jdoucí běhy založí navazující úlohu (follow-up) se stejným ID. `factory backlog check` pak hlásí `duplicate_id` a jedna z úloh se musí ručně přečíslovat. Továrna by měla přidělit ID, které v cílové větvi ještě neexistuje.

## Současný stav (naměřeno v NEO_HEF 2026-10-22, factory 0.1.482)

- Běhy `ROB-S31-T004` a `ROB-TODO-T25` založily každý vlastní `ROB-TODO-T53`. Ručně přečíslováno na T54 (PR NEO_HEF #30688).
- Běh `ROB-TODO-T28` startoval z base z doby před tímto přečíslováním a založil další `ROB-TODO-T54`. Ručně přečíslováno na T55 (PR #30691).
- Příčina podle všeho: `backlog/edit.py` `_next_id` počítá další volné číslo z backlogu v worktree běhu. Ten pochází z base v okamžiku startu běhu, a nezná proto úlohy, které mezitím do cílové větve přidaly jiné běhy nebo člověk.

## Co udělat

1. Při zakládání follow-upu (a při merge PR, který follow-up nese) ověřit ID proti aktuální cílové větvi (`origin/<base>` po fetch), ne jen proti worktree běhu.
2. Když se ID srazí, přečíslovat follow-up při merge automaticky na další volné číslo nad maximem a upravit i odkazy (`related`, `depends_on`, `follow-up-of`) v téže změně. Rozhodnutí zapsat do `docs/decisions.md`.
3. Kolize nesmí projít do cílové větve tiše. Když ji továrna nevyřeší, PR nesmí automerge sloučit a dashboard ukáže důvod.

## Hotovo znamená

- Dva běhy, které založí follow-up souběžně, skončí s různými ID bez ručního zásahu.
- Testy pokrývají souběžné založení a běh ze zastaralé base.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-26 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/173 · náklady $0.00
