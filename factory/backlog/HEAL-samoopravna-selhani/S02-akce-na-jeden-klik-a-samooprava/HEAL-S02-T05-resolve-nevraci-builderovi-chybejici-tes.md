---
id: HEAL-S02-T05
title: "Resolve nevrací builderovi chybějící testy, které nesmí zapsat"
status: done
archived: true
depends_on: []
---

## Zadání
Auto-resolve PR #75 (HEAL-S02-T04, běh c6773833) selhal, i když rebase a přebuild bundlu prošly. Workflow `resolve` znovu posoudilo testovací plán celého tasku, revize testů vrátila chybějící test (migrace sloupce `task_chains.events` do `tests/run/test_chain_parts.py`) a `test_fix` ho zapsal. Resolve ale smí měnit jen konfliktní soubory, tady žádné (konflikt byl jen v generovaném bundlu), takže guard zápis vrátil a běh selhal (`writes_violation`).

Zadání:
1. V běhu `resolve` revize testů neposílá builderovi chybějící testy. Kontroluje jen, že plán pokrývá obě strany rebase. Chybějící test, který při resolve najde, ohlásí jako follow-up tasku (TODO step projektu), ne jako opravu v běhu.
2. Kroky `fix` a `test_fix` v resolve se nespustí, když povolená množina souborů je prázdná. Selhání testů pak běh ukončí s jasným důvodem místo `writes_violation`.

Hotovo znamená:
- Test s fake harnessem: resolve s konfliktem jen v `generated:` výstupu a revizí testů, která hlásí chybějící test, doběhne, vznikne follow-up a guard nic nevrací.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-16 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/78 · náklady $3.22
