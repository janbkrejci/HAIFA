---
id: HAIFA-S01-T22
title: Akceptační test více repozitářů v prohlížeči
status: done
workflow: plan-build-test
depends_on: [HAIFA-S01-T21]
---

## Zadání
Přidej prohlížečový akceptační test celého toku více repozitářů nad `factory obs` s falešným harnessem, od prázdného dashboardu po odebrání repa (vzor: akceptační test F3).

Where: `aifactory/tests/e2e/` (`f3_repo.py`, `test_f3_browser.py` jako vzor), `aifactory/validation/` (`worker.py`, `fake.py`).

Done means:
- Test začne s prázdným `HAIFA_HOME` a dashboard ukáže prázdný stav.
- Přidá repo A s factory napsáním cesty, pak repo B bez factory, projde plán instalace a potvrdí ho. Commit instalace je v logu B i v jeho holém remote.
- Přepne mezi A a B a obrazovka zůstane stejná.
- Spustí task v A. Přehled ukáže běh s fází a potom PR čekající na review.
- Odebere B. `git status`, refy a soubory B jsou stejné jako před odebráním.
- Žádný systémový dialog, žádný požadavek mimo server a žádný skutečný harness (tripwire jako v F3).
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: běh proti GitHubu a Azure DevOps, nativní dialog, skutečné modely.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-07 · workflow plan-build-test · PR https://github.com/janbkrejci/HAIFA/pull/81 · náklady $0.00
