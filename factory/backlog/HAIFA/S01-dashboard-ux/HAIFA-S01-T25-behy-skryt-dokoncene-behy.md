---
id: HAIFA-S01-T25
title: "Běhy: skrýt dokončené běhy"
status: done
depends_on: [HAIFA-S02-T03]
---

## Zadání
Přidej na obrazovku Běhy přepínač, který skryje dokončené běhy.

Where: `aifactory/web/src/` (`views/RunsView.vue`, `components/runs/`, `lib/runs.ts`), testy v `aifactory/web/src/`.

Done means:
- Přepínač „Skrýt dokončené“ v seznamu běhů schová běhy ve stavu úspěch. Běžící, neúspěšné a přerušené běhy zůstanou vidět. Přepínač se kombinuje s filtry stavu a tasku. Výchozí je vypnuto a prohlížeč si volbu pamatuje.
- Součty nákladů dál počítají se všemi běhy.
- Testy (vitest): přepínač, kombinace s filtry, paměť volby, součty beze změny.
- Build frontendu v `aifactory/src/aifactory/web/static/` odpovídá změnám.
- `just test`, `just typecheck`, `just lint` a `just e2e` projdou.

Out of scope: mazání nebo archivace běhů, změna API běhů.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/33 · náklady $1.12
