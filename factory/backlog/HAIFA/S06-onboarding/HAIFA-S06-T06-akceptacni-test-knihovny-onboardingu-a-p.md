---
id: HAIFA-S06-T06
title: "Akceptační test knihovny, onboardingu a převzetí"
status: done
workflow: plan-build-test
depends_on: [HAIFA-S06-T05]
---

## Zadání
Přidej prohlížečový akceptační test týmového toku nad `factory obs` s falešným harnessem: první spuštění, týmová knihovna, jednorázové vytěžení repa sssf, běh se skillem a převzetí na druhém stroji (druhý `HAIFA_HOME`). Vzor jsou akceptační testy F3 a M15.

Where: `aifactory/tests/e2e/` (`f3_repo.py`, `test_f3_browser.py` a test z M15 jako vzor), `aifactory/validation/` (`worker.py`, `fake.py`).

Done means:
- Test začne s prázdným `HAIFA_HOME` A a dashboard otevře Tento počítač. Založí knihovnu ze semínka s holým remote.
- Přidá repo s fixturou sssf, backlogem s jedním taskem a holým remote, projde náhled onboardingu a potvrdí ho. Commit knihovny je v jejím remote dřív než commit repa v remote repa.
- Na záložce Factory přidá skill z knihovny builderovi a commitne ho. Spustí task a uložený system prompt fáze build obsahuje rejstřík se skillem.
- Ve druhém `HAIFA_HOME` B naklonuje knihovnu, přidá klon repa a dashboard ukáže Onboardováno bez nabídky vytěžení. Převzetí nic nezapíše do repa (`git status`, refy a soubory beze změny).
- V B test upraví prompt v klonu repa, commitne ho a na záložce Factory ho exportuje do knihovny. V A po Pull ukáže Knihovna novou verzi a repo stav `outdated`.
- Žádný systémový dialog, žádný požadavek mimo server a žádný skutečný harness (tripwire jako v F3).
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: GitHub a Azure DevOps, skutečné modely, `factory upgrade`.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-08 · workflow plan-build-test · PR https://github.com/janbkrejci/HAIFA/pull/96 · náklady $0.00
