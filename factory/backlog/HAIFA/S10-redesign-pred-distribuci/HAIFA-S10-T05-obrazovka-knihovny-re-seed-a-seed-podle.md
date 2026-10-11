---
id: HAIFA-S10-T05
title: "Obrazovka knihovny, re-seed a seed podle sssf"
status: todo
depends_on: [HAIFA-S10-T04]
---

## Zadání
Obrazovka Knihovna (`#/library`) podle nového modelu dědičnosti (HAIFA-S10-T04).

Kde: `aifactory/web/src/views/LibraryView.vue`, `lib/library.ts`, `web/library.py`, `library/reseed.py`, `library/remote.py`.

Hotovo znamená:
- Taby Agenti, Workflow, Skilly, Rozšíření pi. Vlevo seznam objektů knihovny, vpravo pro vybraný objekt repa, která ho přepisují vlastní kopií, s akcemi „Diff“ a „Přesunout kopii repa do knihovny“.
- Tlačítko „Obnovit výchozí agenty a workflows“ (re-seed z balíčku; změněné týmem jen s potvrzením a diffem).
- Seed odpovídá seznamu sssf (agenti planner, builder, reviewer, documenter, scout + tester, test-reviewer; workflow ze sssf včetně build, build-review, build-test, plan-build-test-quality, quality v našem formátu s test_plan) a obsahuje pi rozšíření `subagents.ts` ze sssf.
- Knihovnu (seed) jde synchronizovat s veřejným git repem (pull/push přes remote knihovny), v UI jasně vidět stav.
- `just check` a `just e2e` projdou.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
