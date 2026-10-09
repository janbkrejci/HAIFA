---
id: HAIFA-S03-T15
title: "Schválení: opakovat merge, dokud GitHub počítá mergeabilitu"
status: done
depends_on: []
---

## Zadání
Schválení PR těsně po resolve napoprvé spadlo s „Pull Request is not mergeable“ a druhý pokus prošel. GitHub počítá mergeabilitu po každém pushi asynchronně a do té doby vrací `UNKNOWN`. Po resolve přišly dva pushe rychle po sobě (force-push rebasované větve, pak commit `status: done` od `approve`). `status` v `providers/github.py` čeká na výsledek nejvýš 5× 2 s (`UNKNOWN_ATTEMPTS`, `UNKNOWN_DELAY`), potom `approve` pustí merge při `UNKNOWN` a GitHub ho odmítne. Hláška „not mergeable“ není v `TRANSIENT_MERGE_ERRORS` (HAIFA-S03-T06), takže schválení skončí `merge_failed`.

Where: `aifactory/src/aifactory/providers/github.py`, `aifactory/src/aifactory/review/`, testy v `aifactory/tests/providers/` a `aifactory/tests/review/`.

Done means:
- Merge odmítnutý s „not mergeable“, zatímco je mergeabilita `UNKNOWN`, se po pauze opakuje, dokud GitHub mergeabilitu nespočítá, s omezenou celkovou dobou (desítky sekund). Teprve potom vrátí `merge_failed` s důvodem.
- Před mergem po pushi commitu `status: done` se čeká na spočítanou mergeabilitu stejně dlouho.
- Skutečný konflikt (`CONFLICTING`) dál končí hned jako `conflict`, bez opakování.
- Testy proti falešnému `gh`: „not mergeable“ při `UNKNOWN` a pak úspěch, „not mergeable“ při `CONFLICTING` bez opakování, vyčerpání pokusů dá `merge_failed`.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: provider Azure DevOps, approve review v hostingu (OB3).

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/41 · náklady $0.76
