---
id: HAIFA-S03-T14
title: "Souběžné běhy: fáze test čeká na volný slot"
status: done
depends_on: []
---

## Zadání
Stroj má 4 jádra a každý běh pouští celou sadu přes `pytest -n auto` (4 workery) a vitest. Při 4–5 souběžných bězích je CPU několikanásobně přetížené: fáze test trvá 17–25 minut místo zhruba 7, překračuje `test_timeout` 1 500 s (HAIFA-S03-T11 resolve skončil kódem 124) a časově citlivé testy kolísají (HAIFA-S01-T27: `test_web_launcher`, `test_web_live`).

Where: krok test (spuštění testovacího příkazu v `aifactory/src/aifactory/workflow/` a `aifactory/src/aifactory/engine/runner.py`), konfigurace v `aifactory/src/aifactory/config/`, trace a dashboard (stav fáze), testy.

Done means:
- Konfigurace `test_slots` (výchozí 1) omezuje, kolik fází test běží na stroji naráz. Ostatní běhy čekají ve frontě v pořadí, v jakém o slot požádaly.
- Čekání je vidět v trace i v dashboardu (fáze test čeká na slot, kolik běhů je před ní).
- Čekání se nepočítá do `test_timeout`. Limit platí jen pro samotný běh testů.
- Slot se uvolní i při pádu, zastavení nebo zabití běhu. Slot držený mrtvým procesem se sám uvolní.
- Testy: dva souběžné běhy se slotem 1 testují jeden po druhém, timeout nezahrnuje čekání, zabitý proces slot uvolní.
- `just test`, `just typecheck` a `just lint` projdou.

Out of scope: limit souběžných běhů jako celku, plánovač tasků.

Pevná omezení:
- `vendor/` a `prototype/` se nemění.
- Testy nevolají model ani síť.

## Běhy
<!-- doplňuje HAIFA při schválení PR -->
- 2026-10-03 · workflow build-test-review · PR https://github.com/janbkrejci/HAIFA/pull/29 · náklady $2.89
