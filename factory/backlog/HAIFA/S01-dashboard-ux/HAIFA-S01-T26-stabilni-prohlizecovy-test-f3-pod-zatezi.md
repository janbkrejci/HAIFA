---
id: HAIFA-S01-T26
title: Stabilní prohlížečový test F3 pod zátěží
status: done
workflow: plan-build-test
depends_on: []
---

## Zadání
Zpevni prohlížečový test F3: pod zátěží stroje selhává, protože na odkaz na spuštěný běh čeká jen 15 s. Od HAIFA-S01-T09 se běh z dashboardu spouští jako samostatný proces `factory task`, jehož start trvá déle.

Where: `aifactory/tests/e2e/test_f3_browser.py`, případně pomocné funkce testu v `aifactory/tests/e2e/`.

Done means:
- Čekání na start běhu a na další kroky, které závisí na podprocesu, má limit podle skutečné doby startu (např. 90 s) a test místo pevných pauz čeká na stav v UI nebo v API.
- Test projde 5× po sobě (`just e2e`) a při selhání vypíše stav běhu z API, aby bylo vidět, na čem čekal.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: změna chování dashboardu, zrychlení startu běhu.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow plan-build-test · PR https://github.com/janbkrejci/HAIFA/pull/10 · náklady $1.14
