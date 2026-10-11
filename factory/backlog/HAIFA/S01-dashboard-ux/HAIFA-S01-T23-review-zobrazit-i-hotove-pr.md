---
id: HAIFA-S01-T23
title: "Review: zobrazit i hotové PR"
status: done
depends_on: [HAIFA-S01-T04]
---

## Zadání
Přidej na obrazovku Review volbu, která ukáže i hotové PR tasků (sloučené a zavřené).

Where: `aifactory/web/src/` (`views/ReviewView.vue`, `components/review/`, `lib/review.ts`), `aifactory/src/aifactory/web/review.py`, testy v `aifactory/web/src/` a `aifactory/tests/web/`.

Done means:
- Volba „Zobrazit hotové“ přidá pod otevřené PR sekci „Hotové“ se sloučenými a zavřenými PR tasků z `task_prs`, nejnovější nahoře, se stavem (sloučeno, zavřeno), datem a odkazem na PR. Výchozí je vypnuto a prohlížeč si volbu pamatuje.
- Detail hotového PR je jen pro čtení: Schválit, Vrátit, Vyřešit konflikt ani Dorovnat s base nejsou dostupné.
- API Review vrací hotové PR jen na vyžádání parametrem, výchozí odpověď se nemění.
- Testy (vitest) volby, sekce a detailu jen pro čtení a test API (pytest) s parametrem i bez něj.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: mazání nebo archivace PR, změna toku schválení.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/19 · náklady $2.64
