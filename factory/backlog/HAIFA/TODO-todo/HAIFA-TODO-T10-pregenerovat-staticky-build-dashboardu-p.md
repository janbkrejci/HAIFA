---
id: HAIFA-TODO-T10
title: Přegenerovat statický build dashboardu po T38
status: done
archived: true
depends_on: []
related: [HAIFA-REFINEMENT-T38]
---

## Zadání
Run `just web-build` and commit the regenerated aifactory/src/aifactory/web/static so the shipped dashboard has the new Overview layout (icon buttons in the header, path in a tooltip, last activity at the bottom, uniform card background).

### Původ

Vznikl při běhu `bbcae0b1` tasku `HAIFA-REFINEMENT-T38` (Přehled: tlačítka ovládání jako ikony vpravo nahoře, aktivita dole, jednotné pozadí karet, cesta v tooltipu), v kroku `build` (agent builder).
Důvod: T38 changed the Vue source of the Overview (aifactory/web/src), but aifactory/src/aifactory/web/static is not among the task's allowed paths, so `just web-build` was not run and the shipped dashboard still shows the old layout.

<!-- factory: follow-up-of=HAIFA-REFINEMENT-T38 -->

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-16 · workflow build-test-review · bez změn, běh f39d90bc · náklady $0.53
