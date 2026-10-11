---
id: HAIFA-S90-T05
title: OB5 Spolehlivý model na pi
status: done
depends_on: []
---

## Zadání
Podmínka: Spustit až po HAIFA-S05-T05 (načítání kontextu a skillů mění kontext agenta na pi).

Vyber pro harness pi model, který spolehlivě vrací platný JSON envelope (space bunny to nedělal, validace `github-160918`).

Done means:
- Roster s vybraným modelem na pi projde `just validate --remote github` bez `failed`.
- Roster je v `aifactory/validation/rosters/`.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · ručně · `just validate --remote github --roster aifactory/validation/rosters/pi-longcat`: R2, RESOLVE, R3, R4, R5, B1 a F2 passed, R1 a R10 inconclusive (roster bez codexu) · F2 napoprvé failed (model nenalezen v `pi --list-models`), samostatně passed
