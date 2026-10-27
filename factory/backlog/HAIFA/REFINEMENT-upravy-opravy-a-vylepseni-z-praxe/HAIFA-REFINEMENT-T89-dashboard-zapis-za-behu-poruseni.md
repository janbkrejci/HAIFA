---
id: HAIFA-REFINEMENT-T89
title: Úprava backlogu z dashboardu za běhu se přičte agentovi jako porušení
status: done
depends_on: []
writes: [aifactory/src/aifactory/run/, aifactory/src/aifactory/web/, aifactory/src/aifactory/backlog/, aifactory/tests/, aifactory/web/src/lib/backlog.ts, aifactory/web/src/lib/backlog.test.ts, aifactory/web/src/lib/backlogStatus.ts, aifactory/web/src/App.vue, aifactory/web/src/App.test.ts, aifactory/web/src/components/UncommittedBanner.vue, aifactory/web/src/components/UncommittedBanner.test.ts, aifactory/web/src/views/BacklogView.vue, aifactory/web/src/views/BacklogView.test.ts]
---

## Zadání
Úprava backlogu z dashboardu (archivace úlohy) během živého běhu se v hlavním checkoutu započítá agentovi jako porušení a shodí jeho fázi.

## Současný stav (naměřeno v NEO_HEF 2026-10-26, factory 0.1.537)

- Během resolve běhu `7f9d9512` (`task retry ROB-TODO-T46`, 17:21–17:39) operátor v dashboardu archivoval `ROB-TODO-T50` a `ROB-TODO-T53` (`archived: true` v hlavním checkoutu).
- Fáze `resolve` po úspěšném vyřešení konfliktu skončila `permission_breach`: „main checkout: factory/backlog/…/ROB-TODO-T50-….md — changed by the agent before a factory write; factory content kept“ (totéž T53). Agent ty soubory neměnil.
- V tomtéž výpisu byl i pohyb `HEAD` hlavního checkoutu (ruční `git pull` mimo továrnu). Ten je porušení oprávněně, archivace z dashboardu ne.
- Současně `factory backlog commit` z dashboardu sloučil PR, ale lokální base neposunul (živý běh), chip zůstal a varování „run factory config pull“ dashboard neukázal.

## Co udělat

1. Zápisy, které do hlavního checkoutu udělá dashboard nebo CLI továrny (task edit, archivace), zapisovat do journalu jako zápisy továrny, aby se agentovi nepřičítaly.
2. Pokud to nejde, dashboard má úpravy backlogu za živého běhu blokovat nebo před nimi varovat.
3. Po `backlog commit` v dashboardu ukázat varování, že base se neposunul kvůli živému běhu a co udělat po jeho konci.

## Hotovo znamená

- Archivace úlohy v dashboardu za živého běhu ho neshodí.
- Dashboard ukáže, že base po `backlog commit` čeká na `config pull`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-27 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/178 · náklady $0.00
