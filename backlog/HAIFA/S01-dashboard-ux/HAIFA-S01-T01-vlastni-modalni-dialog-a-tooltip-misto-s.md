---
id: HAIFA-S01-T01
title: Vlastní modální dialog a tooltip místo systémových
status: done
depends_on: []
---

## Zadání
Nepoužívej v dashboardu systémové dialogy, ale vlastní modální dialog, a nativní tooltipy (atribut `title`) nahraď lepším tooltipem ve vzhledu dashboardu.

Where: `aifactory/web/src/` (`App.vue`, `main.ts`, `style.css`, `components/review/ReviewActions.vue`, `components/runs/RunDetail.vue`, `components/backlog/TreeNode.vue`, `components/backlog/TaskDetail.vue`, `components/backlog/DependencyGraph.vue`, `components/runs/PhaseDots.vue`, `components/runs/StatChip.vue`, `views/` a testy), `aifactory/tests/e2e/test_f3_browser.py`, build v `aifactory/src/aifactory/web/static/`.

Done means:
- Frontend nevolá `window.confirm`, `alert` ani `prompt`. Schválit (s textem `approve_note`) a Zastavit se ptají ve vlastním modálním dialogu s tlačítky Potvrdit a Zrušit. Esc a klik mimo dialog ruší, Enter potvrzuje, fokus zůstává v dialogu a po zavření se vrátí na tlačítko.
- Žádný prvek nemá nativní tooltip. Přepínač motivu, cesta k repu, odznak auto, Odebrat vazbu, tečky fází, statistiky a uzly grafu mají vlastní tooltip. Ukáže se při najetí myší i při fokusu z klávesnice, leží nad horní lištou a neořízne ho rolovací kontejner ani SVG grafu.
- Modál i tooltip jsou sdílené komponenty pro celý dashboard.
- Unit testy (vitest): modál vrátí potvrzení i zrušení, Esc zruší, tooltip se ukáže a skryje. Testy, které dnes podvrhují `window.confirm`, potvrzují v modálu.
- Prohlížečový test selže na jakémkoli systémovém dialogu a schválení potvrdí v modálu.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: dropdowny (samostatný úkol), převod panelu Spustit task na modál.

Pevná omezení:
- Žádná nová závislost frontendu, stejné závislosti jako `vendor/sssf/apps/visualizer`.
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-02 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/2 · náklady $3.53
