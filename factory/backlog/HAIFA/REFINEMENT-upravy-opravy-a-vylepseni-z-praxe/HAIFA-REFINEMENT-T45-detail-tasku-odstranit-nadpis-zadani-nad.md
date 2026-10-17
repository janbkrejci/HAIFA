---
id: HAIFA-REFINEMENT-T45
title: "Detail tasku: odstranit nadpis Zadání nad kartou se záložkami"
status: done
depends_on: []
---

## Zadání
Karta s dokumenty tasku (`components/backlog/TaskDocuments.vue`) má nadpis „Zadání“ a pod ním záložky Zadání a Dokumenty. Nadpis opakuje první záložku a u záložky Dokumenty je zavádějící.

Zadání: nadpis odstranit, záložky zůstávají jako jediné označení karty. Vzhled karty ladí s ostatními kartami detailu.

Hotovo znamená:
- Vitest a browser testy detailu tasku upravené a zelené.
- `just web-test`, `just web-build`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-17 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/92 · náklady $1.07
