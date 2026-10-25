---
id: LEARN-S01-T02
title: "Lekce se stane taskem, který upraví pravidla repa"
status: done
archived: true
depends_on: [LEARN-S01-T01]
---

## Zadání
Zadání:
1. Přijetí lekce (`factory learn accept ID`) založí task v kroku `LEARN` projektu repa (založí ho, pokud chybí) s workflow `build-review`, `writes` jen na cílový soubor pravidel a zadáním z lekce včetně důkazů.
2. Task pak běží běžnou cestou až po PR. Factory sama nic do pravidel nezapisuje.
3. `factory learn dismiss ID` lekci zamítne.

Hotovo znamená:
- Test přijetí a zamítnutí.
- Dotčené testy projdou podle AGENTS.md, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-17 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/88 · náklady $2.97
