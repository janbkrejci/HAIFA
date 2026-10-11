---
id: HAIFA-S01-T24
title: "Backlog: skrýt hotové a stav Bez workflow"
status: done
depends_on: [HAIFA-S01-T07]
---

## Zadání
Přidej na obrazovku Backlog přepínač Skrýt hotové a přejmenuj stav K přípravě na Bez workflow.

Where: `aifactory/web/src/` (`views/BacklogView.vue`, `components/backlog/` (filtry, strom, kanban, graf), `lib/backlog.ts`), `aifactory/src/aifactory/web/backlog.py` (jen pokud je potřeba), testy v `aifactory/web/src/` a `aifactory/tests/web/`.

Done means:
- Přepínač „Skrýt hotové“ ve filtrech Backlogu schová ze stromu, kanbanu i grafu tasky ve stavu Hotovo a Zrušeno. Projekt a step, kterým nezůstane žádný viditelný task, se ve stromu nezobrazí. Výchozí je vypnuto a prohlížeč si volbu pamatuje.
- Stav `todo` (task, který není hotový ani blokovaný, ale nemá workflow vlastní ani zděděné) se v dashboardu jmenuje „Bez workflow“ a má tooltip „Task nejde spustit, dokud nemá workflow (vlastní nebo zděděné z projektu či stepu).“ Sloupec v kanbanu a volba ve filtru stavu se ukážou jen tehdy, když v tom stavu nějaký task je.
- Testy (vitest): přepínač, paměť volby, skrytí prázdných projektů a stepů, popisek a tooltip Bez workflow, skrytí prázdného sloupce a volby filtru.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: změna odvozování stavu v core, filtr podle projektu a stepu (samostatný task).

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-04 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/42 · náklady $1.80
