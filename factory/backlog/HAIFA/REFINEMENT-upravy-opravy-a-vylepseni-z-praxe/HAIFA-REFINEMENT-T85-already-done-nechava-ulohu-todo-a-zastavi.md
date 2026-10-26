---
id: HAIFA-REFINEMENT-T85
title: "already_done nechá úlohu todo a zastaví řetězec auto-continue"
status: done
depends_on: []
related: [HAIFA-REFINEMENT-T68]
writes: [aifactory/src/aifactory/run/unchanged.py, aifactory/src/aifactory/run/task.py, aifactory/src/aifactory/run/follows.py, aifactory/tests/, aifactory/src/aifactory/run/queue.py, aifactory/src/aifactory/web/backlog.py, aifactory/src/aifactory/run/members.py]
---

## Zadání
Běh, ve kterém builder správně ohlásí `already_done` s evidencí, skončí úspěchem bez PR. Úloha ale v backlogu zůstane `todo`/ready a řetězec auto-continue se po takovém běhu zastaví. Operátor ji pak omylem spustí znovu, protože v dashboardu vypadá jako nehotová.

## Současný stav (naměřeno v NEO_HEF 2026-10-21/22, factory 0.1.478–0.1.482)

- `ROB-TODO-T18` skončila `already_done` (práci udělala `ROB-S04-T003`). Bez PR, řetězec se zastavil.
- `ROB-TODO-T30` (běh `a4e59994`) skončila `already_done`, zůstala `todo` a dashboard ji ukazoval jako ready. Byla dvakrát omylem spuštěna znovu (běhy `1022e580`, `ba2471c7`, oba zastaveny) a nakonec ručně zrušena přes PR.
- Souvisí s HAIFA-REFINEMENT-T68 (success bez změn a bez `already_done`). Tady jde o opačný případ: `already_done` vyplněné je, ale stav úlohy se nezapíše.

## Co udělat

1. Po `already_done` zapsat úlohu do cílové větve jako hotovou (`status: done`, záznam v `## Běhy` s evidencí) stejnou cestou jako u schváleného PR, nebo ji označit stavem, který dashboard i výběr další úlohy berou jako uzavřenou.
2. Řetězec auto-continue po `already_done` pokračovat další úlohou stejně jako po sloučeném PR.
3. Když zápis do cílové větve selže, ukázat to v dashboardu u úlohy, ne ji nechat ready.

## Hotovo znamená

- Úloha skončená `already_done` je v backlogu hotová a řetězec pokračuje.
- Test pokrývá `already_done` v řetězci auto-continue.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-26 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/174 · náklady $0.00
