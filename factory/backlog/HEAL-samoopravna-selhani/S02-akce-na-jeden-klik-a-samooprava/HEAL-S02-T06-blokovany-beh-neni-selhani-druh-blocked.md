---
id: HEAL-S02-T06
title: "Blokovaný běh není selhání: druh blocked, Přehled a Běhy"
status: done
archived: true
depends_on: []
writes: [aifactory/, docs/decisions.md]
---

## Zadání
Běh, ve kterém agent ohlásí blokující follow-up nebo blokující existující task (`blocks_task`, `blocked_by`), dnes končí `failed` s chybou `blocked: task X waits for Y` (`run/task.py` `blocked_reason`, `run_blockers`). Přehled ho ukazuje mezi selhanými a Běhy jako Selhal, i když jde o dočasný stav, který se vyřeší dokončením blokátoru.

Zadání:
1. Nový druh selhání `blocked` v `failure.FAILURE_KINDS`, blokátory ve `failure_detail`. Stav běhu zůstává `failed`, aby retry, řetěz a samooprava fungovaly beze změny. Starší běhy s chybou začínající `blocked: ` se čtou jako `blocked` (stejně jako fallback na `other`).
2. Přehled (`web/overview.py`, seznam `failed` a počty) blokované běhy nezahrnuje.
3. Běhy, detail běhu a karta selhání ukazují výsledek „Blokovaný“ s vlastní barvou a odkazy na blokující tasky. `factory task runs` a `factory task show` vypíšou `blocked` s blokátory.
4. Zapsat do `docs/decisions.md` (Běh tasku): blokovaný běh je druh selhání `blocked`, ne selhání pro Přehled.

Hotovo znamená:
- Test: běh skončený blokací má druh `blocked` a blokátory, starý řádek s prefixem se čte jako `blocked`, Přehled ho nevrací mezi selhanými, skutečné selhání ano.
- Vitest Běhů a karty selhání pro `blocked`.
- Dotčené testy projdou podle AGENTS.md, `just web-test`, `just web-build`, celou sadu ověří CI.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-18 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/107 · náklady $3.03
