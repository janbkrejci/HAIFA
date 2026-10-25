---
id: START-S01-T02
title: Vyzkoušet na ukázce z prázdného Přehledu
status: done
archived: true
depends_on: [START-S01-T01]
---

## Zadání
Zadání:
1. Prázdný Přehled (žádné repo) a konec průvodce nastavením nabídnou „Vyzkoušet na ukázce“ vedle „Přidat repozitář“.
2. Tlačítko vytvoří ukázku, otevře její backlog a spustí první task s prvním otestovaným harnessem.
3. Během běhu krátké vysvětlivky u detailu běhu ukážou, co se děje (worktree, build, test, review, PR, merge). Po merge nabídnou přidání vlastního repa.
4. Ukázku jde odebrat jedním tlačítkem včetně adresáře.

Hotovo znamená:
- Vitest, browser test od prázdného Přehledu po hotový běh s fake harnessem.
- `just web-test`, `just web-build`, dotčené testy podle AGENTS.md.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-17 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/85 · náklady $6.16
