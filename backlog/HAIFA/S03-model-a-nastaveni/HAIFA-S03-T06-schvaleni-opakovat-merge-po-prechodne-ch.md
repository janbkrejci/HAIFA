---
id: HAIFA-S03-T06
title: "Schválení: opakovat merge po přechodné chybě GitHubu"
status: done
workflow: plan-build-test
depends_on: []
---

## Zadání
Oprav schválení PR na GitHubu: merge po pushi commitu `status: done` občas selže přechodnou chybou GitHubu „Base branch was modified. Review and try the merge again. (mergePullRequest)“, i když se base nezměnila. Stalo se při schválení HAIFA-S01-T02 (PR #3): `factory task approve` skončil `merge_failed` a druhé spuštění o minutu později PR sloučilo.

Where: `aifactory/src/aifactory/providers/github.py`, `aifactory/src/aifactory/review/`, testy v `aifactory/tests/providers/` a `aifactory/tests/review/`.

Done means:
- Když merge vrátí chybu „Base branch was modified“ (nebo jinou přechodnou odpověď GitHubu po aktualizaci větve PR), provider merge po krátké pauze zopakuje s omezeným počtem pokusů, stejně jako u mergeability `unknown`. Teprve po vyčerpání pokusů vrátí `merge_failed`.
- Opakované `factory task approve` po neúspěchu nepřidá druhý commit `status: done` a PR sloučí.
- Skutečný konflikt dál vrací `conflict`, ne opakování.
- Testy proti falešnému `gh`: první merge vrátí „Base branch was modified“, druhý projde; všechny pokusy selžou a výsledek je `merge_failed`; opakovaný approve bez druhého commitu done.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: approve review v hostingu (OB3), provider Azure DevOps.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-02 · workflow plan-build-test · PR https://github.com/janbkrejci/HAIFA/pull/4 · náklady $1.25
