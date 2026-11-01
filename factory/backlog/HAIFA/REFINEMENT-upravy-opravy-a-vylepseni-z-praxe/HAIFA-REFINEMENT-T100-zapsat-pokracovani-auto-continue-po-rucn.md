---
id: HAIFA-REFINEMENT-T100
title: Zapsat pokračování auto-continue po ručním sloučení PR do decisions a příručky
status: done
workflow: build-review
depends_on: [HAIFA-REFINEMENT-T98, HAIFA-REFINEMENT-T99]
writes: [docs/decisions.md, aifactory/src/aifactory/guide/05-behy-a-review.md]
---

## Zadání
Po T98 a T99 zapiš nové chování do dokumentace.
- docs/decisions.md: k bodu **Auto-continue** připiš krátké pravidlo. Řetěz zastavený `not_merged` (auto-merge PR nesloučil, například workflow bez review) pokračuje jednou, až člověk PR sloučí přes `factory task approve` nebo dashboard, případně v hostingu (zjistí to obnova PR v dashboardu). Pokračuje se stejnými pravidly výběru jako po auto-merge. Task se sloučeným PR, který je v base stále `todo`, se nespustí, dokud ho nedorovná `factory backlog sync`.
- aifactory/src/aifactory/guide/05-behy-a-review.md: jedna až dvě věty pro uživatele ve stejném duchu, stručně jako zbytek příručky.

Mimo rozsah: kód a testy.

Hotovo znamená:
- docs/decisions.md a 05-behy-a-review.md popisují pokračování po ručním sloučení a odpovídají implementaci z T98 a T99.
- Test souladu příručky (GUIDE-S01-T03) prochází.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-11-01 · workflow build-review · PR https://github.com/janbkrejci/HAIFA/pull/192 · náklady $0.00
