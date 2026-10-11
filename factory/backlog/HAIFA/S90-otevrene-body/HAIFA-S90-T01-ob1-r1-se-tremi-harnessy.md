---
id: HAIFA-S90-T01
title: OB1 R1 se třemi harnessy
status: done
workflow: simple-sdlc
depends_on: []
---

## Zadání
Ověř riziko R1 se třemi harnessy (claude, codex, pi) v jednom workflow.

Podmínka: spustit, až bude kredit na codex a spolehlivý model na pi (OB5). Spustit až po HAIFA-S05-T05 (načítání kontextu a skillů v harnessech), jinak výsledek neplatí pro novou verzi.

Done means:
- `just validate --remote github --roster <roster s claude, codex a pi>` skončí u R1 `passed`.
- Výsledky jsou v `aifactory/validation/results/` a zápis v `docs/decisions.md` uvádí, že je R1 ověřený.

Out of scope: změny produktu, pokud validace projde.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-09 · workflow simple-sdlc · PR https://github.com/janbkrejci/HAIFA/pull/1 · náklady $3.62
